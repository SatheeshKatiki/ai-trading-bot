"""Supertrend indicator."""
from __future__ import annotations
import pandas as pd
import numpy as np
from shared.indicators.atr import atr

def supertrend(df: pd.DataFrame, period: int = 10, multiplier: float = 3.0) -> pd.DataFrame:
    """Calculate Supertrend.

    Returns DataFrame with columns: 'supertrend', 'direction' (1 for up, -1 for down).
    """
    # Root-cause fix (found live, 2026-08-06): `atr`/`hl2`/`basic_ub`/
    # `basic_lb` used to be written onto a `df.copy()` one column at a
    # time (`df["atr"] = ...`, `df["hl2"] = ...`, ...) even though the
    # function only ever returns `supertrend`/`direction` — none of those
    # four needed to live on a DataFrame at all. Each `df["new_col"] = ...`
    # assignment calls through to pandas' `Index.insert()`, and under
    # pandas 3.0.3 that per-call cost was observed to become catastrophic
    # in a long-running process calling this function ~5x/second (`py-spy
    # dump` caught the live engine stuck inside exactly this call chain
    # for 20+ minutes at 97-100% CPU). Keeping every intermediate as a
    # plain Series/array and only ever constructing the final 2-column
    # result once, at the very end, avoids the same class of bug — see
    # shared/ai/features.py's docstring and
    # docs/paper_trading_validation/anomaly_log.md's 2026-08-06 entries
    # for the full incident this was root-caused from.
    high = df["high"]
    low = df["low"]
    close = df["close"]

    atr_series = atr(df, window=period)
    hl2 = (high + low) / 2
    basic_ub_series = hl2 + (multiplier * atr_series)
    basic_lb_series = hl2 - (multiplier * atr_series)

    # Initialize bands
    final_ub = np.zeros(len(df))
    final_lb = np.zeros(len(df))
    supertrend_arr = np.zeros(len(df))
    direction = np.ones(len(df), dtype=int)

    basic_ub = basic_ub_series.to_numpy()
    basic_lb = basic_lb_series.to_numpy()
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
                
    return pd.DataFrame(
        {"supertrend": supertrend_arr, "direction": direction},
        index=df.index,
    )
