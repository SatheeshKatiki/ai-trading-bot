import logging
import numpy as np
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
    
    # compute_features() in trading_bot/strategies/marl_strategy.py always
    # returns a 6-element vector (return, rsi, macd_hist, atr, vol_change,
    # close_chg) — the observation this agent's model must accept.
    EXPECTED_OBS_SHAPE = (6,)

    # Minimum action-probability the model must assign to its top action
    # before analyze() will act on it, rather than falling back to HOLD.
    # Same rationale/value as trading_bot/strategies/drl_strategy.py's
    # DRLStrategy.CONFIDENCE_THRESHOLD (4-action space, uniform baseline
    # 0.25).
    CONFIDENCE_THRESHOLD = 0.4

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
                loaded_model = RecurrentPPO.load(self.model_path)
                # Root-cause fix (Medium audit finding): validate the loaded
                # model's observation space matches what this agent will
                # actually feed it, rather than only discovering a mismatch
                # as a runtime shape error deep in live inference.
                actual_shape = tuple(loaded_model.observation_space.shape)
                if actual_shape != self.EXPECTED_OBS_SHAPE:
                    logger.error(
                        "SignalAgent model at %s has observation shape %s but this "
                        "agent constructs a %s observation — refusing to load an "
                        "incompatible model.",
                        self.model_path, actual_shape, self.EXPECTED_OBS_SHAPE,
                    )
                    self.is_active = False
                else:
                    self.model = loaded_model
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

        # Root-cause fix (Medium audit finding): model.predict(deterministic=True)
        # only returns the argmax action with no confidence score, so this
        # agent always acted on the model's top pick even when it was barely
        # more likely than any other action. Call the policy's distribution
        # directly instead — this performs the identical forward pass and
        # identical argmax-based action selection predict() uses internally
        # (CategoricalDistribution.mode() == argmax(probs)), but also exposes
        # the per-action probabilities so a low-conviction NEW entry signal
        # (Long/Short) can be gated to HOLD. A low-conviction CLOSE is
        # intentionally NOT gated — exiting an existing position is risk-
        # reducing, so it shouldn't be blocked by low model conviction the
        # way opening a new position should.
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
        # Only the very first prediction of an episode should carry
        # episode_start=True — every subsequent tick continues it, so the
        # LSTM can actually accumulate memory instead of "resetting" on
        # every single call.
        self.episode_starts = np.array([False])

        action = int(action_t.item())
        confidence = float(probs[0, action].item())

        if action in (1, 2) and confidence < self.CONFIDENCE_THRESHOLD:
            action = 0

        # Action map: 0: Hold, 1: Long, 2: Short, 3: Close
        action_map = {0: "HOLD", 1: "LONG", 2: "SHORT", 3: "CLOSE"}

        return {
            "action": action,
            "action_name": action_map.get(action, "UNKNOWN"),
            "confidence": confidence,
            "source": self.name
        }

    def save_state(self, filepath: str = "lstm_memory.npz"):
        """Saves the LSTM recurrent state to disk, tagged with today's IST
        trading date, so a same-day restart can genuinely continue the
        episode while a later restart knows to discard it as stale.

        Uses numpy's native .npz format rather than pickle. lstm_states is
        always the 2-tuple of numpy arrays (hidden state, cell state)
        RecurrentActorCriticPolicy.predict() returns -- there's no need for
        pickle's ability to serialize arbitrary Python objects here, and
        avoiding it closes an insecure-deserialization path (CWE-502): if
        something with local write access ever substituted a crafted file
        at this path, np.load(..., allow_pickle=False) can only ever
        produce plain arrays, never execute arbitrary code, unlike
        pickle.load on a tampered file.
        """
        if self.lstm_states is not None:
            try:
                h, c = self.lstm_states
                np.savez(
                    filepath,
                    h=h,
                    c=c,
                    saved_date_ist=np.array(datetime.now(_IST).strftime("%Y-%m-%d")),
                )
                logger.info(f"SignalAgent saved LSTM state to {filepath}")
            except Exception as e:
                logger.error(f"SignalAgent failed to save LSTM state: {e}")

    def load_state(self, filepath: str = "lstm_memory.npz"):
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
            with np.load(filepath, allow_pickle=False) as payload:
                if "h" in payload and "c" in payload and "saved_date_ist" in payload:
                    saved_date = payload["saved_date_ist"].item()
                    today = datetime.now(_IST).strftime("%Y-%m-%d")
                    if saved_date == today:
                        self.lstm_states = (payload["h"], payload["c"])
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
                        "SignalAgent found a legacy/malformed LSTM state file in %s — "
                        "treating it as stale and starting a fresh episode.",
                        filepath,
                    )
        except Exception as e:
            logger.error(f"SignalAgent failed to load LSTM state: {e}")
            self.lstm_states = None
