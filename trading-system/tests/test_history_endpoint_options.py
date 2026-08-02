"""Integration test for /api/history's option-derivation path end-to-end
(real FastAPI app via TestClient, real symbol parser, real Black-Scholes
derivation, real CSV cache fallback — the only thing not real is the
live broker call, which naturally fails in a test environment and falls
through to the CSV cache exactly like it would in production without a
broker session).
"""
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient

from api_bridge import app
from shared.security.sessions import create_session, revoke_session

client = TestClient(app)


def _auth_headers():
    token = create_session("history-option-test-user")
    return token, {"Authorization": f"Bearer {token}"}


def test_option_symbol_returns_derived_option_history():
    token, headers = _auth_headers()
    try:
        r = client.get(
            "/api/history",
            params={"symbol": "NIFTY 24350 CE", "start_date": "2026-05-04", "end_date": "2026-05-05", "timeframe": "5 Min"},
            headers=headers,
        )
        assert r.status_code == 200
        data = r.json()
        assert data["underlying"] == "NIFTY"
        assert data["strike"] == 24350.0
        assert data["opt_type"] == "CE"
        assert data["data_points"] > 0
        assert len(data["data"]) == data["data_points"]
        for candle in data["data"]:
            assert candle["high"] >= candle["close"] >= candle["low"]
            assert candle["low"] > 0
    finally:
        revoke_session(token)


def test_equity_symbol_still_uses_the_plain_history_path():
    """Non-option symbols must not be routed through option derivation —
    confirms the parser's is_option gate actually branches correctly."""
    token, headers = _auth_headers()
    try:
        r = client.get(
            "/api/history",
            params={"symbol": "RELIANCE", "start_date": "2026-05-04", "end_date": "2026-05-05", "timeframe": "5 Min"},
            headers=headers,
        )
        assert r.status_code == 200
        data = r.json()
        assert "underlying" not in data  # option-path-only field
        assert "opt_type" not in data
        assert data["data_points"] > 0
        assert all(c["close"] < 5000 for c in data["data"][:20])  # RELIANCE-range, not NIFTY-range
    finally:
        revoke_session(token)


def test_history_endpoint_requires_auth():
    r = client.get(
        "/api/history",
        params={"symbol": "NIFTY 24350 CE", "start_date": "2026-05-04", "end_date": "2026-05-05", "timeframe": "5 Min"},
    )
    assert r.status_code == 401
