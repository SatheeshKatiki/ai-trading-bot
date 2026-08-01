import logging
import numpy as np
import pandas as pd
from typing import Dict, Any, List

# Only import if sb3_contrib is installed to prevent crashes on systems without it
try:
    from sb3_contrib import RecurrentPPO
    HAS_SB3 = True
except ImportError:
    HAS_SB3 = False

logger = logging.getLogger(__name__)

class DRLStrategy:
    """
    Deep Reinforcement Learning (DRL) Strategy using PPO.
    """
    
    def __init__(self, model_path: str = "drl/best_model"):
        self.name = "drl_strategy"
        self.model_path = model_path
        self.model = None
        
        if HAS_SB3:
            try:
                self.model = RecurrentPPO.load(self.model_path)
                logger.info(f"Successfully loaded DRL LSTM model from {self.model_path}")
            except Exception as e:
                logger.error(f"Failed to load DRL LSTM model from {self.model_path}: {e}")

        self.current_position = 0 
        self.entry_price = 0.0
        self.lstm_states = None
        self.episode_starts = np.zeros((1,), dtype=bool)

    def compute_features(self, df: pd.DataFrame) -> np.ndarray:
        if len(df) < 14:
            return None
        latest = df.iloc[-1]
        try:
            features = np.array([
                latest.get('rsi', 50),
                latest.get('macd_hist', 0),
                latest.get('atr', 0),
                latest.get('vol_change', 0)
            ], dtype=np.float32)
        except KeyError:
            return None
        return features

    def on_tick(self, df: pd.DataFrame) -> int:
        if self.model is None:
            return 0
            
        features = self.compute_features(df)
        if features is None:
            return 0
            
        profit_pct = 0.0

        obs = np.append(features, [self.current_position, profit_pct]).astype(np.float32)
        
        action, self.lstm_states = self.model.predict(
            obs, 
            state=self.lstm_states, 
            episode_start=self.episode_starts,
            deterministic=True
        )
        
        if isinstance(action, np.ndarray):
            action = action.item()
            
        if action == 1:
            return 1
        elif action == 2:
            return -1
        return 0

_drl_instance = None

def generate_signals(df: pd.DataFrame, **kwargs) -> pd.Series:
    global _drl_instance
    if _drl_instance is None:
        import os
        model_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "best_model.zip")
        _drl_instance = DRLStrategy(model_path=model_path)
    
    signals = pd.Series(0, index=df.index, dtype=int)
    
    if not HAS_SB3 or _drl_instance.model is None:
        return signals
        
    for i in range(len(df)):
        if i < 14:
            continue
        # Bound memory size to prevent RAM leak during long live sessions
        sub_df = df.iloc[max(0, i - 60):i+1]
        sig = _drl_instance.on_tick(sub_df)
        signals.iloc[i] = sig
                
    return signals
