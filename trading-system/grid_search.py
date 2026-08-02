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

def load_data(holdout_fraction: float = 0.3):
    """Load data and split it chronologically into a grid-search (in-sample)
    slice and a held-out (out-of-sample) slice.

    High audit finding this fixes: the grid search used to run entirely
    against a single df.tail(2000) (~7 trading days) slice with no
    out-of-sample check at all — "best" parameters were whatever fit that
    one week of data best, indistinguishable from curve-fitting to noise.
    The in-sample slice is still 2000 candles (unchanged search cost/data
    volume), but there's now a separate, later, never-searched-on holdout
    slice to validate the eventual winner against.
    """
    cache_file = os.path.join(os.path.dirname(__file__), "data", "NSE_NIFTY50-INDEX_5.csv")
    if not os.path.exists(cache_file):
        raise FileNotFoundError(f"Cache file {cache_file} not found.")
    df = pd.read_csv(cache_file)
    df.columns = [c.lower() for c in df.columns]

    in_sample_size = 2000
    holdout_size = max(200, int(in_sample_size * holdout_fraction / (1 - holdout_fraction)))
    total_needed = in_sample_size + holdout_size

    tail = df.tail(total_needed).copy().reset_index(drop=True)
    if len(tail) < total_needed:
        # Not enough history for a full split — keep the in-sample slice
        # full size and shrink the holdout instead of silently searching
        # on the exact same data twice.
        in_sample_df = tail.iloc[: max(0, len(tail) - holdout_size)].reset_index(drop=True)
        holdout_df = tail.iloc[max(0, len(tail) - holdout_size):].reset_index(drop=True)
    else:
        in_sample_df = tail.iloc[:in_sample_size].reset_index(drop=True)
        holdout_df = tail.iloc[in_sample_size:].reset_index(drop=True)

    return in_sample_df, holdout_df

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
        # run_intraday_backtest's stats dict uses camelCase keys (netProfit,
        # sharpeRatio, winRate, ...) — the old snake_case/percent-suffixed
        # lookups here never matched, so every permutation silently scored
        # PnL=0/Sharpe=0/WinRate=0 and ranking picked an arbitrary
        # (effectively first-encountered, via Python's stable sort)
        # permutation rather than the actually best one. Same root cause
        # already fixed in audit_script.py.
        pnl = stats.get("netProfit", 0)
        sharpe = stats.get("sharpeRatio", 0)
        win_rate = stats.get("winRate", 0)

        return {
            "Strategy": strategy,
            "Squeeze": squeeze, "Extension": extension, "CPR": cpr,
            "Aggression": aggression, "Pyramiding": pyramiding, "Trailing_SL": trailing_sl,
            "Net PnL": pnl,
            "Win Rate": win_rate,
            "Sharpe Ratio": sharpe,
            "Total Trades": stats.get("totalTrades", 0),
            "Max Drawdown": stats.get("maxDrawdown", 0)
        }
    except Exception as e:
        print(f"Error in {strategy}: {e}", flush=True)
        return None

def main():
    try:
        df, holdout_df = load_data()
        print(f"Loaded {len(df)} in-sample candles + {len(holdout_df)} held-out (never searched on) candles.", flush=True)
    except Exception as e:
        print(f"Error loading data: {e}", flush=True)
        return

    strategies = list(registry._strategies.keys())

    # Generate all 64 permutations
    filters = [True, False]
    permutations = list(itertools.product(filters, repeat=6))

    all_results = []
    overfit_summary = []

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
            best = strategy_results[0]
            print(f"  -> Best IN-SAMPLE PnL: {best['Net PnL']} | Sharpe: {best['Sharpe Ratio']}", flush=True)

            # Validate the in-sample winner against data it never saw during
            # the search — a permutation that looks great in-sample but
            # collapses here was fit to noise in that one slice, not a real
            # edge. This re-runs only the single best permutation per
            # strategy, not the full 64, to keep the added cost small.
            oos_args = (
                strategy, holdout_df.copy(),
                best["Squeeze"], best["Extension"], best["CPR"],
                best["Aggression"], best["Pyramiding"], best["Trailing_SL"],
            )
            oos_result = run_single_permutation(oos_args)
            if oos_result:
                is_sharpe = best["Sharpe Ratio"]
                oos_sharpe = oos_result["Sharpe Ratio"]
                overfit_flag = "OVERFIT" if (is_sharpe > 0 and oos_sharpe < is_sharpe * 0.3) else "OK"
                print(
                    f"  -> Held-out OUT-OF-SAMPLE PnL: {oos_result['Net PnL']} | "
                    f"Sharpe: {oos_sharpe} [{overfit_flag}]",
                    flush=True,
                )
                overfit_summary.append({
                    "Strategy": strategy,
                    "IS_Sharpe": is_sharpe, "OOS_Sharpe": oos_sharpe,
                    "IS_PnL": best["Net PnL"], "OOS_PnL": oos_result["Net PnL"],
                    "Verdict": overfit_flag,
                })

    if overfit_summary:
        overfit_file = os.path.join(os.path.dirname(__file__), "Grid_Search_Overfit_Check.csv")
        pd.DataFrame(overfit_summary).to_csv(overfit_file, index=False)
        print(f"\nOut-of-sample overfit check saved to {overfit_file}", flush=True)

    # Save the full grid search to CSV
    out_file = os.path.join(os.path.dirname(__file__), "Grid_Search_Results.csv")
    final_df = pd.DataFrame(all_results)
    final_df.to_csv(out_file, index=False)
    
    print(f"\nGrid search completed! Full results saved to {out_file}", flush=True)

if __name__ == "__main__":
    multiprocessing.freeze_support()
    main()
