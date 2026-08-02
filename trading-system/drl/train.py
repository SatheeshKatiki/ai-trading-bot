import os
import pandas as pd
import numpy as np
from stable_baselines3.common.vec_env import DummyVecEnv
from sb3_contrib import RecurrentPPO

from trading_env import QuantAITradingEnv

def evaluate_on_holdout(model, val_df: pd.DataFrame) -> dict:
    """Run a deterministic rollout of ``model`` through a fresh environment
    built ONLY from ``val_df`` (data the model never trained on) and report
    real out-of-sample performance.

    This is the piece that was previously entirely missing: train_agent()
    called model.learn() against the full dataset with zero holdout, so
    there was no way to tell whether the resulting policy generalizes or
    just memorized/overfit the training data before this function existed.
    """
    env = QuantAITradingEnv(df=val_df, mode="options")
    obs, _ = env.reset()
    lstm_states = None
    episode_start = np.ones((1,), dtype=bool)
    done = False
    total_reward = 0.0

    while not done:
        action, lstm_states = model.predict(
            obs, state=lstm_states, episode_start=episode_start, deterministic=True
        )
        episode_start = np.zeros((1,), dtype=bool)
        obs, reward, terminated, truncated, info = env.step(int(action))
        total_reward += reward
        done = terminated or truncated

    final_balance = info["balance"]
    return_pct = (final_balance - env.initial_balance) / env.initial_balance * 100.0
    return {
        "total_reward": total_reward,
        "final_balance": final_balance,
        "initial_balance": env.initial_balance,
        "return_pct": return_pct,
        "steps": env.current_step,
    }


def train_agent(val_fraction: float = 0.15):
    print("Loading historical data...")
    df = pd.read_csv("nifty_historical_data.csv")

    # ── Chronological train/validation split ──────────────────────────────
    # Root-cause fix: model.learn() previously ran against the ENTIRE
    # dataset with no holdout at all — there was no way to check whether the
    # resulting policy generalizes to data it never saw, only whether it
    # performed well on data it was directly trained on (which any
    # sufficiently large network can trivially memorize). The split is
    # chronological (not shuffled) because shuffling time-series data before
    # splitting would let the model train on data that is chronologically
    # AFTER some of its "validation" data — exactly the kind of lookahead
    # bias this fix exists to prevent.
    split_idx = int(len(df) * (1 - val_fraction))
    train_df = df.iloc[:split_idx].reset_index(drop=True)
    val_df = df.iloc[split_idx:].reset_index(drop=True)
    print(f"Split {len(df)} rows -> {len(train_df)} train / {len(val_df)} validation ({val_fraction:.0%} holdout).")

    print("Initializing environment...")
    # Wrap in DummyVecEnv as required by Stable Baselines
    env = DummyVecEnv([lambda: QuantAITradingEnv(df=train_df, mode="options")])

    print("Creating Recurrent PPO (LSTM) Agent...")
    # RecurrentPPO automatically builds an LSTM memory layer
    model = RecurrentPPO("MlpLstmPolicy", env, verbose=1, tensorboard_log="./ppo_trading_tensorboard/", learning_rate=0.0002)

    print("Training started (LSTM Model, training split only)...")
    # Train for 200,000 steps since the dataset is much larger (20 years)
    model.learn(total_timesteps=200000)

    print("Training complete. Evaluating on the held-out validation split (never seen during training)...")
    val_results = evaluate_on_holdout(model, val_df)
    print(
        f"── Out-of-sample validation results ──\n"
        f"  Steps run        : {val_results['steps']}\n"
        f"  Total reward     : {val_results['total_reward']:.2f}\n"
        f"  Final balance    : {val_results['final_balance']:.2f} "
        f"(started at {val_results['initial_balance']:.2f})\n"
        f"  Return           : {val_results['return_pct']:+.2f}%\n"
    )
    if val_results["return_pct"] <= 0:
        print(
            "WARNING: this model LOST money on data it never trained on. "
            "Training-set performance alone does not justify deploying it — "
            "review before replacing the live best_model.zip."
        )

    print("Saving model...")
    model.save("best_model")
    print("Model saved to best_model.zip")
    return val_results

if __name__ == "__main__":
    train_agent()
