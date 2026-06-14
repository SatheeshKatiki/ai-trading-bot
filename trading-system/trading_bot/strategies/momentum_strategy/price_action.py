import pandas as pd
import numpy as np

class CompressionExpansionDetector:
    """
    Phase 4: Compression -> Expansion Detection
    Identifies periods of low volatility (compression) followed by sudden expansion.
    Used as an additional confidence layer, not a standalone entry.
    """
    def __init__(self, atr_short_period=14, atr_long_period=50):
        self.atr_short_period = atr_short_period
        self.atr_long_period = atr_long_period

    def detect(self, df: pd.DataFrame, idx: int) -> bool:
        """Returns True if the current bar at idx is an expansion following a compression."""
        if idx < self.atr_long_period + 5:
            return False
            
        high = df['high']
        low = df['low']
        close = df['close']
        volume = df['volume'] if 'volume' in df.columns else None

        # True Range
        tr = pd.concat([high - low, abs(high - close.shift()), abs(low - close.shift())], axis=1).max(axis=1)
        
        # We need ATRs up to the *previous* bar to define compression
        atr_short = tr.rolling(window=self.atr_short_period).mean()
        atr_long = tr.rolling(window=self.atr_long_period).mean()

        prev_atr_short = atr_short.iloc[idx-1]
        prev_atr_long = atr_long.iloc[idx-1]
        
        # 1. ATR Compression: Short-term ATR is significantly lower than Long-term ATR
        is_atr_compressed = prev_atr_short < (prev_atr_long * 0.8)

        # 2. Volume Compression (Optional): Previous volume was below average
        is_vol_compressed = True
        if volume is not None:
            vol_sma = volume.rolling(20).mean()
            prev_vol = volume.iloc[idx-1]
            prev_vol_sma = vol_sma.iloc[idx-1]
            is_vol_compressed = prev_vol < prev_vol_sma

        # 3. Current Bar Expansion: Current TR is larger than recent ATR
        current_tr = tr.iloc[idx]
        is_expanding = current_tr > (prev_atr_short * 1.5)

        return is_atr_compressed and is_vol_compressed and is_expanding


class LiquiditySweepDetector:
    """
    Phase 5: Liquidity Sweep Detection
    Detects if the market recently swept a major swing high/low (stop hunt) before reversing into our breakout direction.
    """
    def __init__(self, swing_lookback=20):
        self.swing_lookback = swing_lookback

    def detect(self, df: pd.DataFrame, idx: int, signal_dir: int) -> bool:
        """
        Returns True if a liquidity sweep occurred opposite to our signal direction 
        in the recent `swing_lookback` bars.
        """
        if idx < self.swing_lookback * 2:
            return False

        # Look at the window *before* the current breakout
        window = df.iloc[max(0, idx - self.swing_lookback) : idx]
        
        if len(window) < 5:
            return False

        if signal_dir == 1:
            # We are going LONG. We look for a recent liquidity sweep of a Swing LOW.
            # A sweep means price dropped below a previous swing low, but closed above it.
            
            # Find the lowest low in the window before the last 5 bars of the window
            earlier_window = window.iloc[:-5]
            if len(earlier_window) == 0:
                return False
                
            swing_low = earlier_window['low'].min()
            
            # Check the recent 5 bars inside the window for a sweep
            recent_window = window.iloc[-5:]
            
            # Did it wick below the swing low but close above it?
            sweep_occurred = False
            for _, row in recent_window.iterrows():
                if row['low'] < swing_low and row['close'] > swing_low:
                    sweep_occurred = True
                    break
                    
            return sweep_occurred

        elif signal_dir == -1:
            # We are going SHORT. We look for a recent liquidity sweep of a Swing HIGH.
            earlier_window = window.iloc[:-5]
            if len(earlier_window) == 0:
                return False
                
            swing_high = earlier_window['high'].max()
            
            recent_window = window.iloc[-5:]
            sweep_occurred = False
            for _, row in recent_window.iterrows():
                if row['high'] > swing_high and row['close'] < swing_high:
                    sweep_occurred = True
                    break
                    
            return sweep_occurred

        return False
