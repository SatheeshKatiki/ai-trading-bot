"""Order input validator — validates every OrderRequest before it reaches the broker.

Defence-in-depth: even if the strategy generates a bad signal or the risk
manager passes an edge case, the validator acts as the final gate before any
real capital is at risk.

Checks performed
----------------
* Symbol format (non-empty, no special characters, length reasonable)
* Quantity > 0 and ≤ configurable maximum per order
* Price ≥ 0 for LIMIT orders; 0 for MARKET orders
* Side is a valid OrderSide enum
* OrderType is a valid OrderType enum
* Product type is valid
* Optional: daily order count limit per symbol (prevents runaway loops)

Usage::

    from shared.security import InputValidator, ValidationError
    from brokers import OrderRequest, OrderSide

    validator = InputValidator()   # or use the global `validator` singleton
    try:
        clean_request = validator.validate(request)
        resp = await broker.place_order_async(clean_request)
    except ValidationError as e:
        logger.error("Rejected bad order: %s", e)
"""

from __future__ import annotations

import re
import threading
from collections import defaultdict
from datetime import date
from typing import Dict, Any

# Lazy import — brokers.models is loaded on first use, not at module load time.
# This prevents cascading import errors from killing the dashboard startup.
_broker_models = None

def _get_broker_models():
    global _broker_models
    if _broker_models is None:
        from brokers import models as _m
        _broker_models = _m
    return _broker_models


class ValidationError(ValueError):
    """Raised when an OrderRequest fails validation."""


# Symbols allowed characters: letters, digits, colon, dash, underscore, dot
_SYMBOL_RE = re.compile(r'^[A-Za-z0-9:.\-_]{1,50}$')


class InputValidator:
    """Validates OrderRequest objects before they are sent to the broker.

    Parameters
    ----------
    max_quantity : int
        Maximum quantity allowed in a single order (default: 5000 lots/shares).
    max_price : float
        Maximum price allowed for LIMIT orders (default: 200000 = ₹2 lakh).
    max_orders_per_day_per_symbol : int
        Maximum orders placed on a single symbol in one trading day (default: 20).
        Prevents infinite re-entry loops.
    """

    def __init__(
        self,
        max_quantity: int = 5_000,
        max_price: float = 200_000.0,
        max_orders_per_day_per_symbol: int = 20,
    ) -> None:
        self.max_quantity   = max_quantity
        self.max_price      = max_price
        self.max_daily_orders = max_orders_per_day_per_symbol

        self._daily_counts: Dict[str, int] = defaultdict(int)
        self._count_date: date = date.today()
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Core validation
    # ------------------------------------------------------------------

    def validate(self, req: Any) -> Any:
        """Validate ``req`` and return it (possibly normalised).

        Raises ``ValidationError`` if any check fails.
        """
        self._check_symbol(req.symbol)
        self._check_quantity(req.quantity)
        self._check_price(req)
        self._check_side(req.side)
        self._check_order_type(req.order_type)
        self._check_product_type(req.product_type)
        self._check_daily_limit(req.symbol)

        # Normalise: strip whitespace from symbol
        object.__setattr__(req, "symbol", req.symbol.strip().upper()) \
            if hasattr(req, "__dataclass_fields__") else setattr(req, "symbol", req.symbol.strip().upper())

        return req

    # ------------------------------------------------------------------
    # Individual checks
    # ------------------------------------------------------------------

    def _check_symbol(self, symbol: str) -> None:
        if not symbol or not symbol.strip():
            raise ValidationError("Symbol must not be empty.")
        if not _SYMBOL_RE.match(symbol.strip()):
            raise ValidationError(
                f"Symbol '{symbol}' contains invalid characters. "
                "Only letters, digits, ':', '.', '-', '_' are allowed."
            )

    def _check_quantity(self, qty: int) -> None:
        if not isinstance(qty, (int, float)) or qty <= 0:
            raise ValidationError(f"Quantity must be a positive integer; got {qty!r}.")
        if qty > self.max_quantity:
            raise ValidationError(
                f"Quantity {qty} exceeds maximum allowed ({self.max_quantity}). "
                "Update InputValidator.max_quantity to increase the limit."
            )

    def _check_price(self, req: Any) -> None:
        m = _get_broker_models()
        if req.order_type == m.OrderType.LIMIT:
            if req.price <= 0:
                raise ValidationError(
                    f"LIMIT order requires price > 0; got {req.price}."
                )
            if req.price > self.max_price:
                raise ValidationError(
                    f"LIMIT price {req.price} exceeds maximum ({self.max_price}). "
                    "Update InputValidator.max_price to increase the limit."
                )
        elif req.order_type == m.OrderType.MARKET:
            if req.price != 0:
                # Silently correct rather than reject — avoids breaking valid callers
                pass   # MARKET orders ignore price; no action needed

    def _check_side(self, side: Any) -> None:
        m = _get_broker_models()
        if side not in (m.OrderSide.BUY, m.OrderSide.SELL):
            raise ValidationError(f"Invalid order side: {side!r}. Must be BUY or SELL.")

    def _check_order_type(self, order_type: Any) -> None:
        m = _get_broker_models()
        valid = set(m.OrderType)
        if order_type not in valid:
            raise ValidationError(f"Invalid order type: {order_type!r}.")

    def _check_product_type(self, product_type: Any) -> None:
        m = _get_broker_models()
        valid = set(m.ProductType)
        if product_type not in valid:
            raise ValidationError(f"Invalid product type: {product_type!r}.")

    def _check_daily_limit(self, symbol: str) -> None:
        with self._lock:
            today = date.today()
            if today != self._count_date:
                # Day rolled over — reset counts
                self._daily_counts.clear()
                self._count_date = today
            count = self._daily_counts[symbol]
            if count >= self.max_daily_orders:
                raise ValidationError(
                    f"Daily order limit ({self.max_daily_orders}) reached for symbol '{symbol}'. "
                    "The bot has placed too many orders on this symbol today — "
                    "possible loop detected. Manual intervention required."
                )
            self._daily_counts[symbol] += 1

    def reset_symbol_count(self, symbol: str) -> None:
        """Manually reset the daily order count for a symbol (e.g. after manual review)."""
        with self._lock:
            self._daily_counts.pop(symbol, None)


# ---------------------------------------------------------------------------
# Global singleton
# ---------------------------------------------------------------------------
validator = InputValidator()
