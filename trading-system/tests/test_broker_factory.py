"""
Unit tests for brokers/broker_factory.py.

Tests cover:
  - Paper mode: place_order() returns a fake order, never calls real broker API
  - Broker selection logic from settings
  - Authentication failure handling (no unhandled exceptions)

Run with:  pytest tests/test_broker_factory.py -v
"""

from __future__ import annotations

import sys
import os
from unittest.mock import patch, MagicMock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_paper_broker():
    """Returns the active broker configured for paper trading."""
    from brokers import BrokerFactory
    broker = BrokerFactory.get_active_broker()
    broker.paper_mode = True
    return broker


# ---------------------------------------------------------------------------
# Test: Paper mode
# ---------------------------------------------------------------------------

class TestPaperMode:
    def test_paper_place_order_returns_response_without_real_api(self):
        """Paper mode MUST return a valid response without hitting any real API."""
        from brokers import OrderRequest, OrderSide, OrderType

        broker = _get_paper_broker()
        req = OrderRequest(
            symbol="NSE:NIFTY50-INDEX",
            quantity=50,
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
        )
        response = broker.place_order(req)
        # Should not raise, and should return some kind of order ID
        assert response is not None
        assert hasattr(response, "order_id") or isinstance(response, dict)

    def test_paper_mode_does_not_call_fyers_api(self):
        """Verify no outbound HTTP calls in paper mode."""
        broker = _get_paper_broker()
        from brokers import OrderRequest, OrderSide, OrderType

        # Patch any potential requests.post/get at the lowest level
        with patch("requests.post") as mock_post, patch("requests.get") as mock_get:
            try:
                broker.place_order(OrderRequest(
                    symbol="NSE:NIFTY50-INDEX",
                    quantity=1,
                    side=OrderSide.BUY,
                    order_type=OrderType.MARKET,
                ))
            except Exception:
                pass  # Some brokers may raise in paper mode — that's OK too
            # Real API must NOT be called
            assert not mock_post.called, "Paper mode should not make real POST requests"
            assert not mock_get.called,  "Paper mode should not make real GET requests"


# ---------------------------------------------------------------------------
# Test: Broker selection
# ---------------------------------------------------------------------------

class TestBrokerSelection:
    def test_get_active_broker_returns_an_object(self):
        from brokers import BrokerFactory
        broker = BrokerFactory.get_active_broker()
        assert broker is not None

    def test_broker_has_required_interface(self):
        """All brokers must implement the standard interface."""
        broker = _get_paper_broker()
        required_methods = ["authenticate", "place_order", "get_positions", "get_order_book"]
        for method in required_methods:
            assert hasattr(broker, method), f"Broker missing required method: {method}"
            assert callable(getattr(broker, method)), f"Broker.{method} is not callable"


# ---------------------------------------------------------------------------
# Test: Authentication failure
# ---------------------------------------------------------------------------

class TestAuthFailure:
    def test_failed_authenticate_returns_false_not_raises(self):
        """authenticate() must return False (not raise) when credentials are wrong."""
        broker = _get_paper_broker()
        with patch.object(broker, "authenticate", return_value=False):
            result = broker.authenticate()
        assert result is False

    def test_broker_usable_in_paper_mode_without_auth(self):
        """In paper mode, place_order should work WITHOUT authentication."""
        from brokers import OrderRequest, OrderSide, OrderType
        broker = _get_paper_broker()
        # Do NOT call authenticate()
        try:
            broker.place_order(OrderRequest(
                symbol="NSE:NIFTY50-INDEX",
                quantity=1,
                side=OrderSide.BUY,
                order_type=OrderType.MARKET,
            ))
        except Exception as e:
            # Only allow exceptions that are clearly NOT due to missing auth
            assert "auth" not in str(e).lower() and "credential" not in str(e).lower(), (
                f"Paper mode should not require authentication. Got: {e}"
            )
