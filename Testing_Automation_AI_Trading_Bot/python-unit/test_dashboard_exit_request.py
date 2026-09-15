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


def test_the_stop_is_cancelled_before_the_position_is_dropped():
    """Dropping first would discard sl_order_id and orphan the stop."""
    src = inspect.getsource(main_module.run_live_bot)
    body = src[src.index("async def close_requested_positions"):]
    body = body[:body.index("async def emergency_flatten_all_positions")]
    assert "_cancel_orphaned_stop(" in body
    assert body.index("_cancel_orphaned_stop(") < body.index("del active_positions[")


def test_the_request_matches_the_traded_contract_not_the_dict_key():
    """active_positions is keyed by the UNDERLYING; matching the key alone
    would never find an option position."""
    src = inspect.getsource(main_module.run_live_bot)
    body = src[src.index("async def close_requested_positions"):]
    assert "p.symbol == wanted or k == wanted" in body


def test_the_position_is_locked_against_the_tick_exit_path():
    src = inspect.getsource(main_module.run_live_bot)
    body = src[src.index("async def close_requested_positions"):]
    assert "pos.is_exiting = True" in body


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
