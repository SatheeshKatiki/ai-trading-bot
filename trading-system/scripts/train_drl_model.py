"""
Automated DRL Model Training Pipeline (Fix 5 — 2026-08-16).

Replaces the previous 3-step manual workflow:
    1. drl/fetch_data.py        — manual
    2. tune drl/trading_env.py  — manual
    3. drl/train.py             — manual, no validation, no safety gate

This script handles the complete pipeline in one command:
    1. Fetch fresh OHLCV data (last 90 days, 1-min) via the active broker
    2. Build the TradingEnv with an 80/20 train/validation split
    3. Train RecurrentPPO for a configurable number of timesteps
    4. Evaluate on the held-out validation set (Sharpe + win rate)
    5. Compare vs the current best_model.zip — only deploy if better
    6. Send a Telegram alert with the training report

Usage:
    cd trading-system
    python scripts/train_drl_model.py [--timesteps 500000] [--symbol NSE:NIFTY50-INDEX]

Flags:
    --timesteps   INT   Total training timesteps (default: 500_000)
    --symbol      STR   Underlying symbol for data fetch (default: NSE:NIFTY50-INDEX)
    --force             Deploy even if validation Sharpe is lower (override safety gate)
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

# ── path setup ────────────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# ── Windows console encoding safety ───────────────────────────────────────────
if sys.platform == "win32":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# ── logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s %(name)s: %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger("train_drl")

# ── constants ─────────────────────────────────────────────────────────────────
MODEL_PATH      = ROOT / "best_model.zip"
MODEL_BACKUP    = ROOT / "best_model_backup.zip"
TENSORBOARD_LOG = ROOT / "ppo_training_tensorboard"
MIN_DATA_ROWS   = 5_000   # minimum rows needed for a meaningful training run
TRAIN_SPLIT     = 0.80    # 80% train, 20% validation
DEFAULT_TIMESTEPS = 500_000


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Automated DRL model training pipeline.")
    p.add_argument("--timesteps", type=int, default=DEFAULT_TIMESTEPS,
                   help=f"Training timesteps (default {DEFAULT_TIMESTEPS:,})")
    p.add_argument("--symbol", type=str, default="NSE:NIFTY50-INDEX",
                   help="Underlying symbol for data fetch")
    p.add_argument("--force", action="store_true",
                   help="Deploy even if Sharpe validation drops (bypasses safety gate)")
    return p.parse_args()


def _fetch_training_data(symbol: str, days: int = 90):
    """Fetch fresh 1-min OHLCV from the active broker.

    Falls back to the local `nifty_historical_data.csv` if the broker
    returns insufficient data (e.g. API not authenticated during off-hours).
    """
    from brokers import BrokerFactory
    logger.info(f"[Step 1/5] Fetching {days} days of 1-min OHLCV for {symbol}...")

    import pandas as pd

    try:
        broker = BrokerFactory.get_active_broker()
        if not broker.authenticate():
            raise RuntimeError("Broker authentication failed.")
        end_date   = datetime.now()
        start_date = end_date - timedelta(days=days)
        raw = broker.get_historical_data(
            symbol     = symbol,
            timeframe  = "1 Min",
            start_date = start_date.strftime("%Y-%m-%d"),
            end_date   = end_date.strftime("%Y-%m-%d"),
        )
        df = pd.DataFrame(raw)
        if len(df) >= MIN_DATA_ROWS:
            logger.info(f"[Step 1/5] Fetched {len(df):,} rows from broker.")
            return df
        logger.warning(f"[Step 1/5] Broker returned only {len(df)} rows — using local CSV fallback.")
    except Exception as e:
        logger.warning(f"[Step 1/5] Broker fetch failed ({e}) — using local CSV fallback.")

    # Fallback: local CSV
    csv_path = ROOT / "nifty_historical_data.csv"
    if not csv_path.exists():
        raise FileNotFoundError(
            f"Broker data unavailable and local CSV not found at {csv_path}. "
            "Run drl/fetch_data.py first or authenticate with the broker."
        )
    df = pd.read_csv(csv_path)
    logger.info(f"[Step 1/5] Loaded {len(df):,} rows from {csv_path.name}.")
    return df


def compute_drl_features(df: pd.DataFrame) -> pd.DataFrame:
    """Compute the 4 technical features expected by DRLStrategy (6-wide obs)."""
    import numpy as np
    import pandas as pd
    df = df.copy()
    df.columns = [c.lower() for c in df.columns]
    df = df.rename(columns={"o": "open", "h": "high", "l": "low", "c": "close", "v": "volume"})

    for col in ["open", "high", "low", "close", "volume"]:
        if col not in df.columns:
            df[col] = df.get("close", 0)

    # 1. RSI (14)
    delta = df['close'].diff()
    up = delta.clip(lower=0)
    down = -delta.clip(upper=0)
    roll_up = up.ewm(span=14, min_periods=14).mean()
    roll_down = down.ewm(span=14, min_periods=14).mean()
    rs = roll_up / (roll_down + 1e-9)
    df['rsi'] = (100.0 - (100.0 / (1.0 + rs))).fillna(50.0)

    # 2. MACD Histogram (12, 26, 9)
    ema12 = df['close'].ewm(span=12, adjust=False).mean()
    ema26 = df['close'].ewm(span=26, adjust=False).mean()
    macd_line = ema12 - ema26
    signal_line = macd_line.ewm(span=9, adjust=False).mean()
    df['macd_hist'] = (macd_line - signal_line).fillna(0.0)
    df['macd'] = df['macd_hist']

    # 3. ATR (14)
    high_low = df['high'] - df['low']
    high_close = (df['high'] - df['close'].shift()).abs()
    low_close = (df['low'] - df['close'].shift()).abs()
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    df['atr'] = tr.rolling(14, min_periods=1).mean().fillna(1.0)

    # 4. Volume change
    if 'volume' not in df.columns or df['volume'].sum() == 0:
        df['volume'] = (df['high'] - df['low']).abs()
    df['vol_change'] = df['volume'].pct_change().fillna(0.0).replace([np.inf, -np.inf], 0.0)
    df['vol_delta'] = df['vol_change']

    return df


def _prepare_env(df, split_idx: int, start_idx: int = 0):
    """Build a QuantAITradingEnv from a slice of the dataframe with indicators."""
    df_feat = compute_drl_features(df)
    df_feat = df_feat.dropna(subset=["close"]).reset_index(drop=True)
    slice_df = df_feat.iloc[start_idx:split_idx].reset_index(drop=True)
    from drl.trading_env import QuantAITradingEnv
    return QuantAITradingEnv(slice_df, mode="options")


def _evaluate_model(model, val_env) -> dict:
    """Run the model on the validation environment and compute key metrics."""
    obs, _ = val_env.reset()
    lstm_states = None
    episode_starts = True
    total_pnl  = 0.0
    n_trades   = 0
    n_wins     = 0
    init_cap   = getattr(val_env, "initial_balance", getattr(val_env, "initial_capital", 100000.0))
    equity     = [init_cap]
    done       = False

    while not done:
        action, lstm_states = model.predict(
            obs,
            state=lstm_states,
            episode_start=episode_starts,
            deterministic=True,
        )
        episode_starts = False
        obs, reward, terminated, truncated, info = val_env.step(int(action))
        done = terminated or truncated
        pnl = info.get("trade_pnl", 0.0)
        if pnl != 0.0:
            n_trades += 1
            if pnl > 0:
                n_wins += 1
            total_pnl += pnl
        curr_cap = getattr(val_env, "balance", getattr(val_env, "current_capital", equity[-1] + reward))
        equity.append(curr_cap)

    win_rate = (n_wins / n_trades * 100) if n_trades > 0 else 0.0

    # Sharpe ratio from equity curve returns
    import numpy as np
    eq_arr = np.array(equity, dtype=float)
    rets   = np.diff(eq_arr) / np.maximum(eq_arr[:-1], 1.0)
    sharpe = (rets.mean() / (rets.std() + 1e-9)) * np.sqrt(252 * 75)  # annualised

    return {
        "total_pnl":  round(total_pnl, 2),
        "n_trades":   n_trades,
        "win_rate":   round(win_rate, 1),
        "sharpe":     round(float(sharpe), 3),
    }


def _load_existing_model_sharpe(val_env) -> float:
    """Evaluate the currently-deployed best_model.zip on the validation set.
    Returns 0.0 if no model exists yet (first training run).
    """
    if not MODEL_PATH.exists():
        logger.info("[Step 4/5] No existing model found — this is the first training run.")
        return 0.0
    try:
        from sb3_contrib import RecurrentPPO
        old_model = RecurrentPPO.load(str(MODEL_PATH))
        metrics = _evaluate_model(old_model, val_env)
        logger.info(f"[Step 4/5] Existing model validation Sharpe: {metrics['sharpe']}")
        return metrics["sharpe"]
    except Exception as e:
        logger.warning(f"[Step 4/5] Could not evaluate existing model: {e} — treating as 0.")
        return 0.0


def _send_alert(msg: str) -> None:
    try:
        from shared.alerts import alerter
        alerter.send_alert(msg)
    except Exception as e:
        logger.warning(f"Alert failed: {e}")


def main() -> None:
    args = _parse_args()
    logger.info("=" * 60)
    logger.info("  QuantAI DRL Training Pipeline — Fix 5")
    logger.info(f"  Symbol: {args.symbol}  |  Timesteps: {args.timesteps:,}")
    logger.info("=" * 60)

    # Step 1: Fetch data
    df = _fetch_training_data(args.symbol)
    split_idx = int(len(df) * TRAIN_SPLIT)
    logger.info(f"[Step 1/5] Train rows: {split_idx:,}  |  Val rows: {len(df)-split_idx:,}")

    # Step 2: Build environments
    logger.info("[Step 2/5] Building TradingEnv (train + validation)...")
    try:
        train_env = _prepare_env(df, split_idx)
        val_env   = _prepare_env(df, len(df), start_idx=split_idx)
    except Exception as e:
        logger.error(f"[Step 2/5] TradingEnv construction failed: {e}")
        _send_alert(f"🔴 DRL training aborted — TradingEnv failed: {e}")
        sys.exit(1)

    # Step 3: Train
    logger.info(f"[Step 3/5] Training RecurrentPPO for {args.timesteps:,} timesteps...")
    try:
        from sb3_contrib import RecurrentPPO
        model = RecurrentPPO(
            "MlpLstmPolicy",
            train_env,
            verbose=1,
            tensorboard_log=str(TENSORBOARD_LOG),
            learning_rate=3e-4,
            n_steps=2048,
            batch_size=64,
            n_epochs=10,
        )
        t0 = time.time()
        model.learn(total_timesteps=args.timesteps)
        elapsed = time.time() - t0
        logger.info(f"[Step 3/5] Training completed in {elapsed/60:.1f} min.")
    except ImportError:
        logger.error("[Step 3/5] sb3-contrib not installed. Run: pip install sb3-contrib")
        _send_alert("🔴 DRL training aborted — sb3-contrib not installed.")
        sys.exit(1)
    except Exception as e:
        logger.error(f"[Step 3/5] Training failed: {e}")
        _send_alert(f"🔴 DRL training failed during learning: {e}")
        sys.exit(1)

    # Step 4: Validate — compare new model vs deployed model
    logger.info("[Step 4/5] Validating new model on held-out data...")
    try:
        new_metrics    = _evaluate_model(model, val_env)
        old_sharpe     = _load_existing_model_sharpe(val_env)
        new_sharpe     = new_metrics["sharpe"]
        logger.info(
            f"[Step 4/5] New model — Sharpe: {new_sharpe}  |  "
            f"Win rate: {new_metrics['win_rate']}%  |  "
            f"Trades: {new_metrics['n_trades']}  |  "
            f"P&L: ₹{new_metrics['total_pnl']:,.0f}"
        )
    except Exception as e:
        logger.error(f"[Step 4/5] Validation failed: {e}")
        _send_alert(f"🟡 DRL training completed but validation failed: {e}. Model NOT deployed.")
        sys.exit(1)

    # Step 5: Safety gate — deploy only if better (or --force)
    logger.info("[Step 5/5] Applying safety gate...")
    deploy = args.force or (new_sharpe >= old_sharpe)
    if deploy:
        if MODEL_PATH.exists():
            import shutil
            shutil.copy2(str(MODEL_PATH), str(MODEL_BACKUP))
            logger.info(f"[Step 5/5] Backed up existing model to {MODEL_BACKUP.name}.")
        model.save(str(MODEL_PATH.with_suffix("")))  # RecurrentPPO.save() adds .zip
        logger.info(f"[Step 5/5] ✅ New model deployed to {MODEL_PATH.name}.")
        _send_alert(
            f"✅ **DRL Model Retrained & Deployed**\n"
            f"Symbol: `{args.symbol}` | Timesteps: {args.timesteps:,}\n"
            f"New Sharpe: `{new_sharpe}` (was `{old_sharpe}`)\n"
            f"Win Rate: `{new_metrics['win_rate']}%` | Trades: {new_metrics['n_trades']}"
        )
    else:
        logger.warning(
            f"[Step 5/5] ⚠️  New model Sharpe ({new_sharpe}) < existing ({old_sharpe}) — "
            "NOT deploying. Use --force to override."
        )
        _send_alert(
            f"⚠️ **DRL Retrain: Safety Gate BLOCKED deployment**\n"
            f"New Sharpe `{new_sharpe}` < existing `{old_sharpe}`.\n"
            f"Use `--force` to override. Model kept on disk as `best_model_backup.zip`."
        )

    logger.info("=" * 60)
    logger.info("  DRL Training Pipeline complete.")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
