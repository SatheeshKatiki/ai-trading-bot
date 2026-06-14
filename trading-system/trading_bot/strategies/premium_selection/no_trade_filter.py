"""No-Trade Filter — Time, Choppiness, and Session Guards.

Institutional rule: Capital protection over trade frequency.
The engine must know WHEN NOT to trade as well as when to trade.
"""
from __future__ import annotations
import pandas as pd
from datetime import time


# --- Configurable No-Trade Windows (IST) ---
NO_TRADE_WINDOWS = [
    (time(9, 15), time(9, 30)),    # Opening auction volatility
    (time(12, 0), time(13, 0)),    # Lunch dead zone
    (time(15, 0), time(15, 30)),   # Square-off pressure / close
]

PREFERRED_WINDOWS = [
    (time(9, 30), time(11, 30)),   # Best momentum window
    (time(13, 0), time(15, 0)),    # Afternoon trend window
]


def _is_in_no_trade_window(ts: pd.Timestamp) -> bool:
    """Check if a timestamp falls in a no-trade window."""
    t = ts.time()
    for start, end in NO_TRADE_WINDOWS:
        if start <= t <= end:
            return True
    return False


def _choppiness_index(df: pd.DataFrame, window: int = 14) -> pd.Series:
    """
    Choppiness Index (0-100):
      < 38.2 = Strong trending market
      > 61.8 = Choppy / sideways market
    """
    atr_sum = (df["high"] - df["low"]).rolling(window).sum()
    highest_high = df["high"].rolling(window).max()
    lowest_low   = df["low"].rolling(window).min()
    price_range  = (highest_high - lowest_low).replace(0, 1e-9)

    ci = 100 * (atr_sum / price_range) / window
    return ci.clip(0, 100)


def compute_no_trade_conditions(df: pd.DataFrame) -> pd.DataFrame:
    """
    Computes time-based and market-condition-based no-trade flags.

    Returns DataFrame with columns:
      - choppiness_index  : 0-100 (>61.8 = choppy, avoid)
      - is_trending       : True when CI < 38.2 (strong trend)
      - in_no_trade_window: True during restricted time windows
      - no_trade          : True = SKIP this bar entirely
    """
    df = df.copy()

    # Choppiness index
    df["choppiness_index"] = _choppiness_index(df)
    df["is_trending"]      = df["choppiness_index"] < 61.8   # Not choppy

    # Time filter (only applies if index has datetime information)
    if hasattr(df.index, "hour"):
        df["in_no_trade_window"] = df.index.to_series().apply(_is_in_no_trade_window)
    elif "timestamp" in df.columns:
        df["in_no_trade_window"] = pd.to_datetime(df["timestamp"]).apply(_is_in_no_trade_window)
    else:
        df["in_no_trade_window"] = False

    # Flat market: if last 5 closes within 0.1% range = sideways (vectorized optimization)
    max_close = df["close"].rolling(5).max()
    min_close = df["close"].rolling(5).min()
    mean_close = df["close"].rolling(5).mean().replace(0, 1e-9)
    close_range = (max_close - min_close) / mean_close
    df["is_sideways"] = close_range < 0.001

    # Combined no-trade flag
    df["no_trade"] = df["in_no_trade_window"] | ~df["is_trending"] | df["is_sideways"]

    return df
