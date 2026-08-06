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

    Implementation note — why every column is assembled into a dict
    before the DataFrame is built, instead of the more obvious
    ``feat["x"] = ...`` assigned incrementally as each is computed
    --------------------------------------------------------------------
    Root-cause fix (found live, 2026-08-06): the previous version built
    `feat` as an empty `pd.DataFrame(index=df.index)` and added all 19
    columns one at a time via `feat["name"] = series`. Under pandas 3.0.3,
    each of those assignments calls through to `Index.insert()` to grow
    the DataFrame's *column* index by one label — and in a long-running
    process calling this function roughly 5x/second, that per-column
    `Index.insert()` cost was observed to become catastrophic: `py-spy
    dump` caught the live engine's event loop stuck inside exactly this
    call chain (`compute_features` -> `DataFrame.__setitem__` -> `_set_item`
    -> `Index.insert()`) for 20+ minutes at 97-100% CPU with zero forward
    progress, on three separate live incidents the same day. It did not
    reproduce in an isolated benchmark script (fresh process, single
    call) even against the full 22,781-row real cache — strongly
    suggesting the cost is cumulative across many repeated `Index.insert()`
    calls within one process's lifetime (a known category of issue with
    pandas' PyArrow-backed string dtype machinery), not a function of
    input size. See `docs/paper_trading_validation/anomaly_log.md`'s
    2026-08-06 entries for the full incident.

    Building every column into a plain `dict[str, Series]` first and
    constructing the DataFrame with all columns already known
    (`pd.DataFrame(columns_dict, index=df.index)`) means the column index
    is built exactly once, via a single fast array conversion, instead of
    via 19 sequential `Index.insert()` calls — eliminating the exact code
    path every incident traced back to, regardless of the deeper
    pandas/pyarrow mechanism. This is also a well-known general pandas
    performance best practice independent of this specific incident.
    """
    close = df["close"]
    high = df["high"]
    low = df["low"]
    volume = df["volume"]

    columns: dict[str, pd.Series] = {}

    # --- Price action features ---
    columns["return_1"] = close.pct_change(1)
    columns["return_3"] = close.pct_change(3)
    columns["return_5"] = close.pct_change(5)

    # Candle body ratio (body / range)
    candle_range = high - low
    candle_body = (close - df["open"]).abs()
    columns["body_ratio"] = np.where(candle_range > 0, candle_body / candle_range, 0)

    # Upper and lower shadow ratios
    columns["upper_shadow"] = np.where(
        candle_range > 0,
        (high - np.maximum(close, df["open"])) / candle_range,
        0,
    )
    columns["lower_shadow"] = np.where(
        candle_range > 0,
        (np.minimum(close, df["open"]) - low) / candle_range,
        0,
    )

    # --- EMA features ---
    ema9 = ema(close, window=9)
    ema21 = ema(close, window=21)
    columns["ema_fast_slow_diff"] = (ema9 - ema21) / ema21 * 100  # percentage gap
    columns["price_vs_ema9"] = (close - ema9) / ema9 * 100
    columns["price_vs_ema21"] = (close - ema21) / ema21 * 100

    # --- RSI feature ---
    # rsi()'s ewm(adjust=False)-based smoothing does not produce NaN
    # during its warm-up period (see shared/indicators/rsi.py's
    # docstring) — its first `window` values are numerically valid but
    # come from a still-converging average, which would otherwise reach
    # this function's ML feature matrix as noise the feat.dropna() call
    # below is specifically meant to filter out. Mask them explicitly so
    # dropna() actually removes them, matching this function's own
    # documented "rows with NaN (warmup period) are dropped" contract.
    rsi_14 = rsi(close, window=14)
    rsi_14.iloc[:14] = np.nan
    columns["rsi_14"] = rsi_14

    rsi_7 = rsi(close, window=7)
    rsi_7.iloc[:7] = np.nan
    columns["rsi_7"] = rsi_7

    # --- Volatility features ---
    atr_14 = _atr(high, low, close, window=14)
    columns["atr_14"] = atr_14
    columns["atr_pct"] = atr_14 / close * 100  # ATR as % of price
    columns["volatility_5"] = close.rolling(5).std() / close * 100

    # --- Volume features ---
    vol_ma = volume.rolling(20, min_periods=1).mean()
    columns["volume_ratio"] = np.where(vol_ma > 0, volume / vol_ma, 1.0)
    columns["volume_change"] = volume.pct_change(1)

    # --- Momentum features ---
    columns["momentum_10"] = close / close.shift(10) - 1
    columns["roc_5"] = (close - close.shift(5)) / close.shift(5) * 100

    # --- Trend strength ---
    columns["adx_14"] = _adx(high, low, close, window=14)

    feat = pd.DataFrame(columns, index=df.index)

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

    plus_di = pd.Series(plus_dm, index=high.index).rolling(window, min_periods=1).mean() / (atr + 1e-9) * 100
    minus_di = pd.Series(minus_dm, index=high.index).rolling(window, min_periods=1).mean() / (atr + 1e-9) * 100

    dx = (plus_di - minus_di).abs() / (plus_di + minus_di + 1e-10) * 100
    adx = dx.rolling(window, min_periods=1).mean()
    return adx
