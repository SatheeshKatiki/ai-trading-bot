import sys, os
sys.path.insert(0, os.path.abspath("."))
import asyncio
import pandas as pd
import numpy as np
from api_bridge import get_history
from trading_bot.strategies.ema9_rsi_momentum.config import Ema9RsiMomentumConfig
from trading_bot.strategies.ema9_rsi_momentum.indicators import compute_indicator_set, crossed_above, crossed_below

async def run_simulation():
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

    ema_up = np.asarray(crossed_above(ind.ema_fast, ind.ema_slow), bool)
    ema_dn = np.asarray(crossed_below(ind.ema_fast, ind.ema_slow), bool)
    rsi_vals = np.asarray(ind.rsi, float)
    rsi_ma = np.asarray(ind.rsi_ma, float)
    rsi_prev = pd.Series(rsi_vals).shift(1).bfill().to_numpy()

    from trading_bot.strategies.ema9_rsi_momentum.signal_engine import detect_chop_box, assess_entry_quality

    is_chop = detect_chop_box(df, ind, cfg)
    not_chop = ~is_chop
    quality_pe = assess_entry_quality(df, ind, cfg, np.full(len(df), -1))
    quality_ce = assess_entry_quality(df, ind, cfg, np.full(len(df), 1))
    touch_pe = quality_pe.take
    touch_ce = quality_ce.take

    # 1. 9/20 Crossover (Highest Priority)
    crossover_ce = ema_up & (rsi_vals > rsi_ma) & (rsi_vals >= 48.0)
    crossover_pe = ema_dn & (rsi_vals < rsi_ma) & (rsi_vals <= 52.0)

    # 2. Pullback / Breakdown with Yellow Candle & Touch
    cm = ind.cm_ma
    cr_down2 = np.asarray(cm['price_cross_ma2_down'], bool) if cm is not None else np.zeros(len(df), bool)
    cr_up2 = np.asarray(cm['price_cross_ma2_up'], bool) if cm is not None else np.zeros(len(df), bool)
    bar_hl = np.asarray(cm.get('bar_highlight', False), bool) if cm is not None else np.zeros(len(df), bool)
    close_arr = np.asarray(df['close'], float)
    open_arr = np.asarray(df['open'], float)
    fast = np.asarray(ind.ema_fast)
    slow = np.asarray(ind.ema_slow)

    yellow_ce = cr_up2 | (bar_hl & (close_arr > fast) & (close_arr >= open_arr))
    yellow_pe = cr_down2 | (bar_hl & (close_arr < fast) & (close_arr <= open_arr))

    rsi_s = pd.Series(rsi_vals)
    rsi_falling = (rsi_s < rsi_s.shift(1).bfill()).to_numpy()
    rsi_rising = (rsi_s > rsi_s.shift(1).bfill()).to_numpy()

    rsi_dn_ok = (rsi_vals < rsi_ma) | rsi_falling
    rsi_up_ok = (rsi_vals > rsi_ma) | rsi_rising

    pullback_pe = (fast < slow) & yellow_pe & (rsi_vals < 50.0) & rsi_dn_ok & not_chop & touch_pe
    pullback_ce = (fast > slow) & yellow_ce & (rsi_vals > 50.0) & rsi_up_ok & not_chop & touch_ce

    bullish = crossover_ce | pullback_ce
    bearish = crossover_pe | pullback_pe

    # Simulate with intraday day-reset and SL
    open_pos = None
    prev_date = None
    markers = []

    for i, when in enumerate(df.index):
        cur_date = when.date()
        if prev_date is not None and cur_date != prev_date:
            open_pos = None
        prev_date = cur_date

        t_str = when.strftime('%H:%M')
        if open_pos is not None and t_str >= '15:20':
            markers.append((str(when), 'EXIT (EOD)', float(df.close.iloc[i])))
            open_pos = None
            continue

        # Check SL or Reversal Exit
        if open_pos is not None and i > open_pos['idx']:
            if open_pos['side'] == -1:
                sl_val = open_pos['sl']
                if df.high.iloc[i] >= sl_val:
                    markers.append((str(when), f"SL {round(sl_val)}", float(df.close.iloc[i])))
                    open_pos = None
                elif crossover_ce[i]:
                    markers.append((str(when), 'EXIT', float(df.close.iloc[i])))
                    open_pos = None
            elif open_pos['side'] == 1:
                sl_val = open_pos['sl']
                if df.low.iloc[i] <= sl_val:
                    markers.append((str(when), f"SL {round(sl_val)}", float(df.close.iloc[i])))
                    open_pos = None
                elif crossover_pe[i]:
                    markers.append((str(when), 'EXIT', float(df.close.iloc[i])))
                    open_pos = None

        if open_pos is None and t_str >= '09:20' and t_str <= '15:15':
            if bullish[i]:
                sl = float(df.low.iloc[i] * 0.998)
                markers.append((str(when), 'CE Buy', float(df.close.iloc[i])))
                open_pos = {'side': 1, 'idx': i, 'sl': sl}
            elif bearish[i]:
                sl = float(df.high.iloc[i] * 1.002)
                markers.append((str(when), 'PE Buy', float(df.close.iloc[i])))
                open_pos = {'side': -1, 'idx': i, 'sl': sl}

    for m in markers:
        if '2026-10-01' in m[0] or '2026-09-30' in m[0]:
            print(m)

if __name__ == '__main__':
    asyncio.run(run_simulation())
