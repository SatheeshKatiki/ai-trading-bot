import os
import sys
import json
import time

from brokers import BrokerFactory
from api_bridge import get_historical_data
from trading_bot.strategies.registry import registry
from backtesting_engine.run import Backtest

def test_bt():
    print("Fetching data...")
    t1 = time.time()
    data = get_historical_data("NSE:NIFTY50-INDEX", "2025-05-16", "2026-05-16", "5 Min")
    t2 = time.time()
    print(f"Data fetched in {t2-t1:.2f}s. {len(data)} candles.")
    
    print("Generating signals...")
    import pandas as pd
    df = pd.DataFrame(data)
    df.columns = [c.lower() for c in df.columns]
    
    strategy_fn = registry.get_strategy("ema_rsi")
    signals = strategy_fn(df)
    t3 = time.time()
    print(f"Signals generated in {t3-t2:.2f}s.")
    
    print("Running backtest loop...")
    bt = Backtest(df, initial_capital=100000, commission_per_trade=0, slippage_bps=0)
    bt.run_intraday_backtest(signals, stoploss_pct=1.0)
    t4 = time.time()
    print(f"Backtest engine finished in {t4-t3:.2f}s.")
    
    print(bt.summary())
    
if __name__ == "__main__":
    test_bt()
