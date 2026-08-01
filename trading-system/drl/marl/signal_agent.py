import logging
import numpy as np
import pickle
import os
from drl.marl.base_agent import BaseAgent

# Only import if sb3_contrib is installed to prevent crashes on systems without it
try:
    from sb3_contrib import RecurrentPPO
    HAS_SB3 = True
except ImportError:
    HAS_SB3 = False

logger = logging.getLogger(__name__)

class SignalAgent(BaseAgent):
    """
    The Signal Agent (The Sniper).
    Wraps the Deep Reinforcement Learning LSTM model.
    It takes technical state as input and predicts the next market direction.
    """
    
    def __init__(self, model_path: str):
        super().__init__("SignalAgent_LSTM")
        self.model_path = model_path
        self.lstm_states = None
        self.episode_starts = np.zeros((1,), dtype=bool)
        
        if HAS_SB3:
            try:
                self.model = RecurrentPPO.load(self.model_path)
                logger.info(f"SignalAgent successfully loaded LSTM model from {self.model_path}")
            except Exception as e:
                logger.error(f"SignalAgent failed to load LSTM model: {e}")
                self.is_active = False
        else:
            logger.error("sb3-contrib is not installed. SignalAgent will be inactive.")
            self.is_active = False
            
        # Attempt to load persistent memory state on boot
        if self.is_active:
            self.load_state()

    def analyze(self, obs: np.ndarray) -> dict:
        """
        Takes the observation state (features + current pos + profit) and predicts direction.
        Returns a signal analysis dict.
        """
        if not self.is_active:
            return {"action": 0, "confidence": 0.0, "reason": "Inactive"}
            
        action, self.lstm_states = self.model.predict(
            obs, 
            state=self.lstm_states, 
            episode_start=self.episode_starts,
            deterministic=True # Revert to deterministic mode (optimal strategy)
        )
        
        if isinstance(action, np.ndarray):
            action = action.item()
            
        # Action map: 0: Hold, 1: Long, 2: Short, 3: Close
        action_map = {0: "HOLD", 1: "LONG", 2: "SHORT", 3: "CLOSE"}
        
        return {
            "action": action,
            "action_name": action_map.get(action, "UNKNOWN"),
            "source": self.name
        }

    def save_state(self, filepath: str = "lstm_memory.pkl"):
        """Saves the LSTM recurrent state to disk to survive reboots."""
        if self.lstm_states is not None:
            try:
                with open(filepath, "wb") as f:
                    pickle.dump(self.lstm_states, f)
                logger.info(f"SignalAgent saved LSTM state to {filepath}")
            except Exception as e:
                logger.error(f"SignalAgent failed to save LSTM state: {e}")

    def load_state(self, filepath: str = "lstm_memory.pkl"):
        """Loads the LSTM recurrent state from disk."""
        if os.path.exists(filepath):
            try:
                with open(filepath, "rb") as f:
                    self.lstm_states = pickle.load(f)
                logger.info(f"SignalAgent successfully restored LSTM state from {filepath}")
            except Exception as e:
                logger.error(f"SignalAgent failed to load LSTM state: {e}")
                self.lstm_states = None
