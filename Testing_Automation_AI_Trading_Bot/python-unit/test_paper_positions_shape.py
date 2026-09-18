"""/api/positions must return the shape the dashboard reads (2026-09-18).

config/active_positions.json has TWO writers with different field names:

* paper_observer.py -- symbol/underlying/entry_price/current_price/ltp
* trading_bot/main.py -- entry_price, and NO ltp at all

Neither carries `average_price`, `unrealized_pnl` or `realized_pnl`, which is
what the dashboard's position table renders. In paper mode the endpoint
returned those rows verbatim, so `pos.average_price.toFixed(2)` threw
"Cannot read properties of undefined" and took the whole dashboard down while
a real BANKNIFTY position was open.

A price that is not known stays None -- never 0.0. The UI renders "—" for it.
A zero would be an invented price, and a P&L derived from one is worse than a
blank.
"""

from __future__ import annotations

import _bootstrap  # noqa: F401  (side-effect: puts trading-system/ on sys.path)

from api_bridge import _normalize_paper_positions

OBSERVER_ROW = {
    "symbol": "BANKNIFTY 56000 CE",
    "underlying": "BANKNIFTY",
    "side": 1,
    "quantity": 30,
    "entry_price": 412.5,
    "current_price": 455.0,
    "ltp": 455.0,
    "entry_time": "09:45:43",
    "highest_price": 470.0,
    "lowest_price": 400.0,
    "stop_loss": 350.6,
    "target": 548.6,
    "strategy": "EMA 9 / RSI Momentum",
}

MAIN_ROW = {
    "symbol": "NSE:NIFTY2681824400PE",
    "side": -1,
    "quantity": 65,
    "entry_price": 90.9,
    "entry_time": "2026-09-18T09:45:00",
    "highest_price": 90.9,
    "lowest_price": 90.9,
    "stop_loss": 76.8,
    "target": 0.0,
    "is_partially_booked": False,
    "scales_done": 0,
    "sl_order_id": None,
}


def test_the_observer_row_becomes_the_dashboard_shape():
    [pos] = _normalize_paper_positions({"BANKNIFTY": OBSERVER_ROW})

    assert pos["symbol"] == "BANKNIFTY 56000 CE"
    assert pos["average_price"] == 412.5
    assert pos["ltp"] == 455.0
    assert pos["quantity"] == 30
    assert pos["side"] == "BUY"
    # 30 * (455.0 - 412.5)
    assert pos["unrealized_pnl"] == 1275.0
    assert pos["realized_pnl"] == 0.0


def test_every_field_the_table_renders_is_present():
    """The crash was an absent key, so assert on presence, not just values."""
    [pos] = _normalize_paper_positions({"BANKNIFTY": OBSERVER_ROW})
    for field in ("symbol", "average_price", "ltp", "unrealized_pnl"):
        assert field in pos


def test_a_row_without_a_price_leaves_it_unknown():
    """main.py's rows carry no ltp. Unknown must stay None, never 0.0."""
    [pos] = _normalize_paper_positions({"NSE:NIFTY50-INDEX": MAIN_ROW})

    assert pos["average_price"] == 90.9
    assert pos["ltp"] is None
    assert pos["unrealized_pnl"] is None, "a P&L from an invented price is worse than a blank"
    assert pos["side"] == "SELL"


def test_current_price_is_used_when_ltp_is_missing():
    row = dict(OBSERVER_ROW)
    row.pop("ltp")
    [pos] = _normalize_paper_positions({"BANKNIFTY": row})
    assert pos["ltp"] == 455.0


def test_a_short_position_pnl_is_signed_by_direction():
    row = dict(MAIN_ROW, ltp=80.9)          # short from 90.9, now 80.9 -> profit
    [pos] = _normalize_paper_positions({"NSE:NIFTY50-INDEX": row})
    assert pos["unrealized_pnl"] == 650.0


def test_the_dict_key_is_the_fallback_symbol():
    [pos] = _normalize_paper_positions({"BANKNIFTY": {"entry_price": 1.0, "quantity": 1}})
    assert pos["symbol"] == "BANKNIFTY"


def test_junk_rows_are_skipped_not_raised():
    rows = _normalize_paper_positions({"A": None, "B": "nonsense", "C": OBSERVER_ROW})
    assert len(rows) == 1


def test_no_positions_is_an_empty_list():
    assert _normalize_paper_positions({}) == []
    assert _normalize_paper_positions(None) == []
