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

from shared.indicators import ema, rsi, macd, smc_features

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
        
    # We do NOT use df = df.copy() so that modifications (like scores) reflect back to the caller!
    # Initialize score columns to ensure they are present in the original dataframe
    if 'call_score' not in df.columns:
        df['call_score'] = None
    if 'put_score' not in df.columns:
        df['put_score'] = None
    
    # ---------------------------------------------------------
    # FEATURE ENGINEERING
    # ---------------------------------------------------------
    # Trend
    df['ema_9'] = ema(df['close'], 9)
    df['ema_21'] = ema(df['close'], 21)
    df['ema_diff'] = df['ema_9'] - df['ema_21']
    
    # Momentum
    df['rsi'] = rsi(df['close'], 14)
    
    macd_df = macd(df['close'])
    df['macd_hist'] = macd_df['hist']
    
    # Volatility (ATR)
    high_low = df['high'] - df['low']
    high_close = abs(df['high'] - df['close'].shift())
    low_close = abs(df['low'] - df['close'].shift())
    ranges = pd.concat([high_low, high_close, low_close], axis=1)
    df['atr'] = ranges.max(axis=1).rolling(14).mean()
    
    # Price action features
    df['candle_body'] = df['close'] - df['open']
    df['upper_wick'] = df['high'] - df.apply(lambda x: max(x['open'], x['close']), axis=1)
    df['lower_wick'] = df.apply(lambda x: min(x['open'], x['close']), axis=1) - df['low']
    
    # NEW: Volume & Order Flow Features
    # 1. VWAP Distance (Institutional Entry Zones)
    df['typical_price'] = (df['high'] + df['low'] + df['close']) / 3
    df['vwap'] = (df['typical_price'] * df['volume']).cumsum() / df['volume'].cumsum()
    # Handle division by zero or NaN volume gracefully
    df['vwap_dist'] = np.where(df['vwap'] != 0, (df['close'] - df['vwap']) / df['vwap'] * 100, 0)
    
    # 2. Relative Volume (Volume Profile Anomaly Detection)
    df['vol_ma_20'] = df['volume'].rolling(20).mean()
    df['rel_volume'] = np.where(df['vol_ma_20'] != 0, df['volume'] / df['vol_ma_20'], 1.0)
    
    # Target Variable: 1 if price goes UP in the next 3 candles, 0 otherwise
    # Aggressive: we look for any upside momentum within the next 3 bars!
    df['target'] = (df['close'].shift(-3) > df['close']).astype(int)
    
    # Features list for the model
    features = ['ema_diff', 'rsi', 'macd_hist', 'atr', 'candle_body', 'upper_wick', 'lower_wick', 'vwap_dist', 'rel_volume']
    
    # Drop rows with NaN values created by indicators (excluding None/NaN score columns)
    ml_data = df.dropna(subset=features + ['target']).copy()
    
    if len(ml_data) < 10:
        print("[AI Strategy] Not enough valid data after indicator calculation.")
        return signals
    
    X = ml_data[features]
    y = ml_data['target']
    
    # ---------------------------------------------------------
    # 2. XGBoost ML Modeling (Aggressive Tuning)
    # ---------------------------------------------------------
    try:
        model_path = os.path.join("models", "xgboost_model.json")
        model = xgb.XGBClassifier()
        
        # Check if we need to train
        need_train = True
        if os.path.exists(model_path):
            import time
            mtime = os.path.getmtime(model_path)
            # Re-train every 24 hours to stay adaptive to current market regime
            if (time.time() - mtime) < 86400: 
                need_train = False
                
        X_train = X.iloc[:-3]
        y_train = y.iloc[:-3]
        
        if need_train:
            if len(X_train) > 5 and len(y_train.unique()) > 1:
                print(f"[AI Strategy] Training XGBoost model on {len(X_train)} candles...")
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
                model.fit(X_train, y_train)
                os.makedirs(os.path.dirname(model_path), exist_ok=True)
                model.save_model(model_path)
                print(f"[AI Strategy] Model saved to {model_path}")
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
                
        # Generate probabilities
        if not need_train or (os.path.exists(model_path) and not need_train):
            probs = model.predict_proba(X)[:, 1]
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
        
    return signals
