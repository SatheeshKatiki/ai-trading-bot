"""1-Year Historical Backtest Runner for EMA9/RSI Momentum Strategy with Custom TradingView Setup.

Uses 1-year of NIFTY 5-minute historical data (2025-09-22 to 2026-10-01) from data/NSE_NIFTY50-INDEX_5Min.csv.
Evaluates:
- CM Ultimate MA Yellow Candle triggers at bar close
- Chop Box Filter (Purple 'No Trade' Box suppression)
- Dual Entry Engine (Reversals + Trend Pullbacks)
- Adaptive Dynamic Stop Loss
- Realistic Options Execution: Dynamic Black-Scholes delta, spread, theta decay, and slippage.
"""

import sys
import os
from pathlib import Path
import json
import pandas as pd
import numpy as np

# Ensure workspace root is in path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from trading_bot.strategies.ema9_rsi_momentum import generate_signals, Ema9RsiMomentumConfig
from trading_bot.strategies.ema9_rsi_momentum.signal_engine import compute_cross_signals
from backtesting_engine.run import run_intraday_backtest


def main():
    csv_path = ROOT / "data" / "NSE_NIFTY50-INDEX_5Min.csv"
    if not csv_path.exists():
        print(f"Error: Data file not found at {csv_path}")
        return

    print("=====================================================================")
    print("  1-YEAR NIFTY 5-MIN HISTORICAL BACKTEST: EMA9/RSI MOMENTUM STRATEGY")
    print("  (CM Ultimate MA + Custom RSI + Chop Box Filter + Dual Entry)")
    print("=====================================================================")

    print(f"\n1. Loading historical dataset: {csv_path.name}...")
    df = pd.read_csv(csv_path)
    df["datetime"] = pd.to_datetime(df["datetime"])
    df = df.sort_values("datetime").reset_index(drop=True)
    df = df.set_index("datetime", drop=False)

    start_date = df["datetime"].iloc[0].strftime("%Y-%m-%d %H:%M")
    end_date = df["datetime"].iloc[-1].strftime("%Y-%m-%d %H:%M")
    total_bars = len(df)
    trading_days = df["datetime"].dt.date.nunique()

    print(f"   Period: {start_date} to {end_date}")
    print(f"   Total 5-Min Candles: {total_bars:,}")
    print(f"   Total Trading Days:  {trading_days}")

    # Generate signals
    print("\n2. Computing Indicators & Generating Signals...")
    cfg = Ema9RsiMomentumConfig(
        enable_chop_filter=True,
        chop_atr_mult=0.20,
        enable_pullback_entries=True,
        adaptive_sl_enabled=True,
    )

    signals = generate_signals(df)
    cross = compute_cross_signals(df, cfg)

    total_signals = int((signals != 0).sum())
    ce_signals = int((signals == 1).sum())
    pe_signals = int((signals == -1).sum())

    chop_bars = int(cross.is_chop.sum()) if cross.is_chop is not None else 0
    chop_pct = (chop_bars / total_bars) * 100.0 if total_bars > 0 else 0.0

    print(f"   Total Entry Signals Generated: {total_signals}")
    print(f"     -> CE (Bullish) Entries:     {ce_signals}")
    print(f"     -> PE (Bearish) Entries:     {pe_signals}")
    print(f"   Sideways Chop Bars Suppressed: {chop_bars:,} ({chop_pct:.1f}% of all candles)")

    # Run Backtest with realistic parameters
    print("\n3. Simulating Realistic Options Execution...")
    print("   Lot Size: 75 (1 Lot NIFTY) | Starting Capital: Rs. 1,00,000")
    print("   Friction: Dynamic Black-Scholes Delta, Slippage, Brokerage, Option Spread & Theta Decay")

    res = run_intraday_backtest(
        df=df.copy(),
        signals=signals,
        initial_capital=100000.0,
        multiplier=75,
        target_pct=2.5,
        stoploss_pct=1.0,
        trailing_sl=True,
        trail_trigger=0.5,
        trail_offset=0.35,
        max_daily_loss_pct=3.0,
        max_daily_trades=6,
        model_option_costs=True,
        option_premium_pct=0.40,
        option_spread_pct=0.21,
        option_theta_pct_per_day=9.7,
        bar_minutes=5.0,
    )

    # Format and present results
    total_trades = res.get("total_trades", 0)
    win_trades = res.get("winning_trades", 0)
    loss_trades = res.get("losing_trades", 0)
    win_rate = res.get("win_rate", 0.0)
    total_pnl = res.get("total_pnl", 0.0)
    profit_factor = res.get("profit_factor", "0.0")
    max_dd = res.get("max_drawdown_pct", 0.0)
    return_pct = res.get("return_pct", 0.0)
    final_cap = res.get("final_capital", 100000.0)
    brokerage = res.get("total_brokerage", 0.0)
    slippage = res.get("total_slippage", 0.0)
    theta_cost = res.get("total_theta_cost", 0.0)
    spread_cost = res.get("total_spread_cost", 0.0)

    print("\n=====================================================================")
    print("                    PERFORMANCE REPORT SUMMARY")
    print("=====================================================================")
    print(f"  Initial Capital:         Rs. 1,00,000.00")
    print(f"  Final Capital:           Rs. {final_cap:,.2f}")
    print(f"  Net Total P&L:           Rs. {total_pnl:+,.2f}")
    print(f"  Total Return:            {return_pct:+.2f}%")
    print("---------------------------------------------------------------------")
    print(f"  Total Trades:            {total_trades}")
    print(f"  Winning Trades:          {win_trades} ({win_rate:.1f}%)")
    print(f"  Losing Trades:           {loss_trades} ({100.0 - win_rate:.1f}%)")
    print(f"  Profit Factor:           {profit_factor}")
    print(f"  Max Drawdown:            {max_dd:.2f}%")
    print("---------------------------------------------------------------------")
    print(f"  Carrying Costs & Frictions:")
    print(f"    Brokerage Paid:        Rs. {brokerage:,.2f}")
    print(f"    Slippage Paid:         Rs. {slippage:,.2f}")
    print(f"    Spread Friction:       Rs. {spread_cost:,.2f}")
    print(f"    Option Theta Decay:    Rs. {theta_cost:,.2f}")
    print("=====================================================================\n")

    return res


if __name__ == "__main__":
    main()
