"""Canonical data models shared across all broker adapters.

Using dataclasses (not vendor-specific objects) means the rest of the
trading system stays completely broker-agnostic — strategy code, risk
manager, exit engine, and dashboard never import anything from a
vendor SDK.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional


# ------------------------------------------------------------------
# Enumerations
# ------------------------------------------------------------------

class OrderSide(str, Enum):
    BUY  = "BUY"
    SELL = "SELL"


class OrderType(str, Enum):
    MARKET = "MARKET"
    LIMIT  = "LIMIT"
    SL     = "SL"          # Stop-Loss market
    SL_M   = "SL-M"        # Stop-Loss market (some brokers)


class ProductType(str, Enum):
    INTRADAY = "INTRADAY"
    DELIVERY = "DELIVERY"
    MARGIN   = "MARGIN"


class OrderStatus(str, Enum):
    PENDING   = "PENDING"
    OPEN      = "OPEN"
    COMPLETE  = "COMPLETE"
    REJECTED  = "REJECTED"
    CANCELLED = "CANCELLED"
    PARTIAL   = "PARTIAL"


class PositionSide(str, Enum):
    LONG  = "LONG"
    SHORT = "SHORT"


# ------------------------------------------------------------------
# Request models
# ------------------------------------------------------------------

@dataclass
class OrderRequest:
    """Broker-agnostic order request.  All broker adapters consume this."""
    symbol:        str
    quantity:      int
    side:          OrderSide
    order_type:    OrderType    = OrderType.MARKET
    product_type:  ProductType  = ProductType.INTRADAY
    price:         float        = 0.0          # For LIMIT orders
    trigger_price: float        = 0.0          # For SL orders
    tag:           str          = ""           # Optional label for tracking

    def __post_init__(self) -> None:
        # Normalise string inputs from older calling code
        if isinstance(self.side, str):
            self.side = OrderSide(self.side.upper())
        if isinstance(self.order_type, str):
            self.order_type = OrderType(self.order_type.upper())
        if isinstance(self.product_type, str):
            self.product_type = ProductType(self.product_type.upper())


# ------------------------------------------------------------------
# Response / data models
# ------------------------------------------------------------------

@dataclass
class OrderResponse:
    """Normalised order response returned by every broker adapter."""
    order_id:   str
    status:     OrderStatus
    symbol:     str
    quantity:   int
    side:       OrderSide
    price:      float           = 0.0
    message:    str             = ""
    raw:        Dict[str, Any]  = field(default_factory=dict)

    @classmethod
    def paper(cls, request: OrderRequest) -> "OrderResponse":
        """Synthetic response for paper-trading mode."""
        return cls(
            order_id=f"PAPER-{request.symbol}-{request.side.value}",
            status=OrderStatus.COMPLETE,
            symbol=request.symbol,
            quantity=request.quantity,
            side=request.side,
            message="Paper trade — no real order placed.",
        )


@dataclass
class Position:
    """Open or closed position as reported by the broker."""
    symbol:       str
    side:         PositionSide
    quantity:     int
    average_price: float
    ltp:          float         = 0.0     # Last traded price
    unrealized_pnl: float       = 0.0
    realized_pnl:   float       = 0.0
    product_type:   str         = "INTRADAY"
    raw:            Dict[str, Any] = field(default_factory=dict)


@dataclass
class Balance:
    """Account funds / margin summary."""
    available_cash:  float
    used_margin:     float
    total_balance:   float
    currency:        str            = "INR"
    raw:             Dict[str, Any] = field(default_factory=dict)


@dataclass
class MarketQuote:
    """Normalised real-time quote for a single symbol."""
    symbol:     str
    ltp:        float
    open:       float = 0.0
    high:       float = 0.0
    low:        float = 0.0
    close:      float = 0.0
    volume:     int   = 0
    bid:        float = 0.0
    ask:        float = 0.0
    timestamp:  Optional[datetime] = None


@dataclass
class OrderBookEntry:
    """Single entry in the order book / trade book."""
    order_id:   str
    symbol:     str
    side:       OrderSide
    quantity:   int
    price:      float
    status:     OrderStatus
    order_type: OrderType
    traded_price: float = 0.0
    placed_at:  Optional[datetime] = None
    raw:        Dict[str, Any]     = field(default_factory=dict)


@dataclass
class BrokerInfo:
    """Metadata about a registered broker implementation."""
    broker_id:    str           # e.g. "fyers", "kite", "angel"
    display_name: str           # e.g. "Fyers"
    description:  str           = ""
    website:      str           = ""
    supports_options:    bool   = True
    supports_futures:    bool   = True
    supports_streaming:  bool   = True
    credential_fields:   List[Dict[str, str]] = field(default_factory=list)
    # Each dict: {"key": "api_key", "label": "API Key", "secret": True/False}
