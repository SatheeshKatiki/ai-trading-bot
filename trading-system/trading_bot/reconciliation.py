"""Broker-reconnect position reconciliation — pure decision logic.

Extracted out of `trading_bot.main.run_live_bot`'s `sync_broker_state`
nested closure so it's unit-testable without a live broker connection or
the surrounding ~1000-line function's module/closure state. This module
has no I/O and no side effects: given the local positions the engine
thinks are open, what the broker actually reports, and the broker's
recent order book, it decides which local positions are stale and how
to resolve each one's real exit price and P&L. The caller (`main.py`'s
`sync_broker_state`) is left as a thin wrapper that fetches the broker
data, calls this function, and applies the results (logging, risk-engine
updates, position-file persistence).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List

from brokers import OrderSide, OrderStatus
from brokers.models import OrderBookEntry, Position as BrokerPosition
from shared.exits import Position


@dataclass
class ReconciliationResult:
    """One local position resolved against the broker's real state."""
    symbol: str
    exit_price: float
    pnl: float
    is_estimate: bool   # True if no matching order-book fill was found
    trade_side: str     # "LONG" / "SHORT" — matches TradeRecord's convention
    state_action: str   # "SELL" / "BUY" — matches shared.state.record_trade's convention
    entry_price: float
    quantity: int


def _exit_side_for(symbol: str, position_side: int) -> OrderSide:
    """Matches the same exit-side convention the live exit path uses:
    options are always closed with a SELL; index/equity closes opposite
    the position's own side."""
    is_option = "CE" in symbol or "PE" in symbol
    if is_option:
        return OrderSide.SELL
    return OrderSide.SELL if position_side == 1 else OrderSide.BUY


def compute_reconciliation(
    active_positions: Dict[str, Position],
    broker_positions: List[BrokerPosition],
    order_book: List[OrderBookEntry],
) -> List[ReconciliationResult]:
    """Return a ReconciliationResult for every local position the broker
    no longer shows as open (i.e. it closed while we were disconnected).
    Positions the broker still reports as open are left untouched — the
    caller should not modify them.

    Exit price resolution order:
    1. The broker's order book, if it has a matching COMPLETE fill for
       this symbol on the expected exit side with a real traded price.
    2. Otherwise the local position's stop-loss price, flagged as an
       ESTIMATE via `is_estimate=True` — the caller should log this
       loudly rather than silently trusting it, since the position could
       have hit its target, been closed manually, or gapped through the
       stop-loss to a worse price.
    """
    broker_pos_dict = {p.symbol: p for p in broker_positions}
    results: List[ReconciliationResult] = []

    for sym, local_pos in active_positions.items():
        broker_pos = broker_pos_dict.get(sym)
        if broker_pos is not None and broker_pos.quantity != 0:
            continue  # still open per the broker — nothing to reconcile

        exit_side = _exit_side_for(sym, local_pos.side)

        exit_price = None
        for entry in order_book:
            if (entry.symbol == sym and entry.side == exit_side
                    and entry.status == OrderStatus.COMPLETE and entry.traded_price > 0):
                exit_price = entry.traded_price
                break

        is_estimate = exit_price is None
        if is_estimate:
            exit_price = local_pos.stop_loss

        is_option = "CE" in sym or "PE" in sym
        # `side` only flips the sign for a genuine short position in the
        # underlying -- this system always BUYS options (CE/PE already
        # encodes the directional bet), so a bought option's PnL must never
        # be sign-flipped by `side`. Root-caused 2026-08-03: a stop-loss hit
        # on a PUT was reconciled as a profit.
        pnl = (exit_price - local_pos.entry_price) * local_pos.quantity * (1 if is_option else local_pos.side)
        trade_side = "LONG" if local_pos.side == 1 else "SHORT"
        state_action = "SELL" if is_option else ("SELL" if local_pos.side == 1 else "BUY")

        results.append(ReconciliationResult(
            symbol=sym,
            exit_price=exit_price,
            pnl=pnl,
            is_estimate=is_estimate,
            trade_side=trade_side,
            state_action=state_action,
            entry_price=local_pos.entry_price,
            quantity=local_pos.quantity,
        ))

    return results
