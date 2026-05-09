"""Trend Filter — EMA20 / EMA50 / EMA200 alignment with slope validation.

Institutional rule: Only trade WITH the trend. Reject tangled, flat, or choppy EMA structures.
"""
from __future__ import annotations
import pandas as pd
import numpy as np
from shared.indicators import ema


def compute_trend(df: pd.DataFrame) -> pd.DataFrame:
    """
    Computes EMA20, EMA50, EMA200 and derives trend signals.

    Returns a DataFrame with columns:
      - ema20, ema50, ema200
      - ema20_slope : rate of change of EMA20 over 3 bars (annualised %)
      - trend_bullish : True when all bullish conditions met
      - trend_bearish : True when all bearish conditions met
      - trend_valid   : True when trend is clear (not sideways / tangled)
    """
    df = df.copy()  # safe to mutate — engine provides a copy for the live path
    # Note: backtesting path (generate_signals rolling window) also copies
    df["ema20"]  = ema(df["close"], window=20)
    df["ema50"]  = ema(df["close"], window=50)
    df["ema200"] = ema(df["close"], window=200)

    # EMA slope: % change over 3 bars — must be meaningful
    df["ema20_slope"] = df["ema20"].pct_change(3) * 100
    df["ema50_slope"] = df["ema50"].pct_change(3) * 100

    # Bullish alignment: EMA20 > EMA50 > EMA200, price above EMA20
    df["trend_bullish"] = (
        (df["ema20"] > df["ema50"]) &
        (df["ema50"] > df["ema200"]) &
        (df["close"] > df["ema20"]) &
        (df["ema20_slope"] > 0.02)   # EMA20 must be sloping up (> 0.02% / 3 bars)
    )

    # Bearish alignment: EMA20 < EMA50 < EMA200, price below EMA20
    df["trend_bearish"] = (
        (df["ema20"] < df["ema50"]) &
        (df["ema50"] < df["ema200"]) &
        (df["close"] < df["ema20"]) &
        (df["ema20_slope"] < -0.02)
    )

    # Trend validity: reject tangled EMAs (EMA20 and EMA50 very close to each other)
    ema_gap_pct = ((df["ema20"] - df["ema50"]).abs() / df["ema50"]) * 100
    df["trend_valid"] = (
        (df["trend_bullish"] | df["trend_bearish"]) &
        (ema_gap_pct > 0.05)  # At least 0.05% gap between EMA20 and EMA50
    )

    return df
