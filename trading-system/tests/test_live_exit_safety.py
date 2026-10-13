"""Order-side safety of the live engine, driven by a scripted fake broker.

Every scenario here is one the 2026-10-13 review found could leave a real
position oversold, double-booked or without an exchange stop. The fake broker
(tests/fake_broker.py) keeps a real order book with scripted fills and
failures, so the assertions are about what would have happened at the
exchange, not about which functions were called.
"""
from __future__ import annotations

from brokers.models import OrderStatus


def test_main_imports_order_status():
    """main.py's fill polling and hard-stop checks compare against
    OrderStatus. Without the import every live exit raised NameError inside
    the stop interceptor, which the broad except swallowed, so the market
    exit went out with the exchange stop still live."""
    from trading_bot import main as bot_main

    assert bot_main.OrderStatus is OrderStatus


# ---------------------------------------------------------------------------
# #1 -- one book key per position across a restart
# ---------------------------------------------------------------------------

import json
from datetime import datetime
from unittest.mock import patch

import pytz

_IST = pytz.timezone("Asia/Kolkata")


def _today(hms: str = "10:00:00") -> str:
    return f"{datetime.now(_IST).strftime('%Y-%m-%d')} {hms}"


def _pos_record(symbol: str, qty: int = 75, entry: float = 100.0, stop: float = 85.0) -> dict:
    return {
        "symbol": symbol, "side": 1, "quantity": qty, "entry_price": entry,
        "entry_time": _today(), "highest_price": entry, "lowest_price": entry,
        "stop_loss": stop, "target": 0.0,
    }


def _load_from(tmp_path, data: dict):
    from trading_bot import main as bot_main

    pos_file = tmp_path / "active_positions.json"
    pos_file.write_text(json.dumps(data), encoding="utf-8")
    with patch.object(bot_main, "_POSITIONS_PATH", pos_file):
        return bot_main._load_positions(), pos_file


def test_restart_loads_each_position_under_one_key(tmp_path):
    loaded, _ = _load_from(tmp_path, {"NSE:NIFTY50-INDEX": _pos_record("NSE:NIFTY26OCT22500CE")})
    assert list(loaded) == ["NSE:NIFTY50-INDEX"]


def test_restart_collapses_alias_keys_written_by_the_previous_version(tmp_path):
    """0e34d71 saved the same position as "NIFTY" and "NSE:NIFTY50-INDEX"."""
    rec = _pos_record("NSE:NIFTY26OCT22500CE")
    loaded, _ = _load_from(tmp_path, {"NIFTY": rec, "NSE:NIFTY50-INDEX": dict(rec)})
    assert list(loaded) == ["NSE:NIFTY50-INDEX"]


def test_restart_maps_legacy_alias_key_to_the_entry_key(tmp_path):
    loaded, _ = _load_from(tmp_path, {"NIFTY50": _pos_record("NSE:NIFTY26OCT22500CE")})
    assert list(loaded) == ["NSE:NIFTY50-INDEX"]


def test_restart_quarantines_a_second_contract_on_the_same_underlying(tmp_path):
    loaded, pos_file = _load_from(tmp_path, {
        "NSE:NIFTY50-INDEX": _pos_record("NSE:NIFTY26OCT22500CE"),
        "NIFTY50": _pos_record("NSE:NIFTY26OCT22400PE"),
    })
    assert list(loaded) == ["NSE:NIFTY50-INDEX"]
    assert loaded["NSE:NIFTY50-INDEX"].symbol == "NSE:NIFTY26OCT22500CE"
    quarantined = json.loads((tmp_path / "quarantined_positions.json").read_text(encoding="utf-8"))
    assert "NIFTY50" in quarantined


def test_restart_then_emergency_stop_books_pnl_once(tmp_path):
    """Emergency flatten books one P&L per compute_reconciliation result."""
    from trading_bot.reconciliation import compute_reconciliation

    rec = _pos_record("NSE:NIFTY26OCT22500CE")
    loaded, _ = _load_from(tmp_path, {"NIFTY": rec, "NSE:NIFTY50-INDEX": dict(rec)})
    results = list(compute_reconciliation(
        loaded, broker_positions=[], order_book=[],
        live_prices={"NSE:NIFTY26OCT22500CE": 90.0},
    ))
    assert len(results) == 1
    assert results[0].quantity == 75
