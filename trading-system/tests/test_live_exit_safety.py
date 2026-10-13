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


# ---------------------------------------------------------------------------
# #4 -- each slice settled on its own deadline, fill re-read after cancel
# ---------------------------------------------------------------------------

import asyncio

from brokers.models import OrderRequest, OrderSide, OrderType
from tests.fake_broker import FakeBroker
from trading_bot.iceberg_manager import IcebergManager
from trading_bot.order_safety import confirm_fills

OPT = "NSE:NIFTY26OCT22500CE"
FAST = dict(timeout=0.3, poll_interval=0.02)


def _sell(qty: int, price: float = 95.0) -> OrderRequest:
    return OrderRequest(symbol=OPT, quantity=qty, side=OrderSide.SELL,
                        order_type=OrderType.LIMIT, price=price)


async def _sliced_sell(broker: FakeBroker, qty: int, slice_qty: int):
    mgr = IcebergManager(max_slice_qty=slice_qty, min_delay_sec=0.0, max_delay_sec=0.01)
    with patch("trading_bot.iceberg_manager.ORDER_LIMITER.allow", return_value=True):
        return await mgr.execute_iceberg(broker, _sell(qty), halt_check=None)


def test_a_slow_second_slice_is_still_counted():
    """The shared 3s deadline let slice 1 use the whole budget; slice 2 then
    read as unfilled and its real fill was lost from the book."""
    async def run():
        broker = FakeBroker(holdings={OPT: 150})
        broker.script_next(fill_after=0.25)   # slice 1 uses most of a 0.3s window
        broker.script_next(fill_after=0.45)   # slice 2 fills after a shared deadline would have expired
        responses = await _sliced_sell(broker, 150, 75)
        return broker, await confirm_fills(broker, responses, **FAST)

    broker, fills = asyncio.run(run())
    assert fills.filled_qty == 150 == broker.sold(OPT)
    assert fills.unresolved_order_ids == []
    assert broker.cancel_calls == []


def test_a_fill_during_the_cancel_is_counted():
    async def run():
        broker = FakeBroker(holdings={OPT: 75})
        broker.script_next(fill_after=None, fill_on_cancel=75)
        responses = await _sliced_sell(broker, 75, 75)
        return broker, await confirm_fills(broker, responses, **FAST)

    broker, fills = asyncio.run(run())
    assert broker.sold(OPT) == 75
    assert fills.filled_qty == 75
    assert broker.net[OPT] == 0


def test_a_partial_fill_then_cancel_counts_only_the_fill():
    async def run():
        broker = FakeBroker(holdings={OPT: 150})
        broker.script_next(fill_after=0.0, fill_qty=75)
        responses = await _sliced_sell(broker, 150, 150)
        return broker, await confirm_fills(broker, responses, **FAST)

    broker, fills = asyncio.run(run())
    assert fills.filled_qty == 75 == broker.sold(OPT)
    assert fills.unresolved_order_ids == []
    assert broker.live_orders() == []


def test_a_refused_cancel_leaves_the_order_unresolved():
    async def run():
        broker = FakeBroker(holdings={OPT: 75})
        broker.script_next(fill_after=None, cancel_fails=True)
        broker.script_next(fill_after=None, cancel_fails="dict")
        responses = await _sliced_sell(broker, 150, 75)
        return broker, await confirm_fills(broker, responses, **FAST)

    broker, fills = asyncio.run(run())
    assert fills.filled_qty == 0
    assert fills.unresolved_order_ids == ["F1", "F2"]


def test_an_unfilled_slice_is_cancelled_and_resolved():
    async def run():
        broker = FakeBroker(holdings={OPT: 75})
        broker.script_next(fill_after=None)
        responses = await _sliced_sell(broker, 75, 75)
        return broker, await confirm_fills(broker, responses, **FAST)

    broker, fills = asyncio.run(run())
    assert fills.filled_qty == 0
    assert fills.unresolved_order_ids == []
    assert broker.live_orders() == []
