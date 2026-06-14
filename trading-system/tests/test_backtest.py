import os
import sys
import json
import time
from pathlib import Path

# Add project root to python path
sys.path.append(str(Path(__file__).resolve().parents[1]))

from brokers import BrokerFactory
from trading_bot.strategies.registry import registry
from backtesting_engine.run import run_intraday_backtest

def test_bt():
    print("Fetching data...")
    t1 = time.time()
    broker = BrokerFactory.get_active_broker()
    data = broker.get_historical_data("NSE:NIFTY50-INDEX", "2025-05-16", "2026-05-16", "5 Min")
    t2 = time.time()
    print(f"Data fetched in {t2-t1:.2f}s. {len(data)} candles.")
    
    print("Generating signals...")
    import pandas as pd
    df = pd.DataFrame(data)
    df.columns = [c.lower() for c in df.columns]
    
    signals_data = registry.run_strategy("ema_rsi", df)
    if isinstance(signals_data, tuple):
        signals, _ = signals_data
    else:
        signals = signals_data
    t3 = time.time()
    print(f"Signals generated in {t3-t2:.2f}s.")
    
    print("Running backtest loop...")
    results = run_intraday_backtest(df, signals, initial_capital=100000, commission_per_trade=0, stoploss_pct=1.0)
    t4 = time.time()
    print(f"Backtest engine finished in {t4-t3:.2f}s.")
    
    print(results.get("stats"))
    
if __name__ == "__main__":
    test_bt()
