"""Regression tests for /api/order/execute's rate limiting.

Root-cause fix (production-readiness load-testing finding): ORDER_LIMITER
already gates every order the autonomous engine places on its own
(trading_bot/main.py, trading_bot/iceberg_manager.py), but the manual/
dashboard order-execution endpoint had no rate limit at all — confirmed
via a live load test (40 concurrent requests all succeeded with zero
throttling). A runaway frontend retry loop or a script hammering this
route could fire unbounded real orders once live_trading_mode is on.

These tests exercise the real FastAPI app via TestClient (not a running
server), with BrokerFactory/ORDER_LIMITER mocked so nothing ever reaches
a real broker or the real settings.json — never flip a shared, disk-
backed live_trading_mode flag just to test this, since other processes
on this machine may be reading that same file.

Root-cause fix (found live, 2026-08-05): the endpoint's own
`record_trade()` call was NOT mocked here, so every run of this file
wrote a real "NIFTY-RATELIMIT-TEST" row into the actual, disk-backed
`state.db` — shared.state resolves that path relative to its own
module file, not any test fixture, so there is no isolated test DB to
redirect to. This polluted the live paper-trading validation window's
trade history every single time the suite ran on this machine. Now
mocked like every other side effect here.
"""
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import _bootstrap  # noqa: F401  (side-effect: puts trading-system/ on sys.path)

from fastapi.testclient import TestClient

from api_bridge import app
from shared.security.sessions import create_session, revoke_session

# request.client.host must be a localhost variant to pass this endpoint's
# defense-in-depth IP check (on top of session auth) — TestClient defaults
# to host "testclient", which would otherwise 403 before reaching the code
# under test.
client = TestClient(app, client=("127.0.0.1", 50000))

ORDER_PAYLOAD = {"symbol": "NIFTY-RATELIMIT-TEST", "action": "BUY", "quantity": 1}


def _auth_headers():
    token = create_session("rate-limit-test-user")
    return token, {"Authorization": f"Bearer {token}"}


def _fake_broker(paper_mode: bool):
    broker = MagicMock()
    broker.paper_mode = paper_mode
    broker.BROKER_ID = "fyers"
    broker.place_order.return_value = MagicMock(order_id="TEST-ORDER-1", price=100.0, message="ok")
    return broker


def test_paper_mode_order_ignores_rate_limiter_entirely():
    """Paper orders never reach a real broker API, so the limiter must
    never even be consulted for them."""
    token, headers = _auth_headers()
    try:
        with patch("api_bridge.BrokerFactory.get_active_broker", return_value=_fake_broker(paper_mode=True)), \
             patch("api_bridge._load_config_settings", return_value={"live_trading_mode": False}), \
             patch("api_bridge.ORDER_LIMITER.allow") as mock_allow, \
             patch("shared.state.record_trade") as mock_record_trade:
            resp = client.post("/api/order/execute", json=ORDER_PAYLOAD, headers=headers)
            assert resp.status_code == 200
            mock_allow.assert_not_called()
            mock_record_trade.assert_called_once()
    finally:
        revoke_session(token)


def test_live_mode_order_allowed_by_limiter_succeeds():
    token, headers = _auth_headers()
    try:
        with patch("api_bridge.BrokerFactory.get_active_broker", return_value=_fake_broker(paper_mode=False)), \
             patch("api_bridge._load_config_settings", return_value={"live_trading_mode": True}), \
             patch("api_bridge.ORDER_LIMITER.allow", return_value=True) as mock_allow, \
             patch("shared.state.record_trade") as mock_record_trade:
            resp = client.post("/api/order/execute", json=ORDER_PAYLOAD, headers=headers)
            assert resp.status_code == 200
            assert resp.json()["order_id"] == "TEST-ORDER-1"
            mock_allow.assert_called_once_with("fyers")
            mock_record_trade.assert_called_once()
    finally:
        revoke_session(token)


def test_live_mode_order_denied_by_limiter_returns_429_not_500():
    """This is the specific bug the fix's own exception handling could have
    reintroduced: HTTPException(429) raised inside the try block must not
    be caught by the generic `except Exception` below it and rewritten
    into a 500."""
    token, headers = _auth_headers()
    try:
        fake_broker = _fake_broker(paper_mode=False)
        with patch("api_bridge.BrokerFactory.get_active_broker", return_value=fake_broker), \
             patch("api_bridge._load_config_settings", return_value={"live_trading_mode": True}), \
             patch("api_bridge.ORDER_LIMITER.allow", return_value=False):
            resp = client.post("/api/order/execute", json=ORDER_PAYLOAD, headers=headers)
            assert resp.status_code == 429
            assert "rate limit" in resp.json()["detail"].lower()
            fake_broker.place_order.assert_not_called()  # must short-circuit before ever calling the broker
    finally:
        revoke_session(token)


def test_order_execute_rejects_unauthenticated_requests():
    with patch("api_bridge.BrokerFactory.get_active_broker", return_value=_fake_broker(paper_mode=True)):
        resp = client.post("/api/order/execute", json=ORDER_PAYLOAD)
    assert resp.status_code == 401
