"""Key liquidity levels, computed causally from the frame itself.

Three level families, each chosen because it is where resting stops
genuinely accumulate rather than because it is fashionable:

* **Previous day high / low** -- the most reliably stocked pools on an index.
* **Session high / low so far** -- intraday liquidity built during the day.
* **EQH / EQL pools** -- supplied by :mod:`structure`, already gated behind
  their measured availability delay.

Everything here is derived with shifted/expanding aggregates, so the value at
bar *i* uses only bars strictly before *i*. There are no end-of-frame scalars
in this module, which is exactly why the premium/discount and swing-extreme
levels that ``calculate_smc`` reports are NOT taken from it: those describe
the last bar of the frame. See :mod:`structure`.

Timestamps are used only to group bars into calendar days. Rows are addressed
positionally throughout, so duplicate or non-monotonic labels cannot select
the wrong bar.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class DailyLevels:
    """Per-bar level arrays, aligned positionally to the source frame."""

    prev_day_high: np.ndarray
    prev_day_low: np.ndarray
    session_high: np.ndarray
    session_low: np.ndarray


def _day_codes(index: pd.Index, n: int) -> np.ndarray:
    """Integer day id per bar, or all-zeros when the index carries no dates.

    A frame without a DatetimeIndex is treated as one continuous session
    rather than raising: the strategy still has to return a well-formed
    series, and the no-trade layer is what refuses the trade.
    """
    if not isinstance(index, pd.DatetimeIndex) or n == 0:
        return np.zeros(n, dtype=np.int64)
    dates = index.normalize().to_numpy()
    # Positional run-length coding: a new day starts wherever the normalised
    # date changes. Equivalent to factorize() for a sorted index, and it does
    # not care whether the labels are unique.
    changes = np.r_[True, dates[1:] != dates[:-1]]
    return np.cumsum(changes) - 1


def compute_daily_levels(df: pd.DataFrame) -> DailyLevels:
    """Previous-day and running-session extremes for every bar.

    ``prev_day_*`` is the completed previous day's extreme, constant across
    the day and available from its first bar. ``session_*`` is the extreme of
    the CURRENT day up to and including the PREVIOUS bar -- the current bar is
    excluded so a level can never be defined by the same candle that is about
    to be tested against it.
    """
    n = len(df)
    if n == 0:
        empty = np.zeros(0, dtype=float)
        return DailyLevels(empty, empty.copy(), empty.copy(), empty.copy())

    high = df["high"].to_numpy(dtype=float)
    low = df["low"].to_numpy(dtype=float)
    day = _day_codes(df.index, n)

    prev_day_high = np.full(n, np.nan, dtype=float)
    prev_day_low = np.full(n, np.nan, dtype=float)
    session_high = np.full(n, np.nan, dtype=float)
    session_low = np.full(n, np.nan, dtype=float)

    # Day boundaries, built once from the code array.
    starts = np.flatnonzero(np.r_[True, day[1:] != day[:-1]])
    ends = np.r_[starts[1:], n]  # exclusive

    last_high: Optional[float] = None
    last_low: Optional[float] = None
    for start, end in zip(starts, ends):
        if last_high is not None:
            prev_day_high[start:end] = last_high
            prev_day_low[start:end] = last_low

        day_high = high[start:end]
        day_low = low[start:end]
        # Running extreme EXCLUDING the current bar: accumulate, then shift
        # one position forward inside the day. The day's first bar has no
        # prior bar, so it stays NaN.
        running_high = np.maximum.accumulate(day_high)
        running_low = np.minimum.accumulate(day_low)
        if end - start > 1:
            session_high[start + 1:end] = running_high[:-1]
            session_low[start + 1:end] = running_low[:-1]

        last_high = float(running_high[-1])
        last_low = float(running_low[-1])

    return DailyLevels(prev_day_high, prev_day_low, session_high, session_low)


def nearest_level(*candidates: np.ndarray, reference: np.ndarray,
                  above: bool) -> np.ndarray:
    """Per-bar nearest candidate level on one side of ``reference``.

    ``above=True`` returns the closest level at or above the reference (the
    buy-side pool a rally would run into), ``above=False`` the closest at or
    below. NaN where no candidate qualifies. Candidates that are NaN at a bar
    are simply not considered there, which is how an unavailable level
    absents itself.
    """
    n = reference.shape[0]
    best = np.full(n, np.nan, dtype=float)
    best_dist = np.full(n, np.inf, dtype=float)

    for candidate in candidates:
        if candidate is None:
            continue
        values = np.asarray(candidate, dtype=float)
        if values.shape[0] != n:
            continue
        side = values >= reference if above else values <= reference
        usable = np.isfinite(values) & side
        distance = np.where(usable, np.abs(values - reference), np.inf)
        better = usable & (distance < best_dist)
        best_dist = np.where(better, distance, best_dist)
        best = np.where(better, values, best)

    return best


__all__ = ["DailyLevels", "compute_daily_levels", "nearest_level"]
