import pandas as pd
from trading_bot.strategies.registry import registry
from backtesting_engine.run import run_intraday_backtest

# Test on 1Min data
df1m = pd.read_csv('trading-system/data/NSE_NIFTY50-INDEX_1Min.csv')
df1m.columns = [c.lower() for c in df1m.columns]
df1m.index = pd.to_datetime(df1m['datetime'])

# Test on 5Min data
df5m = pd.read_csv('trading-system/data/NSE_NIFTY50-INDEX_5Min.csv')
df5m.columns = [c.lower() for c in df5m.columns]
df5m.index = pd.to_datetime(df5m['datetime'])

tests = [
    ("1 Min | Institutional Momentum (SL 0.6%)", df1m, "institutional_momentum", 0.6, 2.5),
    ("1 Min | EMA9 RSI Momentum (SL 0.6%)", df1m, "ema9_rsi_momentum", 0.6, 2.5),
    ("5 Min | Institutional Momentum (SL 0.6%)", df5m, "institutional_momentum", 0.6, 2.5),
    ("5 Min | EMA9 RSI Momentum (SL 1.2%)", df5m, "ema9_rsi_momentum", 1.2, 2.5),
]

for label, df_data, strat_name, sl, tp in tests:
    try:
        signals_data = registry.run_strategy(strat_name, df_data.copy(), stoploss_pct=sl, target_pct=tp)
        if isinstance(signals_data, tuple):
            signals, _ = signals_data
        else:
            signals = signals_data

        res = run_intraday_backtest(
            df=df_data.copy(),
            signals=signals,
            initial_capital=100000.0,
            slippage_bps=2.0,
            commission_per_trade=20.0,
            multiplier=65,
            options_delta=0.5,
            stoploss_pct=sl,
            target_pct=tp,
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
        print(f"{label:<45} -> Net PnL: Rs. {pnl:>12,.2f} | Trades: {trades:>4} | WinRate: {win_rate:>5.1f}% | PF: {pf}")
    except Exception as e:
        print(f"{label:<45} -> Error: {e}")
