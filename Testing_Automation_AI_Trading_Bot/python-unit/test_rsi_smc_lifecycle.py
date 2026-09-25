"""The causal / analytical split, and the SMC object lifecycle.

Two things are asserted here:

1. **Nothing is thrown away.** Order Blocks, swing pivots, premium/discount,
   the end-of-frame trend -- every retrospective SMC field remains available
   on the analytical surface, with explicit lifecycle timestamps.
2. **Nothing retrospective can reach a trading decision.** The strategy reads
   only the causal surface, and every object on it is gated on its own
   confirmation bar.

The strict rule this enforces, for every feature: *could the live engine have
known this exact value using only information available at or before
decision_time?* If not, it is blocked until its confirmation bar.
"""
from __future__ import annotations

import pathlib

import numpy as np
import pandas as pd
import pytest

import _bootstrap  # noqa: F401

from trading_bot.strategies.rsi_smc_options_buyer import (
    signal_engine,
    smc_lifecycle,
    structure,
)
from trading_bot.strategies.rsi_smc_options_buyer.config import RsiSmcConfig
from trading_bot.strategies.rsi_smc_options_buyer.smc_lifecycle import SmcState

FIXTURE = (pathlib.Path(__file__).resolve().parent / "fixtures" / "data"
           / "rsi_smc_NIFTY_5Min.csv")

ALL_KINDS = (
    smc_lifecycle.KIND_ORDER_BLOCK,
    smc_lifecycle.KIND_FVG,
    smc_lifecycle.KIND_LIQUIDITY_POOL,
    smc_lifecycle.KIND_SWING,
    smc_lifecycle.KIND_STRUCTURE_EVENT,
)


@pytest.fixture(scope="module")
def nifty() -> pd.DataFrame:
    return pd.read_csv(FIXTURE, parse_dates=["datetime"]).set_index("datetime")


@pytest.fixture(autouse=True)
def _clean():
    structure.clear_cache()
    yield
    structure.clear_cache()


# ---------------------------------------------------------------------
# Nothing is deleted
# ---------------------------------------------------------------------

@pytest.mark.parametrize("kind", ALL_KINDS)
def test_every_smc_kind_is_retained_for_analysis(nifty, kind):
    """Retrospective SMC data is kept, not discarded."""
    analytical = structure.build_analytical(nifty, RsiSmcConfig())
    assert analytical.of_kind(kind), f"{kind} must remain available for charts/research"


def test_end_of_frame_scalars_are_retained_with_an_as_of_stamp(nifty):
    """The fields the causal view refuses are still available here.

    They describe the frame's LAST bar, so they carry an explicit `as_of`
    timestamp rather than pretending to be per-bar.
    """
    analytical = structure.build_analytical(nifty, RsiSmcConfig())
    assert analytical.as_of_index == len(nifty) - 1
    assert analytical.as_of_time == nifty.index[-1]
    assert analytical.equilibrium_price is not None
    assert analytical.premium_zone != (0.0, 0.0)
    assert analytical.discount_zone != (0.0, 0.0)
    assert analytical.ote_zone != (0.0, 0.0)
    assert analytical.trend in (-1, 0, 1)


def test_analytical_records_are_chart_ready(nifty):
    """Each record carries origin, confirmation and (where applicable)
    invalidation, so a chart can label CANDIDATE vs CONFIRMED."""
    analytical = structure.build_analytical(nifty, RsiSmcConfig())
    records = analytical.records()
    assert records
    required = {"kind", "id", "origin_index", "origin_time",
                "confirmation_index", "confirmation_time", "confirmation_lag",
                "invalidation_index", "mitigation_index"}
    assert required <= set(records[0])

    blocks = [r for r in records if r["kind"] == smc_lifecycle.KIND_ORDER_BLOCK]
    assert blocks
    assert any(r["confirmation_lag"] > 0 for r in blocks), (
        "order blocks are confirmed after their origin bar -- that lag is the "
        "whole reason this model exists")


# ---------------------------------------------------------------------
# Nothing retrospective reaches the strategy
# ---------------------------------------------------------------------

def test_analytical_view_is_refused_by_the_causal_guard(nifty):
    analytical = structure.build_analytical(nifty, RsiSmcConfig())
    with pytest.raises(structure.LookAheadError):
        structure.assert_causal(analytical)


def test_causal_view_passes_the_guard(nifty):
    structure.assert_causal(structure.build(nifty, RsiSmcConfig()))


@pytest.mark.parametrize("impostor", [None, object(), {"in_bull_fvg": []}])
def test_arbitrary_objects_are_refused(impostor):
    with pytest.raises(structure.LookAheadError):
        structure.assert_causal(impostor)


def test_signal_engine_calls_the_guard(nifty, monkeypatch):
    """The guard must actually be wired, not merely defined."""
    called = {"n": 0}
    real = structure.assert_causal

    def counting(view):
        called["n"] += 1
        return real(view)

    monkeypatch.setattr(signal_engine._structure, "assert_causal", counting)
    signal_engine.build(nifty, RsiSmcConfig())
    assert called["n"] >= 1


def test_causal_view_exposes_no_end_of_frame_scalar(nifty):
    view = structure.build(nifty, RsiSmcConfig())
    for field in structure.FORBIDDEN_PER_BAR_FIELDS:
        with pytest.raises(structure.LookAheadError):
            getattr(view, field)


# ---------------------------------------------------------------------
# The lifecycle model itself
# ---------------------------------------------------------------------

def test_state_transitions_are_monotonic(nifty):
    """Once an object leaves CANDIDATE it never returns to it."""
    analytical = structure.build_analytical(nifty, RsiSmcConfig())
    for obj in analytical.objects[:200]:
        seen_confirmed = False
        for index in range(0, analytical.n, max(1, analytical.n // 40)):
            state = obj.state_at(index)
            if state is not SmcState.CANDIDATE:
                seen_confirmed = True
            elif seen_confirmed:
                pytest.fail(f"{obj.object_id} returned to CANDIDATE at {index}")


@pytest.mark.parametrize("kind", ALL_KINDS)
def test_confirmation_never_precedes_origin(nifty, kind):
    analytical = structure.build_analytical(nifty, RsiSmcConfig())
    for obj in analytical.of_kind(kind):
        assert obj.confirmation_index >= obj.origin_index, (
            f"{obj.object_id} claims to be knowable before it existed")


def test_usable_at_matches_active_mask(nifty):
    analytical = structure.build_analytical(nifty, RsiSmcConfig())
    for obj in analytical.objects[:50]:
        mask = obj.active_mask(analytical.n)
        for index in (0, analytical.n // 3, analytical.n - 1):
            assert bool(mask[index]) == obj.usable_at(index)


def test_swing_pivot_confirmation_uses_the_pivot_window(nifty):
    """A pivot is a strict extremum over [p-L, p+L], so it is knowable at
    p+L -- not at p."""
    cfg = RsiSmcConfig()
    view = structure.build(nifty, cfg)
    analytical = structure.build_analytical(nifty, cfg)
    swings = analytical.of_kind(smc_lifecycle.KIND_SWING)
    assert swings
    for swing in swings[:20]:
        assert swing.confirmation_lag == view.effective_swing_len


def test_structure_events_are_confirmed_on_their_own_bar(nifty):
    analytical = structure.build_analytical(nifty, RsiSmcConfig())
    events = analytical.of_kind(smc_lifecycle.KIND_STRUCTURE_EVENT)
    assert events
    assert all(e.confirmation_lag == 0 for e in events)


def test_liquidity_pool_confirmation_lag_is_the_pivot_delay(nifty):
    cfg = RsiSmcConfig()
    view = structure.build(nifty, cfg)
    analytical = structure.build_analytical(nifty, cfg)
    pools = analytical.of_kind(smc_lifecycle.KIND_LIQUIDITY_POOL)
    assert pools
    assert {p.confirmation_lag for p in pools} == {view.pool_availability_delay}


# ---------------------------------------------------------------------
# One computation feeds both surfaces
# ---------------------------------------------------------------------

def test_both_surfaces_share_one_calculate_smc_run(nifty):
    cfg = RsiSmcConfig()
    structure.clear_cache()
    structure.build(nifty, cfg, symbol="NIFTY")
    structure.build_analytical(nifty, cfg, symbol="NIFTY")
    stats = structure.cache_stats()
    assert stats["misses"] == 1, "the analytical surface must not recompute SMC"
    assert stats["hits"] == 1


# ---------------------------------------------------------------------
# The strategy's rules are unchanged by the architecture
# ---------------------------------------------------------------------

def test_order_block_trigger_is_off_by_default(nifty):
    """Making Order Blocks causally available must not silently change the
    entry rules."""
    assert RsiSmcConfig().use_ob_trigger is False

    structure.clear_cache()
    default_signals, _, _, _ = signal_engine.build(nifty, RsiSmcConfig())
    structure.clear_cache()
    explicit, _, _, _ = signal_engine.build(
        nifty, RsiSmcConfig(use_ob_trigger=False))
    np.testing.assert_array_equal(default_signals, explicit)


def test_order_block_trigger_can_be_enabled_for_research(nifty):
    structure.clear_cache()
    cfg = RsiSmcConfig(use_ob_trigger=True)
    signals, _, _, _ = signal_engine.build(nifty, cfg)
    assert set(np.unique(signals)) <= {-1, 0, 1}
