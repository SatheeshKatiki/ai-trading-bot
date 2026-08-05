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
from typing import Dict, List, Optional

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
    local_key: str      # active_positions dict key (may differ from `symbol` —
                         # see compute_reconciliation's docstring); the caller
                         # must use THIS, not `symbol`, to delete from that dict


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
    live_prices: Optional[Dict[str, float]] = None,
) -> List[ReconciliationResult]:
    """Return a ReconciliationResult for every local position the broker
    no longer shows as open (i.e. it closed while we were disconnected).
    Positions the broker still reports as open are left untouched — the
    caller should not modify them.

    `live_prices` (optional, keyed by the traded symbol) is a second exit
    price source, checked after the order book but before the stop-loss
    estimate fallback. Added to let this same, already-well-tested pure
    function double as the decision logic for an emergency force-close
    (`main.py`'s `_emergency_flatten_all_positions`, wired to the
    dashboard's panic-exit button) — that caller passes `broker_positions=[]`
    and `order_book=[]` (there's nothing to reconcile against, every open
    position must close) along with a fresh live quote per symbol, so it
    gets a real market exit price instead of falling all the way back to
    the stop-loss estimate meant for "we don't know what really happened
    while disconnected". Omitting `live_prices` (or leaving a symbol out of
    it) preserves the exact prior behavior for real reconciliation callers.

    `active_positions` is keyed by the *underlying* symbol (e.g.
    ``NSE:NIFTY50-INDEX``), not the actual traded instrument — main.py's
    entry path deliberately keys it that way so on_tick's underlying-price
    stream can find the position (see the "We MUST key active_positions by
    the base symbol" comment at its entry sites). The real traded
    instrument for an option strategy lives in ``local_pos.symbol`` (e.g.
    ``NSE:NIFTY2681123750CE``) and can differ from the dict key. Root-cause
    fix (found live, 2026-08-05): this function used to reconcile against
    `sym` (the dict key) instead of `local_pos.symbol`, so for every option
    position it checked whether the *underlying index* was flat at the
    broker/order-book — which it always trivially is, since this system
    never holds a position in the underlying itself — causing every option
    position to look permanently "closed" the moment reconciliation ran.

    Exit price resolution order:
    1. The broker's order book, if it has a matching COMPLETE fill for
       the traded instrument on the expected exit side with a real traded
       price. Not an estimate.
    2. A fresh live quote from `live_prices`, if the caller supplied one
       for this symbol. Not an estimate — it's real market data, just not
       a broker-confirmed fill.
    3. Otherwise the local position's stop-loss price, flagged as an
       ESTIMATE via `is_estimate=True` — the caller should log this
       loudly rather than silently trusting it, since the position could
       have hit its target, been closed manually, or gapped through the
       stop-loss to a worse price.
    """
    broker_pos_dict = {p.symbol: p for p in broker_positions}
    live_prices = live_prices or {}
    results: List[ReconciliationResult] = []

    for local_key, local_pos in active_positions.items():
        traded_symbol = local_pos.symbol
        broker_pos = broker_pos_dict.get(traded_symbol)
        if broker_pos is not None and broker_pos.quantity != 0:
            continue  # still open per the broker — nothing to reconcile

        exit_side = _exit_side_for(traded_symbol, local_pos.side)

        exit_price = None
        for entry in order_book:
            if (entry.symbol == traded_symbol and entry.side == exit_side
                    and entry.status == OrderStatus.COMPLETE and entry.traded_price > 0):
                exit_price = entry.traded_price
                break

        is_estimate = False
        if exit_price is None:
            live_price = live_prices.get(traded_symbol)
            if live_price is not None and live_price > 0:
                exit_price = live_price
            else:
                is_estimate = True
                exit_price = local_pos.stop_loss

        is_option = "CE" in traded_symbol or "PE" in traded_symbol
        # `side` only flips the sign for a genuine short position in the
        # underlying -- this system always BUYS options (CE/PE already
        # encodes the directional bet), so a bought option's PnL must never
        # be sign-flipped by `side`. Root-caused 2026-08-03: a stop-loss hit
        # on a PUT was reconciled as a profit.
        pnl = (exit_price - local_pos.entry_price) * local_pos.quantity * (1 if is_option else local_pos.side)
        trade_side = "LONG" if local_pos.side == 1 else "SHORT"
        state_action = "SELL" if is_option else ("SELL" if local_pos.side == 1 else "BUY")

        results.append(ReconciliationResult(
            symbol=traded_symbol,
            exit_price=exit_price,
            pnl=pnl,
            is_estimate=is_estimate,
            trade_side=trade_side,
            state_action=state_action,
            entry_price=local_pos.entry_price,
            quantity=local_pos.quantity,
            local_key=local_key,
        ))

    return results
