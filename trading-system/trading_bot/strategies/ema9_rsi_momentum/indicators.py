"""Indicator plumbing for the EMA9/RSI Momentum strategy.

Reuses ``shared.indicators`` (``ema``, ``rsi``) for every calculation —
this module adds no new indicator math, only the crossover-detection
helpers those two series need for this strategy's entry/exit rules.

Crossover detection is built purely from vectorized comparisons
(``>``, ``<``, ``.shift``) — never a boolean-mask ``Series.__setitem__`` —
matching the fix pattern documented in
``trading_bot/strategies/ema_rsi_strategy.py`` and
``trading_bot/strategies/_signal_utils.py`` after the 2026-08-06/07/08/28
CPU-livelock incidents (see ``docs/paper_trading_validation/anomaly_log.md``).
Plain comparison operators build a boolean array via a ufunc, not a
``__setitem__`` call, so they were never implicated in that class of bug.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np
import pandas as pd

from shared.indicators import atr, cm_ultimate_moving_average, ema, rsi


@dataclass(frozen=True)
class IndicatorSet:
    """The series this strategy's rules are built from, aligned to the
    input ``DataFrame``'s index."""

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
    """Compute moving averages using CM_Ultimate_MA_MTF_V2, ATR, and RSI + its EMA smoothing.

    Uses CM_Ultimate_MA_MTF_V2 indicator for 9 EMA (fast) and 20 EMA (slow).
    ``rsi`` is the classic RSI of close: ``rsi(close, window=rsi_length)``.
    ``rsi_ma`` is the EMA 20 smoothing of the RSI line:
    ``ema(rsi(close, window=rsi_length), window=rsi_ma_length)``.
    ``atr`` is the 14-period ATR for dynamic volatility scaling.
    """
    close = df["close"]
    rsi_series = rsi(close, window=rsi_length)

    # CM_Ultimate_MA_MTF_V2: MA1 = slow (20 EMA), MA2 = fast (9 EMA)
    cm_df = cm_ultimate_moving_average(
        df,
        ma1_len=ema_slow,
        ma1_type=2,  # 2 = EMA
        optional_2nd_ma=True,
        ma2_len=ema_fast,
        ma2_type=2,  # 2 = EMA
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
    """Boolean numpy array: True on the bar where ``a`` transitions from
    <= ``b`` to > ``b``. NaN comparisons evaluate False, so warm-up bars
    (before either series has enough history) never register a crossover.
    """
    a_arr = np.asarray(a, dtype=float)
    b_arr = np.asarray(b, dtype=float)
    now_above = a_arr > b_arr
    was_le = np.empty_like(now_above)
    was_le[0] = False
    was_le[1:] = a_arr[:-1] <= b_arr[:-1]
    return now_above & was_le


def crossed_below(a: pd.Series, b: pd.Series) -> np.ndarray:
    """Mirror of :func:`crossed_above` — True where ``a`` transitions from
    >= ``b`` to < ``b``."""
    a_arr = np.asarray(a, dtype=float)
    b_arr = np.asarray(b, dtype=float)
    now_below = a_arr < b_arr
    was_ge = np.empty_like(now_below)
    was_ge[0] = False
    was_ge[1:] = a_arr[:-1] >= b_arr[:-1]
    return now_below & was_ge


def crossed_above_level(a: pd.Series, level: float) -> np.ndarray:
    """Scalar-level variant of :func:`crossed_above` — used for the RSI
    momentum-strength bands (40/50/60), which are constants rather than a
    second series."""
    a_arr = np.asarray(a, dtype=float)
    now_above = a_arr > level
    was_le = np.empty_like(now_above)
    was_le[0] = False
    was_le[1:] = a_arr[:-1] <= level
    return now_above & was_le


def crossed_below_level(a: pd.Series, level: float) -> np.ndarray:
    """Scalar-level variant of :func:`crossed_below`."""
    a_arr = np.asarray(a, dtype=float)
    now_below = a_arr < level
    was_ge = np.empty_like(now_below)
    was_ge[0] = False
    was_ge[1:] = a_arr[:-1] >= level
    return now_below & was_ge
