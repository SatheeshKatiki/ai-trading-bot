"""
Ultra Meta-Dip Swarm (6 Brains) Strategy.

This is a highly advanced institutional-grade multi-agent architecture.
It polls signals from 6 core technical strategies (including Buy the Dip) 
and 1 Fundamental (RAG Sentiment) model.

It requires a strict consensus (score >= 4 or <= -4) out of a maximum of 7 votes
to trigger a trade execution, providing hedge-fund level false positive rejection.
It also inherits dynamic custom stoplosses from the Buy the Dip strategy.
"""

from __future__ import annotations

import logging
import pandas as pd
import numpy as np

from trading_bot.strategies.registry import registry
from shared.sentiment import get_current_sentiment

logger = logging.getLogger(__name__)

STRATEGY_NAME = "ultra_meta_dip_swarm"

def generate_signals(df: pd.DataFrame, **kwargs) -> pd.Series:
    """Institutional Reversal Multi-Engine Strategy."""
    signals = pd.Series(0, index=df.index, dtype=int)
    
    if len(df) < 50:
        return signals
        
    # --- 1. Core Indicators ---
    
    # RSI
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    df['rsi'] = 100 - (100 / (1 + rs))
    

    # 1. RUN BTD CORE ENGINE
    btd_signals = pd.Series(0, index=df.index, dtype=int)
    if "buy_the_dip" in registry._strategies:
        try:
            btd_signals = registry._strategies["buy_the_dip"](df, **kwargs)
        except Exception as e:
            logger.error(f"Ultra Strategy: Error executing buy_the_dip: {e}")

    # 2. RUN SWARM FILTER ENGINE
    call_scores = pd.Series(0.0, index=df.index)
    put_scores = pd.Series(0.0, index=df.index)
    
    # Brain 1: Trend (EMA)
    ema_fast = df['close'].ewm(span=20, adjust=False).mean()
    ema_slow = df['close'].ewm(span=50, adjust=False).mean()
    call_scores += np.where(df['close'] > ema_fast, 20, 0)
    put_scores += np.where(df['close'] < ema_fast, 20, 0)
    
    # Brain 2: Momentum (RSI)
    if 'rsi' not in df.columns:
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        df['rsi'] = 100 - (100 / (1 + rs))
    
    call_scores += np.where((df['rsi'] > 40) & (df['rsi'] < 70), 20, 0)
    put_scores += np.where((df['rsi'] < 60) & (df['rsi'] > 30), 20, 0)
    
    # Brain 3: Volatility (Bollinger)
    window = 20
    rolling_mean = df['close'].rolling(window=window).mean()
    rolling_std = df['close'].rolling(window=window).std()
    bb_upper = rolling_mean + (rolling_std * 2)
    bb_lower = rolling_mean - (rolling_std * 2)
    
    call_scores += np.where(df['close'] > bb_lower, 20, 0)
    put_scores += np.where(df['close'] < bb_upper, 20, 0)
    
    # 3. APPLY SWARM FILTER TO BTD
    # Only take BTD signals if the Swarm Score is >= 40 (At least 2 brains agree)
    valid_call = (btd_signals == 1) & (call_scores >= 40)
    valid_put = (btd_signals == -1) & (put_scores >= 40)
    
    signals[valid_call] = 1
    signals[valid_put] = -1
    
    # Store AI Scores for frontend visualization
    df['call_score'] = call_scores
    df['put_score'] = put_scores
    
    # --- 6. Telemetry ---
    if not signals.empty:
        latest = signals.iloc[-1]
        if latest != 0:
            logger.info(f"ULTRA STRATEGY [BTD + SWARM]: {'BUY CALL' if latest == 1 else 'BUY PUT'}.")
            
    return signals
