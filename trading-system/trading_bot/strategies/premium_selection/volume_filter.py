"""Volume Filter — confirms genuine market participation.

Institutional rule: Never trade low-volume breakouts. Volume must lead price.
"""
from __future__ import annotations
import pandas as pd


def compute_volume(df: pd.DataFrame, lookback: int = 20) -> pd.DataFrame:
    """
    Validates volume participation.

    Returns DataFrame with columns:
      - vol_avg           : rolling 20-period average volume
      - vol_ratio         : current volume / vol_avg
      - vol_spike         : True if vol_ratio > 1.5 (breakout participation)
      - vol_consecutive   : True if last 2 bars both above average (sustained)
      - volume_confirmed  : True when volume is genuinely strong
    """
    df = df.copy()

    # Skip if volume is mocked / constant (NIFTY index data)
    if df["volume"].nunique() <= 2:
        df["vol_avg"]          = df["volume"]
        df["vol_ratio"]        = 1.0
        df["vol_spike"]        = True
        df["vol_consecutive"]  = True
        df["volume_confirmed"] = True
        return df

    df["vol_avg"]   = df["volume"].rolling(window=lookback, min_periods=5).mean()
    df["vol_ratio"] = df["volume"] / df["vol_avg"].replace(0, 1)

    # Spike: current bar volume must be ≥ 1.5× average
    df["vol_spike"] = df["vol_ratio"] >= 1.5

    # Consecutive participation: last 2 bars both above average
    vol_above_avg = df["volume"] >= df["vol_avg"]
    df["vol_consecutive"] = vol_above_avg & vol_above_avg.shift(1).fillna(False)

    # Final confirmation: spike OR consistent participation (not both required for index)
    df["volume_confirmed"] = df["vol_spike"] | df["vol_consecutive"]

    return df
