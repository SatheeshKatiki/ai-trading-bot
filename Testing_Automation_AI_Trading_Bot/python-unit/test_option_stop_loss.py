"""Premium-banded initial stop-loss for option buying.

Covers shared/risk/option_stop_loss.py end to end: every band from the spec,
the continuity properties the interpolation is supposed to guarantee, the
premium-floor clamp, config overrides, and the malformed-config fallback that
must never be able to stop the live engine from trading.
"""
import _bootstrap  # noqa: F401  (side-effect: puts trading-system/ on sys.path)

import pytest

from shared.risk.option_stop_loss import (
    DEFAULT_BANDS,
    DEFAULT_MAX_SL_PCT_OF_PREMIUM,
    resolve_initial_stop,
    resolve_stop_points,
)


# ---------------------------------------------------------------------------
# The specified bands
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "premium, lo, hi",
    [
        # premium, expected stop-distance range (rupees) from the spec table
        (5.0, 2.0, 3.0),
        (9.99, 2.0, 3.0),
        (10.0, 3.0, 5.0),
        (15.0, 3.0, 5.0),
        (19.99, 3.0, 5.0),
        (20.0, 5.0, 8.0),
        (35.0, 5.0, 8.0),
        (49.99, 5.0, 8.0),
        (50.0, 10.0, 15.0),
        (75.0, 10.0, 15.0),
        (99.99, 10.0, 15.0),
        (100.0, 15.0, 20.0),
        (125.0, 15.0, 20.0),
        (149.99, 15.0, 20.0),
        (150.0, 20.0, 30.0),
        (200.0, 20.0, 30.0),
        (249.99, 20.0, 30.0),
    ],
)
def test_stop_distance_falls_inside_its_band(premium, lo, hi):
    decision = resolve_initial_stop(premium)
    # Tick rounding can move the distance by half a tick either way.
    assert lo - 0.05 <= decision.sl_points <= hi + 0.05
    assert decision.sl_price == pytest.approx(premium - decision.sl_points, abs=0.051)
    assert decision.sl_price > 0


def test_dynamic_band_above_250_is_percentage_based():
    decision = resolve_initial_stop(300.0)
    assert decision.method == "dynamic_pct"
    # Tapering from 12% at 250 toward 10% at 500 → ~11.6% at 300.
    assert 10.0 <= decision.sl_pct <= 12.0


def test_dynamic_band_tapers_to_the_floor_percentage():
    far = resolve_initial_stop(900.0)
    assert far.sl_pct == pytest.approx(10.0, abs=0.1)


def test_deep_premium_risks_a_smaller_share_than_a_cheap_one():
    """The whole point of the table: percentage risk falls as premium rises."""
    cheap = resolve_initial_stop(8.0)
    mid = resolve_initial_stop(120.0)
    deep = resolve_initial_stop(400.0)
    assert cheap.sl_pct > mid.sl_pct > deep.sl_pct


# ---------------------------------------------------------------------------
# Continuity — the reason interpolation was chosen over a flat midpoint
# ---------------------------------------------------------------------------

def test_stop_distance_is_monotonic_in_premium():
    previous = 0.0
    premium = 1.0
    while premium <= 600.0:
        points = resolve_stop_points(premium)
        assert points >= previous - 0.051, (
            f"stop distance went backwards at premium {premium}: "
            f"{points} < {previous}"
        )
        previous = points
        premium += 0.5


def test_interpolation_hits_the_band_edges_exactly():
    for band in DEFAULT_BANDS:
        at_lower = resolve_stop_points(band.lower if band.lower > 0 else 0.5)
        at_upper = resolve_stop_points(band.upper - 0.01)
        if band.lower > 0:
            assert at_lower == pytest.approx(band.min_points, abs=0.06)
        assert at_upper == pytest.approx(band.max_points, abs=0.06)


def test_handover_to_the_dynamic_band_is_continuous():
    """₹250 is where the fixed table hands over to the percentage band.

    The last band tops out at ₹30 and the dynamic band starts at 12%, and
    12% of ₹250 is also ₹30 — chosen so there is no step at the boundary.
    """
    just_below = resolve_stop_points(249.99)
    just_above = resolve_stop_points(250.01)
    assert abs(just_above - just_below) < 0.1


# ---------------------------------------------------------------------------
# Safety rails
# ---------------------------------------------------------------------------

def test_cheap_option_stop_is_clamped_to_a_share_of_premium():
    """A ₹2.5 option with a ₹2 band stop would leave a ₹0.50 stop price —
    risking 80% of the contract on one tick."""
    decision = resolve_initial_stop(2.5)
    assert decision.clamped is True
    assert decision.sl_points <= 2.5 * (DEFAULT_MAX_SL_PCT_OF_PREMIUM / 100.0) + 0.05
    assert decision.sl_price > 0


def test_stop_price_is_always_positive_and_placeable():
    for premium in (0.5, 1.0, 2.0, 5.0, 10.0, 250.0, 1000.0):
        decision = resolve_initial_stop(premium)
        assert decision.sl_price > 0, f"non-positive stop for premium {premium}"
        assert decision.sl_price < premium
        assert decision.is_tradeable is True
        # Must land on the 0.05 tick grid to be placeable as an SL-M trigger.
        assert abs(round(decision.sl_price / 0.05) * 0.05 - decision.sl_price) < 1e-6


def test_sub_tick_premium_is_reported_untradeable_not_given_a_fake_stop():
    """A one-tick contract cannot carry a stop below itself. The resolver
    must say so rather than return a stop sitting at the entry price — the
    entry path skips the trade on this flag."""
    decision = resolve_initial_stop(0.05)
    assert decision.is_tradeable is False
    assert decision.sl_price > 0  # still never negative or zero


def test_non_positive_premium_is_a_programming_error():
    for bad in (0.0, -1.0):
        with pytest.raises(ValueError):
            resolve_initial_stop(bad)


# ---------------------------------------------------------------------------
# Configurability
# ---------------------------------------------------------------------------

def test_band_mode_min_mid_max_are_honoured():
    premium = 35.0  # ₹20-50 band → ₹5-8
    assert resolve_stop_points(premium, {"option_sl_band_mode": "min"}) == pytest.approx(5.0, abs=0.05)
    assert resolve_stop_points(premium, {"option_sl_band_mode": "max"}) == pytest.approx(8.0, abs=0.05)
    assert resolve_stop_points(premium, {"option_sl_band_mode": "mid"}) == pytest.approx(6.5, abs=0.05)


def test_custom_band_table_overrides_the_default():
    settings = {
        "option_sl_bands": [
            {"lower": 0, "upper": 100, "min_points": 1, "max_points": 1},
        ],
    }
    assert resolve_stop_points(50.0, settings) == pytest.approx(1.0, abs=0.05)


def test_custom_dynamic_band_is_honoured():
    settings = {
        "option_sl_bands": [{"lower": 0, "upper": 100, "min_points": 5, "max_points": 5}],
        "option_sl_dynamic": {"lower": 100.0, "start_pct": 20.0, "end_pct": 20.0, "taper_to": 200.0},
    }
    decision = resolve_initial_stop(150.0, settings)
    assert decision.method == "dynamic_pct"
    assert decision.sl_pct == pytest.approx(20.0, abs=0.2)


def test_malformed_band_config_falls_back_instead_of_raising():
    """This runs inside the live entry path — a typo in settings.json must
    not be able to take the engine down or block every trade."""
    for broken in (
        [{"lower": "not-a-number", "upper": 10, "min_points": 2, "max_points": 3}],
        [{"upper": 10}],
        ["nonsense"],
        [],
    ):
        decision = resolve_initial_stop(120.0, {"option_sl_bands": broken})
        assert decision.sl_points > 0
        # Falls back to the default table's ₹100-150 band.
        assert 15.0 - 0.05 <= decision.sl_points <= 20.0 + 0.05


def test_tick_size_is_configurable():
    decision = resolve_initial_stop(120.0, {"option_sl_tick_size": 1.0})
    assert decision.sl_price == pytest.approx(round(decision.sl_price), abs=1e-9)


def test_decision_reports_its_band_and_method_for_the_journal():
    banded = resolve_initial_stop(120.0)
    assert banded.method == "banded"
    assert banded.band_label == "₹100-150"

    dynamic = resolve_initial_stop(400.0)
    assert dynamic.method == "dynamic_pct"
    assert dynamic.band_label == ">₹250"
