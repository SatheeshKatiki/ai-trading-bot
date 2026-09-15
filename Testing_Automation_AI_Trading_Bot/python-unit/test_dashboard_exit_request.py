"""The dashboard's per-position EXIT must reach the engine (2026-09-16).

The owner exits one live position from the dashboard. Before this, the UI
POSTed straight to /api/order/execute -- which places a counter-order at the
broker and nothing more. api_bridge and main.py are SEPARATE processes sharing
only files, so the engine never learned the position was gone: it kept
managing it, would try to exit it again (a double sell), and left its
exchange-resident stop-loss working against a position no longer held. On a
bought option that stop is a SELL, so triggering it opens a naked short.

The exit now travels as a request file the engine consumes:

    UI -> POST /api/positions/exit
            1. place the counter-order (same path as any manual order)
            2. append the symbol to config/exit_requests.json
    main.py on_tick -> _take_exit_requests()  (read AND clear)
                    -> close_requested_positions(): cancel the stop, record
                       the trade, drop the position

Ordering is deliberate: placing first and queueing second means a failure
after the fill is recovered by the 60s reconciler, whereas queueing first and
failing to place would make the engine forget a position the broker still
holds.

close_requested_positions is a closure inside run_live_bot -- like
emergency_flatten_all_positions it cannot be imported, so its wiring is
source-asserted here and its behaviour is covered by the pieces it reuses
(compute_reconciliation, _cancel_orphaned_stop), which are tested directly in
test_reconciliation.py and test_main_reconcile_broker_state.py.
"""

from __future__ import annotations

import inspect
import json

import pytest

import _bootstrap  # noqa: F401  (side-effect: puts trading-system/ on sys.path)

import trading_bot.main as main_module


# ---------------------------------------------------------------------------
# _take_exit_requests -- read AND clear, exactly once
# ---------------------------------------------------------------------------

def test_a_request_is_read_and_consumed_exactly_once(tmp_path, monkeypatch):
    path = tmp_path / "exit_requests.json"
    path.write_text(json.dumps(["NSE:NIFTY2681824400PE"]), encoding="utf-8")
    monkeypatch.setattr(main_module, "_EXIT_REQUESTS_PATH", path)

    assert main_module._take_exit_requests() == ["NSE:NIFTY2681824400PE"]
    assert not path.exists(), "the file must be cleared by its consumer"
    assert main_module._take_exit_requests() == [], "a request must never be acted on twice"


def test_several_requests_come_back_together(tmp_path, monkeypatch):
    path = tmp_path / "exit_requests.json"
    path.write_text(json.dumps(["A-CE", "B-PE"]), encoding="utf-8")
    monkeypatch.setattr(main_module, "_EXIT_REQUESTS_PATH", path)

    assert main_module._take_exit_requests() == ["A-CE", "B-PE"]


def test_no_file_is_the_normal_case(tmp_path, monkeypatch):
    monkeypatch.setattr(main_module, "_EXIT_REQUESTS_PATH", tmp_path / "absent.json")
    assert main_module._take_exit_requests() == []


def test_a_corrupt_request_file_never_breaks_the_tick_loop(tmp_path, monkeypatch):
    """This runs inside on_tick -- it must fail quiet, not raise."""
    path = tmp_path / "exit_requests.json"
    path.write_text("{not json", encoding="utf-8")
    monkeypatch.setattr(main_module, "_EXIT_REQUESTS_PATH", path)

    assert main_module._take_exit_requests() == []


def test_blank_entries_are_ignored(tmp_path, monkeypatch):
    path = tmp_path / "exit_requests.json"
    path.write_text(json.dumps(["", "NSE:NIFTY2681824400PE", None]), encoding="utf-8")
    monkeypatch.setattr(main_module, "_EXIT_REQUESTS_PATH", path)

    assert main_module._take_exit_requests() == ["NSE:NIFTY2681824400PE"]


# ---------------------------------------------------------------------------
# Wiring inside run_live_bot
# ---------------------------------------------------------------------------

def test_the_tick_loop_consumes_exit_requests():
    src = inspect.getsource(main_module.run_live_bot)
    assert "exit_requests = _take_exit_requests()" in src
    assert "await close_requested_positions(exit_requests)" in src


def test_an_exit_request_is_honoured_even_when_the_engine_is_halted():
    """Halting must not strand the cleanup of a position already closed."""
    src = inspect.getsource(main_module.run_live_bot)
    consume = src.index("exit_requests = _take_exit_requests()")
    halt = src.index('if not settings.get("is_active", True):')
    assert consume < halt, "exit requests must be handled before the is_active halt"


# ---------------------------------------------------------------------------
# _close_requested_positions -- exercised for real
#
# Extracted out of run_live_bot's closure for exactly this reason: as a nested
# function it could only ever be source-asserted. Same split as
# sync_broker_state / _reconcile_broker_state.
# ---------------------------------------------------------------------------

class _Quote:
    def __init__(self, ltp):
        self.ltp = ltp


class _ExitBroker:
    def __init__(self, quotes=None, order_status=None):
        self.paper_mode = False
        self._quotes = quotes or {}
        self._order_status = order_status
        self.cancelled = []

    def get_market_data(self, symbols):
        return {s: _Quote(self._quotes[s]) for s in symbols if s in self._quotes}

    def get_order_status(self, order_id):
        return self._order_status

    def cancel_order(self, order_id):
        self.cancelled.append(order_id)
        return {"status": "ok"}


class _Risk:
    def __init__(self):
        self.current_equity = 100_000.0
        self.daily_pnl = 0.0
        self.recorded_trades = []

    def record_trade(self, t):
        self.recorded_trades.append(t)


class _Portfolio:
    def __init__(self):
        self.pnl_updates = []

    def update_pnl(self, pnl, equity):
        self.pnl_updates.append((pnl, equity))


def _position(symbol="NSE:NIFTY2681824400PE", entry=90.9, stop=76.8, qty=260):
    from shared.exits import Position
    pos = Position(symbol=symbol, side=-1, entry_price=entry, quantity=qty,
                   entry_time="2026-09-16T10:00:00", highest_price=entry,
                   lowest_price=entry, stop_loss=stop, target=0.0)
    pos.sl_order_id = "SL-1"
    return pos


def _run_close(broker, active_positions, symbols, monkeypatch, risk=None, portfolio=None):
    import asyncio
    monkeypatch.setattr(main_module, "record_trade", lambda *a, **kw: None)
    monkeypatch.setattr(main_module, "update_equity", lambda *a, **kw: None)
    monkeypatch.setattr(main_module, "_save_positions", lambda positions: None)
    monkeypatch.setattr(main_module, "alerter",
                        type("_A", (), {"send_alert": staticmethod(lambda m: None)})())
    risk = risk or _Risk()
    portfolio = portfolio or _Portfolio()
    asyncio.run(main_module._close_requested_positions(
        broker, active_positions, risk, portfolio, symbols))
    return risk, portfolio


def test_the_stop_is_cancelled_and_the_position_dropped(monkeypatch):
    """Dropping first would discard sl_order_id and orphan the stop."""
    pos = _position()
    active = {pos.symbol: pos}
    broker = _ExitBroker(quotes={pos.symbol: 120.0})

    risk, _ = _run_close(broker, active, [pos.symbol], monkeypatch)

    assert broker.cancelled == ["SL-1"], "the exchange stop must be cancelled"
    assert active == {}, "the position must be dropped from the book"
    assert len(risk.recorded_trades) == 1, "the exit must be recorded once"


def test_it_matches_the_traded_contract_not_the_dict_key(monkeypatch):
    """active_positions is keyed by the UNDERLYING; matching the key alone
    would never find an option position."""
    pos = _position(symbol="NSE:NIFTY2681824400PE")
    active = {"NSE:NIFTY50-INDEX": pos}          # keyed by the underlying
    broker = _ExitBroker(quotes={pos.symbol: 120.0})

    _run_close(broker, active, ["NSE:NIFTY2681824400PE"], monkeypatch)

    assert active == {}, "the request names the contract, the dict is keyed by the index"
    assert broker.cancelled == ["SL-1"]


def test_an_unknown_symbol_is_ignored(monkeypatch):
    """Already closed elsewhere -- must be a quiet no-op, never a crash."""
    pos = _position()
    active = {pos.symbol: pos}
    broker = _ExitBroker(quotes={pos.symbol: 120.0})

    risk, _ = _run_close(broker, active, ["SOMETHING-ELSE-CE"], monkeypatch)

    assert active == {pos.symbol: pos}
    assert broker.cancelled == []
    assert risk.recorded_trades == []


def test_a_missing_quote_still_closes_the_position(monkeypatch):
    """No live price is not a reason to keep managing a position that is gone;
    compute_reconciliation falls back to the stop as a flagged ESTIMATE."""
    pos = _position()
    active = {pos.symbol: pos}
    broker = _ExitBroker(quotes={})              # no quote available

    risk, _ = _run_close(broker, active, [pos.symbol], monkeypatch)

    assert active == {}
    assert len(risk.recorded_trades) == 1


def test_a_broker_that_raises_on_quotes_does_not_abort_the_close(monkeypatch):
    class _Angry(_ExitBroker):
        def get_market_data(self, symbols):
            raise RuntimeError("quote feed down")

    pos = _position()
    active = {pos.symbol: pos}
    broker = _Angry()

    _run_close(broker, active, [pos.symbol], monkeypatch)

    assert active == {}, "the book must still be closed"
    assert broker.cancelled == ["SL-1"]


def test_the_position_is_locked_against_the_tick_exit_path():
    """is_exiting is set before any await, so on_tick cannot race this."""
    src = inspect.getsource(main_module._close_requested_positions)
    assert "pos.is_exiting = True" in src
    assert src.index("pos.is_exiting = True") < src.index("await asyncio.to_thread")


def test_run_live_bot_delegates_to_the_module_level_routine():
    src = inspect.getsource(main_module.run_live_bot)
    assert "await _close_requested_positions(" in src


# ---------------------------------------------------------------------------
# POST /api/positions/exit -- the endpoint itself
# ---------------------------------------------------------------------------

def _client(tmp_path, monkeypatch, execute=None):
    """A TestClient whose order placement is stubbed, in an isolated cwd.

    /api/positions/exit sits behind the auth middleware, so the client carries
    a real session token. execute_order is stubbed because the real one reaches
    BrokerFactory -- what is under test here is the endpoint's own contract:
    which side it exits on, and that the engine gets told.
    """
    from fastapi.testclient import TestClient

    import api_bridge
    from api_bridge import app
    from shared.security.sessions import create_session

    monkeypatch.chdir(tmp_path)
    (tmp_path / "config").mkdir(exist_ok=True)

    placed = []

    async def _default(req, request):
        placed.append(req)
        return {"status": "success", "order_id": "MOCK-1"}

    monkeypatch.setattr(api_bridge, "execute_order", execute or _default)

    token = create_session("exit-endpoint-test-user")
    client = TestClient(app, client=("127.0.0.1", 50001))
    client.headers.update({"Authorization": f"Bearer {token}"})
    return client, placed, tmp_path / "config" / "exit_requests.json"


def test_a_long_is_exited_with_a_sell_and_the_engine_is_told(tmp_path, monkeypatch):
    client, placed, requests_file = _client(tmp_path, monkeypatch)

    res = client.post("/api/positions/exit",
                      json={"symbol": "NSE:NIFTY2681824400PE", "quantity": 65, "side": "BUY"})

    assert res.status_code == 200
    assert [p.action for p in placed] == ["SELL"]
    assert [p.symbol for p in placed] == ["NSE:NIFTY2681824400PE"]
    assert json.loads(requests_file.read_text(encoding="utf-8")) == ["NSE:NIFTY2681824400PE"]


def test_a_short_is_exited_with_a_buy(tmp_path, monkeypatch):
    client, placed, _ = _client(tmp_path, monkeypatch)

    client.post("/api/positions/exit",
                json={"symbol": "NSE:BANKNIFTY2681852000CE", "quantity": 30, "side": "SELL"})

    assert [p.action for p in placed] == ["BUY"]


def test_nothing_is_queued_when_the_order_could_not_be_placed(tmp_path, monkeypatch):
    """Placing comes FIRST on purpose.

    If the request were queued and the order then failed, the engine would drop
    a position the broker still holds -- unrecoverable without manual help. The
    other way round, the 60s reconciler catches it.
    """
    async def _refuse(req, request):
        raise RuntimeError("broker rejected the order")

    client, _placed, requests_file = _client(tmp_path, monkeypatch, execute=_refuse)

    with pytest.raises(RuntimeError):
        client.post("/api/positions/exit",
                    json={"symbol": "NSE:NIFTY2681824400PE", "quantity": 65, "side": "BUY"})

    assert not requests_file.exists(), "a failed exit must not tell the engine the position is gone"


def test_two_exits_queue_both_symbols(tmp_path, monkeypatch):
    client, _placed, requests_file = _client(tmp_path, monkeypatch)

    client.post("/api/positions/exit", json={"symbol": "A-CE", "quantity": 1, "side": "BUY"})
    client.post("/api/positions/exit", json={"symbol": "B-PE", "quantity": 1, "side": "BUY"})

    assert json.loads(requests_file.read_text(encoding="utf-8")) == ["A-CE", "B-PE"]


def test_the_same_symbol_is_never_queued_twice(tmp_path, monkeypatch):
    """A double-click must not make the engine act on it twice."""
    client, _placed, requests_file = _client(tmp_path, monkeypatch)

    client.post("/api/positions/exit", json={"symbol": "A-CE", "quantity": 1, "side": "BUY"})
    client.post("/api/positions/exit", json={"symbol": "A-CE", "quantity": 1, "side": "BUY"})

    assert json.loads(requests_file.read_text(encoding="utf-8")) == ["A-CE"]


def test_the_endpoint_is_localhost_only(tmp_path, monkeypatch):
    """It places real orders -- it must not be reachable from the network."""
    from fastapi.testclient import TestClient

    import api_bridge
    from api_bridge import app
    from shared.security.sessions import create_session

    monkeypatch.chdir(tmp_path)
    (tmp_path / "config").mkdir(exist_ok=True)
    monkeypatch.setattr(api_bridge, "execute_order",
                        lambda req, request: (_ for _ in ()).throw(AssertionError("must not place")))

    token = create_session("exit-endpoint-remote-user")
    remote = TestClient(app, client=("10.0.0.9", 50002))
    remote.headers.update({"Authorization": f"Bearer {token}"})

    res = remote.post("/api/positions/exit",
                      json={"symbol": "A-CE", "quantity": 1, "side": "BUY"})

    assert res.status_code == 403
    assert not (tmp_path / "config" / "exit_requests.json").exists()
