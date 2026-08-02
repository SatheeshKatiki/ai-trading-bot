"""Regression tests for IcebergManager (trading_bot/iceberg_manager.py).

Root-cause fix (Medium audit finding): the test suite had zero coverage
for iceberg order execution, despite this session finding and fixing a
Critical pyramid-scale-in race condition in the same area (main.py's
background_iceberg_scale/background_iceberg_entry). These tests
exercise the real IcebergManager class against a mocked broker (no
real order placement, no real network calls) to lock in the slicing
math, rate-limit handling, and mid-execution halt behavior.

Uses plain asyncio.run() wrappers rather than pytest-asyncio (not
available for this environment's Python version) so these tests need
no extra plugin/dependency.
"""
import asyncio
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

sys.path.append(str(Path(__file__).resolve().parents[1]))

from trading_bot.iceberg_manager import IcebergManager
from brokers import OrderRequest, OrderSide, OrderType, ProductType
from brokers.models import OrderResponse, OrderStatus
import shared.security.rate_limiter as rate_limiter_mod


def _order(qty: int) -> OrderRequest:
    return OrderRequest(
        symbol="NSE:NIFTY50-INDEX", quantity=qty, side=OrderSide.BUY,
        order_type=OrderType.MARKET, product_type=ProductType.INTRADAY,
    )


def _fake_response(qty: int) -> OrderResponse:
    return OrderResponse(order_id="TEST_ORDER", status=OrderStatus.OPEN,
                          symbol="NSE:NIFTY50-INDEX", quantity=qty, side=OrderSide.BUY)


def test_small_order_executes_as_single_order():
    async def _run():
        manager = IcebergManager(max_slice_qty=500)
        broker = AsyncMock()
        broker.BROKER_ID = "test_broker"
        broker.place_order_async = AsyncMock(return_value=_fake_response(300))

        with patch.object(rate_limiter_mod.ORDER_LIMITER, "allow", return_value=True):
            result = await manager.execute_iceberg(broker, _order(300))

        assert len(result) == 1
        assert broker.place_order_async.call_count == 1
        placed_qty = broker.place_order_async.call_args[0][0].quantity
        assert placed_qty == 300, "an order under max_slice_qty must not be sliced"
    asyncio.run(_run())


def test_large_order_splits_into_correct_slices():
    async def _run():
        manager = IcebergManager(max_slice_qty=500, min_delay_sec=0.0, max_delay_sec=0.0)
        broker = AsyncMock()
        broker.BROKER_ID = "test_broker"
        broker.place_order_async = AsyncMock(side_effect=lambda req: _fake_response(req.quantity))

        with patch.object(rate_limiter_mod.ORDER_LIMITER, "allow", return_value=True), \
             patch("asyncio.sleep", new=AsyncMock(return_value=None)):
            result = await manager.execute_iceberg(broker, _order(1250))

        # 1250 / 500 -> slices of 500, 500, 250
        assert broker.place_order_async.call_count == 3
        placed_qtys = [c[0][0].quantity for c in broker.place_order_async.call_args_list]
        assert placed_qtys == [500, 500, 250]
        assert sum(placed_qtys) == 1250, "total sliced quantity must equal the original order quantity"
        assert len(result) == 3
    asyncio.run(_run())


def test_iceberg_halts_on_margin_rejection():
    async def _run():
        manager = IcebergManager(max_slice_qty=500, min_delay_sec=0.0, max_delay_sec=0.0)
        broker = AsyncMock()
        broker.BROKER_ID = "test_broker"

        call_count = {"n": 0}
        async def flaky_place(req):
            call_count["n"] += 1
            if call_count["n"] == 2:
                raise Exception("Order rejected: insufficient margin")
            return _fake_response(req.quantity)
        broker.place_order_async = AsyncMock(side_effect=flaky_place)

        with patch.object(rate_limiter_mod.ORDER_LIMITER, "allow", return_value=True), \
             patch("asyncio.sleep", new=AsyncMock(return_value=None)):
            result = await manager.execute_iceberg(broker, _order(1500))  # 3 slices of 500

        # Slice 1 succeeds, slice 2 raises a margin rejection and halts remaining slices
        assert call_count["n"] == 2, "execution must stop after a margin rejection, not attempt the 3rd slice"
        assert len(result) == 1
    asyncio.run(_run())


def test_iceberg_halts_on_system_halt_check():
    async def _run():
        manager = IcebergManager(max_slice_qty=500, min_delay_sec=0.0, max_delay_sec=0.0)
        broker = AsyncMock()
        broker.BROKER_ID = "test_broker"
        broker.place_order_async = AsyncMock(side_effect=lambda req: _fake_response(req.quantity))

        # halt_check() is polled between slices (after a slice executes,
        # before the next one starts) -- returning True unconditionally
        # means it must trip right after slice 1, before slice 2 starts.
        halt_check = lambda: True

        with patch.object(rate_limiter_mod.ORDER_LIMITER, "allow", return_value=True), \
             patch("asyncio.sleep", new=AsyncMock(return_value=None)):
            result = await manager.execute_iceberg(broker, _order(1500), halt_check=halt_check)

        # Only the first slice should execute -- halt_check() trips true right after it
        assert broker.place_order_async.call_count == 1
        assert len(result) == 1
    asyncio.run(_run())


def test_rate_limited_slice_is_not_placed():
    async def _run():
        manager = IcebergManager(max_slice_qty=500)
        broker = AsyncMock()
        broker.BROKER_ID = "test_broker"
        broker.place_order_async = AsyncMock(return_value=_fake_response(300))

        with patch.object(rate_limiter_mod.ORDER_LIMITER, "allow", return_value=False):
            result = await manager.execute_iceberg(broker, _order(300))

        assert broker.place_order_async.call_count == 0, "a rate-limited order must never reach the broker"
        assert result == []
    asyncio.run(_run())


if __name__ == "__main__":
    test_small_order_executes_as_single_order()
    test_large_order_splits_into_correct_slices()
    test_iceberg_halts_on_margin_rejection()
    test_iceberg_halts_on_system_halt_check()
    test_rate_limited_slice_is_not_placed()
    print("All iceberg execution tests passed.")
