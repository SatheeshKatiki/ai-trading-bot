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
from typing import Any, Awaitable, Callable, Dict, List, Optional

import requests
from requests.adapters import HTTPAdapter

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

#: Default ceiling (seconds) on any single HTTP request made through a
#: FyersModel's session -- see _TimeoutHTTPAdapter's docstring.
_DEFAULT_REQUEST_TIMEOUT_S = 10


class _TimeoutHTTPAdapter(HTTPAdapter):
    """Injects a default request timeout when the caller doesn't specify one.

    Root cause (found live, 2026-08-13): the vendored fyers_apiv3 SDK's
    FyersModel.get_call() (and its GET/POST/DELETE/PATCH/PUT siblings) call
    self.session.get(...)/.post(...) etc. with no `timeout=` anywhere. A DNS
    resolution failure fails fast, but a hung TCP connect -- a plausible
    state mid-network-recovery -- could block that call indefinitely.
    trading_bot/main.py calls broker.get_market_data() synchronously and
    unwrapped directly on its asyncio event loop; a single hung call there
    is the confirmed root cause of a ~39-minute total engine freeze
    (14:18-14:57 IST), correlated with an 11-entry DNS failure burst for
    api-t1.fyers.in in the same window. This mounts a hard ceiling on every
    request made through the model's session -- without editing the
    vendored SDK -- so a slow network can no longer hang forever; Phase 2's
    asyncio.to_thread wrapping in main.py is the second, independent layer
    that keeps even a still-slow (but now bounded) call from blocking the
    event loop itself.
    """

    def __init__(self, *args: Any, timeout: float = _DEFAULT_REQUEST_TIMEOUT_S, **kwargs: Any) -> None:
        self._timeout = timeout
        super().__init__(*args, **kwargs)

    def send(self, request, **kwargs):  # type: ignore[override]
        if kwargs.get("timeout") is None:
            kwargs["timeout"] = self._timeout
        return super().send(request, **kwargs)


def _mount_default_timeout(fyers_model: Any, timeout: float = _DEFAULT_REQUEST_TIMEOUT_S) -> None:
    """Mount `_TimeoutHTTPAdapter` onto a freshly-built FyersModel's
    `requests.Session`, for both schemes. Safe no-op if the model doesn't
    expose a `.session` (e.g. a stub/mock in tests)."""
    session = getattr(fyers_model, "session", None)
    if not isinstance(session, requests.Session):
        return
    adapter = _TimeoutHTTPAdapter(timeout=timeout)
    session.mount("https://", adapter)
    session.mount("http://", adapter)


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
            credential_fields=[  # type: ignore
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
        self._fyers_model: Any = None   # Lazy-loaded after authenticate()

    # ------------------------------------------------------------------
    # Authentication
    # ------------------------------------------------------------------

    def _create_fyers_model(self, client_id: str, token: str) -> Optional[Any]:
        """Safely instantiate and configure FyersModel with default timeouts."""
        if not token:
            return None
        try:
            try:
                from fyers_apiv3 import fyersModel  # type: ignore[import]
            except ImportError:
                from fyers_api import fyersModel  # type: ignore[import]

            effective_client_id = client_id or self.credentials.get("client_id") or self.credentials.get("app_id", "")
            fyers_cls: Any = getattr(fyersModel, "FyersModel", None)
            if fyers_cls is None:
                return None

            kwargs: Dict[str, Any] = {
                "client_id": effective_client_id,
                "token": token,
                "log_path": "",
            }
            try:
                model = fyers_cls(**kwargs)
            except TypeError:
                kwargs.pop("log_path", None)
                model = fyers_cls(**kwargs)

            _mount_default_timeout(model)
            return model
        except Exception as exc:
            logger.error("Failed to initialize FyersModel SDK: %s", exc)
            return None

    def authenticate(self) -> bool:
        """Authenticate with Fyers using the stored credentials."""
        if self.paper_mode:
            self._authenticated = True
            logger.info("Fyers: paper mode — skipping real authentication.")
            # Initialize model for data fetching in paper mode if token exists!
            token = self._load_cached_token()
            if token:
                self._fyers_model = self._create_fyers_model(
                    client_id=self.credentials.get("client_id", ""),
                    token=token,
                )
                if self._fyers_model:
                    logger.info("Fyers: Initialized model in paper mode for data fetching.")
            return True

        token = self._load_cached_token() or self.credentials.get("access_token")
        client_id = self.credentials.get("client_id", "")
        logger.info(
            "FYERS INIT: client_id=%s, token=%s",
            client_id, "<redacted>" if token else "<missing>",
        )
        if not token:
            logger.warning(
                "Fyers: no access_token found — call get_login_url() then complete_login()."
            )
            return False

        model = self._create_fyers_model(client_id=client_id, token=token)
        if model is None:
            raise AuthenticationError(
                "Fyers SDK init failed: Could not instantiate FyersModel", broker_id=self.BROKER_ID
            )
        self._fyers_model = model
        self._authenticated = True
        logger.info("Fyers: authenticated successfully.")
        return True

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
                kwargs = {
                    "client_id": self.credentials.get("client_id", ""),
                    "secret_key": self.credentials.get("secret_key", ""),
                    "redirect_uri": self.credentials.get("redirect_uri", "https://localhost"),
                    "response_type": "code",
                    "grant_type": "authorization_code",
                }
                session = fyersModel.SessionModel(**kwargs)  # type: ignore
            except AttributeError:
                # Fallback for versions where SessionModel is in the session module
                from fyers_api import session as fyers_session  # type: ignore
                kwargs = {
                    "client_id": self.credentials.get("client_id", ""),
                    "secret_key": self.credentials.get("secret_key", ""),
                    "redirect_uri": self.credentials.get("redirect_uri", "https://localhost"),
                    "response_type": "code",
                    "grant_type": "authorization_code",
                }
                session = fyers_session.SessionModel(**kwargs)  # type: ignore
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
                kwargs = {
                    "client_id": self.credentials.get("client_id", ""),
                    "secret_key": self.credentials.get("secret_key", ""),
                    "redirect_uri": self.credentials.get("redirect_uri", "https://localhost"),
                    "response_type": "code",
                    "grant_type": "authorization_code",
                }
                session = fyersModel.SessionModel(**kwargs)  # type: ignore
            except AttributeError:
                from fyers_api import session as fyers_session  # type: ignore
                kwargs = {
                    "client_id": self.credentials.get("client_id", ""),
                    "secret_key": self.credentials.get("secret_key", ""),
                    "redirect_uri": self.credentials.get("redirect_uri", "https://localhost"),
                    "response_type": "code",
                    "grant_type": "authorization_code",
                }
                session = fyers_session.SessionModel(**kwargs)  # type: ignore
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
        from .token_cache import load_token
        return load_token("fyers")

    def _refresh_fyers_model(self) -> bool:
        """Rebuild `_fyers_model` from whatever token is currently cached
        on disk. Returns whether a token was found to rebuild from.

        Root cause (found live, 2026-08-12): `_fyers_model` is built once
        in `authenticate()` and never touched again for the rest of this
        process's life. If ANYTHING else re-authenticates Fyers afterward
        -- e.g. api_bridge.py's own auto-login running again on its own
        restart, a completely separate process -- Fyers invalidates the
        old session token server-side. This long-running process's model
        then silently fails every call using it, with nothing to detect
        or recover from that short of a full process restart. Live
        incident: a real PE entry signal held for 54 minutes straight
        (12:05-13:00 IST), `get_market_data` returning an empty dict on
        every single tick because of exactly this, blocking the trade
        the entire time with zero visible cause beyond a generic
        "skipping this entry" warning -- confirmed by hand that the
        *current* cached token worked fine when used fresh, proving the
        problem was this object's own staleness, not a real outage.
        """
        token = self._load_cached_token()
        if not token:
            return False
        
        client_id = self.credentials.get("client_id") or self.credentials.get("app_id", "")
        model = self._create_fyers_model(client_id=client_id, token=token)
        if model is not None:
            self._fyers_model = model
            self._authenticated = True
            logger.info("Fyers: refreshed active model with latest cached token.")
            return True
        return False

    def _save_cached_token(self, token: str) -> None:
        from .token_cache import save_token
        save_token(token, "fyers")

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
            "type":         {OrderType.MARKET: 2, OrderType.LIMIT: 1, OrderType.SL_M: 3, OrderType.SL: 4}.get(request.order_type, 1),
            "side":         1 if request.side == OrderSide.BUY else -1,
            "productType":  request.product_type.value,
            "limitPrice":   0 if request.order_type == OrderType.MARKET else request.price,
            "stopPrice":    request.trigger_price,
            "validity":     "DAY",
            "disclosedQty": 0,
            "offlineOrder": False,
            "stopLoss":     0,
            "takeProfit":   0,
        }
        
        # Retry loop for transient broker API errors.
        #
        # A network failure can happen AFTER Fyers has already received and
        # accepted the order but BEFORE the success response reaches us
        # (dropped response, timeout waiting on the socket, etc). Blindly
        # resubmitting the same payload in that case places a second,
        # duplicate real-money order. Fyers' order-placement API has no
        # client-supplied idempotency key, so before each retry we check the
        # live order book for an order that already matches this request —
        # if the broker actually received the previous attempt, it'll be
        # sitting there and we reuse it instead of submitting again.
        max_retries = 3
        for attempt in range(max_retries):
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
                existing = self._find_matching_pending_order(request)
                if existing is not None:
                    logger.warning(
                        "Fyers place_order raised %s but a matching order %s "
                        "already exists in the order book — the broker "
                        "likely received the previous attempt. Returning it "
                        "instead of resubmitting to avoid a duplicate order.",
                        exc, existing.order_id,
                    )
                    return existing
                if attempt < max_retries - 1:
                    logger.warning(f"Fyers place_order failed, retrying ({attempt+1}/{max_retries})... Error: {exc}")
                    time.sleep(0.5)
                else:
                    raise BrokerConnectionError(
                        f"Fyers place_order failed after {max_retries} attempts: {exc}", broker_id=self.BROKER_ID
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
        if self.paper_mode or not self._fyers_model:
            return []
        try:
            resp = self._fyers_model.positions()
            if resp.get("code") != 200:
                raise MarketDataError(
                    f"Fyers positions error: {resp.get('message')}",
                    broker_id=self.BROKER_ID
                )
            positions = []
            for p in resp.get("netPositions", []):
                qty = int(p.get("netQty", 0))
                if qty == 0:
                    continue
                positions.append(Position(
                    symbol=p.get("symbol", ""),
                    side=PositionSide.LONG if qty > 0 else PositionSide.SHORT,
                    quantity=abs(qty),
                    average_price=float(p.get("avgPrice", 0)),
                    ltp=float(p.get("ltp", 0)),
                    unrealized_pnl=float(p.get("unrealized_profit", 0)),
                    realized_pnl=float(p.get("realized_profit", 0)),
                    product_type=p.get("productType", "INTRADAY"),
                    raw=p,
                ))
            return positions
        except Exception as exc:
            raise MarketDataError(
                f"Fyers get_positions failed: {exc}", broker_id=self.BROKER_ID
            ) from exc

    def get_lot_size(self, symbol: str) -> int:
        """Fetch lot size from broker dynamically if cached, otherwise fallback."""
        if hasattr(self, '_lot_size_cache') and self._lot_size_cache:
            return self._lot_size_cache.get(symbol, super().get_lot_size(symbol))
        return super().get_lot_size(symbol)

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
            
            def _map_status(fyers_status: int) -> OrderStatus:
                if fyers_status == 2: return OrderStatus.COMPLETE
                if fyers_status in (1, 6): return OrderStatus.CANCELLED
                if fyers_status == 4: return OrderStatus.REJECTED
                return OrderStatus.OPEN

            for o in resp.get("orderBook", []):
                orders.append(OrderBookEntry(
                    order_id=o.get("id", ""),
                    symbol=o.get("symbol", ""),
                    side=OrderSide.BUY if o.get("side", 1) == 1 else OrderSide.SELL,
                    quantity=int(o.get("qty", 0)),
                    price=float(o.get("limitPrice", 0)),
                    traded_price=float(o.get("tradedPrice", 0.0)),
                    status=_map_status(o.get("status", 5)),
                    order_type=OrderType.MARKET if o.get("type", 2) == 2 else OrderType.LIMIT,
                    raw=o,
                ))
            return orders
        except Exception as exc:
            raise MarketDataError(
                f"Fyers get_order_book failed: {exc}", broker_id=self.BROKER_ID
            ) from exc

    def get_order_status(self, order_id: str) -> Optional[OrderBookEntry]:
        """Fetch the exact status and fill details for a specific order ID."""
        if self.paper_mode:
            return None
        orders = self.get_order_book()
        for order in orders:
            if order.order_id == order_id:
                return order
        return None

    # ------------------------------------------------------------------
    # Market data
    # ------------------------------------------------------------------

    def get_market_data(self, symbols: List[str]) -> Dict[str, MarketQuote]:
        if not self._fyers_model:
            return {}
        try:
            resp = self._fyers_model.quotes({"symbols": ",".join(symbols)})
            # fyers_apiv3's get_call() never raises on a stale/invalid
            # session -- it always returns a dict, just one shaped
            # {"s": "error", ...} instead of the usual {"d": [...]}. See
            # _refresh_fyers_model()'s docstring for why this happens and
            # why a plain retry with the SAME model would fail identically.
            if resp.get("s") == "error":
                logger.warning(
                    "Fyers /quotes returned an error (%s) -- refreshing "
                    "the session from the current cached token and "
                    "retrying once.", resp.get("message"),
                )
                if self._refresh_fyers_model():
                    resp = self._fyers_model.quotes({"symbols": ",".join(symbols)})
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
        """Fetch historical data from Fyers API with automatic pagination for large ranges (1+ years)."""
        from datetime import datetime, timedelta
        
        if not self._fyers_model:
            self.logger.warning("Fyers: not authenticated — cannot fetch historical data from Fyers. YFinance fallback is disabled.")
            return []
            
        try:
            # Map timeframe string to Fyers resolution
            resolution = "5"
            if timeframe == "30 Sec": resolution = "30S"
            elif timeframe == "1 Min": resolution = "1"
            elif timeframe == "3 Min": resolution = "3"
            elif timeframe == "5 Min": resolution = "5"
            elif timeframe == "15 Min": resolution = "15"
            elif timeframe == "30 Min": resolution = "30"
            elif timeframe == "1 Hour": resolution = "60"
            elif timeframe == "1 Day": resolution = "D"
            elif timeframe == "1 Week": resolution = "W"
            elif timeframe == "1 Month": resolution = "M"
            
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
                
            start_dt = datetime.strptime(start_date, '%Y-%m-%d')
            end_dt = datetime.strptime(end_date, '%Y-%m-%d')
            
            import os
            import pandas as pd
            
            # Check CSV Cache First
            clean_sym = symbol.replace(':', '_')
            clean_tf = timeframe.replace(' ', '')
            csv_path = os.path.join(os.path.dirname(__file__), "..", "data", f"{clean_sym}_{clean_tf}.csv")
            
            if os.path.exists(csv_path):
                self.logger.info("FyersBroker: Checking historical data from cache %s", csv_path)
                try:
                    df = pd.read_csv(csv_path)
                    
                    # Verify if the cache covers the requested start_date
                    cache_min_date = df['datetime'].min()[:10]  # Get YYYY-MM-DD
                    cache_max_date = df['datetime'].max()[:10]  # Get YYYY-MM-DD
                    today_str = datetime.now().strftime('%Y-%m-%d')
                    
                    if cache_min_date <= start_date:
                        # Allow cache fully ONLY if end_date is strictly in the past AND cache covers it
                        if end_date < today_str and cache_max_date >= end_date:
                            mask = (df['datetime'] >= start_date) & (df['datetime'] <= f"{end_date} 23:59:59")
                            df_filtered = df.loc[mask]
                            if not df_filtered.empty:
                                self.logger.info("FyersBroker: Cache hit! Range fully covered.")
                                return df_filtered.to_dict(orient='records')
                        
                        # We have partial cache OR end_date is today (ongoing day). We must fetch from API.
                        self.logger.info(f"Cache max date ({cache_max_date}). Fetching fresh data for remaining/ongoing days.")
                        
                        # Adjust start_dt so we don't refetch everything!
                        if cache_max_date < today_str:
                            missing_start_dt = datetime.strptime(cache_max_date, '%Y-%m-%d') + timedelta(days=1)
                        else:
                            missing_start_dt = datetime.strptime(cache_max_date, '%Y-%m-%d')
                            
                        if missing_start_dt <= end_dt:
                            start_dt = missing_start_dt
                            self.logger.info(f"Adjusted API fetch start date to {start_dt.strftime('%Y-%m-%d')}")
                    else:
                        self.logger.info(f"Cache min date ({cache_min_date}) is newer than requested start ({start_date}). Fetching fresh.")
                        df = None # Discard cache, fetch everything
                except Exception as e:
                    self.logger.error("Failed to read cache %s: %s", csv_path, e)
                    df = None
            else:
                df = None
            
            all_candles = []
            current_start = start_dt
            
            # Fyers limits intraday data to 100 days per request. We chunk it.
            while current_start <= end_dt:
                current_end = current_start + timedelta(days=99)
                if current_end > end_dt:
                    current_end = end_dt
                    
                data = {
                    "symbol": symbol,
                    "resolution": resolution,
                    "date_format": "1",
                    "range_from": current_start.strftime('%Y-%m-%d'),
                    "range_to": current_end.strftime('%Y-%m-%d'),
                    "cont_flag": "1"
                }
                
                import time as _time_mod
                chunk_success = False
                
                for attempt in range(3):
                    resp = self._fyers_model.history(data)
                    if resp.get("s") == "ok":
                        all_candles.extend(resp.get("candles", []))
                        chunk_success = True
                        break
                    elif "No data available" in str(resp) or resp.get("s") == "no_data":
                        # "no_data" is Fyers' normal response for a range with no
                        # candles yet (e.g. today's still-forming bars) — not an
                        # error, so don't burn retries/backoff on it.
                        chunk_success = True # Ignore empty chunks gracefully
                        break
                    else:
                        err_msg = resp.get('message', 'Unknown error')
                        logger.warning(f"Fyers history API chunk failed (Attempt {attempt+1}): {err_msg}")
                        _time_mod.sleep(1.0 * (attempt + 1)) # Exponential backoff: 1s, 2s
                        
                if not chunk_success:
                    self.logger.warning(f"Failed to fetch Fyers history chunk {data['range_from']} to {data['range_to']}. Aborting API fetch and falling back to cache if available.")
                    break # Stop fetching, use whatever we fetched + cache
                    
                current_start = current_end + timedelta(days=1)
                # Sleep briefly to avoid API rate limits for subsequent requests
                _time_mod.sleep(0.5)
                
            if not all_candles:
                self.logger.info("Fyers API returned no new candles.")
                if df is not None and not df.empty:
                    self.logger.info("Returning strictly from local cache.")
                    mask = (df['datetime'] >= start_date) & (df['datetime'] <= f"{end_date} 23:59:59")
                    final_filtered = df.loc[mask]
                    return final_filtered.to_dict(orient='records')
                return []
                
            result = []
            for c in all_candles:
                # Fyers returns [timestamp, open, high, low, close, volume]
                result.append({
                    "datetime": datetime.fromtimestamp(c[0]).strftime('%Y-%m-%d %H:%M:%S') if isinstance(c[0], int) else c[0],
                    "open": float(c[1]),
                    "high": float(c[2]),
                    "low": float(c[3]),
                    "close": float(c[4]),
                    "volume": int(c[5])
                })
                
            # Save to cache and combine with existing
            if result:
                try:
                    new_df = pd.DataFrame(result)
                    os.makedirs(os.path.dirname(csv_path), exist_ok=True)
                    if df is not None and not df.empty:
                        # Append to existing cache and drop duplicates
                        combined_df = pd.concat([df, new_df]).drop_duplicates(subset=['datetime']).sort_values('datetime')
                        combined_df.to_csv(csv_path, index=False)
                        self.logger.info("Appended missing Fyers historical data to cache: %s", csv_path)
                        
                        # Apply start/end filter on the COMBINED dataset
                        mask = (combined_df['datetime'] >= start_date) & (combined_df['datetime'] <= f"{end_date} 23:59:59")
                        final_filtered = combined_df.loc[mask]
                        return final_filtered.to_dict(orient='records')
                    else:
                        new_df.to_csv(csv_path, index=False)
                        self.logger.info("Saved Fyers historical data to fresh cache: %s", csv_path)
                        
                        # Apply start/end filter on the fresh dataset
                        mask = (new_df['datetime'] >= start_date) & (new_df['datetime'] <= f"{end_date} 23:59:59")
                        final_filtered = new_df.loc[mask]
                        return final_filtered.to_dict(orient='records')
                except Exception as e:
                    self.logger.error("Failed to save cache to %s: %s", csv_path, e)
                    
            elif df is not None and not df.empty:
                # If no new candles but cache exists, just return the filtered cache
                mask = (df['datetime'] >= start_date) & (df['datetime'] <= f"{end_date} 23:59:59")
                return df.loc[mask].to_dict(orient='records')
                    
            return result
        except Exception as exc:
            logger.warning(f"Fyers get_historical_data exception: {exc}. Falling back to base broker...")
            try:
                return super().get_historical_data(symbol, start_date, end_date, timeframe)
            except Exception as super_exc:
                raise MarketDataError(
                    f"Fyers get_historical_data fallback failed: {super_exc}", broker_id=self.BROKER_ID
                ) from super_exc

    # ------------------------------------------------------------------
    # Streaming
    # ------------------------------------------------------------------

    async def stream_quotes(
        self,
        symbols: List[str],
        on_tick: Callable[[Dict[str, Any]], Awaitable[None]],
        on_reconnect: Optional[Callable[[], Awaitable[None]]] = None,
    ) -> None:
        logger.info("Fyers: Connecting to API Bridge WebSocket for real market data...")
        import websockets
        import os
        os.environ["NO_PROXY"] = "localhost,127.0.0.1"

        # Root-cause fix: /ws/live has required a valid session ?token=
        # ever since the Critical #2 auth-gate fix went in (api_bridge.py's
        # require_session_auth doesn't cover WebSocket handshakes, so the
        # route checks a query-param token itself instead). The frontend's
        # browser client already goes through /api/ws-token for this, but
        # this internal, same-machine, backend-to-backend connection never
        # sent any token at all — meaning the live engine has never
        # actually been able to receive a single real tick since that fix
        # landed, silently retrying this connection forever. Mint one
        # internal session token once (reused across reconnects, not
        # re-created every retry) via the same file-backed session store
        # api_bridge.py's validate_session() reads.
        from shared.security.sessions import create_session
        internal_token = create_session("trading_engine_internal", ttl_seconds=90 * 24 * 60 * 60)
        ws_url = f"ws://127.0.0.1:8000/ws/live?token={internal_token}"

        retry_count = 0
        last_log_time = 0.0

        while True:
            try:
                if on_reconnect:
                    await on_reconnect()
                async with websockets.connect(
                    ws_url,
                    ping_interval=20,
                    ping_timeout=20
                ) as ws:
                    logger.info("Connected to API Bridge WebSocket!")
                    retry_count = 0  # reset on successful connect
                    while True:
                        data = await ws.recv()
                        msg = json.loads(data)
                        
                        raw_ticks = msg.get("raw_ticks", {})
                        if not raw_ticks:
                            continue
                            
                        for sym, val in raw_ticks.items():
                            # Emit ALL raw ticks so both base indices and options reach the aggregator!
                            await on_tick({"symbol": sym, "ltp": val["lp"], "timestamp": int(time.time()), "volume": 0})
            except Exception as e:
                retry_count += 1
                now = time.time()
                # Exponential backoff capped at 25 seconds
                backoff = min(25, 3 + (retry_count * 2))
                
                # Log once at start or every 60 seconds to prevent slamming log file
                if now - last_log_time >= 60.0 or retry_count <= 2:
                    logger.warning("API Bridge WebSocket disconnected (%s). Retrying in %ds (attempt #%d)...", e, backoff, retry_count)
                    last_log_time = now
                else:
                    logger.debug("API Bridge WebSocket reconnecting in %ds (attempt #%d)...", backoff, retry_count)
                    
                await asyncio.sleep(backoff)

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    def close(self) -> None:
        self._fyers_model = None
        self._authenticated = False
        logger.debug("FyersBroker.close() called.")
