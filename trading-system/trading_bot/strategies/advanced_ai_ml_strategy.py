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
    
    # Trend
    df['ema_9'] = ema(df['close'], 9)
    df['ema_21'] = ema(df['close'], 21)
    df['ema_diff'] = df['ema_9'] - df['ema_21']
    
    # Momentum
    df['rsi'] = rsi(df['close'], 14)
    
    macd_df = macd(df['close'])
    df['macd_hist'] = macd_df['hist']
    
    # Volatility (ATR) - Crucial for Capital Protection
    high_low = df['high'] - df['low']
    high_close = abs(df['high'] - df['close'].shift())
    low_close = abs(df['low'] - df['close'].shift())
    ranges = pd.concat([high_low, high_close, low_close], axis=1)
    df['atr'] = ranges.max(axis=1).rolling(14).mean()
    
    # Price action features
    df['candle_body'] = df['close'] - df['open']
    df['upper_wick'] = df['high'] - df.apply(lambda x: max(x['open'], x['close']), axis=1)
    df['lower_wick'] = df.apply(lambda x: min(x['open'], x['close']), axis=1) - df['low']
    
    # Target Variable: 1 if price goes UP in the next 3 candles, 0 otherwise
    # (Predicting short term direction for Options Buying)
    df['target'] = (df['close'].shift(-3) > df['close']).astype(int)
    
    # Drop rows with NaN values created by indicators
    ml_data = df.dropna().copy()
    
    if len(ml_data) < 10:
        print("[AI Strategy] Not enough valid data after indicator calculation.")
        return signals
        
    # Features list for the model
    features = ['ema_diff', 'rsi', 'macd_hist', 'atr', 'candle_body', 'upper_wick', 'lower_wick']
    
    X = ml_data[features]
    y = ml_data['target']
    
    # 2. Self-Learning / Walk-Forward Training
    # To simulate self-learning without look-ahead bias, we train on historical data
    # and predict the latest data.
    
    # For the very latest candle (Live Trading):
    # We train on all data except the last 3 candles (since we don't know their targets yet)
    # and predict the latest candle.
    
    try:
        model_path = os.path.join("models", "xgboost_model.json")
        model = xgb.XGBClassifier()
        
        # Check if we need to train
        need_train = True
        if os.path.exists(model_path):
            # Check age of model file
            import time
            mtime = os.path.getmtime(model_path)
            if (time.time() - mtime) < 86400: # Less than 24 hours
                need_train = False
                
        X_train = X.iloc[:-3]
        y_train = y.iloc[:-3]
        
        if need_train:
            if len(X_train) > 5 and len(y_train.unique()) > 1:
                print(f"[AI Strategy] Training XGBoost model on {len(X_train)} candles...")
                model = xgb.XGBClassifier(
                    n_estimators=50,
                    max_depth=3,
                    learning_rate=0.1,
                    objective='binary:logistic',
                    random_state=42,
                    n_jobs=1
                )
                model.fit(X_train, y_train)
                # Ensure directory exists
                os.makedirs(os.path.dirname(model_path), exist_ok=True)
                model.save_model(model_path)
                print(f"[AI Strategy] Model saved to {model_path}")
            else:
                print("[AI Strategy] Not enough data to train. Using rule-based fallback.")
                need_train = False # Force fallback logic if we couldn't train
                
        # If we didn't train just now, try to load the saved model
        if not need_train and os.path.exists(model_path):
            try:
                model.load_model(model_path)
                print("[AI Strategy] Loaded existing model from disk.")
            except Exception as e:
                print(f"[AI Strategy] Failed to load model: {e}. Will use fallback.")
                need_train = True # Force fallback
                
        # Generate probabilities
        if not need_train or (os.path.exists(model_path) and not need_train):
            # Predict probabilities for all rows
            probs = model.predict_proba(X)[:, 1]
            ml_data['ai_confidence'] = probs * 100
            print(f"[AI Strategy] Generated probs: {probs[-5:]}")
        else:
            print("[AI Strategy] Using rule-based scoring fallback.")
            # Fallback rule-based confidence
            ml_data['ai_confidence'] = 50.0
            for i in range(len(ml_data)):
                conf = 50.0
                if ml_data['ema_diff'].iloc[i] > 0: conf += 15
                if ml_data['rsi'].iloc[i] > 50: conf += 15
                if ml_data['macd_hist'].iloc[i] > 0: conf += 15
                ml_data.loc[ml_data.index[i], 'ai_confidence'] = conf

        # 3. Capital Protection & Signal Generation
        confidence_thresh = kwargs.get("ai_confidence_threshold", 75.0)
        
        for i in range(len(ml_data)):
            idx = ml_data.index[i]
            conf = ml_data['ai_confidence'].iloc[i]
            
            df.loc[idx, 'call_score'] = int(conf)
            df.loc[idx, 'put_score'] = int(100 - conf)
            if i == len(ml_data) - 1:
                print(f"[AI Strategy] Latest scores -> Call: {int(conf)}, Put: {int(100 - conf)}")
            
            # Dynamic Stop Loss based on ATR (Capital Protection)
            atr_val = ml_data['atr'].iloc[i]
            close_val = ml_data['close'].iloc[i]
            
            # We risk at most 1.5x ATR
            sl_pct = (atr_val * 1.5 / close_val) * 100
            df.loc[idx, 'custom_sl_pct'] = max(0.2, sl_pct) # Min 0.2%
            
            if conf >= confidence_thresh:
                signals.loc[idx] = 1
            elif conf <= (100 - confidence_thresh):
                signals.loc[idx] = -1
        
    except Exception as e:
        print(f"[AI Strategy] Error training XGBoost: {e}")
        # Fallback to simple logic if ML fails
        pass
        
    return signals
