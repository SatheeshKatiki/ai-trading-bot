"""Institutional EMA Crossover Options Buying Strategy.

Focused on Call/Put buying with heavy filtering, momentum confirmation,
and Smart Money Concepts. Includes filter debugging.
"""

from __future__ import annotations

import os
import pandas as pd
import numpy as np
import datetime
from typing import Dict, Any

from shared.indicators import ema, rsi, macd, smc_features, supertrend

STRATEGY_NAME = "institutional_ema"

# ---------------------------------------------------------------------------
# Helper Indicators
# ---------------------------------------------------------------------------

def vwap(df: pd.DataFrame) -> pd.Series:
    """Calculate Daily Volume Weighted Average Price (VWAP)."""
    typical_price = (df['high'] + df['low'] + df['close']) / 3
    tp_v = typical_price * df['volume']
    
    if 'datetime' in df.columns:
        dates = pd.to_datetime(df['datetime']).dt.date
        cum_tp_v = tp_v.groupby(dates).cumsum()
        cum_v = df['volume'].groupby(dates).cumsum()
    else:
        try:
            dates = df.index.date
            cum_tp_v = tp_v.groupby(dates).cumsum()
            cum_v = df['volume'].groupby(dates).cumsum()
        except AttributeError:
            cum_tp_v = tp_v.cumsum()
            cum_v = df['volume'].cumsum()
            
    return cum_tp_v / cum_v

def adx(df: pd.DataFrame, period: int = 14) -> pd.DataFrame:
    """Calculate Average Directional Index (ADX) and DMI."""
    high = df['high']
    low = df['low']
    close = df['close']
    
    plus_dm = high.diff()
    minus_dm = -low.diff()
    plus_dm[plus_dm < 0] = 0
    minus_dm[minus_dm < 0] = 0
    
    plus_dm[plus_dm < minus_dm] = 0
    minus_dm[minus_dm < plus_dm] = 0
    
    tr1 = high - low
    tr2 = abs(high - close.shift(1))
    tr3 = abs(low - close.shift(1))
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    
    atr = tr.ewm(alpha=1/period, adjust=False).mean()
    plus_di = 100 * (plus_dm.ewm(alpha=1/period, adjust=False).mean() / atr)
    minus_di = 100 * (minus_dm.ewm(alpha=1/period, adjust=False).mean() / atr)
    
    dx = 100 * abs(plus_di - minus_di) / (plus_di + minus_di)
    adx_val = dx.ewm(alpha=1/period, adjust=False).mean()
    
    return pd.DataFrame({
        'adx': adx_val,
        'plus_di': plus_di,
        'minus_di': minus_di
    })

# ---------------------------------------------------------------------------
# Main Strategy Logic
# ---------------------------------------------------------------------------

def generate_signals(
    df: pd.DataFrame,
    ema_fast: int = 9,
    ema_slow: int = 21,
    rsi_window: int = 14,
    rsi_ema_len: int = 21,
    adx_period: int = 14,
    supertrend_period: int = 10,
    supertrend_mult: float = 3.0,
    volume_sma_len: int = 20,
    **kwargs
) -> pd.Series:
    """Generate institutional options buying signals with debugging."""
    # df = df.copy()  # Removed to allow indicators to be passed back to backtester
    signals = pd.Series(0, index=df.index)
    
    if len(df) < max(ema_slow, rsi_window, adx_period, volume_sma_len) + 5:
        return signals
        
    # 1. Base Technicals
    df['ema_9'] = ema(df['close'], ema_fast)
    df['ema_21'] = ema(df['close'], ema_slow)
    df['rsi'] = rsi(df['close'], rsi_window)
    df['rsi_ema'] = df['rsi'].ewm(span=rsi_ema_len, adjust=False).mean()
    
    macd_df = macd(df['close'])
    df['macd'] = macd_df['macd']
    df['macd_signal'] = macd_df['signal']
    df['macd_hist'] = macd_df['hist']
    
    df['vwap'] = vwap(df)
    
    st_df = supertrend(df, period=supertrend_period, multiplier=supertrend_mult)
    df['supertrend'] = st_df['supertrend']
    df['st_direction'] = st_df['direction']
    
    adx_df = adx(df, period=adx_period)
    df['adx'] = adx_df['adx']
    df['plus_di'] = adx_df['plus_di']
    df['minus_di'] = adx_df['minus_di']
    
    df['volume_sma'] = df['volume'].rolling(window=volume_sma_len).mean()
    
    # Calculate ATR (Average True Range) for dynamic SL/Target
    high_low = df['high'] - df['low']
    high_close = abs(df['high'] - df['close'].shift())
    low_close = abs(df['low'] - df['close'].shift())
    ranges = pd.concat([high_low, high_close, low_close], axis=1)
    true_range = ranges.max(axis=1)
    df['atr'] = true_range.rolling(14).mean()
    
    # Swing High/Low for Breakout and Risk Management
    df['swing_high'] = df['high'].rolling(window=10).max()
    df['swing_low'] = df['low'].rolling(window=10).min()
    
    smc_df = smc_features(df)
    for col in smc_df.columns:
        if col not in df.columns:
            df[col] = smc_df[col]
    
    # Check if we have volume data (Yahoo Finance/Brokers lack volume for indices)
    # Require at least 20% of candles to have >0 volume to consider it valid volume data
    volume_ratio = (df['volume'] > 0).mean()
    has_volume = volume_ratio > 0.2
    if not has_volume:
        print("[WARNING] Sparse or no volume data detected. Bypassing Volume & VWAP filters for testing.")
    
    # Debug counters for CALL
    counts = {
        'total_candles': 0,
        'ema_pass': 0,
        'rsi_pass': 0,
        'macd_pass': 0,
        'vwap_pass': 0,
        'st_pass': 0,
        'adx_pass': 0,
        'vol_pass': 0,
        'smc_pass': 0,
        'candle_pass': 0
    }
    
    # 2. Signal Generation
    # 2. Vectorized Signal Generation
    score_call = pd.Series(0, index=df.index)
    score_put = pd.Series(0, index=df.index)
    
    # --- CALL Conditions ---
    # 1. EMA Trend
    c_ema_call_cross = (df['ema_9'] > df['ema_21']) & (df['ema_9'].shift(1) <= df['ema_21'].shift(1))
    ema_dist = df['ema_9'] - df['ema_21']
    c_ema_accel_call = (ema_dist > ema_dist.shift(1)) & (ema_dist > 0)
    
    score_call[c_ema_call_cross] += 25
    score_call[~c_ema_call_cross & c_ema_accel_call] += 15
    score_call[~c_ema_call_cross & ~c_ema_accel_call & (df['ema_9'] > df['ema_21'])] += 10
    
    # 2. Breakout
    c_breakout_call = (df['close'] > df['swing_high'].shift(1))
    if has_volume:
        c_breakout_call = c_breakout_call & (df['volume'] > df['volume_sma'] * 1.2)
    score_call[c_breakout_call] += 20
    
    # 3. Pullback
    c_pullback_call = (df['low'] <= df['ema_9']) & (df['close'] > df['ema_9']) & (df['close'] > df['open'])
    score_call[c_pullback_call] += 20
    
    # 4. RSI
    c_rsi_call = (df['rsi'] > df['rsi_ema']) & (df['rsi'] > 50)
    score_call[c_rsi_call] += 15
    
    # 5. MACD
    c_macd_call = (df['macd'] > df['macd_signal']) & (df['macd_hist'] > 0)
    score_call[c_macd_call] += 15
    
    # 6. VWAP
    if has_volume:
        c_vwap_call = df['close'] > df['vwap']
        score_call[c_vwap_call] += 10
    else:
        score_call += 10
        
    # 7. ADX
    adx_thresh = kwargs.get("adx_threshold", 20)
    c_adx_call = (df['adx'] > adx_thresh) & (df['plus_di'] > df['minus_di'])
    score_call[c_adx_call] += 10
    
    # 8. Volume
    if has_volume:
        c_vol_call = df['volume'] > df['volume_sma']
        score_call[c_vol_call] += 10
    else:
        score_call += 10
        
    # 9. SMC
    c_smc_call = (df['bos_bullish'].rolling(5).max() > 0) | (df['bullish_fvg'].rolling(5).max() > 0)
    score_call[c_smc_call] += 10
    
    # 10. Candle Strength
    candle_body = df['close'] - df['open']
    upper_wick = df['high'] - df['close']
    c_candle_call = (candle_body > 0) & (upper_wick < candle_body * 0.3)
    score_call[c_candle_call] += 5
    
    # --- PUT Conditions ---
    # 1. EMA Trend
    c_ema_put_cross = (df['ema_9'] < df['ema_21']) & (df['ema_9'].shift(1) >= df['ema_21'].shift(1))
    ema_dist_put = df['ema_21'] - df['ema_9']
    c_ema_accel_put = (ema_dist_put > ema_dist_put.shift(1)) & (ema_dist_put > 0)
    
    score_put[c_ema_put_cross] += 25
    score_put[~c_ema_put_cross & c_ema_accel_put] += 15
    score_put[~c_ema_put_cross & ~c_ema_accel_put & (df['ema_9'] < df['ema_21'])] += 10
    
    # 2. Breakout
    c_breakout_put = (df['close'] < df['swing_low'].shift(1))
    if has_volume:
        c_breakout_put = c_breakout_put & (df['volume'] > df['volume_sma'] * 1.2)
    score_put[c_breakout_put] += 20
    
    # 3. Pullback
    c_pullback_put = (df['high'] >= df['ema_9']) & (df['close'] < df['ema_9']) & (df['close'] < df['open'])
    score_put[c_pullback_put] += 20
    
    # 4. RSI
    c_rsi_put = (df['rsi'] < df['rsi_ema']) & (df['rsi'] < 50)
    score_put[c_rsi_put] += 15
    
    # 5. MACD
    c_macd_put = (df['macd'] < df['macd_signal']) & (df['macd_hist'] < 0)
    score_put[c_macd_put] += 15
    
    # 6. VWAP
    if has_volume:
        c_vwap_put = df['close'] < df['vwap']
        score_put[c_vwap_put] += 10
    else:
        score_put += 10
        
    # 7. ADX
    c_adx_put = (df['adx'] > 25) & (df['minus_di'] > df['plus_di'])
    score_put[c_adx_put] += 10
    
    # 8. Volume
    if has_volume:
        c_vol_put = df['volume'] > df['volume_sma']
        score_put[c_vol_put] += 10
    else:
        score_put += 10
        
    # 9. SMC
    c_smc_put = (df['bos_bearish'].rolling(5).max() > 0) | (df['bearish_fvg'].rolling(5).max() > 0)
    score_put[c_smc_put] += 10
    
    # 10. Candle Strength
    lower_wick = df['open'] - df['low']
    c_candle_put = (candle_body < 0) & (lower_wick < abs(candle_body) * 0.3)
    score_put[c_candle_put] += 5
    
    # Normalize scores
    df['call_score'] = (score_call / 140 * 100).astype(int)
    df['put_score'] = (score_put / 140 * 100).astype(int)
    
    # Dynamic Threshold
    threshold = pd.Series(75, index=df.index)
    threshold[df['adx'] > 25] = kwargs.get("score_threshold_trending", 75)
    threshold[df['adx'] < 20] = kwargs.get("score_threshold_sideways", 80)
    
    # Mandatory Filters
    mandatory_call = pd.Series(True, index=df.index)
    if kwargs.get("enable_ema_filter", True):
        mandatory_call = mandatory_call & (df['ema_9'] > df['ema_21'])
    if kwargs.get("enable_volume_filter", True) and has_volume:
        mandatory_call = mandatory_call & (df['volume'] > df['volume_sma'])
        
    mandatory_put = pd.Series(True, index=df.index)
    if kwargs.get("enable_ema_filter", True):
        mandatory_put = mandatory_put & (df['ema_9'] < df['ema_21'])
    if kwargs.get("enable_volume_filter", True) and has_volume:
        mandatory_put = mandatory_put & (df['volume'] > df['volume_sma'])
        
    # Generate Signals
    signals[(df['call_score'] >= threshold) & mandatory_call] = 1
    signals[(df['put_score'] >= threshold) & mandatory_put] = -1
    
    # Time Filters (Vectorized)
    if 'datetime' in df.columns:
        df['datetime_dt'] = pd.to_datetime(df['datetime'])
        minutes = df['datetime_dt'].dt.hour * 60 + df['datetime_dt'].dt.minute
        is_lunch = (minutes >= 690) & (minutes < 810)
        valid_time = (minutes >= 585) & (minutes < 870) & ~is_lunch
        signals[~valid_time] = 0
        
    # Custom SL calculation (Vectorized)
    sl_dist_call = df['close'] - df['swing_low']
    df['custom_sl_pct'] = 0.2 # Default min
    df.loc[(df['call_score'] >= threshold) & mandatory_call, 'custom_sl_pct'] = (sl_dist_call / df['close'] * 100).clip(lower=0.2)
    
    sl_dist_put = df['swing_high'] - df['close']
    df.loc[(df['put_score'] >= threshold) & mandatory_put, 'custom_sl_pct'] = (sl_dist_put / df['close'] * 100).clip(lower=0.2)
            
    print("\n=== [DEBUG] CALL Signal Filters Breakdown ===")
    print(f"Analyzed Candles: {counts['total_candles']}")
    for k, v in counts.items():
        if k != 'total_candles':
            pct = (v / counts['total_candles'] * 100) if counts['total_candles'] > 0 else 0
            print(f" - {k}: {v} ({pct:.1f}%)")
    print("==============================================")
                
    return signals
