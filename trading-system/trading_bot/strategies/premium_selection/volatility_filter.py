"""Volatility Filter — ATR-based controlled momentum validation.

Avoid: extremely low volatility (no opportunity) and extreme spikes (news/irrational moves).
Trade only controlled momentum expansion.
"""
from __future__ import annotations
import pandas as pd
from shared.indicators import atr


def compute_volatility(
    df: pd.DataFrame,
    atr_window: int = 14,
    low_vol_pct: float = 0.0001,   # ATR < 0.01% of price = too quiet
    high_vol_pct: float = 0.025,  # ATR > 2.5% of price = too wild (news spike)
) -> pd.DataFrame:
    """
    Computes ATR and classifies volatility regime.

    Returns DataFrame with columns:
      - atr_val        : raw ATR value
      - atr_pct        : ATR as percentage of close price
      - atr_avg        : 20-period rolling average of ATR (baseline)
      - vol_expanding  : ATR > ATR average (momentum expanding)
      - volatility_ok  : True when volatility is in the tradeable zone
    """
    df = df.copy()

    df["atr_val"] = atr(df, window=atr_window)
    df["atr_pct"] = df["atr_val"] / df["close"].replace(0, 1e-9)
    df["atr_avg"] = df["atr_val"].rolling(20, min_periods=5).mean()

    # Expanding ATR = momentum building (prefer this)
    df["vol_expanding"] = df["atr_val"] > df["atr_avg"]

    # Reject: too quiet OR news-driven spike
    too_quiet = df["atr_pct"] < low_vol_pct
    too_wild  = df["atr_pct"] > high_vol_pct

    # Candle range vs ATR: reject if single candle is > 4× ATR (news spike)
    candle_range = df["high"] - df["low"]
    news_spike   = candle_range > (df["atr_val"] * 4.0)

    df["volatility_ok"] = ~too_quiet & ~too_wild & ~news_spike

    return df
