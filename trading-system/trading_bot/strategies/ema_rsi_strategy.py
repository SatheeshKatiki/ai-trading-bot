"""EMA + RSI Trend Strategy.

This module implements the EMA + RSI based intraday strategy. It provides a
``generate_signals`` function that receives a ``pandas.DataFrame`` with OHLCV
columns and returns a ``Series`` of signals:

* ``1``  - BUY signal
* ``-1`` - SELL signal
* ``0``  - NO TRADE

The logic follows the rules:

* **Buy** when EMA_fast > EMA_slow, RSI > buy threshold, and volume is above
  the recent average (simple volatility filter).
* **Sell** when EMA_fast < EMA_slow and RSI < sell threshold.
* Otherwise, no trade.
"""

from __future__ import annotations

import pandas as pd

from shared.indicators import ema, rsi

# Type alias for readability
DataFrame = pd.DataFrame

STRATEGY_NAME = "ema_rsi"


def _volume_filter(df: DataFrame, lookback: int = 20) -> pd.Series:
    """Return a boolean mask where volume exceeds its ``lookback``-period average.

    The lookback defaults to 20 periods (minutes for 1-minute candles).
    If volume is constant (e.g. mocked data), the filter is bypassed (all True).
    """
    # If volume has zero variance (constant/mocked), bypass the filter
    if df["volume"].nunique() <= 1:
        return pd.Series(True, index=df.index)
    vol_avg = df["volume"].rolling(window=lookback, min_periods=1).mean()
    return df["volume"] >= vol_avg


def generate_signals(
    df: DataFrame,
    ema_fast: int = 20,
    ema_slow: int = 50,
    rsi_window: int = 14,
    rsi_buy_thresh: float = 55,
    rsi_sell_thresh: float = 45,
    **kwargs
) -> pd.Series:
    """Generate trade signals for the EMA + RSI strategy.

    Parameters
    ----------
    df : pandas.DataFrame
        Must contain ``close`` and ``volume`` columns.
    ema_fast : int
        Fast EMA window (default 20).
    ema_slow : int
        Slow EMA window (default 50).
    rsi_window : int
        RSI lookback period (default 14).
    rsi_buy_thresh : float
        RSI value above which a buy is allowed (default 55).
    rsi_sell_thresh : float
        RSI value below which a sell is triggered (default 45).

    Returns
    -------
    pandas.Series[int]
        ``1`` (buy), ``-1`` (sell), or ``0`` (no trade).
    """
    df["ema_fast"] = ema(df["close"], window=ema_fast)
    df["ema_slow"] = ema(df["close"], window=ema_slow)
    df["rsi"] = rsi(df["close"], window=rsi_window)
    
    # Add Supertrend for extra confirmation
    from shared.indicators import supertrend
    st_df = supertrend(df, period=10, multiplier=3.0)
    df["st_direction"] = st_df["direction"]

    bullish = (df["ema_fast"] > df["ema_slow"]) & (df["rsi"] > rsi_buy_thresh) & (df["st_direction"] == 1) & _volume_filter(df)
    bearish = (df["ema_fast"] < df["ema_slow"]) & (df["rsi"] < rsi_sell_thresh) & (df["st_direction"] == -1) & _volume_filter(df)

    signals = pd.Series(0, index=df.index, dtype=int)
    signals[bullish] = 1
    signals[bearish] = -1
    return signals
