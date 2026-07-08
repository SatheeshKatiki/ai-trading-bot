"""
Meta-Agent AI Swarm (Portfolio Manager).

This is a multi-agent architecture that polls signals from 5 technical strategies
and 1 Fundamental (RAG Sentiment) model. It requires a consensus (score >= 3 or <= -3)
to trigger a trade execution, providing hedge-fund level false positive rejection.
"""

from __future__ import annotations

import logging
import pandas as pd

from trading_bot.strategies.registry import registry
from shared.sentiment import get_current_sentiment

logger = logging.getLogger(__name__)

STRATEGY_NAME = "meta_agent_swarm"

def generate_signals(df: pd.DataFrame, **kwargs) -> pd.Series:
    """Generate trade signals based on Swarm Consensus."""
    
    # The 5 core technical brains
    agents = [
        "advanced_ai", 
        "institutional_momentum", 
        "ema_crossover", 
        "ema_rsi", 
        "enhanced_ai"
    ]
    
    # Initialize voting ledger
    votes_df = pd.DataFrame(index=df.index)
    votes_df['total_score'] = 0.0
    
    # 1. Tally Technical Agents
    for agent in agents:
        try:
            if agent in registry._strategies:
                signal = registry._strategies[agent](df, **kwargs)
                votes_df[agent] = signal
                votes_df['total_score'] += signal.fillna(0)
            else:
                logger.warning(f"Meta-Agent: Sub-agent '{agent}' not found in registry.")
        except Exception as e:
            logger.error(f"Meta-Agent: Error executing sub-agent '{agent}': {e}")
            
    # 2. Tally Fundamental RAG (Sentiment) Agent
    try:
        import datetime
        is_backtest = False
        if not df.empty:
            last_idx = df.index[-1]
            try:
                if isinstance(last_idx, pd.Timestamp):
                    last_dt = last_idx.to_pydatetime()
                else:
                    last_dt = pd.to_datetime(last_idx).to_pydatetime()
                    
                if last_dt.tzinfo is not None:
                    now = datetime.datetime.now(datetime.timezone.utc)
                else:
                    now = datetime.datetime.now()
                    
                diff = now - last_dt
                if diff.total_seconds() > 86400:
                    is_backtest = True
            except Exception:
                pass
                
        if is_backtest:
            logger.debug("Meta-Agent: Backtest mode detected. Disabling Live RAG Sentiment to prevent Look-Ahead Bias.")
            votes_df['rag_sentiment'] = 0
        else:
            sentiment = get_current_sentiment()
            score = sentiment.get("score", 0.0)
            
            # Determine RAG Vote based on VADER compound polarity
            rag_vote = 0
            if score > 0.1:
                rag_vote = 1
            elif score < -0.1:
                rag_vote = -1
                
            votes_df['rag_sentiment'] = rag_vote
            votes_df['total_score'] += rag_vote
        
    except Exception as e:
        logger.error(f"Meta-Agent: Error fetching RAG sentiment: {e}")
        
    # 3. Calculate Consensus
    # Swarm logic: Needs at least a net sum of 3 votes to execute
    final_signal = pd.Series(0, index=df.index, dtype=int)
    final_signal[votes_df['total_score'] >= 3] = 1
    final_signal[votes_df['total_score'] <= -3] = -1
    
    # 4. Telemetry logging for the latest candle
    if not final_signal.empty:
        latest = final_signal.iloc[-1]
        score = votes_df['total_score'].iloc[-1]
        if latest != 0:
            logger.info(f"[Meta-Agent Swarm] Consensus Reached! Action: {latest}, Net Score: {score}/6")
        
    return final_signal
