import logging
import numpy as np
import pandas as pd
from typing import Dict, Any, List

from shared.state import BaseStrategy, StrategySignal

# Only import if stable_baselines3 is installed to prevent crashes on systems without it
try:
    from stable_baselines3 import PPO
    HAS_SB3 = True
except ImportError:
    HAS_SB3 = False

logger = logging.getLogger(__name__)

class DRLStrategy(BaseStrategy):
    """
    Deep Reinforcement Learning (DRL) Strategy using PPO.
    Takes market data, computes features, feeds them into the trained model,
    and maps the discrete action to a StrategySignal.
    """
    
    def __init__(self, model_path: str = "drl/best_model"):
        self.name = "drl_strategy"
        self.model_path = model_path
        self.model = None
        
        if HAS_SB3:
            try:
                self.model = PPO.load(self.model_path)
                logger.info(f"Successfully loaded DRL model from {self.model_path}")
            except Exception as e:
                logger.error(f"Failed to load DRL model from {self.model_path}: {e}")
        else:
            logger.error("stable-baselines3 is not installed. DRLStrategy will not function.")

        # Track current state for the env simulation
        self.current_position = 0 # 0: None, 1: Long, 2: Short
        self.entry_price = 0.0

    def compute_features(self, df: pd.DataFrame) -> np.ndarray:
        """
        Calculates the exact same features used during training.
        """
        # Ensure we have at least 14 rows for RSI etc.
        if len(df) < 14:
            return None
            
        # Example feature extraction (must match training_env.py)
        # Assuming df already has 'rsi', 'macd', 'atr', 'vol_delta' 
        # populated by the main engine's tick processor
        
        latest = df.iloc[-1]
        
        try:
            features = np.array([
                latest.get('rsi', 50),
                latest.get('macd', 0),
                latest.get('atr', 0),
                latest.get('vol_delta', 0)
            ], dtype=np.float32)
        except KeyError as e:
            logger.warning(f"Missing feature for DRL state: {e}")
            return None
            
        return features

    def on_tick(self, symbol: str, df: pd.DataFrame, open_positions: Dict[str, Any]) -> StrategySignal:
        if self.model is None:
            return None
            
        features = self.compute_features(df)
        if features is None:
            return None
            
        current_price = df.iloc[-1]['close']
        
        # Calculate current profit percentage if we have an open position
        profit_pct = 0.0
        pos = open_positions.get(symbol)
        
        if pos:
            # Sync internal state with actual portfolio
            if pos['side'] == 'BUY':
                self.current_position = 1
                self.entry_price = pos['average_price']
                profit_pct = (current_price - self.entry_price) / self.entry_price
            elif pos['side'] == 'SELL':
                self.current_position = 2
                self.entry_price = pos['average_price']
                profit_pct = (self.entry_price - current_price) / self.entry_price
        else:
            self.current_position = 0
            self.entry_price = 0.0
            
        # Construct full observation [features, pos, profit_pct]
        obs = np.append(features, [self.current_position, profit_pct]).astype(np.float32)
        
        # Get action from DRL agent
        # action space: 0 (Hold), 1 (Buy Call), 2 (Buy Put), 3 (Close)
        action, _states = self.model.predict(obs, deterministic=True)
        
        action = int(action)
        
        if action == 1 and self.current_position == 0:
            return StrategySignal(
                symbol=symbol,
                action="BUY",
                strategy=self.name,
                confidence=0.9,
                metadata={"drl_action": 1}
            )
        elif action == 2 and self.current_position == 0:
            return StrategySignal(
                symbol=symbol,
                action="SELL",
                strategy=self.name,
                confidence=0.9,
                metadata={"drl_action": 2}
            )
        elif action == 3 and self.current_position != 0:
            return StrategySignal(
                symbol=symbol,
                action="SQUAREOFF",
                strategy=self.name,
                confidence=1.0,
                metadata={"drl_action": 3}
            )
            
        return None

# Global instance for the registry wrapper
_drl_instance = None

def generate_signals(df: pd.DataFrame, **kwargs) -> pd.Series:
    """
    Wrapper for StrategyRegistry.
    Evaluates the DRL model over the dataframe and returns a Series of signals (1, -1, 0).
    """
    global _drl_instance
    if _drl_instance is None:
        import os
        # Point to the right model path
        model_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "drl", "best_model")
        _drl_instance = DRLStrategy(model_path=model_path)
    
    signals = pd.Series(0, index=df.index, dtype=int)
    
    if not HAS_SB3 or _drl_instance.model is None:
        return signals
        
    for i in range(len(df)):
        if i < 14:
            continue
            
        sub_df = df.iloc[:i+1]
        
        # We assume open_positions is empty for historical backtest/signal generation
        # Real-time state management is handled by main loop
        sig = _drl_instance.on_tick("UNKNOWN", sub_df, {})
        
        if sig:
            if sig.action == "BUY":
                signals.iloc[i] = 1
            elif sig.action == "SELL":
                signals.iloc[i] = -1
                
    return signals
