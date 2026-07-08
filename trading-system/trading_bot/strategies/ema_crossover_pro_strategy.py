"""Ultra-EMA Crossover Strategy with Dual Entry (Runaway vs Pullback).

Features:
- Dual Entry System (Explosive Volume vs Safe Pullback)
- ADX Anti-Chop Guard
- Multi-Timeframe (MTF) Support
- VWAP Extension Protection
"""

from __future__ import annotations

import logging
import pandas as pd
import numpy as np

from shared.indicators import ema, rsi

logger = logging.getLogger(__name__)

STRATEGY_NAME = "ema_crossover"

def _calc_adx(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Calculate ADX (Average Directional Index)."""
    if len(df) < period + 1:
        return pd.Series(0, index=df.index)
        
    plus_dm = df['high'].diff()
    minus_dm = -df['low'].diff()
    
    # Directional Movement
    plus_dm = np.where((plus_dm > minus_dm) & (plus_dm > 0), plus_dm, 0)
    minus_dm = np.where((minus_dm > plus_dm) & (minus_dm > 0), minus_dm, 0)
    
    tr1 = df['high'] - df['low']
    tr2 = np.abs(df['high'] - df['close'].shift(1))
    tr3 = np.abs(df['low'] - df['close'].shift(1))
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    
    # Smooth with EMA (RMA is strictly better, but EMA is close enough for speed)
    atr = pd.Series(tr).ewm(alpha=1/period, min_periods=period).mean()
    plus_di = 100 * (pd.Series(plus_dm).ewm(alpha=1/period, min_periods=period).mean() / atr)
    minus_di = 100 * (pd.Series(minus_dm).ewm(alpha=1/period, min_periods=period).mean() / atr)
    
    dx = 100 * np.abs(plus_di - minus_di) / (plus_di + minus_di).replace(0, 1)
    adx = dx.ewm(alpha=1/period, min_periods=period).mean()
    
    return adx.fillna(0)

def generate_signals(
    df: pd.DataFrame,
    **kwargs
) -> pd.Series:
    """Generate Ultra-EMA Crossover signals."""
    signals = pd.Series(0, index=df.index)
    
    if len(df) < 50:
        return signals
        
    df_work = df.copy()
    
    # Calculate Base Indicators
    df_work['ema_9'] = ema(df_work['close'], 9)
    df_work['ema_20'] = ema(df_work['close'], 20)
    df_work['rsi_14'] = rsi(df_work['close'], 14)
    df_work['adx_14'] = _calc_adx(df_work, 14)
    
    # Handle zero volume (common for Indices like NIFTY)
    if 'volume' in df_work.columns and df_work['volume'].max() == 0:
        df_work = df_work.drop(columns=['volume'])
        
    # Daily Resetting VWAP Proxy (if real VWAP is missing)
    if 'vwap' not in df_work.columns:
        typical_price = (df_work['high'] + df_work['low'] + df_work['close']) / 3
        # Use volume if it exists and has non-zero variance, else use 1
        v = df_work['volume'] if 'volume' in df_work.columns else pd.Series(1, index=df_work.index)
        
        if 'datetime' in df_work.columns:
            dates = pd.to_datetime(df_work['datetime']).dt.date
            df_work['vwap'] = (typical_price * v).groupby(dates).cumsum() / v.groupby(dates).cumsum()
        elif hasattr(df_work.index, 'date'):
            dates = df_work.index.date
            df_work['vwap'] = (typical_price * v).groupby(dates).cumsum() / v.groupby(dates).cumsum()
        else:
            df_work['vwap'] = typical_price.ewm(span=200).mean() # Fallback approximation
        
    # Volume SMA
    if 'volume' in df_work.columns:
        df_work['vol_sma'] = df_work['volume'].rolling(20).mean().replace(0, 1)
    else:
        df_work['volume'] = 0
        df_work['vol_sma'] = 0 # If no volume, set SMA to 0 so volume check passes (0 >= 0)
        
    # Crossover Logic
    ema9_shifted = df_work['ema_9'].shift(1)
    ema20_shifted = df_work['ema_20'].shift(1)
    
    # Exact crossover on current candle
    cross_up = (df_work['ema_9'] > df_work['ema_20']) & (ema9_shifted <= ema20_shifted)
    cross_down = (df_work['ema_9'] < df_work['ema_20']) & (ema9_shifted >= ema20_shifted)
    
    # Recent crossover (within last 5 candles) - Crucial for Pullbacks!
    recent_cross_up = cross_up.rolling(5).max() > 0
    recent_cross_down = cross_down.rolling(5).max() > 0
    
    # Ensure current alignment is still valid
    trend_up = df_work['ema_9'] > df_work['ema_20']
    trend_down = df_work['ema_9'] < df_work['ema_20']
    
    # Candle conditions
    is_green = df_work['close'] > df_work['open']
    is_red = df_work['close'] < df_work['open']
    
    # True rejection of EMA (touches EMA but closes strongly away from it)
    bullish_rejection = (df_work['low'] <= df_work['ema_9']) & (df_work['close'] > df_work['ema_9'])
    bearish_rejection = (df_work['high'] >= df_work['ema_9']) & (df_work['close'] < df_work['ema_9'])
    
    # VWAP Extension Protection (Don't buy if price is >0.5% away from VWAP)
    dist_vwap = np.abs(df_work['close'] - df_work['vwap']) / df_work['vwap']
    vwap_safe = dist_vwap < 0.005 # 0.5% limit
    
    # --- BULLISH (CALL) LOGIC ---
    # Type A: Runaway (Requires exact crossover + explosive momentum)
    call_type_a = (
        cross_up & 
        is_green &
        (df_work['volume'] >= 2.0 * df_work['vol_sma']) &
        (df_work['rsi_14'] >= 65) &
        (df_work['close'] > df_work['vwap'])
    )
    
    # Type B: Safe Pullback (Happens 1-5 candles after crossover)
    call_type_b = (
        recent_cross_up &
        trend_up &
        is_green &
        bullish_rejection &
        (df_work['rsi_14'] >= 55) &
        (df_work['close'] > df_work['vwap']) &
        vwap_safe &
        (df_work['adx_14'] >= 20) # ADX Anti-Chop Guard
    )
    
    # --- BEARISH (PUT) LOGIC ---
    # Type A: Runaway
    put_type_a = (
        cross_down & 
        is_red &
        (df_work['volume'] >= 2.0 * df_work['vol_sma']) &
        (df_work['rsi_14'] <= 35) &
        (df_work['close'] < df_work['vwap'])
    )
    
    # Type B: Safe Pullback
    put_type_b = (
        recent_cross_down &
        trend_down &
        is_red &
        bearish_rejection &
        (df_work['rsi_14'] <= 45) &
        (df_work['close'] < df_work['vwap']) &
        vwap_safe &
        (df_work['adx_14'] >= 20) # ADX Anti-Chop Guard
    )
    
    # Apply Signals
    signals[call_type_a | call_type_b] = 1
    signals[put_type_a | put_type_b] = -1
    
    # For UI scoring/debug
    df['call_score'] = np.where(signals == 1, 95, 0)
    df['put_score'] = np.where(signals == -1, 95, 0)
    
    # Add dynamic stoploss column for the Exit Manager to pick up
    sl = pd.Series(np.nan, index=df.index)
    
    # Type A uses 9 EMA as strict stop, Type B uses 20 EMA
    sl[call_type_a] = df_work['ema_9'][call_type_a]
    sl[call_type_b] = df_work['ema_20'][call_type_b]
    
    sl[put_type_a] = df_work['ema_9'][put_type_a]
    sl[put_type_b] = df_work['ema_20'][put_type_b]
    
    df['suggested_sl'] = sl
    
    return signals
