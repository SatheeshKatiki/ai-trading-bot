"""Audit P4 (2026-09-12): measure IV / VIX at entry, and an optional VIX gate.

There was no IV or VIX input to any entry decision. A buyer paying up after a
gap open loses to falling IV even when direction is right -- 2026-09-11's
NIFTY CE lost about half of its -20 premium that way. But no IV history
exists to backtest a threshold, so:

* both paper books record entry IV and India VIX (from the same chain
  snapshot), and the variant scorecard groups results by VIX band;
* the portfolio guard gains ``max_entry_vix`` -- OFF unless set -- applied
  identically by every engine; with it on and VIX unknown, the trade is
  refused rather than guessed. The live engine fetches VIX only while the
  gate is on, so default behaviour is unchanged.
"""

from __future__ import annotations

import datetime
import inspect
import json

import pandas as pd
import pytz

import _bootstrap
import ema9_variant_observer as ev
import paper_observer as po
from shared.risk.portfolio_guard import entry_block_reason


def _block(**kw):
    args = dict(direction=1, open_directions=[], day_pnl=0.0, capital=100_000.0, trade_risk=1_000.0, settings={})
    args.update(kw)
    return entry_block_reason(**args)


# ---------------------------------------------------------------------------
# The gate
# ---------------------------------------------------------------------------

def test_gate_is_off_by_default():
    assert _block(vix=35.0) is None
    assert _block(vix=None) is None


def test_gate_blocks_above_its_threshold():
    assert "above the entry gate" in _block(vix=19.2, settings={"max_entry_vix": 18})
    assert _block(vix=17.9, settings={"max_entry_vix": 18}) is None


def test_gate_on_with_unknown_vix_refuses():
    assert "unknown" in _block(vix=None, settings={"max_entry_vix": 18})


# ---------------------------------------------------------------------------
# Recording
# ---------------------------------------------------------------------------

def test_main_book_records_iv_and_vix(monkeypatch):
    chain = {"pcr": 1.0, "indiaVix": {"value": 13.4}, "chain": [
        {"strike": 23_300.0, "ce": {"ltp": 120.0, "bid": 119.8, "ask": 120.2, "iv": 11.6, "delta": 0.51}}]}
    monkeypatch.setattr(po, "fetch_option_chain", lambda *a, **k: chain)
    opt = po.select_best_option("NIFTY", "BUY", 23_290.0)
    assert opt["vix"] == 13.4 and opt["iv"] == 11.6
    src = inspect.getsource(po.run_session)
    assert '"entry_iv": opt.get("iv")' in src and '"entry_vix": opt.get("vix")' in src
    assert "vix=opt.get(\"vix\")" in inspect.getsource(po.portfolio_block)


def test_variant_book_records_vix_and_reports_by_band(monkeypatch, tmp_path):
    monkeypatch.setattr(po, "alerter", None)
    monkeypatch.setattr(ev, "VARIANTS_DIR", tmp_path / "variants")
    monkeypatch.setattr(ev, "latest_closed_signal", lambda df, cfg: 1)
    chain = {"underlying_price": 23_290.0, "synthetic": False, "indiaVix": {"value": 16.2}, "chain": [
        {"strike": 23_300.0, "ce": {"ltp": 120.0, "bid": 119.8, "ask": 120.2, "delta": 0.51, "spread_pct": 0.3},
         "pe": {"ltp": 110.0, "bid": 109.8, "ask": 110.2, "delta": -0.49, "spread_pct": 0.3}}]}
    monkeypatch.setattr(po, "fetch_option_chain", lambda *a, **k: chain)
    sess = ev.load_session(tmp_path / "none.json", "5m_atm", "2026-09-14")
    df = pd.DataFrame({"open": [1.0], "high": [1.0], "low": [1.0], "close": [23_290.0], "volume": [0.0]},
                      index=pd.DatetimeIndex(["2026-09-14 10:15"]))
    now = pytz.timezone("Asia/Kolkata").localize(datetime.datetime(2026, 9, 14, 10, 21))
    ev.consider_entry(sess, "NIFTY", ev.build_config("5m_atm"), df, now)
    assert sess["open_positions"]["NIFTY"]["entry_vix"] == 16.2

    with open(ev.session_file("5m_atm", "2026-09-14"), "w", encoding="utf-8") as f:
        json.dump({"trades": [{"symbol": "NIFTY", "net_pnl": 50.0, "net_return_pct": 0.5, "entry_vix": 16.2},
                              {"symbol": "NIFTY", "net_pnl": -80.0, "net_return_pct": -0.8, "entry_vix": 11.0}]}, f)
    card = ev.build_scorecard("5m_atm")
    assert card["by_entry_vix"]["15-18"]["trades"] == 1 and card["by_entry_vix"]["<12"]["trades"] == 1
    assert ev.vix_band(None) == "unknown" and ev.vix_band(18.0) == "18+"


def test_live_engine_fetches_vix_only_when_the_gate_is_on():
    src = (_bootstrap.TRADING_SYSTEM_ROOT / "trading_bot" / "main.py").read_text(encoding="utf-8")
    assert 'vix=(await _india_vix(broker)) if settings.get("max_entry_vix") is not None else None' in src
    assert '_INDIA_VIX_SYMBOL = "NSE:INDIAVIX-INDEX"' in src
