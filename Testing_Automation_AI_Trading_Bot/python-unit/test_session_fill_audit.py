"""Tests for the paper-session fill audit (2026-09-09).

`scripts/audit_session_fills.py` answers one question about a recorded trade:
**was it filled at a price the market actually quoted?**

Run against the five sessions on disk when it was written, the answer was
*no, not once* -- 14 trades, 0 real. Day_5 (2026-09-09) even caught the
transition mid-session: the 09:15 trades carried model premiums from the
Black-Scholes chain, and the 11:35 onwards trades carried the literal
`100.0` fallback, because the chain had moved to `ce`/`pe` keys while
`select_best_option()` still read `call`/`put`.

The fingerprints this relies on:

* ``entry_premium == 100.0`` with no quote -> ``opt_details.get("ltp", 100.0)``
* ``abs(opt_delta) == 0.50`` exactly -> the constant fallback. A genuine ATM
  delta is 0.5091, 0.4907, 0.5093...; exactly 0.5000 essentially never occurs
  in a real quote.
* no ``entry_bid``/``entry_ask`` -> priced before quotes were captured
* ``mark_source == "model"`` -> exit extrapolated, not read
"""

from __future__ import annotations

import json

import pytest

from scripts.audit_session_fills import (
    FABRICATED,
    MODEL,
    REAL,
    audit_session,
    classify_trade,
)


def _real_trade(**over):
    t = {
        "contract": "NIFTY 23450 CE",
        "entry_premium": 139.45,
        "entry_ltp": 138.50,
        "entry_bid": 138.15,
        "entry_ask": 139.45,
        "entry_spread_pct": 0.94,
        "opt_delta": 0.5091,
        "opt_theta": -13.93,
        "mark_source": "broker",
        "net_pnl": 120.0,
    }
    t.update(over)
    return t


# ---------------------------------------------------------------------------
# Fabricated
# ---------------------------------------------------------------------------

def test_the_hardcoded_100_premium_is_caught():
    verdict, reasons = classify_trade(
        {"entry_premium": 100.0, "opt_delta": 0.5091}
    )
    assert verdict == FABRICATED
    assert any("100.0" in r for r in reasons)


def test_the_constant_half_delta_is_caught():
    """Even when the premium looks plausible, delta gives it away."""
    verdict, reasons = classify_trade(
        {"entry_premium": 176.44, "opt_delta": -0.5, "entry_ask": 176.44}
    )
    assert verdict == FABRICATED
    assert any("0.5" in r for r in reasons)


def test_a_real_atm_delta_is_not_mistaken_for_the_fallback():
    """0.5091 is a real quote; only exactly 0.5000 is the fallback."""
    verdict, _ = classify_trade(_real_trade(opt_delta=0.5091))
    assert verdict == REAL
    verdict, _ = classify_trade(_real_trade(opt_delta=-0.4907))
    assert verdict == REAL


# ---------------------------------------------------------------------------
# Model
# ---------------------------------------------------------------------------

def test_a_trade_with_no_quote_recorded_is_model():
    verdict, reasons = classify_trade(
        {"entry_premium": 531.82, "opt_delta": 0.7761, "net_pnl": -1227.8}
    )
    assert verdict == MODEL
    assert any("bid/ask" in r for r in reasons)


def test_filling_below_the_ask_is_flagged():
    """A buyer does not get the mid."""
    verdict, reasons = classify_trade(_real_trade(entry_premium=138.50))
    assert verdict == MODEL
    assert any("below the ask" in r for r in reasons)


def test_an_extrapolated_exit_is_flagged():
    verdict, reasons = classify_trade(_real_trade(mark_source="model"))
    assert verdict == MODEL
    assert any("extrapolated" in r for r in reasons)


def test_missing_mark_source_is_flagged():
    t = _real_trade()
    del t["mark_source"]
    verdict, reasons = classify_trade(t)
    assert verdict == MODEL
    assert any("provenance unknown" in r for r in reasons)


# ---------------------------------------------------------------------------
# Real
# ---------------------------------------------------------------------------

def test_a_fully_sourced_trade_passes():
    verdict, _ = classify_trade(_real_trade())
    assert verdict == REAL


def test_entry_exactly_at_the_ask_is_accepted():
    verdict, _ = classify_trade(_real_trade(entry_premium=139.45, entry_ask=139.45))
    assert verdict == REAL


# ---------------------------------------------------------------------------
# Session-level verdicts
# ---------------------------------------------------------------------------

def _write(tmp_path, trades, name="session_Test.json"):
    p = tmp_path / name
    p.write_text(json.dumps({"date": "Test", "trades": trades}), encoding="utf-8")
    return p


def test_one_fabricated_trade_makes_the_session_unusable(tmp_path):
    path = _write(tmp_path, [_real_trade(), {"entry_premium": 100.0}])
    assert audit_session(path)["verdict"] == "UNUSABLE"


def test_a_model_trade_makes_the_session_not_evidence(tmp_path):
    path = _write(tmp_path, [_real_trade(), _real_trade(mark_source="model")])
    assert audit_session(path)["verdict"] == "NOT EVIDENCE"


def test_an_all_real_session_is_usable(tmp_path):
    path = _write(tmp_path, [_real_trade(), _real_trade()])
    report = audit_session(path)
    assert report["verdict"] == "USABLE"
    assert report["counts"][REAL] == 2


def test_an_empty_session_is_not_claimed_as_evidence(tmp_path):
    assert audit_session(_write(tmp_path, []))["verdict"] == "NO TRADES"


def test_a_corrupt_file_reports_an_error_rather_than_crashing(tmp_path):
    p = tmp_path / "session_bad.json"
    p.write_text("{not json", encoding="utf-8")
    assert "error" in audit_session(p)


def test_net_pnl_is_totalled(tmp_path):
    path = _write(tmp_path, [_real_trade(net_pnl=100.0), _real_trade(net_pnl=-40.5)])
    assert audit_session(path)["net_pnl"] == pytest.approx(59.5)
