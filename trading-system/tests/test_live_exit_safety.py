"""Order-side safety of the live engine, driven by a scripted fake broker.

Every scenario here is one the 2026-10-13 review found could leave a real
position oversold, double-booked or without an exchange stop. The fake broker
(tests/fake_broker.py) keeps a real order book with scripted fills and
failures, so the assertions are about what would have happened at the
exchange, not about which functions were called.
"""
from __future__ import annotations


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


# ---------------------------------------------------------------------------
# #5 -- the exchange stop is resolved before any local sell
# ---------------------------------------------------------------------------

from shared.exits import Position
from trading_bot.order_safety import execute_exit_orders


def _position(qty: int = 75, stop: float = 85.0) -> Position:
    return Position(symbol=OPT, side=1, entry_price=100.0, quantity=qty, entry_time=_today(),
                    highest_price=100.0, lowest_price=100.0, stop_loss=stop, target=0.0)


def _place_stop(broker: FakeBroker, pos: Position, **script) -> str:
    broker.script_next(**script)
    resp = broker.place_order(OrderRequest(symbol=OPT, quantity=pos.quantity, side=OrderSide.SELL,
                                           order_type=OrderType.SL, trigger_price=pos.stop_loss,
                                           price=round(pos.stop_loss * 0.9, 2)))
    pos.sl_order_id = resp.order_id
    return resp.order_id


async def _exit(broker: FakeBroker, pos: Position, qty: int | None = None):
    mgr = IcebergManager(max_slice_qty=500, min_delay_sec=0.0, max_delay_sec=0.0)
    with patch("trading_bot.iceberg_manager.ORDER_LIMITER.allow", return_value=True):
        return await execute_exit_orders(broker, mgr, pos, _sell(qty or pos.quantity), 84.0, **FAST)


def test_a_partly_filled_stop_reduces_the_local_sell():
    """The stop-limit sold 25 of 75 in a gap; selling the full 75 locally
    would have left the account short 25."""
    broker = FakeBroker(holdings={OPT: 75})
    pos = _position()
    stop_id = _place_stop(broker, pos)
    broker.trigger(stop_id, qty=25, price=80.0)

    fill = asyncio.run(_exit(broker, pos))
    assert broker.net[OPT] == 0
    assert (fill.stop_filled, fill.local_filled) == (25, 50)
    assert broker.place_calls[-1].quantity == 50
    assert fill.avg_price == (25 * 80.0 + 50 * 95.0) / 75
    assert pos.sl_order_id is None and broker.live_stops() == []


def test_a_fully_filled_stop_sends_no_local_sell():
    broker = FakeBroker(holdings={OPT: 75})
    pos = _position()
    broker.trigger(_place_stop(broker, pos), price=84.0)
    placed = len(broker.place_calls)

    fill = asyncio.run(_exit(broker, pos))
    assert len(broker.place_calls) == placed
    assert fill.filled_qty == 75 and fill.local_filled == 0
    assert broker.net[OPT] == 0


def test_a_stop_that_will_not_cancel_blocks_the_local_sell():
    broker = FakeBroker(holdings={OPT: 75})
    pos = _position()
    stop_id = _place_stop(broker, pos, cancel_fails=True)
    placed = len(broker.place_calls)

    fill = asyncio.run(_exit(broker, pos))
    assert fill.stop_cleared is False
    assert len(broker.place_calls) == placed
    assert pos.sl_order_id == stop_id
    assert [o.order_id for o in broker.live_stops()] == [stop_id]
    # The stop still protects the lots and is the only order that can sell them.
    broker.trigger(stop_id)
    assert broker.net[OPT] == 0


def test_a_stop_refused_by_error_reply_blocks_the_local_sell():
    broker = FakeBroker(holdings={OPT: 75})
    pos = _position()
    _place_stop(broker, pos, cancel_fails="dict")
    fill = asyncio.run(_exit(broker, pos))
    assert fill.stop_cleared is False and broker.sold(OPT) == 0


def test_a_stop_that_fills_during_the_cancel_is_counted():
    broker = FakeBroker(holdings={OPT: 75})
    pos = _position()
    _place_stop(broker, pos, fill_on_cancel=75, fill_price=83.0)

    fill = asyncio.run(_exit(broker, pos))
    assert fill.stop_filled == 75 and fill.local_filled == 0
    assert broker.net[OPT] == 0


def test_a_partial_local_exit_never_exceeds_holdings():
    broker = FakeBroker(holdings={OPT: 150})
    pos = _position(qty=150)
    stop_id = _place_stop(broker, pos)
    broker.trigger(stop_id, qty=75, price=80.0)

    fill = asyncio.run(_exit(broker, pos, qty=150))
    assert fill.filled_qty == 150
    assert broker.net[OPT] == 0


# ---------------------------------------------------------------------------
# Exchange stop side: a bought option is always closed by a SELL
# ---------------------------------------------------------------------------

from trading_bot.order_safety import place_hard_stop, stop_request

PE = "NSE:NIFTY26OCT22500PE"


def test_the_stop_for_a_bought_pe_sells():
    """Position.side is the directional bet (PE = -1), not long/short the
    contract. The old `SELL if side == 1 else BUY` placed a BUY stop for
    every PE position: a falling premium would have bought more lots."""
    pe = Position(symbol=PE, side=-1, entry_price=100.0, quantity=75, entry_time=_today(),
                  highest_price=100.0, lowest_price=100.0, stop_loss=85.0, target=0.0)
    req = stop_request(pe, 75)
    assert req.side == OrderSide.SELL
    assert req.order_type == OrderType.SL
    assert (req.trigger_price, req.price) == (85.0, 76.5)


def test_the_stop_for_a_bought_ce_sells():
    assert stop_request(_position(), 75).side == OrderSide.SELL


def test_the_stop_for_a_short_underlying_buys():
    short = Position(symbol="NSE:RELIANCE-EQ", side=-1, entry_price=100.0, quantity=10,
                     entry_time=_today(), highest_price=100.0, lowest_price=100.0,
                     stop_loss=105.0, target=0.0)
    req = stop_request(short, 10)
    assert (req.side, req.order_type, req.price) == (OrderSide.BUY, OrderType.SL_M, 0.0)


def test_place_hard_stop_reports_failure_as_none():
    broker = FakeBroker()
    broker.script_next(place_fails=True)
    assert asyncio.run(place_hard_stop(broker, _position(), 75)) is None
    assert asyncio.run(place_hard_stop(broker, _position(), 75)) == "F1"


# ---------------------------------------------------------------------------
# #6 -- lots left open by an exit get an exchange stop back
# ---------------------------------------------------------------------------

from trading_bot.order_safety import protect_remaining


def _exit_then_protect(broker: FakeBroker, pos: Position):
    async def run():
        fill = await _exit(broker, pos)
        pos.quantity -= fill.filled_qty
        await protect_remaining(broker, pos)
        return fill
    return asyncio.run(run())


def test_a_partial_exit_restores_a_stop_for_the_remainder():
    broker = FakeBroker(holdings={OPT: 150})
    pos = _position(qty=150)
    _place_stop(broker, pos)
    broker.script_next(fill_after=0.0, fill_qty=75)     # local sell fills half

    fill = _exit_then_protect(broker, pos)
    assert fill.local_filled == 75 and pos.quantity == 75
    stops = broker.live_stops(OPT)
    assert len(stops) == 1 and stops[0].request.quantity == 75
    assert pos.sl_order_id == stops[0].order_id
    broker.trigger(pos.sl_order_id)
    assert broker.net[OPT] == 0


def test_an_unfilled_exit_restores_the_stop():
    broker = FakeBroker(holdings={OPT: 75})
    pos = _position()
    _place_stop(broker, pos)
    broker.script_next(fill_after=None)                 # local sell never fills

    fill = _exit_then_protect(broker, pos)
    assert fill.filled_qty == 0
    stops = broker.live_stops(OPT)
    assert len(stops) == 1 and stops[0].request.quantity == 75


def test_protect_remaining_keeps_an_existing_stop():
    broker = FakeBroker(holdings={OPT: 75})
    pos = _position()
    stop_id = _place_stop(broker, pos)
    assert asyncio.run(protect_remaining(broker, pos)) == stop_id
    assert len(broker.live_stops()) == 1


# ---------------------------------------------------------------------------
# #2 -- the exit lock is released by the exit finishing, not by a timer
# ---------------------------------------------------------------------------

from trading_bot.order_safety import exit_in_flight, guard_for, start_exit


async def _tick_loop(broker: FakeBroker, pos: Position, ticks: int, stuck_after: float, on_stuck=None):
    """What on_tick does with the exit gate: skip while an exit is in flight,
    otherwise start one (the exit condition is assumed true on every tick)."""
    mgr = IcebergManager(max_slice_qty=500, min_delay_sec=0.0, max_delay_sec=0.0)

    async def exit_task():
        fill = await execute_exit_orders(broker, mgr, pos, _sell(pos.quantity), 84.0, **FAST)
        pos.quantity -= fill.filled_qty
        pos.is_exiting = False

    with patch("trading_bot.iceberg_manager.ORDER_LIMITER.allow", return_value=True):
        for _ in range(ticks):
            if pos.quantity > 0 and not exit_in_flight(pos, stuck_after=stuck_after, on_stuck=on_stuck):
                pos.is_exiting = True
                start_exit(pos, asyncio.create_task(exit_task()))
            await asyncio.sleep(0.01)
        task = guard_for(pos).exit_task
        if task is not None:
            await task


def test_a_slow_exit_is_never_restarted_by_the_lock_timer():
    """The 30s reset let the next tick start a second exit while the first
    was still working; both sold. Here the exit takes far longer than the
    stuck threshold and ticks keep arriving."""
    broker = FakeBroker(holdings={OPT: 75})
    broker.place_delay = 0.3                       # the exit is slow at the broker
    pos = _position()
    stuck = []

    asyncio.run(_tick_loop(broker, pos, ticks=40, stuck_after=0.05, on_stuck=stuck.append))
    sells = [r for r in broker.place_calls if r.side == OrderSide.SELL]
    assert len(sells) == 1
    assert broker.net[OPT] == 0
    assert len(stuck) == 1                         # reported once, not retried


def test_the_lock_is_released_when_the_exit_finishes_unfilled():
    broker = FakeBroker(holdings={OPT: 75})
    broker.set_default(fill_after=None)            # nothing ever fills
    pos = _position()

    asyncio.run(_tick_loop(broker, pos, ticks=5, stuck_after=60.0))
    assert pos.is_exiting is False
    assert not exit_in_flight(pos)


def test_a_lock_with_no_tracked_task_is_kept():
    """The dashboard close path sets is_exiting itself, with no task."""
    pos = _position()
    pos.is_exiting = True
    assert exit_in_flight(pos) is True and pos.is_exiting is True


def test_a_held_position_stays_locked_after_its_task_ends():
    async def run():
        pos = _position()
        pos.is_exiting = True
        start_exit(pos, asyncio.create_task(asyncio.sleep(0)))
        guard_for(pos).hold_reason = "unresolved exit orders ['F1']"
        await asyncio.sleep(0.01)
        return pos

    pos = asyncio.run(run())
    assert exit_in_flight(pos) is True


# ---------------------------------------------------------------------------
# #3 -- trailing-stop replacement keeps at most one live stop
# ---------------------------------------------------------------------------

from trading_bot.order_safety import replace_stop


def _open(pos):
    return lambda: True


def test_two_rungs_in_quick_succession_leave_one_stop():
    async def run():
        broker = FakeBroker(holdings={OPT: 75})
        broker.place_delay = 0.05
        pos = _position()
        _place_stop(broker, pos)
        pos.stop_loss = 100.0
        t1 = asyncio.create_task(replace_stop(broker, pos, _open(pos)))
        await asyncio.sleep(0.01)
        pos.stop_loss = 115.0                       # next rung lands mid-replacement
        t2 = asyncio.create_task(replace_stop(broker, pos, _open(pos)))
        return broker, pos, await asyncio.gather(t1, t2)

    broker, pos, outcomes = asyncio.run(run())
    assert outcomes == ["replaced", "replaced"]
    stops = broker.live_stops(OPT)
    assert [s.order_id for s in stops] == [pos.sl_order_id]
    assert stops[0].request.trigger_price == 115.0 and stops[0].request.quantity == 75


def test_a_refused_cancel_of_the_old_stop_cancels_the_new_one():
    broker = FakeBroker(holdings={OPT: 75})
    pos = _position()
    old_id = _place_stop(broker, pos, cancel_fail_count=1)
    pos.stop_loss = 100.0

    outcome = asyncio.run(replace_stop(broker, pos, _open(pos)))
    assert outcome == "kept_old"
    assert [s.order_id for s in broker.live_stops()] == [old_id] == [pos.sl_order_id]


def test_two_live_stops_are_both_cleared_before_the_exit_sells():
    broker = FakeBroker(holdings={OPT: 75})
    pos = _position()
    _place_stop(broker, pos, cancel_fail_count=1)
    broker.script_next(cancel_fail_count=1)         # the new stop's cleanup fails once too
    pos.stop_loss = 100.0

    assert asyncio.run(replace_stop(broker, pos, _open(pos))) == "two_live"
    assert len(broker.live_stops()) == 2
    fill = asyncio.run(_exit(broker, pos))
    assert fill.local_filled == 75
    assert broker.live_stops() == [] and broker.net[OPT] == 0


def test_a_stop_update_queued_behind_an_exit_places_nothing():
    """The update would otherwise place a fresh stop after the exit had
    closed the position: a live sell order against no holdings."""
    async def run():
        broker = FakeBroker(holdings={OPT: 75})
        broker.place_delay = 0.05
        pos = _position()
        _place_stop(broker, pos)
        pos.is_exiting = True
        start_exit(pos, asyncio.create_task(_exit(broker, pos)))
        await asyncio.sleep(0)                      # the exit takes the stop lock first
        pos.stop_loss = 100.0
        outcome = await replace_stop(broker, pos, _open(pos))
        await guard_for(pos).exit_task
        return broker, outcome

    broker, outcome = asyncio.run(run())
    assert outcome == "skipped"
    assert broker.live_stops() == [] and broker.net[OPT] == 0


def test_an_exit_waits_for_an_in_flight_stop_update():
    async def run():
        broker = FakeBroker(holdings={OPT: 75})
        broker.place_delay = 0.05
        pos = _position()
        _place_stop(broker, pos)
        pos.stop_loss = 100.0
        update = asyncio.create_task(replace_stop(broker, pos, _open(pos)))
        await asyncio.sleep(0.01)                   # the update is placing its new stop
        fill = await _exit(broker, pos)
        return broker, await update, fill

    broker, outcome, fill = asyncio.run(run())
    assert outcome == "replaced"
    assert fill.local_filled == 75
    assert broker.live_stops() == [] and broker.net[OPT] == 0


def test_an_update_after_the_position_closed_places_nothing():
    broker = FakeBroker(holdings={OPT: 75})
    pos = _position()
    assert asyncio.run(replace_stop(broker, pos, lambda: False)) == "skipped"
    assert broker.place_calls == []


def test_an_old_stop_that_sold_during_replacement_shrinks_the_new_one():
    broker = FakeBroker(holdings={OPT: 75})
    pos = _position()
    _place_stop(broker, pos, fill_on_cancel=25, fill_price=84.0)
    pos.stop_loss = 100.0

    assert asyncio.run(replace_stop(broker, pos, _open(pos))) == "stop_fired"
    stops = broker.live_stops(OPT)
    assert len(stops) == 1 and stops[0].request.quantity == 50

    fill = asyncio.run(_exit(broker, pos))
    assert (fill.stop_filled, fill.local_filled) == (25, 50)
    assert broker.live_stops() == [] and broker.net[OPT] == 0
