from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime, timedelta
import pandas as pd
import json
import os

# Import the Broker Factory to make the API broker-agnostic!
from brokers import BrokerFactory
# Import the actual strategy signal generator
from trading_bot.strategies.ema_rsi_strategy import generate_signals

app = FastAPI(title="Broker Terminal Data Bridge & Backtester")

# Allow requests from the Next.js frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health")
async def health():
    return {"status": "ok"}

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
    strategy: str = Query("ema_rsi", description="Strategy name")
):
    """Triggers a true Python backtest using the actual strategy files and broker data."""
    try:
        broker = BrokerFactory.get_active_broker()
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
        
        # Generate Signals using Python Strategy
        signals = generate_signals(
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
            initial_capital=100000.0,
            slippage_bps=2.0, 
            commission_per_trade=20.0,
            multiplier=10
        )
        
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
        start_date = end_date - timedelta(days=5)
        
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
        
        # Generate Signals
        signals = generate_signals(
            df, 
            ema_fast=ema_fast, 
            ema_slow=ema_slow, 
            rsi_window=rsi_window, 
            rsi_buy_thresh=rsi_buy, 
            rsi_sell_thresh=rsi_sell
        )
        
        last_signal = int(signals.iloc[-1])
        
        bias = "NEUTRAL"
        confidence = 50
        status = "Scanning..."
        
        if last_signal == 1:
            bias = "BUY"
            confidence = 85
            status = "Strong Bullish Trend Detected"
        elif last_signal == -1:
            bias = "SELL"
            confidence = 85
            status = "Bearish Momentum Detected"
        else:
            price_change = df['close'].iloc[-1] - df['close'].iloc[-5] if len(df) >= 5 else 0
            if price_change > 0:
                bias = "BULLISH"
                confidence = 65
                status = "Mild Bullish Bias"
            else:
                bias = "BEARISH"
                confidence = 65
                status = "Mild Bearish Bias"
                
        trend_data = []
        for i in range(max(0, len(df) - 10), len(df)):
            current_time = df['datetime'].iloc[i].split(' ')[1][:5] if 'datetime' in df.columns else "00:00"
            trend_data.append({
                "name": current_time,
                "value": float(df['close'].iloc[i])
            })
            
        return {
            "confidence": confidence,
            "status": status,
            "bias": f"{bias} Bias Detected",
            "trendData": trend_data,
            "signals": [
                {
                    "symbol": symbol,
                    "type": "Intraday",
                    "bias": bias,
                    "strength": "Strong" if confidence > 70 else "Moderate",
                    "confidence": confidence,
                    "time": "Just Now",
                    "reason": f"Live strategy analysis on {symbol} shows {status.lower()}."
                }
            ]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
