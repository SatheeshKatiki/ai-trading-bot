"""Regression tests for /api/panic-exit and the emergency-stop flag it sets
(api_bridge.py) -- the kill-switch wiring checked as part of designing a
safe way to test GO_NO_GO_CHECKLIST.md's §2.8 ahead of the next live
session.

Root-cause fix (found live, 2026-08-05): this endpoint only ever called
broker.get_positions()/get_order_book()/place_order() directly -- but
FyersBroker's paper-mode implementation of both `get_positions()` and
`get_order_book()` unconditionally return `[]`, so the endpoint always
reported cancelled=0/closed=0 and never touched anything trading_bot/main.py
actually has open. Worse: main.py runs in a completely separate process
with no shared in-memory state, so even a real broker fill here would leave
main.py's own tracked positions/risk state unaware a panic exit ever
happened. Fixed by adding a cross-process `emergency_stop` flag in
config/settings.json (main.py's on_tick() already reloads that file every
tick for other settings) that main.py checks and acts on directly, with the
broker-level calls now demoted to a best-effort, live-mode-only layer.

Tests here exercise the real FastAPI app via TestClient, with BrokerFactory
mocked and the working directory pointed at an isolated tmp_path so nothing
here ever touches this machine's real config/settings.json -- see
tests/test_order_rate_limit.py's own docstring for the exact incident that
established this rule (a previous test file wrote real rows into the live
state.db because it didn't isolate a disk-backed side effect).
"""
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import _bootstrap  # noqa: F401  (side-effect: puts trading-system/ on sys.path)

from fastapi.testclient import TestClient

from api_bridge import app
from shared.security.sessions import create_session, revoke_session

client = TestClient(app, client=("127.0.0.1", 50000))
remote_client = TestClient(app, client=("203.0.113.5", 51000))


def _auth_headers():
    token = create_session("panic-exit-test-user")
    return token, {"Authorization": f"Bearer {token}"}


def _fake_broker(paper_mode: bool, authenticated: bool = True):
    broker = MagicMock()
    broker.paper_mode = paper_mode
    broker.BROKER_ID = "fyers"
    broker.authenticate.return_value = authenticated
    broker.get_order_book.return_value = [] if paper_mode else []
    broker.get_positions.return_value = [] if paper_mode else []
    return broker


def _write_config(tmp_path, settings=None, active_positions=None):
    config_dir = tmp_path / "config"
    config_dir.mkdir(exist_ok=True)
    (config_dir / "settings.json").write_text(json.dumps(settings or {}), encoding="utf-8")
    (config_dir / "active_positions.json").write_text(
        json.dumps(active_positions if active_positions is not None else {}), encoding="utf-8"
    )


def test_panic_exit_sets_emergency_stop_flag(tmp_path, monkeypatch):
    _write_config(tmp_path, settings={"live_trading_mode": False})
    monkeypatch.chdir(tmp_path)
    token, headers = _auth_headers()
    try:
        with patch("api_bridge.BrokerFactory.get_active_broker", return_value=_fake_broker(paper_mode=True)):
            resp = client.post("/api/panic-exit", headers=headers)
        assert resp.status_code == 200
        saved = json.loads((tmp_path / "config" / "settings.json").read_text(encoding="utf-8"))
        assert saved["emergency_stop"] is True
    finally:
        revoke_session(token)


def test_panic_exit_preserves_other_settings_fields(tmp_path, monkeypatch):
    """_set_emergency_stop must be a targeted merge, not a destructive
    overwrite of the rest of settings.json."""
    _write_config(tmp_path, settings={"live_trading_mode": False, "active_strategy": "ema_rsi", "quantity": 65})
    monkeypatch.chdir(tmp_path)
    token, headers = _auth_headers()
    try:
        with patch("api_bridge.BrokerFactory.get_active_broker", return_value=_fake_broker(paper_mode=True)):
            client.post("/api/panic-exit", headers=headers)
        saved = json.loads((tmp_path / "config" / "settings.json").read_text(encoding="utf-8"))
        assert saved["emergency_stop"] is True
        assert saved["active_strategy"] == "ema_rsi"
        assert saved["quantity"] == 65
    finally:
        revoke_session(token)


def test_panic_exit_reports_currently_open_positions(tmp_path, monkeypatch):
    _write_config(tmp_path, active_positions={
        "NSE:NIFTY50-INDEX": {"symbol": "NSE:NIFTY2681124550CE", "side": 1, "quantity": 65},
    })
    monkeypatch.chdir(tmp_path)
    token, headers = _auth_headers()
    try:
        with patch("api_bridge.BrokerFactory.get_active_broker", return_value=_fake_broker(paper_mode=True)):
            resp = client.post("/api/panic-exit", headers=headers)
        assert resp.status_code == 200
        body = resp.json()
        assert body["flagged_positions"] == ["NSE:NIFTY50-INDEX"]
    finally:
        revoke_session(token)


def test_panic_exit_with_no_open_positions_reports_empty_list(tmp_path, monkeypatch):
    _write_config(tmp_path, active_positions={})
    monkeypatch.chdir(tmp_path)
    token, headers = _auth_headers()
    try:
        with patch("api_bridge.BrokerFactory.get_active_broker", return_value=_fake_broker(paper_mode=True)):
            resp = client.post("/api/panic-exit", headers=headers)
        assert resp.json()["flagged_positions"] == []
    finally:
        revoke_session(token)


def test_panic_exit_broker_auth_failure_does_not_block_the_flag(tmp_path, monkeypatch):
    """The exact bug being fixed: a broker-side problem (unauthenticated,
    unreachable, paper-mode no-ops) must never prevent emergency_stop from
    being set -- that flag is now the primary mechanism, not a bonus."""
    _write_config(tmp_path, active_positions={"NSE:NIFTY50-INDEX": {"symbol": "X", "quantity": 65}})
    monkeypatch.chdir(tmp_path)
    token, headers = _auth_headers()
    try:
        with patch("api_bridge.BrokerFactory.get_active_broker",
                    return_value=_fake_broker(paper_mode=True, authenticated=False)):
            resp = client.post("/api/panic-exit", headers=headers)
        assert resp.status_code == 200
        saved = json.loads((tmp_path / "config" / "settings.json").read_text(encoding="utf-8"))
        assert saved["emergency_stop"] is True
    finally:
        revoke_session(token)


def test_panic_exit_broker_exception_does_not_block_the_flag(tmp_path, monkeypatch):
    _write_config(tmp_path, active_positions={"NSE:NIFTY50-INDEX": {"symbol": "X", "quantity": 65}})
    monkeypatch.chdir(tmp_path)
    token, headers = _auth_headers()
    try:
        with patch("api_bridge.BrokerFactory.get_active_broker", side_effect=RuntimeError("broker down")):
            resp = client.post("/api/panic-exit", headers=headers)
        assert resp.status_code == 200  # must not become a 500
        saved = json.loads((tmp_path / "config" / "settings.json").read_text(encoding="utf-8"))
        assert saved["emergency_stop"] is True
    finally:
        revoke_session(token)


def test_panic_exit_rejects_unauthenticated_requests(tmp_path, monkeypatch):
    _write_config(tmp_path)
    monkeypatch.chdir(tmp_path)
    with patch("api_bridge.BrokerFactory.get_active_broker", return_value=_fake_broker(paper_mode=True)):
        resp = client.post("/api/panic-exit")
    assert resp.status_code == 401


def test_panic_exit_rejects_non_localhost_even_with_valid_auth(tmp_path, monkeypatch):
    _write_config(tmp_path)
    monkeypatch.chdir(tmp_path)
    token, headers = _auth_headers()
    try:
        resp = remote_client.post("/api/panic-exit", headers=headers)
        assert resp.status_code == 403
    finally:
        revoke_session(token)


def test_panic_exit_status_reflects_flag_and_open_positions(tmp_path, monkeypatch):
    _write_config(
        tmp_path,
        settings={"emergency_stop": True},
        active_positions={"NSE:NIFTY50-INDEX": {"symbol": "X"}},
    )
    monkeypatch.chdir(tmp_path)
    token, headers = _auth_headers()
    try:
        resp = client.get("/api/panic-exit/status", headers=headers)
        assert resp.status_code == 200
        body = resp.json()
        assert body["emergency_stop"] is True
        assert body["open_positions"] == ["NSE:NIFTY50-INDEX"]
    finally:
        revoke_session(token)


def test_panic_exit_status_when_never_triggered(tmp_path, monkeypatch):
    _write_config(tmp_path, settings={})
    monkeypatch.chdir(tmp_path)
    token, headers = _auth_headers()
    try:
        resp = client.get("/api/panic-exit/status", headers=headers)
        assert resp.json()["emergency_stop"] is False
    finally:
        revoke_session(token)


def test_panic_exit_clear_resets_the_flag(tmp_path, monkeypatch):
    _write_config(tmp_path, settings={"emergency_stop": True, "active_strategy": "ema_rsi"})
    monkeypatch.chdir(tmp_path)
    token, headers = _auth_headers()
    try:
        resp = client.post("/api/panic-exit/clear", headers=headers)
        assert resp.status_code == 200
        saved = json.loads((tmp_path / "config" / "settings.json").read_text(encoding="utf-8"))
        assert saved["emergency_stop"] is False
        assert saved["active_strategy"] == "ema_rsi"  # untouched
    finally:
        revoke_session(token)


def test_panic_exit_clear_rejects_non_localhost(tmp_path, monkeypatch):
    _write_config(tmp_path, settings={"emergency_stop": True})
    monkeypatch.chdir(tmp_path)
    token, headers = _auth_headers()
    try:
        resp = remote_client.post("/api/panic-exit/clear", headers=headers)
        assert resp.status_code == 403
        saved = json.loads((tmp_path / "config" / "settings.json").read_text(encoding="utf-8"))
        assert saved["emergency_stop"] is True  # must NOT have been cleared
    finally:
        revoke_session(token)


def test_panic_exit_clear_rejects_unauthenticated_requests(tmp_path, monkeypatch):
    _write_config(tmp_path, settings={"emergency_stop": True})
    monkeypatch.chdir(tmp_path)
    resp = client.post("/api/panic-exit/clear")
    assert resp.status_code == 401
