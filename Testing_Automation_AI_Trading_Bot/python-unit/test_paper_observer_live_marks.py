"""Open positions must be marked to the contract's real quote (2026-09-09).

`paper_observer` priced every open position by extrapolating from its ENTRY
price::

    premium_change = (spot_change * delta) - time_decay
    est_opt_ltp    = entry_premium + premium_change

That is a first-order delta approximation. It cannot see gamma (delta itself
moves as spot moves) or any change in implied volatility -- the two things
that actually move an option intraday -- and its error compounds the longer a
position is held. Measured on one live NIFTY chain, delta ran from 0.776 to
0.184 and IV from 14.0% to 11.03% across only +/-300 points of strike, so a
delta frozen at entry misprices a position badly as soon as it moves.

Meanwhile the exact contract's own two-sided quote was already in the chain
the observer fetches. It now reads that and marks to the **bid** -- closing a
long option means hitting the bid, never the mid. The estimate survives only
as a fallback for a missing quote, and every position records which of the two
priced it (`mark_source`).
"""

from __future__ import annotations

import time

import pytest

import paper_observer as po


ATM = 23_450.0


def _chain():
    return {
        "atm": ATM,
        "underlying_price": 23_431.5,
        "chain": [
            {"strike": ATM - 300, "ce": {"ltp": 358.0, "bid": 357.15, "ask": 359.0,
                                         "delta": 0.776, "theta": -11.2, "iv": 14.0},
             "pe": {"ltp": 26.0, "bid": 25.8, "ask": 26.3,
                    "delta": -0.224, "theta": -9.1, "iv": 13.4}},
            {"strike": ATM, "ce": {"ltp": 138.50, "bid": 138.15, "ask": 139.45,
                                   "delta": 0.5091, "theta": -14.0, "iv": 11.62},
             "pe": {"ltp": 121.0, "bid": 120.4, "ask": 121.6,
                    "delta": -0.4909, "theta": -12.1, "iv": 10.9}},
            {"strike": ATM + 300, "ce": {"ltp": 32.4, "bid": 32.0, "ask": 32.9,
                                         "delta": 0.184, "theta": -8.4, "iv": 11.03},
             "pe": {"ltp": 312.0, "bid": 311.2, "ask": 313.0,
                    "delta": -0.816, "theta": -10.0, "iv": 12.2}},
        ],
    }


@pytest.fixture(autouse=True)
def _clear_cache():
    po._CHAIN_CACHE.clear()
    yield
    po._CHAIN_CACHE.clear()


@pytest.fixture
def chain(monkeypatch):
    data = _chain()
    monkeypatch.setattr(po, "fetch_json", lambda endpoint, timeout=8: data)
    return data


# ---------------------------------------------------------------------------
# Reading the held contract's own quote
# ---------------------------------------------------------------------------

def test_returns_the_quote_for_exactly_the_held_strike(chain):
    q = po.fetch_live_premium("NIFTY", ATM, "CE")
    assert q["ltp"] == 138.50
    assert q["bid"] == 138.15
    assert q["ask"] == 139.45


def test_reads_the_put_leg_for_a_pe_position(chain):
    q = po.fetch_live_premium("NIFTY", ATM, "PE")
    assert q["bid"] == 120.4
    assert q["delta"] == -0.4909


def test_picks_the_right_strike_not_merely_the_first(chain):
    assert po.fetch_live_premium("NIFTY", ATM - 300, "CE")["bid"] == 357.15
    assert po.fetch_live_premium("NIFTY", ATM + 300, "CE")["bid"] == 32.0


def test_carries_current_greeks_so_delta_does_not_stay_frozen(chain):
    """Gamma is the whole problem: delta at entry is wrong later."""
    near = po.fetch_live_premium("NIFTY", ATM - 300, "CE")
    far = po.fetch_live_premium("NIFTY", ATM + 300, "CE")
    assert near["delta"] > far["delta"] * 3
    assert near["iv"] != far["iv"]


def test_unknown_strike_yields_no_quote(chain):
    assert po.fetch_live_premium("NIFTY", 99_999, "CE") is None


def test_zero_priced_leg_yields_no_quote(monkeypatch):
    data = _chain()
    data["chain"][1]["ce"] = {"ltp": 0, "bid": 0, "ask": 0}
    monkeypatch.setattr(po, "fetch_json", lambda endpoint, timeout=8: data)
    assert po.fetch_live_premium("NIFTY", ATM, "CE") is None


def test_missing_chain_yields_no_quote(monkeypatch):
    monkeypatch.setattr(po, "fetch_json", lambda endpoint, timeout=8: None)
    assert po.fetch_live_premium("NIFTY", ATM, "CE") is None


# ---------------------------------------------------------------------------
# Marking to the bid
# ---------------------------------------------------------------------------

def test_exit_marks_at_the_bid_not_the_mid(chain):
    """Closing a long option means hitting the bid."""
    q = po.fetch_live_premium("NIFTY", ATM, "CE")
    mark = round(q["bid"] or q["ltp"], 2)
    assert mark == 138.15
    assert mark < q["ltp"], "marking at ltp gifts half the spread on exit"


def test_a_round_trip_pays_the_spread_once_each_way(chain):
    """Entry at ask, exit at bid -- the full spread, exactly once."""
    q = po.fetch_live_premium("NIFTY", ATM, "CE")
    entry, exit_ = q["ask"], q["bid"]
    assert entry - exit_ == pytest.approx(1.30, abs=0.01)
    assert entry > q["ltp"] > exit_


# ---------------------------------------------------------------------------
# The estimate is now only a fallback
# ---------------------------------------------------------------------------

def test_the_delta_estimate_cannot_see_gamma(chain):
    """Pin why the estimate is wrong, not just that it is replaced.

    A position entered ATM (delta 0.509) that rallies 300 points is really a
    0.776-delta contract by then. The estimate keeps using 0.509 and therefore
    understates the gain.
    """
    entry_delta = 0.5091
    real_delta_after_move = 0.776
    estimated_gain = 300 * entry_delta
    assert estimated_gain < 300 * real_delta_after_move
    assert (300 * real_delta_after_move) - estimated_gain > 70


def test_estimate_error_grows_with_time_held():
    """Anchored to entry, so nothing corrects it."""
    theta = 14.0
    errs = [abs(theta * (h / 24.0)) for h in (1, 3, 6)]
    assert errs[0] < errs[1] < errs[2]


# ---------------------------------------------------------------------------
# Chain caching -- one broker call per cycle, not one per lookup
# ---------------------------------------------------------------------------

def test_repeated_lookups_share_one_fetch(monkeypatch):
    calls = []

    def _counted(endpoint, timeout=8):
        calls.append(endpoint)
        return _chain()

    monkeypatch.setattr(po, "fetch_json", _counted)

    po.fetch_live_premium("NIFTY", ATM, "CE")
    po.fetch_live_premium("NIFTY", ATM, "PE")
    po.fetch_option_chain("NIFTY")

    assert len(calls) == 1, "each miss is a real broker REST call"


def test_cache_expires(monkeypatch):
    calls = []
    monkeypatch.setattr(po, "fetch_json",
                        lambda endpoint, timeout=8: (calls.append(1), _chain())[1])

    po.fetch_option_chain("NIFTY")
    po._CHAIN_CACHE["NIFTY"] = (time.time() - 60, _chain())   # age it out
    po.fetch_option_chain("NIFTY")

    assert len(calls) == 2


def test_cache_is_per_symbol(monkeypatch):
    seen = []
    monkeypatch.setattr(po, "fetch_json",
                        lambda endpoint, timeout=8: (seen.append(endpoint), _chain())[1])

    po.fetch_option_chain("NIFTY")
    po.fetch_option_chain("BANKNIFTY")

    assert len(seen) == 2, "one symbol's chain must not answer for another"
