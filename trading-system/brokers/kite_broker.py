"""Zerodha Kite (KiteConnect) broker adapter.

Credential fields required
--------------------------
  api_key      : Kite API Key
  api_secret   : Kite API Secret
  access_token : Populated automatically after complete_login()

Install the SDK:  pip install kiteconnect
"""

from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable, Dict, List, Optional

from .base_broker import BaseBroker
from .exceptions import (
    AuthenticationError, BrokerConnectionError,
    MarketDataError, OrderRejectedError,
)
from .models import (
    Balance, BrokerInfo, MarketQuote, OrderBookEntry,
    OrderRequest, OrderResponse, OrderSide, OrderStatus,
    OrderType, Position, PositionSide,
)

logger = logging.getLogger(__name__)


class KiteBroker(BaseBroker):
    """Zerodha Kite broker adapter (kiteconnect SDK)."""

    BROKER_ID    = "kite"
    DISPLAY_NAME = "Zerodha (Kite)"

    @classmethod
    def info(cls) -> BrokerInfo:
        return BrokerInfo(
            broker_id=cls.BROKER_ID,
            display_name=cls.DISPLAY_NAME,
            description="Zerodha Kite — India's largest discount broker.",
            website="https://zerodha.com",
            supports_options=True,
            supports_futures=True,
            supports_streaming=True,
            credential_fields=[
                {"key": "api_key",      "label": "API Key",     "secret": False},
                {"key": "api_secret",   "label": "API Secret",  "secret": True},
                {"key": "access_token", "label": "Access Token (auto-filled after login)",
                 "secret": True},
            ],
        )

    def __init__(self, credentials: Dict[str, str], paper_mode: bool = False) -> None:
        super().__init__(credentials, paper_mode)
        self._kite = None    # kiteconnect.KiteConnect instance

    # ------------------------------------------------------------------
    # Authentication
    # ------------------------------------------------------------------

    def authenticate(self) -> bool:
        if self.paper_mode:
            self._authenticated = True
            return True

        token = self.credentials.get("access_token", "")
        if not token:
            logger.warning("Kite: no access_token — call get_login_url() then complete_login().")
            return False

        try:
            from kiteconnect import KiteConnect   # type: ignore[import]
            self._kite = KiteConnect(api_key=self.credentials.get("api_key", ""))
            self._kite.set_access_token(token)
            self._authenticated = True
            logger.info("Kite: authenticated successfully.")
            return True
        except ImportError:
            raise BrokerConnectionError(
                "kiteconnect not installed. Run: pip install kiteconnect",
                broker_id=self.BROKER_ID,
            )
        except Exception as exc:
            raise AuthenticationError(
                f"Kite authentication failed: {exc}", broker_id=self.BROKER_ID
            ) from exc

    def get_login_url(self) -> Optional[str]:
        try:
            from kiteconnect import KiteConnect   # type: ignore[import]
            kite = KiteConnect(api_key=self.credentials.get("api_key", ""))
            return kite.login_url()
        except Exception as exc:
            logger.error("Could not generate Kite login URL: %s", exc)
            return None

    def complete_login(self, request_token: str) -> bool:
        """Exchange request_token (from callback URL) for access_token."""
        try:
            from kiteconnect import KiteConnect   # type: ignore[import]
            kite = KiteConnect(api_key=self.credentials.get("api_key", ""))
            data  = kite.generate_session(
                request_token, api_secret=self.credentials.get("api_secret", "")
            )
            token = data.get("access_token", "")
            if not token:
                raise AuthenticationError("Empty token from Kite.", broker_id=self.BROKER_ID)
            self.credentials["access_token"] = token
            return self.authenticate()
        except AuthenticationError:
            raise
        except Exception as exc:
            raise AuthenticationError(
                f"Kite complete_login failed: {exc}", broker_id=self.BROKER_ID
            ) from exc

    # ------------------------------------------------------------------
    # Order management
    # ------------------------------------------------------------------

    def place_order(self, request: OrderRequest) -> OrderResponse:
        if self.paper_mode:
            logger.info("Kite [PAPER] %s %d %s", request.symbol, request.quantity, request.side)
            return OrderResponse.paper(request)

        if not self._kite:
            raise AuthenticationError("Not authenticated.", broker_id=self.BROKER_ID)

        try:
            from kiteconnect import KiteConnect   # type: ignore[import]
            order_id = self._kite.place_order(
                variety=KiteConnect.VARIETY_REGULAR,
                exchange=KiteConnect.EXCHANGE_NSE,
                tradingsymbol=request.symbol,
                transaction_type=(
                    KiteConnect.TRANSACTION_TYPE_BUY
                    if request.side == OrderSide.BUY
                    else KiteConnect.TRANSACTION_TYPE_SELL
                ),
                quantity=request.quantity,
                product=(
                    KiteConnect.PRODUCT_MIS
                    if request.product_type.value == "INTRADAY"
                    else KiteConnect.PRODUCT_CNC
                ),
                order_type=(
                    KiteConnect.ORDER_TYPE_MARKET
                    if request.order_type == OrderType.MARKET
                    else KiteConnect.ORDER_TYPE_LIMIT
                ),
                price=request.price if request.price else None,
            )
            return OrderResponse(
                order_id=str(order_id),
                status=OrderStatus.OPEN,
                symbol=request.symbol,
                quantity=request.quantity,
                side=request.side,
            )
        except Exception as exc:
            raise OrderRejectedError(
                f"Kite place_order failed: {exc}", broker_id=self.BROKER_ID
            ) from exc

    def cancel_order(self, order_id: str) -> Dict[str, Any]:
        if self.paper_mode:
            return {"status": "cancelled", "order_id": order_id}
        if not self._kite:
            raise AuthenticationError("Not authenticated.", broker_id=self.BROKER_ID)
        try:
            from kiteconnect import KiteConnect   # type: ignore[import]
            self._kite.cancel_order(variety=KiteConnect.VARIETY_REGULAR, order_id=order_id)
            return {"status": "cancelled", "order_id": order_id}
        except Exception as exc:
            raise BrokerConnectionError(
                f"Kite cancel_order failed: {exc}", broker_id=self.BROKER_ID
            ) from exc

    # ------------------------------------------------------------------
    # Account information
    # ------------------------------------------------------------------

    def get_positions(self) -> List[Position]:
        if self.paper_mode or not self._kite:
            return []
        try:
            data = self._kite.positions()
            positions = []
            for p in data.get("net", []):
                qty = int(p.get("quantity", 0))
                if qty == 0:
                    continue
                positions.append(Position(
                    symbol=p.get("tradingsymbol", ""),
                    side=PositionSide.LONG if qty > 0 else PositionSide.SHORT,
                    quantity=abs(qty),
                    average_price=float(p.get("average_price", 0)),
                    ltp=float(p.get("last_price", 0)),
                    unrealized_pnl=float(p.get("unrealised", 0)),
                    realized_pnl=float(p.get("realised", 0)),
                    product_type=p.get("product", "MIS"),
                    raw=p,
                ))
            return positions
        except Exception as exc:
            raise MarketDataError(
                f"Kite get_positions failed: {exc}", broker_id=self.BROKER_ID
            ) from exc

    def get_lot_size(self, symbol: str) -> int:
        """Fetch lot size from broker dynamically if cached, otherwise fallback."""
        if hasattr(self, '_lot_size_cache') and self._lot_size_cache:
            return self._lot_size_cache.get(symbol, super().get_lot_size(symbol))
        return super().get_lot_size(symbol)

    def get_balance(self) -> Balance:
        if self.paper_mode:
            return Balance(available_cash=10_000.0, used_margin=0.0, total_balance=10_000.0)
        if not self._kite:
            raise AuthenticationError("Not authenticated.", broker_id=self.BROKER_ID)
        try:
            data  = self._kite.margins(segment="equity")
            avail = float(data.get("available", {}).get("live_balance", 0))
            used  = float(data.get("utilised", {}).get("span", 0))
            return Balance(available_cash=avail, used_margin=used,
                           total_balance=avail + used, raw=data)
        except Exception as exc:
            raise MarketDataError(
                f"Kite get_balance failed: {exc}", broker_id=self.BROKER_ID
            ) from exc

    def get_order_book(self) -> List[OrderBookEntry]:
        if self.paper_mode or not self._kite:
            return []
        try:
            orders = self._kite.orders()
            return [
                OrderBookEntry(
                    order_id=o.get("order_id", ""),
                    symbol=o.get("tradingsymbol", ""),
                    side=OrderSide.BUY if o.get("transaction_type") == "BUY" else OrderSide.SELL,
                    quantity=int(o.get("quantity", 0)),
                    price=float(o.get("price", 0)),
                    status=OrderStatus.OPEN,
                    order_type=OrderType.MARKET if o.get("order_type") == "MARKET" else OrderType.LIMIT,
                    raw=o,
                )
                for o in orders
            ]
        except Exception as exc:
            raise MarketDataError(
                f"Kite get_order_book failed: {exc}", broker_id=self.BROKER_ID
            ) from exc

    # ------------------------------------------------------------------
    # Market data
    # ------------------------------------------------------------------

    def get_market_data(self, symbols: List[str]) -> Dict[str, MarketQuote]:
        if self.paper_mode or not self._kite:
            return {}
        try:
            resp   = self._kite.quote(symbols)
            quotes = {}
            for sym, q in resp.items():
                ohlc = q.get("ohlc", {})
                quotes[sym] = MarketQuote(
                    symbol=sym,
                    ltp=float(q.get("last_price", 0)),
                    open=float(ohlc.get("open", 0)),
                    high=float(ohlc.get("high", 0)),
                    low=float(ohlc.get("low", 0)),
                    close=float(ohlc.get("close", 0)),
                    volume=int(q.get("volume", 0)),
                )
            return quotes
        except Exception as exc:
            raise MarketDataError(
                f"Kite get_market_data failed: {exc}", broker_id=self.BROKER_ID
            ) from exc

    # ------------------------------------------------------------------
    # Streaming
    # ------------------------------------------------------------------

    async def stream_quotes(
        self,
        symbols: List[str],
        on_tick: Callable[[Dict[str, Any]], Awaitable[None]],
    ) -> None:
        if self.paper_mode:
            await self._synthetic_stream(symbols, on_tick)
            return
        # KiteTicker is callback-based; bridge to asyncio here via a queue
        logger.warning("Kite live KiteTicker bridge not yet wired — using synthetic stream.")
        await self._synthetic_stream(symbols, on_tick)

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    def close(self) -> None:
        self._kite = None
        self._authenticated = False
        logger.debug("KiteBroker.close() called.")
