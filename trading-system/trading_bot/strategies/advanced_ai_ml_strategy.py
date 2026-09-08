"""Advanced AI/ML Self-Learning Strategy using XGBoost.

Focused on capital protection, dynamic risk management, and adaptive learning.
"""

from __future__ import annotations

import os
import pandas as pd
import numpy as np
from typing import Dict, Any
import xgboost as xgb
from sklearn.model_selection import train_test_split

from pathlib import Path

from shared.indicators import ema, rsi, macd, smc_features
from trading_bot.strategies._signal_utils import edge_trigger as _edge_trigger

# Anchored to THIS FILE, not the process working directory.
#
# Root-caused 2026-09-09: this was `os.path.join("models", "xgboost_model.json")`
# -- resolved against whatever CWD the process happened to have. Run from the
# repo root it wrote `./models/`; run from `trading-system/` (as main.py,
# api_bridge.py and the pytest suite all do) it wrote
# `trading-system/models/`. Both paths were tracked in git and had drifted
# into two different models with different content and mtimes, and merely
# RUNNING THE TEST SUITE silently retrained and overwrote whichever one the
# CWD pointed at -- i.e. the live production artifact. Mirrors the convention
# shared/ai/model.py already uses for trade_filter_rf.pkl.
#
# Overridable via QUANTAI_XGB_MODEL_PATH so a test run, a backtest sweep or a
# parallel experiment can retrain against a scratch artifact instead of the
# deployed one. The unit suite sets it (see the suite's conftest.py): this
# strategy auto-retrains any model older than 24h, so without an override a
# plain `pytest` run silently rewrote the live production model -- verified,
# not theoretical.
_MODEL_PATH = Path(
    os.environ.get("QUANTAI_XGB_MODEL_PATH")
    or (Path(__file__).resolve().parents[2] / "models" / "xgboost_model.json")
)

#: Absolute floor for a freshly-trained binary classifier. Below this the run
#: is not a usable model, it is a failed one -- 50% is a coin flip on a
#: two-class target, so anything at or under that has learned nothing.
#: Deliberately stricter than chance to leave no ambiguity.
_MIN_XGB_ACCURACY = 0.55


def _inline_retrain_allowed() -> bool:
    """May *generating a signal* retrain and overwrite the deployed model?

    Default: no.

    This function used to retrain and save whenever the artifact was older
    than 24h -- as a side effect of being asked for a signal. Anything that
    evaluated this strategy therefore rewrote the live, git-tracked model:
    a backtest sweep, a parallel experiment, the tick loop, and the unit
    suite. It was traced on 2026-09-09 to a write that lands during
    interpreter shutdown (a background thread finishing after pytest's own
    session hooks have run), which is exactly why it was so hard to see and
    why no amount of per-test cleanup could contain it.

    A trading desk does not re-fit its model because someone asked it for a
    quote. Retraining is a deliberate, supervised operation -- it belongs to
    `scripts/daily_ai_retrain.py` and the scheduler, which set this flag.
    With it off the strategy still trains in memory when no artifact exists,
    so signal quality is unchanged; it simply does not publish.
    """
    return os.environ.get("QUANTAI_ALLOW_INLINE_RETRAIN", "0").lower() in ("1", "true", "yes")

STRATEGY_NAME = "advanced_ai"

def generate_signals(
    df: pd.DataFrame,
    **kwargs
) -> pd.Series:
    """Generate signals using an adaptive XGBoost Machine Learning model.
    
    Focuses on capital protection and self-learning from recent data.
    """
    signals = pd.Series(0, index=df.index)
    
    if len(df) < 30:
        print("[AI Strategy] Not enough data to train ML model (need at least 30 candles).")
        return signals
        
    # Work on a copy to avoid polluting the caller's DataFrame with feature columns.
    # Scores and SL columns will be written back to the original df at the end.
    df_work = df.copy()
    if 'call_score' not in df.columns:
        df['call_score'] = None
    if 'put_score' not in df.columns:
        df['put_score'] = None
    
    # ---------------------------------------------------------
    # FEATURE ENGINEERING (on df_work copy)
    # ---------------------------------------------------------
    # Trend
    df_work['ema_9'] = ema(df_work['close'], 9)
    df_work['ema_21'] = ema(df_work['close'], 21)
    df_work['ema_diff'] = df_work['ema_9'] - df_work['ema_21']
    
    # Momentum
    df_work['rsi'] = rsi(df_work['close'], 14)
    
    macd_df = macd(df_work['close'])
    df_work['macd_hist'] = macd_df['hist']
    
    # Volatility (ATR)
    high_low = df_work['high'] - df_work['low']
    high_close = abs(df_work['high'] - df_work['close'].shift())
    low_close = abs(df_work['low'] - df_work['close'].shift())
    ranges = pd.concat([high_low, high_close, low_close], axis=1)
    df_work['atr'] = ranges.max(axis=1).rolling(14).mean()
    
    # Price action features (vectorised — avoids slow row-wise apply)
    df_work['candle_body'] = df_work['close'] - df_work['open']
    df_work['upper_wick'] = df_work['high'] - df_work[['open', 'close']].max(axis=1)
    df_work['lower_wick'] = df_work[['open', 'close']].min(axis=1) - df_work['low']
    
    # Volume & Order Flow Features
    # 1. Daily Anchored VWAP (correct institutional calculation — resets each day)
    df_work['typical_price'] = (df_work['high'] + df_work['low'] + df_work['close']) / 3
    dt_col = 'datetime' if 'datetime' in df_work.columns else ('time' if 'time' in df_work.columns else None)
    if dt_col:
        df_work['_vwap_date'] = pd.to_datetime(df_work[dt_col]).dt.date
    elif isinstance(df_work.index, pd.DatetimeIndex):
        df_work['_vwap_date'] = df_work.index.date
    else:
        df_work['_vwap_date'] = '1970-01-01'
    df_work['_vol_price'] = df_work['typical_price'] * df_work['volume']
    vol_cumsum = df_work.groupby('_vwap_date')['volume'].cumsum()
    vol_price_cumsum = df_work.groupby('_vwap_date')['_vol_price'].cumsum()
    
    # Safe division to prevent zero-volume candles causing NaN rows
    df_work['vwap'] = np.where(
        vol_cumsum != 0,
        vol_price_cumsum / vol_cumsum.replace(0, np.nan),
        df_work['close']
    )
    df_work.drop(['_vwap_date', '_vol_price'], axis=1, inplace=True)
    df_work['vwap_dist'] = np.where(
        df_work['vwap'] != 0,
        (df_work['close'] - df_work['vwap']) / df_work['vwap'] * 100,
        0
    )
    
    # 2. Relative Volume (anomaly detection)
    df_work['vol_ma_20'] = df_work['volume'].rolling(20).mean()
    df_work['rel_volume'] = np.where(df_work['vol_ma_20'] != 0, df_work['volume'] / df_work['vol_ma_20'], 1.0)
    
    # Features list for the model
    features = ['ema_diff', 'rsi', 'macd_hist', 'atr', 'candle_body', 'upper_wick', 'lower_wick', 'vwap_dist', 'rel_volume']
    
    # Create prediction data — includes ALL rows that have valid features (including live candle)
    ml_data = df_work.dropna(subset=features).copy()
    
    if len(ml_data) < 10:
        print("[AI Strategy] Not enough valid data after indicator calculation.")
        return signals
    
    # Target: 1 if price goes UP in next 3 candles — ONLY used for training
    ml_data['target'] = (ml_data['close'].shift(-3) > ml_data['close']).astype(int)
    
    if len(ml_data) < 10:
        print("[AI Strategy] Not enough valid data after indicator calculation.")
        return signals
    
    # Walk-forward split: train on first 70% only to prevent data leakage
    train_data = ml_data.iloc[:-3].dropna(subset=['target'])  # drop last 3 (no future target)
    split_idx = max(5, int(len(train_data) * 0.7))
    train_split = train_data.iloc[:split_idx]
    
    X_train = train_split[features]
    y_train = train_split['target']
    # Predict on ALL ml_data (all valid-feature rows, including live candle)
    X_predict = ml_data[features]
    
    # ---------------------------------------------------------
    # 2. XGBoost ML Modeling (Aggressive Tuning)
    # ---------------------------------------------------------
    try:
        model_path = str(_MODEL_PATH)
        model = xgb.XGBClassifier()
        
        # Check if we need to train
        need_train = True
        if os.path.exists(model_path):
            import time
            mtime = os.path.getmtime(model_path)
            # Re-train every 24 hours to stay adaptive to current market regime
            if (time.time() - mtime) < 86400: 
                need_train = False
                
        X_train_slice = X_train.iloc[:-3] if len(X_train) > 3 else X_train
        y_train_slice = y_train.iloc[:-3] if len(y_train) > 3 else y_train
        
        if need_train:
            if len(X_train_slice) > 5 and len(y_train_slice.unique()) > 1:
                print(f"[AI Strategy] Training XGBoost model on {len(X_train_slice)} candles...")
                # Aggressive Tuning: Deeper trees to capture micro-patterns, smaller learning rate
                model = xgb.XGBClassifier(
                    n_estimators=100,
                    max_depth=5,
                    learning_rate=0.05,
                    subsample=0.8,
                    colsample_bytree=0.8,
                    objective='binary:logistic',
                    random_state=42,
                    n_jobs=1
                )
                model.fit(X_train_slice, y_train_slice)

                # ── Accuracy gate ────────────────────────────────────────
                # Audit Critical #12 added a deployment gate to
                # shared/ai/model.py, but this strategy has its OWN save path
                # and bypassed it entirely: every retrain hot-deployed
                # unconditionally, overwriting the live artifact even when the
                # run had learned nothing. Hold out the tail of the training
                # window (chronological, never shuffled -- shuffling leaks
                # future bars into the score) and refuse to publish a model
                # that cannot beat the floor.
                deploy = True
                holdout_acc = None
                split = int(len(X_train_slice) * 0.8)
                if split >= 5 and len(X_train_slice) - split >= 5:
                    X_fit, X_hold = X_train_slice.iloc[:split], X_train_slice.iloc[split:]
                    y_fit, y_hold = y_train_slice.iloc[:split], y_train_slice.iloc[split:]
                    if len(y_fit.unique()) > 1:
                        gate_model = xgb.XGBClassifier(
                            n_estimators=100, max_depth=5, learning_rate=0.05,
                            subsample=0.8, colsample_bytree=0.8,
                            objective='binary:logistic', random_state=42, n_jobs=1,
                        )
                        gate_model.fit(X_fit, y_fit)
                        holdout_acc = float((gate_model.predict(X_hold) == y_hold).mean())
                        if holdout_acc < _MIN_XGB_ACCURACY:
                            deploy = False

                if not deploy:
                    print(
                        f"[AI Strategy] REJECTED retrain: holdout accuracy "
                        f"{holdout_acc:.1%} < {_MIN_XGB_ACCURACY:.0%} floor. "
                        f"Keeping the existing deployed model."
                    )
                    need_train = False
                elif not _inline_retrain_allowed():
                    # Trained in memory and used for THIS call's signals, but
                    # not published. See _inline_retrain_allowed().
                    print(
                        "[AI Strategy] Model retrained in memory; not published "
                        "(inline retrain disabled). Set QUANTAI_ALLOW_INLINE_RETRAIN=1 "
                        "or use scripts/daily_ai_retrain.py to deploy."
                    )
                    need_train = False
                else:
                    import tempfile
                    os.makedirs(os.path.dirname(model_path), exist_ok=True)

                    # Atomic save to prevent cross-process corruption during simultaneous Live+Backtest
                    temp_fd, temp_path = tempfile.mkstemp(dir=os.path.dirname(model_path), prefix="xgboost_tmp_", suffix=".json")
                    try:
                        os.close(temp_fd) # Close immediately, XGBoost handles opening
                        model.save_model(temp_path)
                        os.replace(temp_path, model_path)
                    except Exception as e:
                        if os.path.exists(temp_path):
                            os.unlink(temp_path)
                        raise e
                    if holdout_acc is not None:
                        print(f"[AI Strategy] Model saved to {model_path} (holdout accuracy {holdout_acc:.1%}).")
                    else:
                        print(f"[AI Strategy] Model saved to {model_path} (too few rows to gate).")
                    need_train = False
            else:
                print("[AI Strategy] Not enough data to train. Using rule-based fallback.")
                need_train = False
                
        if not need_train and os.path.exists(model_path):
            try:
                model.load_model(model_path)
                print("[AI Strategy] Loaded existing model from disk.")
            except Exception as e:
                print(f"[AI Strategy] Failed to load model: {e}. Will use fallback.")
                need_train = True
                
        # Generate probabilities for ALL candles (including live)
        if not need_train or (os.path.exists(model_path) and not need_train):
            probs = model.predict_proba(X_predict)[:, 1]
            ml_data['ai_confidence'] = probs * 100
        else:
            print("[AI Strategy] Using rule-based scoring fallback.")
            ml_data['ai_confidence'] = 50.0
            for i in range(len(ml_data)):
                conf = 50.0
                if ml_data['ema_diff'].iloc[i] > 0: conf += 15
                if ml_data['rsi'].iloc[i] > 50: conf += 15
                if ml_data['macd_hist'].iloc[i] > 0: conf += 15
                if ml_data['rel_volume'].iloc[i] > 1.2: conf += 10
                ml_data.loc[ml_data.index[i], 'ai_confidence'] = conf

        # ---------------------------------------------------------
        # 3. Dynamic Thresholds & Trailing SL Generation
        # ---------------------------------------------------------
        for i in range(len(ml_data)):
            idx = ml_data.index[i]
            conf = ml_data['ai_confidence'].iloc[i]
            
            df.loc[idx, 'call_score'] = int(conf)
            df.loc[idx, 'put_score'] = int(100 - conf)
            
            atr_val = ml_data['atr'].iloc[i]
            close_val = ml_data['close'].iloc[i]
            
            # --- Dynamic Volatility Adjustment ---
            # If ATR is high (> 0.2% of price), require higher confidence.
            # Aggressive Base = 60%. Choppy Base = 75%
            atr_pct = (atr_val / close_val) * 100
            if atr_pct > 0.25:
                # Highly volatile
                dynamic_thresh = 75.0
            elif atr_pct > 0.15:
                # Medium volatility
                dynamic_thresh = 65.0
            else:
                # Smooth trending (Low ATR)
                dynamic_thresh = 60.0
                
            # Overwrite the threshold with user's kwargs if they provided a specific override
            confidence_thresh = kwargs.get("ai_confidence_threshold", dynamic_thresh)
            
            # --- Capital Protection Outputs ---
            # Aggressive SL: We risk 1.2x ATR
            sl_pct = (atr_val * 1.2 / close_val) * 100
            df.loc[idx, 'custom_sl_pct'] = max(0.15, sl_pct) # Extremely tight min 0.15%
            
            # Smart Trailing SL Output: Lock profits when in favor by 1x ATR
            df.loc[idx, 'trailing_sl_trigger'] = (atr_val * 1.0 / close_val) * 100
            df.loc[idx, 'trailing_sl_offset'] = max(0.1, sl_pct * 0.5) # Trail closely
            
            # --- Signal Evaluation ---
            if conf >= confidence_thresh:
                signals.loc[idx] = 1
            elif conf <= (100 - confidence_thresh):
                signals.loc[idx] = -1
                
            if i == len(ml_data) - 1:
                print(f"[AI Strategy] ATR: {atr_pct:.2f}% -> Dynamic Thresh: {confidence_thresh}% | Call: {int(conf)}, Put: {int(100 - conf)}")
        
    except Exception as e:
        import traceback
        print(f"[AI Strategy] Error in ML engine: {e}")
        traceback.print_exc()

    # ── Edge-trigger the signal (root-cause fix, 2026-08-08) ───────────
    # The ML confidence score stays above threshold for long stretches —
    # measured 64% of all bars, in 453 runs averaging 2.2 bars and
    # reaching 22. Both main.py's live entry path and the validation
    # harness are LEVEL-triggered ("if flat and signal != 0, enter"), so
    # every stop-out inside a run was immediately followed by re-entry
    # into the same losing direction, repeatedly, for as long as the run
    # lasted. Measured consequence: 8.1 trades/day (vs 2.9 for
    # institutional_momentum), 52 of 122 days breaching the Rs 5,000
    # daily-loss limit, a -Rs 17,252 worst day, and a 61.9% max drawdown
    # that is 2.95x what its own consecutive-loss streaks explain.
    #
    # A sustained run above the confidence threshold is ONE setup, not
    # one setup per bar. Emitting only on the transition into a run
    # preserves the strategy's philosophy and every setup it detects,
    # while removing the re-entry churn. Note the legacy backtest engine
    # already edge-triggers internally (`sig_vals[i-1] != 1`); this
    # aligns the strategy's own output with that same semantics for the
    # live path, which does not.
    # Root-cause fix (2026-08-28): the first line here was a no-op
    # (`where(cond, other=signals)` returns `signals` unchanged), and the
    # second was a boolean-mask `Series.__setitem__` — the CPU-livelock
    # signature that pegged a core and silenced the live engine for a whole
    # session on 2026-08-28 via its instance in `ema_rsi_strategy.py`. Both
    # replaced with the shared numpy-based helper. See
    # docs/paper_trading_validation/anomaly_log.md's 2026-08-28 entry.
    signals = _edge_trigger(signals)

    return signals
