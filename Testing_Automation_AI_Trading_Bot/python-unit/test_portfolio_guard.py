"""One portfolio rule for every engine (2026-09-12, audit P2).

Measured on 49 sessions with all three indices (5-min / ATM, the owner's
ladder, one lot, Rs 1,00,000): worst day -10,282 with no cap, -6,861 with
one position per direction, -4,736 adding the 3% daily loss stop.

* NIFTY / BANKNIFTY / SENSEX move together (5-min correlation 0.75-0.91;
  61% of signals have a same-direction twin within 15 min) -- at most one
  open position per direction.
* The day's loss limit stops new entries (the paper books had none).
* No single trade may risk more than the day's whole loss limit (the live
  minimum-lot override let one BANKNIFTY lot through at ~2.4x the policy).
"""

from __future__ import annotations

import datetime
import types

import pandas as pd
import pytest
import pytz

import _bootstrap
import ema9_variant_observer as ev
import paper_observer as po
from shared.risk.portfolio_guard import (
    daily_loss_limit,
    entry_block_reason,
    option_direction,
)

CAPITAL = 100_000.0


def _block(**kw):
    args = dict(direction=1, open_directions=[], day_pnl=0.0, capital=CAPITAL, trade_risk=1_000.0, settings={})
    args.update(kw)
    return entry_block_reason(**args)


# ---------------------------------------------------------------------------
# The rule
# ---------------------------------------------------------------------------

def test_a_clean_entry_passes():
    assert _block() is None


def test_one_position_per_direction():
    assert "already open" in _block(open_directions=[1])
    assert _block(open_directions=[-1]) is None                       # a PE does not block a CE
    assert _block(open_directions=[1], settings={"max_same_direction_positions": 2}) is None


def test_daily_loss_stop():
    assert daily_loss_limit(CAPITAL) == 3_000.0
    assert "daily loss limit" in _block(day_pnl=-3_000.0)
    assert _block(day_pnl=-2_999.0) is None
    assert "daily loss limit" in _block(day_pnl=-1_500.0, settings={"max_daily_loss_pct": 1.5})


def test_no_trade_may_risk_the_whole_day():
    assert "exceeds the day's whole loss limit" in _block(trade_risk=3_600.0)   # BANKNIFTY ATM ~Rs 800
    assert _block(trade_risk=2_400.0) is None


@pytest.mark.parametrize("symbol,direction", [
    ("NSE:NIFTY2691523300CE", 1), ("NSE:BANKNIFTY26SEP56200PE", -1), ("BANKNIFTY 56200.0 CE", 1),
    ("NSE:RELIANCE-EQ", 0), ("NSE:NIFTY50-INDEX", 0), ("", 0),
])
def test_direction_reads_the_suffix(symbol, direction):
    assert option_direction(symbol) == direction


# ---------------------------------------------------------------------------
# Paper books
# ---------------------------------------------------------------------------

def test_main_book_applies_the_rule():
    open_ce = {"NIFTY": {"direction": "BUY", "entry_premium": 100.0, "current_ltp": 95.0, "quantity": 65}}
    opt = {"ltp": 800.0, "ask": 801.0}
    assert "already open" in po.portfolio_block("SENSEX", "BUY", {"ltp": 570.0, "ask": 571.0},
                                                {"trades": []}, open_ce, {})
    assert po.portfolio_block("SENSEX", "SELL", {"ltp": 570.0, "ask": 571.0}, {"trades": []}, open_ce, {}) is None
    assert "exceeds" in po.portfolio_block("BANKNIFTY", "SELL", opt, {"trades": []}, {}, {})
    lost = {"trades": [{"net_pnl": -3_100.0}]}
    assert "daily loss limit" in po.portfolio_block("NIFTY", "BUY", {"ltp": 120.0, "ask": 120.5}, lost, {}, {})


IST = pytz.timezone("Asia/Kolkata")


def test_variant_book_skips_a_same_direction_twin(monkeypatch, tmp_path):
    monkeypatch.setattr(po, "alerter", None)
    monkeypatch.setattr(ev, "VARIANTS_DIR", tmp_path / "variants")
    monkeypatch.setattr(ev, "latest_closed_signal", lambda df, cfg: 1)
    chain = {"underlying_price": 74_800.0, "synthetic": False, "chain": [
        {"strike": 74_800.0, "ce": {"ltp": 570.0, "bid": 569.0, "ask": 571.0, "delta": 0.52, "spread_pct": 0.3},
         "pe": {"ltp": 360.0, "bid": 359.0, "ask": 361.0, "delta": -0.48, "spread_pct": 0.3}}]}
    monkeypatch.setattr(po, "fetch_option_chain", lambda *a, **k: chain)
    sess = ev.load_session(tmp_path / "none.json", "5m_atm", "2026-09-14")
    sess["open_positions"]["NIFTY"] = {"side": 1, "entry_premium": 120.0, "current_ltp": 121.0, "quantity": 65}
    df = pd.DataFrame({"open": [1.0], "high": [1.0], "low": [1.0], "close": [74_800.0], "volume": [0.0]},
                      index=pd.DatetimeIndex(["2026-09-14 10:15"]))
    now = IST.localize(datetime.datetime(2026, 9, 14, 10, 21))
    ev.consider_entry(sess, "SENSEX", ev.build_config("5m_atm"), df, now)
    assert "SENSEX" not in sess["open_positions"]
    assert "already open" in sess["signals"][-1]["action"]


def test_variant_book_reads_the_dashboard_limits():
    src = __import__("inspect").getsource(ev.run_books)
    assert "RISK_SETTINGS.update(settings)" in src


# ---------------------------------------------------------------------------
# Live engine
# ---------------------------------------------------------------------------

def test_live_engine_applies_the_same_rule_before_the_risk_gate():
    src = (_bootstrap.TRADING_SYSTEM_ROOT / "trading_bot" / "main.py").read_text(encoding="utf-8")
    guard = src.index("_guard_block = entry_block_reason(")
    gate = src.index("allowed, reject_reason = risk_manager.can_trade(")
    assert guard < gate
    assert "open_directions=[option_direction(p.symbol) for p in active_positions.values()]" in src
