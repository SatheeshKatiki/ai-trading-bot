import sys, os
sys.path.insert(0, os.path.abspath("."))
import asyncio
import pandas as pd
import numpy as np
from api_bridge import get_history
from trading_bot.strategies.ema9_rsi_momentum.config import Ema9RsiMomentumConfig
from trading_bot.strategies.ema9_rsi_momentum.signal_engine import compute_cross_signals

async def test():
    hist = await get_history('NSE:NIFTY50-INDEX', '2026-09-28', '2026-10-02', '5 Min')
    df = pd.DataFrame(hist['data'])
    cols = {c.lower(): c for c in df.columns}
    tcol = cols.get('time') or cols.get('datetime') or cols.get('date')
    for need in ('open', 'high', 'low', 'close'):
        df[need] = pd.to_numeric(df[cols[need]], errors='coerce')
    ts = pd.to_datetime(df[tcol], errors='coerce', utc=False)
    df = df.assign(_ts=ts).dropna(subset=['_ts', 'close']).set_index('_ts').sort_index()

    cfg = Ema9RsiMomentumConfig.from_settings({}, symbol='NSE:NIFTY50-INDEX', timeframe_minutes=5)
    sig = compute_cross_signals(df, cfg)
    bullish = np.asarray(sig.bullish, dtype=bool)
    bearish = np.asarray(sig.bearish, dtype=bool)

    print("=== Signal Engine Output (compute_cross_signals) ===")
    for i, when in enumerate(df.index):
        if '2026-09-30' in str(when) or '2026-10-01' in str(when):
            if bullish[i] or bearish[i]:
                side = 'CE Buy' if bullish[i] else 'PE Buy'
                print(f"{when.strftime('%Y-%m-%d %H:%M')} -> {side} | Close: {df.close.iloc[i]} | RSI: {sig.indicators.rsi.iloc[i]:.1f}")

    # Full trade simulation with day reset and EOD
    open_pos = None
    prev_date = None
    close_arr = np.asarray(df['close'], float)
    high_arr = np.asarray(df['high'], float)
    low_arr = np.asarray(df['low'], float)

    print("\n=== Simulated Trade Markers ===")
    for i, when in enumerate(df.index):
        cur_date = when.date()
        if prev_date is not None and cur_date != prev_date:
            open_pos = None
        prev_date = cur_date

        t_str = when.strftime('%H:%M')
        if open_pos is not None and t_str >= '15:20':
            if '2026-09-30' in str(when) or '2026-10-01' in str(when):
                print(f"{when.strftime('%Y-%m-%d %H:%M')} -> EXIT (EOD) | Close: {close_arr[i]}")
            open_pos = None
            continue

        if open_pos is not None and i > open_pos['idx']:
            sl = open_pos['sl']
            if open_pos['side'] == 1 and low_arr[i] <= sl:
                if '2026-09-30' in str(when) or '2026-10-01' in str(when):
                    print(f"{when.strftime('%Y-%m-%d %H:%M')} -> SL | Close: {close_arr[i]}")
                open_pos = None
            elif open_pos['side'] == -1 and high_arr[i] >= sl:
                if '2026-09-30' in str(when) or '2026-10-01' in str(when):
                    print(f"{when.strftime('%Y-%m-%d %H:%M')} -> SL | Close: {close_arr[i]}")
                open_pos = None
            elif open_pos['side'] == 1 and bearish[i]:
                if '2026-09-30' in str(when) or '2026-10-01' in str(when):
                    print(f"{when.strftime('%Y-%m-%d %H:%M')} -> EXIT | Close: {close_arr[i]}")
                open_pos = None
            elif open_pos['side'] == -1 and bullish[i]:
                if '2026-09-30' in str(when) or '2026-10-01' in str(when):
                    print(f"{when.strftime('%Y-%m-%d %H:%M')} -> EXIT | Close: {close_arr[i]}")
                open_pos = None

        if open_pos is None:
            if bullish[i]:
                sl = float(low_arr[i] * 0.998)
                if '2026-09-30' in str(when) or '2026-10-01' in str(when):
                    print(f"{when.strftime('%Y-%m-%d %H:%M')} -> CE Buy | Close: {close_arr[i]}")
                open_pos = {'side': 1, 'idx': i, 'sl': sl}
            elif bearish[i]:
                sl = float(high_arr[i] * 1.002)
                if '2026-09-30' in str(when) or '2026-10-01' in str(when):
                    print(f"{when.strftime('%Y-%m-%d %H:%M')} -> PE Buy | Close: {close_arr[i]}")
                open_pos = {'side': -1, 'idx': i, 'sl': sl}

if __name__ == '__main__':
    asyncio.run(test())
