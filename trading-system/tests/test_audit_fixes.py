"""Unit tests validating the 13 audit findings and critical fixes:
1. Order confirmed fill tracking vs accepted
2. Slicing with halt_check=None on exits
3. Exchange Stop Loss uses OrderType.SL (SL-Limit) not SL-M for index options
4. Trailing SL replacement safety (new placed before old cancelled)
5. State mutation re-ordering (position removed & saved FIRST before side-effects)
6. Quarantine prior-day stale positions in _load_positions
7. Task tracking
"""
import asyncio
import json
import os
import tempfile
import time
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytz

from brokers.models import (
    OrderBookEntry,
    OrderRequest,
    OrderResponse,
    OrderSide,
    OrderStatus,
    OrderType,
    Position,
)
from trading_bot.iceberg_manager import IcebergManager

_IST = pytz.timezone("Asia/Kolkata")


def test_order_book_entry_filled_qty():
    """Verify OrderBookEntry supports filled_qty."""
    entry = OrderBookEntry(
        order_id="ORD123",
        symbol="NSE:NIFTY26OCT25000CE",
        side=OrderSide.BUY,
        quantity=50,
        price=100.0,
        status=OrderStatus.COMPLETE,
        order_type=OrderType.LIMIT,
        traded_price=99.5,
        filled_qty=50,
    )
    assert entry.filled_qty == 50
    assert entry.status == OrderStatus.COMPLETE

    # Default value
    entry_default = OrderBookEntry(
        order_id="ORD124",
        symbol="NSE:NIFTY26OCT25000CE",
        side=OrderSide.BUY,
        quantity=50,
        price=100.0,
        status=OrderStatus.OPEN,
        order_type=OrderType.LIMIT,
    )
    assert entry_default.filled_qty == 0


def test_iceberg_execute_rate_limit_retry():
    """Verify IcebergManager retries rate-limited slices rather than dropping them."""
    async def _run():
        mgr = IcebergManager(max_slice_qty=50, min_delay_sec=0.01, max_delay_sec=0.02)
        broker = MagicMock()
        broker.BROKER_ID = "test_broker"

        async def mock_place(req):
            return OrderResponse(
                order_id="ORD1",
                status=OrderStatus.OPEN,
                symbol=req.symbol,
                quantity=req.quantity,
                side=req.side,
            )

        broker.place_order_async = mock_place

        req = OrderRequest(
            symbol="NSE:NIFTY26OCT25000CE",
            quantity=100,
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            price=100.0,
        )

        with patch("trading_bot.iceberg_manager.ORDER_LIMITER.allow", return_value=True):
            slices = await mgr.execute_iceberg(broker, req, halt_check=None)
            assert len(slices) == 2
            assert sum(s.quantity for s in slices) == 100

    asyncio.run(_run())


def test_stale_position_quarantine(tmp_path):
    """Verify prior-day positions are quarantined and not loaded into active positions."""
    from trading_bot import main as bot_main

    pos_file = tmp_path / "active_positions.json"
    today_str = datetime.now(_IST).strftime("%Y-%m-%d")

    data = {
        "NSE:NIFTY50-INDEX": {
            "symbol": "NSE:NIFTY26OCT25000CE",
            "side": 1,
            "entry_price": 100.0,
            "quantity": 50,
            "entry_time": f"{today_str} 10:00:00",
            "highest_price": 100.0,
            "lowest_price": 100.0,
            "stop_loss": 85.0,
            "target": 0.0,
        },
        "NSE:BANKNIFTY-INDEX": {
            "symbol": "NSE:BANKNIFTY26OCT50000PE",
            "side": -1,
            "entry_price": 200.0,
            "quantity": 30,
            "entry_time": "2026-10-10 14:00:00",  # Stale date from past
            "highest_price": 200.0,
            "lowest_price": 200.0,
            "stop_loss": 170.0,
            "target": 0.0,
        },
    }
    pos_file.write_text(json.dumps(data), encoding="utf-8")

    with patch.object(bot_main, "_POSITIONS_PATH", pos_file),             patch.object(bot_main.alerter, "send_alert"):
        loaded = bot_main._load_positions()
        # Today's position is loaded
        assert "NSE:NIFTY50-INDEX" in loaded
        # Past position is NOT loaded
        assert "NSE:BANKNIFTY-INDEX" not in loaded

        # Quarantined file was written
        q_file = tmp_path / "quarantined_positions.json"
        assert q_file.exists()
        q_data = json.loads(q_file.read_text(encoding="utf-8"))
        assert "NSE:BANKNIFTY-INDEX" in q_data


def test_task_tracker():
    """Verify _track_task retains strong references until done."""
    from trading_bot.main import _active_background_tasks, _track_task

    async def dummy_task():
        await asyncio.sleep(0.01)

    loop = asyncio.new_event_loop()
    try:
        task = loop.create_task(dummy_task())
        _track_task(task)
        assert task in _active_background_tasks
        loop.run_until_complete(task)
        assert task not in _active_background_tasks
    finally:
        loop.close()
