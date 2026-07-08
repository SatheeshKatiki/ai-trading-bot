"""AI Feature Engineering for trade signal filtering.

Extracts features from OHLCV data that are fed into the ML model to score
trade confidence. Features capture price action, momentum, volatility, and
volume dynamics.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from shared.indicators import ema, rsi


def compute_features(df: pd.DataFrame) -> pd.DataFrame:
    """Compute ML features from an OHLCV DataFrame.

    Parameters
    ----------
    df : pandas.DataFrame
        Must contain columns: open, high, low, close, volume.

    Returns
    -------
    pandas.DataFrame
        Feature matrix aligned with ``df`` index. Rows with NaN (warmup
        period) are dropped.
    """
    feat = pd.DataFrame(index=df.index)

    close = df["close"]
    high = df["high"]
    low = df["low"]
    volume = df["volume"]

    # --- Price action features ---
    feat["return_1"] = close.pct_change(1)
    feat["return_3"] = close.pct_change(3)
    feat["return_5"] = close.pct_change(5)

    # Candle body ratio (body / range)
    candle_range = high - low
    candle_body = (close - df["open"]).abs()
    feat["body_ratio"] = np.where(candle_range > 0, candle_body / candle_range, 0)

    # Upper and lower shadow ratios
    feat["upper_shadow"] = np.where(
        candle_range > 0,
        (high - np.maximum(close, df["open"])) / candle_range,
        0,
    )
    feat["lower_shadow"] = np.where(
        candle_range > 0,
        (np.minimum(close, df["open"]) - low) / candle_range,
        0,
    )

    # --- EMA features ---
    ema9 = ema(close, window=9)
    ema21 = ema(close, window=21)
    feat["ema_fast_slow_diff"] = (ema9 - ema21) / ema21 * 100  # percentage gap
    feat["price_vs_ema9"] = (close - ema9) / ema9 * 100
    feat["price_vs_ema21"] = (close - ema21) / ema21 * 100

    # --- RSI feature ---
    feat["rsi_14"] = rsi(close, window=14)
    feat["rsi_7"] = rsi(close, window=7)

    # --- Volatility features ---
    feat["atr_14"] = _atr(high, low, close, window=14)
    feat["atr_pct"] = feat["atr_14"] / close * 100  # ATR as % of price
    feat["volatility_5"] = close.rolling(5).std() / close * 100

    # --- Volume features ---
    vol_ma = volume.rolling(20, min_periods=1).mean()
    feat["volume_ratio"] = np.where(vol_ma > 0, volume / vol_ma, 1.0)
    feat["volume_change"] = volume.pct_change(1)

    # --- Momentum features ---
    feat["momentum_10"] = close / close.shift(10) - 1
    feat["roc_5"] = (close - close.shift(5)) / close.shift(5) * 100

    # --- Trend strength ---
    feat["adx_14"] = _adx(high, low, close, window=14)

    # Replace inf/-inf with 0.0 (caused by division-by-zero in pct_change,
    # volume_ratio, ATR/ADX when denominators are zero), to avoid dropping
    # rows during illiquid flat-volume periods. Then drop structural NaN rows.
    feat.replace([np.inf, -np.inf], 0.0, inplace=True)
    return feat.dropna()


def _atr(high: pd.Series, low: pd.Series, close: pd.Series, window: int = 14) -> pd.Series:
    """Average True Range."""
    prev_close = close.shift(1)
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low - prev_close).abs(),
    ], axis=1).max(axis=1)
    return tr.rolling(window=window, min_periods=1).mean()


def _adx(high: pd.Series, low: pd.Series, close: pd.Series, window: int = 14) -> pd.Series:
    """Average Directional Index (simplified)."""
    prev_high = high.shift(1)
    prev_low = low.shift(1)

    plus_dm = np.where((high - prev_high) > (prev_low - low), np.maximum(high - prev_high, 0), 0)
    minus_dm = np.where((prev_low - low) > (high - prev_high), np.maximum(prev_low - low, 0), 0)

    atr = _atr(high, low, close, window)

    plus_di = pd.Series(plus_dm, index=high.index).rolling(window, min_periods=1).mean() / atr * 100
    minus_di = pd.Series(minus_dm, index=high.index).rolling(window, min_periods=1).mean() / atr * 100

    dx = (plus_di - minus_di).abs() / (plus_di + minus_di + 1e-10) * 100
    adx = dx.rolling(window, min_periods=1).mean()
    return adx
