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
    df["final_ub"] = 0.0
    df["final_lb"] = 0.0
    df["supertrend"] = 0.0
    df["direction"] = 1
    
    # Iterate to calculate final bands and direction
    for i in range(1, len(df)):
        # Final Upper Band
        if df["basic_ub"].iloc[i] < df["final_ub"].iloc[i-1] or close.iloc[i-1] > df["final_ub"].iloc[i-1]:
            df.loc[df.index[i], "final_ub"] = df["basic_ub"].iloc[i]
        else:
            df.loc[df.index[i], "final_ub"] = df["final_ub"].iloc[i-1]
            
        # Final Lower Band
        if df["basic_lb"].iloc[i] > df["final_lb"].iloc[i-1] or close.iloc[i-1] < df["final_lb"].iloc[i-1]:
            df.loc[df.index[i], "final_lb"] = df["basic_lb"].iloc[i]
        else:
            df.loc[df.index[i], "final_lb"] = df["final_lb"].iloc[i-1]
            
        # Supertrend and Direction
        if df["supertrend"].iloc[i-1] == df["final_ub"].iloc[i-1]:
            if close.iloc[i] > df["final_ub"].iloc[i]:
                df.loc[df.index[i], "supertrend"] = df["final_lb"].iloc[i]
                df.loc[df.index[i], "direction"] = 1
            else:
                df.loc[df.index[i], "supertrend"] = df["final_ub"].iloc[i]
                df.loc[df.index[i], "direction"] = -1
        else:
            if close.iloc[i] < df["final_lb"].iloc[i]:
                df.loc[df.index[i], "supertrend"] = df["final_ub"].iloc[i]
                df.loc[df.index[i], "direction"] = -1
            else:
                df.loc[df.index[i], "supertrend"] = df["final_lb"].iloc[i]
                df.loc[df.index[i], "direction"] = 1
                
    return df[["supertrend", "direction"]]
