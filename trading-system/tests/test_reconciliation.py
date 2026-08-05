"""Regression tests for broker-reconnect position reconciliation
(trading_bot/reconciliation.py).

Root-cause fix (production-readiness audit finding): the reconciliation
logic that runs after a WebSocket reconnect — deciding whether a locally
tracked position actually closed while disconnected, and at what real
price — was previously buried in a nested closure inside
`trading_bot.main.run_live_bot` and had zero test coverage, despite
being exactly the kind of code that only ever runs during a real network
outage (i.e. the worst possible time to discover a bug in it). It has
since been extracted into `trading_bot/reconciliation.py` as a pure
function with no I/O, so it can be exercised directly here against real
`Position`/`OrderBookEntry`/broker-`Position` objects — not mocks of the
decision logic itself.
"""
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from brokers import OrderSide, OrderStatus
from brokers.models import OrderBookEntry, OrderType, Position as BrokerPosition, PositionSide
from shared.exits import Position
from trading_bot.reconciliation import compute_reconciliation


def _local_long(symbol="NSE:NIFTY25AUG24000CE", entry_price=100.0, quantity=65, stop_loss=90.0):
    return Position(
        symbol=symbol, side=1, entry_price=entry_price, quantity=quantity,
        entry_time="2026-08-02T10:00:00", highest_price=entry_price,
        lowest_price=entry_price, stop_loss=stop_loss, target=entry_price * 1.2,
    )


def _local_short(symbol="NSE:NIFTY50-INDEX", entry_price=24000.0, quantity=25, stop_loss=24100.0):
    return Position(
        symbol=symbol, side=-1, entry_price=entry_price, quantity=quantity,
        entry_time="2026-08-02T10:00:00", highest_price=entry_price,
        lowest_price=entry_price, stop_loss=stop_loss, target=entry_price * 0.98,
    )


def _order_book_fill(symbol, side, traded_price, status=OrderStatus.COMPLETE):
    return OrderBookEntry(
        order_id="ORD1", symbol=symbol, side=side, quantity=65, price=traded_price,
        status=status, order_type=OrderType.MARKET, traded_price=traded_price,
    )


def test_position_still_open_on_broker_is_not_reconciled():
    """Broker still reports the position open — must be left completely alone."""
    local = _local_long()
    active_positions = {local.symbol: local}
    broker_positions = [BrokerPosition(symbol=local.symbol, side=PositionSide.LONG, quantity=65, average_price=100.0)]

    results = compute_reconciliation(active_positions, broker_positions, order_book=[])

    assert results == []
    assert local.symbol in active_positions  # caller only deletes what's returned


def test_closed_option_position_resolves_real_fill_price_from_order_book():
    """The common case: option closed while disconnected, order book has the real fill."""
    local = _local_long(symbol="NSE:NIFTY25AUG24000CE", entry_price=100.0, quantity=65, stop_loss=90.0)
    active_positions = {local.symbol: local}
    # Broker no longer lists it at all (fully squared off).
    order_book = [_order_book_fill(local.symbol, OrderSide.SELL, traded_price=135.0)]

    results = compute_reconciliation(active_positions, broker_positions=[], order_book=order_book)

    assert len(results) == 1
    r = results[0]
    assert r.symbol == local.symbol
    assert r.is_estimate is False
    assert r.exit_price == 135.0
    assert r.pnl == (135.0 - 100.0) * 65 * 1  # long: (exit - entry) * qty * side
    assert r.state_action == "SELL"  # options always close with a SELL
    assert r.trade_side == "LONG"


def test_closed_put_option_position_pnl_is_not_sign_flipped():
    """Regression test for a real bug (root-caused 2026-08-03): a bought PUT
    uses side=-1 to encode "bearish bet", not "short the contract" -- this
    system only ever BUYS options, so PnL must never be sign-flipped by
    `side` for an option position, unlike a genuine short index/equity
    position. Before the fix, this exact scenario (premium fell, a bought
    PUT should show a LOSS) computed a positive PnL instead -- a stop-loss
    hit was once literally recorded as a profit because of this.
    """
    local = Position(
        symbol="NSE:NIFTY26AUG24600PE", side=-1, entry_price=75.05, quantity=65,
        entry_time="2026-08-03T10:34:10", highest_price=75.05,
        lowest_price=75.05, stop_loss=74.712275, target=77.67675,
    )
    active_positions = {local.symbol: local}
    # Premium fell (as it did for real that day) -- a bought PUT loses value
    # right alongside it, exactly like a bought CALL would.
    order_book = [_order_book_fill(local.symbol, OrderSide.SELL, traded_price=59.60)]

    results = compute_reconciliation(active_positions, broker_positions=[], order_book=order_book)

    assert len(results) == 1
    r = results[0]
    assert r.exit_price == 59.60
    assert r.pnl == (59.60 - 75.05) * 65 * 1  # option: side never flips the sign
    assert r.pnl < 0  # premium fell -> a bought PUT must show a loss, not a gain
    assert r.state_action == "SELL"
    assert r.trade_side == "SHORT"  # trade_side label still reflects the directional bet


def test_closed_put_option_position_stop_loss_estimate_is_a_loss():
    """The exact real-world scenario: no order-book fill found, falls back to
    the stop_loss estimate. A stop-loss exists to cap a loss -- it must never
    be able to compute as a profit."""
    local = Position(
        symbol="NSE:NIFTY26AUG24600PE", side=-1, entry_price=75.05, quantity=65,
        entry_time="2026-08-03T10:34:10", highest_price=75.05,
        lowest_price=75.05, stop_loss=74.712275, target=77.67675,
    )
    active_positions = {local.symbol: local}

    results = compute_reconciliation(active_positions, broker_positions=[], order_book=[])

    assert len(results) == 1
    r = results[0]
    assert r.is_estimate is True
    assert r.exit_price == 74.712275
    assert r.pnl < 0  # a stop-loss hit can never be a profit


def test_closed_short_index_position_uses_buy_exit_side():
    """Short equity/index positions close with a BUY, not a SELL — must not be confused with the option convention."""
    local = _local_short(symbol="NSE:NIFTY50-INDEX", entry_price=24000.0, quantity=25, stop_loss=24100.0)
    active_positions = {local.symbol: local}
    # A SELL fill for this symbol must NOT match (wrong side for closing a short) —
    # only the BUY fill should be picked up.
    order_book = [
        _order_book_fill(local.symbol, OrderSide.SELL, traded_price=23000.0),
        _order_book_fill(local.symbol, OrderSide.BUY, traded_price=23950.0),
    ]

    results = compute_reconciliation(active_positions, broker_positions=[], order_book=order_book)

    assert len(results) == 1
    r = results[0]
    assert r.exit_price == 23950.0
    assert r.pnl == (23950.0 - 24000.0) * 25 * -1  # short: negative side flips the sign
    assert r.pnl > 0  # price dropped after shorting -> profit
    assert r.state_action == "BUY"
    assert r.trade_side == "SHORT"


def test_no_matching_order_book_fill_falls_back_to_stop_loss_as_estimate():
    """No matching fill anywhere in the order book (e.g. rolled off, or closed
    by something outside this order book) -- must fall back to stop_loss and
    flag it as an estimate rather than silently treating it as fact."""
    local = _local_long(symbol="NSE:NIFTY25AUG24000CE", entry_price=100.0, quantity=65, stop_loss=85.0)
    active_positions = {local.symbol: local}

    # Order book has fills, but none for this symbol/side/status combination.
    order_book = [
        _order_book_fill("NSE:NIFTY25AUG24100CE", OrderSide.SELL, traded_price=50.0),
        _order_book_fill(local.symbol, OrderSide.BUY, traded_price=100.0),          # wrong side (that's the entry, not exit)
        _order_book_fill(local.symbol, OrderSide.SELL, traded_price=0.0),           # zero traded_price must be rejected
        _order_book_fill(local.symbol, OrderSide.SELL, 130.0, status=OrderStatus.PENDING),  # not COMPLETE
    ]

    results = compute_reconciliation(active_positions, broker_positions=[], order_book=order_book)

    assert len(results) == 1
    r = results[0]
    assert r.is_estimate is True
    assert r.exit_price == 85.0  # the stop_loss price
    assert r.pnl == (85.0 - 100.0) * 65 * 1


def test_broker_reports_zero_quantity_counts_as_flat():
    """Broker still lists the symbol but with quantity 0 -- must be treated
    the same as not being listed at all."""
    local = _local_long(symbol="NSE:NIFTY25AUG24000CE", entry_price=100.0, quantity=65, stop_loss=90.0)
    active_positions = {local.symbol: local}
    broker_positions = [BrokerPosition(symbol=local.symbol, side=PositionSide.LONG, quantity=0, average_price=100.0)]
    order_book = [_order_book_fill(local.symbol, OrderSide.SELL, traded_price=110.0)]

    results = compute_reconciliation(active_positions, broker_positions, order_book)

    assert len(results) == 1
    assert results[0].exit_price == 110.0


def test_mixed_open_and_closed_positions_only_reconciles_the_closed_one():
    still_open = _local_long(symbol="NSE:NIFTY25AUG24000CE", entry_price=100.0, quantity=65, stop_loss=90.0)
    closed = _local_short(symbol="NSE:NIFTY50-INDEX", entry_price=24000.0, quantity=25, stop_loss=24100.0)
    active_positions = {still_open.symbol: still_open, closed.symbol: closed}

    broker_positions = [BrokerPosition(symbol=still_open.symbol, side=PositionSide.LONG, quantity=65, average_price=100.0)]
    order_book = [_order_book_fill(closed.symbol, OrderSide.BUY, traded_price=23900.0)]

    results = compute_reconciliation(active_positions, broker_positions, order_book)

    assert len(results) == 1
    assert results[0].symbol == closed.symbol
    # both positions remain in the dict -- compute_reconciliation never mutates its input
    assert set(active_positions.keys()) == {still_open.symbol, closed.symbol}


def test_empty_active_positions_returns_no_results():
    assert compute_reconciliation({}, broker_positions=[], order_book=[]) == []


def test_option_position_keyed_by_underlying_reconciles_against_its_own_symbol():
    """Root-cause regression (found live, 2026-08-05): main.py deliberately
    keys `active_positions` by the underlying (e.g. NSE:NIFTY50-INDEX) for
    option strategies, NOT by the actual traded option symbol -- see the
    "We MUST key active_positions by the base symbol" comment at its entry
    sites. Every prior test above happened to use the same string for both
    the dict key and Position.symbol, masking a real bug: this function
    used to reconcile against the dict key instead of `local_pos.symbol`,
    so it checked whether the *underlying index* was flat at the broker
    (trivially always true -- this system never holds the index itself),
    causing every option position to be force-closed as "broker flat" the
    moment reconciliation ran, regardless of the option's real state."""
    underlying_key = "NSE:NIFTY50-INDEX"
    option_symbol = "NSE:NIFTY2681123750CE"
    local = Position(
        symbol=option_symbol, side=1, entry_price=898.4, quantity=65,
        entry_time="2026-08-05T10:05:07", highest_price=898.4,
        lowest_price=898.4, stop_loss=894.3572, target=929.844,
    )
    active_positions = {underlying_key: local}
    # The option itself is still genuinely open at the broker.
    broker_positions = [BrokerPosition(symbol=option_symbol, side=PositionSide.LONG, quantity=65, average_price=898.4)]

    results = compute_reconciliation(active_positions, broker_positions, order_book=[])

    assert results == []  # must be left alone -- the option is still open
    assert underlying_key in active_positions


def test_option_position_keyed_by_underlying_resolves_and_reports_local_key():
    """Same key/symbol split as above, but the option really has closed --
    the result must reconcile against/report the real option symbol while
    `local_key` carries the dict key the caller needs for deletion."""
    underlying_key = "NSE:NIFTY50-INDEX"
    option_symbol = "NSE:NIFTY2681123750CE"
    local = Position(
        symbol=option_symbol, side=1, entry_price=898.4, quantity=65,
        entry_time="2026-08-05T10:05:07", highest_price=898.4,
        lowest_price=898.4, stop_loss=894.3572, target=929.844,
    )
    active_positions = {underlying_key: local}
    order_book = [_order_book_fill(option_symbol, OrderSide.SELL, traded_price=910.0)]

    results = compute_reconciliation(active_positions, broker_positions=[], order_book=order_book)

    assert len(results) == 1
    r = results[0]
    assert r.symbol == option_symbol       # the real traded instrument
    assert r.local_key == underlying_key   # what the caller must delete from active_positions
    assert r.exit_price == 910.0
    assert r.is_estimate is False
