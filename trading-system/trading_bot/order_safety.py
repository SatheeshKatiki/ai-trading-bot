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
from typing import Any, Callable, Iterable, List, Optional

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

    if pos is not None:
        # Under the stop lock, so a trailing-stop replacement cannot place a
        # new stop between this resolution and the local sell.
        async with guard_for(pos).stop_lock:
            if not await _clear_all_stops(broker, pos, result, held, exit_price):
                logger.error("Exchange stop %s for %s could not be cancelled -- not selling locally.",
                             pos.sl_order_id, exit_req.symbol)
                return result
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


# ---------------------------------------------------------------------------
# Placing an exchange stop
# ---------------------------------------------------------------------------

#: Limit price of an option stop-limit, as a fraction of its trigger.
STOP_LIMIT_FRACTION = 0.90


def stop_request(pos: Any, qty: int) -> Any:
    """The exchange stop for `qty` of `pos`: stop-limit for options (limit
    10% under the trigger), stop-market otherwise."""
    from brokers.models import OrderRequest, OrderSide, OrderType
    from shared.instruments import is_option_symbol

    is_opt = is_option_symbol(pos.symbol)
    return OrderRequest(
        symbol=pos.symbol,
        quantity=int(qty),
        side=OrderSide.SELL if pos.side == 1 or is_opt else OrderSide.BUY,
        order_type=OrderType.SL if is_opt else OrderType.SL_M,
        trigger_price=round(pos.stop_loss, 2),
        price=round(pos.stop_loss * STOP_LIMIT_FRACTION, 2) if is_opt else 0.0,
    )


async def place_hard_stop(broker: Any, pos: Any, qty: int) -> Optional[str]:
    """Place the exchange stop for `qty` of `pos`; its order id, or None."""
    try:
        resp = await broker.place_order_async(stop_request(pos, qty))
    except Exception as exc:
        logger.error("Exchange stop placement failed for %s: %s", pos.symbol, exc)
        return None
    order_id = getattr(resp, "order_id", None) if resp else None
    if not order_id:
        logger.error("Exchange stop for %s returned no order id: %s", pos.symbol, resp)
        return None
    return order_id


async def protect_remaining(broker: Any, pos: Any) -> Optional[str]:
    """Put an exchange stop back on the lots an exit left open.

    An exit cancels the stop before selling; if the sell fills only partly
    (or not at all) the remaining lots would otherwise have no exchange stop
    until some later exit succeeds. No-op when a stop is already tracked.
    """
    if getattr(broker, "paper_mode", False) or pos is None or pos.quantity <= 0:
        return None
    if getattr(pos, "sl_order_id", None):
        return pos.sl_order_id
    order_id = await place_hard_stop(broker, pos, pos.quantity)
    if order_id:
        pos.sl_order_id = order_id
        logger.info("Exchange stop restored for %d remaining of %s at %.2f (ID: %s)",
                    pos.quantity, pos.symbol, pos.stop_loss, order_id)
    return order_id


# ---------------------------------------------------------------------------
# Per-position runtime guards
# ---------------------------------------------------------------------------
# Kept here, not on shared.exits.Position: they are facts about this running
# process (a lock, a task), never persisted, and Position is shared with code
# that serialises a fixed set of fields.

#: An exit task still running after this long is reported, never released:
#: its orders may still fill, so a second exit could sell the same lots.
EXIT_STUCK_AFTER_S = 60.0


@dataclass
class PositionGuard:
    #: Serialises everything that touches this position's exchange stop:
    #: trailing-stop replacement and the stop resolution inside an exit.
    stop_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    exit_task: Optional[asyncio.Task] = None
    exit_started: float = 0.0
    stuck_reported: bool = False
    #: Set when an exit left orders that may still fill. The position stays
    #: locked until the operator resolves it (or the engine restarts).
    hold_reason: Optional[str] = None
    #: Entry orders are still being placed or settled.
    entry_pending: bool = False
    #: Stops other than pos.sl_order_id that may still be live (a replacement
    #: whose cleanup was refused). An exit must clear these too.
    extra_stop_ids: List[str] = field(default_factory=list)
    #: Stops that can no longer trade but sold lots the book has not yet
    #: booked. The next exit counts their fills.
    dead_stop_ids: List[str] = field(default_factory=list)


# id(pos) -> (pos, guard). Holding `pos` keeps its id from being reused while
# the guard exists; forget() releases both once the position is closed.
_GUARDS: dict[int, tuple[Any, PositionGuard]] = {}


def guard_for(pos: Any) -> PositionGuard:
    entry = _GUARDS.get(id(pos))
    if entry is None or entry[0] is not pos:
        entry = (pos, PositionGuard())
        _GUARDS[id(pos)] = entry
    return entry[1]


def forget(pos: Any) -> None:
    entry = _GUARDS.get(id(pos))
    if entry is not None and entry[0] is pos:
        del _GUARDS[id(pos)]


def start_exit(pos: Any, task: asyncio.Task, now: Optional[float] = None) -> None:
    """Record the exit task that now owns `pos` (`pos.is_exiting` is set by the caller)."""
    guard = guard_for(pos)
    guard.exit_task = task
    guard.exit_started = time.monotonic() if now is None else now
    guard.stuck_reported = False


def exit_running(pos: Any) -> bool:
    """An exit task for `pos` exists and has not finished."""
    entry = _GUARDS.get(id(pos))
    task = entry[1].exit_task if entry is not None and entry[0] is pos else None
    return task is not None and not task.done()


def exit_in_flight(pos: Any, now: Optional[float] = None,
                   stuck_after: float = EXIT_STUCK_AFTER_S,
                   on_stuck: Optional[Callable[[float], None]] = None) -> bool:
    """True while `pos` must not be exited again.

    The lock is released only when the exit task that took it has finished
    and left nothing that may still trade. A slow task is never timed out:
    its orders could still fill, so starting a second exit is how a position
    gets sold twice. A lock with no tracked task (e.g. the dashboard close
    path) is left alone, as before.
    """
    if not getattr(pos, "is_exiting", False):
        return False
    guard = guard_for(pos)
    task = guard.exit_task
    if task is None:
        return True
    if not task.done():
        now = time.monotonic() if now is None else now
        if now - guard.exit_started > stuck_after and not guard.stuck_reported:
            guard.stuck_reported = True
            logger.critical("Exit for %s has been running %.0fs -- still waiting for it, not retrying.",
                            getattr(pos, "symbol", "?"), now - guard.exit_started)
            if on_stuck is not None:
                on_stuck(now - guard.exit_started)
        return True
    if guard.hold_reason:
        return True
    guard.exit_task = None
    pos.is_exiting = False
    return False


async def _clear_all_stops(broker: Any, pos: Any, result: ExitFill, held: int, exit_price: float) -> bool:
    """Take every exchange stop of `pos` out of play and count what they sold.

    False (with `result.stop_cleared` False) when any stop is still live; the
    ones that are, stay tracked so a later attempt retries them.
    """
    guard = guard_for(pos)
    candidates = [oid for oid in [pos.sl_order_id, *guard.extra_stop_ids] if oid]
    still_live: List[str] = []
    for order_id in candidates:
        stop = await resolve_stop(broker, order_id)
        if not stop.cleared:
            still_live.append(order_id)
        elif stop.filled > 0 and order_id not in guard.dead_stop_ids:
            guard.dead_stop_ids.append(order_id)
    if still_live:
        pos.sl_order_id, guard.extra_stop_ids = still_live[0], still_live[1:]
        result.stop_cleared = False
        return False
    pos.sl_order_id, guard.extra_stop_ids = None, []

    filled, value = 0, 0.0
    for order_id in guard.dead_stop_ids:
        qty, price = filled_of(await read_order(broker, order_id))
        filled += qty
        value += qty * (price if price > 0 else float(getattr(pos, "stop_loss", exit_price)))
    guard.dead_stop_ids = []
    result.stop_filled = min(filled, held)
    result.stop_price = value / filled if filled else 0.0
    return True


# ---------------------------------------------------------------------------
# Trailing-stop replacement
# ---------------------------------------------------------------------------

async def replace_stop(broker: Any, pos: Any, still_open: Callable[[], bool]) -> str:
    """Move `pos`'s exchange stop to `pos.stop_loss`, keeping at most one live stop.

    New stop first, then the old one cancelled. If the old one will not
    cancel, the new one is cancelled instead so the old stop stays the only
    one. Runs under the position's stop lock, and does nothing once an exit
    has started or the position has left the book, so it can never leave a
    stop behind a closed position.

    Returns "replaced", "placed", "skipped", "kept_old" (the old stop is
    still the live one), "stop_fired" (the old stop had sold lots) or
    "two_live" (both could be live; tracked for the exit to clear).
    """
    guard = guard_for(pos)
    async with guard.stop_lock:
        if exit_running(pos) or not still_open() or pos.quantity <= 0:
            return "skipped"
        old_id = pos.sl_order_id
        new_id = await place_hard_stop(broker, pos, pos.quantity)
        if not new_id:
            return "kept_old"
        if not old_id:
            pos.sl_order_id = new_id
            return "placed"

        if await cancel_order(broker, old_id):
            sold, _ = filled_of(await read_order(broker, old_id))
            pos.sl_order_id = new_id
            if sold <= 0:
                return "replaced"
            # The old stop sold lots before the cancel landed; the new stop
            # covers the full quantity and would oversell. Shrink it.
            guard.dead_stop_ids.append(old_id)
            await _shrink_stop(broker, pos, guard, pos.quantity - sold)
            return "stop_fired"

        old = await read_order(broker, old_id)
        if old is not None and old.status == OrderStatus.COMPLETE:
            # The old stop has closed the position; the new one must go.
            pos.sl_order_id = old_id
            if not await cancel_order(broker, new_id):
                guard.extra_stop_ids.append(new_id)
            return "stop_fired"
        if await cancel_order(broker, new_id):
            return "kept_old"
        pos.sl_order_id = new_id
        guard.extra_stop_ids.append(old_id)
        return "two_live"


async def _shrink_stop(broker: Any, pos: Any, guard: PositionGuard, qty: int) -> None:
    current = pos.sl_order_id
    if not await cancel_order(broker, current):
        return
    pos.sl_order_id = None
    if qty > 0:
        pos.sl_order_id = await place_hard_stop(broker, pos, qty)
