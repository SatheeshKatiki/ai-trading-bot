"""shared/risk/instrument_focus.py — per-instrument AI-confidence gating.

Covers the mechanism behind "mainly focus NIFTY and SENSEX": those two trade
at whatever confidence bar the active strategy already computed; BANKNIFTY
and FINNIFTY need at least a stricter floor. The function must never LOWER
a strategy's own bar (e.g. enhanced_ai's 0.85 must not be relaxed to a lower
secondary floor), only ever raise it for non-focus instruments.
"""
import _bootstrap  # noqa: F401  (side-effect: puts trading-system/ on sys.path)

import pytest

from shared.risk.instrument_focus import (
    DEFAULT_FOCUS_INSTRUMENTS,
    DEFAULT_SECONDARY_MIN_CONFIDENCE,
    resolve_min_confidence,
)


def test_focus_instruments_keep_the_base_threshold():
    for instrument in ("NIFTY", "SENSEX"):
        assert resolve_min_confidence(instrument, 0.60) == 0.60


def test_secondary_instruments_are_raised_to_the_floor():
    for instrument in ("BANKNIFTY", "FINNIFTY"):
        assert resolve_min_confidence(instrument, 0.60) == pytest.approx(
            DEFAULT_SECONDARY_MIN_CONFIDENCE
        )


def test_a_stricter_base_threshold_is_never_relaxed():
    """enhanced_ai's own 0.85 bar must survive being applied to a secondary
    instrument, even though the secondary floor is also 0.85 — the function
    takes the max, never lowers."""
    result = resolve_min_confidence("BANKNIFTY", 0.90, {"secondary_instrument_min_confidence": 0.85})
    assert result == 0.90


def test_matching_is_case_insensitive():
    assert resolve_min_confidence("nifty", 0.60) == 0.60
    assert resolve_min_confidence("banknifty", 0.60) == pytest.approx(
        DEFAULT_SECONDARY_MIN_CONFIDENCE
    )


def test_default_focus_set_is_nifty_and_sensex():
    assert set(DEFAULT_FOCUS_INSTRUMENTS) == {"NIFTY", "SENSEX"}


def test_custom_focus_instruments_setting_is_honoured():
    settings = {"focus_instruments": ["BANKNIFTY"]}
    assert resolve_min_confidence("BANKNIFTY", 0.60, settings) == 0.60
    assert resolve_min_confidence("NIFTY", 0.60, settings) == pytest.approx(
        DEFAULT_SECONDARY_MIN_CONFIDENCE
    )


def test_custom_secondary_floor_is_honoured():
    settings = {"secondary_instrument_min_confidence": 0.95}
    assert resolve_min_confidence("FINNIFTY", 0.60, settings) == pytest.approx(0.95)


def test_missing_settings_falls_back_to_defaults():
    assert resolve_min_confidence("FINNIFTY", 0.60, None) == pytest.approx(
        DEFAULT_SECONDARY_MIN_CONFIDENCE
    )
    assert resolve_min_confidence("FINNIFTY", 0.60, {}) == pytest.approx(
        DEFAULT_SECONDARY_MIN_CONFIDENCE
    )


def test_sizing_and_risk_caps_are_out_of_scope_for_this_function():
    """This module only ever returns a confidence threshold — it has no
    concept of position size or risk amount, which is the point: focus is
    expressed purely as a signal-quality gate, not a capital-allocation
    decision."""
    import inspect

    signature = inspect.signature(resolve_min_confidence)
    assert set(signature.parameters) == {"instrument", "base_min_confidence", "settings"}
