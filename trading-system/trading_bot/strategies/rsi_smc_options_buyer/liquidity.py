"""Liquidity-sweep detection, vectorised.

A sweep is the event this strategy is built on: price pushes through a level
where stops rest, takes them, and closes back on the original side. A push
that CLOSES beyond the level is not a sweep -- it is a break, and it is
refused here rather than filtered out later.

Why this module exists at all
-----------------------------
``LiquidityPool`` in ``shared/indicators/smart_money_concepts.py`` declares
``swept`` and ``sweep_index`` and never assigns either -- nothing in the
engine detects a sweep. ``LiquiditySweepDetector`` in
``trading_bot/strategies/momentum_strategy/price_action.py`` does implement
the definition, but it is dead code: ``TradeQualityScorer`` constructs it at
``trade_scorer.py:25`` and never calls it, and a repository-wide search finds
no other caller. It is also scalar and ``iterrows``-based, so running it over
every bar of an 18,000-bar frame is not viable.

So the DEFINITION is reused and the IMPLEMENTATION is vectorised.
:func:`reference_sweeps` reproduces ``LiquiditySweepDetector.detect()``
bar-for-bar, and a test pins that equivalence on real NIFTY 5-minute data. It
is the same core routine (:func:`_sweep_against`) that the strategy uses
against SMC pools and daily levels, so the two cannot drift apart.

The intentional difference from the reference
---------------------------------------------
The reference defines its level as *the lowest low of the earlier part of a
rolling 20-bar window*. This strategy also sweeps **named** levels -- EQH/EQL
pools, previous-day high/low, session high/low -- because a rolling extreme
is wherever price happens to have been, while a named level is where stops
are actually resting. Both are detected by the same core routine with the
same wick-through-and-close-back rule, the same current-bar exclusion and the
same ``idx < 2 * lookback`` warm-up guard; only the level being tested
differs. Named levels additionally carry the availability delay applied in
:mod:`structure`, which the rolling extreme does not need because it is
computed from closed bars directly.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

#: The reference detector hard-codes 5 as the number of most-recent bars
#: inside its window that may carry the sweep. Kept as a named constant so
#: the equivalence test and the strategy read the same number.
REFERENCE_RECENT_BARS = 5
#: ``LiquiditySweepDetector.__init__``'s default.
REFERENCE_SWING_LOOKBACK = 20


@dataclass(frozen=True)
class SweepResult:
    """Per-bar sweep flags and the level each sweep ran through."""

    #: A sell-side sweep (wick BELOW a low level, close back above) happened
    #: within the recent window -- the setup for a LONG / CE.
    bullish: np.ndarray
    #: A buy-side sweep (wick ABOVE a high level, close back below) -- SHORT / PE.
    bearish: np.ndarray
    #: The level swept, and the extreme the wick reached. NaN where no sweep.
    bullish_level: np.ndarray
    bearish_level: np.ndarray
    bullish_extreme: np.ndarray
    bearish_extreme: np.ndarray


def _shift(values: np.ndarray, k: int) -> np.ndarray:
    """``values[i - k]`` aligned to position ``i``, NaN-padded at the front.

    Positional only -- never a label-based ``Series.shift`` lookup, because
    the live candle cache can carry duplicate and non-monotonic timestamps.
    """
    out = np.full(values.shape[0], np.nan, dtype=float)
    if k <= 0:
        return values.astype(float, copy=True)
    if k < values.shape[0]:
        out[k:] = values[:-k]
    return out


def _sweep_against(level: np.ndarray, high: np.ndarray, low: np.ndarray,
                   close: np.ndarray, recent_bars: int, warmup: int,
                   is_high_level: bool):
    """Core rule, shared by every caller so the semantics cannot diverge.

    At bar ``i``, look back over the ``recent_bars`` bars STRICTLY BEFORE
    ``i`` -- the current bar is excluded, exactly as the reference detector
    excludes it with ``df.iloc[idx - lookback : idx]``. A sweep occurred if
    any of those bars wicked past ``level[i]`` and closed back on the
    original side.

    Returns ``(hit, swept_level, extreme)``.
    """
    n = level.shape[0]
    hit = np.zeros(n, dtype=bool)
    extreme = np.full(n, np.nan, dtype=float)

    for k in range(1, int(recent_bars) + 1):
        prior_high = _shift(high, k)
        prior_low = _shift(low, k)
        prior_close = _shift(close, k)
        if is_high_level:
            # Buy-side: wick ABOVE the level, close back BELOW it.
            pierced = (prior_high > level) & (prior_close < level)
            candidate = prior_high
            better = pierced & (~hit | (candidate > np.nan_to_num(extreme, nan=-np.inf)))
        else:
            # Sell-side: wick BELOW the level, close back ABOVE it.
            pierced = (prior_low < level) & (prior_close > level)
            candidate = prior_low
            better = pierced & (~hit | (candidate < np.nan_to_num(extreme, nan=np.inf)))
        extreme = np.where(better, candidate, extreme)
        hit = hit | np.nan_to_num(pierced, nan=0.0).astype(bool)

    # Warm-up guard, mirroring the reference's `idx < swing_lookback * 2`.
    if warmup > 0:
        positions = np.arange(n)
        too_early = positions < warmup
        hit = hit & ~too_early
        extreme = np.where(too_early, np.nan, extreme)

    swept_level = np.where(hit, level, np.nan)
    extreme = np.where(hit, extreme, np.nan)
    return hit, swept_level, extreme


def rolling_extreme_levels(df: pd.DataFrame, lookback: int = REFERENCE_SWING_LOOKBACK,
                           recent_bars: int = REFERENCE_RECENT_BARS):
    """The reference detector's own level definition, vectorised.

    ``LiquiditySweepDetector`` takes ``window = df.iloc[idx - lookback : idx]``
    and uses ``window.iloc[:-recent_bars]`` -- positions ``idx - lookback``
    through ``idx - recent_bars - 1`` -- to define the swing extreme. That is
    a rolling window of ``lookback - recent_bars`` bars ending at position
    ``idx - recent_bars - 1``, i.e. a ``rolling(lookback - recent_bars)``
    aggregate shifted by ``recent_bars + 1``.
    """
    width = int(lookback) - int(recent_bars)
    shift = int(recent_bars) + 1
    if width <= 0:
        nan = np.full(len(df), np.nan, dtype=float)
        return nan, nan.copy()
    low = pd.Series(df["low"].to_numpy(dtype=float))
    high = pd.Series(df["high"].to_numpy(dtype=float))
    swing_low = low.rolling(width).min().shift(shift).to_numpy(dtype=float)
    swing_high = high.rolling(width).max().shift(shift).to_numpy(dtype=float)
    return swing_low, swing_high


def reference_sweeps(df: pd.DataFrame, lookback: int = REFERENCE_SWING_LOOKBACK,
                     recent_bars: int = REFERENCE_RECENT_BARS) -> SweepResult:
    """Bar-for-bar equivalent of ``LiquiditySweepDetector.detect()``.

    ``detect(df, idx, signal_dir=1)`` maps to ``bullish[idx]`` and
    ``signal_dir=-1`` to ``bearish[idx]``. Pinned by
    ``test_rsi_smc_liquidity.py`` against the real implementation on real
    NIFTY data; this function exists to make that comparison possible, and
    the strategy uses the same core rule against named levels.
    """
    n = len(df)
    if n == 0:
        empty_b = np.zeros(0, dtype=bool)
        empty_f = np.zeros(0, dtype=float)
        return SweepResult(empty_b, empty_b.copy(), empty_f, empty_f.copy(),
                           empty_f.copy(), empty_f.copy())

    high = df["high"].to_numpy(dtype=float)
    low = df["low"].to_numpy(dtype=float)
    close = df["close"].to_numpy(dtype=float)
    swing_low, swing_high = rolling_extreme_levels(df, lookback, recent_bars)
    warmup = int(lookback) * 2

    bull, bull_level, bull_extreme = _sweep_against(
        swing_low, high, low, close, recent_bars, warmup, is_high_level=False)
    bear, bear_level, bear_extreme = _sweep_against(
        swing_high, high, low, close, recent_bars, warmup, is_high_level=True)

    return SweepResult(bull, bear, bull_level, bear_level, bull_extreme, bear_extreme)


def key_level_sweeps(df: pd.DataFrame, level_low: np.ndarray, level_high: np.ndarray,
                     recent_bars: int = REFERENCE_RECENT_BARS,
                     warmup: int = 0) -> SweepResult:
    """Sweeps of NAMED levels (EQL/EQH pools, PDL/PDH, session extremes).

    Identical rule to :func:`reference_sweeps`; only the level differs. The
    caller is responsible for supplying levels that were already available at
    each bar -- :mod:`structure` applies the measured pool availability delay
    and :mod:`levels` derives the daily levels from shifted aggregates.
    """
    n = len(df)
    if n == 0:
        empty_b = np.zeros(0, dtype=bool)
        empty_f = np.zeros(0, dtype=float)
        return SweepResult(empty_b, empty_b.copy(), empty_f, empty_f.copy(),
                           empty_f.copy(), empty_f.copy())

    high = df["high"].to_numpy(dtype=float)
    low = df["low"].to_numpy(dtype=float)
    close = df["close"].to_numpy(dtype=float)

    bull, bull_level, bull_extreme = _sweep_against(
        np.asarray(level_low, dtype=float), high, low, close,
        recent_bars, warmup, is_high_level=False)
    bear, bear_level, bear_extreme = _sweep_against(
        np.asarray(level_high, dtype=float), high, low, close,
        recent_bars, warmup, is_high_level=True)

    return SweepResult(bull, bear, bull_level, bear_level, bull_extreme, bear_extreme)


def combine(*results: SweepResult) -> SweepResult:
    """Union of several sweep results, keeping the most extreme wick.

    Used to let a single setup qualify off a pool sweep OR a previous-day
    level sweep without giving either a second vote -- the output is still a
    plain boolean per bar.
    """
    usable = [r for r in results if r is not None and r.bullish.shape[0]]
    if not usable:
        empty_b = np.zeros(0, dtype=bool)
        empty_f = np.zeros(0, dtype=float)
        return SweepResult(empty_b, empty_b.copy(), empty_f, empty_f.copy(),
                           empty_f.copy(), empty_f.copy())

    n = usable[0].bullish.shape[0]
    bull = np.zeros(n, dtype=bool)
    bear = np.zeros(n, dtype=bool)
    bull_level = np.full(n, np.nan, dtype=float)
    bear_level = np.full(n, np.nan, dtype=float)
    bull_extreme = np.full(n, np.nan, dtype=float)
    bear_extreme = np.full(n, np.nan, dtype=float)

    for result in usable:
        # Prefer the deeper wick: it is the more meaningful stop run, and it
        # gives the structural stop the wider, safer invalidation level.
        take_bull = result.bullish & (
            ~bull | (np.nan_to_num(result.bullish_extreme, nan=np.inf)
                     < np.nan_to_num(bull_extreme, nan=np.inf)))
        bull_level = np.where(take_bull, result.bullish_level, bull_level)
        bull_extreme = np.where(take_bull, result.bullish_extreme, bull_extreme)
        bull = bull | result.bullish

        take_bear = result.bearish & (
            ~bear | (np.nan_to_num(result.bearish_extreme, nan=-np.inf)
                     > np.nan_to_num(bear_extreme, nan=-np.inf)))
        bear_level = np.where(take_bear, result.bearish_level, bear_level)
        bear_extreme = np.where(take_bear, result.bearish_extreme, bear_extreme)
        bear = bear | result.bearish

    return SweepResult(bull, bear, bull_level, bear_level, bull_extreme, bear_extreme)


__all__ = [
    "SweepResult",
    "REFERENCE_RECENT_BARS",
    "REFERENCE_SWING_LOOKBACK",
    "rolling_extreme_levels",
    "reference_sweeps",
    "key_level_sweeps",
    "combine",
]
