import pandas as pd
from trading_bot.strategies.ema9_rsi_momentum import generate_signals

df = pd.read_csv('trading-system/data/NSE_NIFTY50-INDEX_5Min.csv')
sig_series = generate_signals(df, enable_touch_filter=True)
df['signal'] = sig_series

df_today = df[df['datetime'].str.startswith('2026-08-31')]
print(f"{'Time':<8} | {'Open':<8} {'High':<8} {'Low':<8} {'Close':<8} | {'SIGNAL'}")
print("-" * 65)
for idx, row in df_today.iterrows():
    sig = '---'
    if row['signal'] == 1: sig = 'BUY CE'
    elif row['signal'] == -1: sig = 'BUY PE'
    t = row['datetime'].split(' ')[1]
    if sig != '---' or ('11:20' <= t <= '11:55') or ('13:40' <= t <= '14:05') or ('14:30' <= t <= '15:20'):
        print(f"{t:<8} | {row['open']:<8.1f} {row['high']:<8.1f} {row['low']:<8.1f} {row['close']:<8.1f} | {sig}")
