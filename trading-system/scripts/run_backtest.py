import argparse
import pandas as pd
from datetime import datetime, timedelta
import sys
import os

# Add project root to python path so it can find trading_bot and brokers
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from trading_bot.strategies.registry import registry
from brokers import BrokerFactory
from backtesting_engine.run import run_intraday_backtest

# Import and Register strategies
from trading_bot.strategies.ema_rsi_strategy import generate_signals as ema_rsi_signals
from trading_bot.strategies.enhanced_ai_strategy import generate_signals as enhanced_signals
from trading_bot.strategies.premium_selection import generate_signals as premium_signals
from trading_bot.strategies.institutional_ema_strategy import generate_signals as institutional_signals
from trading_bot.strategies.buy_the_dip_strategy import generate_signals as buy_the_dip_signals

registry.register("ema_rsi",      ema_rsi_signals)
registry.register("enhanced_ai",  enhanced_signals)
registry.register("premium",      premium_signals)
registry.register("institutional_ema", institutional_signals)
registry.register("buy_the_dip", buy_the_dip_signals)

def main():
    parser = argparse.ArgumentParser(description="Run Backtest for a Strategy")
    parser.add_argument("--strategy", type=str, default="ema_rsi", help="Strategy name")
    parser.add_argument("--symbol", type=str, default="NIFTY", help="Symbol to test")
    parser.add_argument("--days", type=int, default=5, help="Number of days of historical data to test")
    args = parser.parse_args()

    print(f"=== Starting Backtest ===")
    print(f"Strategy: {args.strategy}")
    print(f"Symbol:   {args.symbol}")
    print(f"Days:     {args.days}")
    print(f"=========================")

    # Fetch Data
    broker = BrokerFactory.get_active_broker()
    
    from datetime import datetime, timedelta
    
    end_date = datetime.now()
    # If today is Sunday (6) or Saturday (5), move back to Friday
    if end_date.weekday() == 6:
        end_date = end_date - timedelta(days=2)
    elif end_date.weekday() == 5:
        end_date = end_date - timedelta(days=1)
        
    start_date = end_date - timedelta(days=args.days)
    
    print(f"Fetching data from {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}...")
    data = broker.get_historical_data(
        args.symbol, 
        start_date.strftime('%Y-%m-%d'), 
        end_date.strftime('%Y-%m-%d'), 
        "5 Min"
    )

    if not data:
        print("Failed to fetch data! Check broker connection or keys.")
        return

    df = pd.DataFrame(data)
    df.columns = [c.lower() for c in df.columns]

    # Load Settings from settings.json
    import json
    settings = {}
    settings_file = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config", "settings.json")
    if os.path.exists(settings_file):
        with open(settings_file, "r") as f:
            settings = json.load(f)
            print(f"Loaded settings from {settings_file}")

    # Generate Signals
    try:
        signals_data = registry.run_strategy(
            args.strategy, 
            df,
            **settings
        )
        if isinstance(signals_data, tuple):
            signals, rejection_logs = signals_data
        else:
            signals, rejection_logs = signals_data, []
        print(f"Successfully generated signals using {args.strategy} with loaded settings.")
    except Exception as e:
        print(f"Error running strategy {args.strategy}: {e}. Falling back to default ema_rsi.")
        signals = ema_rsi_signals(df)
        rejection_logs = []

    # Run Backtest
    print("Running backtest engine simulation...")
    results = run_intraday_backtest(
        df, 
        signals, 
        initial_capital=100000.0,
        slippage_bps=2.0, 
        commission_per_trade=20.0,
        multiplier=10,
        target_pct=settings.get("target_pct", 2.0),
        stoploss_pct=settings.get("stoploss_pct", 1.8),
        enable_partial_profits=True,
        rejection_logs=rejection_logs
    )

    # Print Stats
    print("\n=== Backtest Results ===")
    stats = results.get("stats", {})
    print(f"profitFactor: {stats.get('profitFactor', 'N/A')}")
    print(f"winRate: {stats.get('winRate', 'N/A')}")
    print(f"totalTrades: {stats.get('totalTrades', 0)}")
    print(f"maxDrawdown: {stats.get('maxDrawdown', 'N/A')}")
    print(f"netProfit: {stats.get('netProfit', 0.0):.2f}")
    print(f"avgWinScore: {stats.get('avgWinScore', 'N/A')}")
    print(f"avgLossScore: {stats.get('avgLossScore', 'N/A')}")
    print(f"targetPct: {settings.get('target_pct', 2.0)}%")
    print(f"stoplossPct: {settings.get('stoploss_pct', 1.8)}%")
    print("=========================")
    
    # Print Losing Trades for Deep Analysis
    trades = results.get("trades", [])
    losing_trades = [t for t in trades if t['pnl'] < 0]
    
    call_trades = [t for t in trades if t['type'] == 'BUY']
    put_trades = [t for t in trades if t['type'] == 'SELL']
    
    print(f"Total Call Trades (CE): {len(call_trades)}")
    print(f"Total Put Trades (PE): {len(put_trades)}")
    print("=========================")
    
    if losing_trades:
        print("\n=== [DEBUG] Losing Trades Analysis ===")
        for t in losing_trades[:10]: # Show up to 10
            print(f"Time: {t['time']} | Type: {t['type']} | Score: {t['score']} | PnL: {t['pnl']:.2f}")
        print("=======================================")

if __name__ == "__main__":
    main()
