from fastapi import FastAPI, Query, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime, timedelta
import pandas as pd
import numpy as np
import json
import os
import time

def convert_numpy_types(obj):
    import math
    """Recursively convert numpy types to native Python types for JSON serialization."""
    if isinstance(obj, dict):
        return {k: convert_numpy_types(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [convert_numpy_types(v) for v in obj]
    elif isinstance(obj, (np.integer, np.int64, np.int32)):
        return int(obj)
    elif isinstance(obj, (np.floating, np.float64, np.float32, float)):
        val = float(obj)
        if math.isnan(val) or math.isinf(val):
            return 0.0
        return val
    elif isinstance(obj, np.ndarray):
        return convert_numpy_types(obj.tolist())
    else:
        return obj

# Import the Broker Factory to make the API broker-agnostic!
from brokers import BrokerFactory
# Import the Strategy Registry to support multiple strategies
from trading_bot.strategies.registry import registry
from trading_bot.strategies.ema_rsi_strategy import generate_signals as ema_rsi_signals
from trading_bot.strategies.enhanced_ai_strategy import generate_signals as enhanced_signals
from trading_bot.strategies.premium_selection import generate_signals as premium_signals
from trading_bot.strategies.institutional_ema_strategy import generate_signals as institutional_signals
from trading_bot.strategies.advanced_ai_ml_strategy import generate_signals as advanced_ai_signals

# Register strategies for the API
registry.register("ema_rsi",      ema_rsi_signals)
registry.register("enhanced_ai",  enhanced_signals)
registry.register("premium",      premium_signals)
registry.register("institutional_ema", institutional_signals)
registry.register("advanced_ai", advanced_ai_signals)

app = FastAPI(title="Broker Terminal Data Bridge & Backtester")

# Allow requests from the Next.js frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from fastapi import WebSocket
from fyers_apiv3.FyersWebsocket import data_ws
import asyncio
import threading

# Global state for live market data (Institutional Streaming)
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

def start_fyers_socket():
    try:
        token_path = ".fyers_tokens.json"
        if not os.path.exists(token_path):
            print("Token not found for WebSocket")
            return
            
        with open(token_path, "r") as f:
            token_data = json.load(f)
            token = token_data["access_token"]
            
        client_id = "0KHBQ6IQA4-100"
        
        def on_message(message):
            global current_market_data
            if isinstance(message, dict):
                symbol = message.get('symbol')
                lp = message.get('ltp')
                if symbol and lp:
                    print(f"Fyers Tick: {symbol} @ {lp}") # Debug log to check speed
                    current_market_data[symbol] = {
                        "lp": lp,
                        "chp": message.get('chp', 0.0)
                    }
                    
        def on_error(message):
            print(f"Fyers WS Error: {message}")
            
        def on_open():
            print("Fyers WS Connected!")
            # Subscribe to Nifty, Sensex, Bank Nifty
            if fyers_socket_instance:
                fyers_socket_instance.subscribe(symbols=["NSE:NIFTY50-INDEX", "BSE:SENSEX-INDEX", "NSE:NIFTYBANK-INDEX", "NSE:RELIANCE-EQ", "NSE:TCS-EQ"], data_type="symbolData")
            
        def on_close():
            print("Fyers WS Closed")

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
        print(f"Error starting Fyers socket: {e}")

from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Start the Fyers socket in background thread
    threading.Thread(target=start_fyers_socket, daemon=True).start()
    yield

app.router.lifespan_context = lifespan

signals_cache = {"data": None, "last_updated": 0}

@app.websocket("/ws/live")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
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
                        print(f"[WS] Loaded signals from file: {signals_cache['data'].get('confidence')}%")
                except:
                    pass
                    
            if signals_cache["data"] is None or (time.time() - signals_cache["last_updated"] > 60 and is_market_open):
                try:
                    # Fetch signals for NIFTY by default
                    signals_cache["data"] = await get_signals("NIFTY")
                    signals_cache["last_updated"] = time.time()
                    print(f"[WS] Updated signals cache: {signals_cache['data'].get('confidence')}%")
                except Exception as e:
                    print(f"[WS] Error updating signals cache: {e}")
                    
            # Send the latest data for NIFTY, SENSEX, BANKNIFTY and dynamic stocks
            websocket_data = {
                "NIFTY": current_market_data.get("NSE:NIFTY50-INDEX", {"lp": 23820.35, "chp": -1.49}),
                "SENSEX": current_market_data.get("BSE:SENSEX-INDEX", {"lp": 76015.28, "chp": -1.70}),
                "BANKNIFTY": current_market_data.get("NSE:NIFTYBANK-INDEX", {"lp": 51000.00, "chp": 0.0})
            }
            
            for k, v in current_market_data.items():
                if k not in ["NSE:NIFTY50-INDEX", "BSE:SENSEX-INDEX", "NSE:NIFTYBANK-INDEX"]:
                    short_key = k.split(":")[1].split("-")[0] if ":" in k else k
                    websocket_data[short_key] = v
                    
            # Add trades to WebSocket stream
            from shared.state import load_state
            state = load_state(reload_trades=True)
            websocket_data["trades"] = state.get("trades", [])
            
            # Add signalsData to WebSocket stream
            websocket_data["signalsData"] = signals_cache["data"]
                    
            await websocket.send_json(websocket_data)
            await asyncio.sleep(0.1) # Ultra fast stream (100ms)
    except Exception as e:
        pass

@app.get("/health")
async def health():
    return {"status": "ok"}

@app.post("/api/panic-exit")
async def panic_exit():
    """Nuclear Option: Immediately cancels all orders and squares off all positions."""
    try:
        broker = BrokerFactory.get_active_broker()
        if not broker.authenticate():
            raise HTTPException(status_code=401, detail="Broker not authenticated")
            
        print("!!! PANIC EXIT TRIGGERED !!!")
        
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
                broker.place_order(
                    symbol=pos.symbol,
                    side=side,
                    quantity=qty,
                    order_type="MARKET",
                    product="INTRADAY"
                )
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
        print(f"Panic Exit Failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/engine/status")
async def get_engine_status():
    return engine_state

@app.post("/api/engine/toggle")
async def toggle_engine():
    global engine_state
    engine_state["is_active"] = not engine_state["is_active"]
    if engine_state["is_active"]:
        engine_state["last_start_time"] = datetime.now().isoformat()
        print(">>> TRADING ENGINE STARTED <<<")
    else:
        print("<<< TRADING ENGINE STOPPED >>>")
    
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
        client_id = "0KHBQ6IQA4-100"
        
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
        client_id = "0KHBQ6IQA4-100"
        
        fyers = fyersModel.FyersModel(client_id=client_id, is_async=False, token=token, log_path="")
        
        # Dynamic WebSocket Subscription for real-time updates
        global fyers_socket_instance
        if fyers_socket_instance and symbol not in current_market_data:
            print(f"Subscribing to {symbol} dynamically via WebSocket...")
            try:
                fyers_socket_instance.subscribe(symbols=[symbol], data_type="symbolData")
                # Initialize to prevent duplicate subscriptions
                current_market_data[symbol] = {"lp": 0.0, "chp": 0.0}
            except Exception as e:
                print(f"Failed to subscribe to {symbol}: {e}")

        data = {"symbols": symbol}
        quotes = fyers.quotes(data=data)
        print(f"Quotes response for {symbol}: {quotes}") # Debug log
        
        # Fallback: If WebSocket didn't receive ticks yet, populate from REST API!
        if quotes and quotes.get("s") == "ok" and "d" in quotes and len(quotes["d"]) > 0:
            quote_item = quotes["d"][0]
            v = quote_item.get("v", {})
            lp = v.get("lp")
            chp = v.get("chp", 0.0)
            if lp:
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
        broker = BrokerFactory.get_active_broker()
        print(f"Fetching history via broker: {broker.DISPLAY_NAME} for {symbol}")
        
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

@app.get("/api/backtest")
async def get_backtest(
    symbol: str = Query(..., description="The stock ticker"),
    start_date: str = Query(..., description="Start date"),
    end_date: str = Query(..., description="End date"),
    timeframe: str = Query("5 Min", description="Timeframe"),
    strategy: str = Query("ema_rsi", description="Strategy name"),
    initial_capital: float = Query(100000.0, description="Initial Capital")
):
    """Triggers a true Python backtest using the actual strategy files and broker data."""
    try:
        broker = BrokerFactory.get_active_broker()
        
        # Map symbol using institutional formatter
        original_symbol = symbol
        symbol = format_broker_symbol(symbol)
            
        data = broker.get_historical_data(symbol, start_date, end_date, timeframe)
        
        if not data:
            raise HTTPException(status_code=404, detail=f"No data found for backtest")
            
        # Convert list of dicts to DataFrame for the strategy
        df = pd.DataFrame(data)
        
        # Load Settings
        settings = {}
        if os.path.exists("settings.json"):
            with open("settings.json", "r") as f:
                settings = json.load(f)
                
        ema_fast = settings.get("ema_fast", 20)
        ema_slow = settings.get("ema_slow", 50)
        rsi_window = settings.get("rsi_window", 14)
        rsi_buy = settings.get("rsi_buy", 55)
        rsi_sell = settings.get("rsi_sell", 45)
        
        # Lowercase columns for the strategy
        df.columns = [c.lower() for c in df.columns]
        
        # Generate Signals using Python Strategy via Registry
        try:
            signals = registry.run_strategy(
                strategy, 
                df, 
                ema_fast=ema_fast, 
                ema_slow=ema_slow, 
                rsi_window=rsi_window, 
                rsi_buy_thresh=rsi_buy, 
                rsi_sell_thresh=rsi_sell
            )
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
        
        # Use the formal backtesting engine function for institutional accuracy
        from backtesting_engine.run import run_intraday_backtest
        
        results = run_intraday_backtest(
            df, 
            signals, 
            initial_capital=initial_capital,
            slippage_bps=2.0, 
            commission_per_trade=20.0,
            multiplier=10
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
        settings = {}
        if os.path.exists("settings.json"):
            with open("settings.json", "r") as f:
                settings = json.load(f)
                
        # Calculate extra stats
        trades = results["trades"]
        call_trades = [t for t in trades if t['type'] == 'BUY']
        put_trades = [t for t in trades if t['type'] == 'SELL']
        
        # Add to stats
        results["stats"]["targetPct"] = settings.get("target_pct", 2.0)
        results["stats"]["stoplossPct"] = settings.get("stoploss_pct", 1.8)
        results["stats"]["totalCE"] = len(call_trades)
        results["stats"]["totalPE"] = len(put_trades)
            
        return {
            "symbol": symbol,
            "timeframe": timeframe,
            "strategy": strategy,
            "stats": results["stats"],
            "equityCurve": results["equityCurve"],
            "trades": results["trades"][-20:]
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/equity-data")
async def get_equity_data(symbol: str = "NIFTY"):
    """Returns real price action data mapped as equity data for the dashboard."""
    try:
        broker = BrokerFactory.get_active_broker()
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
        print(f"Error in /equity-data: {e}")
        return []

@app.get("/api/signals")
async def get_signals(
    symbol: str = Query("NIFTY", description="The stock ticker")
):
    """Generates live signals using the actual strategy files and broker data."""
    try:
        end_date = datetime.now()
        start_date = end_date - timedelta(days=10)
        
        # Map symbol using institutional formatter
        symbol = format_broker_symbol(symbol)

        broker = BrokerFactory.get_active_broker()
        data = broker.get_historical_data(symbol, start_date.strftime('%Y-%m-%d'), end_date.strftime('%Y-%m-%d'), "5 Min")
        
        if not data:
            raise HTTPException(status_code=404, detail=f"No data found for signals")
            
        df = pd.DataFrame(data)
        df.columns = [c.lower() for c in df.columns]
        
        # Load Settings
        settings = {}
        if os.path.exists("settings.json"):
            with open("settings.json", "r") as f:
                settings = json.load(f)
                
        ema_fast = settings.get("ema_fast", 20)
        ema_slow = settings.get("ema_slow", 50)
        rsi_window = settings.get("rsi_window", 14)
        rsi_buy = settings.get("rsi_buy", 55)
        rsi_sell = settings.get("rsi_sell", 45)
        # Generate Signals via Registry using advanced_ai!
        from trading_bot.strategies.advanced_ai_ml_strategy import generate_signals as advanced_ai_signals
        signals = advanced_ai_signals(df)
        
        # Read scores from dataframe
        call_scores = df['call_score'] if 'call_score' in df.columns else pd.Series(0, index=df.index)
        put_scores = df['put_score'] if 'put_score' in df.columns else pd.Series(0, index=df.index)
        
        # Determine if market is open (9:15 AM to 3:30 PM IST)
        try:
            import pytz
            ist = pytz.timezone('Asia/Kolkata')
            now = datetime.now(ist)
        except Exception:
            # Fallback if pytz is not available or fails
            now = datetime.now() 
            
        market_open = now.replace(hour=9, minute=15, second=0, microsecond=0)
        market_close = now.replace(hour=15, minute=30, second=0, microsecond=0)
        
        is_market_open = market_open <= now <= market_close and now.weekday() < 5
        
        if is_market_open:
            valid_calls = call_scores.dropna()
            valid_puts = put_scores.dropna()
            last_call_score = int(valid_calls.iloc[-1]) if len(valid_calls) > 0 else 0
            last_put_score = int(valid_puts.iloc[-1]) if len(valid_puts) > 0 else 0
            confidence = max(last_call_score, last_put_score)
        else:
            # Market is closed: Show the last found non-zero confidence
            active_call_scores = call_scores[call_scores > 0]
            active_put_scores = put_scores[put_scores > 0]
            
            last_call_score = int(active_call_scores.iloc[-1]) if len(active_call_scores) > 0 else 0
            last_put_score = int(active_put_scores.iloc[-1]) if len(active_put_scores) > 0 else 0
            
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
            if last_call_score > last_put_score:
                bias = "BULLISH"
                status = "Mild Bullish Bias"
            else:
                bias = "BEARISH"
                status = "Mild Bearish Bias"
                
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
                
        # Save score to file (only if confidence > 0!)
        if confidence > 0:
            try:
                with open("last_confidence.json", "w") as f:
                    json.dump({"confidence": confidence, "status": status, "bias": bias}, f)
            except Exception as e:
                print(f"Error saving confidence file: {e}")
                
        return {
            "confidence": confidence,
            "status": status,
            "bias": f"{bias} Bias Detected",
            "trendData": trend_data,
            "signals": real_signals[-10:][::-1] # Reverse to show latest first!
        }
    except Exception as e:
        print(f"[ERROR] In get_live_signals: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

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
        if os.path.exists("settings.json"):
            with open("settings.json", "r") as f:
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
                [sys.executable, "scripts/automated_login.py"],
                capture_output=True,
                text=True,
                check=False,
                cwd=os.getcwd()
            )
            
            if process.returncode != 0:
                # Revert to backup if failed!
                save_credentials("fyers", backup_creds)
                raise HTTPException(status_code=400, detail="Incorrect credentials or unable to login. Please check your details.")
            
        # Save remaining settings to settings.json
            
        # Save remaining settings to settings.json
        existing = {}
        if os.path.exists("settings.json"):
            with open("settings.json", "r") as f:
                existing = json.load(f)
                
        # Remove any existing plain text credentials from settings.json
        for key in ["fyers_user_id", "fyers_pin", "fyers_totp_key"]:
            if key in existing:
                existing.pop(key)
                
        existing.update(new_settings)
        
        with open("settings.json", "w") as f:
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
            subprocess.run([sys.executable, "scripts/auto_login_fyers.py"], 
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
            [sys.executable, "scripts/automated_login.py"],
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
            [sys.executable, "scripts/automated_login.py"],
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

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
