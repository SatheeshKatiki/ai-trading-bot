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
    For live indices where websocket volume is 0, the filter is also bypassed.
    """
    # If volume has zero variance (constant/mocked), bypass the filter
    if df["volume"].nunique() <= 1:
        return pd.Series(True, index=df.index)
    vol_avg = df["volume"].rolling(window=lookback, min_periods=1).mean()
    # Bypass filter if the live candle volume is exactly 0 (due to index WS missing volume)
    return (df["volume"] >= vol_avg) | (df["volume"] == 0)


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
    # Root-cause fix (found live, 2026-08-06): these used to be written
    # straight into the caller's `df` one column at a time
    # (`df["ema_fast"] = ...`, `df["ema_slow"] = ...`, ...). `df` here is
    # `main.py`'s live CandleAggregator's own stored dataframe, and this
    # function runs on it roughly every 0.2s for the active symbol — each
    # incremental `df["new_col"] = ...` assignment calls through to
    # pandas' `Index.insert()` to grow the column index by one label, and
    # under pandas 3.0.3 that per-call cost was observed to become
    # catastrophic in a long-running process: `py-spy dump` caught the
    # live engine's event loop stuck inside exactly this class of call
    # chain for 20+ minutes at 97-100% CPU with zero forward progress, on
    # three separate live incidents the same day (root-caused primarily
    # to the identical pattern in shared/ai/features.py — see that
    # module's docstring and docs/paper_trading_validation/anomaly_log.md's
    # 2026-08-06 entries for the full incident). Computing into local
    # variables and only ever reading `close`/`rsi_series`/etc. (never
    # `df["ema_fast"]`) avoids the same class of bug here too, since
    # nothing downstream of this function actually needs these values
    # written back onto `df`.
    close = df["close"]
    ema_fast_series = ema(close, window=ema_fast)
    ema_slow_series = ema(close, window=ema_slow)
    rsi_series = rsi(close, window=rsi_window)

    # Add Supertrend for extra confirmation
    from shared.indicators import supertrend
    st_df = supertrend(df, period=10, multiplier=3.0)
    st_direction = st_df["direction"]

    bullish = (ema_fast_series > ema_slow_series) & (rsi_series > rsi_buy_thresh) & (st_direction == 1) & _volume_filter(df)
    bearish = (ema_fast_series < ema_slow_series) & (rsi_series < rsi_sell_thresh) & (st_direction == -1) & _volume_filter(df)

    signals = pd.Series(0, index=df.index, dtype=int)
    signals[bullish] = 1
    signals[bearish] = -1
    return signals
