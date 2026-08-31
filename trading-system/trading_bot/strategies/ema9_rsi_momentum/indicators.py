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

import numpy as np
import pandas as pd

from shared.indicators import ema, rsi


@dataclass(frozen=True)
class IndicatorSet:
    """The four series this strategy's rules are built from, aligned to the
    input ``DataFrame``'s index."""

    ema_fast: pd.Series
    ema_slow: pd.Series
    rsi: pd.Series
    rsi_ma: pd.Series


def compute_indicator_set(
    df: pd.DataFrame,
    ema_fast: int,
    ema_slow: int,
    rsi_length: int,
    rsi_ma_length: int = 20,
) -> IndicatorSet:
    """Compute EMA fast/slow (on close) and RSI + its EMA smoothing (TradingView RSI-EMA).

    ``rsi`` is the classic RSI of close: ``rsi(close, window=rsi_length)``.
    ``rsi_ma`` is the EMA 20 smoothing of the RSI line:
    ``ema(rsi(close, window=rsi_length), window=rsi_ma_length)``.
    """
    close = df["close"]
    rsi_series = rsi(close, window=rsi_length)
    return IndicatorSet(
        ema_fast=ema(close, window=ema_fast),
        ema_slow=ema(close, window=ema_slow),
        rsi=rsi_series,
        rsi_ma=ema(rsi_series, window=rsi_ma_length),
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
