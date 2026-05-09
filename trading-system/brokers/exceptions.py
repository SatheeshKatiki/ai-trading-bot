"""Broker exception hierarchy.

All broker-related errors derive from ``BrokerError`` so callers can
catch the whole family with a single except clause, or target specific
failure modes (authentication, order rejection, connectivity) individually.
"""

from __future__ import annotations


class BrokerError(Exception):
    """Base class for all broker-layer errors."""

    def __init__(self, message: str, broker_id: str = "", raw_response: object = None) -> None:
        super().__init__(message)
        self.broker_id    = broker_id
        self.raw_response = raw_response

    def __str__(self) -> str:
        prefix = f"[{self.broker_id}] " if self.broker_id else ""
        return f"{prefix}{super().__str__()}"


# ------------------------------------------------------------------
# Authentication / session errors
# ------------------------------------------------------------------

class AuthenticationError(BrokerError):
    """Raised when login / token generation fails."""


class TokenExpiredError(AuthenticationError):
    """Access token is expired and must be refreshed."""


class InvalidCredentialsError(AuthenticationError):
    """API key, secret, or TOTP code is wrong."""


# ------------------------------------------------------------------
# Order errors
# ------------------------------------------------------------------

class OrderError(BrokerError):
    """Base for order-related failures."""


class OrderRejectedError(OrderError):
    """Broker rejected the order (insufficient margin, circuit breaker, etc.)."""

    def __init__(self, message: str, order_id: str = "", **kwargs) -> None:
        super().__init__(message, **kwargs)
        self.order_id = order_id


class OrderNotFoundError(OrderError):
    """Cancel / modify request for an order that does not exist."""


class InsufficientFundsError(OrderError):
    """Not enough margin / funds to place the order."""


# ------------------------------------------------------------------
# Market data errors
# ------------------------------------------------------------------

class MarketDataError(BrokerError):
    """Failed to fetch quotes, OHLCV data, or option chain."""


class SymbolNotFoundError(MarketDataError):
    """The requested symbol does not exist on this broker."""


# ------------------------------------------------------------------
# Connectivity errors
# ------------------------------------------------------------------

class BrokerConnectionError(BrokerError):
    """Network-level failure reaching the broker API."""


class BrokerTimeoutError(BrokerConnectionError):
    """Request timed out."""


class StreamDisconnectedError(BrokerConnectionError):
    """Live data websocket dropped unexpectedly."""


# ------------------------------------------------------------------
# Configuration / setup errors
# ------------------------------------------------------------------

class BrokerNotConfiguredError(BrokerError):
    """Broker selected but credentials are missing or incomplete."""


class BrokerNotFoundError(BrokerError):
    """Requested broker_id is not registered in BrokerFactory."""


class UnsupportedOperationError(BrokerError):
    """This broker does not support the requested operation."""
