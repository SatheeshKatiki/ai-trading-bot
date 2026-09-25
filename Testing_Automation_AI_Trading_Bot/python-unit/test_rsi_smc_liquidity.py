"""Liquidity-sweep equivalence with the existing reference implementation.

`LiquiditySweepDetector` (momentum_strategy/price_action.py) owns the
DEFINITION of a sweep in this repository. It is dead code -- `TradeQualityScorer`
constructs it and never calls it -- but it is still the reference, and
rsi_smc_options_buyer's vectorised detector must agree with it exactly rather
than inventing a second definition.

If this test fails, the two have diverged and the strategy's liquidity logic
no longer means what the repository says a sweep means.
"""
from __future__ import annotations

import pathlib

import numpy as np
import pandas as pd
import pytest

import _bootstrap  # noqa: F401

from trading_bot.strategies.momentum_strategy.price_action import LiquiditySweepDetector
from trading_bot.strategies.rsi_smc_options_buyer import liquidity

FIXTURE = (pathlib.Path(__file__).resolve().parent / "fixtures" / "data"
           / "rsi_smc_NIFTY_5Min.csv")


@pytest.fixture(scope="module")
def nifty() -> pd.DataFrame:
    # Positional index: the reference detector uses `df.iloc[...]` throughout.
    return pd.read_csv(FIXTURE, parse_dates=["datetime"]).reset_index(drop=True)


@pytest.mark.parametrize("lookback", [20, 30])
def test_vectorised_matches_reference_bar_for_bar(nifty, lookback):
    """The whole point. Every bar, both directions, real data."""
    reference = LiquiditySweepDetector(swing_lookback=lookback)
    result = liquidity.reference_sweeps(nifty, lookback, liquidity.REFERENCE_RECENT_BARS)

    expected_bull = np.array([reference.detect(nifty, i, 1) for i in range(len(nifty))])
    expected_bear = np.array([reference.detect(nifty, i, -1) for i in range(len(nifty))])

    bull_mismatch = np.flatnonzero(result.bullish != expected_bull)
    bear_mismatch = np.flatnonzero(result.bearish != expected_bear)

    assert bull_mismatch.size == 0, (
        f"bullish sweeps differ at {bull_mismatch.size} bars, first "
        f"{bull_mismatch[:5].tolist()}")
    assert bear_mismatch.size == 0, (
        f"bearish sweeps differ at {bear_mismatch.size} bars, first "
        f"{bear_mismatch[:5].tolist()}")


def test_reference_actually_fires_on_this_fixture(nifty):
    """Guards against a vacuous pass: both arrays being empty would also
    'match'."""
    result = liquidity.reference_sweeps(nifty, 20, 5)
    assert result.bullish.sum() > 20
    assert result.bearish.sum() > 20


def test_warmup_guard_is_preserved(nifty):
    """The reference refuses any bar with `idx < swing_lookback * 2`."""
    result = liquidity.reference_sweeps(nifty, 20, 5)
    assert not result.bullish[:40].any()
    assert not result.bearish[:40].any()


def test_current_bar_is_excluded():
    """A sweep must be carried by a bar BEFORE the one being evaluated.

    The reference slices `df.iloc[idx - lookback : idx]`, which stops short of
    `idx`. A detector that included the current bar would be reading the bar
    still forming, live.
    """
    n = 60
    frame = pd.DataFrame({
        "open": np.full(n, 100.0), "high": np.full(n, 101.0),
        "low": np.full(n, 99.0), "close": np.full(n, 100.0),
        "volume": np.ones(n),
    })
    # A single sweep bar at the very end: wick below everything, close back up.
    frame.loc[n - 1, "low"] = 90.0
    frame.loc[n - 1, "close"] = 100.0

    result = liquidity.reference_sweeps(frame, 20, 5)
    assert not result.bullish[n - 1], "the evaluated bar must not sweep itself"


def test_break_is_not_a_sweep():
    """Wicking through and CLOSING beyond the level is a break, not a sweep."""
    n = 60
    frame = pd.DataFrame({
        "open": np.full(n, 100.0), "high": np.full(n, 101.0),
        "low": np.full(n, 99.0), "close": np.full(n, 100.0),
        "volume": np.ones(n),
    })
    level_low = 99.0
    # Bar n-3 pierces below and CLOSES below -> a break.
    frame.loc[n - 3, "low"] = 95.0
    frame.loc[n - 3, "close"] = 96.0

    levels_low = np.full(n, level_low)
    levels_high = np.full(n, np.nan)
    result = liquidity.key_level_sweeps(frame, levels_low, levels_high, 5, warmup=0)
    assert not result.bullish[n - 1], "a close beyond the level is a break"

    # Same bar, but closing back ABOVE the level -> a sweep.
    frame.loc[n - 3, "close"] = 100.0
    result = liquidity.key_level_sweeps(frame, levels_low, levels_high, 5, warmup=0)
    assert result.bullish[n - 1], "wick through + close back inside is a sweep"


def test_named_level_sweep_records_level_and_extreme():
    n = 40
    frame = pd.DataFrame({
        "open": np.full(n, 100.0), "high": np.full(n, 101.0),
        "low": np.full(n, 99.0), "close": np.full(n, 100.0),
        "volume": np.ones(n),
    })
    frame.loc[n - 2, "low"] = 94.0
    levels_low = np.full(n, 98.0)
    result = liquidity.key_level_sweeps(frame, levels_low, np.full(n, np.nan), 5, 0)
    assert result.bullish[n - 1]
    assert result.bullish_level[n - 1] == pytest.approx(98.0)
    assert result.bullish_extreme[n - 1] == pytest.approx(94.0)


def test_nan_levels_never_sweep():
    n = 40
    frame = pd.DataFrame({
        "open": np.full(n, 100.0), "high": np.full(n, 101.0),
        "low": np.full(n, 90.0), "close": np.full(n, 100.0),
        "volume": np.ones(n),
    })
    nans = np.full(n, np.nan)
    result = liquidity.key_level_sweeps(frame, nans, nans.copy(), 5, 0)
    assert not result.bullish.any() and not result.bearish.any()


def test_combine_keeps_the_deeper_wick():
    n = 20
    a = liquidity.SweepResult(
        bullish=np.array([True] * n), bearish=np.zeros(n, dtype=bool),
        bullish_level=np.full(n, 100.0), bearish_level=np.full(n, np.nan),
        bullish_extreme=np.full(n, 95.0), bearish_extreme=np.full(n, np.nan))
    b = liquidity.SweepResult(
        bullish=np.array([True] * n), bearish=np.zeros(n, dtype=bool),
        bullish_level=np.full(n, 99.0), bearish_level=np.full(n, np.nan),
        bullish_extreme=np.full(n, 90.0), bearish_extreme=np.full(n, np.nan))
    merged = liquidity.combine(a, b)
    assert merged.bullish.all()
    # The deeper wick (90) wins: it is the more meaningful stop run and gives
    # the structural stop the wider, safer invalidation.
    assert merged.bullish_extreme[0] == pytest.approx(90.0)


def test_empty_frame_is_handled():
    empty = pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
    result = liquidity.reference_sweeps(empty)
    assert result.bullish.shape[0] == 0
