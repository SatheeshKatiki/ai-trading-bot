"""Broker abstraction layer — public API.

Import everything you need from here:

    from brokers import BrokerFactory, BaseBroker, OrderRequest, OrderSide
    from brokers.exceptions import AuthenticationError, OrderRejectedError

Typical usage in trading engine:
    broker = BrokerFactory.get_active_broker()
    resp   = await broker.place_order_async(
                 OrderRequest(symbol="NSE:NIFTY-INDEX", quantity=1,
                              side=OrderSide.BUY))
"""

from .base_broker    import BaseBroker
from .broker_factory import BrokerFactory
from .credentials    import (
    save_credentials, load_credentials,
    delete_credentials, credentials_exist,
    list_saved_brokers,
)
from .exceptions     import (
    BrokerError, AuthenticationError, TokenExpiredError,
    InvalidCredentialsError, OrderError, OrderRejectedError,
    OrderNotFoundError, InsufficientFundsError,
    MarketDataError, SymbolNotFoundError,
    BrokerConnectionError, BrokerTimeoutError,
    StreamDisconnectedError, BrokerNotConfiguredError,
    BrokerNotFoundError, UnsupportedOperationError,
)
from .models         import (
    OrderRequest, OrderResponse, OrderSide, OrderType,
    ProductType, OrderStatus, Position, PositionSide,
    Balance, MarketQuote, OrderBookEntry, BrokerInfo,
)

__all__ = [
    # Core abstractions
    "BaseBroker",
    "BrokerFactory",
    # Credential helpers
    "save_credentials", "load_credentials",
    "delete_credentials", "credentials_exist",
    "list_saved_brokers",
    # Exceptions
    "BrokerError", "AuthenticationError", "TokenExpiredError",
    "InvalidCredentialsError", "OrderError", "OrderRejectedError",
    "OrderNotFoundError", "InsufficientFundsError",
    "MarketDataError", "SymbolNotFoundError",
    "BrokerConnectionError", "BrokerTimeoutError",
    "StreamDisconnectedError", "BrokerNotConfiguredError",
    "BrokerNotFoundError", "UnsupportedOperationError",
    # Models
    "OrderRequest", "OrderResponse", "OrderSide", "OrderType",
    "ProductType", "OrderStatus", "Position", "PositionSide",
    "Balance", "MarketQuote", "OrderBookEntry", "BrokerInfo",
]
