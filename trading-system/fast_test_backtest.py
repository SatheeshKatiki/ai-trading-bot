import pandas as pd
from trading_bot.strategies.registry import registry
from backtesting_engine.run import run_intraday_backtest

df = pd.read_csv('trading-system/data/NSE_NIFTY50-INDEX_5Min.csv')
df.columns = [c.lower() for c in df.columns]

# Ensure datetime index
if 'datetime' in df.columns:
    df.index = pd.to_datetime(df['datetime'])

print(f"Loaded DataFrame: {len(df)} rows.")

strategies = [
    ("EMA9_RSI_Momentum (Touch Filter ON)", "ema9_rsi_momentum", {"enable_touch_filter": True}),
    ("EMA9_RSI_Momentum (Touch Filter OFF)", "ema9_rsi_momentum", {"enable_touch_filter": False}),
    ("EMA_RSI (Fast=20, Slow=50)", "ema_rsi", {}),
    ("Institutional Momentum", "institutional_momentum", {}),
    ("Momentum 15/5", "momentum_15_5", {}),
    ("Structure Break", "structure_break", {}),
    ("Buy The Dip", "buy_the_dip", {}),
]

for label, strat_name, extra_kwargs in strategies:
    try:
        signals_data = registry.run_strategy(
            strat_name,
            df.copy(),
            stoploss_pct=1.2,
            target_pct=2.5,
            enable_ema_filter=True,
            enable_vwap_filter=True,
            enable_rsi_filter=True,
            **extra_kwargs
        )
        if isinstance(signals_data, tuple):
            signals, rejection_logs = signals_data
        else:
            signals, rejection_logs = signals_data, []

        sig_count = (signals != 0).sum() if hasattr(signals, '__len__') else 0

        res = run_intraday_backtest(
            df=df.copy(),
            signals=signals,
            initial_capital=100000.0,
            slippage_bps=2.0,
            commission_per_trade=20.0,
            multiplier=65,
            options_delta=0.5,
            stoploss_pct=1.2,
            target_pct=2.5,
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
        
        print(f"{label:<40} | Signals: {sig_count:>4} | Trades: {trades:>4} | Net PnL: Rs. {pnl:>12,.2f} | WinRate: {win_rate:>5.1f}% | PF: {pf}")
    except Exception as e:
        print(f"{label:<40} | Error: {e}")
