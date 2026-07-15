"""Angel One (SmartAPI) broker adapter.

Credential fields required
--------------------------
  client_id   : Angel One Client / User ID
  mpin        : Trading MPIN
  totp_secret : TOTP secret key (for 2FA; the app generates the OTP from this)
  api_key     : SmartAPI API Key from developer console

Install the SDK:  pip install smartapi-python
"""

from __future__ import annotations

import logging
import time
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


def _get_totp(secret: str) -> str:
    """Generate a TOTP code from ``secret`` using pyotp."""
    try:
        import pyotp   # type: ignore[import]
        return pyotp.TOTP(secret).now()
    except ImportError:
        logger.warning("pyotp not installed — TOTP generation unavailable. pip install pyotp")
        return ""


class AngelBroker(BaseBroker):
    """Angel One SmartAPI broker adapter."""

    BROKER_ID    = "angel"
    DISPLAY_NAME = "Angel One"

    @classmethod
    def info(cls) -> BrokerInfo:
        return BrokerInfo(
            broker_id=cls.BROKER_ID,
            display_name=cls.DISPLAY_NAME,
            description="Angel One — Full-service Indian broker with SmartAPI.",
            website="https://smartapi.angelbroking.com",
            supports_options=True,
            supports_futures=True,
            supports_streaming=True,
            credential_fields=[
                {"key": "client_id",   "label": "Client ID",       "secret": False},
                {"key": "mpin",        "label": "Trading MPIN",    "secret": True},
                {"key": "totp_secret", "label": "TOTP Secret Key", "secret": True},
                {"key": "api_key",     "label": "SmartAPI Key",    "secret": True},
            ],
        )

    def __init__(self, credentials: Dict[str, str], paper_mode: bool = False) -> None:
        super().__init__(credentials, paper_mode)
        self._smart = None   # SmartConnect instance
        self._auth_token: str  = ""
        self._feed_token: str  = ""

    # ------------------------------------------------------------------
    # Authentication  (direct — no OAuth redirect needed)
    # ------------------------------------------------------------------

    def authenticate(self) -> bool:
        if self.paper_mode:
            self._authenticated = True
            return True

        try:
            from SmartApi import SmartConnect   # type: ignore[import]
        except ImportError:
            raise BrokerConnectionError(
                "smartapi-python not installed. Run: pip install smartapi-python",
                broker_id=self.BROKER_ID,
            )

        totp_code = _get_totp(self.credentials.get("totp_secret", ""))
        if not totp_code:
            raise AuthenticationError(
                "TOTP code could not be generated — check totp_secret.", broker_id=self.BROKER_ID
            )

        try:
            smart = SmartConnect(api_key=self.credentials.get("api_key", ""))
            resp  = smart.generateSession(
                clientCode=self.credentials.get("client_id", ""),
                password=self.credentials.get("mpin", ""),
                totp=totp_code,
            )
            if resp.get("status") is False:
                raise AuthenticationError(
                    resp.get("message", "Login failed"), broker_id=self.BROKER_ID
                )
            self._smart      = smart
            self._auth_token = resp["data"]["jwtToken"]
            self._feed_token = smart.getfeedToken()
            self._authenticated = True
            logger.info("Angel One: authenticated successfully.")
            return True
        except AuthenticationError:
            raise
        except Exception as exc:
            raise AuthenticationError(
                f"Angel One authentication failed: {exc}", broker_id=self.BROKER_ID
            ) from exc

    # Angel One uses direct login — no browser redirect
    def get_login_url(self) -> Optional[str]:
        return None

    # ------------------------------------------------------------------
    # Order management
    # ------------------------------------------------------------------

    def place_order(self, request: OrderRequest) -> OrderResponse:
        if self.paper_mode:
            logger.info("Angel [PAPER] %s %d %s", request.symbol, request.quantity, request.side)
            return OrderResponse.paper(request)

        if not self._smart:
            raise AuthenticationError("Not authenticated.", broker_id=self.BROKER_ID)

        order_params = {
            "variety":      "NORMAL",
            "tradingsymbol": request.symbol,
            "symboltoken":  "",       # ideally resolved from symbol master
            "transactiontype": request.side.value,
            "exchange":     "NSE",
            "ordertype":    request.order_type.value,
            "producttype":  "INTRADAY" if request.product_type.value == "INTRADAY" else "DELIVERY",
            "duration":     "DAY",
            "price":        str(request.price),
            "triggerprice": str(request.trigger_price),
            "quantity":     str(request.quantity),
        }
        try:
            resp = self._smart.placeOrder(order_params)
            if resp.get("status") is False:
                raise OrderRejectedError(
                    resp.get("message", "Order rejected"), broker_id=self.BROKER_ID, raw_response=resp
                )
            order_id = resp.get("data", {}).get("orderid", "")
            return OrderResponse(
                order_id=order_id,
                status=OrderStatus.OPEN,
                symbol=request.symbol,
                quantity=request.quantity,
                side=request.side,
                raw=resp,
            )
        except OrderRejectedError:
            raise
        except Exception as exc:
            raise BrokerConnectionError(
                f"Angel place_order failed: {exc}", broker_id=self.BROKER_ID
            ) from exc

    def cancel_order(self, order_id: str) -> Dict[str, Any]:
        if self.paper_mode:
            return {"status": "cancelled", "order_id": order_id}
        if not self._smart:
            raise AuthenticationError("Not authenticated.", broker_id=self.BROKER_ID)
        try:
            resp = self._smart.cancelOrder(order_id=order_id, variety="NORMAL")
            return resp
        except Exception as exc:
            raise BrokerConnectionError(
                f"Angel cancel_order failed: {exc}", broker_id=self.BROKER_ID
            ) from exc

    # ------------------------------------------------------------------
    # Account information
    # ------------------------------------------------------------------

    def get_positions(self) -> List[Position]:
        if self.paper_mode or not self._smart:
            return []
        try:
            data = self._smart.position()
            if not data or not data.get("data"):
                return []
            
            positions = []
            for p in (data.get("data") or []):
                qty = int(p.get("netqty", 0))
                if qty == 0:
                    continue
                positions.append(Position(
                    symbol=p.get("tradingsymbol", ""),
                    side=PositionSide.LONG if qty > 0 else PositionSide.SHORT,
                    quantity=abs(qty),
                    average_price=float(p.get("netprice", 0)),
                    ltp=float(p.get("ltp", 0)),
                    unrealized_pnl=float(p.get("unrealised", 0)),
                    realized_pnl=float(p.get("realised", 0)),
                    product_type=p.get("producttype", "MIS"),
                    raw=p,
                ))
            return positions
        except Exception as exc:
            raise MarketDataError(
                f"Angel get_positions failed: {exc}", broker_id=self.BROKER_ID
            ) from exc

    def get_lot_size(self, symbol: str) -> int:
        """Fetch lot size from broker dynamically if cached, otherwise fallback."""
        if hasattr(self, '_lot_size_cache') and self._lot_size_cache:
            return self._lot_size_cache.get(symbol, super().get_lot_size(symbol))
        return super().get_lot_size(symbol)

    def get_balance(self) -> Balance:
        if self.paper_mode:
            return Balance(available_cash=10_000.0, used_margin=0.0, total_balance=10_000.0)
        if not self._smart:
            raise AuthenticationError("Not authenticated.", broker_id=self.BROKER_ID)
        try:
            resp  = self._smart.rmsLimit()
            data  = resp.get("data", {}) or {}
            avail = float(data.get("availablecash", 0))
            used  = float(data.get("utiliseddebits", 0))
            return Balance(available_cash=avail, used_margin=used,
                           total_balance=avail + used, raw=resp)
        except Exception as exc:
            raise MarketDataError(
                f"Angel get_balance failed: {exc}", broker_id=self.BROKER_ID
            ) from exc

    def get_order_book(self) -> List[OrderBookEntry]:
        if self.paper_mode or not self._smart:
            return []
        try:
            resp   = self._smart.orderBook()
            orders = []
            for o in (resp.get("data") or []):
                orders.append(OrderBookEntry(
                    order_id=o.get("orderid", ""),
                    symbol=o.get("tradingsymbol", ""),
                    side=OrderSide.BUY if o.get("transactiontype") == "BUY" else OrderSide.SELL,
                    quantity=int(o.get("quantity", 0)),
                    price=float(o.get("price", 0)),
                    status=OrderStatus.OPEN,
                    order_type=OrderType.MARKET if o.get("ordertype") == "MARKET" else OrderType.LIMIT,
                    raw=o,
                ))
            return orders
        except Exception as exc:
            raise MarketDataError(
                f"Angel get_order_book failed: {exc}", broker_id=self.BROKER_ID
            ) from exc

    # ------------------------------------------------------------------
    # Market data
    # ------------------------------------------------------------------

    def get_market_data(self, symbols: List[str]) -> Dict[str, MarketQuote]:
        if self.paper_mode or not self._smart:
            return {}
        try:
            resp = self._smart.ltpData("NSE", symbols[0], "")
            data = resp.get("data", {}) or {}
            sym  = symbols[0]
            return {sym: MarketQuote(symbol=sym, ltp=float(data.get("ltp", 0)))}
        except Exception as exc:
            raise MarketDataError(
                f"Angel get_market_data failed: {exc}", broker_id=self.BROKER_ID
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
        logger.warning("Angel One live websocket bridge not yet wired — using synthetic stream.")
        await self._synthetic_stream(symbols, on_tick)

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    def close(self) -> None:
        if self._smart:
            try:
                self._smart.terminateSession(self.credentials.get("client_id", ""))
            except Exception:
                pass
        self._smart = None
        self._authenticated = False
        logger.debug("AngelBroker.close() called.")
