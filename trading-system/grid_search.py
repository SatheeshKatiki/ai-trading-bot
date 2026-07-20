import os
import sys
import pandas as pd
import numpy as np
import time
import itertools
from concurrent.futures import ProcessPoolExecutor
import multiprocessing
import warnings
warnings.filterwarnings('ignore')

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from trading_bot.strategies.registry import registry
from backtesting_engine.run import run_intraday_backtest

def load_data():
    cache_file = os.path.join(os.path.dirname(__file__), "data", "NSE_NIFTY50-INDEX_5.csv")
    if not os.path.exists(cache_file):
        raise FileNotFoundError(f"Cache file {cache_file} not found.")
    df = pd.read_csv(cache_file)
    df.columns = [c.lower() for c in df.columns]
    # Slice to last 2000 candles for reasonable grid search speed
    return df.tail(2000).copy()

def run_single_permutation(args):
    strategy, df_chunk, squeeze, extension, cpr, aggression, pyramiding, trailing_sl = args
    
    # Base fixed settings
    settings = {
        "ema_fast": 20, "ema_slow": 50, "rsi_window": 14,
        "rsi_buy_thresh": 55, "rsi_sell_thresh": 45,
        "stoploss_pct": 1.0, "target_pct": 2.5,
        "enable_ema_filter": False, "enable_volume_filter": False,
        "enable_adx_filter": False, "enable_vwap_filter": False,
        "enable_rsi_filter": False, "donchian_period": 10,
        
        # Grid Search parameters
        "enable_squeeze_filter": squeeze,
        "enable_extension_filter": extension,
        "enable_cpr_filter": cpr,
        "enable_aggression_filter": aggression,
    }
    
    try:
        signals_data = registry.run_strategy(strategy, df_chunk.copy(), **settings)
        if isinstance(signals_data, tuple):
            signals = signals_data[0]
        else:
            signals = signals_data
            
        results = run_intraday_backtest(
            df_chunk.copy(), 
            signals,
            initial_capital=100000.0,
            quantity=50,
            stoploss_pct=1.0,
            target_pct=2.5,
            trailing_sl=trailing_sl,
            trail_trigger=0.8,
            trail_offset=0.2,
            enable_pyramiding=pyramiding,
            scale_pct=0.2,
            max_scales=2,
            max_daily_loss_pct=3.0,
            max_daily_trades=0
        )
        
        stats = results.get('stats', {})
        pnl = stats.get("total_pnl", 0)
        sharpe = stats.get("sharpe", 0)
        win_rate = stats.get("win_rate_%", 0)
        
        return {
            "Strategy": strategy,
            "Squeeze": squeeze, "Extension": extension, "CPR": cpr, 
            "Aggression": aggression, "Pyramiding": pyramiding, "Trailing_SL": trailing_sl,
            "Net PnL": pnl,
            "Win Rate": win_rate,
            "Sharpe Ratio": sharpe,
            "Total Trades": stats.get("total_trades", 0),
            "Max Drawdown": stats.get("max_drawdown_%", 0)
        }
    except Exception as e:
        print(f"Error in {strategy}: {e}", flush=True)
        return None

def main():
    try:
        df = load_data()
        print(f"Loaded dataset with {len(df)} candles.", flush=True)
    except Exception as e:
        print(f"Error loading data: {e}", flush=True)
        return

    strategies = list(registry._strategies.keys())
    
    # Generate all 64 permutations
    filters = [True, False]
    permutations = list(itertools.product(filters, repeat=6))
    
    all_results = []
    
    print(f"Executing 64 permutations across {len(strategies)} strategies (Total: {64*len(strategies)} backtests)...", flush=True)
    
    for strategy in strategies:
        print(f"Optimizing {strategy}...", flush=True)
        
        # Exclude AI/Meta strategies from exhaustive grid search due to computational intensity
        if "ai" in strategy.lower() or "meta" in strategy.lower():
            print(f"Skipping {strategy} (too slow for exhaustive grid search).")
            continue
            
        df_to_use = df.copy()
            
        args_list = [(strategy, df_to_use, *p) for p in permutations]
        
        strategy_results = []
        for idx, args in enumerate(args_list):
            if idx % 10 == 0:
                print(f"  -> Running perm {idx}/64 for {strategy}", flush=True)
            res = run_single_permutation(args)
            if res:
                strategy_results.append(res)
                    
        # Rank within strategy
        if strategy_results:
            strategy_results = sorted(strategy_results, key=lambda x: (x["Sharpe Ratio"], x["Net PnL"]), reverse=True)
            all_results.extend(strategy_results)
            print(f"  -> Best PnL: {strategy_results[0]['Net PnL']} | Best Sharpe: {strategy_results[0]['Sharpe Ratio']}", flush=True)
            
    # Save the full grid search to CSV
    out_file = os.path.join(os.path.dirname(__file__), "Grid_Search_Results.csv")
    final_df = pd.DataFrame(all_results)
    final_df.to_csv(out_file, index=False)
    
    print(f"\nGrid search completed! Full results saved to {out_file}", flush=True)

if __name__ == "__main__":
    multiprocessing.freeze_support()
    main()
