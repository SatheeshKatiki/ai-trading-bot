"""Abstract broker interface — every concrete adapter must implement this.

Design rules
------------
* Trading logic (main.py, strategies, risk manager) imports ONLY from this
* module and ``brokers.models``.  No vendor SDK ever leaks into application code.
* Each abstract method has a concrete default implementation where a safe
* no-op or synthetic fallback makes sense (e.g. ``stream_quotes`` in paper
* mode).
* ``place_order`` (sync) and ``place_order_async`` (async / non-blocking)
* are both required so the trading engine can choose the right variant.
"""

from __future__ import annotations

import asyncio
import logging
import random
import time
from abc import ABC, abstractmethod
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Awaitable, Callable, Dict, List, Optional

from .models import (
    Balance, BrokerInfo, MarketQuote, OrderBookEntry,
    OrderRequest, OrderResponse, OrderSide, OrderStatus,
    Position,
)

logger = logging.getLogger(__name__)

# Shared thread-pool for offloading blocking SDK calls
_BROKER_EXECUTOR = ThreadPoolExecutor(max_workers=2, thread_name_prefix="BrokerIO")


class BaseBroker(ABC):
    """Abstract base for all broker adapters.

    Lifecycle
    ---------
    1. Instantiated by ``BrokerFactory.get_active_broker()``.
    2. ``authenticate()`` is called once to establish a session.
    3. During trading the bot calls ``stream_quotes()`` and ``place_order_async()``.
    4. On shutdown ``close()`` releases any open connections.
    """

    # Subclasses must set these class-level attributes
    BROKER_ID:    str = ""   # e.g. "fyers"
    DISPLAY_NAME: str = ""   # e.g. "Fyers"

    def __init__(self, credentials: Dict[str, str], paper_mode: bool = False) -> None:
        """
        Parameters
        ----------
        credentials : dict
            Flat key→value map of credential fields (see BrokerInfo.credential_fields).
        paper_mode : bool
            When True the broker runs in simulation mode — no real API calls.
        """
        self.credentials  = credentials
        self.paper_mode   = paper_mode
        self._authenticated = False
        self.logger = logging.getLogger(f"brokers.{self.BROKER_ID}")
        if paper_mode:
            self.logger.warning(
                "%s: credentials not set or paper_mode=True — "
                "running in paper-trading simulation mode.",
                self.DISPLAY_NAME,
            )

    # ------------------------------------------------------------------
    # Broker metadata (override in subclass to provide rich info)
    # ------------------------------------------------------------------

    @classmethod
    def info(cls) -> BrokerInfo:
        """Return static metadata about this broker."""
        return BrokerInfo(
            broker_id=cls.BROKER_ID,
            display_name=cls.DISPLAY_NAME,
        )

    # ------------------------------------------------------------------
    # Authentication
    # ------------------------------------------------------------------

    @abstractmethod
    def authenticate(self) -> bool:
        """Establish a session with the broker.

        Returns True on success, False on recoverable failure.
        Raises ``AuthenticationError`` for unrecoverable failures.
        """

    def get_login_url(self) -> Optional[str]:
        """Return OAuth login URL for brokers that require browser-based login.

        Returns None for brokers that authenticate directly (e.g. Angel One).
        Override in subclasses that need it.
        """
        return None

    def complete_login(self, auth_code: str) -> bool:
        """Complete the OAuth flow with the code received after browser login.

        Override in subclasses that use OAuth (Fyers, Kite).
        Returns True on success.
        """
        return False

    @property
    def is_authenticated(self) -> bool:
        return self._authenticated

    # ------------------------------------------------------------------
    # Order management
    # ------------------------------------------------------------------

    @abstractmethod
    def place_order(self, request: OrderRequest) -> OrderResponse:
        """Place an order synchronously (blocking).

        Prefer ``place_order_async`` inside async code.
        """

    async def place_order_async(self, request: OrderRequest) -> OrderResponse:
        """Place an order without blocking the asyncio event loop.

        Default implementation offloads ``place_order`` to the shared
        thread-pool.  Subclasses may override with a native async SDK call.
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(_BROKER_EXECUTOR, self.place_order, request)

    @abstractmethod
    def cancel_order(self, order_id: str) -> Dict[str, Any]:
        """Cancel a pending order by ID."""

    def modify_order(
        self,
        order_id: str,
        quantity: Optional[int] = None,
        price: Optional[float] = None,
        trigger_price: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Modify a pending order.  Not all brokers support this; raises
        ``UnsupportedOperationError`` by default."""
        from .exceptions import UnsupportedOperationError
        raise UnsupportedOperationError(
            f"{self.DISPLAY_NAME} does not support order modification via this adapter.",
            broker_id=self.BROKER_ID,
        )

    # ------------------------------------------------------------------
    # Account information
    # ------------------------------------------------------------------

    @abstractmethod
    def get_positions(self) -> List[Position]:
        """Return all open (intraday) positions."""

    @abstractmethod
    def get_balance(self) -> Balance:
        """Return available funds and margin utilisation."""

    @abstractmethod
    def get_order_book(self) -> List[OrderBookEntry]:
        """Return today's orders (pending + completed)."""

    # ------------------------------------------------------------------
    # Market data
    # ------------------------------------------------------------------

    @abstractmethod
    def get_market_data(self, symbols: List[str]) -> Dict[str, MarketQuote]:
        """Fetch real-time quotes for a list of symbols.

        Returns a dict keyed by symbol, each value a ``MarketQuote``.
        """

    def get_historical_data(
        self, 
        symbol: str, 
        start_date: str, 
        end_date: str, 
        timeframe: str = "5 Min"
    ) -> List[Dict[str, Any]]:
        """Fetch historical data. 
        
        First attempts to load from a local CSV cache under `trading-system/data` if available.
        Otherwise, falls back to fetching via yfinance.
        """
        import os
        import pandas as pd
        from datetime import datetime
        
        # 1. Fetch via yfinance (Broker API is handled by subclasses)
        self.logger.info(f"Fetching history for {symbol} via yfinance fallback.")
        import yfinance as yf
        
        # Clean symbol to find correct yfinance ticker
        clean_symbol = symbol.split(":")[-1]
        clean_symbol = clean_symbol.replace("-EQ", "").replace("-INDEX", "")
        
        ticker_symbol = clean_symbol
        if not clean_symbol.endswith(".NS") and not clean_symbol.endswith(".BO"):
            if any(n in clean_symbol.upper() for n in ["NIFTY", "NSEI"]):
                ticker_symbol = "^NSEI"
            elif any(s in clean_symbol.upper() for s in ["SENSEX", "BSESN"]):
                ticker_symbol = "^BSESN"
            else:
                ticker_symbol = f"{clean_symbol}.NS"
                
        try:
            from datetime import datetime, timedelta
            interval = "1m"
            max_days = 730
            if timeframe == "30 Sec": interval = "1m"; max_days = 7
            elif timeframe == "1 Min": interval = "1m"; max_days = 7
            elif timeframe == "3 Min": interval = "2m"; max_days = 60
            elif timeframe == "5 Min": interval = "5m"; max_days = 60
            elif timeframe == "15 Min": interval = "15m"; max_days = 60
            elif timeframe == "1 Hour": interval = "60m"; max_days = 730
            elif timeframe == "1 Day": interval = "1d"; max_days = 3650
            elif timeframe == "1 Week": interval = "1wk"; max_days = 3650
            elif timeframe == "1 Month": interval = "1mo"; max_days = 3650
            
            # Truncate start_date to max_days allowed by yfinance (relative to today)
            start_dt = datetime.strptime(start_date, '%Y-%m-%d')
            end_dt = datetime.strptime(end_date, '%Y-%m-%d')
            
            today_dt = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
            oldest_allowed_dt = today_dt - timedelta(days=max_days - 1)
            
            if start_dt < oldest_allowed_dt:
                start_dt = oldest_allowed_dt
                start_date = start_dt.strftime('%Y-%m-%d')
                self.logger.info(f"yfinance limit: truncated start_date to {start_date} for interval {interval}")
                
            if end_dt < oldest_allowed_dt:
                self.logger.warning(f"yfinance limit: requested end_date {end_date} is older than allowed {max_days} days. Returning empty.")
                return []
            
            ticker = yf.Ticker(ticker_symbol)
            df = ticker.history(start=start_date, end=end_date, interval=interval)
            
            if df.empty:
                return []
                
            data = []
            for index, row in df.iterrows():
                data.append({
                    "datetime": index.strftime('%Y-%m-%d %H:%M:%S'),
                    "close": float(row['Close']),
                    "high": float(row['High']),
                    "low": float(row['Low']),
                    "open": float(row['Open']),
                    "volume": int(row['Volume'])
                })
            return data
        except Exception as e:
            self.logger.error(f"Failed to fetch yfinance fallback: {e}")
            return []

    # ------------------------------------------------------------------
    # Streaming  (real-time tick feed)
    # ------------------------------------------------------------------

    @abstractmethod
    async def stream_quotes(
        self,
        symbols: List[str],
        on_tick: Callable[[Dict[str, Any]], Awaitable[None]],
    ) -> None:
        """Stream live ticks and invoke ``on_tick`` for each message.

        This method should run indefinitely until cancelled.
        The tick dict must contain at minimum: symbol, ltp, volume, timestamp.
        """

    async def _synthetic_stream(
        self,
        symbols: List[str],
        on_tick: Callable[[Dict[str, Any]], Awaitable[None]],
        tick_interval: float = 1.0,
    ) -> None:
        """Paper-mode fallback: generates realistic random-walk ticks.

        Yields the event loop between each symbol so other coroutines
        (exit evaluation, signal checks) are never starved.
        """
        prices = {sym: 1000.0 + random.uniform(-100, 100) for sym in symbols}
        interval_per_sym = tick_interval / max(len(symbols), 1)

        while True:
            ts = time.time()
            for sym in symbols:
                prices[sym] += random.uniform(-2.0, 2.0)
                prices[sym] = max(prices[sym], 1.0)
                tick: Dict[str, Any] = {
                    "symbol":    sym,
                    "ltp":       round(prices[sym], 2),
                    "volume":    random.randint(100, 5000),
                    "timestamp": ts,
                    "bid":       round(prices[sym] - 0.05, 2),
                    "ask":       round(prices[sym] + 0.05, 2),
                }
                await on_tick(tick)
                await asyncio.sleep(0)          # yield between symbols

            elapsed = time.time() - ts
            await asyncio.sleep(max(0.0, tick_interval - elapsed))

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    @abstractmethod
    def close(self) -> None:
        """Release websocket connections, threads, and other resources."""

    def __repr__(self) -> str:
        mode = "PAPER" if self.paper_mode else "LIVE"
        auth = "✓" if self._authenticated else "✗"
        return f"<{self.__class__.__name__} mode={mode} auth={auth}>"
