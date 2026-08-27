"""Regression coverage for a live 2026-08-25 finding: a spot price of
`0.0` reaching `options_selector.select_option()` blew up inside
`calculate_greeks()`'s `math.log(spot / strike)` with
`ValueError: expected a positive input, got 0.0`, logged by main.py's
option auto-map block as a generic "Failed to auto-map option" error.

Root cause: `on_tick`'s auto-map block called `select_option(instrument_key,
ltp, ...)` with whatever `ltp = tick["ltp"]` happened to be, with no check
that it was a real, positive price. A malformed/keepalive tick (or any
other zero/negative `ltp`) fed the Black-Scholes math a spot price it can
never validly handle.

Fixed by extracting `_has_valid_spot_price_for_option_mapping()` (used as
an early guard in `on_tick` before `select_option()` is ever called) —
this test pins that pure predicate, and separately documents the
underlying `calculate_greeks` behavior the guard exists to avoid
triggering.
"""
import math

import pytest

import _bootstrap  # noqa: F401  (side-effect: puts trading-system/ on sys.path)

from trading_bot.main import _has_valid_spot_price_for_option_mapping
from trading_bot.strategies.premium_selection.options_selector import calculate_greeks


def test_rejects_zero_spot_price():
    assert _has_valid_spot_price_for_option_mapping(0.0) is False


def test_rejects_negative_spot_price():
    assert _has_valid_spot_price_for_option_mapping(-1.0) is False


def test_accepts_a_real_spot_price():
    assert _has_valid_spot_price_for_option_mapping(24350.5) is True


def test_calculate_greeks_with_zero_spot_raises_the_exact_error_the_guard_exists_to_avoid():
    """Documents the failure the 2026-08-25 incident hit live: without the
    on_tick guard, a zero spot price reaches this math.log call directly."""
    with pytest.raises(ValueError, match="expected a positive input"):
        calculate_greeks(0.0, 24350, days_to_expiry=3, option_type="CE")


def test_calculate_greeks_with_a_real_spot_price_does_not_raise():
    greeks = calculate_greeks(24350.5, 24350, days_to_expiry=3, option_type="CE")
    assert math.isfinite(greeks["delta"])
    assert math.isfinite(greeks["theta"])
