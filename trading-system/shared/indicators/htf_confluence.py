"""Multi-Timeframe (MTF) Trend Confluence Engine.

Analyzes Higher Timeframe (15-Minute & 1-Hour) trend alignment for 5-minute trades.
Directs trade management behavior:
  - 🚀 TREND RIDE MODE: When 5m trade aligns with 15m/1h Macro Trend -> gives trade room
    to ride multi-rung trend continuation (Standard ladder: 15%, 33%, 50%, 75%, 100%+).
  - ⚡ QUICK SCALP MODE: When 5m trade is counter to Macro Trend -> locks profits fast
    with a tighter ladder (10% Breakeven, 20%, 35%) and tighter stop loss to prevent
    drawdown when the macro trend reasserts itself.
"""

from __future__ import annotations

import datetime as _dt
from typing import Dict, Any, Optional, Tuple
import pandas as pd
import numpy as np

# Rungs for Trend Ride (Institutional Tailwind)
LADDER_TREND_RIDE: Tuple[float, ...] = (15.0, 33.0, 50.0, 75.0, 100.0, 150.0, 200.0)
INITIAL_SL_TREND_RIDE: float = 15.0

# Rungs for Quick Scalp (Counter-Trend Pullback)
LADDER_QUICK_SCALP: Tuple[float, ...] = (10.0, 20.0, 35.0, 50.0, 75.0)
INITIAL_SL_QUICK_SCALP: float = 12.0


def detect_htf_trend(df_5m: pd.DataFrame) -> Dict[str, Any]:
    """Calculate 15-Minute and 1-Hour trend direction from 5-minute candle history.

    Args:
        df_5m: DataFrame of 5-minute candles with open, high, low, close.

    Returns:
        Dict containing:
            trend_15m: "BULLISH" | "BEARISH" | "NEUTRAL"
            trend_1h: "BULLISH" | "BEARISH" | "NEUTRAL"
            macro_bias: "BULLISH" | "BEARISH" | "NEUTRAL"
            details: summary string for logging & alerts
    """
    if df_5m is None or len(df_5m) < 15:
        return {
            "trend_15m": "NEUTRAL",
            "trend_1h": "NEUTRAL",
            "macro_bias": "NEUTRAL",
            "details": "Insufficient history",
        }

    df = df_5m.copy()
    if not isinstance(df.index, pd.DatetimeIndex):
        if "datetime" in df.columns:
            df.index = pd.to_datetime(df["datetime"])
        elif "timestamp" in df.columns:
            df.index = pd.to_datetime(df["timestamp"])
        else:
            return {
                "trend_15m": "NEUTRAL",
                "trend_1h": "NEUTRAL",
                "macro_bias": "NEUTRAL",
                "details": "No datetime index",
            }

    df.columns = [c.lower() for c in df.columns]

    # 1. 15-Minute Resampled Trend
    trend_15m = "NEUTRAL"
    try:
        agg15 = df.resample("15min", label="right", closed="right").agg({
            "open": "first", "high": "max", "low": "min", "close": "last"
        }).dropna()

        # Drop currently forming incomplete bar if length allows
        if len(agg15) > 1:
            agg15 = agg15.iloc[:-1]

        if len(agg15) >= 21:
            ema9_15 = agg15["close"].ewm(span=9, adjust=False).mean().iloc[-1]
            ema21_15 = agg15["close"].ewm(span=21, adjust=False).mean().iloc[-1]
            last_close_15 = float(agg15["close"].iloc[-1])

            # RSI 14 on 15m
            delta = agg15["close"].diff()
            gain = delta.clip(lower=0)
            loss = -delta.clip(upper=0)
            avg_gain = gain.ewm(alpha=1/14, adjust=False).mean()
            avg_loss = loss.ewm(alpha=1/14, adjust=False).mean()
            rs = avg_gain / (avg_loss + 1e-9)
            rsi_15 = float(100 - (100 / (1 + rs)).iloc[-1])

            if last_close_15 > ema21_15 and (ema9_15 >= ema21_15 or rsi_15 >= 50.0):
                trend_15m = "BULLISH"
            elif last_close_15 < ema21_15 and (ema9_15 <= ema21_15 or rsi_15 <= 50.0):
                trend_15m = "BEARISH"
    except Exception:
        trend_15m = "NEUTRAL"

    # 2. 1-Hour Resampled Trend
    trend_1h = "NEUTRAL"
    try:
        agg1h = df.resample("1h", label="right", closed="right").agg({
            "open": "first", "high": "max", "low": "min", "close": "last"
        }).dropna()

        if len(agg1h) > 1:
            agg1h = agg1h.iloc[:-1]

        if len(agg1h) >= 5:
            period_1h = min(20, len(agg1h))
            ema20_1h = agg1h["close"].ewm(span=period_1h, adjust=False).mean().iloc[-1]
            last_close_1h = float(agg1h["close"].iloc[-1])
            if last_close_1h > ema20_1h:
                trend_1h = "BULLISH"
            elif last_close_1h < ema20_1h:
                trend_1h = "BEARISH"
    except Exception:
        trend_1h = "NEUTRAL"

    # 3. Overall Macro Bias
    if trend_15m == "BULLISH" and trend_1h in ("BULLISH", "NEUTRAL"):
        macro_bias = "BULLISH"
    elif trend_15m == "BEARISH" and trend_1h in ("BEARISH", "NEUTRAL"):
        macro_bias = "BEARISH"
    elif trend_1h == "BULLISH":
        macro_bias = "BULLISH"
    elif trend_1h == "BEARISH":
        macro_bias = "BEARISH"
    else:
        macro_bias = "NEUTRAL"

    return {
        "trend_15m": trend_15m,
        "trend_1h": trend_1h,
        "macro_bias": macro_bias,
        "details": f"15m: {trend_15m}, 1h: {trend_1h}",
    }


def get_trade_holding_mode(direction: str, htf_bias: Dict[str, Any]) -> Dict[str, Any]:
    """Determine whether to RIDE or SCALP based on Higher Timeframe alignment.

    Args:
        direction: "BUY" (CE) or "SELL" (PE)
        htf_bias: Output dict from detect_htf_trend()

    Returns:
        Dict with mode, label, profit ladder, initial stop loss, and rationale.
    """
    trend_15m = htf_bias.get("trend_15m", "NEUTRAL")
    macro_bias = htf_bias.get("macro_bias", "NEUTRAL")

    # Does trade align with the 15m / macro trend?
    is_aligned = False
    if direction in ("BUY", "LONG", 1):
        is_aligned = (trend_15m == "BULLISH") or (macro_bias == "BULLISH" and trend_15m != "BEARISH")
    elif direction in ("SELL", "SHORT", -1):
        is_aligned = (trend_15m == "BEARISH") or (macro_bias == "BEARISH" and trend_15m != "BULLISH")

    if is_aligned:
        return {
            "mode": "RIDE",
            "is_aligned": True,
            "label": f"🚀 TREND RIDE ({trend_15m.capitalize()} 15m Confluence)",
            "short_label": "TREND RIDE",
            "profit_ladder_pct": LADDER_TREND_RIDE,
            "initial_sl_pct": INITIAL_SL_TREND_RIDE,
            "trail_trigger_pct": 0.50,
            "trail_offset_pct": 0.35,
            "description": "With-trend trade: Holding for full multi-rung trend continuation.",
        }
    else:
        opp_trend = "Bearish" if direction in ("BUY", "LONG", 1) else "Bullish"
        return {
            "mode": "SCALP",
            "is_aligned": False,
            "label": f"⚡ QUICK SCALP (Counter-{opp_trend} 15m)",
            "short_label": "QUICK SCALP",
            "profit_ladder_pct": LADDER_QUICK_SCALP,
            "initial_sl_pct": INITIAL_SL_QUICK_SCALP,
            "trail_trigger_pct": 0.35,
            "trail_offset_pct": 0.25,
            "description": "Counter-trend trade: Locking profit fast at +10% BE and trailing tightly.",
        }
