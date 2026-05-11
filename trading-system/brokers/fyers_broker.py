"""Fyers broker adapter.

Implements ``BaseBroker`` using the ``fyers-api`` SDK.
Runs in paper mode automatically when credentials are missing or incomplete.

Credential fields required
--------------------------
  client_id     : Fyers App Client ID   (e.g. "XY12345-100")
  secret_key    : Fyers App Secret Key
  redirect_uri  : OAuth redirect URI    (default https://localhost)
  access_token  : Cached post-login token (populated after complete_login)
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from pathlib import Path
from typing import Any, Awaitable, Callable, Dict, List, Optional

from .base_broker import BaseBroker, _BROKER_EXECUTOR
from .exceptions import (
    AuthenticationError, BrokerConnectionError,
    InsufficientFundsError, MarketDataError,
    OrderRejectedError, UnsupportedOperationError,
)
from .models import (
    Balance, BrokerInfo, MarketQuote, OrderBookEntry,
    OrderRequest, OrderResponse, OrderSide, OrderStatus,
    OrderType, Position, PositionSide,
)

logger = logging.getLogger(__name__)

# Cached token survives process restarts
_TOKEN_CACHE = Path(__file__).resolve().parents[1] / ".fyers_tokens.json"


class FyersBroker(BaseBroker):
    """Fyers broker adapter (fyers-api SDK)."""

    BROKER_ID    = "fyers"
    DISPLAY_NAME = "Fyers"

    @classmethod
    def info(cls) -> BrokerInfo:
        return BrokerInfo(
            broker_id=cls.BROKER_ID,
            display_name=cls.DISPLAY_NAME,
            description="Fyers Securities — Indian equity & derivatives broker.",
            website="https://fyers.in",
            supports_options=True,
            supports_futures=True,
            supports_streaming=True,
            credential_fields=[
                {"key": "client_id",    "label": "Client ID",     "secret": False},
                {"key": "secret_key",   "label": "Secret Key",    "secret": True},
                {"key": "redirect_uri", "label": "Redirect URI",  "secret": False,
                 "default": "https://localhost"},
                {"key": "access_token", "label": "Access Token (auto-filled after login)",
                 "secret": True},
            ],
        )

    def __init__(self, credentials: Dict[str, str], paper_mode: bool = False) -> None:
        super().__init__(credentials, paper_mode)
        self._fyers_model = None   # Lazy-loaded after authenticate()

    # ------------------------------------------------------------------
    # Authentication
    # ------------------------------------------------------------------

    def authenticate(self) -> bool:
        if self.paper_mode:
            self._authenticated = True
            logger.info("Fyers: paper mode — skipping real authentication.")
            
            # Initialize model for data fetching in paper mode if token exists!
            token = self._load_cached_token()
            if token:
                try:
                    from fyers_apiv3 import fyersModel
                except ImportError:
                    from fyers_api import fyersModel
                    
                self._fyers_model = fyersModel.FyersModel(
                    client_id=self.credentials.get("client_id", ""),
                    token=token,
                    log_path="",
                )
                logger.info("Fyers: Initialized model in paper mode for data fetching.")
            return True

        token = self.credentials.get("access_token") or self._load_cached_token()
        if not token:
            logger.warning(
                "Fyers: no access_token found — call get_login_url() then complete_login()."
            )
            return False

        try:
            try:
                from fyers_apiv3 import fyersModel
            except ImportError:
                from fyers_api import fyersModel   # type: ignore[import]
                
            self._fyers_model = fyersModel.FyersModel(
                client_id=self.credentials.get("client_id", ""),
                token=token,
                log_path="",
            )
            self._authenticated = True
            logger.info("Fyers: authenticated successfully.")
            return True
        except Exception as exc:
            raise AuthenticationError(
                f"Fyers SDK init failed: {exc}", broker_id=self.BROKER_ID
            ) from exc

    def get_login_url(self) -> Optional[str]:
        """Generate the Fyers OAuth URL the user must visit in a browser."""
        if self.paper_mode:
            return None
        try:
            try:
                from fyers_apiv3 import fyersModel
            except ImportError:
                from fyers_api import fyersModel   # type: ignore[import]
                
            try:
                session = fyersModel.SessionModel(
                    client_id=self.credentials.get("client_id", ""),
                    secret_key=self.credentials.get("secret_key", ""),
                    redirect_uri=self.credentials.get("redirect_uri", "https://localhost"),
                    response_type="code",
                    grant_type="authorization_code",
                )
            except AttributeError:
                # Fallback for versions where SessionModel is in the session module
                from fyers_api import session as fyers_session
                session = fyers_session.SessionModel(
                    client_id=self.credentials.get("client_id", ""),
                    secret_key=self.credentials.get("secret_key", ""),
                    redirect_uri=self.credentials.get("redirect_uri", "https://localhost"),
                    response_type="code",
                    grant_type="authorization_code",
                )
            return session.generate_authcode()
        except Exception as exc:
            logger.error("Could not generate Fyers login URL: %s", exc)
            return None

    def complete_login(self, auth_code: str) -> bool:
        """Exchange the auth code for an access token and cache it."""
        try:
            try:
                from fyers_apiv3 import fyersModel
            except ImportError:
                from fyers_api import fyersModel   # type: ignore[import]
                
            try:
                session = fyersModel.SessionModel(
                    client_id=self.credentials.get("client_id", ""),
                    secret_key=self.credentials.get("secret_key", ""),
                    redirect_uri=self.credentials.get("redirect_uri", "https://localhost"),
                    response_type="code",
                    grant_type="authorization_code",
                )
            except AttributeError:
                from fyers_api import session as fyers_session
                session = fyers_session.SessionModel(
                    client_id=self.credentials.get("client_id", ""),
                    secret_key=self.credentials.get("secret_key", ""),
                    redirect_uri=self.credentials.get("redirect_uri", "https://localhost"),
                    response_type="code",
                    grant_type="authorization_code",
                )
            session.set_token(auth_code)
            resp  = session.generate_token()
            token = resp.get("access_token", "")
            if not token:
                raise AuthenticationError(
                    f"Empty token in response: {resp}", broker_id=self.BROKER_ID
                )
            self._save_cached_token(token)
            # Also push it back into credentials so authenticate() sees it
            self.credentials["access_token"] = token
            return self.authenticate()
        except AuthenticationError:
            raise
        except Exception as exc:
            raise AuthenticationError(
                f"Fyers complete_login failed: {exc}", broker_id=self.BROKER_ID
            ) from exc

    def _load_cached_token(self) -> str:
        if _TOKEN_CACHE.is_file():
            try:
                data = json.loads(_TOKEN_CACHE.read_text(encoding="utf-8"))
                return data.get("access_token", "")
            except Exception:
                pass
        return ""

    def _save_cached_token(self, token: str) -> None:
        _TOKEN_CACHE.write_text(
            json.dumps({"access_token": token}, indent=2), encoding="utf-8"
        )
        logger.info("Fyers: access token cached → %s", _TOKEN_CACHE)

    # ------------------------------------------------------------------
    # Order management
    # ------------------------------------------------------------------

    def place_order(self, request: OrderRequest) -> OrderResponse:
        if self.paper_mode:
            logger.info("Fyers [PAPER] %s %d %s", request.symbol, request.quantity, request.side)
            return OrderResponse.paper(request)

        if not self._fyers_model:
            raise AuthenticationError("Not authenticated.", broker_id=self.BROKER_ID)

        payload = {
            "symbol":       request.symbol,
            "qty":          request.quantity,
            "type":         2 if request.order_type == OrderType.MARKET else 1,
            "side":         1 if request.side == OrderSide.BUY else -1,
            "productType":  request.product_type.value,
            "limitPrice":   request.price,
            "stopPrice":    request.trigger_price,
            "validity":     "DAY",
            "disclosedQty": 0,
            "offlineOrder": False,
            "stopLoss":     0,
            "takeProfit":   0,
        }
        try:
            resp = self._fyers_model.place_order(payload)
            order_id = resp.get("id", "")
            code     = resp.get("s", "")
            if code != "ok":
                raise OrderRejectedError(
                    resp.get("message", "Order rejected"),
                    order_id=order_id, broker_id=self.BROKER_ID, raw_response=resp,
                )
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
                f"Fyers place_order failed: {exc}", broker_id=self.BROKER_ID
            ) from exc

    def cancel_order(self, order_id: str) -> Dict[str, Any]:
        if self.paper_mode:
            return {"status": "cancelled", "order_id": order_id}
        if not self._fyers_model:
            raise AuthenticationError("Not authenticated.", broker_id=self.BROKER_ID)
        try:
            return self._fyers_model.cancel_order({"id": order_id})
        except Exception as exc:
            raise BrokerConnectionError(
                f"Fyers cancel_order failed: {exc}", broker_id=self.BROKER_ID
            ) from exc

    # ------------------------------------------------------------------
    # Account information
    # ------------------------------------------------------------------

    def get_positions(self) -> List[Position]:
        if self.paper_mode:
            return []
        if not self._fyers_model:
            raise AuthenticationError("Not authenticated.", broker_id=self.BROKER_ID)
        try:
            resp = self._fyers_model.positions()
            positions = []
            for p in resp.get("netPositions", []):
                positions.append(Position(
                    symbol=p.get("symbol", ""),
                    side=PositionSide.LONG if p.get("side", 1) == 1 else PositionSide.SHORT,
                    quantity=abs(int(p.get("netQty", 0))),
                    average_price=float(p.get("avgPrice", 0)),
                    ltp=float(p.get("ltp", 0)),
                    unrealized_pnl=float(p.get("unrealizedProfit", 0)),
                    realized_pnl=float(p.get("realizedProfit", 0)),
                    product_type=p.get("productType", "INTRADAY"),
                    raw=p,
                ))
            return positions
        except Exception as exc:
            raise MarketDataError(
                f"Fyers get_positions failed: {exc}", broker_id=self.BROKER_ID
            ) from exc

    def get_balance(self) -> Balance:
        if self.paper_mode:
            return Balance(available_cash=10_000.0, used_margin=0.0, total_balance=10_000.0)
        if not self._fyers_model:
            raise AuthenticationError("Not authenticated.", broker_id=self.BROKER_ID)
        try:
            resp = self._fyers_model.funds()
            fund = resp.get("fund_limit", [{}])
            def _val(key: str) -> float:
                for item in fund:
                    if item.get("title") == key:
                        return float(item.get("equityAmount", 0))
                return 0.0
            avail = _val("Available Balance") or _val("Available Margin")
            used  = _val("Utilized Margin") or _val("Used Margin")
            total = avail + used
            return Balance(available_cash=avail, used_margin=used, total_balance=total, raw=resp)
        except Exception as exc:
            raise MarketDataError(
                f"Fyers get_balance failed: {exc}", broker_id=self.BROKER_ID
            ) from exc

    def get_order_book(self) -> List[OrderBookEntry]:
        if self.paper_mode:
            return []
        if not self._fyers_model:
            raise AuthenticationError("Not authenticated.", broker_id=self.BROKER_ID)
        try:
            resp   = self._fyers_model.orderbook()
            orders = []
            for o in resp.get("orderBook", []):
                orders.append(OrderBookEntry(
                    order_id=o.get("id", ""),
                    symbol=o.get("symbol", ""),
                    side=OrderSide.BUY if o.get("side", 1) == 1 else OrderSide.SELL,
                    quantity=int(o.get("qty", 0)),
                    price=float(o.get("limitPrice", 0)),
                    status=OrderStatus.OPEN,
                    order_type=OrderType.MARKET if o.get("type", 2) == 2 else OrderType.LIMIT,
                    raw=o,
                ))
            return orders
        except Exception as exc:
            raise MarketDataError(
                f"Fyers get_order_book failed: {exc}", broker_id=self.BROKER_ID
            ) from exc

    # ------------------------------------------------------------------
    # Market data
    # ------------------------------------------------------------------

    def get_market_data(self, symbols: List[str]) -> Dict[str, MarketQuote]:
        if self.paper_mode or not self._fyers_model:
            return {}
        try:
            resp   = self._fyers_model.quotes({"symbols": ",".join(symbols)})
            quotes = {}
            for q in resp.get("d", []):
                v = q.get("v", {})
                sym = q.get("n", "")
                quotes[sym] = MarketQuote(
                    symbol=sym,
                    ltp=float(v.get("lp", 0)),
                    open=float(v.get("open_price", 0)),
                    high=float(v.get("high_price", 0)),
                    low=float(v.get("low_price", 0)),
                    close=float(v.get("prev_close_price", 0)),
                    volume=int(v.get("volume", 0)),
                    bid=float(v.get("bid", 0)),
                    ask=float(v.get("ask", 0)),
                )
            return quotes
        except Exception as exc:
            raise MarketDataError(
                f"Fyers get_market_data failed: {exc}", broker_id=self.BROKER_ID
            ) from exc

    def get_historical_data(
        self, 
        symbol: str, 
        start_date: str, 
        end_date: str, 
        timeframe: str = "5 Min"
    ) -> List[Dict[str, Any]]:
        """Fetch historical data from Fyers API."""
        from datetime import datetime
        
        if not self._fyers_model:
            self.logger.warning("Fyers: not authenticated — cannot fetch historical data from Fyers.")
            return []
            
        try:
            # Map timeframe string to Fyers resolution
            resolution = "5"
            if timeframe == "1 Min": resolution = "1"
            elif timeframe == "3 Min": resolution = "3"
            elif timeframe == "5 Min": resolution = "5"
            elif timeframe == "15 Min": resolution = "15"
            elif timeframe == "30 Min": resolution = "30"
            elif timeframe == "1 Hour": resolution = "60"
            elif timeframe == "1 Day": resolution = "D"
            # Map short symbols to Fyers format
            if symbol == "NIFTY":
                symbol = "NSE:NIFTY50-INDEX"
            elif symbol == "BANKNIFTY":
                symbol = "NSE:NIFTYBANK-INDEX"
            elif symbol == "RELIANCE":
                symbol = "NSE:RELIANCE-EQ"
            elif symbol == "TCS":
                symbol = "NSE:TCS-EQ"
            elif symbol == "INFY":
                symbol = "NSE:INFY-EQ"
            elif ":" not in symbol:
                symbol = f"NSE:{symbol}-EQ"
                
            data = {
                "symbol": symbol,
                "resolution": resolution,
                "date_format": "1",
                "range_from": start_date,
                "range_to": end_date,
                "cont_flag": "1"
            }
            
            resp = self._fyers_model.history(data)
            
            if resp.get("s") != "ok":
                raise MarketDataError(
                    f"Fyers history API failed: {resp.get('message', 'Unknown error')}",
                    broker_id=self.BROKER_ID
                )
                
            candles = resp.get("candles", [])
            result = []
            for c in candles:
                # Fyers returns [timestamp, open, high, low, close, volume]
                result.append({
                    "datetime": datetime.fromtimestamp(c[0]).strftime('%Y-%m-%d %H:%M:%S') if isinstance(c[0], int) else c[0],
                    "open": float(c[1]),
                    "high": float(c[2]),
                    "low": float(c[3]),
                    "close": float(c[4]),
                    "volume": int(c[5])
                })
            return result
        except Exception as exc:
            raise MarketDataError(
                f"Fyers get_historical_data failed: {exc}", broker_id=self.BROKER_ID
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
            logger.info("Fyers [PAPER]: synthetic tick stream for %s", symbols)
            await self._synthetic_stream(symbols, on_tick)
            return
        # Real Fyers websocket — bridge event-based SDK to async callback
        logger.warning("Fyers live websocket not yet wired — using synthetic stream.")
        await self._synthetic_stream(symbols, on_tick)

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    def close(self) -> None:
        self._fyers_model = None
        self._authenticated = False
        logger.debug("FyersBroker.close() called.")
    def close(self) -> None:
        self._fyers_model = None
        self._authenticated = False
        logger.debug("FyersBroker.close() called.")
