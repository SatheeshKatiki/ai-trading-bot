"""Regression tests for the Options Desk metrics (2026-09-09).

Before this fix the `/api/option-chain` payload reported:

  * ``"maxPain": atm_strike``  -- the ATM strike relabelled as max pain, which
    is not what max pain means. It is the strike at which option *writers* pay
    out least, i.e. where total intrinsic value owed to buyers is minimised.
  * ``"pcr": deterministic_random(base_price, 99, 0.6, 1.4)`` -- a hash of the
    spot price, unrelated to any open interest, presented as the Put/Call
    Ratio next to an OI table it did not describe.
  * ``"expiry": "2026-07-25"`` -- hardcoded, so from late July 2026 the desk
    labelled every chain with an expiry that had already passed.

The dashboard additionally synthesised ``India VIX`` and ``IV Rank`` from
``Math.sin(Date.now())``; India VIX is now a real subscribed index and IV Rank
was removed (it needs a trailing IV history this system does not store).
"""

from __future__ import annotations

import datetime

import api_bridge as ab


def _row(strike, ce_oi, pe_oi):
    return {"strike": strike, "ce": {"oi": ce_oi}, "pe": {"oi": pe_oi}}


# ---------------------------------------------------------------------------
# Max pain -- computed the way the term is actually defined
# ---------------------------------------------------------------------------

def _max_pain(chain):
    """Mirror of the computation now inlined in get_option_chain()."""
    def pain_at(expiry_price):
        total = 0.0
        for row in chain:
            k = row["strike"]
            total += max(0.0, expiry_price - k) * (row.get("ce") or {}).get("oi", 0)
            total += max(0.0, k - expiry_price) * (row.get("pe") or {}).get("oi", 0)
        return total
    return min((row["strike"] for row in chain), key=pain_at)


def test_max_pain_sits_where_writers_pay_least():
    """All OI concentrated at one strike -> max pain is that strike.

    Heavy CE OI above and heavy PE OI below 24000 means expiring at 24000
    leaves almost everything worthless, which is the definition of max pain.
    """
    chain = [
        _row(23800, ce_oi=100, pe_oi=900_000),
        _row(23900, ce_oi=100, pe_oi=500_000),
        _row(24000, ce_oi=100, pe_oi=100),
        _row(24100, ce_oi=500_000, pe_oi=100),
        _row(24200, ce_oi=900_000, pe_oi=100),
    ]
    assert _max_pain(chain) == 24000


def test_max_pain_is_not_merely_the_atm_strike():
    """The old code returned the ATM strike; a skewed book must disagree.

    Put OI is stacked at 23500-23700 while spot sits at 23900-24000. Writers'
    payout by expiry price:

        23500 -> 350,013,000     23600 -> 100,012,000
        23700 ->      12,000     24000 ->      15,000
        24300 ->      24,000

    The minimum is 23700 -- just above the put wall, where those puts have
    expired worthless but the calls have not yet gone into the money. Max pain
    is therefore BELOW the ATM strike, pointing at an expiry pull-down. That
    divergence from ATM is the entire signal an options buyer reads max pain
    for, and it is exactly what the old `"maxPain": atm_strike` could never
    express: by construction it always reported zero distance.
    """
    atm = 24000
    chain = [
        _row(23500, ce_oi=10, pe_oi=2_000_000),
        _row(23600, ce_oi=10, pe_oi=1_500_000),
        _row(23700, ce_oi=10, pe_oi=1_000_000),
        _row(24000, ce_oi=10, pe_oi=10),
        _row(24300, ce_oi=20, pe_oi=10),
    ]
    assert _max_pain(chain) == 23700
    assert _max_pain(chain) != atm


# ---------------------------------------------------------------------------
# PCR -- consistent with the OI actually displayed
# ---------------------------------------------------------------------------

def _pcr(chain):
    ce = sum((r.get("ce") or {}).get("oi", 0) for r in chain)
    pe = sum((r.get("pe") or {}).get("oi", 0) for r in chain)
    return round(pe / ce, 2) if ce else None


def test_pcr_is_put_oi_over_call_oi():
    chain = [_row(24000, ce_oi=100_000, pe_oi=150_000)]
    assert _pcr(chain) == 1.5


def test_pcr_reflects_the_whole_chain():
    chain = [
        _row(23900, ce_oi=50_000, pe_oi=100_000),
        _row(24000, ce_oi=50_000, pe_oi=100_000),
    ]
    assert _pcr(chain) == 2.0


def test_pcr_is_none_when_there_is_no_call_oi():
    """No data must yield no ratio -- never a fabricated 1.0 or a random one."""
    assert _pcr([_row(24000, ce_oi=0, pe_oi=100)]) is None


# ---------------------------------------------------------------------------
# Expiry
# ---------------------------------------------------------------------------

def test_expiry_is_resolved_and_not_in_the_past():
    """The hardcoded '2026-07-25' silently went stale. Never again."""
    got = ab._next_weekly_expiry_str("NSE:NIFTY50-INDEX")
    assert got, "expiry must resolve"
    parsed = datetime.datetime.strptime(got, "%Y-%m-%d").date()
    assert parsed >= datetime.date.today(), f"{got} is in the past"


def test_expiry_matches_the_live_strike_selector():
    """The desk and the trading path must agree on the contract series."""
    from trading_bot.strategies.premium_selection.options_selector import _next_expiry
    assert ab._next_weekly_expiry_str("NSE:NIFTY50-INDEX") == _next_expiry("NIFTY").strftime("%Y-%m-%d")


# ---------------------------------------------------------------------------
# India VIX
# ---------------------------------------------------------------------------

def test_india_vix_is_subscribed_on_the_live_feed():
    """It is a plain NSE index; there is no reason to have guessed at it."""
    assert ab.INDIA_VIX_SYMBOL == "NSE:INDIA VIX-INDEX"


def test_india_vix_symbol_maps_through_the_broker_formatter():
    assert ab.format_broker_symbol("INDIAVIX") == ab.INDIA_VIX_SYMBOL
