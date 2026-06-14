import pandas as pd
import numpy as np
import logging

logger = logging.getLogger(__name__)

class MarketRegimeDetector:
    """
    Phase 2: Market Regime Intelligence Layer
    Detects market conditions and assigns a Regime Score (0-100).
    """
    
    def __init__(self, adx_period=14, bb_period=20, bb_std=2.0):
        self.adx_period = adx_period
        self.bb_period = bb_period
        self.bb_std = bb_std

    def detect(self, df: pd.DataFrame, daily_vix: float = 15.0) -> dict:
        """
        Original slow detect per bar - fallback.
        """
        res = self.detect_vectorized(df, daily_vix)
        if len(res) == 0:
            return {"regime_score": 50, "action": "REDUCED_EXPOSURE", "state": "UNKNOWN"}
        row = res.iloc[-1]
        return row.to_dict()

    def detect_vectorized(self, df: pd.DataFrame, daily_vix: float = 15.0) -> pd.DataFrame:
        if len(df) < max(self.adx_period, self.bb_period) + 1:
            res = pd.DataFrame(index=df.index)
            res['regime_score'] = 50
            res['action'] = "REDUCED_EXPOSURE"
            res['state'] = "UNKNOWN"
            return res
        
        high = df['high']
        low = df['low']
        close = df['close']
        
        # 1. ADX for Trend vs Sideways
        tr = pd.concat([high - low, abs(high - close.shift()), abs(low - close.shift())], axis=1).max(axis=1)
        plus_dm = high.diff().clip(lower=0)
        minus_dm = low.diff().clip(upper=0).abs()
        
        tr_smooth = tr.rolling(window=self.adx_period).sum()
        plus_di = 100 * (plus_dm.rolling(window=self.adx_period).sum() / tr_smooth)
        minus_di = 100 * (minus_dm.rolling(window=self.adx_period).sum() / tr_smooth)
        dx = 100 * abs(plus_di - minus_di) / (plus_di + minus_di + 1e-9)
        adx = dx.rolling(window=self.adx_period).mean()
        
        state = np.where(adx >= 25, "TRENDING", "SIDEWAYS")
        
        # 2. Bollinger Band Width for Expansion vs Compression
        sma = close.rolling(window=self.bb_period).mean()
        std = close.rolling(window=self.bb_period).std()
        upper_bb = sma + (self.bb_std * std)
        lower_bb = sma - (self.bb_std * std)
        bb_width = ((upper_bb - lower_bb) / sma) * 100
        
        bb_width_sma = bb_width.rolling(window=self.bb_period).mean()
        phase = np.where(bb_width > bb_width_sma, "EXPANSION", "COMPRESSION")
        
        # 3. Volatility classification using VIX and ATR
        atr = tr.rolling(window=14).mean()
        atr_pct = (atr / close) * 100
        
        volatility = np.where((daily_vix > 25) | (atr_pct > 0.5), "HIGH",
                     np.where((daily_vix < 12) | (atr_pct < 0.15), "LOW", "NORMAL"))
                     
        # 4. Calculate Regime Score (0-100)
        score = np.zeros(len(df))
        
        # Trend component (max 40)
        score += np.where(adx >= 35, 40,
                 np.where(adx >= 25, 30,
                 np.where(adx >= 20, 15, 0)))
                 
        # Expansion component (max 30)
        score += np.where(phase == "EXPANSION", 30, 10)
        
        # Volatility component (max 30)
        score += np.where(volatility == "NORMAL", 30,
                 np.where(volatility == "HIGH", 20, 10))
                 
        # Determine Action Rules
        action = np.where(score < 40, "NO_TRADE",
                 np.where(score <= 70, "REDUCED_EXPOSURE", "FULL_ALLOCATION"))
                 
        res = pd.DataFrame({
            "state": state,
            "phase": phase,
            "volatility": volatility,
            "adx": adx.round(2),
            "bb_width": bb_width.round(2),
            "regime_score": score.astype(int),
            "action": action
        }, index=df.index)
        
        # Fill na for first rows
        mask = res['adx'].isna()
        res.loc[mask, 'regime_score'] = 50
        res.loc[mask, 'action'] = "REDUCED_EXPOSURE"
        res.loc[mask, 'state'] = "UNKNOWN"
        
        return res
