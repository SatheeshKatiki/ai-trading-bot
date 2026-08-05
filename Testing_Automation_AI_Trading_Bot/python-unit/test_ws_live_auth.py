"""Regression test for /ws/live's session-token requirement, and
specifically for the internal engine-to-bridge connection that was
broken by it.

Root-cause fix (found while starting the live engine for the first time
since the Critical #2 auth-gate fix landed): api_bridge.py's /ws/live
has required a valid session ?token= ever since that fix went in — the
frontend's browser client already goes through /api/ws-token for this,
but brokers/fyers_broker.py's stream_quotes() (the trading engine's own
connection to its own API bridge, for receiving live ticks) never sent
any token at all. This meant the live engine could connect to nothing
and would have silently produced zero ticks for the entire length of a
paper-trading validation run, with no crash and no obvious signal beyond
a repeating "WebSocket disconnected... retrying" log line.

This test exercises the real /ws/live route (not a mock) via FastAPI
TestClient's websocket support, proving: no token -> rejected, and a
session token created the same way fyers_broker.py now creates one
(shared.security.sessions.create_session) -> accepted. This is the
server-side half of the contract; the fix itself (fyers_broker.py
building its ws_url with a token from create_session()) was verified
live against a real running instance of api_bridge.py, logging
"Connected to API Bridge WebSocket!" where it previously logged
"disconnected or failed: ... HTTP 403" on every single attempt.
"""
import sys
from pathlib import Path

import _bootstrap  # noqa: F401  (side-effect: puts trading-system/ on sys.path)

from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from api_bridge import app
from shared.security.sessions import create_session, revoke_session

client = TestClient(app)


def test_ws_live_rejects_connection_with_no_token():
    try:
        with client.websocket_connect("/ws/live"):
            assert False, "connection should have been rejected"
    except WebSocketDisconnect as e:
        assert e.code == 4401


def test_ws_live_rejects_invalid_token():
    try:
        with client.websocket_connect("/ws/live?token=not-a-real-token"):
            assert False, "connection should have been rejected"
    except WebSocketDisconnect as e:
        assert e.code == 4401


def test_ws_live_accepts_a_real_session_token():
    """This is exactly the pattern fyers_broker.py's stream_quotes() now
    uses: mint a session via create_session(), pass it as ?token=."""
    token = create_session("test-engine-internal")
    try:
        with client.websocket_connect(f"/ws/live?token={token}") as ws:
            # Connection accepted (no immediate close) -- this is the
            # server-side half of the contract the engine fix depends on.
            assert ws is not None
    finally:
        revoke_session(token)
