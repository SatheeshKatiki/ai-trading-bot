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
    
    # Check if we have volume data (Yahoo Finance lacks volume for indices)
    has_volume = df['volume'].sum() > 0
    if not has_volume:
        print("[WARNING] No volume data detected (common with Yahoo Finance NIFTY). Bypassing Volume & VWAP filters for testing.")
    
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
    for i in range(2, len(df)):
        if pd.isna(df['ema_21'].iloc[i]) or pd.isna(df['adx'].iloc[i]):
            continue
            
        # Time Filter: No entries before 09:30 AM and after 03:00 PM
        # Also Lunch Break (12:00 to 13:30)
        time_str = "00:00"
        if 'datetime' in df.columns:
            time_str = df['datetime'].iloc[i].split(' ')[1][:5]
        else:
            current_time_str = str(df.index[i])
            if ' ' in current_time_str:
                time_str = current_time_str.split(' ')[1][:5]
            else:
                time_str = current_time_str[:5]
                
        try:
            parts = time_str.split(':')
            minutes = int(parts[0]) * 60 + int(parts[1])
            
            # Strict Time Filters:
            # 09:45 = 585 minutes
            # 11:30 = 690 minutes
            # 13:30 = 810 minutes
            # 14:30 = 870 minutes
            
            is_lunch = (minutes >= 690 and minutes < 810)
            
            # Only trade between 09:45 AM and 02:30 PM, and skip lunch!
            if minutes < 585 or minutes >= 870 or is_lunch:
                continue
        except Exception as e:
            # If parsing fails, default to skip just to be safe
            continue
            
        counts['total_candles'] += 1
            
        close = df['close'].iloc[i]
        open_p = df['open'].iloc[i]
        high = df['high'].iloc[i]
        low = df['low'].iloc[i]
        
        # Conditions for CALL (CE)
        # 1. Mandatory Conditions (Must pass if enabled)
        mandatory_call = True
        if kwargs.get("enable_ema_filter", True):
            mandatory_call = mandatory_call and (df['ema_9'].iloc[i] > df['ema_21'].iloc[i])
        if kwargs.get("enable_volume_filter", True):
            mandatory_call = mandatory_call and (df['volume'].iloc[i] > df['volume_sma'].iloc[i])
            
        # 2. Scoring Components
        score_call = 0
        
        # EMA Trend / Crossover (25 points max)
        c_ema_call = (df['ema_9'].iloc[i] > df['ema_21'].iloc[i]) and (df['ema_9'].iloc[i-1] <= df['ema_21'].iloc[i-1])
        ema_dist = df['ema_9'].iloc[i] - df['ema_21'].iloc[i]
        ema_dist_prev = df['ema_9'].iloc[i-1] - df['ema_21'].iloc[i-1]
        c_ema_accel_call = ema_dist > ema_dist_prev and ema_dist > 0
        
        if c_ema_call: score_call += 25
        elif c_ema_accel_call: score_call += 15 # Accelerating
        elif df['ema_9'].iloc[i] > df['ema_21'].iloc[i]: score_call += 10 # State only
        
        # Breakout Confirmation (20 points)
        c_breakout_call = (close > df['swing_high'].iloc[i-1]) and (df['volume'].iloc[i] > df['volume_sma'].iloc[i] * 1.2) if has_volume else (close > df['swing_high'].iloc[i-1])
        if c_breakout_call: score_call += 20
        
        # Pullback Continuation (20 points)
        c_pullback_call = (low <= df['ema_9'].iloc[i]) and (close > df['ema_9'].iloc[i]) and (close > open_p)
        if c_pullback_call: score_call += 20
        
        # RSI Momentum (15 points)
        c_rsi_call = (df['rsi'].iloc[i] > df['rsi_ema'].iloc[i]) and (df['rsi'].iloc[i] > 50)
        if c_rsi_call: score_call += 15
        
        # MACD Momentum (15 points)
        c_macd_call = (df['macd'].iloc[i] > df['macd_signal'].iloc[i]) and (df['macd_hist'].iloc[i] > 0)
        if c_macd_call: score_call += 15
        
        # VWAP Alignment (10 points)
        c_vwap_call = (close > df['vwap'].iloc[i]) if has_volume else True
        if c_vwap_call: score_call += 10
        
        # ADX Strength (10 points)
        adx_thresh = kwargs.get("adx_threshold", 20)
        c_adx_call = (df['adx'].iloc[i] > adx_thresh) and (df['plus_di'].iloc[i] > df['minus_di'].iloc[i])
        if c_adx_call: score_call += 10
        
        # Volume Confirmation (10 points)
        c_vol_call = (df['volume'].iloc[i] > df['volume_sma'].iloc[i]) if has_volume else True
        if c_vol_call: score_call += 10
        
        # SMC Confirmation (10 points) - Look back 5 candles for footprint
        lookback = 5
        start_idx = max(0, i - lookback)
        c_smc_call = df['bos_bullish'].iloc[start_idx:i+1].any() or df['bullish_fvg'].iloc[start_idx:i+1].any()
        if c_smc_call: score_call += 10
        
        # Candle Strength (5 points)
        candle_body = close - open_p
        upper_wick = high - close
        c_candle_call = candle_body > 0 and (upper_wick < candle_body * 0.3)
        if c_candle_call: score_call += 5
        
        # -------------------------------------------------------------------
        # Conditions for PUT (PE)
        # 1. Mandatory Conditions
        mandatory_put = True
        if kwargs.get("enable_ema_filter", True):
            mandatory_put = mandatory_put and (df['ema_9'].iloc[i] < df['ema_21'].iloc[i])
        if kwargs.get("enable_volume_filter", True):
            mandatory_put = mandatory_put and (df['volume'].iloc[i] > df['volume_sma'].iloc[i])
            
        # 2. Scoring Components
        score_put = 0
        
        # EMA Trend / Crossover (25 points max)
        c_ema_put = (df['ema_9'].iloc[i] < df['ema_21'].iloc[i]) and (df['ema_9'].iloc[i-1] >= df['ema_21'].iloc[i-1])
        ema_dist_put = df['ema_21'].iloc[i] - df['ema_9'].iloc[i]
        ema_dist_prev_put = df['ema_21'].iloc[i-1] - df['ema_9'].iloc[i-1]
        c_ema_accel_put = ema_dist_put > ema_dist_prev_put and ema_dist_put > 0
        
        if c_ema_put: score_put += 25
        elif c_ema_accel_put: score_put += 15 # Accelerating
        elif df['ema_9'].iloc[i] < df['ema_21'].iloc[i]: score_put += 10 # State only
        
        # Breakout Confirmation (20 points)
        c_breakout_put = (close < df['swing_low'].iloc[i-1]) and (df['volume'].iloc[i] > df['volume_sma'].iloc[i] * 1.2) if has_volume else (close < df['swing_low'].iloc[i-1])
        if c_breakout_put: score_put += 20
        
        # Pullback Continuation (20 points)
        c_pullback_put = (high >= df['ema_9'].iloc[i]) and (close < df['ema_9'].iloc[i]) and (close < open_p)
        if c_pullback_put: score_put += 20
        
        # RSI Momentum (15 points)
        c_rsi_put = (df['rsi'].iloc[i] < df['rsi_ema'].iloc[i]) and (df['rsi'].iloc[i] < 50)
        if c_rsi_put: score_put += 15
        
        # MACD Momentum (15 points)
        c_macd_put = (df['macd'].iloc[i] < df['macd_signal'].iloc[i]) and (df['macd_hist'].iloc[i] < 0)
        if c_macd_put: score_put += 15
        
        # VWAP Alignment (10 points)
        c_vwap_put = (close < df['vwap'].iloc[i]) if has_volume else True
        if c_vwap_put: score_put += 10
        
        # ADX Strength (10 points)
        c_adx_put = (df['adx'].iloc[i] > 25) and (df['minus_di'].iloc[i] > df['plus_di'].iloc[i])
        if c_adx_put: score_put += 10
        
        # Volume Confirmation (10 points)
        c_vol_put = (df['volume'].iloc[i] > df['volume_sma'].iloc[i]) if has_volume else True
        if c_vol_put: score_put += 10
        
        # SMC Confirmation (10 points) - Look back 5 candles for footprint
        c_smc_put = df['bos_bearish'].iloc[start_idx:i+1].any() or df['bearish_fvg'].iloc[start_idx:i+1].any()
        if c_smc_put: score_put += 10
        
        # Candle Strength (5 points)
        lower_wick = open_p - low
        c_candle_put = candle_body < 0 and (lower_wick < abs(candle_body) * 0.3)
        if c_candle_put: score_put += 5
        
        # Normalize scores to 100 (Total possible points was 140)
        score_call = int((score_call / 140) * 100)
        score_put = int((score_put / 140) * 100)
        
        # Market Regime Detection & Adaptive Thresholds
        adx_val = df['adx'].iloc[i]
        if adx_val > 25:
            # Trending market: Use baseline threshold (no more 65)
            threshold = kwargs.get("score_threshold_trending", 75)
        elif adx_val < 20:
            # Sideways market: Be more defensive
            threshold = kwargs.get("score_threshold_sideways", 80)
        else:
            # Normal market
            threshold = kwargs.get("score_threshold", 75)
            
        # Set custom SL based on swings if entering
        if score_call >= threshold and mandatory_call:
            sl_dist = close - df['swing_low'].iloc[i]
            df.loc[df.index[i], 'custom_sl_pct'] = max(0.2, (sl_dist / close * 100))
        elif score_put >= threshold and mandatory_put:
            sl_dist = df['swing_high'].iloc[i] - close
            df.loc[df.index[i], 'custom_sl_pct'] = max(0.2, (sl_dist / close * 100))
        
        # Save scores for analytics
        df.loc[df.index[i], 'call_score'] = score_call
        df.loc[df.index[i], 'put_score'] = score_put
        
        # Generate Signals
        if score_call >= threshold and mandatory_call:
            signals.iloc[i] = 1
        elif score_put >= threshold and mandatory_put:
            signals.iloc[i] = -1
        
        # End of loop iteration
        pass
            
    print("\n=== [DEBUG] CALL Signal Filters Breakdown ===")
    print(f"Analyzed Candles: {counts['total_candles']}")
    for k, v in counts.items():
        if k != 'total_candles':
            pct = (v / counts['total_candles'] * 100) if counts['total_candles'] > 0 else 0
            print(f" - {k}: {v} ({pct:.1f}%)")
    print("==============================================")
                
    return signals
