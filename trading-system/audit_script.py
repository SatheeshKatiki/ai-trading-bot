import os
import sys
import pandas as pd
import numpy as np
import time
import hashlib
import json
import warnings
warnings.filterwarnings('ignore')

# Ensure paths are correct
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from trading_bot.strategies.registry import registry
from backtesting_engine.run import run_intraday_backtest

settings = {
    "ema_fast": 20,
    "ema_slow": 50,
    "rsi_window": 14,
    "rsi_buy_thresh": 55,
    "rsi_sell_thresh": 45,
    "stoploss_pct": 15.0,
    "target_pct": 500.0,
    "enable_ema_filter": False,
    "enable_volume_filter": False,
    "enable_adx_filter": False,
    "enable_vwap_filter": False,
    "enable_rsi_filter": False,
    "enable_squeeze_filter": True,
    "enable_extension_filter": True,
    "enable_cpr_filter": False,
    "enable_aggression_filter": True,
    "donchian_period": 10
}

def load_data():
    cache_file = os.path.join(os.path.dirname(__file__), "data", "NSE_NIFTY50-INDEX_5Min.csv")
    if not os.path.exists(cache_file):
        raise FileNotFoundError(f"Cache file {cache_file} not found.")
    df = pd.read_csv(cache_file)
    df.columns = [c.lower() for c in df.columns]
    # Slice to last 1000 rows so AI strategies don't take hours to simulate
    return df.tail(1000).copy()

def run_single_iteration(strategy, df):
    try:
        signals_data = registry.run_strategy(strategy, df.copy(), **settings)
        if isinstance(signals_data, tuple):
            signals = signals_data[0]
        else:
            signals = signals_data
            
        results = run_intraday_backtest(
            df.copy(), 
            signals,
            initial_capital=100000.0,
            quantity=50,
            stoploss_pct=15.0,
            target_pct=500.0,
            trailing_sl=True,
            trail_trigger=0.8,
            trail_offset=0.2,
            enable_pyramiding=True,
            scale_pct=0.2,
            max_scales=2,
            max_daily_loss_pct=3.0,
            max_daily_trades=0
        )
        return results.get('stats', {})
    except Exception as e:
        return {"error": str(e)}

def main():
    try:
        df = load_data()
        print(f"Loaded dataset with {len(df)} candles.")
    except Exception as e:
        print(e)
        return

    strategies = list(registry._strategies.keys())
    results_list = []

    for strat in strategies:
        print(f"Evaluating strategy: {strat}")
        stats = run_single_iteration(strat, df)
        error = stats.get("error")

        if error:
            print(f"  -> FAILED: {error}")

        # run_intraday_backtest's stats dict uses camelCase keys
        # (profitFactor, netProfit, winRate, ...) — report exactly what it
        # computed, or leave a metric blank if the run failed. Do not
        # invent a value for a metric that wasn't actually produced.
        results_list.append({
            "Strategy": strat,
            "Net PnL (₹)": stats.get("netProfit") if not error else None,
            "Win Rate (%)": stats.get("winRate") if not error else None,
            "Max Drawdown (%)": stats.get("maxDrawdown") if not error else None,
            "Profit Factor": stats.get("profitFactor") if not error else None,
            "Sharpe Ratio": stats.get("sharpeRatio") if not error else None,
            "Total Trades": stats.get("totalTrades") if not error else None,
            "Error": error or "",
        })

    report_df = pd.DataFrame(results_list)

    # Sort by Net PnL then Sharpe, treating a failed/missing run as lowest
    # priority rather than crashing on a mix of numbers, "Infinity", and None.
    sort_pnl = pd.to_numeric(report_df["Net PnL (₹)"], errors="coerce").fillna(-np.inf)
    sort_sharpe = pd.to_numeric(report_df["Sharpe Ratio"], errors="coerce").fillna(-np.inf)
    report_df = (
        report_df.assign(_sort_pnl=sort_pnl, _sort_sharpe=sort_sharpe)
        .sort_values(by=["_sort_pnl", "_sort_sharpe"], ascending=[False, False])
        .drop(columns=["_sort_pnl", "_sort_sharpe"])
    )

    out_file = os.path.join(os.path.dirname(__file__), "Strategy_Audit_Report.xlsx")
    report_df.to_excel(out_file, index=False)
    print(f"\nAudit Complete! Report saved to {out_file}")

if __name__ == "__main__":
    main()
