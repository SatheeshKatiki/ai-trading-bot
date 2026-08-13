"""Regression tests for trading_bot.main._reconcile_broker_state -- the
full WebSocket-reconnect-while-holding-a-position pipeline.

Closes docs/GO_NO_GO_CHECKLIST.md's §2.6 ("WebSocket reconnect/
reconciliation verified against the broker while actually holding a
position"), which had zero test coverage -- and remained completely
untested LIVE too, even after 5 real WebSocket disconnects in a single
session (2026-08-13), none of which happened to coincide with an open
position.

trading_bot/reconciliation.py's compute_reconciliation (the pure
decision logic) already has thorough coverage in test_reconciliation.py,
including the exact "still open on the broker, leave it alone" case.
What was never tested is the surrounding pipeline in
trading_bot.main._reconcile_broker_state (formerly the untestable
sync_broker_state closure, extracted here for exactly this purpose):
the paper-mode short-circuit that protects active_positions from ever
being touched in the mode this system actually runs in, and -- for
live/non-paper mode -- that a real reconciliation result actually gets
applied correctly to active_positions, risk_manager, and portfolio_risk,
not just computed and discarded.
"""
import _bootstrap  # noqa: F401  (side-effect: puts trading-system/ on sys.path)

from brokers.models import Position as BrokerPosition, PositionSide
from shared.exits import Position
from trading_bot.main import _reconcile_broker_state
import trading_bot.main as main_module


def _open_position(symbol="NSE:NIFTY2681824400PE", side=-1, entry_price=90.9, stop_loss=76.8, quantity=260):
    return Position(
        symbol=symbol, side=side, entry_price=entry_price, quantity=quantity,
        entry_time="2026-08-13T13:35:14", highest_price=entry_price,
        lowest_price=entry_price, stop_loss=stop_loss, target=0.0,
    )


class _FakeRiskManager:
    def __init__(self, current_equity=100_000.0):
        self.current_equity = current_equity
        self.recorded_trades = []

    def record_trade(self, trade_record):
        self.recorded_trades.append(trade_record)


class _FakePortfolioRisk:
    def __init__(self):
        self.pnl_updates = []

    def update_pnl(self, pnl, equity):
        self.pnl_updates.append((pnl, equity))


class _FakeBroker:
    def __init__(self, paper_mode, positions=None, order_book=None):
        self.paper_mode = paper_mode
        self._positions = positions if positions is not None else []
        self._order_book = order_book if order_book is not None else []

    def get_positions(self):
        return self._positions

    def get_order_book(self):
        return self._order_book


async def _run(coro):
    return await coro


def _call(broker, active_positions, risk_manager=None, portfolio_risk=None):
    import asyncio
    risk_manager = risk_manager or _FakeRiskManager()
    portfolio_risk = portfolio_risk or _FakePortfolioRisk()
    asyncio.run(_run(_reconcile_broker_state(broker, active_positions, risk_manager, portfolio_risk)))
    return risk_manager, portfolio_risk


# ---------------------------------------------------------------------------
# Paper mode -- the mode this system actually runs in today
# ---------------------------------------------------------------------------

def test_paper_mode_leaves_an_open_position_completely_untouched(monkeypatch):
    """The exact §2.6 scenario in the mode currently live: a WebSocket
    reconnect fires sync_broker_state -> _reconcile_broker_state while a
    real position is open. In paper mode this must be a complete no-op --
    the position, its stop-loss, everything, must come out identical."""
    record_trade_calls = []
    monkeypatch.setattr(main_module, "record_trade", lambda *a, **kw: record_trade_calls.append((a, kw)))
    save_positions_calls = []
    monkeypatch.setattr(main_module, "_save_positions", lambda positions: save_positions_calls.append(dict(positions)))

    position = _open_position()
    active_positions = {position.symbol: position}
    broker = _FakeBroker(paper_mode=True)  # get_positions()/get_order_book() must never even be called

    risk_manager, portfolio_risk = _call(broker, active_positions)

    assert active_positions == {position.symbol: position}
    assert active_positions[position.symbol].stop_loss == 76.8
    assert active_positions[position.symbol].entry_price == 90.9
    assert record_trade_calls == []
    assert save_positions_calls == []
    assert risk_manager.recorded_trades == []
    assert portfolio_risk.pnl_updates == []


def test_paper_mode_never_calls_get_positions_or_get_order_book():
    """Belt-and-suspenders on the exact 2026-08-05 incident this guard
    exists for: FyersBroker.get_positions() unconditionally returns []
    in paper mode, which is what caused the original false-flat bug --
    confirming the paper-mode branch returns before ever calling it."""
    calls = []

    class _TattlingBroker(_FakeBroker):
        def get_positions(self):
            calls.append("get_positions")
            return super().get_positions()

        def get_order_book(self):
            calls.append("get_order_book")
            return super().get_order_book()

    position = _open_position()
    _call(_TattlingBroker(paper_mode=True), {position.symbol: position})

    assert calls == []


# ---------------------------------------------------------------------------
# Non-paper mode -- the full pipeline beyond compute_reconciliation's
# already-tested pure decision logic
# ---------------------------------------------------------------------------

def test_live_mode_position_still_open_on_broker_is_left_alone(monkeypatch):
    """The core §2.6 assertion for a real broker: reconnecting while the
    broker confirms the position is STILL open must leave
    active_positions, its stop-loss, and everything else completely
    unmodified -- not just that compute_reconciliation() returns []
    (already proven in test_reconciliation.py), but that nothing in this
    surrounding pipeline touches state when there's nothing to
    reconcile."""
    monkeypatch.setattr(main_module, "record_trade", lambda *a, **kw: (_ for _ in ()).throw(
        AssertionError("record_trade must not be called -- nothing closed")))
    monkeypatch.setattr(main_module, "_save_positions", lambda positions: (_ for _ in ()).throw(
        AssertionError("_save_positions must not be called -- nothing changed")))

    position = _open_position()
    active_positions = {position.symbol: position}
    broker_position = BrokerPosition(
        symbol=position.symbol, side=PositionSide.SHORT, quantity=260, average_price=90.9,
    )
    broker = _FakeBroker(paper_mode=False, positions=[broker_position])

    risk_manager, portfolio_risk = _call(broker, active_positions)

    assert active_positions == {position.symbol: position}
    assert active_positions[position.symbol].stop_loss == 76.8
    assert risk_manager.recorded_trades == []
    assert portfolio_risk.pnl_updates == []


def test_live_mode_position_closed_while_disconnected_is_fully_applied(monkeypatch):
    """The other half of §2.6: the position genuinely closed while
    disconnected (broker reports flat) -- the reconciliation result must
    be fully applied, not just computed: removed from active_positions,
    persisted, and recorded against both risk_manager and
    portfolio_risk. This is the part test_reconciliation.py's pure-
    function tests structurally cannot cover, since they only assert on
    compute_reconciliation's return value."""
    save_positions_calls = []
    monkeypatch.setattr(main_module, "_save_positions", lambda positions: save_positions_calls.append(dict(positions)))
    record_trade_calls = []
    monkeypatch.setattr(main_module, "record_trade", lambda *a, **kw: record_trade_calls.append((a, kw)))

    position = _open_position(stop_loss=76.8)
    active_positions = {position.symbol: position}
    # Broker reports flat (no open positions at all) -- position closed
    # while disconnected, no order-book fill available -> stop-loss
    # price used as the estimate (see test_reconciliation.py for that
    # decision logic's own coverage).
    broker = _FakeBroker(paper_mode=False, positions=[], order_book=[])

    risk_manager, portfolio_risk = _call(broker, active_positions)

    assert active_positions == {}  # removed
    assert len(save_positions_calls) == 1
    assert position.symbol not in save_positions_calls[0]
    assert len(record_trade_calls) == 1
    assert len(risk_manager.recorded_trades) == 1
    assert risk_manager.recorded_trades[0].exit_price == 76.8  # the SL estimate
    assert len(portfolio_risk.pnl_updates) == 1


def test_a_broker_missing_get_positions_entirely_is_a_safe_noop():
    """Some broker adapters may not implement get_positions() at all --
    must degrade to a no-op, not raise AttributeError mid-reconnect."""
    class _MinimalBroker:
        paper_mode = False

    position = _open_position()
    active_positions = {position.symbol: position}

    _call(_MinimalBroker(), active_positions)

    assert active_positions == {position.symbol: position}
