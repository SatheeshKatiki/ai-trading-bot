import pandas as pd
import numpy as np

def get_squeeze_mask(df: pd.DataFrame, window: int = 20) -> pd.Series:
    """
    TTM Squeeze Filter.
    Returns a boolean mask where True means the market is currently in a squeeze.
    (Bollinger Bands are inside Keltner Channels).
    """
    if 'close' not in df.columns or 'high' not in df.columns or 'low' not in df.columns:
        return pd.Series(False, index=df.index)
        
    close = df['close']
    ema_20 = close.ewm(span=window, adjust=False).mean()
    
    # Bollinger Bands
    std_20 = close.rolling(window).std()
    bb_upper = ema_20 + (2 * std_20)
    bb_lower = ema_20 - (2 * std_20)
    
    # Keltner Channels
    tr_col1 = df['high'] - df['low']
    tr_col2 = (df['high'] - close.shift(1)).abs()
    tr_col3 = (df['low'] - close.shift(1)).abs()
    tr = pd.concat([tr_col1, tr_col2, tr_col3], axis=1).max(axis=1)
    
    atr_20 = tr.rolling(window).mean()
    kc_upper = ema_20 + (1.5 * atr_20)
    kc_lower = ema_20 - (1.5 * atr_20)
    
    # Squeeze is ON when BB is completely inside KC
    squeeze_on = (bb_upper < kc_upper) & (bb_lower > kc_lower)
    
    # Check if we were in a squeeze recently (last 5 bars)
    squeeze_recent = squeeze_on.rolling(5).max() > 0
    return squeeze_recent


def get_extension_mask(df: pd.DataFrame, ema_window: int = 20, threshold: float = 0.006) -> pd.Series:
    """
    EMA Extension Filter.
    Returns True if price is over-extended from the EMA.
    """
    if 'close' not in df.columns:
        return pd.Series(False, index=df.index)
        
    close = df['close']
    ema_val = close.ewm(span=ema_window, adjust=False).mean()
    
    # Distance from EMA in percentage
    ema_extension = (close - ema_val).abs() / ema_val
    return ema_extension > threshold


def get_cpr_rejection_masks(df: pd.DataFrame, proximity_threshold: float = 0.0015) -> tuple[pd.Series, pd.Series]:
    """
    CPR Rejection Filter.
    Returns (bull_reject_mask, bear_reject_mask).
    Bull reject if approaching R1/Top CPR. Bear reject if approaching S1/Bottom CPR.
    """
    if 'high' not in df.columns or 'low' not in df.columns or 'close' not in df.columns:
        return pd.Series(False, index=df.index), pd.Series(False, index=df.index)

    # Determine dates for daily grouping
    if 'datetime' in df.columns:
        dates = pd.to_datetime(df['datetime']).dt.date
    elif isinstance(df.index, pd.DatetimeIndex):
        dates = df.index.date
    else:
        return pd.Series(False, index=df.index), pd.Series(False, index=df.index)
        
    # Calculate Daily Pivots on shifted data (yesterday's OHLC determines today's CPR)
    daily_df = df.groupby(dates).agg({'high':'max', 'low':'min', 'close':'last'})
    daily_df = daily_df.shift(1)
    
    pdh = daily_df['high'].reindex(dates).values
    pdl = daily_df['low'].reindex(dates).values
    pdc = daily_df['close'].reindex(dates).values
    
    pivot = (pdh + pdl + pdc) / 3
    bc = (pdh + pdl) / 2
    tc = (pivot - bc) + pivot
    
    # Handle NaNs and 1D arrays properly
    pivot = pd.Series(pivot, index=df.index).ffill()
    bc = pd.Series(bc, index=df.index).ffill()
    tc = pd.Series(tc, index=df.index).ffill()
    pdh = pd.Series(pdh, index=df.index).ffill()
    pdl = pd.Series(pdl, index=df.index).ffill()
    
    top_cpr = pd.concat([tc, bc], axis=1).max(axis=1)
    bottom_cpr = pd.concat([tc, bc], axis=1).min(axis=1)
    
    r1 = (2 * pivot) - pdl
    s1 = (2 * pivot) - pdh
    
    close = df['close']
    
    # Reject Longs if approaching Resistance (R1 or Top CPR) from below
    bull_reject = ((r1 > close) & ((r1 - close) / close < proximity_threshold)) | \
                  ((top_cpr > close) & ((top_cpr - close) / close < proximity_threshold))
                  
    # Reject Shorts if approaching Support (S1 or Bottom CPR) from above
    bear_reject = ((close > s1) & ((close - s1) / close < proximity_threshold)) | \
                  ((close > bottom_cpr) & ((close - bottom_cpr) / close < proximity_threshold))
                  
    return bull_reject, bear_reject


def get_aggression_masks(df: pd.DataFrame, threshold: float = 0.6) -> tuple[pd.Series, pd.Series]:
    """
    Candle Aggression Filter.
    Returns (bull_reject_mask, bear_reject_mask).
    Reject if the breakout candle is weak (e.g., Doji).
    """
    if 'open' not in df.columns or 'high' not in df.columns or 'low' not in df.columns or 'close' not in df.columns:
        return pd.Series(False, index=df.index), pd.Series(False, index=df.index)
        
    high = df['high']
    low = df['low']
    close = df['close']
    
    candle_range = (high - low).replace(0, 0.00001)
    
    bull_strength = (close - low) / candle_range
    bear_strength = (high - close) / candle_range
    
    bull_reject = bull_strength < threshold
    bear_reject = bear_strength < threshold
    
    return bull_reject, bear_reject


def apply_institutional_filters(
    df: pd.DataFrame, 
    bullish: pd.Series, 
    bearish: pd.Series, 
    **kwargs
) -> tuple[pd.Series, pd.Series]:
    """
    Master function to intercept raw signals and nullify them based on UI toggles.
    """
    # Accept either boolean True or string "true" (from UI params)
    def is_true(val):
        if isinstance(val, str):
            return val.lower() == 'true'
        return bool(val)
        
    f_squeeze = is_true(kwargs.get("enable_squeeze_filter", False))
    f_extension = is_true(kwargs.get("enable_extension_filter", False))
    f_cpr = is_true(kwargs.get("enable_cpr_filter", False))
    f_aggression = is_true(kwargs.get("enable_aggression_filter", False))
    
    # Apply Squeeze
    if f_squeeze:
        squeeze_mask = get_squeeze_mask(df)
        bullish = bullish & ~squeeze_mask
        bearish = bearish & ~squeeze_mask
        
    # Apply Extension
    if f_extension:
        ext_mask = get_extension_mask(df)
        bullish = bullish & ~ext_mask
        bearish = bearish & ~ext_mask
        
    # Apply CPR
    if f_cpr:
        bull_cpr_rej, bear_cpr_rej = get_cpr_rejection_masks(df)
        bullish = bullish & ~bull_cpr_rej
        bearish = bearish & ~bear_cpr_rej
        
    # Apply Aggression
    if f_aggression:
        bull_agg_rej, bear_agg_rej = get_aggression_masks(df)
        bullish = bullish & ~bull_agg_rej
        bearish = bearish & ~bear_agg_rej
        
    return bullish, bearish
