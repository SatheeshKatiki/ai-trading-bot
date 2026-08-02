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

    # compute_features() always returns exactly 4 features (rsi, macd_hist,
    # atr, vol_change); on_tick() appends [current_position, profit_pct] ->
    # the observation the model must accept is always exactly 6-wide.
    EXPECTED_OBS_SHAPE = (6,)

    # Minimum action-probability the model must assign to its top action
    # before on_tick() will act on it. With a 4-action space (Hold, Buy
    # Call, Buy Put, Close), a uniform/no-information policy scores 0.25
    # on each action; 0.4 requires meaningfully more conviction than
    # chance before a live signal is emitted, rather than acting on an
    # essentially-undecided prediction.
    CONFIDENCE_THRESHOLD = 0.4

    def __init__(self, model_path: str = "drl/best_model"):
        self.name = "drl_strategy"
        self.model_path = model_path
        self.model = None

        if HAS_SB3:
            try:
                loaded_model = RecurrentPPO.load(self.model_path)
                # Root-cause fix (Medium audit finding): previously any
                # model.zip that loaded successfully was used regardless of
                # whether its observation space actually matches what this
                # strategy constructs. A schema mismatch would previously
                # only surface as a runtime shape-mismatch exception deep in
                # a live tick, with no clear diagnostic. Validate up front
                # and refuse to use an incompatible model, falling back to
                # the existing model=None / all-neutral-signal path.
                actual_shape = tuple(loaded_model.observation_space.shape)
                if actual_shape != self.EXPECTED_OBS_SHAPE:
                    logger.error(
                        "DRL model at %s has observation shape %s but this strategy "
                        "constructs a %s observation — refusing to load an incompatible "
                        "model. Falling back to no-signal (neutral) mode.",
                        self.model_path, actual_shape, self.EXPECTED_OBS_SHAPE,
                    )
                else:
                    self.model = loaded_model
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

        # Root-cause fix (Medium audit finding): model.predict(deterministic=True)
        # only returns the argmax action with no confidence score, so the
        # strategy acted on the model's top pick even when it was barely
        # more likely than any other action (near-uniform, low-conviction
        # prediction). Call the policy's distribution directly instead —
        # this performs the identical forward pass and identical
        # argmax-based action selection predict() uses internally
        # (CategoricalDistribution.mode() == argmax(probs), verified against
        # stable_baselines3's own implementation), but also exposes the
        # per-action probabilities so a low-conviction prediction can be
        # gated to a neutral Hold instead of acted on.
        import torch
        policy = self.model.policy
        obs_tensor, _ = policy.obs_to_tensor(obs)

        if self.lstm_states is None:
            zeros = np.zeros(policy.lstm_hidden_state_shape)
            state = (zeros, zeros)
        else:
            state = self.lstm_states
        states_t = (
            torch.tensor(state[0], dtype=torch.float32, device=policy.device),
            torch.tensor(state[1], dtype=torch.float32, device=policy.device),
        )
        episode_starts_t = torch.tensor(self.episode_starts, dtype=torch.float32, device=policy.device)

        with torch.no_grad():
            distribution, new_states = policy.get_distribution(obs_tensor, states_t, episode_starts_t)
            action_t = distribution.get_actions(deterministic=True)
            probs = distribution.distribution.probs

        self.lstm_states = (new_states[0].cpu().numpy(), new_states[1].cpu().numpy())
        action = int(action_t.item())
        confidence = float(probs[0, action].item())

        if confidence < self.CONFIDENCE_THRESHOLD:
            return 0

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
