import os
import sys
import json
import time
from pathlib import Path

# Add project root to python path
sys.path.append(str(Path(__file__).resolve().parents[1]))

from brokers import BrokerFactory

def test_history():
    broker = BrokerFactory.get_active_broker()
    print("Broker:", broker.DISPLAY_NAME)
    
    symbol = "NSE:NIFTY50-INDEX"
    start = "2025-05-16"
    end = "2026-05-16"
    
    print(f"Fetching {start} to {end} for {symbol}...")
    data = broker.get_historical_data(symbol, start, end, "5 Min")
    print(f"Got {len(data)} candles.")
    
    if len(data) > 0:
        import pandas as pd
        from backtesting_engine.run import run_intraday_backtest
        from trading_bot.strategies.registry import registry
        
        df = pd.DataFrame(data)
        df.columns = [c.lower() for c in df.columns]
        
        print("Generating signals...")
        t3 = time.time()
        signals_data = registry.run_strategy("ema_rsi", df)
        if isinstance(signals_data, tuple):
            signals, _ = signals_data
        else:
            signals = signals_data
        t4 = time.time()
        print(f"Signals generated in {t4-t3:.2f}s.")
        
        print("Running backtest loop...")
        stats = run_intraday_backtest(df, signals, initial_capital=100000, commission_per_trade=0, stoploss_pct=1.0)
        t5 = time.time()
        print(f"Backtest engine finished in {t5-t4:.2f}s.")
        print(stats)
        
if __name__ == "__main__":
    test_history()
