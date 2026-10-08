import sys, os
sys.path.insert(0, os.path.abspath("."))
import asyncio
import pandas as pd
import numpy as np
from api_bridge import get_history
from trading_bot.strategies.ema9_rsi_momentum.config import Ema9RsiMomentumConfig
from trading_bot.strategies.ema9_rsi_momentum.indicators import compute_indicator_set, crossed_above, crossed_below
from trading_bot.strategies.ema9_rsi_momentum.signal_engine import detect_chop_box, assess_entry_quality, adx

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
    ind = compute_indicator_set(df, cfg.ema_fast, cfg.ema_slow, cfg.rsi_length, cfg.rsi_ma_length)

    ema_up = crossed_above(ind.ema_fast, ind.ema_slow)
    ema_dn = crossed_below(ind.ema_fast, ind.ema_slow)
    rsi_vals = np.asarray(ind.rsi, dtype=float)
    rsi_ma_vals = np.asarray(ind.rsi_ma, dtype=float)
    rsi_bullish = np.asarray(rsi_vals > rsi_ma_vals, dtype=bool)
    rsi_bearish = np.asarray(rsi_vals < rsi_ma_vals, dtype=bool)

    cm_df = ind.cm_ma
    cr_up2 = np.asarray(cm_df['price_cross_ma2_up'], dtype=bool)
    cr_down2 = np.asarray(cm_df['price_cross_ma2_down'], dtype=bool)
    bar_hl = np.asarray(cm_df.get('bar_highlight', False), dtype=bool)
    close_arr = np.asarray(df['close'], dtype=float)
    open_arr = np.asarray(df['open'], dtype=float)
    fast_arr = np.asarray(ind.ema_fast, dtype=float)
    yellow_ce = cr_up2 | (bar_hl & (close_arr > fast_arr) & (close_arr >= open_arr))
    yellow_pe = cr_down2 | (bar_hl & (close_arr < fast_arr) & (close_arr <= open_arr))

    is_chop = detect_chop_box(df, ind, cfg)
    not_chop = ~is_chop
    adx_series = adx(df, window=14)
    adx_ok = np.asarray(adx_series >= cfg.min_adx, dtype=bool)

    # In assess_entry_quality: pass direction array (+1 for CE, -1 for PE)
    quality_ce = assess_entry_quality(df, ind, cfg, np.full(len(df), 1))
    quality_pe = assess_entry_quality(df, ind, cfg, np.full(len(df), -1))
    touch_ce = quality_ce.take
    touch_pe = quality_pe.take

    crossover_ce = ema_up & rsi_bullish & (rsi_vals >= 48.0)
    crossover_pe = ema_dn & rsi_bearish & (rsi_vals <= 52.0)

    rsi_s = pd.Series(rsi_vals)
    rsi_falling = (rsi_s < rsi_s.shift(1).bfill()).to_numpy()
    rsi_rising = (rsi_s > rsi_s.shift(1).bfill()).to_numpy()
    rsi_bear_momentum = rsi_bearish | rsi_falling
    rsi_bull_momentum = rsi_bullish | rsi_rising

    pullback_ce = (ind.ema_fast > ind.ema_slow) & yellow_ce & (ind.rsi > 50.0) & rsi_bull_momentum & not_chop & touch_ce & adx_ok
    pullback_pe = (ind.ema_fast < ind.ema_slow) & yellow_pe & (ind.rsi < 50.0) & rsi_bear_momentum & not_chop & touch_pe & adx_ok

    cand_ce = np.asarray(crossover_ce | pullback_ce, dtype=bool)
    cand_pe = np.asarray(crossover_pe | pullback_pe, dtype=bool)

    for i, when in enumerate(df.index):
        if '2026-10-01' in str(when) or '2026-09-30' in str(when):
            if cand_ce[i] or cand_pe[i]:
                side = 'CE' if cand_ce[i] else 'PE'
                which = 'Crossover' if (crossover_ce[i] or crossover_pe[i]) else 'Pullback/Breakdown'
                print(f"{when.strftime('%Y-%m-%d %H:%M')} -> {side} Buy ({which}) | Close: {close_arr[i]} | RSI: {rsi_vals[i]:.1f}")

if __name__ == '__main__':
    asyncio.run(test())
