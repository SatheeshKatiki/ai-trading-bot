from fastapi import FastAPI, Query, HTTPException, BackgroundTasks, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime, timedelta, timezone
import logging
import logging.handlers
import pandas as pd
import numpy as np
import json
import os
import time

# Module-level logger — NEVER use print() in async FastAPI code
logger = logging.getLogger("api_bridge")

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
        if not root_logger.level:
            root_logger.setLevel(logging.INFO)

_setup_log_rotation()

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

# Register strategies for the API
registry.register("ema_rsi",      ema_rsi_signals)
registry.register("enhanced_ai",  enhanced_signals)
registry.register("premium",      premium_signals)
registry.register("advanced_ai", advanced_ai_signals)
registry.register("institutional_momentum", momentum_signals)
registry.register("ema_crossover", ema_crossover_signals)
registry.register("meta_agent_swarm", meta_agent_signals)
registry.register("buy_the_dip", buy_dip_signals)

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

@app.on_event("startup")
async def startup_event():
    logger.info("Initializing API Bridge and restoring application state...")
    
    # 0. Fetch latest lot sizes dynamically in background
    try:
        from shared.lot_size_updater import update_lot_sizes_in_settings
        asyncio.create_task(update_lot_sizes_in_settings())
    except Exception as e:
        logger.error(f"Failed to start lot size updater: {e}")

    asyncio.create_task(daily_retrain_scheduler())

# Global state for live market data (Institutional Streaming)
market_data_lock = threading.Lock()
current_market_data = {
    "NSE:NIFTY50-INDEX": {"lp": 23820.35, "chp": -1.49},
    "BSE:SENSEX-INDEX": {"lp": 76015.28, "chp": -1.70},
    "NSE:NIFTYBANK-INDEX": {"lp": 51000.00, "chp": 0.0}
}
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
    Supports all NSE/BSE stocks, indices, and correctly formats them.
    """
    symbol = symbol.strip().upper()
    
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
        
    # 3. Format as Equity (EQ) by default for unrecognized symbols
    # This covers all 2000+ NSE/BSE stocks perfectly!
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
        token_path = ".fyers_tokens.json"
        if not os.path.exists(token_path):
            logger.warning("Token not found for WebSocket. Falling back to yfinance polling for Paper Mode.")
            import yfinance as yf
            import time
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
            
        with open(token_path, "r") as f:
            token_data = json.load(f)
            token = token_data["access_token"]
            
        client_id = _get_fyers_client_id()
        
        def on_message(message):
            global current_market_data
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
            
        def on_open():
            global _subscribed_symbols
            _subscribed_symbols = {"NSE:NIFTY50-INDEX", "BSE:SENSEX-INDEX", "NSE:NIFTYBANK-INDEX", "NSE:RELIANCE-EQ", "NSE:TCS-EQ"}
            logger.info("Fyers WS Connected!")
            if fyers_socket_instance:
                fyers_socket_instance.subscribe(symbols=list(_subscribed_symbols), data_type="symbolData")
            
        def on_close():
            logger.info("Fyers WS Closed")

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
        res = subprocess.run([sys.executable, "scripts/auth/auto_login_fyers.py"], check=True, capture_output=True, text=True)
        logger.info(f"Auto-login completed successfully: {res.stdout.splitlines()[-1] if res.stdout else ''}")
    except Exception as e:
        logger.error(f"Auto-login failed: {e}")
        if hasattr(e, 'stderr') and e.stderr:
            logger.error(f"Auto-login stderr: {e.stderr}")
            
    # Start the Fyers socket in background thread
    threading.Thread(target=start_fyers_socket, daemon=True).start()
    
    # Start the WebSocket Broadcaster task
    asyncio.create_task(websocket_broadcaster())
    
    yield

app.router.lifespan_context = lifespan


# Trade state cache for WebSocket (prevents SQLite reads at 20fps)
from shared.state import load_state as _load_state_fn
_ws_trade_cache: dict = {"trades": [], "pnl": 0.0, "equity": 100000.0}
_ws_trade_last_read: float = 0.0
_WS_TRADE_CACHE_TTL: float = 0.05  # Refresh trades from DB at 20 FPS for ultra-low latency

signals_cache = {"data": None, "last_updated": 0}
active_connections: set[WebSocket] = set()

async def websocket_broadcaster():
    """Single global background task that computes the market snapshot and broadcasts to all connected clients."""
    global _ws_trade_cache, _ws_trade_last_read
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
            websocket_data["pnl"] = _ws_trade_cache.get("pnl", 0.0)
            websocket_data["equity"] = _ws_trade_cache.get("equity", 100000.0)
            websocket_data["raw_ticks"] = snapshot
            websocket_data["signalsData"] = signals_cache["data"]

            # --- Dynamic Subscription Sync ---
            global _subscribed_symbols
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
    return {"status": "ok"}

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
            timestamp=datetime.now(timezone.utc).isoformat(),
            qty=req.quantity
        )
            
        return {"status": "success", "order_id": response.order_id, "message": response.message}
    except Exception as e:
        logger.error(f"Order Execution Failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/panic-exit")
async def panic_exit(request: Request):
    """Nuclear Option: Immediately cancels all orders and squares off all positions."""
    if request.client and request.client.host not in ["127.0.0.1", "localhost", "::1"]:
        logger.warning(f"Unauthorized Panic Exit attempt from {request.client.host}")
        raise HTTPException(status_code=403, detail="Forbidden: Localhost access only")
        
    try:
        broker = BrokerFactory.get_active_broker()
        if not broker.authenticate():
            raise HTTPException(status_code=401, detail="Broker not authenticated")
            
        logger.warning("!!! PANIC EXIT TRIGGERED !!!")
        
        # 1. Cancel all pending orders
        pending_orders = broker.get_orders()
        cancelled_count = 0
        for order in pending_orders:
            if order.status in ["OPEN", "PENDING", "PARTIALLY_FILLED"]:
                broker.cancel_order(order.id)
                cancelled_count += 1
                
        # 2. Square off all active positions
        positions = broker.get_positions()
        closed_count = 0
        for pos in positions:
            if pos.quantity != 0:
                # Opposite side market order
                side = "SELL" if pos.quantity > 0 else "BUY"
                qty = abs(pos.quantity)
                broker.place_order(OrderRequest(
                    symbol=pos.symbol,
                    side=OrderSide.SELL if side == "SELL" else OrderSide.BUY,
                    quantity=qty,
                    order_type=OrderType.MARKET,
                ))
                closed_count += 1
        
        # 3. Log the nuclear event
        log_file = "fyersApi.log"
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(log_file, "a") as f:
            f.write(f"\n[{timestamp}] !!! PANIC EXIT EXECUTED !!! Cancelled: {cancelled_count}, Closed: {closed_count}\n")
            
        return {
            "status": "success",
            "message": "Panic Exit Executed Successfully",
            "cancelled": cancelled_count,
            "closed": closed_count
        }
    except Exception as e:
        logger.error("Panic Exit Failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))

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
        token_path = ".fyers_tokens.json"
        if not os.path.exists(token_path):
            return {"s": "error", "message": "Token not found"}
            
        with open(token_path, "r") as f:
            token_data = json.load(f)
            token = token_data["access_token"]
            
        from fyers_apiv3 import fyersModel
        client_id = _get_fyers_client_id()
        
        fyers = fyersModel.FyersModel(client_id=client_id, is_async=False, token=token, log_path="")
        funds = fyers.funds()
        return funds
    except Exception as e:
        return {"s": "error", "message": str(e)}

@app.get("/api/quote")
async def get_quote(
    symbol: str = Query(..., description="The symbol (e.g., NSE:NIFTY50-INDEX)")
):
    """Fetches real-time quote (LTP) from Fyers."""
    try:
        token_path = ".fyers_tokens.json"
        if not os.path.exists(token_path):
            return {"s": "error", "message": "Token not found"}
            
        with open(token_path, "r") as f:
            token_data = json.load(f)
            token = token_data["access_token"]
            
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
        quotes = fyers.quotes(data=data)
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

@app.get("/api/history")
async def get_history(
    symbol: str = Query(..., description="The stock ticker (e.g., RELIANCE, TCS)"),
    start_date: str = Query(..., description="Start date (YYYY-MM-DD)"),
    end_date: str = Query(..., description="End date (YYYY-MM-DD)"),
    timeframe: str = Query("5 Min", description="Timeframe")
):
    """Fetches real historical data dynamically from the ACTIVE BROKER."""
    try:
        with open("history_debug.txt", "a") as f:
            f.write(f"Requested {symbol} from {start_date} to {end_date} for {timeframe}\n")
        
        broker = BrokerFactory.get_active_broker()
        broker.authenticate()
        logger.info("Fetching history via broker: %s for %s", broker.DISPLAY_NAME, symbol)
        
        # Map symbol using institutional formatter
        original_symbol = symbol
        symbol = format_broker_symbol(symbol)
            
        data = broker.get_historical_data(symbol, start_date, end_date, timeframe)
        
        if not data:
            raise HTTPException(status_code=404, detail=f"No data returned by broker for {symbol}")
            
        return {
            "symbol": symbol,
            "timeframe": timeframe,
            "data_points": len(data),
            "data": data
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/inspect")
def inspect_broker():
    broker = BrokerFactory.get_active_broker()
    return {
        "client_id": broker.credentials.get("client_id"),
        "cached_token_head": broker._load_cached_token()[:20] if broker._load_cached_token() else None,
        "token_in_credentials": broker.credentials.get("access_token"),
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
    max_daily_trades: int = Query(6, description="Maximum number of trades allowed per day")
):
    """Triggers a true Python backtest using the actual strategy files and broker data."""
    try:
        broker = BrokerFactory.get_active_broker()
        broker.authenticate()
        
        # Map symbol using institutional formatter
        original_symbol = symbol
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

        # Save results for analytics!
        backtest_output = {
            "symbol": symbol,
            "timeframe": timeframe,
            "strategy": strategy,
            "stats": results["stats"],
            "equityCurve": results["equityCurve"],
            "trades": results["trades"]
        }
        with open("backtest_results.json", "w") as f:
            json.dump(backtest_output, f, indent=4)
            
        # Read settings for target and stoploss
        import gc
        del df
        gc.collect()
        
        settings = {}
        if os.path.exists("config/settings.json"):
            with open("config/settings.json", "r") as f:
                settings = json.load(f)
                
        # Calculate extra stats
        trades = results["trades"]
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
            "rejectionLogs": results.get("rejectionLogs", [])
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/equity-data")
async def get_equity_data(symbol: str = "NIFTY"):
    """Returns real price action data mapped as equity data for the dashboard."""
    try:
        broker = BrokerFactory.get_active_broker()
        broker.authenticate()
        end_date = datetime.now()
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
        end_date = datetime.now()
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
        raise HTTPException(status_code=500, detail=str(e))

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
        raise HTTPException(status_code=500, detail=str(e))

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
        raise HTTPException(status_code=500, detail=str(e))

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
        raise HTTPException(status_code=500, detail=str(e))

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
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/settings")
async def save_settings(new_settings: dict):
    try:
        import os
        import json
        
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
            
        # Save remaining settings to config/settings.json
        existing = {}
        if os.path.exists("config/settings.json"):
            with open("config/settings.json", "r") as f:
                existing = json.load(f)
                
        # Remove any existing plain text credentials from settings
        for key in ["fyers_user_id", "fyers_pin", "fyers_totp_key"]:
            if key in existing:
                existing.pop(key)
                
        existing.update(new_settings)
        
        with open("config/settings.json", "w") as f:
            json.dump(existing, f, indent=4)
            
        return {"status": "success", "message": "Settings saved successfully (Credentials Encrypted)!"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
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
        raise HTTPException(status_code=500, detail=str(e))

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
            return {
                "status": "success",
                "message": "Login successful! Credentials are correct."
            }
        else:
            return {
                "status": "error",
                "message": "Incorrect credentials or unable to login. Please check your details."
            }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

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
        raise HTTPException(status_code=500, detail=str(e))

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
        raise HTTPException(status_code=500, detail=str(e))

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
        import os
        db_path = os.path.join(os.getcwd(), 'state.db')
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
        import hashlib
        
        def deterministic_random(seed_str, salt, min_val, max_val):
            h = hashlib.md5((str(seed_str) + str(salt)).encode()).hexdigest()
            rand_float = int(h[:8], 16) / 4294967295.0
            return min_val + (rand_float * (max_val - min_val))
            
        # 1. Fetch Real Live Spot Price
        base_price = 24000.0
        try:
            token_path = ".fyers_tokens.json"
            if os.path.exists(token_path):
                with open(token_path, "r") as f:
                    token_data = json.load(f)
                    token = token_data.get("access_token")
                if token:
                    from fyers_apiv3 import fyersModel
                    client_id = _get_fyers_client_id()
                    fyers = fyersModel.FyersModel(client_id=client_id, is_async=False, token=token, log_path="")
                    
                    query_symbol = "NSE:NIFTY50-INDEX"
                    if "BANKNIFTY" in symbol:
                        query_symbol = "NSE:NIFTYBANK-INDEX"
                    elif "FINNIFTY" in symbol:
                        query_symbol = "NSE:FINNIFTY-INDEX"
                        
                    quotes = fyers.quotes(data={"symbols": query_symbol})
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
# Authentication System (Next.js Dashboard)
# ---------------------------------------------------------------------------
import hashlib
import secrets
import time
from pydantic import BaseModel
from pathlib import Path

_AUTH_FILE = Path("dashboard_auth.json")
_MAX_ATTEMPTS = 5
_LOCKOUT_SECS = 120
_ITERATIONS = 260_000

auth_state = {
    "failed_attempts": 0,
    "lockout_until": 0.0
}

class LoginRequest(BaseModel):
    password: str

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

@app.get("/api/auth/status")
async def auth_status():
    has_password = _AUTH_FILE.exists()
    locked_out = time.time() < auth_state["lockout_until"]
    return {
        "hasPassword": has_password,
        "lockedOut": locked_out,
        "lockoutSeconds": max(0, int(auth_state["lockout_until"] - time.time()))
    }

class ResetRequest(BaseModel):
    client_id: str
    new_password: str

@app.post("/api/auth/reset")
async def auth_reset(req: ResetRequest):
    import dotenv
    dotenv.load_dotenv()
    valid_client_id = os.getenv("FYERS_CLIENT_ID")
    
    if not valid_client_id or req.client_id.strip() != valid_client_id.strip():
        raise HTTPException(status_code=401, detail="Invalid Recovery Key (Client ID)")
        
    if not req.new_password or len(req.new_password) < 4:
        raise HTTPException(status_code=400, detail="Password must be at least 4 characters")
        
    auth_data = {
        "password_hash": _hash_password(req.new_password),
        "created_at": time.time()
    }
    with open(_AUTH_FILE, "w", encoding="utf-8") as f:
        json.dump(auth_data, f, indent=2)
        
    # Reset lockouts
    auth_state["failed_attempts"] = 0
    auth_state["lockout_until"] = 0
    
    return {"status": "success", "message": "Password reset successfully"}

@app.post("/api/auth/setup")
async def auth_setup(req: LoginRequest):
    if _AUTH_FILE.exists():
        raise HTTPException(status_code=400, detail="Password already set")
    if not req.password or len(req.password) < 4:
        raise HTTPException(status_code=400, detail="Password must be at least 4 characters")
    
    auth_data = {
        "password_hash": _hash_password(req.password),
        "created_at": time.time()
    }
    with open(_AUTH_FILE, "w", encoding="utf-8") as f:
        json.dump(auth_data, f, indent=2)
    return {"status": "success", "message": "Password configured successfully"}

@app.post("/api/auth/login")
async def auth_login(req: LoginRequest):
    if not _AUTH_FILE.exists():
        raise HTTPException(status_code=400, detail="No password configured yet")
    
    # Lock disabled for now per user request
    # if time.time() < auth_state["lockout_until"]:
    #     raise HTTPException(status_code=429, detail="Too many attempts. Try again later.")
        
    try:
        with open(_AUTH_FILE, "r", encoding="utf-8") as f:
            auth_data = json.load(f)
    except Exception as e:
        raise HTTPException(status_code=500, detail="Error reading auth file")
        
    if _verify_password(auth_data.get("password_hash", ""), req.password):
        auth_state["failed_attempts"] = 0 # reset
        auth_data["last_activity_time"] = time.time()
        try:
            with open(_AUTH_FILE, "w", encoding="utf-8") as f:
                json.dump(auth_data, f, indent=2)
        except:
            pass
        return {"status": "success", "token": "mana_ai_auth_v1_valid"}
    else:
        # Lock disabled for now per user request
        # auth_state["failed_attempts"] += 1
        # if auth_state["failed_attempts"] >= _MAX_ATTEMPTS:
        #     auth_state["lockout_until"] = time.time() + _LOCKOUT_SECS
        #     auth_state["failed_attempts"] = 0
        #     raise HTTPException(status_code=429, detail="Too many attempts. Locked out for 2 minutes.")
        raise HTTPException(status_code=401, detail="Invalid password")
        
@app.get("/api/btst")
async def get_btst_prediction(symbol: str = "NIFTY"):
    try:
        end_date = datetime.now()
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
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
