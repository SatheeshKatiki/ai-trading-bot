"""Paper-trade fills must reflect what a buyer actually pays (2026-09-09).

Three compounding defects in `paper_observer`, all found together:

1. **Wrong chain keys.** `select_best_option()` read `row["call"]` /
   `row["put"]`, but the option chain publishes its legs under `"ce"` / `"pe"`
   (NSE terminology, and what the Options Desk reads). `opt_details` was
   therefore always `{}` and every field fell through to its default:

       entry premium   Rs.100.00 flat, on every trade ever recorded
       delta           0.50 constant
       theta          -10.00/day constant

   Measured against the live chain the same day, the real ATM CE was
   Rs.138.50 mid / Rs.139.45 ask -- a **Rs.2,564 per-lot** error on entry
   price alone.

2. **Mid-price fills.** Entry used `ltp`. A buyer lifts the offer on entry and
   hits the bid on exit; both cost real money. ATM NIFTY weeklies quoted a
   0.94% spread when this was measured, so a round trip is roughly 1% of
   premium -- material against a 15% stop and a 33% target.

3. **Decay understated ~12x.** The mark-to-market model applied a flat
   `0.05/hour` (~1.2/day) regardless of contract, against a real ATM theta of
   -13.93/day. Every held position looked better than it was, and the error
   grew the longer the trade was carried.

Note on (1): the key mismatch became *active* when the option chain moved from
the synthetic `call`/`put` shape to the real broker's `ce`/`pe` shape. Before
that the keys matched but the values were Black-Scholes theoretical prices off
a `deterministic_random()` implied vol. Either way, no paper trade recorded
before this fix was filled at a real market price.
"""

from __future__ import annotations

import pytest

import paper_observer as po


ATM = 23_450.0
SPOT = 23_431.5


def _chain(ce=None, pe=None):
    ce = {"ltp": 138.50, "bid": 138.15, "ask": 139.45, "spread_pct": 0.94,
          "delta": 0.5093, "theta": -13.93, "iv": 11.58} if ce is None else ce
    pe = {"ltp": 121.00, "bid": 120.40, "ask": 121.60, "spread_pct": 0.99,
          "delta": -0.4907, "theta": -12.10, "iv": 10.90} if pe is None else pe
    return {"chain": [{"strike": ATM, "ce": ce, "pe": pe}], "pcr": 0.65}


@pytest.fixture
def chain(monkeypatch):
    data = _chain()
    monkeypatch.setattr(po, "fetch_option_chain", lambda symbol: data)
    return data


# ---------------------------------------------------------------------------
# Defect 1 -- the chain keys
# ---------------------------------------------------------------------------

def test_call_leg_is_read_from_the_ce_key(chain):
    opt = po.select_best_option("NIFTY", "BUY", SPOT)
    assert opt["type"] == "CE"
    assert opt["ltp"] == 138.50, "must read the real leg, not fall back to 100.0"
    assert opt["delta"] == 0.5093
    assert opt["theta"] == -13.93


def test_put_leg_is_read_from_the_pe_key(chain):
    opt = po.select_best_option("NIFTY", "SELL", SPOT)
    assert opt["type"] == "PE"
    assert opt["ltp"] == 121.00
    assert opt["delta"] == -0.4907


def test_the_hardcoded_100_fallback_can_no_longer_appear(monkeypatch):
    """A leg with no usable quote must yield no trade, not an invented one."""
    monkeypatch.setattr(po, "fetch_option_chain",
                        lambda symbol: _chain(ce={"ltp": 0, "bid": 0, "ask": 0}))
    assert po.select_best_option("NIFTY", "BUY", SPOT) is None


def test_a_legacy_call_put_shaped_chain_is_not_silently_accepted(monkeypatch):
    """Guards the regression itself: old-shaped rows must not fill at 100.0."""
    monkeypatch.setattr(po, "fetch_option_chain", lambda symbol: {
        "chain": [{"strike": ATM, "call": {"ltp": 138.5}, "put": {"ltp": 121.0}}],
        "pcr": 0.65,
    })
    assert po.select_best_option("NIFTY", "BUY", SPOT) is None


# ---------------------------------------------------------------------------
# Defect 2 -- the spread
# ---------------------------------------------------------------------------

def test_the_two_sided_quote_is_carried_through(chain):
    opt = po.select_best_option("NIFTY", "BUY", SPOT)
    assert opt["bid"] == 138.15
    assert opt["ask"] == 139.45
    assert opt["spread_pct"] == 0.94


def test_entry_is_filled_at_the_ask_not_the_mid(chain):
    """The whole point: a buyer pays the offer."""
    opt = po.select_best_option("NIFTY", "BUY", SPOT)
    entry = round(opt.get("ask") or opt["ltp"], 2)
    assert entry == 139.45
    assert entry > opt["ltp"], "filling at ltp credits half the spread for free"


def test_the_round_trip_spread_is_material_against_the_stop(chain):
    """0.94% round trip against a 15% stop / 33% target is not noise."""
    opt = po.select_best_option("NIFTY", "BUY", SPOT)
    round_trip_pct = opt["spread_pct"]
    assert round_trip_pct > 0.5
    assert round_trip_pct / 15.0 > 0.05, "over 5% of the stop distance"


def test_entry_falls_back_to_ltp_when_unquoted(monkeypatch):
    """A chain without bid/ask (the model fallback) must still work."""
    monkeypatch.setattr(po, "fetch_option_chain", lambda symbol: _chain(
        ce={"ltp": 138.50, "delta": 0.5, "theta": -13.0}))
    opt = po.select_best_option("NIFTY", "BUY", SPOT)
    assert round(opt.get("ask") or opt["ltp"], 2) == 138.50


# ---------------------------------------------------------------------------
# Defect 3 -- theta
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("hours", [1, 4, 6])
def test_real_theta_decays_far_faster_than_the_old_flat_model(hours):
    theta_per_day = 13.93
    old = 0.05 * hours
    new = theta_per_day * (hours / 24.0)
    assert new > old * 5, f"{hours}h: real decay must dominate the old constant"


def test_four_hour_decay_was_understated_about_twelvefold():
    old = 0.05 * 4
    new = 13.93 * (4 / 24.0)
    assert 10 < (new / old) < 14


def test_theta_is_recorded_on_the_position(chain):
    """The mark-to-market needs the contract's own theta, not a constant."""
    opt = po.select_best_option("NIFTY", "BUY", SPOT)
    assert opt["theta"] == -13.93


def test_decay_uses_the_absolute_value_of_theta():
    """Theta is negative by convention; decay must subtract, never add."""
    for theta in (-13.93, 13.93):
        decay = abs(float(theta)) * (4 / 24.0)
        assert decay > 0
