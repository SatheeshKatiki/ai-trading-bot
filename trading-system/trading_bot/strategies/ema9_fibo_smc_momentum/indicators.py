"""Indicator & Price Action plumbing for EMA 9 / Fibo OTE Momentum Pro.

Reuses core shared indicators (ema, rsi, atr, cm_ultimate_moving_average)
and introduces Pure Price Action market structure detection:
- Fractal Swing Points & Break of Structure (BOS / MSS).
- Candlestick Rejection Wick / Order Flow Absorption.
- Candlestick Exhaustion Wick at Resistance / Extension targets.
- Structural Swing Trailing levels (Higher Lows for CE, Lower Highs for PE).
- Supportive RSI Divergence detection.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional, Tuple

import numpy as np
import pandas as pd

from shared.indicators import atr, cm_ultimate_moving_average, ema, rsi


@dataclass(frozen=True)
class IndicatorSet:
    """The series this strategy's rules are built from, aligned to df index."""
    ema_fast: pd.Series
    ema_slow: pd.Series
    rsi: pd.Series
    rsi_ma: pd.Series
    cm_ma: Optional[pd.DataFrame] = None
    atr: Optional[pd.Series] = None


def compute_indicator_set(
    df: pd.DataFrame,
    ema_fast: int = 9,
    ema_slow: int = 20,
    rsi_length: int = 14,
    rsi_ma_length: int = 20,
) -> IndicatorSet:
    """Compute moving averages using CM_Ultimate_MA_MTF_V2, ATR, and RSI + its EMA smoothing."""
    close = df["close"]
    rsi_series = rsi(close, window=rsi_length)

    cm_df = cm_ultimate_moving_average(
        df,
        ma1_len=ema_slow,
        ma1_type=2,  # EMA
        optional_2nd_ma=True,
        ma2_len=ema_fast,
        ma2_type=2,  # EMA
    )

    if "high" in df.columns and "low" in df.columns and len(df) >= 1:
        atr_series = atr(df, window=14)
    else:
        atr_series = pd.Series(0.005 * close, index=df.index)

    return IndicatorSet(
        ema_fast=cm_df["ma2"],
        ema_slow=cm_df["ma1"],
        rsi=rsi_series,
        rsi_ma=ema(rsi_series, window=rsi_ma_length),
        cm_ma=cm_df,
        atr=atr_series,
    )


def crossed_above(a: pd.Series, b: pd.Series) -> np.ndarray:
    """Boolean numpy array: True on the bar where a transitions from <= b to > b."""
    a_arr = np.asarray(a, dtype=float)
    b_arr = np.asarray(b, dtype=float)
    now_above = a_arr > b_arr
    was_le = np.empty_like(now_above)
    was_le[0] = False
    was_le[1:] = a_arr[:-1] <= b_arr[:-1]
    return now_above & was_le


def crossed_below(a: pd.Series, b: pd.Series) -> np.ndarray:
    """Mirror of crossed_above — True where a transitions from >= b to < b."""
    a_arr = np.asarray(a, dtype=float)
    b_arr = np.asarray(b, dtype=float)
    now_below = a_arr < b_arr
    was_ge = np.empty_like(now_below)
    was_ge[0] = False
    was_ge[1:] = a_arr[:-1] >= b_arr[:-1]
    return now_below & was_ge


# ─────────────────────────────────────────────────────────────────────
# Pure Price Action: Market Structure, Rejections & Trailing
# ─────────────────────────────────────────────────────────────────────

def detect_swing_points(
    high: np.ndarray,
    low: np.ndarray,
    lookback: int = 15,
) -> Tuple[np.ndarray, np.ndarray]:
    """Computes dynamic rolling swing highs and swing lows across lookback bars."""
    high_s = pd.Series(high)
    low_s = pd.Series(low)
    r_high = high_s.rolling(window=lookback, min_periods=1).max().to_numpy()
    r_low = low_s.rolling(window=lookback, min_periods=1).min().to_numpy()
    return r_high, r_low


def detect_rejection_wick(
    high: np.ndarray,
    low: np.ndarray,
    open_: np.ndarray,
    close: np.ndarray,
    direction: int,
    min_wick_ratio: float = 0.30,
) -> np.ndarray:
    """Detects candlestick rejection wicks indicating institutional absorption.

    For Bullish (direction=1, CE):
        Lower wick >= min_wick_ratio of total candle range and close is in upper 60%.
    For Bearish (direction=-1, PE):
        Upper wick >= min_wick_ratio of total candle range and close is in lower 60%.
    """
    span = np.nan_to_num(np.maximum(high - low, 1e-9), nan=1e-9)
    span = np.where(span <= 0, 1e-9, span)
    if direction == 1:
        lower_wick = np.nan_to_num(np.minimum(open_, close) - low, nan=0.0)
        wick_ratio = lower_wick / span
        held_upper = close >= (low + 0.35 * span)
        return (wick_ratio >= min_wick_ratio) & held_upper
    else:
        upper_wick = np.nan_to_num(high - np.maximum(open_, close), nan=0.0)
        wick_ratio = upper_wick / span
        held_lower = close <= (high - 0.35 * span)
        return (wick_ratio >= min_wick_ratio) & held_lower


def detect_exhaustion_wick(
    high: np.ndarray,
    low: np.ndarray,
    open_: np.ndarray,
    close: np.ndarray,
    direction: int,
    min_ratio: float = 0.40,
) -> np.ndarray:
    """Detects opposite exhaustion wick signaling peak distribution at key levels.

    For CE position (direction=1):
        Exhaustion is an upper rejection wick (Shooting Star / Bearish Pinbar) >= 40% range.
    For PE position (direction=-1):
        Exhaustion is a lower rejection wick (Hammer / Bullish Pinbar) >= 40% range.
    """
    span = np.nan_to_num(np.maximum(high - low, 1e-9), nan=1e-9)
    span = np.where(span <= 0, 1e-9, span)
    if direction == 1:
        upper_wick = np.nan_to_num(high - np.maximum(open_, close), nan=0.0)
        wick_ratio = upper_wick / span
        held_lower = close <= (low + 0.45 * span)
        return (wick_ratio >= min_ratio) & held_lower
    else:
        lower_wick = np.nan_to_num(np.minimum(open_, close) - low, nan=0.0)
        wick_ratio = lower_wick / span
        held_upper = close >= (low + 0.55 * span)
        return (wick_ratio >= min_ratio) & held_upper


def detect_structure_swings(
    high: np.ndarray,
    low: np.ndarray,
    close: np.ndarray,
    lookback: int = 5,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Identifies structural Higher Lows (HL) and Lower Highs (LH) for trailing exits.
    Strictly causal (no lookahead bias): a pivot at bar p is confirmed at bar p + lookback.

    Returns:
        (higher_lows, lower_highs, bos_bullish, bos_bearish) arrays.
    """
    n = len(close)
    if n == 0:
        return np.zeros(0), np.zeros(0), np.zeros(0, dtype=bool), np.zeros(0, dtype=bool)

    hl_arr = np.zeros(n, dtype=float)
    lh_arr = np.zeros(n, dtype=float)
    bos_bull = np.zeros(n, dtype=bool)
    bos_bear = np.zeros(n, dtype=bool)

    last_sh = float(high[0]) if (len(high) > 0 and np.isfinite(high[0])) else 0.0
    last_sl = float(low[0]) if (len(low) > 0 and np.isfinite(low[0])) else 0.0

    for i in range(n):
        # A fractal pivot at candidate p is confirmed at bar i = p + lookback
        p = i - lookback
        if p >= lookback:
            win_high = high[p - lookback : i + 1]
            if len(win_high) > 0 and np.any(np.isfinite(win_high)):
                m_high = np.nanmax(win_high)
                if np.isfinite(high[p]) and high[p] == m_high:
                    last_sh = float(high[p])

            win_low = low[p - lookback : i + 1]
            if len(win_low) > 0 and np.any(np.isfinite(win_low)):
                m_low = np.nanmin(win_low)
                if np.isfinite(low[p]) and low[p] == m_low:
                    last_sl = float(low[p])

        hl_arr[i] = last_sl
        lh_arr[i] = last_sh

        # Break of Structure (BOS)
        if i > 0 and last_sh > 0 and close[i] > last_sh and close[i - 1] <= last_sh:
            bos_bull[i] = True
        if i > 0 and last_sl > 0 and close[i] < last_sl and close[i - 1] >= last_sl:
            bos_bear[i] = True

    return hl_arr, lh_arr, bos_bull, bos_bear


def detect_rsi_divergence(
    close: np.ndarray,
    rsi_vals: np.ndarray,
    direction: int,
    lookback: int = 14,
) -> np.ndarray:
    """Detects momentum exhaustion divergence against current trade direction.
    Robust to NaNs and boundary values.
    """
    n = len(close)
    div_arr = np.zeros(n, dtype=bool)
    if n <= lookback * 2:
        return div_arr

    for i in range(lookback * 2, n):
        c_sub = close[i - lookback : i + 1]
        r_sub = rsi_vals[i - lookback : i + 1]

        if not np.all(np.isfinite(c_sub)) or not np.all(np.isfinite(r_sub)):
            continue

        c_past = c_sub[:-1]
        r_past = r_sub[:-1]
        if len(c_past) == 0 or len(r_past) == 0:
            continue

        if direction == 1:
            # Higher High in price with Lower High in RSI
            if close[i] >= np.nanmax(c_past) and rsi_vals[i] < (np.nanmax(r_past) - 2.5):
                div_arr[i] = True
        elif direction == -1:
            # Lower Low in price with Higher Low in RSI
            if close[i] <= np.nanmin(c_past) and rsi_vals[i] > (np.nanmin(r_past) + 2.5):
                div_arr[i] = True

    return div_arr


def calculate_fibonacci_levels(
    swing_high: float,
    swing_low: float,
    direction: int,
    tp1_ext: float = 1.0,
    tp2_ext: float = 1.272,
    tp3_ext: float = 1.618,
) -> Optional[Dict[str, float]]:
    """Calculates Institutional Fibonacci Retracement & Extension levels."""
    if not (np.isfinite(swing_high) and np.isfinite(swing_low)):
        return None
    span = float(swing_high) - float(swing_low)
    if span <= 0 or not np.isfinite(span):
        return None

    if direction == 1:
        return {
            "equilibrium": round(swing_high - 0.500 * span, 2),
            "ote_low": round(swing_high - 0.620 * span, 2),
            "sweet_spot": round(swing_high - 0.705 * span, 2),
            "ote_high": round(swing_high - 0.790 * span, 2),
            "invalidation": round(swing_low, 2),
            "tp1": round(swing_high + (tp1_ext - 1.0) * span, 2),
            "tp2": round(swing_high + (tp2_ext - 1.0) * span, 2),
            "tp3": round(swing_high + (tp3_ext - 1.0) * span, 2),
        }
    else:
        return {
            "equilibrium": round(swing_low + 0.500 * span, 2),
            "ote_low": round(swing_low + 0.620 * span, 2),
            "sweet_spot": round(swing_low + 0.705 * span, 2),
            "ote_high": round(swing_low + 0.790 * span, 2),
            "invalidation": round(swing_high, 2),
            "tp1": round(swing_low - (tp1_ext - 1.0) * span, 2),
            "tp2": round(swing_low - (tp2_ext - 1.0) * span, 2),
            "tp3": round(swing_low - (tp3_ext - 1.0) * span, 2),
        }


def is_in_fibo_ote_zone(
    bar_high: float,
    bar_low: float,
    bar_close: float,
    swing_high: float,
    swing_low: float,
    direction: int,
    ote_low: float = 0.62,
    ote_high: float = 0.79,
) -> bool:
    """Evaluates whether candle retested the Optimal Trade Entry (OTE) zone."""
    if not (np.isfinite(bar_high) and np.isfinite(bar_low) and np.isfinite(bar_close) and np.isfinite(swing_high) and np.isfinite(swing_low)):
        return False
    span = float(swing_high) - float(swing_low)
    if span <= 0 or not np.isfinite(span):
        return False

    if direction == 1:
        shallow_ote = swing_high - ote_low * span   # 0.62
        deep_ote = swing_high - ote_high * span     # 0.79
        tested_pocket = (bar_low <= shallow_ote) and (bar_low >= (swing_low - 0.05 * span))
        held_invalidation = bar_close >= deep_ote
        return bool(tested_pocket and held_invalidation)
    else:
        shallow_ote = swing_low + ote_low * span    # 0.62
        deep_ote = swing_low + ote_high * span      # 0.79
        tested_pocket = (bar_high >= shallow_ote) and (bar_high <= (swing_high + 0.05 * span))
        held_invalidation = bar_close <= deep_ote
        return bool(tested_pocket and held_invalidation)
