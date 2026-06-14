import pandas as pd
import logging
from .price_action import CompressionExpansionDetector, LiquiditySweepDetector

logger = logging.getLogger(__name__)

class TradeQualityScorer:
    """
    Phase 3: Trade Quality Scoring Engine
    Scores a generated signal from 0 to 100 based on multi-factor confirmations.
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
        
        # 1. Trend Alignment (20 pts)
        # Check if 20 EMA, 50 EMA, and 200 EMA are aligned
        if signal_dir == 1:
            trend_aligned = row.get('ema_20', 0) > row.get('ema_50', 0) > row.get('ema_200', 0)
        else:
            trend_aligned = row.get('ema_20', float('inf')) < row.get('ema_50', float('inf')) < row.get('ema_200', float('inf'))
            
        factors["trend_alignment"] = self.weights["trend_alignment"] if trend_aligned else 0
        score += factors["trend_alignment"]
        
        # 2. VWAP Alignment (15 pts)
        if signal_dir == 1:
            vwap_aligned = row['close'] > row.get('vwap', 0)
        else:
            vwap_aligned = row['close'] < row.get('vwap', float('inf'))
            
        factors["vwap_alignment"] = self.weights["vwap_alignment"] if vwap_aligned else 0
        score += factors["vwap_alignment"]
        
        # 3. RSI Momentum (15 pts)
        rsi = row.get('rsi', 50)
        if signal_dir == 1:
            rsi_strong = rsi > 55
        else:
            rsi_strong = rsi < 45
            
        factors["rsi_momentum"] = self.weights["rsi_momentum"] if rsi_strong else 0
        score += factors["rsi_momentum"]
        
        # 4. Volume Expansion (15 pts)
        if idx > 0:
            vol_current = row.get('volume', 0)
            vol_prev = df['volume'].iloc[idx-1] if 'volume' in df.columns else 0
            vol_sma = df['volume'].rolling(20).mean().iloc[idx] if 'volume' in df.columns else 0
            
            vol_expanded = vol_current > vol_sma and vol_current > vol_prev
        else:
            vol_expanded = False
            
        factors["volume_expansion"] = self.weights["volume_expansion"] if vol_expanded else 0
        score += factors["volume_expansion"]
        
        # 5. Regime Context (20 pts)
        # High regime score (Trending + Expansion) gives max points
        regime_pts = min(self.weights["regime_context"], (regime_score / 100.0) * self.weights["regime_context"])
        factors["regime_context"] = int(regime_pts)
        score += factors["regime_context"]
        
        # 6. ATR / Range Expansion (15 pts)
        if idx > 0 and 'high' in df.columns and 'low' in df.columns:
            current_range = row['high'] - row['low']
            prev_range = df['high'].iloc[idx-1] - df['low'].iloc[idx-1]
            range_expanded = current_range > prev_range
        else:
            range_expanded = False
            
        factors["atr_expansion"] = self.weights["atr_expansion"] if range_expanded else 0
        score += factors["atr_expansion"]
        
        # 7. Advanced Price Action (Bonus Points)
        bonus = 0
        if self.comp_exp_detector.detect(df, idx):
            bonus += 10
            factors["compression_expansion_bonus"] = 10
            
        if self.sweep_detector.detect(df, idx, signal_dir):
            bonus += 15
            factors["liquidity_sweep_bonus"] = 15
            
        score += bonus
        score = min(100, score)  # Cap at 100
        
        # Determine Conviction
        if score < 60:
            conviction = "REJECT"
        elif 60 <= score < 80:
            conviction = "MODERATE"
        else:
            conviction = "HIGH_CONVICTION"
            
        return {
            "trade_score": int(score),
            "conviction": conviction,
            "factors": factors
        }
