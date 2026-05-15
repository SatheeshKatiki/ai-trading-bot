"""Supertrend indicator."""
from __future__ import annotations
import pandas as pd
import numpy as np
from shared.indicators.atr import atr

def supertrend(df: pd.DataFrame, period: int = 10, multiplier: float = 3.0) -> pd.DataFrame:
    """Calculate Supertrend.
    
    Returns DataFrame with columns: 'supertrend', 'direction' (1 for up, -1 for down).
    """
    df = df.copy()
    high = df["high"]
    low = df["low"]
    close = df["close"]
    
    # Calculate ATR
    df["atr"] = atr(df, window=period)
    
    # Calculate Basic Bands
    df["hl2"] = (high + low) / 2
    df["basic_ub"] = df["hl2"] + (multiplier * df["atr"])
    df["basic_lb"] = df["hl2"] - (multiplier * df["atr"])
    
    # Initialize bands
    final_ub = np.zeros(len(df))
    final_lb = np.zeros(len(df))
    supertrend_arr = np.zeros(len(df))
    direction = np.ones(len(df), dtype=int)
    
    basic_ub = df["basic_ub"].to_numpy()
    basic_lb = df["basic_lb"].to_numpy()
    close_arr = close.to_numpy()
    
    # Iterate to calculate final bands and direction
    for i in range(1, len(df)):
        # Final Upper Band
        if basic_ub[i] < final_ub[i-1] or close_arr[i-1] > final_ub[i-1]:
            final_ub[i] = basic_ub[i]
        else:
            final_ub[i] = final_ub[i-1]
            
        # Final Lower Band
        if basic_lb[i] > final_lb[i-1] or close_arr[i-1] < final_lb[i-1]:
            final_lb[i] = basic_lb[i]
        else:
            final_lb[i] = final_lb[i-1]
            
        # Supertrend and Direction
        if supertrend_arr[i-1] == final_ub[i-1]:
            if close_arr[i] > final_ub[i]:
                supertrend_arr[i] = final_lb[i]
                direction[i] = 1
            else:
                supertrend_arr[i] = final_ub[i]
                direction[i] = -1
        else:
            if close_arr[i] < final_lb[i]:
                supertrend_arr[i] = final_ub[i]
                direction[i] = -1
            else:
                supertrend_arr[i] = final_lb[i]
                direction[i] = 1
                
    df["supertrend"] = supertrend_arr
    df["direction"] = direction
    return df[["supertrend", "direction"]]
