"""Order-side safety for the live engine.

What the broker says about an order, turned into what the book may believe.
Pulled out of run_live_bot()'s closures so a scripted broker can drive it in
tests (tests/test_live_exit_safety.py).

The rule everything here follows: a quantity counts as traded only when the
broker reports it filled, and an order counts as finished only when it is
complete or its cancel was accepted. Anything else is "unresolved" -- it may
still trade, and the caller must not act as if it cannot.
"""
from __future__ import annotations

import asyncio
import dataclasses
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Iterable, List, Optional

from brokers.models import OrderStatus

logger = logging.getLogger(__name__)

#: How long one slice is polled for a fill before its remainder is cancelled.
SLICE_FILL_TIMEOUT_S = 3.0
POLL_INTERVAL_S = 0.5


@dataclass
class SliceFill:
    order_id: str
    requested: int
    filled: int
    avg_price: float
    #: True when the order can trade no further: complete, or its cancel was
    #: accepted. False means it may still be working at the exchange.
    resolved: bool


@dataclass
class FillSummary:
    slices: List[SliceFill] = field(default_factory=list)

    @property
    def filled_qty(self) -> int:
        return sum(s.filled for s in self.slices)

    @property
    def unresolved_order_ids(self) -> List[str]:
        return [s.order_id for s in self.slices if not s.resolved]

    def avg_price(self, fallback: float) -> float:
        """Quantity-weighted fill price; slices with no reported price use `fallback`."""
        qty = self.filled_qty
        if qty <= 0:
            return fallback
        value = sum(s.filled * (s.avg_price if s.avg_price > 0 else fallback) for s in self.slices)
        return value / qty


def filled_of(entry: Any) -> tuple[int, float]:
    """(filled quantity, average traded price) from an order-book entry."""
    if entry is None:
        return 0, 0.0
    filled = int(getattr(entry, "filled_qty", 0) or 0)
    if filled == 0 and getattr(entry, "status", None) == OrderStatus.COMPLETE:
        filled = int(getattr(entry, "quantity", 0) or 0)
    return filled, float(getattr(entry, "traded_price", 0.0) or 0.0)


async def read_order(broker: Any, order_id: str) -> Any:
    try:
        return await asyncio.to_thread(broker.get_order_status, order_id)
    except Exception as exc:
        logger.warning("Order status lookup failed for %s: %s", order_id, exc)
        return None


def cancel_accepted(result: Any) -> bool:
    """Brokers report a refused cancel either by raising or in the response
    (Fyers: ``{"s": "error", ...}``)."""
    if isinstance(result, dict):
        state = str(result.get("s", result.get("status", ""))).lower()
        if state in ("error", "failed", "failure", "rejected"):
            return False
    return True


async def cancel_order(broker: Any, order_id: str) -> bool:
    """Cancel `order_id`; True only when the broker accepted the cancel."""
    try:
        result = await asyncio.to_thread(broker.cancel_order, order_id)
    except Exception as exc:
        logger.warning("Cancel of %s failed: %s", order_id, exc)
        return False
    if not cancel_accepted(result):
        logger.warning("Cancel of %s refused by broker: %s", order_id, result)
        return False
    return True


async def settle_order(
    broker: Any,
    order_id: str,
    requested: int,
    timeout: float = SLICE_FILL_TIMEOUT_S,
    poll_interval: float = POLL_INTERVAL_S,
) -> SliceFill:
    """Wait up to `timeout` for `order_id` to fill, then cancel what is left
    and read back the final fill.

    The read after the cancel is what counts: a slice can fill between the
    last poll and the cancel, and only the broker's final filled quantity
    says how much traded.
    """
    deadline = time.monotonic() + timeout
    filled, price = 0, 0.0
    while True:
        entry = await read_order(broker, order_id)
        if entry is not None:
            filled, price = filled_of(entry)
            if filled >= requested or entry.status == OrderStatus.COMPLETE:
                return SliceFill(order_id, requested, filled, price, resolved=True)
        if time.monotonic() >= deadline:
            break
        await asyncio.sleep(poll_interval)

    cancelled = await cancel_order(broker, order_id)
    final = await read_order(broker, order_id)
    if final is not None:
        filled, price = filled_of(final)
    complete = final is not None and (final.status == OrderStatus.COMPLETE or filled >= requested)
    return SliceFill(order_id, requested, filled, price, resolved=complete or cancelled)


async def confirm_fills(
    broker: Any,
    responses: Iterable[Any],
    timeout: float = SLICE_FILL_TIMEOUT_S,
    poll_interval: float = POLL_INTERVAL_S,
) -> FillSummary:
    """Settle every placed slice, each against its own deadline."""
    summary = FillSummary()
    for resp in responses:
        if not resp or not getattr(resp, "order_id", None):
            continue
        summary.slices.append(
            await settle_order(broker, resp.order_id, int(resp.quantity), timeout, poll_interval)
        )
    return summary


# ---------------------------------------------------------------------------
# The exchange stop, before any local exit
# ---------------------------------------------------------------------------

@dataclass
class StopResolution:
    filled: int
    avg_price: float
    #: True when the stop can trade no further (complete, or cancel accepted).
    cleared: bool


async def resolve_stop(broker: Any, order_id: str) -> StopResolution:
    """Take an exchange stop out of play, reporting how much of it traded.

    A stop-limit can fill partly in a gap, so a stop that is not COMPLETE may
    still have sold lots. If the cancel is refused and the order is not
    complete, the stop is still live: `cleared` is False and nothing may be
    sold locally, or the stop and the local exit would both sell.
    """
    entry = await read_order(broker, order_id)
    filled, price = filled_of(entry)
    if entry is not None and entry.status == OrderStatus.COMPLETE:
        return StopResolution(filled, price, cleared=True)
    cancelled = await cancel_order(broker, order_id)
    final = await read_order(broker, order_id)
    if final is not None:
        filled, price = filled_of(final)
        if final.status == OrderStatus.COMPLETE:
            return StopResolution(filled, price, cleared=True)
    return StopResolution(filled, price, cleared=cancelled)


@dataclass
class ExitFill:
    #: False: the exchange stop is still live and nothing was sold.
    stop_cleared: bool = True
    stop_filled: int = 0
    stop_price: float = 0.0
    local_filled: int = 0
    local_price: float = 0.0
    unresolved_order_ids: List[str] = field(default_factory=list)

    @property
    def filled_qty(self) -> int:
        return self.stop_filled + self.local_filled

    @property
    def avg_price(self) -> float:
        qty = self.filled_qty
        if qty <= 0:
            return 0.0
        return (self.stop_filled * self.stop_price + self.local_filled * self.local_price) / qty


async def execute_exit_orders(
    broker: Any,
    iceberg: Any,
    pos: Any,
    exit_req: Any,
    exit_price: float,
    timeout: float = SLICE_FILL_TIMEOUT_S,
    poll_interval: float = POLL_INTERVAL_S,
) -> ExitFill:
    """The order side of an exit: clear the exchange stop, sell what the stop
    did not, and report what actually traded. Changes nothing in the book
    except `pos.sl_order_id`, which is cleared once the stop is out of play.
    """
    result = ExitFill()
    held = int(pos.quantity) if pos is not None else int(exit_req.quantity)

    if pos is not None and getattr(pos, "sl_order_id", None):
        stop = await resolve_stop(broker, pos.sl_order_id)
        if not stop.cleared:
            logger.error("Exchange stop %s for %s could not be cancelled -- not selling locally.",
                         pos.sl_order_id, exit_req.symbol)
            result.stop_cleared = False
            return result
        pos.sl_order_id = None
        result.stop_filled = min(stop.filled, held)
        result.stop_price = stop.avg_price if stop.avg_price > 0 else float(getattr(pos, "stop_loss", exit_price))
        if result.stop_filled:
            logger.warning("Exchange stop for %s had already sold %d of %d.",
                           exit_req.symbol, result.stop_filled, held)

    to_sell = min(int(exit_req.quantity), held - result.stop_filled)
    if to_sell <= 0:
        return result
    if to_sell != exit_req.quantity:
        exit_req = dataclasses.replace(exit_req, quantity=to_sell)

    responses = await iceberg.execute_iceberg(broker, exit_req, halt_check=None)
    if getattr(broker, "paper_mode", False):
        result.local_filled = sum(int(r.quantity) for r in responses if r)
        result.local_price = exit_price
        return result

    fills = await confirm_fills(broker, responses, timeout, poll_interval)
    result.local_filled = fills.filled_qty
    result.local_price = fills.avg_price(exit_price)
    result.unresolved_order_ids = fills.unresolved_order_ids
    return result
