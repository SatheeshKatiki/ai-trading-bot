"""Tests for the REAL broker option chain (2026-09-09).

`/api/option-chain` previously always returned a Black-Scholes *model* chain:
theoretical premiums from a `deterministic_random()` implied vol, invented
open interest, a PCR that was an MD5 hash of the spot price, "max pain" that
was just the ATM strike, a hardcoded past expiry, and **no bid/ask at all**.
`paper_observer.select_best_option()` reads `ltp`, `delta` and `pcr` from this
payload to pick strikes and set entry premiums, so paper fills were priced by
the model rather than the market.

It now prefers Fyers' real `/options-chain-v3`, which supplies traded
premiums, genuine bid/ask, real OI and OI change, real volume, the real expiry
series and the real India VIX. IV is recovered from each real premium by
bisection and the Greeks follow from that -- the honest direction, and the
inverse of the model chain which invented a vol and priced from it.

Verified live on 2026-09-09 against NIFTY: ATM CE IV 11.86 / PE IV 9.07
straddling a real India VIX of 11.23, ATM deltas +0.5158 / -0.4811, ATM spread
0.42-0.70%, and max pain 100 pts away from ATM (the old value was always
exactly ATM, so "distance to max pain" was structurally always zero).
"""

from __future__ import annotations

import math

import pytest

import api_bridge as ab


R = 0.065
T_WEEK = 6.0 / 365.0


# ---------------------------------------------------------------------------
# Implied volatility solver
# ---------------------------------------------------------------------------

def _bs_call(S, K, T, r, sigma):
    d1 = (math.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)
    ncdf = lambda x: (1.0 + math.erf(x / math.sqrt(2.0))) / 2.0
    return S * ncdf(d1) - K * math.exp(-r * T) * ncdf(d2)


def _bs_put(S, K, T, r, sigma):
    d1 = (math.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)
    ncdf = lambda x: (1.0 + math.erf(x / math.sqrt(2.0))) / 2.0
    return K * math.exp(-r * T) * ncdf(-d2) - S * ncdf(-d1)


@pytest.mark.parametrize("sigma", [0.08, 0.12, 0.20, 0.45])
def test_iv_solver_round_trips_a_known_call_vol(sigma):
    """Price a call at a known vol, then recover that vol from the price."""
    S, K = 23_650.0, 23_650.0
    premium = _bs_call(S, K, T_WEEK, R, sigma)
    got = ab._implied_vol(premium, S, K, T_WEEK, R, is_call=True)
    assert got == pytest.approx(sigma, abs=1e-3)


@pytest.mark.parametrize("sigma", [0.08, 0.12, 0.20, 0.45])
def test_iv_solver_round_trips_a_known_put_vol(sigma):
    S, K = 23_650.0, 23_700.0
    premium = _bs_put(S, K, T_WEEK, R, sigma)
    got = ab._implied_vol(premium, S, K, T_WEEK, R, is_call=False)
    assert got == pytest.approx(sigma, abs=1e-3)


def test_iv_is_none_for_pure_intrinsic_premium():
    """Deep ITM with no time value left cannot imply a vol.

    Returning None is the point: the frontend renders an em-dash. It used to
    substitute `Math.max(12, 28 - distance/100)` -- a fabricated smile that
    looked like data.
    """
    S, K = 24_000.0, 23_000.0
    assert ab._implied_vol(S - K, S, K, T_WEEK, R, is_call=True) is None


def test_iv_is_none_for_impossible_premium():
    """A premium above what any sane vol produces must not silently clamp."""
    assert ab._implied_vol(9_999.0, 23_650.0, 23_650.0, T_WEEK, R, is_call=True) is None


@pytest.mark.parametrize("bad", [0, -5, None])
def test_iv_rejects_non_positive_premiums(bad):
    assert ab._implied_vol(bad, 23_650.0, 23_650.0, T_WEEK, R, is_call=True) is None


# ---------------------------------------------------------------------------
# Greeks derived from that IV
# ---------------------------------------------------------------------------

def test_atm_call_delta_is_about_half():
    g = ab._greeks_from_iv(23_650.0, 23_650.0, T_WEEK, R, 0.12, is_call=True)
    assert 0.45 < g["delta"] < 0.60


def test_atm_put_delta_is_about_minus_half():
    g = ab._greeks_from_iv(23_650.0, 23_650.0, T_WEEK, R, 0.12, is_call=False)
    assert -0.60 < g["delta"] < -0.40


def test_put_call_delta_parity_holds():
    """delta_call - delta_put == 1 for the same strike, vol and expiry."""
    c = ab._greeks_from_iv(23_650.0, 23_700.0, T_WEEK, R, 0.12, is_call=True)
    p = ab._greeks_from_iv(23_650.0, 23_700.0, T_WEEK, R, 0.12, is_call=False)
    assert c["delta"] - p["delta"] == pytest.approx(1.0, abs=1e-3)


def test_theta_is_negative_for_long_options():
    """An option BUYER pays theta -- on both legs. Sign errors here would
    invert every decay-based exit rule downstream."""
    for is_call in (True, False):
        g = ab._greeks_from_iv(23_650.0, 23_650.0, T_WEEK, R, 0.12, is_call)
        assert g["theta"] < 0


def test_gamma_and_vega_are_positive_for_long_options():
    g = ab._greeks_from_iv(23_650.0, 23_650.0, T_WEEK, R, 0.12, is_call=True)
    assert g["gamma"] > 0 and g["vega"] > 0


def test_greeks_are_empty_without_a_usable_vol():
    assert ab._greeks_from_iv(23_650.0, 23_650.0, T_WEEK, R, None, True) == {}
    assert ab._greeks_from_iv(23_650.0, 23_650.0, 0.0, R, 0.12, True) == {}


# ---------------------------------------------------------------------------
# Leg normalisation -- the spread is the headline addition
# ---------------------------------------------------------------------------

def _row(**kw):
    base = {
        "ltp": 153.05, "bid": 153.65, "ask": 154.30, "strike_price": 23_650,
        "oi": 2_350_920, "oich": 617_695, "oichp": 265.97, "volume": 3_592_095,
        "ltpch": -109.9, "ltpchp": -30.2, "symbol": "NSE:NIFTY2691523650CE",
    }
    base.update(kw)
    return base


def test_leg_exposes_the_real_spread():
    """Bid/ask is what an option buyer actually pays away, twice.

    The model chain had none, so every fill priced against it implicitly
    assumed perfect mid-price execution.
    """
    leg = ab._chain_leg(_row(), 23_635.1, T_WEEK, R, is_call=True)
    assert leg["bid"] == 153.65 and leg["ask"] == 154.30
    assert leg["spread"] == pytest.approx(0.65, abs=0.01)
    assert leg["spread_pct"] == pytest.approx(0.42, abs=0.02)


def test_leg_spread_is_none_when_unquoted():
    """No two-sided quote means no spread -- not a spread of zero."""
    leg = ab._chain_leg(_row(bid=0, ask=0), 23_635.1, T_WEEK, R, is_call=True)
    assert leg["spread"] is None and leg["spread_pct"] is None


def test_leg_carries_real_open_interest_unmodified():
    leg = ab._chain_leg(_row(), 23_635.1, T_WEEK, R, is_call=True)
    assert leg["oi"] == 2_350_920
    assert leg["oichg"] == 617_695
    assert leg["volume"] == 3_592_095


def test_leg_iv_and_greeks_are_derived_from_the_traded_premium():
    leg = ab._chain_leg(_row(), 23_635.1, T_WEEK, R, is_call=True)
    assert leg["iv"] is not None and 1 < leg["iv"] < 100
    assert 0.3 < leg["delta"] < 0.7
    assert leg["theta"] < 0
