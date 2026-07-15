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

        token = self._load_cached_token() or self.credentials.get("access_token")
        client_id = self.credentials.get("client_id", "")
        logger.info(f"FYERS INIT: client_id={client_id}, token={token}")
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
            "limitPrice":   0 if request.order_type == OrderType.MARKET else request.price,
            "stopPrice":    request.trigger_price,
            "validity":     "DAY",
            "disclosedQty": 0,
            "offlineOrder": False,
            "stopLoss":     0,
            "takeProfit":   0,
        }
        
        # Retry loop for transient broker API errors
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
                    today_str = datetime.now().strftime('%Y-%m-%d')
                    
                    if cache_min_date <= start_date:
                        if end_date < today_str:
                            # Cache has the full range!
                            mask = (df['datetime'] >= start_date) & (df['datetime'] <= f"{end_date} 23:59:59")
                            df_filtered = df.loc[mask]
                            if not df_filtered.empty:
                                return df_filtered.to_dict(orient='records')
                        else:
                            self.logger.info(f"End date ({end_date}) is today or future. Fetching fresh to get live candles.")
                    else:
                        self.logger.info(f"Cache min date ({cache_min_date}) is newer than requested start ({start_date}). Fetching fresh.")
                except Exception as e:
                    self.logger.error("Failed to read cache %s: %s", csv_path, e)
            
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
                
                resp = self._fyers_model.history(data)
                
                if resp.get("s") != "ok":
                    if "No data available" in str(resp):
                        pass # Ignore empty chunks
                    else:
                        logger.warning(f"Fyers history API chunk failed: {resp.get('message', 'Unknown error')}")
                else:
                    all_candles.extend(resp.get("candles", []))
                    
                current_start = current_end + timedelta(days=1)
                # Sleep briefly to avoid API rate limits — use non-blocking sleep
                import time as _time_mod
                _time_mod.sleep(0.1)
                
            if not all_candles:
                self.logger.info("Fyers returned no candles. YFinance fallback is disabled.")
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
                
            # Save to cache
            if result:
                try:
                    df = pd.DataFrame(result)
                    os.makedirs(os.path.dirname(csv_path), exist_ok=True)
                    df.to_csv(csv_path, index=False)
                    self.logger.info("Saved Fyers historical data to cache: %s", csv_path)
                except Exception as e:
                    self.logger.error("Failed to save cache to %s: %s", csv_path, e)
                    
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
    ) -> None:
        logger.info("Fyers: Connecting to API Bridge WebSocket for real market data...")
        import websockets
        import json
        import os
        os.environ["NO_PROXY"] = "localhost,127.0.0.1"
        
        while True:
            try:
                async with websockets.connect(
                    "ws://127.0.0.1:8000/ws/live",
                    ping_interval=20,
                    ping_timeout=20
                ) as ws:
                    logger.info("Connected to API Bridge WebSocket!")
                    while True:
                        data = await ws.recv()
                        msg = json.loads(data)
                        
                        for sym, val in msg.items():
                            if sym in ["trades", "signalsData"]:
                                continue
                            long_sym = sym
                            if sym == "NIFTY":
                                long_sym = "NSE:NIFTY50-INDEX"
                            elif sym == "BANKNIFTY":
                                long_sym = "NSE:NIFTYBANK-INDEX"
                            elif sym == "SENSEX":
                                long_sym = "BSE:SENSEX-INDEX"
                            elif sym == "RELIANCE":
                                long_sym = "NSE:RELIANCE-EQ"
                            elif ":" not in sym:
                                long_sym = f"NSE:{sym}-EQ"
                                
                            if long_sym in symbols:
                                import time
                                await on_tick({"symbol": long_sym, "ltp": val["lp"], "timestamp": int(time.time()), "volume": 0})
                                
            except Exception as e:
                logger.error("API Bridge WebSocket disconnected or failed: %s. Retrying in 5 seconds...", e)
                await asyncio.sleep(5)

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    def close(self) -> None:
        self._fyers_model = None
        self._authenticated = False
        logger.debug("FyersBroker.close() called.")
