import pandas as pd
from trading_bot.strategies.registry import registry
from backtesting_engine.run import run_intraday_backtest
from brokers.broker_factory import BrokerFactory

broker = BrokerFactory.get_active_broker()
data = broker.get_historical_data("NSE:NIFTY50-INDEX", "2024-01-01", "2026-08-31", "5 Min")
df = pd.DataFrame(data)
df.columns = [c.lower() for c in df.columns]

print(f"Loaded DataFrame with {len(df)} candles.")

strats = list(registry._strategies.keys())
for strat_name in strats:
    try:
        signals_data = registry.run_strategy(
            strat_name,
            df.copy(),
            stoploss_pct=1.2,
            target_pct=2.5,
            enable_ema_filter=True,
            enable_vwap_filter=True,
            enable_rsi_filter=True,
        )
        if isinstance(signals_data, tuple):
            signals, rejection_logs = signals_data
        else:
            signals, rejection_logs = signals_data, []

        sig_count = (signals != 0).sum() if hasattr(signals, '__len__') else 0

        res = run_intraday_backtest(
            df=df.copy(),
            signals=signals,
            target_pct=2.5,
            stoploss_pct=1.2,
            initial_capital=100000.0,
            multiplier=65,
            trailing_sl=True,
            trail_trigger=0.5,
            trail_offset=0.35,
            enable_pyramiding=True,
            scale_pct=0.2,
            max_scales=2,
            max_daily_loss_pct=3.0,
            max_daily_trades=6,
            enable_compounding=True
        )
        
        pnl = res.get('total_pnl', 0)
        trades = res.get('total_trades', 0)
        win_rate = res.get('win_rate', 0)
        pf = res.get('profit_factor', 0)
        
        print(f"{strat_name:<25} | Sigs: {sig_count:>5} | Trades: {trades:>5} | Net PnL: Rs. {pnl:>12,.2f} | WinRate: {win_rate:>5.1f}% | PF: {pf:>4.2f}")
    except Exception as e:
        print(f"{strat_name:<25} | Error: {e}")
