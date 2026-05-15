import pandas as pd
import numpy as np

STRATEGY_NAME = "buy_the_dip"

def generate_signals(df: pd.DataFrame, **kwargs) -> pd.Series:
    """Buy the Dip / Mean Reversion Strategy."""
    signals = pd.Series(0, index=df.index)
    
    if len(df) < 20:
        return signals
        
    # Calculate Indicators
    # 1. RSI
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    df['rsi'] = 100 - (100 / (1 + rs))
    
    # 2. Swing Low/High (last 5 candles)
    df['swing_low'] = df['low'].rolling(window=5).min()
    df['swing_high'] = df['high'].rolling(window=5).max()
    
    # 3. EMA 50 for Trend Filter
    df['ema_50'] = df['close'].ewm(span=50, adjust=False).mean()
    
    # 4. Candle Patterns
    # Hammer: Small body, long lower shadow
    body = abs(df['close'] - df['open'])
    lower_shadow = df[['open', 'close']].min(axis=1) - df['low']
    upper_shadow = df['high'] - df[['open', 'close']].max(axis=1)
    df['is_hammer'] = (lower_shadow > body * 1.5) & (upper_shadow < body)
    
    # Engulfing
    df['is_bullish_engulfing'] = (df['close'] > df['open']) & (df['close'].shift() < df['open'].shift()) & (df['close'] > df['open'].shift()) & (df['open'] < df['close'].shift())
    
    # Loop to generate signals
    for i in range(5, len(df)):
        current_price = df['close'].iloc[i]
        
        # Trend Filter
        uptrend = current_price > df['ema_50'].iloc[i]
        downtrend = current_price < df['ema_50'].iloc[i]
        
        # ENTRY Condition (CALL)
        # Market was falling (RSI < 35 or price near swing low)
        falling_call = df['rsi'].iloc[i-1] < 35 or df['close'].iloc[i-1] < df['swing_low'].iloc[i-5]
        
        # Reversal Candle or RSI crossing up
        reversal_call = df['is_hammer'].iloc[i] or df['is_bullish_engulfing'].iloc[i] or (df['rsi'].iloc[i] > 30 and df['rsi'].iloc[i-1] <= 30)
        
        # ENTRY Condition (PUT)
        # Market was rising (RSI > 65 or price near swing high)
        rising_put = df['rsi'].iloc[i-1] > 65 or df['close'].iloc[i-1] > df['swing_high'].iloc[i-5]
        
        # Reversal Candle or RSI crossing down
        reversal_put = (df['close'].iloc[i] < df['open'].iloc[i] and df['close'].iloc[i-1] > df['open'].iloc[i-1]) or (df['rsi'].iloc[i] < 70 and df['rsi'].iloc[i-1] >= 70)
        
        if uptrend and falling_call and reversal_call:
            signals.iloc[i] = 1 # BUY CALL
            # Set custom SL slightly below swing low
            sl_dist = current_price - df['swing_low'].iloc[i]
            df.loc[df.index[i], 'custom_sl_pct'] = max(0.2, (sl_dist / current_price * 100) + 0.05)
            
        elif downtrend and rising_put and reversal_put:
            signals.iloc[i] = -1 # BUY PUT
            # Set custom SL slightly above swing high
            sl_dist = df['swing_high'].iloc[i] - current_price
            df.loc[df.index[i], 'custom_sl_pct'] = max(0.2, (sl_dist / current_price * 100) + 0.05)
            
    return signals
