import pandas as pd

def smc_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Computes basic Smart Money Concept (SMC) signals for the dataframe.
    Includes Break of Structure (BOS) and Fair Value Gaps (FVG).
    """
    df = df.copy()
    
    # 1. Fair Value Gap (FVG)
    # Bullish FVG: Low of candle 3 is higher than High of candle 1
    # Bearish FVG: High of candle 3 is lower than Low of candle 1
    high_1 = df['high'].shift(2)
    low_1 = df['low'].shift(2)
    low_3 = df['low']
    high_3 = df['high']
    
    df['bullish_fvg'] = low_3 > high_1
    df['bearish_fvg'] = high_3 < low_1
    
    # 2. Break of Structure (BOS) / Change of Character (CHOCH)
    # Simplified logic: breaking the highest high / lowest low of the last 10 periods
    rolling_high = df['high'].shift(1).rolling(window=10).max()
    rolling_low = df['low'].shift(1).rolling(window=10).min()
    
    df['bos_bullish'] = df['close'] > rolling_high
    df['bos_bearish'] = df['close'] < rolling_low
    
    return df
