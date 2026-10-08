import sys, os
sys.path.insert(0, os.path.abspath("."))
import asyncio
import pandas as pd
import numpy as np
from api_bridge import get_history
from trading_bot.strategies.ema9_rsi_momentum.config import Ema9RsiMomentumConfig
from trading_bot.strategies.ema9_rsi_momentum.indicators import compute_indicator_set
from trading_bot.strategies.ema9_rsi_momentum.signal_engine import detect_chop_box, compute_cross_signals

async def main():
    hist = await get_history('NSE:NIFTY50-INDEX', '2026-09-28', '2026-10-02', '5 Min')
    df = pd.DataFrame(hist['data'])
    cols = {c.lower(): c for c in df.columns}
    tcol = cols.get('time') or cols.get('datetime') or cols.get('date')
    for need in ('open', 'high', 'low', 'close'):
        df[need] = pd.to_numeric(df[cols[need]], errors='coerce')
    ts = pd.to_datetime(df[tcol], errors='coerce', utc=False)
    df = df.assign(_ts=ts).dropna(subset=['_ts', 'close']).set_index('_ts').sort_index()

    cfg = Ema9RsiMomentumConfig.from_settings({}, symbol='NSE:NIFTY50-INDEX', timeframe_minutes=5)
    ind = compute_indicator_set(df, cfg.ema_fast, cfg.ema_slow, cfg.rsi_length, cfg.rsi_ma_length)
    is_chop = detect_chop_box(df, ind, cfg)
    sig = compute_cross_signals(df, cfg)

    for i, when in enumerate(df.index):
        if '2026-10-01' in str(when) and str(when) <= '2026-10-01 12:35:00':
            c = df.close.iloc[i]
            o = df.open.iloc[i]
            h = df.high.iloc[i]
            l = df.low.iloc[i]
            e9 = ind.ema_fast.iloc[i]
            e20 = ind.ema_slow.iloc[i]
            rsi = ind.rsi.iloc[i]
            rsi_ma = ind.rsi_ma.iloc[i]
            chop = is_chop[i]
            cm = ind.cm_ma
            hl = cm['bar_highlight'].iloc[i]
            dn = cm['price_cross_ma2_down'].iloc[i]
            up = cm['price_cross_ma2_up'].iloc[i]
            bull = sig.bullish.iloc[i]
            bear = sig.bearish.iloc[i]
            t = when.strftime('%H:%M')
            print(f"{t} | O:{o:.1f} H:{h:.1f} L:{l:.1f} C:{c:.1f} | E9:{e9:.1f} E20:{e20:.1f} | RSI:{rsi:.1f} MA:{rsi_ma:.1f} | Chop:{chop} | CM hl:{hl} dn:{dn} up:{up} | Bull:{bull} Bear:{bear}")

if __name__ == '__main__':
    asyncio.run(main())
