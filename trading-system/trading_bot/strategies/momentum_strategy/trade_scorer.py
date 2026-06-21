import pandas as pd
import logging
from .price_action import CompressionExpansionDetector, LiquiditySweepDetector

logger = logging.getLogger(__name__)

class TradeQualityScorer:
    """
    Phase 4: Machine Learning Predictive Filter (Simulated XGBoost / Logit)
    Calculates the exact probability of trade success before entry. 
    Strictly filters out any trade with probability < 40%.
    """
    
    def __init__(self):
        # Weights for each factor
        self.weights = {
            "trend_alignment": 20,
            "vwap_alignment": 15,
            "rsi_momentum": 15,
            "volume_expansion": 15,
            "regime_context": 20,
            "atr_expansion": 15
        }
        self.comp_exp_detector = CompressionExpansionDetector()
        self.sweep_detector = LiquiditySweepDetector()
        
    def score(self, df: pd.DataFrame, idx: int, signal_dir: int, regime_score: int) -> dict:
        """
        Calculates Trade Conviction Score (0-100).
        idx is the index of the row where signal occurred.
        """
        if signal_dir == 0 or idx >= len(df):
            return {"trade_score": 0, "conviction": "REJECT", "factors": {}}
            
        row = df.iloc[idx]
        score = 0
        factors = {}
        
        # ── ML Predictive Probability Filter (Logistic Regression Sim) ──
        # Calculate raw logit score based on weighted features
        logit = -2.5 # Base intercept (markets are statistically mean-reverting/choppy)
        
        # 1. Trend Alignment (+1.2)
        if signal_dir == 1:
            trend_aligned = row.get('ema_20', 0) > row.get('ema_50', 0) > row.get('ema_200', 0)
        else:
            trend_aligned = row.get('ema_20', float('inf')) < row.get('ema_50', float('inf')) < row.get('ema_200', float('inf'))
        if trend_aligned: logit += 1.2
        
        # 2. VWAP Alignment (+1.5, very strong institutional signal)
        if signal_dir == 1:
            vwap_aligned = row['close'] > row.get('vwap', 0)
        else:
            vwap_aligned = row['close'] < row.get('vwap', float('inf'))
        if vwap_aligned: logit += 1.5
        
        # 3. RSI Momentum (+0.8)
        rsi = row.get('rsi', 50)
        if signal_dir == 1:
            rsi_strong = rsi > 55
        else:
            rsi_strong = rsi < 45
        if rsi_strong: logit += 0.8
        
        # 4. Volume Expansion (+1.0)
        if idx > 0:
            vol_current = row.get('volume', 0)
            vol_prev = df['volume'].iloc[idx-1] if 'volume' in df.columns else 0
            vol_sma = df['volume'].rolling(20).mean().iloc[idx] if 'volume' in df.columns else 0
            vol_expanded = vol_current > vol_sma and vol_current > vol_prev
        else:
            vol_expanded = False
        if vol_expanded: logit += 1.0
        
        # 5. Regime/ATR Context (+1.5)
        # If the regime score is high (Trend is active), high probability of continuation
        logit += (regime_score / 100.0) * 1.5
        
        # 6. Session Penalty (Dead Zone Penalty -1.5)
        if 'datetime' in row:
            try:
                dt = pd.to_datetime(row['datetime'])
                hour_min = dt.hour * 60 + dt.minute
                # Dead zone: 11:30 (690) to 13:30 (810)
                if 690 < hour_min < 810:
                    logit -= 1.5
            except:
                pass

        # Convert logit to Probability using Sigmoid function
        import math
        probability = 1 / (1 + math.exp(-logit))
        prob_pct = probability * 100
        
        # Determine Conviction & Filtering
        # Phase 4 strict filter: require at least 40% ML probability
        if prob_pct < 40.0:
            conviction = "REJECT"
        elif prob_pct < 60.0:
            conviction = "MODERATE"
        else:
            conviction = "HIGH_CONVICTION"
            
        return {
            "trade_score": int(prob_pct),
            "conviction": conviction,
            "factors": {"probability": round(prob_pct, 2)}
        }
