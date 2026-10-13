"""A scripted in-memory broker for order-side safety tests.

Keeps a real order book: every order has a status, a filled quantity and an
average price, and fills arrive on a script (after a delay, partially, at the
moment a cancel is attempted, or when a test triggers a stop). The broker
also keeps the net position per symbol, so a test can assert what would have
happened at the exchange -- "never sold more than was held", "at most one
live stop" -- instead of asserting which methods were called.
"""
from __future__ import annotations

import asyncio
import itertools
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Deque, Dict, List, Optional

from brokers.models import (
    OrderBookEntry,
    OrderRequest,
    OrderResponse,
    OrderSide,
    OrderStatus,
    OrderType,
)


@dataclass
class Script:
    """How the next placed order behaves.

    fill_after: seconds after placement at which `fill_qty` fills (None = never
    fills on its own; stops always wait for `trigger`).
    fill_qty: how much fills then (None = the whole order).
    fill_on_cancel: fill this much the instant a cancel arrives, before the
    cancel is applied -- the fill-versus-cancel race.
    cancel_fails: the cancel raises (True) or returns an error dict ("dict").
    cancel_fail_count: the first N cancels raise, later ones work.
    place_fails: placement raises.
    """
    fill_after: Optional[float] = 0.0
    fill_qty: Optional[int] = None
    fill_price: Optional[float] = None
    fill_on_cancel: int = 0
    cancel_fails: object = False
    cancel_fail_count: int = 0
    place_fails: bool = False


@dataclass
class FakeOrder:
    order_id: str
    request: OrderRequest
    script: Script
    placed_at: float
    status: OrderStatus = OrderStatus.OPEN
    filled: int = 0
    value: float = 0.0
    timed_fill_done: bool = False

    @property
    def is_stop(self) -> bool:
        return self.request.order_type in (OrderType.SL, OrderType.SL_M)

    @property
    def avg_price(self) -> float:
        return self.value / self.filled if self.filled else 0.0


class FakeBroker:
    BROKER_ID = "fake"
    DISPLAY_NAME = "Fake"

    def __init__(self, holdings: Optional[Dict[str, int]] = None, default_price: float = 100.0):
        self.paper_mode = False
        self.orders: Dict[str, FakeOrder] = {}
        self.net: Dict[str, int] = defaultdict(int, holdings or {})
        self.default_price = default_price
        self._scripts: Deque[Script] = deque()
        self._default_script = Script()
        self._ids = itertools.count(1)
        self.cancel_calls: List[str] = []
        self.place_calls: List[OrderRequest] = []
        self.place_delay = 0.0

    # ── scripting ────────────────────────────────────────────────────
    def script_next(self, **kwargs) -> None:
        self._scripts.append(Script(**kwargs))

    def set_default(self, **kwargs) -> None:
        self._default_script = Script(**kwargs)

    def trigger(self, order_id: str, qty: Optional[int] = None, price: Optional[float] = None) -> None:
        """A stop order's trigger is hit and `qty` of it fills."""
        order = self.orders[order_id]
        assert order.is_stop and order.status == OrderStatus.OPEN, f"{order_id} is not a live stop"
        self._fill(order, qty if qty is not None else order.request.quantity - order.filled,
                   price if price is not None else (order.request.trigger_price or self.default_price))

    # ── inspection ───────────────────────────────────────────────────
    def live_stops(self, symbol: Optional[str] = None) -> List[FakeOrder]:
        return [o for o in self.orders.values()
                if o.is_stop and o.status == OrderStatus.OPEN
                and (symbol is None or o.request.symbol == symbol)]

    def live_orders(self) -> List[FakeOrder]:
        self._advance_all()
        return [o for o in self.orders.values() if o.status == OrderStatus.OPEN]

    def sold(self, symbol: str) -> int:
        return sum(o.filled for o in self.orders.values()
                   if o.request.symbol == symbol and o.request.side == OrderSide.SELL)

    # ── internals ────────────────────────────────────────────────────
    def _fill(self, order: FakeOrder, qty: int, price: float) -> None:
        qty = max(0, min(qty, order.request.quantity - order.filled))
        if qty == 0:
            return
        order.filled += qty
        order.value += qty * price
        sign = 1 if order.request.side == OrderSide.BUY else -1
        self.net[order.request.symbol] += sign * qty
        if order.filled >= order.request.quantity:
            order.status = OrderStatus.COMPLETE

    def _advance(self, order: FakeOrder) -> None:
        s = order.script
        if (order.status == OrderStatus.OPEN and not order.is_stop and not order.timed_fill_done
                and s.fill_after is not None and time.monotonic() - order.placed_at >= s.fill_after):
            order.timed_fill_done = True
            qty = s.fill_qty if s.fill_qty is not None else order.request.quantity
            self._fill(order, qty, s.fill_price or order.request.price or self.default_price)

    def _advance_all(self) -> None:
        for order in list(self.orders.values()):
            self._advance(order)

    # ── broker API ───────────────────────────────────────────────────
    def place_order(self, request: OrderRequest) -> OrderResponse:
        self.place_calls.append(request)
        script = self._scripts.popleft() if self._scripts else self._default_script
        if script.place_fails:
            raise RuntimeError("scripted placement failure")
        order_id = f"F{next(self._ids)}"
        order = FakeOrder(order_id, request, script, time.monotonic())
        self.orders[order_id] = order
        self._advance(order)
        return OrderResponse(order_id=order_id, status=OrderStatus.OPEN, symbol=request.symbol,
                             quantity=request.quantity, side=request.side, price=request.price)

    async def place_order_async(self, request: OrderRequest) -> OrderResponse:
        if self.place_delay:
            await asyncio.sleep(self.place_delay)
        return self.place_order(request)

    def get_order_status(self, order_id: str) -> Optional[OrderBookEntry]:
        order = self.orders.get(order_id)
        if order is None:
            return None
        self._advance(order)
        r = order.request
        return OrderBookEntry(
            order_id=order_id, symbol=r.symbol, side=r.side, quantity=r.quantity,
            price=r.price, status=order.status, order_type=r.order_type,
            traded_price=order.avg_price, filled_qty=order.filled,
        )

    def cancel_order(self, order_id: str):
        self.cancel_calls.append(order_id)
        order = self.orders[order_id]
        self._advance(order)
        if order.script.fill_on_cancel:
            self._fill(order, order.script.fill_on_cancel,
                       order.script.fill_price or order.request.price or self.default_price)
        if order.script.cancel_fail_count > 0:
            order.script.cancel_fail_count -= 1
            raise RuntimeError("scripted transient cancel failure")
        if order.script.cancel_fails == "dict":
            return {"s": "error", "code": -52, "message": "scripted cancel failure"}
        if order.script.cancel_fails:
            raise RuntimeError("scripted cancel failure")
        if order.status != OrderStatus.OPEN:
            raise RuntimeError(f"order {order_id} is {order.status.value}, cannot cancel")
        order.status = OrderStatus.CANCELLED
        return {"s": "ok", "code": 1103, "id": order_id}
