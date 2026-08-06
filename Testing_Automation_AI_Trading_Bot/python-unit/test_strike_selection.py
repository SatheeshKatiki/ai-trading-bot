"""Strike selection: ATM/ITM only, never OTM — and nearest-expiry correctness.

Covers two things requested together: (1) select_option() must be
architecturally incapable of returning an OTM strike, regardless of what a
caller passes, and (2) expiry selection always resolves to the nearest
upcoming contract with the correct exchange calendar.

Before this, the "never OTM" property held only because both real call sites
happened to always pass itm_strikes=1 — a caller convention, not a guarantee.
These tests exercise the guarantee directly by trying to break it.
"""
from datetime import date, timedelta

import _bootstrap  # noqa: F401  (side-effect: puts trading-system/ on sys.path)

import pytest

from trading_bot.strategies.premium_selection.options_selector import (
    MAX_ITM_STRIKES,
    MIN_ITM_STRIKES,
    INSTRUMENT_CONFIG,
    select_option,
)


SPOT = 24_512.0  # NIFTY spot, arbitrary but realistic


def _atm_strike(spot: float, step: int) -> float:
    return round(spot / step) * step


def _is_itm_or_atm(strike: float, spot: float, direction: str, step: int) -> bool:
    """True if `strike` is at least as far ITM as the ATM strike itself.

    Comparing against the raw spot price (rather than the ATM strike) is the
    wrong test here: strikes sit on a discrete grid, so "ATM" (the nearest
    strike to spot) is essentially never exactly at spot — it can legally
    fall a few points to either side of it. What select_option() actually
    guarantees is that the resolved offset never moves PAST the ATM strike
    in the OTM direction, which is what this compares against instead.

    CALL: ITM/ATM when strike <= the ATM strike.
    PUT:  ITM/ATM when strike >= the ATM strike.
    """
    atm = _atm_strike(spot, step)
    if direction == "CE":
        return strike <= atm
    return strike >= atm


@pytest.mark.parametrize("direction", ["CE", "PE"])
@pytest.mark.parametrize("requested_offset", [-10, -2, -1, 0, 1, 2, 3, 5, 100])
def test_never_selects_an_otm_strike_regardless_of_requested_offset(direction, requested_offset):
    """The core guarantee: no matter what a caller (buggy, malicious, or a
    future strategy) passes, the resulting strike is never OTM."""
    contract = select_option("NIFTY", SPOT, direction, itm_strikes=requested_offset)
    step = INSTRUMENT_CONFIG["NIFTY"]["strike_step"]

    assert _is_itm_or_atm(contract.strike, SPOT, direction, step), (
        f"{direction} strike {contract.strike} is OTM relative to spot {SPOT} "
        f"(requested_offset={requested_offset})"
    )


def test_negative_offset_is_clamped_to_atm_not_otm():
    """A negative itm_strikes would, without clamping, push the strike to
    the OTM side of spot. It must land on ATM instead."""
    call = select_option("NIFTY", SPOT, "CE", itm_strikes=-5)
    put = select_option("NIFTY", SPOT, "PE", itm_strikes=-5)

    atm = round(SPOT / INSTRUMENT_CONFIG["NIFTY"]["strike_step"]) * INSTRUMENT_CONFIG["NIFTY"]["strike_step"]
    assert call.strike == atm
    assert put.strike == atm
    assert call.itm_offset == MIN_ITM_STRIKES


def test_excessive_offset_is_clamped_to_the_max():
    contract = select_option("NIFTY", SPOT, "CE", itm_strikes=50)
    assert contract.itm_offset == MAX_ITM_STRIKES


def test_default_offset_is_atm():
    """select_option()'s own default (no itm_strikes passed) is ATM (0) —
    "maximum preferred ATM only". Both live call sites in main.py
    explicitly opt into itm_strikes=1 for liquidity; the function itself
    defaults to the most conservative choice."""
    contract = select_option("NIFTY", SPOT, "CE")
    assert contract.itm_offset == 0


@pytest.mark.parametrize("instrument", ["NIFTY", "BANKNIFTY", "FINNIFTY", "SENSEX"])
@pytest.mark.parametrize("direction", ["CE", "PE"])
def test_atm_and_itm1_are_itm_or_atm_for_every_instrument(instrument, direction):
    """Sweep all four tradeable instruments — the guarantee must hold
    everywhere, not just for NIFTY."""
    spot = 52_000.0 if instrument == "BANKNIFTY" else (
        80_000.0 if instrument == "SENSEX" else 23_500.0
    )
    step = INSTRUMENT_CONFIG[instrument]["strike_step"]
    for offset in (0, 1):
        contract = select_option(instrument, spot, direction, itm_strikes=offset)
        assert _is_itm_or_atm(contract.strike, spot, direction, step)


def test_atm_strike_is_the_nearest_valid_strike_to_spot():
    contract = select_option("NIFTY", SPOT, "CE", itm_strikes=0)
    step = INSTRUMENT_CONFIG["NIFTY"]["strike_step"]
    assert abs(contract.strike - SPOT) <= step / 2 + 1e-6


# ---------------------------------------------------------------------------
# Nearest expiry
# ---------------------------------------------------------------------------

def test_expiry_is_never_more_than_one_week_out():
    """_next_expiry always resolves to the soonest upcoming contract for the
    instrument's own weekly cycle — never skips ahead to a later one."""
    for instrument in ("NIFTY", "BANKNIFTY", "FINNIFTY", "SENSEX"):
        contract = select_option(instrument, SPOT, "CE")
        assert contract.expiry >= date.today()
        assert contract.expiry <= date.today() + timedelta(days=7)


def test_expiry_matches_each_instruments_configured_weekday():
    for instrument, cfg in INSTRUMENT_CONFIG.items():
        contract = select_option(instrument, SPOT, "CE")
        assert contract.expiry.weekday() == cfg["expiry_day"], (
            f"{instrument} resolved to weekday {contract.expiry.weekday()}, "
            f"expected {cfg['expiry_day']}"
        )


def test_nifty_and_banknifty_expire_tuesday_not_thursday():
    """NSE consolidated weekly index-options expiry to Tuesday for
    NIFTY/BANKNIFTY (verified 2026-08-03 against the live symbol master).
    A stale Thursday assumption would build a symbol for a non-existent
    contract on every entry."""
    assert INSTRUMENT_CONFIG["NIFTY"]["expiry_day"] == 1
    assert INSTRUMENT_CONFIG["BANKNIFTY"]["expiry_day"] == 1


def test_sensex_still_expires_thursday():
    """BSE's SENSEX weekly expiry is Thursday — distinct from NSE's Tuesday,
    and must not be accidentally aligned to it."""
    assert INSTRUMENT_CONFIG["SENSEX"]["expiry_day"] == 3
