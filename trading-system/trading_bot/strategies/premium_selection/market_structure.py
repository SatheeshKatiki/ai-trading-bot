"""Market Structure Filter — Higher Highs/Lows, Breakout-Retest, Pullback Entry.

Institutional rule: Entries must be structurally justified.
No mid-range entries. No late chasing. Prefer pullback-retest setups.
"""
from __future__ import annotations
import pandas as pd


def compute_market_structure(
    df: pd.DataFrame,
    swing_lookback: int = 10,
    pullback_bars: int = 3,
) -> pd.DataFrame:
    """
    Detects:
      - Higher Highs / Higher Lows (bullish structure)
      - Lower Highs / Lower Lows  (bearish structure)
      - Breakout above recent resistance
      - Pullback entry (price dipped after breakout, then resumed)
      - Mid-range rejection (avoid entries in middle of S/R range)

    Returns DataFrame with columns:
      - swing_high, swing_low  : rolling lookback high/low
      - higher_highs           : current high > previous swing high
      - lower_lows             : current low < previous swing low
      - breakout_bullish       : close breaks above swing_high
      - breakdown_bearish      : close breaks below swing_low
      - pullback_bullish       : price pulled back after bullish breakout
      - pullback_bearish       : price pulled back after bearish breakdown
      - structure_bullish      : valid bullish structure for entry
      - structure_bearish      : valid bearish structure for entry
    """
    df = df.copy()

    # Swing highs/lows using rolling lookback (exclude current bar)
    df["swing_high"] = df["high"].shift(1).rolling(swing_lookback).max()
    df["swing_low"]  = df["low"].shift(1).rolling(swing_lookback).min()

    # Higher Highs / Lower Lows
    df["higher_highs"] = df["high"] > df["swing_high"].shift(swing_lookback)
    df["lower_lows"]   = df["low"]  < df["swing_low"].shift(swing_lookback)

    # Breakout
    df["breakout_bullish"] = df["close"] > df["swing_high"]
    df["breakdown_bearish"]= df["close"] < df["swing_low"]

    # --- Pullback detection ---
    # Bullish pullback: there was a recent breakout, price dipped ≥ 1 bar, now recovering
    recent_breakout = df["breakout_bullish"].shift(1).rolling(pullback_bars).max().fillna(False).astype(bool)
    price_dipped    = df["low"] < df["close"].shift(1)      # price came down at least once
    recovering      = df["close"] > df["open"]              # current bar is bullish (recovery)
    df["pullback_bullish"] = recent_breakout & recovering

    # Bearish pullback: there was a recent breakdown, price bounced, now resuming down
    recent_breakdown = df["breakdown_bearish"].shift(1).rolling(pullback_bars).max().fillna(False).astype(bool)
    price_bounced    = df["high"] > df["close"].shift(1)
    resuming_down    = df["close"] < df["open"]
    df["pullback_bearish"] = recent_breakdown & resuming_down

    # --- Mid-range rejection ---
    # Avoid entries when price is between 40-60% of the S/R range
    sr_range = (df["swing_high"] - df["swing_low"]).replace(0, 1e-9)
    price_position = (df["close"] - df["swing_low"]) / sr_range
    in_middle_zone = (price_position >= 0.35) & (price_position <= 0.65)

    # Final structural validation
    # Prefer pullback entries; also accept fresh breakouts if not in middle zone
    df["structure_bullish"] = (
        (df["pullback_bullish"] | (df["breakout_bullish"] & ~in_middle_zone)) &
        df["higher_highs"]
    )

    df["structure_bearish"] = (
        (df["pullback_bearish"] | (df["breakdown_bearish"] & ~in_middle_zone)) &
        df["lower_lows"]
    )

    return df
