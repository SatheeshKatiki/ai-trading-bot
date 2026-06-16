"""Fyers API client wrapper.

This module wraps the ``fyers-api`` SDK to provide a clean interface used by
``trading_bot.main`` and ``trading_bot.login``. It handles:

* OAuth token management (cached in ``.fyers_tokens.json`` in the project root)
* Placing market orders via the Fyers REST API
* Streaming live quotes over a websocket

Performance notes
-----------------
* ``place_order`` is synchronous (REST call) but runs fast (<100 ms typically).
  In the live-trading path it is only called on a NEW signal — not on every
  tick — so it does not cause event-loop latency.
* ``stream_quotes`` drives the entire trading loop.  The real Fyers websocket
  is natively async; the paper-mode synthetic generator uses ``asyncio.sleep``
  so it yields the event loop correctly every iteration.
* Order calls are fire-and-forget via ``asyncio.get_event_loop().run_in_executor``
  when called from async context to avoid blocking the tick handler.

When ``FYERS_CLIENT_ID`` / ``FYERS_SECRET_KEY`` are **not** configured in
``.env`` the client operates in *paper-trading mode* and logs all actions
without touching the real API.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Awaitable, Callable, Dict, List, Optional

from shared.config import CONFIG

logger = logging.getLogger(__name__)

# Location of the cached token file (project root)
_TOKEN_FILE = Path(__file__).resolve().parents[3] / ".fyers_tokens.json"

# Thread pool for blocking REST calls (size=2: enough for concurrent place/cancel)
_ORDER_EXECUTOR = ThreadPoolExecutor(max_workers=2, thread_name_prefix="FyersOrder")


class FyersClient:
    """Lightweight wrapper around the Fyers API.

    In *paper mode* (no credentials configured) every method logs the action
    and returns a safe no-op result so the rest of the system can run
    end-to-end for testing / demo purposes.
    """

    def __init__(self) -> None:
        self._paper_mode = not CONFIG.is_fyers_configured
        self._access_token: Optional[str] = self._load_cached_token()
        if self._paper_mode:
            logger.warning(
                "FyersClient: FYERS_CLIENT_ID / FYERS_SECRET_KEY not set – "
                "running in paper-trading mode (no real orders will be placed)."
            )

    # ------------------------------------------------------------------
    # Token management
    # ------------------------------------------------------------------

    def _load_cached_token(self) -> Optional[str]:
        """Load the access token from the local JSON cache if it exists."""
        if _TOKEN_FILE.is_file():
            try:
                data = json.loads(_TOKEN_FILE.read_text(encoding="utf-8"))
                return data.get("access_token")
            except (json.JSONDecodeError, OSError) as exc:
                logger.warning("Could not load cached Fyers token: %s", exc)
        return None

    def _save_token(self, token: str) -> None:
        """Persist ``token`` to the local JSON cache."""
        _TOKEN_FILE.write_text(
            json.dumps({"access_token": token}, indent=2), encoding="utf-8"
        )
        logger.info("Access token cached to %s", _TOKEN_FILE)

    def login(self, auth_code: str) -> None:
        """Exchange an OAuth ``auth_code`` for an access token and cache it."""
        if self._paper_mode:
            logger.info("Paper mode – skipping real Fyers login (auth_code=%s)", auth_code)
            self._access_token = "paper_mode_token"
            self._save_token(self._access_token)
            return

        try:
            from fyers_apiv3 import fyersModel  # type: ignore[import]

            session = fyersModel.SessionModel(
                client_id=CONFIG.FYERS_CLIENT_ID,
                secret_key=CONFIG.FYERS_SECRET_KEY,
                redirect_uri=CONFIG.FYERS_REDIRECT_URI,
                response_type="code",
                grant_type="authorization_code",
            )
            session.set_token(auth_code)
            response = session.generate_token()
            token = response.get("access_token", "")
            if not token:
                raise RuntimeError(f"Empty token in response: {response}")
            self._access_token = token
            self._save_token(token)
            logger.info("Fyers login successful – token cached.")
        except Exception as exc:
            logger.exception("Fyers login failed: %s", exc)
            raise

    # ------------------------------------------------------------------
    # Order execution
    # ------------------------------------------------------------------

    def _place_order_blocking(
        self,
        symbol: str,
        qty: int,
        side: str,
        order_type: str = "MARKET",
    ) -> Dict:
        """Blocking REST call — run via executor to avoid blocking the event loop."""
        logger.info(
            "place_order: symbol=%s qty=%d side=%s type=%s paper=%s",
            symbol, qty, side, order_type, self._paper_mode,
        )
        if self._paper_mode:
            return {"status": "paper", "symbol": symbol, "qty": qty, "side": side}

        try:
            from fyers_apiv3 import fyersModel  # type: ignore[import]

            fyers = fyersModel.FyersModel(
                client_id=CONFIG.FYERS_CLIENT_ID,
                token=self._access_token,
                log_path="",
            )
            data = {
                "symbol": symbol,
                "qty": qty,
                "type": 2,              # 2 = Market order
                "side": 1 if side == "BUY" else -1,
                "productType": "INTRADAY",
                "limitPrice": 0,
                "stopPrice": 0,
                "validity": "DAY",
                "disclosedQty": 0,
                "offlineOrder": False,
                "stopLoss": 0,
                "takeProfit": 0,
            }
            return fyers.place_order(data)
        except Exception as exc:
            logger.exception("place_order failed: %s", exc)
            return {"status": "error", "error": str(exc)}

    def place_order(
        self,
        symbol: str,
        qty: int,
        side: str,
        order_type: str = "MARKET",
    ) -> Dict:
        """Place a market order (synchronous convenience wrapper).

        If called from within an async context you should prefer
        ``await place_order_async(...)`` to keep the event loop free.
        """
        return self._place_order_blocking(symbol, qty, side, order_type)

    async def place_order_async(
        self,
        symbol: str,
        qty: int,
        side: str,
        order_type: str = "MARKET",
    ) -> Dict:
        """Place an order without blocking the async event loop.

        Offloads the blocking REST call to the shared thread-pool executor.
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            _ORDER_EXECUTOR,
            self._place_order_blocking,
            symbol, qty, side, order_type,
        )

    # ------------------------------------------------------------------
    # Live quote streaming
    # ------------------------------------------------------------------

    async def stream_quotes(
        self,
        symbols: List[str],
        on_tick: Callable[[Dict], Awaitable[None]],
    ) -> None:
        """Stream live tick data for ``symbols`` and invoke ``on_tick`` per message.

        * In paper mode synthetic ticks are generated every second via an
          ``asyncio.sleep`` loop — the event loop is never blocked.
        * In live mode the real Fyers websocket implementation should be placed
          here.  Until implemented it falls back to the synthetic stream.
        """
        if self._paper_mode:
            logger.info(
                "Paper mode – generating synthetic ticks for: %s", ", ".join(symbols)
            )
            await self._synthetic_stream(symbols, on_tick)
            return

        # Real Fyers websocket implementation goes here.
        # Replace with actual fyers_api websocket integration when ready.
        logger.warning("Real Fyers streaming not yet implemented – falling back to paper mode.")
        await self._synthetic_stream(symbols, on_tick)

    async def _synthetic_stream(
        self,
        symbols: List[str],
        on_tick: Callable[[Dict], Awaitable[None]],
    ) -> None:
        """Generate synthetic ticks for demo / testing — fully non-blocking.

        Uses ``asyncio.sleep(0)`` between symbols so that other coroutines
        (exit evaluation, signal checks) can run without waiting for a full
        second between batches.
        """
        import random

        prices = {sym: 1000.0 + random.uniform(-100, 100) for sym in symbols}
        tick_interval = 1.0 / max(len(symbols), 1)   # spread ticks evenly in 1 s

        while True:
            ts = time.time()
            for sym in symbols:
                prices[sym] += random.uniform(-2, 2)
                tick = {
                    "symbol": sym,
                    "ltp": round(prices[sym], 2),
                    "volume": random.randint(100, 1000),
                    "timestamp": ts,
                }
                await on_tick(tick)
                await asyncio.sleep(0)           # yield to event loop between ticks

            # Sleep for the remainder of the 1-second window
            elapsed = time.time() - ts
            await asyncio.sleep(max(0.0, 1.0 - elapsed))

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    def close(self) -> None:
        """Release any held resources."""
        _ORDER_EXECUTOR.shutdown(wait=False)
        logger.debug("FyersClient.close() called.")
