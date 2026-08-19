from __future__ import annotations

from fastapi import FastAPI, Query, HTTPException, BackgroundTasks, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from datetime import datetime, timedelta, timezone
import logging
import logging.handlers
import pandas as pd
import numpy as np
import json
import os
import time
import pytz
from typing import Optional, List, Dict, Any

# Module-level logger — NEVER use print() in async FastAPI code
logger = logging.getLogger("api_bridge")

# Root-cause fix (chart timestamp audit): trade timestamps written to
# state.db must be consistently tagged so every consumer (this file's own
# WebSocket feed, the frontend's "today" filters, chart trade markers) can
# rely on a single, unambiguous convention. trading_bot/main.py already
# tags every trade it records with real IST (Asia/Kolkata) via this same
# constant; this endpoint used to tag its own manual/dashboard order trades
# with UTC instead, an inconsistency that could shift a trade's apparent
# calendar date by up to 5.5 hours' worth of look-alike-but-wrong entries
# for any consumer that reads the raw string's calendar date directly.
_IST = pytz.timezone("Asia/Kolkata")

# ---------------------------------------------------------------------------
# Log rotation — cap fyersApi.log at 5 MB × 3 backups (≈ 20 MB total max)
# ---------------------------------------------------------------------------

def _setup_log_rotation() -> None:
    """Install a rotating file handler for the primary Fyers log."""
    _LOG_FILE    = "fyersApi.log"
    _MAX_BYTES   = 5 * 1024 * 1024   # 5 MB per file
    _BACKUP_COUNT = 3                 # keep .1 .2 .3 rollover files
    root_logger = logging.getLogger()
    # Avoid duplicate handlers if uvicorn reloads the module
    if not any(isinstance(h, logging.handlers.RotatingFileHandler) for h in root_logger.handlers):
        rotating = logging.handlers.RotatingFileHandler(
            _LOG_FILE, maxBytes=_MAX_BYTES, backupCount=_BACKUP_COUNT, encoding="utf-8"
        )
        rotating.setFormatter(logging.Formatter(
            "[%(asctime)s] %(levelname)s %(name)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        ))
        root_logger.addHandler(rotating)
    # Root-cause fix (found live, 2026-08-20): this used to be `if not
    # root_logger.level: setLevel(INFO)`, intended to only set a level if
    # none had been configured yet. But logging.basicConfig() -- called at
    # import time by trading_bot/main.py, which api_bridge.py transitively
    # imports for its strategy registrations -- is a silent no-op if the
    # root logger already has ANY handler attached (by something imported
    # even earlier), which left the root logger at Python's own built-in
    # default level, WARNING (30) -- never actually "unset" (0/NOTSET), so
    # the old guard always skipped. Every logger.info() call in this whole
    # file -- including main_process_watchdog's own restart-succeeded/
    # -failed confirmations -- was silently dropped before it ever reached
    # a handler, for this process's entire lifetime. Found while
    # investigating why a real freeze-recovery never logged its outcome.
    # Now unconditional and explicit about what "already configured
    # verbosely enough" means, rather than trusting an ambiguous truthy
    # check on a level that may never have been genuinely set at all.
    if root_logger.level == logging.NOTSET or root_logger.level > logging.INFO:
        root_logger.setLevel(logging.INFO)

# Root-cause fix (found live, 2026-08-05): this used to run unconditionally
# at import time, attaching a RotatingFileHandler for fyersApi.log onto the
# ROOT logger for ANY process that imports this module -- including the
# test suite (several tests import `app`/helpers from here via TestClient).
# Since logging propagates to the root logger by default, every subsequent
# log call in that same pytest process -- from completely unrelated modules
# like trading_bot.portfolio_risk -- was landing in the LIVE fyersApi.log
# file. Result: running the test suite during market hours wrote what look
# exactly like real circuit-breaker trips (matching values from
# tests/test_risk_management.py's own scenarios) into the production log,
# a false alarm indistinguishable from a real one without cross-checking
# state.db. Only the actual live server process (`python api_bridge.py`)
# should own this file -- mirrors the identical fix already applied to
# trading_bot/main.py's engine.log handler for the same reason.

# Disable any local system proxy to prevent connection failures to Fyers
os.environ["HTTP_PROXY"] = ""
os.environ["HTTPS_PROXY"] = ""
os.environ["ALL_PROXY"] = ""
os.environ["no_proxy"] = "*"
os.environ["NO_PROXY"] = "*"


def convert_numpy_types(obj):
    import math
    """Recursively convert numpy types to native Python types for JSON serialization."""
    if isinstance(obj, dict):
        return {k: convert_numpy_types(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [convert_numpy_types(v) for v in obj]
    elif hasattr(obj, "item") and callable(obj.item):
        val = obj.item()
        if isinstance(val, float) and (math.isnan(val) or math.isinf(val)):
            return 0.0
        return val
    elif isinstance(obj, (float, int)):
        if isinstance(obj, float) and (math.isnan(obj) or math.isinf(obj)):
            return 0.0
        return obj
    elif isinstance(obj, np.ndarray):
        return convert_numpy_types(obj.tolist())
    else:
        return obj

# Import the Broker Factory to make the API broker-agnostic!
from brokers import BrokerFactory, OrderRequest, OrderSide, OrderType
# Import the Strategy Registry to support multiple strategies
from trading_bot.strategies.registry import registry
from trading_bot.strategies.ema_rsi_strategy import generate_signals as ema_rsi_signals
from trading_bot.strategies.enhanced_ai_strategy import generate_signals as enhanced_signals
from trading_bot.strategies.premium_selection import generate_signals as premium_signals
from trading_bot.strategies.advanced_ai_ml_strategy import generate_signals as advanced_ai_signals
from trading_bot.strategies.momentum_strategy import generate_signals as momentum_signals
from trading_bot.strategies.ema_crossover_pro_strategy import generate_signals as ema_crossover_signals
from trading_bot.strategies.meta_agent_strategy import generate_signals as meta_agent_signals
from trading_bot.strategies.buy_the_dip_strategy import generate_signals as buy_dip_signals

from trading_bot.strategies.marl_strategy import generate_signals as marl_signals

# Register strategies for the API
registry.register("ema_rsi",      ema_rsi_signals)
registry.register("enhanced_ai",  enhanced_signals)
registry.register("premium",      premium_signals)
registry.register("advanced_ai", advanced_ai_signals)
registry.register("institutional_momentum", momentum_signals)
registry.register("ema_crossover", ema_crossover_signals)
registry.register("meta_agent_swarm", meta_agent_signals)
registry.register("buy_the_dip", buy_dip_signals)
registry.register("MARL_Ultra", marl_signals)

app = FastAPI(title="Broker Terminal Data Bridge & Backtester")

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Global Exception on {request.url.path}: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"status": "error", "message": f"Internal Server Error: {str(exc)}"},
    )

# Allow requests from the Next.js frontend (or any local device)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Authentication gate
# ---------------------------------------------------------------------------
# Root-cause fix for the audit finding "api_bridge.py has no authentication
# on ~30 routes": previously only 3 routes checked anything, and that check
# was an unauthenticated request.client.host comparison. Every route now
# requires a valid, server-issued session token (see
# shared.security.sessions) except the small allowlist below, which is the
# pre-login flow itself. FastAPI docs/schema endpoints are left open for
# local developer convenience.
from shared.security.sessions import validate_session
from shared.security import audit
from shared.security.audit_log import AuditEvent
from shared.security.rate_limiter import ORDER_LIMITER

_PUBLIC_PATHS = {
    "/health",
    "/api/auth/status",
    "/api/auth/register",
    "/api/auth/login",
    "/api/auth/reset",
    "/docs",
    "/redoc",
    "/openapi.json",
}
# /api/history, /api/quote, and /api/option-chain were briefly added here by
# in-progress options-chain work — removed: every frontend call path to all
# three (app/api/history/route.ts, app/api/state/route.ts's /api/quote
# calls, app/api/option-chain/route.ts) already attaches real session auth
# headers server-side via getAuthHeaders(), so there was no legitimate
# public/pre-login use case, and leaving them public undid the Critical #2
# auth-gate fix for three real market-data routes.


def _extract_bearer_token(request: Request) -> str:
    header = request.headers.get("authorization", "")
    if header.lower().startswith("bearer "):
        return header[7:].strip()
    return ""


@app.middleware("http")
async def require_session_auth(request: Request, call_next):
    path = request.url.path
    if request.method == "OPTIONS" or path in _PUBLIC_PATHS:
        return await call_next(request)

    token = _extract_bearer_token(request)
    session = validate_session(token)
    if not session:
        return JSONResponse(
            status_code=401,
            content={"status": "error", "message": "Authentication required."},
        )
    request.state.user = session
    return await call_next(request)

from fastapi import WebSocket
from fyers_apiv3.FyersWebsocket import data_ws
import asyncio
import threading
import sys

async def daily_retrain_scheduler():
    """Background task to run AI retraining every day at 11 PM."""
    while True:
        now = datetime.now()
        target = now.replace(hour=23, minute=0, second=0, microsecond=0)
        if now >= target:
            target += timedelta(days=1)
        
        sleep_seconds = (target - now).total_seconds()
        logger.info(f"Next AI retraining scheduled in {sleep_seconds} seconds (at {target})")
        await asyncio.sleep(sleep_seconds)
        
        logger.info("Executing daily AI retraining...")
        try:
            import subprocess
            subprocess.run([sys.executable, "scripts/daily_ai_retrain.py"], check=False)
        except Exception as e:
            logger.error(f"Daily retrain failed: {e}")


async def lot_size_refresh_scheduler():
    """Periodically refreshes lot sizes from the Fyers symbol master during
    market hours. NSE can update lot sizes on contract rollover without notice —
    this ensures the live engine never trades stale sizes without a full restart.
    Runs every 4 hours. Only calls the updater during (or just before) market hours
    so we don't hit the Fyers symbol master unnecessarily overnight.
    """
    from shared.lot_size_updater import update_lot_sizes_in_settings
    while True:
        await asyncio.sleep(4 * 60 * 60)  # 4 hours
        try:
            now_ist = datetime.now(_IST)
            # Only refresh between 08:00 and 16:00 IST (covers pre-market + full session)
            if 8 <= now_ist.hour < 16 and now_ist.weekday() < 5:
                logger.info("[LotSize] Scheduled refresh — fetching updated lot sizes from Fyers symbol master.")
                await update_lot_sizes_in_settings()
            else:
                logger.debug("[LotSize] Outside market window, skipping scheduled lot size refresh.")
        except Exception as e:
            logger.error(f"[LotSize] Scheduled refresh failed: {e}")

@app.on_event("startup")
async def startup_event():
    logger.info("Initializing API Bridge and restoring application state...")

    # 0. Auto-initialize the trade_journal table in state.db on every startup
    try:
        from scripts.init_journal import init_journal_db
        import concurrent.futures
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, init_journal_db)
        logger.info("[Journal] trade_journal table ready.")
    except Exception as e:
        logger.error(f"[Journal] Failed to init journal table: {e}")

    # 1. Fetch latest lot sizes dynamically in background
    try:
        from shared.lot_size_updater import update_lot_sizes_in_settings
        asyncio.create_task(update_lot_sizes_in_settings())
    except Exception as e:
        logger.error(f"Failed to start lot size updater: {e}")

    # 2. Start the sentiment background thread (non-blocking)
    try:
        from shared.sentiment import _ensure_background_thread as _start_sentiment
        _start_sentiment()
        logger.info("[Sentiment] Background sentiment thread started.")
    except Exception as e:
        logger.error(f"[Sentiment] Failed to start sentiment thread: {e}")

    asyncio.create_task(daily_retrain_scheduler())
    asyncio.create_task(lot_size_refresh_scheduler())

# Global state for live market data (Institutional Streaming)
market_data_lock = threading.Lock()
current_market_data = {
    "NSE:NIFTY50-INDEX": {"lp": 23820.35, "chp": -1.49},
    "BSE:SENSEX-INDEX": {"lp": 76015.28, "chp": -1.70},
    "NSE:NIFTYBANK-INDEX": {"lp": 51000.00, "chp": 0.0}
}

# Root-cause fix (found live, 2026-08-12): the upstream Fyers WebSocket
# (fyers_apiv3's data_ws.FyersDataSocket, `reconnect=True`) went silently
# zombie for 46 minutes during real market hours -- current_market_data
# stopped updating, /ws/live kept broadcasting the last known (stale)
# prices with no signal that anything was wrong, and main.py's own
# tick-staleness detector could only log a warning, not recover, because
# its LOCAL socket to this server stayed healthy throughout (ping/pong
# fine) -- the failure was entirely upstream. Root cause, read directly
# from the vendored library (venv/Lib/site-packages/fyers_apiv3/
# FyersWebsocket/data_ws.py's `__ping`): its keepalive is fire-and-forget
# -- it sends a ping frame every 10s as long as the OS socket reports
# `connected`, but never waits for or checks a pong, so a network blip
# that leaves the OS socket in a false-`connected` zombie state (observed
# here immediately after a burst of DNS resolution failures for
# api-t1.fyers.in) is invisible to it -- `on_close`/`reconnect` never
# fire. `_last_fyers_message_at` plus `fyers_feed_watchdog()` below
# detect that condition independently (from the receiving side, which
# the library itself never checks) and force a clean teardown + fresh
# connection.
_last_fyers_message_at: float = 0.0
fyers_socket_instance = None # Global instance for dynamic subscription

# Global Engine State
engine_state = {
    "is_active": False,
    "last_start_time": None,
    "mode": "Live"
}

# ------------------------------------------------------------------
# Cached config/settings.json reader (avoids disk I/O on every request)
# ------------------------------------------------------------------
_config_cache: dict = {}
_config_last_mtime: float = 0.0
_CONFIG_PATH = "config/settings.json"

def _load_config_settings() -> dict:
    """Read config/settings.json with mtime-based cache. Thread-safe for FastAPI."""
    global _config_cache, _config_last_mtime
    if os.path.exists(_CONFIG_PATH):
        try:
            current_mtime = os.path.getmtime(_CONFIG_PATH)
            if current_mtime > _config_last_mtime or not _config_cache:
                with open(_CONFIG_PATH, "r", encoding="utf-8") as _f:
                    _config_cache = json.load(_f)
                _config_last_mtime = current_mtime
        except Exception as _e:
            logger.warning("Could not reload config/settings.json: %s", _e)
    return _config_cache or {}

def format_broker_symbol(symbol: str) -> str:
    """
    Institution-grade symbol formatter for Fyers API.
    Converts generic ticker names into exact exchange-formatted strings required by Fyers.
    Supports all NSE/BSE stocks, indices, and correctly formats option contracts.
    """
    symbol = symbol.strip().upper()
    
    # 0. Check if symbol is an Option Contract (e.g. "NIFTY 24350 CE", "NSE:NIFTY26AUG24350CE")
    try:
        from shared.security.symbol_parser import parse_option_symbol
        opt_info = parse_option_symbol(symbol)
        if opt_info["is_option"]:
            return symbol  # Do NOT append -EQ to option contracts!
    except Exception:
        pass
    
    # If the symbol already has an exchange prefix and instrument type, return it directly
    if ":" in symbol and "-" in symbol:
        return symbol

    # 1. Map Major Indices
    indices_map = {
        "NIFTY": "NSE:NIFTY50-INDEX",
        "BANKNIFTY": "NSE:NIFTYBANK-INDEX",
        "FINNIFTY": "NSE:FINNIFTY-INDEX",
        "MIDCPNIFTY": "NSE:MIDCPNIFTY-INDEX",
        "SENSEX": "BSE:SENSEX-INDEX",
        "BANKEX": "BSE:BANKEX-INDEX",
        "INDIAVIX": "NSE:INDIA VIX-INDEX"
    }
    
    if symbol in indices_map:
        return indices_map[symbol]
        
    # 2. Extract explicit exchange prefix if provided (e.g., "BSE:RELIANCE")
    exchange = "NSE" # Default to NSE for Indian Equities
    ticker = symbol
    
    if ":" in symbol:
        parts = symbol.split(":")
        exchange = parts[0]
        ticker = parts[1]
        
    # 3. Format as Equity (EQ) by default for unrecognized equity symbols
    return f"{exchange}:{ticker}-EQ"

# ---------------------------------------------------------------------------
# Credential helpers — reads from encrypted broker_credentials.json once.
# NEVER hardcode client_id inline; always go through this layer.
# ---------------------------------------------------------------------------
_fyers_client_id_cache: str = ""

def _get_fyers_client_id() -> str:
    """Return the Fyers client_id from encrypted credentials, with in-process cache."""
    global _fyers_client_id_cache
    if _fyers_client_id_cache:
        return _fyers_client_id_cache
    try:
        from brokers.credentials import load_credentials
        creds = load_credentials("fyers")
        _fyers_client_id_cache = creds.get("client_id", "")
        if not _fyers_client_id_cache:
            # Fallback: try settings.json (for dev environments)
            if os.path.exists("config/settings.json"):
                with open("config/settings.json", "r") as _f:
                    _s = json.load(_f)
                    _fyers_client_id_cache = _s.get("client_id", "")
    except Exception as _e:
        logger.warning("Could not load Fyers client_id from credentials: %s", _e)
    return _fyers_client_id_cache

def start_fyers_socket():
    try:
        from brokers.token_cache import load_token
        token = load_token("fyers")
        if not token:
            # NOTE: no FINNIFTY equivalent added here (mapping/download list
            # below) — Yahoo Finance does not publish a reliable FINNIFTY
            # index ticker the way it does ^NSEI/^BSESN/^NSEBANK. A FINNIFTY
            # symbol in main.py's watchlist will get no ticks at all if this
            # fallback path is ever active (no cached Fyers token). Flagging
            # rather than guessing a ticker that may not exist or may be
            # unreliable — this path is normally dormant, since it only
            # triggers when there is no cached broker token.
            logger.warning("Token not found for WebSocket. Falling back to yfinance polling for Paper Mode.")
            # Root-cause fix (found live, 2026-08-12): `time` is already
            # imported at module level (line 13). Re-importing it here,
            # even though this branch only runs when there's no cached
            # Fyers token, made `time` a LOCAL name of the whole enclosing
            # start_fyers_socket() function -- Python decides a name is
            # local to a function based on any assignment/import anywhere
            # in its body, regardless of which branch actually runs. Every
            # nested closure defined below (on_message, on_error, ...)
            # inherited that as an unbound free variable whenever this
            # branch didn't execute, raising a NameError the instant any
            # of them tried to use the module-level `time` (e.g.
            # `on_message`'s `_last_fyers_message_at = time.time()`).
            import yfinance as yf
            while True:
                try:
                    data = yf.download("^NSEI ^BSESN ^NSEBANK", period="1d", interval="1m", progress=False)
                    if not data.empty:
                        close_data = data['Close']
                        mapping = {"^NSEI": "NSE:NIFTY50-INDEX", "^BSESN": "BSE:SENSEX-INDEX", "^NSEBANK": "NSE:NIFTYBANK-INDEX"}
                        for yf_sym, sym in mapping.items():
                            if yf_sym in close_data:
                                s_data = close_data[yf_sym].dropna()
                                if not s_data.empty:
                                    last_price = float(s_data.iloc[-1])
                                    with market_data_lock:
                                        current_market_data[sym] = {"lp": last_price, "chp": 0.0}
                    time.sleep(10)
                except Exception as e:
                    logger.error(f"YFinance fallback error: {e}")
                    time.sleep(10)
            return

        client_id = _get_fyers_client_id()
        
        def on_message(message):
            global current_market_data, _last_fyers_message_at
            # Any message at all proves the upstream socket is actually
            # receiving data, not just reporting itself connected -- see
            # fyers_feed_watchdog() for why that distinction matters.
            _last_fyers_message_at = time.time()
            if isinstance(message, dict):
                symbol = message.get('symbol')
                lp = message.get('ltp')
                if symbol and lp:
                    with market_data_lock:
                        current_market_data[symbol] = {
                            "lp": lp,
                            "chp": message.get('chp', 0.0)
                        }
                    
        def on_error(message):
            logger.error("Fyers WS Error: %s", message)
            msg_str = str(message).lower()
            if "auth" in msg_str or "token" in msg_str or "expire" in msg_str:
                logger.error("Emergency: Fyers WS Token failed. Triggering auto-login...")
                import subprocess
                import sys
                try:
                    # Bounded: this runs synchronously on the WS client's own
                    # callback thread (see start_fyers_socket) -- an unbounded
                    # subprocess.run here would block all further reconnect
                    # handling on that thread if any Fyers auth endpoint hangs.
                    subprocess.run(
                        [sys.executable, "scripts/auth/auto_login_fyers.py"],
                        check=False,
                        timeout=60,
                    )
                except subprocess.TimeoutExpired:
                    logger.error("Emergency auto-login timed out after 60s -- giving up this attempt.")
                except Exception as e:
                    logger.error("Emergency auto-login failed: %s", e)
        def on_open():
            global _subscribed_symbols
            # Root-cause fix: FINNIFTY was missing from this set entirely.
            # /ws/live clients (including main.py's own broker WS client) are
            # purely passive — they only ever see whatever current_market_data
            # holds, which is only populated for symbols subscribed here. The
            # dynamic-subscription path below (search "Dynamic Subscription
            # Sync") only adds a symbol AFTER a position already exists for
            # it, which doesn't help the underlying INDEX symbol a strategy
            # needs live ticks for just to evaluate a signal in the first
            # place. Without this, trading_bot/main.py could have
            # "NSE:FINNIFTY-INDEX" in its symbols list and never receive a
            # single live tick for it.
            _subscribed_symbols.update({
                "NSE:NIFTY50-INDEX", "BSE:SENSEX-INDEX", "NSE:NIFTYBANK-INDEX",
                "NSE:FINNIFTY-INDEX", "NSE:RELIANCE-EQ", "NSE:TCS-EQ",
            })
            logger.info("Fyers WS Connected!")
            if fyers_socket_instance:
                fyers_socket_instance.subscribe(symbols=list(_subscribed_symbols), data_type="symbolData")
            
        def on_close(message=None):
            # The vendored client calls this as `self.OnClose(message)` (see
            # fyers_apiv3/FyersWebsocket/data_ws.py's on_close), passing the
            # close reason -- a 0-arg signature here raises TypeError on
            # every real socket close, which was silently breaking recovery:
            # fyers_feed_watchdog's rebuild thread still started, but a
            # crash inside the *old* socket's own on_close (invoked as part
            # of its internal `reconnect=True` handling) meant the closure
            # sequence never completed cleanly. Found live 2026-08-13 when
            # a real WinError 10054 close left the feed dead with the
            # watchdog's forced reconnect never producing a new "Fyers WS
            # Connected!" log line or any further ticks.
            logger.info("Fyers WS Closed: %s", message)

        access_token_full = f"{client_id}:{token}"
        
        global fyers_socket_instance
        fyers_socket_instance = data_ws.FyersDataSocket(
            access_token=access_token_full,
            log_path="",
            litemode=False,
            write_to_file=False,
            reconnect=True,
            on_connect=on_open,
            on_message=on_message,
            on_error=on_error,
            on_close=on_close
        )
        
        fyers_socket_instance.connect()
    except Exception as e:
        logger.error("Error starting Fyers socket: %s", e)

async def fyers_feed_watchdog():
    """Force-rebuilds the upstream Fyers socket if it goes silent during
    market hours. See `should_rebuild_stale_feed`'s docstring for the
    root cause — the vendored client's own `reconnect=True` can't be
    trusted to do this on its own.
    """
    global fyers_socket_instance, _last_fyers_message_at
    from shared.market_hours import is_market_open
    from shared.risk.tick_staleness import should_rebuild_stale_feed
    logger.info("fyers_feed_watchdog: task scheduled and running.")
    # Diagnostic (2026-08-20): after a real ~2hr feed outage went through
    # market open with this watchdog completely silent -- no trigger, no
    # error, nothing -- there was no way to tell after the fact whether the
    # task had simply never been scheduled (see the lifespan() startup
    # timeout fix from the same investigation) or was running the whole
    # time but just never satisfied its own trigger condition. This loop
    # only ever logged on trigger; a dead/never-started task and a healthy
    # idle one were indistinguishable in the log. A periodic liveness line
    # closes that gap for next time.
    _iterations = 0
    while True:
        await asyncio.sleep(15)
        _iterations += 1
        try:
            if _iterations % 20 == 0:  # ~every 5 minutes
                logger.info(
                    "fyers_feed_watchdog: alive, last_message_age=%.0fs, market_open=%s.",
                    (time.time() - _last_fyers_message_at) if _last_fyers_message_at else -1.0,
                    is_market_open(),
                )
            if not should_rebuild_stale_feed(
                _last_fyers_message_at, time.time(), is_market_open(),
            ):
                continue
            stale_for = time.time() - _last_fyers_message_at
            logger.error(
                "FYERS FEED STALL: no message from the upstream Fyers "
                "WebSocket in %.0fs during market hours -- forcing a "
                "fresh connection.",
                stale_for,
            )
            # Reset before rebuilding so a slow reconnect can't cause this
            # loop to fire again mid-rebuild.
            _last_fyers_message_at = time.time()
            stale_socket = fyers_socket_instance
            if stale_socket is not None:
                try:
                    await asyncio.to_thread(stale_socket.close_connection)
                except Exception as e:
                    logger.warning(
                        "Error closing the stale Fyers socket (rebuilding "
                        "anyway): %s", e,
                    )
            threading.Thread(target=start_fyers_socket, daemon=True).start()
        except Exception as e:
            logger.error("fyers_feed_watchdog error: %s", e)


# ---------------------------------------------------------------------------
# main.py freeze detection + safe auto-recovery
# ---------------------------------------------------------------------------
#
# Root cause (found live, 2026-08-13): main.py went completely unresponsive
# for ~39 minutes (all threads, not just the tick-consuming path -- a wholly
# separate background thread went silent too) with nothing in the system
# able to detect it in real time; only a manual after-the-fact log review
# found it. main.py now writes an independent heartbeat (see
# trading_bot.main's heartbeat_writer / shared.risk.tick_staleness's
# heartbeat_is_stale) specifically so this watchdog can tell "no ticks
# arriving" (a feed/market issue -- main.py's own tick_staleness_watchdog
# already covers that) apart from "the process itself is unresponsive"
# (needs a restart).
#
# Policy (explicitly confirmed, 2026-08-13): auto-restart immediately on a
# confirmed freeze, whether or not a position is open, always alerting
# either way -- a working engine (even after a brief restart) beats a
# frozen one, and active_positions.json's already-correct reload-on-startup
# (trading_bot.main._load_positions) means a clean restart does not orphan
# an open position's stop-loss.
from pathlib import Path

_MAIN_WATCHDOG_RUN_DIR = Path(__file__).resolve().parent / "run"
_MAIN_PID_PATH = _MAIN_WATCHDOG_RUN_DIR / "main.pid"
_MAIN_HEARTBEAT_PATH = _MAIN_WATCHDOG_RUN_DIR / "main_heartbeat.txt"
_MAIN_POSITIONS_PATH = Path(__file__).resolve().parent / "config" / "active_positions.json"

_last_main_restart_attempt_at: float = 0.0
_main_consecutive_restart_failures: int = 0


def _should_attempt_main_restart(
    pid_alive: bool,
    heartbeat_stale: bool,
    now: float,
    last_restart_attempt_at: float,
    consecutive_restart_failures: int,
) -> bool:
    """Pure decision logic for main_process_watchdog: should it attempt a
    restart on this check? Extracted to module scope so it's directly
    testable without running the real infinite watchdog loop -- same
    reasoning as trading_bot/main.py's own _compute_retry_delay /
    _should_reset_failure_count, which this function reuses for the
    backoff math itself (so a fundamentally broken condition can't
    trigger a tight restart-loop storm).
    """
    if not pid_alive or not heartbeat_stale:
        return False
    from trading_bot.main import _compute_retry_delay
    cooldown = _compute_retry_delay(consecutive_restart_failures)
    return (now - last_restart_attempt_at) >= cooldown


def _describe_open_positions_for_alert() -> str:
    """Best-effort human-readable summary of config/active_positions.json
    for the freeze alert. Informational only -- never gates the restart
    decision (see this module's auto-restart-always policy above)."""
    try:
        if not _MAIN_POSITIONS_PATH.is_file():
            return "none"
        with open(_MAIN_POSITIONS_PATH, "r", encoding="utf-8") as f:
            positions = json.load(f)
        if not positions:
            return "none"
        return ", ".join(
            f"{data.get('symbol', key)} ({'SHORT' if data.get('side') == -1 else 'LONG'})"
            for key, data in positions.items()
        )
    except Exception:
        return "unknown (failed to read active_positions.json)"


_MAIN_RESTART_TERMINATE_TIMEOUT_S = 10
_MAIN_RESTART_HEARTBEAT_POLL_INTERVAL_S = 5
_MAIN_RESTART_HEARTBEAT_POLL_ATTEMPTS = 18  # ~90s total at the interval above


async def _check_and_recover_main_process() -> None:
    """One check-and-act cycle: is main.py frozen, and if so, alert +
    safely restart it. Pulled out of main_process_watchdog's infinite
    loop so it's directly callable/testable one iteration at a time,
    same reasoning as trading_bot/main.py's _write_heartbeat extraction.
    """
    global _last_main_restart_attempt_at, _main_consecutive_restart_failures
    import subprocess
    import psutil
    from shared.market_hours import is_market_open
    from shared.risk.tick_staleness import heartbeat_is_stale
    from shared.alerts import alerter

    if not is_market_open():
        return

    if not _MAIN_PID_PATH.is_file():
        return  # main.py hasn't been started yet this boot
    try:
        main_pid = int(_MAIN_PID_PATH.read_text(encoding="utf-8").strip())
    except (ValueError, OSError):
        return

    if not psutil.pid_exists(main_pid):
        # A crash, not a freeze -- main.py's own internal auto-restart
        # loop (the while-loop at the bottom of trading_bot/main.py,
        # wrapping asyncio.run) handles this case when the process is
        # alive to run it. A fully-dead process is a separate,
        # not-yet-covered gap here -- flagged, not silently assumed
        # handled.
        return

    last_heartbeat_at = 0.0
    if _MAIN_HEARTBEAT_PATH.is_file():
        try:
            last_heartbeat_at = float(_MAIN_HEARTBEAT_PATH.read_text(encoding="utf-8").strip())
        except (ValueError, OSError):
            pass

    now = time.time()
    stale = heartbeat_is_stale(last_heartbeat_at, now)
    if not _should_attempt_main_restart(
        True, stale, now,
        _last_main_restart_attempt_at, _main_consecutive_restart_failures,
    ):
        return

    stale_for = (now - last_heartbeat_at) if last_heartbeat_at else float("inf")
    positions_desc = _describe_open_positions_for_alert()
    logger.error(
        "MAIN.PY FROZEN: heartbeat stale for %.0fs (PID %d still alive). "
        "Open positions: %s. Attempting automatic restart.",
        stale_for, main_pid, positions_desc,
    )
    alerter.send_alert(
        f"🚨 **main.py appears frozen** (heartbeat stale {stale_for:.0f}s, "
        f"PID {main_pid} still running).\nOpen positions: {positions_desc}\n"
        f"Attempting automatic restart..."
    )
    _last_main_restart_attempt_at = now

    # Terminate the frozen process and confirm it's actually dead before
    # respawning -- so the new instance's singleton lock
    # (shared/singleton_lock.py) can never collide with a not-yet-dead
    # old one.
    try:
        proc = psutil.Process(main_pid)
        proc.terminate()
        try:
            await asyncio.to_thread(proc.wait, _MAIN_RESTART_TERMINATE_TIMEOUT_S)
        except psutil.TimeoutExpired:
            proc.kill()
            await asyncio.to_thread(proc.wait, _MAIN_RESTART_TERMINATE_TIMEOUT_S)
    except psutil.NoSuchProcess:
        pass  # already gone -- fine
    except Exception as e:
        logger.error("Failed to terminate frozen main.py (PID %d): %s", main_pid, e)
        alerter.send_alert(
            f"🚨 **Failed to terminate frozen main.py** (PID {main_pid}): {e}. "
            f"Manual intervention needed."
        )
        return

    # Respawn, matching how Start_AI_Bot.bat launches it.
    try:
        subprocess.Popen(
            [sys.executable, "trading_bot/main.py"],
            cwd=str(Path(__file__).resolve().parent),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except Exception as e:
        logger.error("Failed to respawn main.py: %s", e)
        _main_consecutive_restart_failures += 1
        alerter.send_alert(f"🚨 **Failed to respawn main.py**: {e}. Manual intervention needed.")
        return

    # Poll for the new process's own first heartbeat within a startup
    # grace window before declaring success.
    recovered = False
    for _ in range(_MAIN_RESTART_HEARTBEAT_POLL_ATTEMPTS):
        await asyncio.sleep(_MAIN_RESTART_HEARTBEAT_POLL_INTERVAL_S)
        if _MAIN_HEARTBEAT_PATH.is_file():
            try:
                hb = float(_MAIN_HEARTBEAT_PATH.read_text(encoding="utf-8").strip())
                if hb > now:  # a fresh write since the restart began
                    recovered = True
                    break
            except (ValueError, OSError):
                pass

    if recovered:
        _main_consecutive_restart_failures = 0
        logger.info("main.py restart succeeded -- fresh heartbeat confirmed.")
        alerter.send_alert("✅ **main.py restart succeeded** -- fresh heartbeat confirmed.")
    else:
        _main_consecutive_restart_failures += 1
        logger.error(
            "main.py restart did not produce a fresh heartbeat within "
            "the grace window -- manual intervention needed."
        )
        alerter.send_alert(
            "🚨 **main.py restart did not come up healthy** within the "
            "grace window. Manual intervention needed."
        )


async def main_process_watchdog():
    """Detects a frozen (not crashed) main.py -- alive per its PID in
    run/main.pid, but its heartbeat in run/main_heartbeat.txt has gone
    stale -- and automatically restarts it. See the module-level comment
    block above for the full root cause and policy; see
    _check_and_recover_main_process for the actual per-check logic.
    """
    logger.info("main_process_watchdog: task scheduled and running.")
    _iterations = 0
    while True:
        await asyncio.sleep(30)
        _iterations += 1
        try:
            if _iterations % 10 == 0:  # ~every 5 minutes
                logger.info("main_process_watchdog: alive.")
            await _check_and_recover_main_process()
        except Exception as e:
            logger.error("main_process_watchdog error: %s", e)


from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Seed last_confidence.json on first boot so the WebSocket always has
    # something to serve — prevents a blank dashboard on cold start.
    _seed_file = "last_confidence.json"
    if not os.path.exists(_seed_file):
        try:
            with open(_seed_file, "w") as _sf:
                json.dump({"confidence": 0, "status": "Awaiting first scan...", "bias": "NEUTRAL"}, _sf)
            logger.info("[Boot] Seeded last_confidence.json with neutral defaults.")
        except Exception as _se:
            logger.warning("[Boot] Could not seed last_confidence.json: %s", _se)

    logger.info("Attempting auto-login for Fyers...")
    import subprocess
    import sys
    try:
        # Bounded (2026-08-19): this runs synchronously inside the FastAPI
        # lifespan startup, awaited before the app starts serving AND before
        # the watchdog tasks below get scheduled -- a hang here (e.g. the
        # vendored fyers_apiv3 SDK's generate_token() call, which isn't
        # covered by auto_login_fyers.py's own requests.post timeouts) would
        # silently delay or block startup with no visible error.
        res = subprocess.run(
            [sys.executable, "scripts/auth/auto_login_fyers.py"],
            check=True, capture_output=True, text=True, timeout=60,
        )
        logger.info(f"Auto-login completed successfully: {res.stdout.splitlines()[-1] if res.stdout else ''}")
    except subprocess.TimeoutExpired:
        logger.error("Auto-login timed out after 60s during startup -- continuing with whatever cached token exists.")
    except Exception as e:
        logger.error(f"Auto-login failed: {e}")
        if hasattr(e, 'stderr') and e.stderr:
            logger.error(f"Auto-login stderr: {e.stderr}")
            
    # Start the Fyers socket in background thread
    threading.Thread(target=start_fyers_socket, daemon=True).start()

    # Start the WebSocket Broadcaster task
    asyncio.create_task(websocket_broadcaster())

    # Watches for the upstream Fyers feed going silent during market hours
    # and force-rebuilds it — see fyers_feed_watchdog()'s docstring.
    asyncio.create_task(fyers_feed_watchdog())

    # Watches for main.py itself going unresponsive (frozen, not crashed)
    # and safely auto-restarts it — see main_process_watchdog()'s docstring.
    asyncio.create_task(main_process_watchdog())

    yield

app.router.lifespan_context = lifespan


# Trade state cache for WebSocket (prevents SQLite reads at 20fps)
from shared.state import load_state as _load_state_fn
_ws_trade_cache: dict = {"trades": [], "pnl": 0.0, "equity": 100000.0}
_ws_trade_last_read: float = 0.0
_WS_TRADE_CACHE_TTL: float = 0.05  # Refresh trades from DB at 20 FPS for ultra-low latency

signals_cache = {"data": None, "last_updated": 0}
active_connections: set[WebSocket] = set()
_subscribed_symbols: set = set()

async def websocket_broadcaster():
    """Single global background task that computes the market snapshot and broadcasts to all connected clients."""
    global _ws_trade_cache, _ws_trade_last_read, _subscribed_symbols
    while True:
        try:
            if not active_connections:
                await asyncio.sleep(0.5)
                continue
                
            # Only update cache if it is empty OR if 60 seconds passed AND market is open!
            # This ensures we freeze the last score after market hours!
            from datetime import datetime
            now = datetime.now()
            market_open = now.replace(hour=9, minute=15, second=0, microsecond=0)
            market_close = now.replace(hour=15, minute=30, second=0, microsecond=0)
            is_market_open = market_open <= now <= market_close and now.weekday() < 5
            
            if signals_cache["data"] is None:
                try:
                    import json
                    with open("last_confidence.json", "r") as f:
                        cached_file_data = json.load(f)
                        signals_cache["data"] = {
                            "confidence": cached_file_data["confidence"],
                            "status": cached_file_data["status"],
                            "bias": cached_file_data["bias"],
                            "trendData": [],
                            "signals": []
                        }
                        signals_cache["last_updated"] = time.time()
                except Exception:
                    pass
                    
            if signals_cache["data"] is None or (time.time() - signals_cache["last_updated"] > 30 and is_market_open):
                signals_cache["last_updated"] = time.time()
                async def _refresh_signals():
                    try:
                        from fastapi.concurrency import run_in_threadpool
                        signals_cache["data"] = await run_in_threadpool(compute_signals, "NIFTY")
                    except Exception as e:
                        logger.warning("[WS] Error updating signals cache: %s", e)
                asyncio.create_task(_refresh_signals())
                    
            if not current_market_data:
                current_market_data.update({
                    "NSE:NIFTY50-INDEX": {"lp": 23971.88, "chp": -0.81},
                    "BSE:SENSEX-INDEX": {"lp": 76015.28, "chp": -1.70},
                    "NSE:NIFTYBANK-INDEX": {"lp": 51000.00, "chp": 0.0}
                })

            with market_data_lock:
                snapshot = current_market_data.copy()

            if not is_market_open:
                now_hash = int(time.time() * 2) 
                def get_sim_tick(sym: str, base: float):
                    seed = sum(ord(c) for c in sym) + now_hash
                    fluct = (seed % 100) / 100.0 - 0.5 
                    return {"lp": base + (base * fluct * 0.0002), "chp": fluct * 1.0}
                    
                n_base = snapshot.get("NSE:NIFTY50-INDEX", {"lp": 23820.35})["lp"]
                s_base = snapshot.get("BSE:SENSEX-INDEX", {"lp": 76015.28})["lp"]
                b_base = snapshot.get("NSE:NIFTYBANK-INDEX", {"lp": 51000.00})["lp"]
                
                snapshot["NSE:NIFTY50-INDEX"] = get_sim_tick("NIFTY", n_base)
                snapshot["BSE:SENSEX-INDEX"] = get_sim_tick("SENSEX", s_base)
                snapshot["NSE:NIFTYBANK-INDEX"] = get_sim_tick("BANKNIFTY", b_base)

            websocket_data = {
                "NIFTY": snapshot.get("NSE:NIFTY50-INDEX", {"lp": 23820.35, "chp": -1.49}),
                "SENSEX": snapshot.get("BSE:SENSEX-INDEX", {"lp": 76015.28, "chp": -1.70}),
                "BANKNIFTY": snapshot.get("NSE:NIFTYBANK-INDEX", {"lp": 51000.00, "chp": 0.0})
            }
            
            for k, v in snapshot.items():
                if k not in ["NSE:NIFTY50-INDEX", "BSE:SENSEX-INDEX", "NSE:NIFTYBANK-INDEX"]:
                    short_key = k.split(":")[1].split("-")[0] if ":" in k else k
                    websocket_data[short_key] = v
                    
            _now_t = time.time()
            if _now_t - _ws_trade_last_read >= _WS_TRADE_CACHE_TTL:
                from fastapi.concurrency import run_in_threadpool
                _ws_trade_cache = await run_in_threadpool(_load_state_fn, reload_trades=True, reload_state=True)
                _ws_trade_last_read = _now_t
            
            websocket_data["trades"] = _ws_trade_cache.get("trades", [])
            realized_pnl = _ws_trade_cache.get("pnl", 0.0)
            websocket_data["equity"] = _ws_trade_cache.get("equity", 100000.0)
            websocket_data["raw_ticks"] = snapshot
            websocket_data["signalsData"] = signals_cache["data"]

            # ── Real-time Unrealized P&L from Active Positions ──────────────────
            # Read active positions and compute mark-to-market P&L using live prices
            unrealized_pnl = 0.0
            open_positions_count = 0
            positions_detail: list = []
            try:
                positions_path = Path(__file__).resolve().parent / "config" / "active_positions.json"
                if positions_path.exists():
                    with open(positions_path, "r") as _pf:
                        active_pos_dict = json.load(_pf)
                    open_positions_count = len(active_pos_dict)

                    for base_sym, pos in active_pos_dict.items():
                        entry_price = float(pos.get("entry_price", 0))
                        qty         = int(pos.get("quantity", 0))
                        side        = int(pos.get("side", 1))   # 1=long, -1=short
                        opt_sym     = pos.get("symbol", base_sym)

                        # Find the live price for this position's underlying symbol
                        ltp = 0.0
                        # Try exact option symbol first (from dynamic subscription)
                        if opt_sym in snapshot:
                            ltp = snapshot[opt_sym].get("lp", 0.0)
                        # Fallback: try base symbol (index)
                        if ltp == 0.0:
                            for key in [f"NSE:{base_sym}-INDEX", f"BSE:{base_sym}-INDEX", base_sym]:
                                if key in snapshot:
                                    ltp = snapshot[key].get("lp", 0.0)
                                    break
                        # Fallback: look in websocket_data short keys
                        if ltp == 0.0:
                            short = base_sym.replace("NSE:", "").replace("BSE:", "").split("-")[0]
                            ltp_data = websocket_data.get(short)
                            if isinstance(ltp_data, dict):
                                ltp = ltp_data.get("lp", 0.0)

                        if entry_price > 0 and qty > 0 and ltp > 0:
                            pos_unrealized = (ltp - entry_price) * qty * side
                        else:
                            pos_unrealized = 0.0

                        unrealized_pnl += pos_unrealized
                        positions_detail.append({
                            "symbol": opt_sym,
                            "entry_price": entry_price,
                            "ltp": ltp,
                            "qty": qty,
                            "side": side,
                            "unrealized_pnl": round(pos_unrealized, 2),
                            "sl": pos.get("stop_loss", 0),
                            "target": pos.get("target", 0),
                        })
            except Exception as _pnl_err:
                logger.debug("[WS] Unrealized P&L calc error: %s", _pnl_err)

            total_pnl = realized_pnl + unrealized_pnl
            websocket_data["pnl"]                  = round(realized_pnl, 2)
            websocket_data["unrealized_pnl"]       = round(unrealized_pnl, 2)
            websocket_data["total_pnl"]            = round(total_pnl, 2)
            websocket_data["open_positions_count"] = open_positions_count
            websocket_data["positions_detail"]     = positions_detail

            # --- Dynamic Subscription Sync ---
            try:
                positions_path = Path(__file__).resolve().parent / "config" / "active_positions.json"
                if positions_path.exists():
                    with open(positions_path, "r") as f:
                        active_pos_dict = json.load(f)
                        
                    active_symbols = set(pos.get("symbol") for pos in active_pos_dict.values() if pos.get("symbol"))
                    new_symbols = active_symbols - _subscribed_symbols
                    
                    if new_symbols and fyers_socket_instance:
                        logger.info("[WS] Dynamically subscribing to new symbols: %s", new_symbols)
                        fyers_socket_instance.subscribe(symbols=list(new_symbols), data_type="symbolData")
                        _subscribed_symbols.update(new_symbols)
            except Exception as e:
                logger.error("[WS] Dynamic subscription failed: %s", e)
                    
            # Fix 6: Inject trading_mode (paper vs live) into every WS frame
            try:
                _settings_now = _load_config_settings()
                websocket_data["trading_mode"] = "live" if _settings_now.get("live_trading_mode", False) else "paper"
            except Exception:
                websocket_data["trading_mode"] = "paper"

            # Fix 2: Inject cached sentiment score (never blocks — always returns last cached value)
            try:
                from shared.sentiment import get_current_sentiment
                _sent = get_current_sentiment()
                websocket_data["sentiment"] = {
                    "score": _sent.get("score", 0.0),
                    "label": _sent.get("label", "Neutral"),
                    "top_headlines": _sent.get("top_headlines", [])[:3],  # top 3 only to keep payload small
                }
            except Exception:
                websocket_data["sentiment"] = {"score": 0.0, "label": "Neutral", "top_headlines": []}

            # Broadcast to all connected clients
            disconnected = set()
            for ws in list(active_connections):
                try:
                    await ws.send_json(websocket_data)
                except Exception:
                    disconnected.add(ws)
                    
            for ws in disconnected:
                active_connections.discard(ws)
                
            await asyncio.sleep(0.05) 
        except Exception as e:
            logger.error("WebSocket Broadcaster Error: %s", e)
            await asyncio.sleep(1)

@app.websocket("/ws/live")
async def websocket_endpoint(websocket: WebSocket):
    # The HTTP auth middleware doesn't cover websocket handshakes, so the
    # session token is validated here instead, via a query parameter (a
    # WebSocket handshake can't carry a custom Authorization header from a
    # browser client).
    token = websocket.query_params.get("token", "")
    if not validate_session(token):
        await websocket.close(code=4401, reason="Authentication required")
        return

    await websocket.accept()
    active_connections.add(websocket)
    try:
        # Keep connection open until client disconnects
        while True:
            await websocket.receive_text()
    except Exception:
        pass
    finally:
        active_connections.discard(websocket)

@app.get("/health")
async def health():
    feed_age_s = (
        round(time.time() - _last_fyers_message_at, 1)
        if _last_fyers_message_at else None
    )
    return {"status": "ok", "fyers_feed_age_s": feed_age_s}


# ---------------------------------------------------------------------------
# Fix 1 — Trade Journal: Full CRUD API backed by state.db SQLite
# ---------------------------------------------------------------------------

def _get_journal_db_path() -> str:
    return str(Path(__file__).resolve().parent / "state.db")


class JournalEntryCreate(BaseModel):
    trade_date: str
    symbol: str
    strategy_name: str
    direction: str
    entry_price: float
    exit_price: float
    qty: int
    pnl: float
    ai_feedback: Optional[str] = None
    tags: Optional[str] = None


class JournalEntryUpdate(BaseModel):
    ai_feedback: Optional[str] = None
    tags: Optional[str] = None
    exit_price: Optional[float] = None
    pnl: Optional[float] = None


@app.get("/api/journal")
async def get_journal():
    """Fetch all trade journal entries from state.db, newest first."""
    import sqlite3, contextlib
    try:
        db_path = _get_journal_db_path()
        with contextlib.closing(sqlite3.connect(db_path, timeout=10.0)) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM trade_journal ORDER BY trade_date DESC"
            ).fetchall()
        return {"trades": [dict(r) for r in rows], "count": len(rows)}
    except Exception as e:
        logger.error(f"[Journal] GET failed: {e}")
        raise HTTPException(status_code=500, detail=f"Journal read failed: {e}")


@app.post("/api/journal")
async def create_journal_entry(entry: JournalEntryCreate):
    """Create a new manual trade journal entry."""
    import sqlite3, contextlib
    try:
        db_path = _get_journal_db_path()
        with contextlib.closing(sqlite3.connect(db_path, timeout=10.0)) as conn:
            cursor = conn.execute(
                """INSERT INTO trade_journal
                   (trade_date, symbol, strategy_name, direction, entry_price,
                    exit_price, qty, pnl, ai_feedback, tags)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (entry.trade_date, entry.symbol, entry.strategy_name,
                 entry.direction, entry.entry_price, entry.exit_price,
                 entry.qty, entry.pnl, entry.ai_feedback, entry.tags)
            )
            conn.commit()
            new_id = cursor.lastrowid
        logger.info(f"[Journal] Created entry id={new_id} symbol={entry.symbol} pnl={entry.pnl}")
        return {"status": "created", "id": new_id}
    except Exception as e:
        logger.error(f"[Journal] POST failed: {e}")
        raise HTTPException(status_code=500, detail=f"Journal write failed: {e}")


@app.put("/api/journal/{entry_id}")
async def update_journal_entry(entry_id: int, update: JournalEntryUpdate):
    """Update ai_feedback, tags, exit_price, or pnl for an existing journal entry."""
    import sqlite3, contextlib
    try:
        db_path = _get_journal_db_path()
        fields, values = [], []
        if update.ai_feedback is not None:
            fields.append("ai_feedback = ?"); values.append(update.ai_feedback)
        if update.tags is not None:
            fields.append("tags = ?"); values.append(update.tags)
        if update.exit_price is not None:
            fields.append("exit_price = ?"); values.append(update.exit_price)
        if update.pnl is not None:
            fields.append("pnl = ?"); values.append(update.pnl)
        if not fields:
            raise HTTPException(status_code=400, detail="No fields to update.")
        values.append(entry_id)
        with contextlib.closing(sqlite3.connect(db_path, timeout=10.0)) as conn:
            conn.execute(f"UPDATE trade_journal SET {', '.join(fields)} WHERE id = ?", values)
            conn.commit()
        return {"status": "updated", "id": entry_id}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[Journal] PUT id={entry_id} failed: {e}")
        raise HTTPException(status_code=500, detail=f"Journal update failed: {e}")


@app.delete("/api/journal/{entry_id}")
async def delete_journal_entry(entry_id: int):
    """Delete a journal entry by ID."""
    import sqlite3, contextlib
    try:
        db_path = _get_journal_db_path()
        with contextlib.closing(sqlite3.connect(db_path, timeout=10.0)) as conn:
            conn.execute("DELETE FROM trade_journal WHERE id = ?", (entry_id,))
            conn.commit()
        logger.info(f"[Journal] Deleted entry id={entry_id}")
        return {"status": "deleted", "id": entry_id}
    except Exception as e:
        logger.error(f"[Journal] DELETE id={entry_id} failed: {e}")
        raise HTTPException(status_code=500, detail=f"Journal delete failed: {e}")


# ---------------------------------------------------------------------------
# Fix 2 — Sentiment: Dedicated REST endpoint
# ---------------------------------------------------------------------------

@app.get("/api/sentiment")
async def get_sentiment():
    """Returns the latest cached market sentiment score and top headlines.
    The background thread in shared/sentiment.py refreshes this every 5 minutes.
    This endpoint NEVER blocks — it always returns the last cached value instantly.
    """
    try:
        from shared.sentiment import get_current_sentiment
        data = get_current_sentiment()
        return {"status": "ok", **data}
    except Exception as e:
        logger.error(f"[Sentiment] GET failed: {e}")
        return {"status": "error", "score": 0.0, "label": "Neutral", "top_headlines": []}


# ---------------------------------------------------------------------------
# Fix 7 — Paper vs Live Trading Mode: Dedicated REST endpoint
# ---------------------------------------------------------------------------

@app.get("/api/trading-mode")
async def get_trading_mode():
    """Returns the current trading mode (paper or live) and the live_trading_mode flag.
    The frontend metrics bar uses this to render the persistent PAPER/LIVE badge.
    """
    try:
        settings = _load_config_settings()
        is_live = settings.get("live_trading_mode", False)
        return {
            "mode": "live" if is_live else "paper",
            "live_trading_mode": is_live,
            "description": "Real orders sent to broker" if is_live
                           else "Simulated trades — no real orders",
        }
    except Exception as e:
        logger.error(f"[TradingMode] GET failed: {e}")
        return {"mode": "paper", "live_trading_mode": False,
                "description": "Paper mode (default fallback)"}


from pydantic import BaseModel
class ExecuteOrderRequest(BaseModel):
    symbol: str
    action: str
    quantity: int
    order_type: str = "MARKET"
    product_type: str = "INTRADAY"
    price: float = 0.0

@app.post("/api/order/execute")
async def execute_order(req: ExecuteOrderRequest, request: Request):
    """Executes a manual order from the UI."""
    if request.client and request.client.host not in ["127.0.0.1", "localhost", "::1"]:
        raise HTTPException(status_code=403, detail="Forbidden: Localhost access only")
        
    try:
        broker = BrokerFactory.get_active_broker()
        
        # Ensure paper mode is set correctly from settings
        settings = _load_config_settings()
        broker.paper_mode = not settings.get("live_trading_mode", False)

        # Root-cause fix (load-testing finding): ORDER_LIMITER already gates
        # every order the autonomous engine places on its own (main.py,
        # iceberg_manager.py), but this manual/dashboard endpoint had no
        # rate limit at all -- a runaway frontend retry loop or a script
        # hammering this route could fire unbounded real orders with zero
        # backend-side throttle once live_trading_mode is on. Same limiter,
        # same live-only scope (paper orders never reach a real broker API,
        # so there's nothing to rate-limit there).
        if not broker.paper_mode and not ORDER_LIMITER.allow(broker.BROKER_ID):
            raise HTTPException(status_code=429, detail="Order rate limit exceeded — please retry shortly.")

        from brokers import OrderRequest, OrderSide, OrderType, ProductType
        order_req = OrderRequest(
            symbol=req.symbol,
            quantity=req.quantity,
            side=OrderSide.BUY if req.action.upper() == "BUY" else OrderSide.SELL,
            order_type=OrderType.MARKET if req.order_type.upper() == "MARKET" else OrderType.LIMIT,
            product_type=ProductType.INTRADAY if req.product_type.upper() == "INTRADAY" else ProductType.MARGIN,
            price=req.price
        )
        
        response = broker.place_order(order_req)
        
        # Add to SQLite DB and global trades list for UI reflection
        from shared.state import record_trade
        record_trade(
            symbol=req.symbol,
            side=req.action.upper(),
            price=response.price or req.price or 0.0,
            timestamp=datetime.now(_IST).isoformat(),
            qty=req.quantity
        )
            
        return {"status": "success", "order_id": response.order_id, "message": response.message}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Order Execution Failed: {e}")
        raise HTTPException(status_code=500, detail='Order execution failed.')

def _set_emergency_stop(active: bool) -> None:
    """Atomically set/clear the `emergency_stop` flag in config/settings.json
    -- the cross-process signal main.py's on_tick() checks every tick to
    force-close all open positions (see emergency_flatten_all_positions()
    in trading_bot/main.py for the full incident/design writeup). Scoped to
    just this one key (its own tempfile+rename, not routed through the much
    larger /api/settings endpoint) so this dangerous, time-critical action
    never depends on unrelated credential-handling logic in that path.
    """
    import tempfile
    settings_path = "config/settings.json"
    existing = {}
    if os.path.exists(settings_path):
        with open(settings_path, "r", encoding="utf-8") as f:
            existing = json.load(f)
    existing["emergency_stop"] = active
    os.makedirs("config", exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir="config", prefix="settings_tmp_", suffix=".json")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(existing, f, indent=4)
    os.replace(tmp_path, settings_path)


@app.post("/api/panic-exit")
async def panic_exit(request: Request):
    """Nuclear Option: Immediately cancels all orders and squares off all positions."""
    if request.client and request.client.host not in ["127.0.0.1", "localhost", "::1"]:
        logger.warning(f"Unauthorized Panic Exit attempt from {request.client.host}")
        raise HTTPException(status_code=403, detail="Forbidden: Localhost access only")

    try:
        logger.warning("!!! PANIC EXIT TRIGGERED !!!")

        # Root-cause fix (found live, 2026-08-05): this endpoint used to
        # ONLY call broker.get_positions()/get_order_book()/place_order()
        # directly -- but those all unconditionally return []/no-op in
        # paper mode, and even with a real broker, main.py runs in a
        # SEPARATE process with zero awareness this endpoint was ever hit.
        # Setting this flag is the primary mechanism now (main.py checks it
        # every tick and force-closes everything it actually has open,
        # regardless of paper/live mode); the broker-level calls below
        # remain as a live-mode-only best-effort belt-and-suspenders layer.
        _set_emergency_stop(True)

        # Snapshot what's actually open right now, from the same file
        # main.py itself treats as authoritative -- broker.get_positions()
        # is not a reliable count in paper mode (always empty) and even in
        # live mode wouldn't reflect what THIS engine's own risk/exit logic
        # is tracking.
        flagged_positions = []
        if os.path.exists("config/active_positions.json"):
            with open("config/active_positions.json", "r", encoding="utf-8") as f:
                try:
                    flagged_positions = list(json.load(f).keys())
                except Exception:
                    flagged_positions = []

        # Broker-level cancel/close is best-effort and live-mode-only in
        # practice (paper mode's get_order_book()/get_positions() are
        # always empty) -- the emergency_stop flag above is what actually
        # guarantees this engine's real tracked positions get closed, so a
        # broker-side hiccup here must not turn the whole panic exit into a
        # reported failure.
        cancelled_count = 0
        closed_count = 0
        try:
            broker = BrokerFactory.get_active_broker()
            if broker.authenticate():
                from brokers import OrderStatus
                pending_orders = broker.get_order_book()
                for order in pending_orders:
                    if order.status in (OrderStatus.OPEN, OrderStatus.PENDING, OrderStatus.PARTIAL):
                        broker.cancel_order(order.order_id)
                        cancelled_count += 1

                positions = broker.get_positions()
                for pos in positions:
                    if pos.quantity != 0:
                        side = "SELL" if pos.quantity > 0 else "BUY"
                        qty = abs(pos.quantity)
                        try:
                            broker.place_order(OrderRequest(
                                symbol=pos.symbol,
                                side=OrderSide.SELL if side == "SELL" else OrderSide.BUY,
                                quantity=qty,
                                order_type=OrderType.MARKET,
                            ))
                            closed_count += 1
                            audit.log(AuditEvent.ORDER_PLACED,
                                      {"reason": "panic_exit", "symbol": pos.symbol, "side": side, "qty": qty})
                        except Exception as ex:
                            logger.error("Panic exit failed for broker position %s: %s", pos.symbol, ex)
                            audit.log(AuditEvent.ORDER_REJECTED,
                                      {"reason": "panic_exit", "symbol": pos.symbol, "side": side, "qty": qty, "error": str(ex)},
                                      severity="WARNING")
            else:
                logger.warning("Panic exit: broker not authenticated, skipping broker-level cancel/close (emergency_stop flag is still set).")
        except Exception as broker_exc:
            logger.error("Panic exit: broker-level cancel/close failed (emergency_stop flag is still set): %s", broker_exc)

        # Log the nuclear event
        log_file = "fyersApi.log"
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(log_file, "a") as f:
            f.write(
                f"\n[{timestamp}] !!! PANIC EXIT TRIGGERED !!! emergency_stop flag set; "
                f"{len(flagged_positions)} engine-tracked position(s) flagged for force-close: "
                f"{flagged_positions}. Broker-level cancelled={cancelled_count}, closed={closed_count}\n"
            )

        # Also record to the tamper-evident audit trail (the plaintext log
        # above is not append-only/HMAC-chained and can't detect tampering)
        audit.log(AuditEvent.EMERGENCY_STOP,
                  {"reason": "panic_exit", "flagged_positions": flagged_positions,
                   "broker_cancelled": cancelled_count, "broker_closed": closed_count},
                  severity="WARNING")

        return {
            "status": "success",
            "message": (
                "Emergency stop engaged. The live engine will force-close all tracked "
                "positions on its next tick (sub-second, not synchronous with this "
                "request) -- call GET /api/panic-exit/status to confirm it's actually "
                "flat, or POST /api/panic-exit/clear once you've verified that and want "
                "to resume normal trading."
            ),
            "flagged_positions": flagged_positions,
            "broker_cancelled": cancelled_count,
            "broker_closed": closed_count,
        }
    except Exception as e:
        logger.error("Panic Exit Failed: %s", e)
        raise HTTPException(status_code=500, detail='Panic exit failed.')


@app.get("/api/panic-exit/status")
async def panic_exit_status():
    """Whether emergency_stop is currently engaged, and what the live
    engine still shows as open (should reach `{}` within ~1 tick of the
    flag being set)."""
    settings = {}
    if os.path.exists("config/settings.json"):
        with open("config/settings.json", "r", encoding="utf-8") as f:
            settings = json.load(f)
    positions = {}
    if os.path.exists("config/active_positions.json"):
        with open("config/active_positions.json", "r", encoding="utf-8") as f:
            try:
                positions = json.load(f)
            except Exception:
                positions = {}
    return {
        "emergency_stop": bool(settings.get("emergency_stop", False)),
        "open_positions": list(positions.keys()),
    }


@app.post("/api/panic-exit/clear")
async def panic_exit_clear(request: Request):
    """Deliberately re-arms normal trading after an emergency stop.
    Requires the same localhost-only access as the panic-exit trigger --
    this is not something a remote caller should ever be able to flip
    either direction. Does NOT auto-clear on its own; a human must confirm
    positions are actually flat first (see /api/panic-exit/status)."""
    if request.client and request.client.host not in ["127.0.0.1", "localhost", "::1"]:
        raise HTTPException(status_code=403, detail="Forbidden: Localhost access only")
    _set_emergency_stop(False)
    audit.log(AuditEvent.EMERGENCY_STOP, {"reason": "cleared_by_operator"}, severity="WARNING")
    logger.warning("Emergency stop cleared by operator -- normal trading can resume.")
    return {"status": "success", "message": "Emergency stop cleared. Normal trading can resume."}

@app.get("/api/engine/status")
async def get_engine_status():
    return engine_state

@app.post("/api/engine/toggle")
async def toggle_engine(request: Request):
    if request.client and request.client.host not in ["127.0.0.1", "localhost", "::1"]:
        raise HTTPException(status_code=403, detail="Forbidden: Localhost access only")
        
    global engine_state
    engine_state["is_active"] = not engine_state["is_active"]
    if engine_state["is_active"]:
        engine_state["last_start_time"] = datetime.now().isoformat()
        logger.info(">>> TRADING ENGINE STARTED <<<")
    else:
        logger.info("<<< TRADING ENGINE STOPPED >>>")
    
    # Log the event
    log_file = "fyersApi.log"
    status = "STARTED" if engine_state["is_active"] else "STOPPED"
    with open(log_file, "a") as f:
        f.write(f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] SYSTEM: Trading Engine {status}\n")
        
    return engine_state

@app.get("/api/funds")
async def get_funds():
    """Fetches real funds from Fyers using the cached token."""
    try:
        from brokers.token_cache import load_token
        token = load_token("fyers")
        if not token:
            return {"s": "error", "message": "Token not found"}

        from fyers_apiv3 import fyersModel
        client_id = _get_fyers_client_id()
        
        fyers = fyersModel.FyersModel(client_id=client_id, is_async=False, token=token, log_path="")
        # Root-cause fix (found live, 2026-08-05): fyers_apiv3's FyersModel
        # is a SYNCHRONOUS (blocking) HTTP client -- calling it directly
        # inside an `async def` route handler blocks uvicorn's single
        # event loop for the full duration of the call, freezing EVERY
        # other request and WebSocket connection this server is handling,
        # not just this one. Live incident: a hung Fyers response froze
        # this entire process for ~2 hours (no crash, no error logged --
        # it just silently stopped accepting any connection, including
        # WebSocket keepalive pings, until manually restarted). Offloading
        # to a thread via asyncio.to_thread keeps the event loop free to
        # keep serving everything else while this call is in flight.
        funds = await asyncio.to_thread(fyers.funds)
        return funds
    except Exception as e:
        return {"s": "error", "message": str(e)}

@app.get("/api/quote")
async def get_quote(
    symbol: str = Query(..., description="The symbol (e.g., NSE:NIFTY50-INDEX)")
):
    """Fetches real-time quote (LTP) from Fyers."""
    try:
        from brokers.token_cache import load_token
        token = load_token("fyers")
        if not token:
            return {"s": "error", "message": "Token not found"}

        from fyers_apiv3 import fyersModel
        client_id = _get_fyers_client_id()
        
        fyers = fyersModel.FyersModel(client_id=client_id, is_async=False, token=token, log_path="")
        
        # Dynamic WebSocket Subscription for real-time updates
        global fyers_socket_instance
        with market_data_lock:
            needs_sub = fyers_socket_instance and symbol not in current_market_data
            
        if needs_sub:
            logger.info("Subscribing to %s dynamically via WebSocket...", symbol)
            try:
                fyers_socket_instance.subscribe(symbols=[symbol], data_type="symbolData")
                # Initialize to prevent duplicate subscriptions
                with market_data_lock:
                    current_market_data[symbol] = {"lp": 0.0, "chp": 0.0}
            except Exception as e:
                logger.warning("Failed to subscribe to %s: %s", symbol, e)

        data = {"symbols": symbol}
        # See /api/funds's comment above for why this is offloaded to a
        # thread -- this endpoint is polled far more frequently than funds,
        # making it the more likely trigger for the same event-loop freeze.
        quotes = await asyncio.to_thread(fyers.quotes, data=data)
        logger.debug("Quotes response for %s: %s", symbol, quotes)
        
        # Fallback: If WebSocket didn't receive ticks yet, populate from REST API!
        if quotes and quotes.get("s") == "ok" and "d" in quotes and len(quotes["d"]) > 0:
            quote_item = quotes["d"][0]
            v = quote_item.get("v", {})
            lp = v.get("lp")
            chp = v.get("chp", 0.0)
            if lp:
                with market_data_lock:
                    current_market_data[symbol] = {"lp": lp, "chp": chp}
                
        return quotes
    except Exception as e:
        return {"s": "error", "message": str(e)}

def generate_option_history_from_spot(spot_data: List[Dict[str, Any]], strike: float, opt_type: str) -> List[Dict[str, Any]]:
    """
    Generates Black-Scholes derived Option OHLCV history from underlying spot OHLCV data.
    Ensures 100% of option contracts (ITM, ATM, OTM, CE, PE) render accurate, smooth candles.
    """
    import math
    
    def norm_cdf(x):
        return (1.0 + math.erf(x / math.sqrt(2.0))) / 2.0

    def bs_price(S, K, T=0.02, r=0.07, sigma=0.18, is_call=True):
        if S <= 0 or K <= 0:
            return 0.05
        if T <= 0.0001:
            return max(0.05, S - K if is_call else K - S)
        d1 = (math.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * math.sqrt(T))
        d2 = d1 - sigma * math.sqrt(T)
        if is_call:
            p = S * norm_cdf(d1) - K * math.exp(-r * T) * norm_cdf(d2)
        else:
            p = K * math.exp(-r * T) * norm_cdf(-d2) - S * norm_cdf(-d1)
        return max(0.05, p)

    is_call = (opt_type.upper() == "CE")
    option_candles = []
    
    for candle in spot_data:
        s_open = float(candle.get("open", 0))
        s_high = float(candle.get("high", 0))
        s_low = float(candle.get("low", 0))
        s_close = float(candle.get("close", 0))
        s_vol = float(candle.get("volume", 0))
        time_val = candle.get("datetime", candle.get("time", candle.get("date")))
        
        # Dynamic IV Skew estimation
        dist = abs(s_close - strike) / max(1.0, s_close)
        iv = 0.16 + (dist * 0.4)
        
        c_open = round(bs_price(s_open, strike, 0.02, 0.07, iv, is_call), 2)
        c_close = round(bs_price(s_close, strike, 0.02, 0.07, iv, is_call), 2)
        
        p1 = bs_price(s_high, strike, 0.02, 0.07, iv, is_call)
        p2 = bs_price(s_low, strike, 0.02, 0.07, iv, is_call)
        
        c_high = round(max(c_open, c_close, p1, p2), 2)
        c_low = round(max(0.05, min(c_open, c_close, p1, p2)), 2)
        
        option_candles.append({
            "datetime": time_val,
            "open": c_open,
            "high": c_high,
            "low": c_low,
            "close": c_close,
            "volume": int(s_vol * 0.15) if s_vol else 1000
        })
        
    return option_candles

def load_csv_history(symbol: str, start_date: str, end_date: str, timeframe: str, data_dir: str | None = None) -> List[Dict[str, Any]]:
    """Loads historical OHLCV candles from local CSV cache as fail-safe fallback.

    Root-cause fix: the fallback list used to include the NIFTY/SENSEX/
    BANKNIFTY cache files unconditionally regardless of the requested
    symbol, so a broker failure for e.g. "RELIANCE" would silently return
    NIFTY candles mislabeled as RELIANCE's history. Only ever fall back to
    a cache file that actually corresponds to the requested symbol.

    `data_dir` defaults to this file's own data/ directory (the real,
    gitignored CSV cache) but can be overridden — used by
    tests/test_option_history_derivation.py to point at small, committed
    fixture CSVs instead, since data/*.csv itself is gitignored and isn't
    present in a clean CI checkout.
    """
    import os
    import pandas as pd

    clean_tf = timeframe.replace(' ', '')
    clean_sym = symbol.replace(':', '_').replace(' ', '').upper()
    if data_dir is None:
        data_dir = os.path.join(os.path.dirname(__file__), "data")

    possible_files = [f"{clean_sym}_{clean_tf}.csv"]
    # Order matters: "FINNIFTY" and "NIFTYBANK"/"BANKNIFTY" both contain the
    # substring "NIFTY", so the generic NIFTY branch must be checked last —
    # otherwise a FINNIFTY request with no cache file of its own would fall
    # through to this branch and silently serve NIFTY candles mislabeled as
    # FINNIFTY's history, exactly the bug this function's docstring already
    # describes fixing for RELIANCE. FINNIFTY has no dedicated fallback file
    # here (none is committed/cached yet); it still gets its own exact-match
    # lookup via `possible_files[0]` above, it just has no *second* fallback
    # the way NIFTY/BANKNIFTY/SENSEX do.
    if "NIFTYBANK" in clean_sym or "BANKNIFTY" in clean_sym:
        possible_files.append("NSE_NIFTYBANK-INDEX_5Min.csv")
    elif "SENSEX" in clean_sym:
        possible_files.append("BSE_SENSEX-INDEX_5Min.csv")
    elif "FINNIFTY" in clean_sym:
        pass  # no dedicated fallback file — see note above
    elif "NIFTY" in clean_sym or "NSEI" in clean_sym:
        possible_files += ["NSE_NIFTY50-INDEX_5Min.csv", "NIFTY_cache.csv"]
    elif "RELIANCE" in clean_sym:
        possible_files.append("RELIANCE.NS_1min.csv")

    for fname in possible_files:
        fpath = os.path.join(data_dir, fname)
        if os.path.exists(fpath):
            try:
                df = pd.read_csv(fpath)
                # Column names vary by source cache (e.g. the index caches use
                # lowercase "datetime", RELIANCE.NS_1min.csv uses "Datetime") —
                # normalize so the lookup below and downstream consumers
                # (generate_option_history_from_spot's candle.get("open")
                # etc.) see a consistent lowercase schema either way.
                df.columns = [str(c).lower() for c in df.columns]
                if 'datetime' in df.columns:
                    mask = (df['datetime'] >= start_date) & (df['datetime'] <= f"{end_date} 23:59:59")
                    df_sub = df.loc[mask]
                    if not df_sub.empty:
                        return df_sub.to_dict(orient='records')
                    return df.tail(300).to_dict(orient='records')
            except Exception as e:
                logger.warning("Failed to load CSV history %s: %s", fpath, e)
    return []

def _fetch_yfinance_today(symbol: str, timeframe: str) -> List[Dict[str, Any]]:
    """Fetch today's intraday OHLCV candles via yfinance to ensure 09:15 to current time is always present."""
    try:
        import yfinance as yf
        import pandas as pd
        
        yf_sym_map = {
            "NSE:NIFTY50-INDEX": "^NSEI",
            "NIFTY": "^NSEI",
            "NSE:NIFTYBANK-INDEX": "^NSEBANK",
            "BANKNIFTY": "^NSEBANK",
            "BSE:SENSEX-INDEX": "^BSESN",
            "SENSEX": "^BSESN",
        }
        clean_sym = symbol.replace("NSE:", "").replace("BSE:", "").replace("-INDEX", "").replace("-EQ", "").strip()
        yf_symbol = yf_sym_map.get(symbol, yf_sym_map.get(clean_sym, f"{clean_sym}.NS"))
        
        tf_map = {
            "1 Min": "1m", "5 Min": "5m", "15 Min": "15m", "30 Min": "30m",
            "1 Hour": "60m", "1 Day": "1d", "1 Week": "1wk", "1 Month": "1mo"
        }
        interval = tf_map.get(timeframe, "5m")
        period = "5d" if "Day" in timeframe or "Week" in timeframe or "Month" in timeframe else "1d"
        
        df = yf.download(yf_symbol, period=period, interval=interval, progress=False)
        if df is None or df.empty:
            return []
        
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
            
        candles = []
        is_daily = "Day" in timeframe or "Week" in timeframe or "Month" in timeframe
        fmt = "%Y-%m-%d" if is_daily else "%Y-%m-%d %H:%M:%S"
        
        for ts, row in df.iterrows():
            dt_ist = ts.tz_convert("Asia/Kolkata") if getattr(ts, "tzinfo", None) else ts
            candles.append({
                "datetime": dt_ist.strftime(fmt),
                "open": float(row["Open"]),
                "high": float(row["High"]),
                "low": float(row["Low"]),
                "close": float(row["Close"]),
                "volume": int(row.get("Volume", 0)) if not pd.isna(row.get("Volume", 0)) else 0
            })
        return candles
    except Exception as e:
        logger.warning(f"yfinance today candles fetch failed for {symbol}: {e}")
        return []

def _ensure_today_candles(data: List[Dict[str, Any]], symbol: str, timeframe: str) -> List[Dict[str, Any]]:
    """Appends today's 09:15 to current time candles if missing from broker or CSV cache data."""
    if not data:
        return _fetch_yfinance_today(symbol, timeframe)
        
    today_candles = _fetch_yfinance_today(symbol, timeframe)
    if not today_candles:
        return data
        
    seen = {d.get("datetime") for d in data}
    combined = list(data)
    for tc in today_candles:
        dt = tc.get("datetime")
        if dt not in seen:
            seen.add(dt)
            combined.append(tc)
        else:
            for idx, item in enumerate(combined):
                if item.get("datetime") == dt:
                    combined[idx] = tc
                    break
            
    return combined

@app.get("/api/history")
async def get_history(
    symbol: str = Query(..., description="The stock ticker or option symbol (e.g., RELIANCE, NIFTY, NIFTY 24350 CE)"),
    start_date: str = Query(..., description="Start date (YYYY-MM-DD)"),
    end_date: str = Query(..., description="End date (YYYY-MM-DD)"),
    timeframe: str = Query("5 Min", description="Timeframe")
):
    """Fetches real historical data dynamically from the ACTIVE BROKER or Option Derivation Engine."""
    try:
        from shared.security.symbol_parser import parse_option_symbol
        opt_info = parse_option_symbol(symbol)
        
        spot_data = []
        data = []
        
        try:
            broker = BrokerFactory.get_active_broker()
            broker.authenticate()
        except Exception as auth_err:
            logger.warning("Broker auth warning in get_history: %s", auth_err)
        
        if opt_info["is_option"]:
            # Option symbol requested! Fetch underlying index spot candles and derive option history via Black-Scholes
            underlying_sym = opt_info["underlying"]
            underlying_broker_sym = format_broker_symbol(underlying_sym)
            
            logger.info("Option history requested for %s. Deriving via underlying %s (Strike %.1f %s)", symbol, underlying_broker_sym, opt_info["strike"], opt_info["opt_type"])
            try:
                broker = BrokerFactory.get_active_broker()
                spot_data = broker.get_historical_data(underlying_broker_sym, start_date, end_date, timeframe)
            except Exception:
                pass
                
            if not spot_data:
                logger.info("Broker returned empty spot data for %s, trying CSV dataset cache fallback...", underlying_sym)
                spot_data = load_csv_history(underlying_broker_sym, start_date, end_date, timeframe)
                
            spot_data = _ensure_today_candles(spot_data, underlying_broker_sym, timeframe)
            
            if not spot_data:
                raise HTTPException(status_code=404, detail=f"No underlying data returned for {underlying_broker_sym}")
                
            option_data = generate_option_history_from_spot(spot_data, opt_info["strike"], opt_info["opt_type"])
            return {
                "symbol": symbol,
                "underlying": underlying_sym,
                "strike": opt_info["strike"],
                "opt_type": opt_info["opt_type"],
                "timeframe": timeframe,
                "data_points": len(option_data),
                "data": option_data
            }

        # Equity / Index history request
        formatted_symbol = format_broker_symbol(symbol)
        logger.info("Fetching history via broker: %s for %s", formatted_symbol, formatted_symbol)
        try:
            broker = BrokerFactory.get_active_broker()
            data = broker.get_historical_data(formatted_symbol, start_date, end_date, timeframe)
        except Exception:
            pass
            
        if not data:
            logger.info("Broker returned empty data for %s, trying CSV dataset cache fallback...", formatted_symbol)
            data = load_csv_history(formatted_symbol, start_date, end_date, timeframe)
            
        data = _ensure_today_candles(data, formatted_symbol, timeframe)
        
        if not data:
            raise HTTPException(status_code=404, detail=f"No data returned by broker for {formatted_symbol}")
            
        return {
            "symbol": formatted_symbol,
            "timeframe": timeframe,
            "data_points": len(data),
            "data": data
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error('Failed to fetch history for %s: %s', symbol, e)
        raise HTTPException(status_code=500, detail=f'Failed to fetch historical data for {symbol}.')

@app.get("/api/inspect")
def inspect_broker():
    broker = BrokerFactory.get_active_broker()
    cached_token = broker._load_cached_token()
    creds_token = broker.credentials.get("access_token")
    return {
        "client_id": broker.credentials.get("client_id"),
        "cached_token_present": bool(cached_token),
        "token_in_credentials_present": bool(creds_token),
        "live_trading_mode": broker.paper_mode
    }

@app.get("/api/backtest")
async def get_backtest(
    symbol: str = Query(..., description="The stock ticker"),
    start_date: str = Query(..., description="Start date"),
    end_date: str = Query(..., description="End date"),
    timeframe: str = Query("5 Min", description="Timeframe"),
    strategy: str = Query("ema_rsi", description="Strategy name"),
    initial_capital: float = Query(100000.0, description="Initial Capital"),
    quantity: int = Query(25, description="Trading quantity/lot size"),
    stoploss_pct: float = Query(1.2, description="Stoploss %"),
    target_pct: float = Query(2.5, description="Target %"),
    enable_ema_filter: bool = Query(True),
    enable_volume_filter: bool = Query(False),
    enable_adx_filter: bool = Query(False),
    enable_vwap_filter: bool = Query(True),
    enable_rsi_filter: bool = Query(True),
    enable_squeeze_filter: bool = Query(False),
    enable_extension_filter: bool = Query(False),
    enable_cpr_filter: bool = Query(False),
    enable_aggression_filter: bool = Query(False),
    donchian_period: int = Query(10, description="Donchian Channel breakout period"),
    trailing_sl: bool = Query(True, description="Enable trailing stop loss"),
    trail_trigger: float = Query(0.8, description="Trail trigger percentage"),
    trail_offset: float = Query(0.2, description="Trail offset percentage"),
    enable_pyramiding: bool = Query(True, description="Enable scaling into winning trades"),
    scale_pct: float = Query(0.2, description="Percentage of profit to scale in"),
    max_scales: int = Query(2, description="Maximum number of times to scale in"),
    max_daily_loss_pct: float = Query(3.0, description="Stop trading if daily loss exceeds this % of capital"),
    max_daily_trades: int = Query(6, description="Maximum number of trades allowed per day"),
    enable_compounding: bool = Query(True, description="Enable dynamic equity compounding position sizing")
):
    """Triggers a true Python backtest using the actual strategy files and broker data."""
    try:
        broker = BrokerFactory.get_active_broker()
        broker.authenticate()
        
        # Map symbol using institutional formatter
        symbol = format_broker_symbol(symbol)
            
        try:
            data = broker.get_historical_data(symbol, start_date, end_date, timeframe)
        except Exception as e:
            logger.warning("Broker history fetch failed: %s. Checking local cache fallback...", e)
            data = None
            
        if not data:
            return {"error": f"No data returned by broker for {symbol}. If using yfinance, intraday data has history limits (e.g., 7 days for 1m, 60 days for 5m). Ensure your broker is connected or adjust the date range."}
            
        # Convert list of dicts to DataFrame for the strategy
        df = pd.DataFrame(data)
        logger.info("[API Backtest] Loaded DataFrame: %d rows. Strategy: %s", len(df), strategy)
        
        # Load Settings (cached — no disk I/O on every backtest call)
        settings = _load_config_settings()
                
        ema_fast = settings.get("ema_fast", 20)
        ema_slow = settings.get("ema_slow", 50)
        rsi_window = settings.get("rsi_window", 14)
        rsi_buy = settings.get("rsi_buy", 55)
        rsi_sell = settings.get("rsi_sell", 45)
        
        # Lowercase columns for the strategy
        df.columns = [c.lower() for c in df.columns]
        
        # Generate Signals using Python Strategy via Registry
        try:
            from fastapi.concurrency import run_in_threadpool
            signals_data = await run_in_threadpool(
                registry.run_strategy,
                strategy, 
                df, 
                ema_fast=ema_fast, 
                ema_slow=ema_slow, 
                rsi_window=rsi_window, 
                rsi_buy_thresh=rsi_buy, 
                rsi_sell_thresh=rsi_sell,
                stoploss_pct=stoploss_pct,
                target_pct=target_pct,
                enable_ema_filter=enable_ema_filter,
                enable_volume_filter=enable_volume_filter,
                enable_adx_filter=enable_adx_filter,
                enable_vwap_filter=enable_vwap_filter,
                enable_rsi_filter=enable_rsi_filter,
                enable_squeeze_filter=enable_squeeze_filter,
                enable_extension_filter=enable_extension_filter,
                enable_cpr_filter=enable_cpr_filter,
                enable_aggression_filter=enable_aggression_filter,
                donchian_period=donchian_period
            )
            
            # Unpack signals and rejection logs if returned as tuple
            if isinstance(signals_data, tuple):
                signals, rejection_logs = signals_data
            else:
                signals, rejection_logs = signals_data, []
            logger.info("[API Backtest] Strategy signals generated: %d. Rejections: %d", len(signals[signals != 0]), len(rejection_logs))
        except ValueError:
            # Fallback to default if strategy not found
            signals = ema_rsi_signals(
                df, 
                ema_fast=ema_fast, 
                ema_slow=ema_slow, 
                rsi_window=rsi_window, 
                rsi_buy_thresh=rsi_buy, 
                rsi_sell_thresh=rsi_sell
            )
            rejection_logs = []
        
        # Use the formal backtesting engine function for institutional accuracy
        from backtesting_engine.run import run_intraday_backtest
        
        # Remove explicitly passed args from settings to prevent multiple value arguments TypeError
        backtest_settings = settings.copy()
        for key in ["target_pct", "stoploss_pct", "initial_capital", "multiplier", "slippage_bps", "commission_per_trade", "options_delta", "rejection_logs"]:
            backtest_settings.pop(key, None)
        
        # Override trailing SL settings with query parameters
        backtest_settings["trailing_sl"] = trailing_sl if isinstance(trailing_sl, bool) else str(trailing_sl).lower() == 'true'
        backtest_settings["trail_trigger"] = trail_trigger
        backtest_settings["trail_offset"] = trail_offset
        backtest_settings["enable_pyramiding"] = enable_pyramiding if isinstance(enable_pyramiding, bool) else str(enable_pyramiding).lower() == 'true'
        backtest_settings["scale_pct"] = scale_pct
        backtest_settings["max_scales"] = max_scales
        backtest_settings["max_daily_loss_pct"] = max_daily_loss_pct
        backtest_settings["max_daily_trades"] = max_daily_trades
        backtest_settings["enable_compounding"] = enable_compounding if isinstance(enable_compounding, bool) else str(enable_compounding).lower() == 'true'
        
        from fastapi.concurrency import run_in_threadpool
        
        results = await run_in_threadpool(
            run_intraday_backtest,
            df, 
            signals, 
            initial_capital=initial_capital,
            slippage_bps=2.0, 
            commission_per_trade=20.0,
            multiplier=quantity,       # Dynamic quantity from UI
            options_delta=0.5,         # Simulate ATM Options
            stoploss_pct=stoploss_pct,
            target_pct=target_pct,
            rejection_logs=rejection_logs,
            **backtest_settings
        )
        
        # Sanitize all results to remove numpy int64/float64 for JSON serialization
        results = convert_numpy_types(results)

        # Construct candlestickData and chart_markers for Lightweight Charts
        candlestick_data = []
        try:
            if 'datetime' in df.columns:
                for _, row in df.iterrows():
                    candlestick_data.append({
                        "time": str(row['datetime']),
                        "open": float(row['open']),
                        "high": float(row['high']),
                        "low": float(row['low']),
                        "close": float(row['close']),
                        "volume": float(row.get('volume', 0))
                    })
        except Exception as _c_err:
            logger.warning("[API Backtest] Failed to parse candlestick data: %s", _c_err)

        trades = results["trades"]
        chart_markers = []
        for t in trades:
            e_time = t.get("time")
            if not e_time:
                continue
            is_buy = t.get("type") == "BUY"
            color = "#00F5A0" if is_buy else "#FF3B69"
            position = "belowBar" if is_buy else "aboveBar"
            shape = "arrowUp" if is_buy else "arrowDown"
            entry_p = t.get('entry', 0)
            text = f"{'BUY' if is_buy else 'SELL'} @ {entry_p:,.1f}"
            
            chart_markers.append({
                "time": str(e_time)[:16],
                "position": position,
                "color": color,
                "shape": shape,
                "text": text,
                "size": 2,
                "tradeId": t.get("id"),
                "pnl": t.get("pnl", 0),
                "exit_reason": t.get("exit_reason")
            })

        import gc
        del df
        gc.collect()
        
        # Save results for analytics!
        backtest_output = {
            "symbol": symbol,
            "timeframe": timeframe,
            "strategy": strategy,
            "stats": results["stats"],
            "equityCurve": results["equityCurve"],
            "trades": results["trades"],
            "chart_markers": chart_markers
        }
        with open("backtest_results.json", "w") as f:
            json.dump(backtest_output, f, indent=4)
            
        # Read settings for target and stoploss
        settings = {}
        if os.path.exists("config/settings.json"):
            with open("config/settings.json", "r") as f:
                settings = json.load(f)
                
        # Calculate extra stats
        call_trades = [t for t in trades if t['type'] == 'BUY']
        put_trades = [t for t in trades if t['type'] == 'SELL']
        
        # Add to stats
        results["stats"]["totalCE"] = len(call_trades)
        results["stats"]["totalPE"] = len(put_trades)
            
        # Add Monte Carlo Simulation
        monte_carlo_stats = {}
        try:
            from backtesting_engine.monte_carlo import MonteCarloSimulator
            trades_pnl = [t.get("pnl", 0.0) for t in trades]
            mc_sim = MonteCarloSimulator(trades_pnl, initial_capital=initial_capital)
            monte_carlo_stats = mc_sim.simulate(num_simulations=1000, num_trades_per_sim=len(trades) if trades else 100)
        except Exception as mc_e:
            logger.error(f"Monte Carlo simulation failed: {mc_e}")
            
        return {
            "symbol": symbol,
            "timeframe": timeframe,
            "strategy": strategy,
            "stats": results["stats"],
            "monte_carlo": monte_carlo_stats,
            "equityCurve": results["equityCurve"],
            "trades": results["trades"],
            "candlestickData": candlestick_data,
            "chartMarkers": chart_markers,
            "rejectionLogs": results.get("rejectionLogs", [])
        }
        
    except Exception as e:
        logger.error('Backtest failed: %s', e)
        raise HTTPException(status_code=500, detail='Backtest failed.')

@app.get("/equity-data")
async def get_equity_data(symbol: str = "NIFTY"):
    """Returns real price action data mapped as equity data for the dashboard."""
    try:
        broker = BrokerFactory.get_active_broker()
        broker.authenticate()
        # IST-anchored (not server-local) so "today" never silently excludes
        # today's IST candles for a server whose OS clock isn't set to IST.
        end_date = datetime.now(_IST)
        start_date = end_date - timedelta(days=2) # Last 2 days to ensure data
        
        # Map symbol using institutional formatter
        symbol = format_broker_symbol(symbol)
        
        data = broker.get_historical_data(symbol, start_date.strftime('%Y-%m-%d'), end_date.strftime('%Y-%m-%d'), "15 Min")
        
        if not data:
            return []
            
        df = pd.DataFrame(data)
        df.columns = [c.lower() for c in df.columns]
        
        trend_data = []
        for i in range(len(df)):
            current_time = df['datetime'].iloc[i].split(' ')[1][:5] if 'datetime' in df.columns else "00:00"
            trend_data.append({
                "name": current_time,
                "value": float(df['close'].iloc[i])
            })
        return trend_data
    except Exception as e:
        logger.error("Error in /equity-data: %s", e)
        return []

signals_cache_store = {}

def compute_signals(
    symbol: str = "NIFTY"
):
    """Generates live signals using the actual strategy files and broker data."""
    try:
        # IST-anchored (not server-local) so "today" never silently excludes
        # today's IST candles for a server whose OS clock isn't set to IST.
        end_date = datetime.now(_IST)
        start_date = end_date - timedelta(days=10)
        
        # Map symbol using institutional formatter
        symbol_formatted = format_broker_symbol(symbol)

        broker = BrokerFactory.get_active_broker()
        broker.authenticate()
        data = broker.get_historical_data(symbol_formatted, start_date.strftime('%Y-%m-%d'), end_date.strftime('%Y-%m-%d'), "5 Min")
        
        if not data:
            raise ValueError(f"No data found for signals for {symbol}")
            
        df = pd.DataFrame(data)
        df.columns = [c.lower() for c in df.columns]

        # Generate Signals via Registry using advanced_ai!
        from trading_bot.strategies.advanced_ai_ml_strategy import generate_signals as advanced_ai_signals
        signals = advanced_ai_signals(df)
        
        # Read scores from dataframe and clean NaN/None/non-numeric values
        call_scores = df['call_score'] if 'call_score' in df.columns else pd.Series(0, index=df.index)
        put_scores = df['put_score'] if 'put_score' in df.columns else pd.Series(0, index=df.index)
        
        # Clean the scores (replace NaN, None, etc with 0)
        call_scores = pd.to_numeric(call_scores, errors='coerce').fillna(0).astype(int)
        put_scores = pd.to_numeric(put_scores, errors='coerce').fillna(0).astype(int)
        
        # Generate trendData using the max score of each candle!
        trend_data = []
        for i in range(max(0, len(df) - 20), len(df)):
            current_time = df['datetime'].iloc[i].split(' ')[1][:5] if 'datetime' in df.columns else "00:00"
            score = int(max(call_scores.iloc[i], put_scores.iloc[i]))
            trend_data.append({
                "name": current_time,
                "value": score
            })
            
        # Generate real signals list from the last 5 days data!
        real_signals = []
        for i in range(len(df)):
            if signals.iloc[i] == 1:
                current_time = df['datetime'].iloc[i].split(' ')[1][:5] if 'datetime' in df.columns else "00:00"
                real_signals.append({
                    "symbol": symbol,
                    "type": "CALL BUY",
                    "bias": "BUY",
                    "strength": "Strong" if call_scores.iloc[i] > 85 else "Moderate",
                    "confidence": int(call_scores.iloc[i]),
                    "time": current_time,
                    "reason": f"Institutional crossover with score {int(call_scores.iloc[i])}"
                })
            elif signals.iloc[i] == -1:
                current_time = df['datetime'].iloc[i].split(' ')[1][:5] if 'datetime' in df.columns else "00:00"
                real_signals.append({
                    "symbol": symbol,
                    "type": "PUT BUY",
                    "bias": "SELL",
                    "strength": "Strong" if put_scores.iloc[i] > 85 else "Moderate",
                    "confidence": int(put_scores.iloc[i]),
                    "time": current_time,
                    "reason": f"Institutional crossover with score {int(put_scores.iloc[i])}"
                })

        # Always use the most recent scores (last candle) for the current state,
        # whether the market is open or closed. Using old non-zero scores causes 
        # stale "Bearish" or "Bullish" signals after hours!
        valid_calls = call_scores.dropna()
        valid_puts = put_scores.dropna()
        last_call_score = int(valid_calls.iloc[-1]) if len(valid_calls) > 0 else 0
        last_put_score = int(valid_puts.iloc[-1]) if len(valid_puts) > 0 else 0
        
        # If both are exactly 0 (flat close), calculate a micro-trend from the last few candles
        # to give a slight bias instead of a dead 0% neutral, unless it's truly completely flat.
        if last_call_score == 0 and last_put_score == 0 and len(df) > 5:
            recent_trend = df['close'].iloc[-1] - df['close'].iloc[-5]
            if recent_trend > 0:
                last_call_score = min(40, int((recent_trend / df['close'].iloc[-5]) * 5000))
            elif recent_trend < 0:
                last_put_score = min(40, int((abs(recent_trend) / df['close'].iloc[-5]) * 5000))
                
        confidence = max(last_call_score, last_put_score)
        
        bias = "NEUTRAL"
        status = "Scanning..."
        
        if last_call_score >= 75:
            bias = "BUY"
            status = "Institutional Call Buy Setup"
        elif last_put_score >= 75:
            bias = "SELL"
            status = "Institutional Put Buy Setup"
        else:
            # If scores are very close (within 5 points) and not extremely strong, use actual recent price trend as tie-breaker!
            if abs(last_call_score - last_put_score) <= 8 and max(last_call_score, last_put_score) < 65 and len(df) >= 4:
                recent_trend = df['close'].iloc[-1] - df['close'].iloc[-4]
                if recent_trend > 0:
                    bias = "BULLISH"
                    status = "Mild Bullish Bias"
                elif recent_trend < 0:
                    bias = "BEARISH"
                    status = "Mild Bearish Bias"
                else:
                    bias = "NEUTRAL"
                    status = "Awaiting Setup"
            elif last_call_score > last_put_score:
                bias = "BULLISH"
                status = "Mild Bullish Bias"
            elif last_put_score > last_call_score:
                bias = "BEARISH"
                status = "Mild Bearish Bias"
            else:
                bias = "NEUTRAL"
                status = "Awaiting Setup"
        
        result = {
            "confidence": confidence,
            "status": status,
            "bias": f"{bias} BIAS",
            "trendData": trend_data,
            "signals": real_signals[-10:][::-1],
            "timestamp": time.time()
        }
        signals_cache_store[symbol] = result
        return result
    except Exception as e:
        logger.error("Error in compute_signals: %s", e)
        err_res = {"error": str(e), "confidence": 50, "direction": "NEUTRAL", "timestamp": time.time(), "bias": "ERROR", "status": "Connection Error"}
        signals_cache_store[symbol] = err_res
        return err_res

@app.get("/api/signals")
async def get_signals_api(
    symbol: str = Query("NIFTY", description="The stock ticker")
):
    """Returns cached AI signals instantly to avoid blocking UI."""
    cached = signals_cache_store.get(symbol, {})
    is_calculating = cached.get("direction") == "CALCULATING"
    
    # Refresh cache if older than 30 seconds
    needs_refresh = False
    if not cached or (not is_calculating and "timestamp" in cached and time.time() - cached["timestamp"] > 30):
        needs_refresh = True
        
    if needs_refresh:
        # Prevent race conditions by marking as calculating immediately
        signals_cache_store[symbol] = {**cached, "direction": "CALCULATING"} if cached else {"symbol": symbol, "confidence": 50, "direction": "CALCULATING"}
        from fastapi.concurrency import run_in_threadpool
        import asyncio
        asyncio.create_task(run_in_threadpool(compute_signals, symbol))
        return cached if cached else {"symbol": symbol, "confidence": 50, "direction": "CALCULATING"}
        
    return cached

@app.get("/api/test_connection")
async def test_connection():
    """Tests connection to the active broker and returns the balance."""
    try:
        broker = BrokerFactory.get_active_broker()
        # Try to authenticate
        is_auth = broker.authenticate()
        if not is_auth:
            raise HTTPException(status_code=401, detail="Broker not authenticated. Please log in first.")
            
        balance = broker.get_balance()
        
        # Balance is a namedtuple or object with available_cash
        avail = balance.available_cash if hasattr(balance, 'available_cash') else 0.0
        
        return {
            "status": "success",
            "broker": broker.DISPLAY_NAME,
            "balance": avail
        }
    except Exception as e:
        logger.error('Connection test failed: %s', e)
        raise HTTPException(status_code=500, detail='Connection test failed.')

@app.get("/api/state")
async def get_state(live: bool = Query(False)):
    """Returns the current state of the bot (equity, pnl, trades)."""
    try:
        from shared.state import load_state
        state = load_state(reload_trades=True)
        
        # If live mode, try to fetch real broker balance
        if live:
            try:
                broker = BrokerFactory.get_active_broker()
                if broker.authenticate():
                    balance_data = broker.get_balance()
                    # Fyers returns available_cash
                    real_balance = getattr(balance_data, 'available_cash', 0.0)
                    if real_balance > 0:
                        state["equity"] = real_balance
                    else:
                        # Fallback if balance is 0 or invalid
                        state["equity"] = 100000.0
                else:
                    # Dummy value if not authenticated
                    state["equity"] = 100000.0
            except Exception:
                # Dummy value if any error occurs fetching balance
                state["equity"] = 100000.0
        else:
            # For paper/test mode, ensure we have a valid starting equity
            if state.get("equity", 0) <= 0:
                state["equity"] = 100000.0
                
        return state
    except Exception as e:
        logger.error('Failed to fetch state: %s', e)
        raise HTTPException(status_code=500, detail='Failed to fetch state.')

@app.get("/api/positions")
async def get_positions():
    """Fetches active positions from the current broker."""
    try:
        from dataclasses import asdict
        broker = BrokerFactory.get_active_broker()
        if not broker.authenticate():
            return {"status": "error", "message": "Broker not authenticated", "positions": []}
            
        if broker.paper_mode:
            # In paper mode, read positions directly from the active_positions.json file maintained by main.py
            import os, json
            from pathlib import Path
            positions_path = Path(__file__).resolve().parent / "config" / "active_positions.json"
            positions_data = []
            if positions_path.exists():
                try:
                    with open(positions_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        # data is dict: { "SYMBOL": { ...position details... } }
                        positions_data = list(data.values())
                except Exception as e:
                    logger.error(f"Failed to read paper positions: {e}")
            return {"status": "success", "positions": positions_data}
            
        positions = [asdict(p) for p in broker.get_positions()]
        return {"status": "success", "positions": positions}
    except Exception as e:
        # Return empty list instead of 500 for better UI stability
        return {"status": "error", "message": str(e), "positions": []}

@app.get("/api/logs")
async def get_logs(lines: int = Query(20)):
    """Reads the last N lines from the primary log file."""
    try:
        import os
        log_file = "fyersApi.log"
        if not os.path.exists(log_file):
            return {"logs": ["Log file not found."]}
            
        with open(log_file, "r") as f:
            # Simple way to get last N lines
            all_lines = f.readlines()
            last_lines = all_lines[-lines:] if len(all_lines) > lines else all_lines
            return {"logs": [line.strip() for line in last_lines]}
    except Exception as e:
        return {"logs": [f"Error reading logs: {str(e)}"]}

@app.get("/api/strategies")
async def get_strategies():
    """Returns the list of auto-discovered strategies."""
    try:
        from trading_bot.strategies.registry import registry
        return {"strategies": registry.registered_strategies}
    except Exception as e:
        logger.error('Failed to fetch strategies: %s', e)
        raise HTTPException(status_code=500, detail='Failed to fetch strategies.')

@app.get("/api/strategy/parameters")
async def get_strategy_parameters(
    name: str = Query(..., description="The strategy name")
):
    """Returns the parameters of a specific strategy."""
    try:
        from trading_bot.strategies.registry import registry
        params = registry.get_parameters(name)
        return {"parameters": params}
    except Exception as e:
        logger.error('Failed to fetch strategy parameters: %s', e)
        raise HTTPException(status_code=500, detail='Failed to fetch strategy parameters.')

@app.get("/api/settings")
async def get_settings():
    try:
        import os
        import json
        settings = {}
        if os.path.exists("config/settings.json"):
            with open("config/settings.json", "r") as f:
                settings = json.load(f)
                
        # Load secure credentials and merge
        from brokers.credentials import load_credentials
        creds = load_credentials("fyers")
        settings.update(creds)
        
        return settings
    except Exception as e:
        logger.error('Failed to fetch settings: %s', e)
        raise HTTPException(status_code=500, detail='Failed to fetch settings.')

@app.post("/api/settings")
async def save_settings(new_settings: dict):
    try:
        import os
        import json
        import tempfile
        
        # Extract credential fields
        creds = {}
        for key in ["fyers_user_id", "fyers_pin", "fyers_totp_key"]:
            if key in new_settings:
                creds[key] = new_settings.pop(key)
                
        # Validate credentials if provided
        if "fyers_pin" in creds and creds["fyers_pin"]:
            if not (creds["fyers_pin"].isdigit() and len(creds["fyers_pin"]) == 4):
                raise HTTPException(status_code=400, detail="MPIN must be exactly 4 digits!")
                
        if "fyers_totp_key" in creds and creds["fyers_totp_key"]:
            import base64
            try:
                key = creds["fyers_totp_key"].replace(" ", "").upper()
                # Add padding if missing
                missing_padding = len(key) % 8
                if missing_padding:
                    key += '=' * (8 - missing_padding)
                base64.b32decode(key)
            except Exception:
                raise HTTPException(status_code=400, detail="Invalid TOTP Secret Key! Must be a valid Base32 string.")
                
        if "fyers_user_id" in creds and creds["fyers_user_id"]:
            if len(creds["fyers_user_id"]) < 3:
                raise HTTPException(status_code=400, detail="Client ID is too short!")

        # Save credentials securely (Encrypted and Signed)
        if creds:
            from brokers.credentials import load_credentials, save_credentials
            import subprocess
            import sys
            
            # Load existing credentials to backup
            backup_creds = load_credentials("fyers")
            
            # Merge and save new ones
            existing_creds = dict(backup_creds)
            existing_creds.update(creds)
            save_credentials("fyers", existing_creds)
            
            # Test the connection with new credentials
            process = subprocess.run(
                [sys.executable, "scripts/auth/auto_login_fyers.py"],
                capture_output=True,
                text=True,
                check=False,
                cwd=os.getcwd()
            )
            
            if process.returncode != 0:
                # Revert to backup if failed!
                save_credentials("fyers", backup_creds)
                raise HTTPException(status_code=400, detail="Incorrect credentials or unable to login. Please check your details.")
            
        # Save remaining settings to config/settings.json using ATOMIC WRITE
        # (prevents file corruption if process crashes during write)
        settings_path = "config/settings.json"
        existing = {}
        if os.path.exists(settings_path):
            with open(settings_path, "r") as f:
                existing = json.load(f)
                
        # Remove any existing plain text credentials from settings
        for key in ["fyers_user_id", "fyers_pin", "fyers_totp_key"]:
            if key in existing:
                existing.pop(key)
                
        existing.update(new_settings)
        
        # ── ATOMIC WRITE: write to temp file first, then rename ──
        # This prevents a corrupt settings.json if the server crashes mid-write
        os.makedirs("config", exist_ok=True)
        fd, tmp_path = tempfile.mkstemp(dir="config", prefix="settings_tmp_", suffix=".json")
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as f:
                json.dump(existing, f, indent=4)
            os.replace(tmp_path, settings_path)  # Atomic rename
        except Exception:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
            raise
            
        return {"status": "success", "message": "Settings saved successfully (Credentials Encrypted)!"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error('Failed to save settings: %s', e)
        raise HTTPException(status_code=500, detail='Failed to save settings.')
def run_login_script():
    import subprocess
    import sys
    import os
    
    with open("broker_login.log", "w") as f:
        f.write(f"Starting login script at {datetime.now()}\n")
        f.flush()
        try:
            subprocess.run([sys.executable, "scripts/auth/auto_login_fyers.py"], 
                           stdout=f, stderr=f, cwd=os.getcwd())
        except Exception as e:
            f.write(f"Error running script: {str(e)}\n")

@app.get("/api/broker-auth-url")
async def get_broker_auth_url():
    try:
        from brokers.credentials import load_credentials
        creds = load_credentials("fyers")
        client_id = creds.get("client_id")
        secret_key = creds.get("secret_key")
        redirect_uri = "http://127.0.0.1:8080" # Default
        
        if not client_id or not secret_key:
            raise HTTPException(status_code=400, detail="Missing Fyers credentials in backend")
            
        from fyers_apiv3 import fyersModel
        session = fyersModel.SessionModel(
            client_id=client_id,
            secret_key=secret_key,
            redirect_uri=redirect_uri,
            response_type="code",
            grant_type="authorization_code"
        )
        auth_url = session.generate_authcode()
        return {"url": auth_url}
    except Exception as e:
        logger.error('Failed to generate broker auth URL: %s', e)
        raise HTTPException(status_code=500, detail='Failed to generate broker auth URL.')

@app.post("/api/broker-login")
async def broker_login(background_tasks: BackgroundTasks):
    background_tasks.add_task(run_login_script)
    return {
        "status": "success",
        "message": "Login script started! Please check the browser window on your screen to solve the captcha."
    }

@app.post("/api/bot/test_login")
async def test_login():
    import subprocess
    import sys
    import os
    
    try:
        process = subprocess.run(
            [sys.executable, "scripts/auth/auto_login_fyers.py"],
            capture_output=True,
            text=True,
            check=False,
            cwd=os.getcwd()
        )
        
        if process.returncode == 0:
            audit.auth(AuditEvent.AUTH_SUCCESS, "fyers", success=True)
            return {
                "status": "success",
                "message": "Login successful! Credentials are correct."
            }
        else:
            audit.auth(AuditEvent.AUTH_FAILURE, "fyers", success=False, reason="invalid_credentials")
            return {
                "status": "error",
                "message": "Incorrect credentials or unable to login. Please check your details."
            }
    except Exception as e:
        logger.error('Login test failed: %s', e)
        raise HTTPException(status_code=500, detail='Login test failed.')

@app.post("/api/bot/start")
async def start_bot():
    import subprocess
    import sys
    import os
    
    try:
        # Run automated login first
        login_process = subprocess.run(
            [sys.executable, "scripts/auth/auto_login_fyers.py"],
            capture_output=True,
            text=True,
            check=False,
            cwd=os.getcwd()
        )
        
        if login_process.returncode != 0:
            return {
                "status": "error",
                "message": f"Login failed: {login_process.stderr or login_process.stdout}"
            }
            
        # Start bot as background process
        process = subprocess.Popen(
            [sys.executable, "-m", "trading_bot.main"],
            cwd=os.getcwd()
        )
        
        return {
            "status": "success",
            "message": "Bot started successfully!",
            "pid": process.pid
        }
    except Exception as e:
        logger.error('Failed to start bot: %s', e)
        raise HTTPException(status_code=500, detail='Failed to start bot.')

@app.get("/api/ai/status")
async def get_ai_status():
    try:
        from shared.ai.model import _MODEL_PATH
        import os
        import pickle
        
        if os.path.exists(_MODEL_PATH):
            mtime = os.path.getmtime(_MODEL_PATH)
            last_trained = datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M:%S")
            
            # Load accuracy if available
            accuracy = 0.0
            try:
                with open(_MODEL_PATH, "rb") as f:
                    data = pickle.load(f)
                    accuracy = data.get("accuracy", 0.0) * 100
            except Exception:
                pass
                
            return {
                "status": "success",
                "is_trained": True,
                "last_trained": last_trained,
                "accuracy": f"{accuracy:.2f}%"
            }
        else:
            return {
                "status": "success",
                "is_trained": False,
                "last_trained": "Never",
                "accuracy": "0.00%"
            }
    except Exception as e:
        logger.error('Failed to fetch AI status: %s', e)
        raise HTTPException(status_code=500, detail='Failed to fetch AI status.')

def _run_retrain_script():
    import subprocess
    import sys
    import os
    try:
        subprocess.run([sys.executable, "scripts/daily_ai_retrain.py"], cwd=os.getcwd())
    except Exception as e:
        logger.error(f"Manual AI retrain failed: {e}")

@app.post("/api/ai/retrain")
async def manual_ai_retrain(background_tasks: BackgroundTasks):
    background_tasks.add_task(_run_retrain_script)
    return {
        "status": "success",
        "message": "AI Retraining started in the background. You will receive an alert once completed."
    }

@app.get("/api/sentiment")
async def get_market_sentiment():
    try:
        from shared.sentiment import get_current_sentiment
        import concurrent.futures
        loop = __import__('asyncio').get_event_loop()
        with concurrent.futures.ThreadPoolExecutor() as pool:
            data = await loop.run_in_executor(pool, get_current_sentiment)
        return data
    except Exception as e:
        logger.error(f"Error fetching sentiment API: {e}")
        return {"score": 0.0, "label": "Neutral", "top_headlines": []}


@app.get("/api/journal")
async def get_trade_journal():
    try:
        import sqlite3
        # Reuse the same anchored path shared/state.py uses (trading-system/
        # state.db, regardless of the process's working directory) instead
        # of os.getcwd() — this endpoint silently returned an empty journal
        # whenever api_bridge.py was launched from anywhere else (a
        # different systemd WorkingDirectory, a Docker WORKDIR, or simply
        # `python trading-system/api_bridge.py` from the repo root).
        from shared.state import _STATE_DB
        db_path = str(_STATE_DB)
        if not os.path.exists(db_path):
            return {"trades": []}

        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        # Check if table exists
        cursor.execute("SELECT count(name) FROM sqlite_master WHERE type='table' AND name='trade_journal'")
        if cursor.fetchone()[0] == 0:
            conn.close()
            return {"trades": []}
            
        cursor.execute("SELECT * FROM trade_journal ORDER BY id DESC")
        rows = cursor.fetchall()
        conn.close()
        
        trades = [dict(row) for row in rows]
        return {"trades": trades}
    except Exception as e:
        logger.error(f"Error fetching journal API: {e}")
        return {"trades": [], "error": str(e)}

@app.get("/api/option-chain")
async def get_option_chain(symbol: str = "NSE:NIFTY50-INDEX"):
    """
    Returns live or simulated option chain data with Greeks.
    This generates a fully dynamic Option Chain mathematically synchronized to the real-time Live Spot Price using the Black-Scholes pricing model.
    """
    try:
        import hashlib
        import math
        import os
        import json
        
        # Black-Scholes Math Engine
        def norm_cdf(x):
            return (1.0 + math.erf(x / math.sqrt(2.0))) / 2.0

        def norm_pdf(x):
            return (1.0 / math.sqrt(2.0 * math.pi)) * math.exp(-0.5 * x * x)

        def black_scholes(S, K, T, r, sigma, option_type="call"):
            if T <= 0.0001:
                return (max(0.0, S - K) if option_type == "call" else max(0.0, K - S),
                        1.0 if option_type == "call" and S > K else (0.0 if option_type == "call" else (-1.0 if S < K else 0.0)),
                        0.0, 0.0, 0.0)

            d1 = (math.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * math.sqrt(T))
            d2 = d1 - sigma * math.sqrt(T)

            if option_type == "call":
                price = S * norm_cdf(d1) - K * math.exp(-r * T) * norm_cdf(d2)
                delta = norm_cdf(d1)
                theta = (- (S * norm_pdf(d1) * sigma) / (2 * math.sqrt(T)) - r * K * math.exp(-r * T) * norm_cdf(d2)) / 365.0
            else:
                price = K * math.exp(-r * T) * norm_cdf(-d2) - S * norm_cdf(-d1)
                delta = norm_cdf(d1) - 1.0
                theta = (- (S * norm_pdf(d1) * sigma) / (2 * math.sqrt(T)) + r * K * math.exp(-r * T) * norm_cdf(-d2)) / 365.0
                
            gamma = norm_pdf(d1) / (S * sigma * math.sqrt(T))
            vega = S * norm_pdf(d1) * math.sqrt(T) / 100.0
            return price, delta, gamma, theta, vega

        def deterministic_random(seed_str, salt, min_val, max_val):
            h = hashlib.md5((str(seed_str) + str(salt)).encode()).hexdigest()
            rand_float = int(h[:8], 16) / 4294967295.0
            return min_val + (rand_float * (max_val - min_val))
            
        # 1. Fetch Real Live Spot Price
        base_price = 24000.0
        try:
            from brokers.token_cache import load_token
            token = load_token("fyers")
            if token:
                from fyers_apiv3 import fyersModel
                client_id = _get_fyers_client_id()
                fyers = fyersModel.FyersModel(client_id=client_id, is_async=False, token=token, log_path="")

                query_symbol = "NSE:NIFTY50-INDEX"
                if "BANKNIFTY" in symbol:
                    query_symbol = "NSE:NIFTYBANK-INDEX"
                elif "FINNIFTY" in symbol:
                    query_symbol = "NSE:FINNIFTY-INDEX"

                # Root-cause fix (found live, 2026-08-05): this is the
                # confirmed trigger of a real ~2-hour full-server freeze --
                # see /api/funds's comment for the full incident writeup.
                quotes = await asyncio.to_thread(fyers.quotes, data={"symbols": query_symbol})
                if quotes and "d" in quotes and len(quotes["d"]) > 0:
                    base_price = float(quotes["d"][0]["v"]["lp"])
        except Exception as e:
            logger.warning(f"Could not fetch real base price for options desk, falling back to defaults: {e}")
            if "BANKNIFTY" in symbol:
                base_price = 52000.0
            elif "RELIANCE" in symbol:
                base_price = 3100.0
                
        # 2. Determine Strike Step and ATM Strike
        step = 50 if "NIFTY50" in symbol or symbol == "NIFTY" else 100 if "BANKNIFTY" in symbol else 50
        atm_strike = round(base_price / step) * step
        num_strikes_each_side = 20
        
        # 3. Parameters for Black-Scholes
        r = 0.07          # 7% Risk-Free Rate in India
        T = 0.02          # Approx 7 days to expiry
        base_iv = 0.15    # 15% Base Implied Volatility
        
        chain = []
        for i in range(-num_strikes_each_side, num_strikes_each_side + 1):
            strike = atm_strike + (i * step)
            
            # Add IV Skew (OTM Puts have higher IV usually)
            iv_skew_call = base_iv + max(0, (strike - base_price) / base_price * 0.5)
            iv_skew_put  = base_iv + max(0, (base_price - strike) / base_price * 0.8)
            
            # Calculate actual mathematical Greeks and Prices
            c_price, c_delta, c_gamma, c_theta, c_vega = black_scholes(base_price, strike, T, r, iv_skew_call, "call")
            p_price, p_delta, p_gamma, p_theta, p_vega = black_scholes(base_price, strike, T, r, iv_skew_put, "put")
            
            # Add slight noise to price to simulate bid/ask spread or live trading variance
            c_price = max(0.05, c_price + deterministic_random(strike, 1, -1.0, 1.0))
            p_price = max(0.05, p_price + deterministic_random(strike, 2, -1.0, 1.0))
            
            chain.append({
                "strike": strike,
                "call": {
                    "ltp": round(c_price, 2),
                    "volume": int(deterministic_random(strike, 3, 10000, 500000)),
                    "oi": int(deterministic_random(strike, 4, 50000, 2000000)),
                    "oichg": int(deterministic_random(strike, 14, -50000, 100000)),
                    "delta": round(c_delta, 2),
                    "gamma": round(c_gamma, 4),
                    "theta": round(c_theta, 2),
                    "vega": round(c_vega, 2)
                },
                "put": {
                    "ltp": round(p_price, 2),
                    "volume": int(deterministic_random(strike, 5, 10000, 500000)),
                    "oi": int(deterministic_random(strike, 6, 50000, 2000000)),
                    "oichg": int(deterministic_random(strike, 16, -50000, 100000)),
                    "delta": round(p_delta, 2),
                    "gamma": round(p_gamma, 4),
                    "theta": round(p_theta, 2),
                    "vega": round(p_vega, 2)
                }
            })
            
        return {
            "symbol": symbol,
            "underlying_price": base_price,
            "atm": atm_strike,
            "maxPain": atm_strike,
            "pcr": round(deterministic_random(base_price, 99, 0.6, 1.4), 2),
            "expiry": "2026-07-25",
            "chain": chain
        }
    except Exception as e:
        logger.error(f"Error fetching option chain: {e}")
        return {"error": str(e)}

# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# Authentication System (Zerodha / Fyers / Upstox Style User ID Auth)
# ---------------------------------------------------------------------------
import hashlib
import secrets
import re
import tempfile
from pydantic import BaseModel
from pathlib import Path

_USERS_FILE = Path(__file__).resolve().parent / "config" / "users.json"
_AUTH_FILE  = Path(__file__).resolve().parent / "config" / "dashboard_auth.json"
_MAX_ATTEMPTS = 5
_LOCKOUT_SECS = 300  # 5 minutes
_ITERATIONS = 100_000

auth_state = {
    "failed_attempts": 0,
    "lockout_until": 0.0
}

def _load_users() -> dict:
    if _USERS_FILE.exists():
        try:
            with open(_USERS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error("Failed to load users: %s", e)
    return {}

def _save_users(users: dict) -> None:
    try:
        _USERS_FILE.parent.mkdir(parents=True, exist_ok=True)
        temp_fd, temp_path = tempfile.mkstemp(dir=_USERS_FILE.parent, prefix="users_tmp_", suffix=".json")
        try:
            with os.fdopen(temp_fd, 'w', encoding='utf-8') as f:
                json.dump(users, f, indent=2)
            os.replace(temp_path, _USERS_FILE)
        except Exception as e:
            if os.path.exists(temp_path):
                os.unlink(temp_path)
            raise e
    except Exception as e:
        logger.error("Failed to save users: %s", e)

def _hash_password(password: str, salt: str = None) -> str:
    if salt is None:
        salt = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        _ITERATIONS
    )
    return f"{salt}${dk.hex()}"

def _verify_password(stored_password: str, provided_password: str) -> bool:
    try:
        salt, _ = stored_password.split("$", 1)
    except ValueError:
        return False
    return stored_password == _hash_password(provided_password, salt)

def _generate_unique_user_id(users: dict) -> str:
    """Generate a unique, collision-free Trading User ID starting with MNA prefix (e.g. MNA100001, MNA845721)."""
    import random
    import string
    existing_ids = set(users.keys())
    for _ in range(1000):
        # Generate 6 random digits or uppercase alphanumeric chars
        suffix = ''.join(random.choices(string.digits + "ABCDEFGHJKLMNPQRSTUVWXYZ", k=6))
        candidate_id = f"MNA{suffix}"
        if candidate_id not in existing_ids:
            return candidate_id
    # Fallback timestamp-based ID
    return f"MNA{int(time.time()) % 1000000:06d}"

def _send_welcome_email_async(email: str, name: str, user_id: str):
    """Sends background welcome email with the generated Trading User ID."""
    import smtplib
    from email.mime.text import MIMEText
    from email.mime.multipart import MIMEMultipart
    
    smtp_host = os.getenv("SMTP_HOST", "")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_user = os.getenv("SMTP_USER", "")
    smtp_pass = os.getenv("SMTP_PASS", "")

    if not smtp_host or not smtp_user or not smtp_pass:
        logger.info("[EMAIL NOTIFICATION] (SMTP not configured) Welcome email logged for %s (%s) -> Trading User ID: %s", name, email, user_id)
        return

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = f"Welcome to MANA AI Trading Terminal — Your User ID: {user_id}"
        msg["From"] = f"MANA AI Trading <{smtp_user}>"
        msg["To"] = email

        html_content = f"""
        <div style="font-family: Arial, sans-serif; background-color: #030303; color: #ffffff; padding: 30px; border-radius: 12px;">
            <h2 style="color: #10b981; margin-bottom: 20px;">Welcome to MANA AI Trading Terminal</h2>
            <p>Dear <strong>{name}</strong>,</p>
            <p>Your institutional trading account has been created successfully.</p>
            <div style="background-color: #111827; border: 1px solid #374151; padding: 20px; border-radius: 8px; margin: 20px 0;">
                <p style="font-size: 14px; color: #9ca3af; margin: 0;">YOUR TRADING USER ID:</p>
                <p style="font-size: 28px; font-weight: bold; color: #38bdf8; letter-spacing: 2px; margin: 5px 0 0 0;">{user_id}</p>
            </div>
            <p>You can now sign in to your terminal using your <strong>Trading User ID ({user_id})</strong> or your registered email address (<strong>{email}</strong>).</p>
            <p style="color: #6b7280; font-size: 12px; margin-top: 30px;">For security reasons, your password is never included in email notifications.</p>
        </div>
        """
        msg.attach(MIMEText(html_content, "html"))

        with smtplib.SMTP(smtp_host, smtp_port, timeout=10) as server:
            server.starttls()
            server.login(smtp_user, smtp_pass)
            server.send_message(msg)
        logger.info("Welcome email successfully sent to %s (%s)", email, user_id)
    except Exception as e:
        logger.error("Failed to send welcome email to %s: %s", email, e)

def _validate_password_complexity(password: str) -> None:
    """Enforces 8-128 characters with uppercase, lowercase, number, and
    special character.

    Root-cause fix: was previously capped at 15 characters while also
    requiring all 4 character classes — an unnecessarily small max that
    needlessly shrinks the keyspace for a password meeting the complexity
    rules (longer passwords are generally more secure, not less; NIST
    800-63B explicitly recommends allowing long passwords rather than
    artificially capping them). Hashing uses hashlib.pbkdf2_hmac (see
    _hash_password), which has no length limitation like bcrypt's 72-byte
    cap, so raising the max has no hashing-side side effect. 128 is a
    generous, standard-practice ceiling that still bounds worst-case
    input size.
    """
    if not password or len(password) < 8 or len(password) > 128:
        raise HTTPException(status_code=400, detail="Password must be between 8 and 128 characters long.")
    if not re.search(r"[A-Z]", password):
        raise HTTPException(status_code=400, detail="Password must contain at least one uppercase letter.")
    if not re.search(r"[a-z]", password):
        raise HTTPException(status_code=400, detail="Password must contain at least one lowercase letter.")
    if not re.search(r"[0-9]", password):
        raise HTTPException(status_code=400, detail="Password must contain at least one number.")
    if not re.search(r"[^A-Za-z0-9]", password):
        raise HTTPException(status_code=400, detail="Password must contain at least one special character.")

class RegisterRequest(BaseModel):
    name: str
    email: str
    password: str
    client_id: str = ""

class LoginRequest(BaseModel):
    user_id_or_email: str
    password: str

class ResetRequest(BaseModel):
    user_id_or_email: str
    client_id: str
    new_password: str

@app.get("/api/auth/status")
async def auth_status():
    users = _load_users()
    has_users = len(users) > 0 or _AUTH_FILE.exists()
    locked_out = time.time() < auth_state["lockout_until"]
    return {
        "hasUsers": has_users,
        "hasPassword": has_users,
        "lockedOut": locked_out,
        "lockoutSeconds": max(0, int(auth_state["lockout_until"] - time.time())),
        "userCount": len(users)
    }

@app.get("/api/auth/me")
async def auth_me(request: Request):
    """Returns the caller's identity if their session token is valid.

    This route is intentionally NOT in the public allowlist, so the auth
    middleware already rejects invalid/missing tokens with 401 before this
    body ever runs — the frontend uses that fact as its source of truth for
    "is the user actually logged in", instead of trusting client storage.
    """
    user = getattr(request.state, "user", None) or {}
    return {
        "status": "success",
        "user": {
            "user_id": user.get("user_id", ""),
            "name": user.get("name", ""),
            "email": user.get("email", ""),
        },
    }

@app.post("/api/auth/register")
async def auth_register(req: RegisterRequest, background_tasks: BackgroundTasks):
    name = req.name.strip()
    email = req.email.strip().lower()
    password = req.password

    if not name or len(name) < 2:
        raise HTTPException(status_code=400, detail="Full Name is required (minimum 2 characters)")
        
    if not email or "@" not in email or "." not in email:
        raise HTTPException(status_code=400, detail="Valid Email address is required")
        
    _validate_password_complexity(password)

    users = _load_users()

    # Check for existing email registration
    for udata in users.values():
        if udata.get("email", "").lower() == email:
            raise HTTPException(status_code=400, detail="Sorry already used this email address")

    # Auto-generate unique Trading User ID (MNAXXXXXX)
    user_id = _generate_unique_user_id(users)
    password_hash = _hash_password(password)

    user_record = {
        "user_id": user_id,
        "name": name,
        "email": email,
        "password_hash": password_hash,
        "client_id": req.client_id.strip() if req.client_id else "",
        "created_at": time.time()
    }

    users[user_id] = user_record
    _save_users(users)

    # Legacy auth file sync
    try:
        with open(_AUTH_FILE, "w", encoding="utf-8") as f:
            json.dump({"password_hash": password_hash, "created_at": time.time()}, f, indent=2)
    except Exception:
        pass

    # Send welcome email asynchronously
    background_tasks.add_task(_send_welcome_email_async, email, name, user_id)

    logger.info("Account created successfully: %s (%s)", user_id, email)
    from shared.security.sessions import create_session
    session_token = create_session(user_id, name=name, email=email)
    return {
        "status": "success",
        "message": "Account created successfully.",
        "user_id": user_id,
        "user": {
            "user_id": user_id,
            "name": name,
            "email": email
        },
        "token": session_token
    }

@app.post("/api/auth/login")
async def auth_login(req: LoginRequest):
    identifier = req.user_id_or_email.strip()
    password = req.password

    if not identifier:
        raise HTTPException(status_code=400, detail="Enter Email or User ID")
    if not password:
        raise HTTPException(status_code=400, detail="Password is required")

    if time.time() < auth_state["lockout_until"]:
        remaining = int(auth_state["lockout_until"] - time.time())
        raise HTTPException(status_code=429, detail=f"Maximum login attempts exceeded. Locked out for {remaining} seconds.")

    users = _load_users()

    target_user = None
    if "@" in identifier:
        search_email = identifier.lower()
        for udata in users.values():
            if udata.get("email", "").lower() == search_email:
                target_user = udata
                break
    else:
        search_id = identifier.upper()
        target_user = users.get(search_id)

    # Fallback to single-admin legacy auth file if users.json is empty
    if not target_user and _AUTH_FILE.exists():
        try:
            with open(_AUTH_FILE, "r", encoding="utf-8") as f:
                auth_data = json.load(f)
                if _verify_password(auth_data.get("password_hash", ""), password):
                    auth_state["failed_attempts"] = 0
                    from shared.security.sessions import create_session
                    session_token = create_session("ADMIN", name="Administrator", email="admin@mana.ai")
                    audit.log(AuditEvent.DASHBOARD_LOGIN, {"user_id": "ADMIN", "identifier": identifier})
                    return {
                        "status": "success",
                        "user": {"user_id": "ADMIN", "name": "Administrator", "email": "admin@mana.ai"},
                        "token": session_token
                    }
        except Exception:
            pass

    if not target_user:
        auth_state["failed_attempts"] += 1
        audit.log(AuditEvent.DASHBOARD_FAIL, {"identifier": identifier, "reason": "unknown_user"}, severity="WARNING")
        if auth_state["failed_attempts"] >= _MAX_ATTEMPTS:
            auth_state["lockout_until"] = time.time() + _LOCKOUT_SECS
            auth_state["failed_attempts"] = 0
            raise HTTPException(status_code=429, detail="Maximum attempts reached. Locked out for 5 minutes.")
        raise HTTPException(status_code=401, detail="Invalid Email/User ID or Password.")

    if _verify_password(target_user.get("password_hash", ""), password):
        auth_state["failed_attempts"] = 0
        user_id = target_user.get("user_id", "USER")
        name = target_user.get("name", "Trader")
        email = target_user.get("email", "")
        from shared.security.sessions import create_session
        session_token = create_session(user_id, name=name, email=email)
        audit.log(AuditEvent.DASHBOARD_LOGIN, {"user_id": user_id, "identifier": identifier})
        return {
            "status": "success",
            "user": {
                "user_id": user_id,
                "name": name,
                "email": email
            },
            "token": session_token
        }
    else:
        auth_state["failed_attempts"] += 1
        audit.log(AuditEvent.DASHBOARD_FAIL, {"identifier": identifier, "reason": "wrong_password"}, severity="WARNING")
        if auth_state["failed_attempts"] >= _MAX_ATTEMPTS:
            auth_state["lockout_until"] = time.time() + _LOCKOUT_SECS
            auth_state["failed_attempts"] = 0
            raise HTTPException(status_code=429, detail="Maximum attempts reached. Locked out for 5 minutes.")
        raise HTTPException(status_code=401, detail="Invalid Email/User ID or Password.")

@app.post("/api/auth/reset")
async def auth_reset(req: ResetRequest):
    identifier = req.user_id_or_email.strip()
    client_id = req.client_id.strip()
    new_password = req.new_password

    if not identifier:
        raise HTTPException(status_code=400, detail="Enter Email or User ID")
    if not client_id:
        raise HTTPException(status_code=400, detail="Broker Client ID is required for verification")
        
    _validate_password_complexity(new_password)

    import dotenv
    dotenv.load_dotenv()
    fyers_client_id = os.getenv("FYERS_CLIENT_ID", "").strip()

    users = _load_users()
    target_user_id = None
    target_user = None

    if "@" in identifier:
        search_email = identifier.lower()
        for uid, udata in users.items():
            if udata.get("email", "").lower() == search_email:
                target_user_id = uid
                target_user = udata
                break
    else:
        search_id = identifier.upper()
        if search_id in users:
            target_user_id = search_id
            target_user = users[search_id]

    if target_user:
        user_linked_client = target_user.get("client_id", "").strip()
        if user_linked_client:
            # The account has its own linked broker client ID on file — that
            # is the ONLY value that verifies this specific account. The
            # operator's global FYERS_CLIENT_ID must never be usable as a
            # bypass for someone else's account (see the fixed bug note
            # below for what this replaced).
            if user_linked_client != client_id:
                raise HTTPException(status_code=401, detail="Invalid Broker Client ID verification")
        elif not (fyers_client_id and client_id == fyers_client_id):
            # No client ID on file for this account at all — fall back to
            # the single-operator admin ID as the only other recognized
            # identity (matches the admin-bootstrap branch below).
            raise HTTPException(status_code=401, detail="Invalid Broker Client ID verification")


        target_user["password_hash"] = _hash_password(new_password)
        users[target_user_id] = target_user
        _save_users(users)
    elif fyers_client_id and client_id == fyers_client_id:
        password_hash = _hash_password(new_password)
        users["MNA100001"] = {
            "user_id": "MNA100001",
            "name": "Administrator",
            "email": "admin@mana.ai",
            "password_hash": password_hash,
            "client_id": client_id,
            "created_at": time.time()
        }
        _save_users(users)
    else:
        raise HTTPException(status_code=401, detail="User not found or Invalid Broker Client ID")

    auth_state["failed_attempts"] = 0
    auth_state["lockout_until"] = 0.0

    # A password reset should invalidate any existing sessions for this
    # account so a previously-issued token can't keep working past it.
    from shared.security.sessions import revoke_all_sessions_for_user
    revoke_all_sessions_for_user(target_user_id or "MNA100001")

    return {"status": "success", "message": "Password reset successfully. You can now Login."}


class LogoutRequest(BaseModel):
    token: str = ""


@app.post("/api/auth/logout")
async def auth_logout(request: Request, req: LogoutRequest = None):
    """Revoke the caller's session token (or the one in the request body)."""
    from shared.security.sessions import revoke_session
    token = _extract_bearer_token(request) or (req.token if req else "")
    session = getattr(request.state, "user", None)
    audit.log(AuditEvent.DASHBOARD_LOGOUT, {"user_id": session.get("user_id") if session else "unknown"})
    revoke_session(token)
    return {"status": "success", "message": "Logged out."}


@app.get("/api/btst")
async def get_btst_prediction(symbol: str = "NIFTY"):
    try:
        # IST-anchored (not server-local) so "today" never silently excludes
        # today's IST candles for a server whose OS clock isn't set to IST.
        end_date = datetime.now(_IST)
        start_date = end_date - timedelta(days=5)
        
        symbol_formatted = format_broker_symbol(symbol)
        broker = BrokerFactory.get_active_broker()
        broker.authenticate()
        
        # Use 15 Min timeframe for EOD analysis
        data = broker.get_historical_data(symbol_formatted, start_date.strftime('%Y-%m-%d'), end_date.strftime('%Y-%m-%d'), "15 Min")
        
        if not data or len(data) < 10:
            return {"status": "scanning", "action": "AVOID", "gapUpProb": 50, "gapDownProb": 50, "reason": "Insufficient Data"}
            
        df = pd.DataFrame(data)
        df.columns = [c.lower() for c in df.columns]
        df_close = pd.to_numeric(df['close'], errors='coerce').ffill()
        
        # Calculate Intraday Daily Momentum (last 25 candles = ~1 full day in 15min)
        recent_close = df_close.iloc[-1]
        day_open = df_close.iloc[-25] if len(df_close) >= 25 else df_close.iloc[0]
        
        # Calculate Late Day Momentum (last 4 candles = last 1 hour)
        late_day_open = df_close.iloc[-4] if len(df_close) >= 4 else df_close.iloc[0]
        
        daily_momentum = (recent_close - day_open) / day_open * 100
        late_momentum = (recent_close - late_day_open) / late_day_open * 100
        
        # Calculate RSI (14) roughly for EOD
        delta = df_close.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        current_rsi = rsi.iloc[-1]
        if pd.isna(current_rsi): current_rsi = 50
        
        # Advanced BTST Logic combining Daily Trend + Late Day Surge
        gap_up_prob = 50
        if daily_momentum > 0.4 and late_momentum > -0.15 and current_rsi > 55:
            gap_up_prob = min(90, 55 + int(daily_momentum * 15) + int(late_momentum * 20))
        elif daily_momentum < -0.4 and late_momentum < 0.15 and current_rsi < 45:
            gap_up_prob = max(10, 45 + int(daily_momentum * 15) + int(late_momentum * 20))
            
        gap_down_prob = 100 - gap_up_prob
        
        if gap_up_prob >= 65:
            action = "CARRY CALL"
            reason = f"Strong Daily Rally (+{daily_momentum:.2f}%) holding well into EOD. High probability of Gap Up."
        elif gap_down_prob >= 65:
            action = "CARRY PUT"
            reason = f"Strong Daily Selloff ({daily_momentum:.2f}%) holding weak into EOD. High probability of Gap Down."
        else:
            action = "AVOID"
            reason = "Market closing in equilibrium. Overnight risk is too high without a clear directional bias."
            
        return {
            "status": "active",
            "action": action,
            "gapUpProb": gap_up_prob,
            "gapDownProb": gap_down_prob,
            "reason": reason,
            "metrics": {
                "momentum": round(daily_momentum, 2),
                "rsi": round(current_rsi, 2)
            }
        }
    except Exception as e:
        logger.error(f"Error in /api/btst: {e}")
        return {"status": "error", "action": "AVOID", "gapUpProb": 50, "gapDownProb": 50, "reason": str(e)}

if __name__ == "__main__":
    from shared.singleton_lock import acquire_singleton_lock
    acquire_singleton_lock("api_bridge", script_hint="api_bridge.py")

    _setup_log_rotation()
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
