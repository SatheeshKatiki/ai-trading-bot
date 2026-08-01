import logging
import numpy as np
import pickle
import os
from datetime import datetime, timezone, timedelta
from drl.marl.base_agent import BaseAgent

_IST = timezone(timedelta(hours=5, minutes=30))

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
        # True until this agent's first prediction — sb3-contrib's recurrent
        # policies need episode_start=True on exactly the first observation
        # of a new episode so they reset their internal hidden state instead
        # of continuing from whatever state happens to be sitting in
        # self.lstm_states. load_state() below may flip this back to False
        # if it finds state worth genuinely continuing from.
        self.episode_starts = np.array([True])

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

        # Attempt to load persistent memory state on boot — only reused if
        # it was saved earlier the SAME trading day (see load_state()).
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
        # Only the very first prediction of an episode should carry
        # episode_start=True — every subsequent tick continues it, so the
        # LSTM can actually accumulate memory instead of "resetting" on
        # every single call.
        self.episode_starts = np.array([False])

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
        """Saves the LSTM recurrent state to disk, tagged with today's IST
        trading date, so a same-day restart can genuinely continue the
        episode while a later restart knows to discard it as stale."""
        if self.lstm_states is not None:
            try:
                payload = {
                    "lstm_states": self.lstm_states,
                    "saved_date_ist": datetime.now(_IST).strftime("%Y-%m-%d"),
                }
                with open(filepath, "wb") as f:
                    pickle.dump(payload, f)
                logger.info(f"SignalAgent saved LSTM state to {filepath}")
            except Exception as e:
                logger.error(f"SignalAgent failed to save LSTM state: {e}")

    def load_state(self, filepath: str = "lstm_memory.pkl"):
        """Restores LSTM state saved earlier the SAME trading day only.

        A restart on a different day (or a legacy pre-dated state file with
        no date marker at all) starts a fresh episode instead of feeding
        today's market observations through recurrent state built up in a
        different, unrelated market regime — this was previously always
        restored unconditionally regardless of age.
        """
        if not os.path.exists(filepath):
            return
        try:
            with open(filepath, "rb") as f:
                payload = pickle.load(f)

            if isinstance(payload, dict) and "lstm_states" in payload:
                saved_date = payload.get("saved_date_ist")
                today = datetime.now(_IST).strftime("%Y-%m-%d")
                if saved_date == today:
                    self.lstm_states = payload["lstm_states"]
                    self.episode_starts = np.array([False])  # genuine same-day continuation
                    logger.info(f"SignalAgent restored same-day LSTM state from {filepath}")
                else:
                    logger.warning(
                        "SignalAgent found LSTM state saved on %s (today is %s) — "
                        "discarding it and starting a fresh episode instead of "
                        "continuing recurrent state from a different market regime.",
                        saved_date, today,
                    )
            else:
                logger.warning(
                    "SignalAgent found a legacy LSTM state file with no date marker "
                    "in %s — treating it as stale and starting a fresh episode.",
                    filepath,
                )
        except Exception as e:
            logger.error(f"SignalAgent failed to load LSTM state: {e}")
            self.lstm_states = None
