import logging
from typing import Any
import pandas as pd
import numpy as np
from drl.marl.base_agent import BaseAgent

logger = logging.getLogger(__name__)

class AlphaAgent(BaseAgent):
    """
    The Alpha Agent (Meta Agent) - Professional Options Buyer Edition.
    
    Combines:
    1. VIX/Regime analysis (BB Width)
    2. ADX Trend Strength filter (only trade trending markets)
    3. EMA Chop Zone detection (avoid trading between EMA-9 and EMA-20)
    4. Smart Money / Order Flow tracking (Volume Spikes)
    5. Expiry Scalper tracking
    6. Session Time Filter (High-profit windows only)
    
    A professional options buyer knows: buying premium in a sideways/choppy
    market is THETA DECAY SUICIDE. Only trade when trend is confirmed.
    """
    
    def __init__(self):
        super().__init__("AlphaAgent_Context")
        
    def _is_expiry_day(self, current_time, symbol: str, broker: Any = None) -> bool:
        """
        Determines if today is the expiry day for the given instrument dynamically from Broker API.
        Avoids static day-of-week assumptions (which fail on exchange holidays or specification changes).
        """
        today_date = current_time.date() if hasattr(current_time, 'date') else current_time
        
        # 1. Try fetching real active expiry dates dynamically from Broker API if available
        if broker and hasattr(broker, 'get_expiry_dates'):
            try:
                expiries = broker.get_expiry_dates(symbol)
                if expiries and len(expiries) > 0:
                    nearest_expiry = expiries[0]  # e.g., date object or "YYYY-MM-DD"
                    if isinstance(nearest_expiry, str):
                        from datetime import datetime
                        nearest_expiry = datetime.strptime(nearest_expiry, "%Y-%m-%d").date()
                    return today_date == nearest_expiry
            except Exception as e:
                logger.warning(f"Could not fetch dynamic expiry from broker for {symbol}: {e}")

        # 2. Dynamic Fallback: Check if day of week matches current NSE/BSE specs
        day_of_week = current_time.dayofweek if hasattr(current_time, 'dayofweek') else 3
        symbol = symbol.upper()
        
        # Updated Exchange specs: NIFTY=Thu, BANKNIFTY=Wed, FINNIFTY=Tue, SENSEX=Fri
        if "NIFTY50" in symbol or "NIFTY-I" in symbol or symbol == "NIFTY":
            return day_of_week == 3  # Thursday
        elif "SENSEX" in symbol:
            return day_of_week == 4  # Friday
        elif "BANKNIFTY" in symbol or "BANK-I" in symbol or symbol == "BANKNIFTY":
            return day_of_week == 2  # Wednesday
        elif "FINNIFTY" in symbol:
            return day_of_week == 1  # Tuesday
            
        return day_of_week == 3

    def _compute_adx(self, df: pd.DataFrame, period: int = 14) -> float:
        """
        Compute ADX (Average Directional Index) — the single best indicator
        for measuring TREND STRENGTH. ADX > 20 = trending, < 20 = sideways.
        
        A professional options buyer NEVER buys premium when ADX < 20.
        """
        if len(df) < period + 5:
            return 25.0  # Default to "trending" if not enough data
        
        high = df['high'].to_numpy()
        low = df['low'].to_numpy()
        close = df['close'].to_numpy()
        
        # True Range
        tr = np.maximum(
            high[1:] - low[1:],
            np.maximum(
                np.abs(high[1:] - close[:-1]),
                np.abs(low[1:] - close[:-1])
            )
        )
        
        # Directional Movement
        up_move = high[1:] - high[:-1]
        down_move = low[:-1] - low[1:]
        
        plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
        minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)
        
        # Smooth using Wilder's method
        def wilder_smooth(arr, n):
            result = np.zeros(len(arr))
            result[n-1] = arr[:n].sum()
            for i in range(n, len(arr)):
                result[i] = result[i-1] - (result[i-1] / n) + arr[i]
            return result
        
        n = period
        if len(tr) < n:
            return 25.0
            
        atr_smooth = wilder_smooth(tr, n)
        plus_di_smooth = wilder_smooth(plus_dm, n)
        minus_di_smooth = wilder_smooth(minus_dm, n)
        
        # Avoid division by zero
        with np.errstate(divide='ignore', invalid='ignore'):
            plus_di = np.where(atr_smooth > 0, 100 * plus_di_smooth / atr_smooth, 0)
            minus_di = np.where(atr_smooth > 0, 100 * minus_di_smooth / atr_smooth, 0)
            dx = np.where((plus_di + minus_di) > 0, 
                          100 * np.abs(plus_di - minus_di) / (plus_di + minus_di), 0)
        
        # ADX = smoothed DX
        if len(dx) < n:
            return 25.0
        adx_smooth = wilder_smooth(dx[n-1:], n)
        
        return float(adx_smooth[-1]) if len(adx_smooth) > 0 else 25.0

    def _is_high_profit_session(self, current_time) -> bool:
        """
        Professional options buyers know WHEN to trade.
        High-profit windows for NIFTY options:
        - 09:15 - 09:45: Opening range breakout (highest gamma, biggest moves)
        - 14:30 - 15:00: Closing momentum (institutional squaring off)
        
        Dead zones (avoid):
        - 10:30 - 13:00: Choppy lunch time, theta decay maximum
        - After 15:00: Too volatile, spreads widen, options become illiquid
        """
        try:
            if hasattr(current_time, 'hour'):
                hour = current_time.hour
                minute = current_time.minute
                time_minutes = hour * 60 + minute
                
                opening_start = 9 * 60 + 15   # 9:15
                opening_end   = 9 * 60 + 45   # 9:45
                closing_start = 14 * 60 + 30  # 14:30
                closing_end   = 15 * 60 + 0   # 15:00
                
                return (opening_start <= time_minutes <= opening_end) or \
                       (closing_start <= time_minutes <= closing_end)
        except Exception:
            pass
        return True  # Default: allow trading

    def _is_blocked_session(self, current_time) -> bool:
        """Block entries after 15:00 — options become dangerous (wide spreads, expiry risk)."""
        try:
            if hasattr(current_time, 'hour'):
                hour = current_time.hour
                minute = current_time.minute
                time_minutes = hour * 60 + minute
                block_from = 15 * 60  # 15:00
                return time_minutes >= block_from
        except Exception:
            pass
        return False

    def analyze(self, df: pd.DataFrame, symbol: str = "NSE:NIFTY50-INDEX", broker: Any = None) -> dict:
        """
        Professional multi-layer market context analysis.
        Returns:
            allowed_to_trade (bool)
            mode (str) - 'NORMAL', 'SCALP', 'HOLD'
            reason (str)
            adx (float) - trend strength
            session_quality (str) - 'HIGH', 'MEDIUM', 'LOW'
        """
        if df.empty or len(df) < 20:
            return {
                "allowed_to_trade": True,
                "mode": "NORMAL",
                "reason": "Insufficient data for Alpha Agent.",
                "adx": 25.0,
                "session_quality": "MEDIUM"
            }
            
        context = {
            "allowed_to_trade": True,
            "mode": "NORMAL",
            "reason": "Clear trend confirmed. Trading allowed.",
            "adx": 25.0,
            "session_quality": "MEDIUM"
        }
        
        current_time = df.index[-1]
        latest = df.iloc[-1]
        
        # ── Layer 1: Session Time Filter ────────────────────────────────────
        # Block all NEW entries after 15:00 (options illiquid, risky)
        if self._is_blocked_session(current_time):
            context["allowed_to_trade"] = False
            context["mode"] = "HOLD"
            context["reason"] = "Session blocked after 15:00. Options become dangerous."
            context["session_quality"] = "LOW"
            return context
        
        session_is_high = self._is_high_profit_session(current_time)
        context["session_quality"] = "HIGH" if session_is_high else "MEDIUM"
        
        # ── Layer 2: Expiry Day Detection ───────────────────────────────────
        is_expiry = self._is_expiry_day(current_time, symbol, broker=broker)
        if is_expiry:
            date_str = current_time.date() if hasattr(current_time, 'date') else str(current_time)
            logger.info(f"[AlphaAgent] Expiry Day detected for {symbol} at {date_str}.")
            context["mode"] = "SCALP"
            context["reason"] = "Expiry day detected. Switching to aggressive SCALP mode."
            
        # ── Layer 3: Smart Money / Volume Spike Detection ───────────────────
        vol_ma = df['volume'].rolling(window=20).mean().iloc[-2]
        current_vol = latest['volume']
        
        if vol_ma > 0 and current_vol > (vol_ma * 3):  # 300% spike
            logger.warning(f"[AlphaAgent] SMART MONEY SPIKE DETECTED on {symbol}! Volume: {current_vol}")
            context["mode"] = "SCALP"
            context["reason"] = f"Volume spike ({current_vol} vs avg {vol_ma:.0f}). Switching to SCALP mode."

        # ── Layer 4: Sideways Market Filter (BB Width) ──────────────────────
        close_prices = df['close']
        rolling_mean = close_prices.rolling(window=20).mean()
        rolling_std = close_prices.rolling(window=20).std()
        
        bb_upper = rolling_mean + (2 * rolling_std)
        bb_lower = rolling_mean - (2 * rolling_std)
        bb_width_pct = ((bb_upper - bb_lower) / rolling_mean).iloc[-1] * 100
        
        # Tightened from 0.05% to 0.08% — catches more sideways conditions
        if bb_width_pct < 0.08:
            if current_vol < (vol_ma * 2):
                logger.info(f"[AlphaAgent] Market extremely sideways (BB Width: {bb_width_pct:.3f}%). Blocking.")
                context["allowed_to_trade"] = False
                context["reason"] = f"Sideways regime (BB Width {bb_width_pct:.3f}% < 0.08%). Theta decay risk. Blocked."
                return context

        # ── Layer 5: ADX Trend Strength Filter ─────────────────────────────
        # THE MOST IMPORTANT FILTER for options buyers.
        # ADX < 20 = sideways = buy premium and watch it decay
        # ADX > 20 = trending = premium will appreciate with delta
        adx = self._compute_adx(df, period=14)
        context["adx"] = adx
        
        ADX_THRESHOLD = 18.0  # Slightly below 20 to catch early trend formation
        
        if adx < ADX_THRESHOLD:
            logger.info(f"[AlphaAgent] Weak trend detected. ADX={adx:.1f} < {ADX_THRESHOLD}. Blocking trades.")
            context["allowed_to_trade"] = False
            context["reason"] = f"Weak trend (ADX={adx:.1f} < {ADX_THRESHOLD}). Options decay risk high. Blocked."
            return context
        
        # ── Layer 6: EMA Chop Zone Detection ───────────────────────────────
        # Professional: If price is stuck between EMA-9 and EMA-20, 
        # market is in a "chop zone" — no clear direction. Avoid.
        if len(df) >= 26:
            ema9 = close_prices.ewm(span=9, adjust=False).mean().iloc[-1]
            ema20 = close_prices.ewm(span=20, adjust=False).mean().iloc[-1]
            current_close = float(latest['close'])
            
            ema_upper = max(ema9, ema20)
            ema_lower = min(ema9, ema20)
            chop_band = (ema_upper - ema_lower) / ema_lower * 100  # % distance between EMAs
            
            # If price is INSIDE the EMA band AND the band is very tight
            price_in_chop_zone = (ema_lower <= current_close <= ema_upper)
            tight_ema_band = chop_band < 0.15  # EMAs within 0.15% of each other
            
            if price_in_chop_zone and tight_ema_band:
                logger.info(f"[AlphaAgent] Price in EMA chop zone (EMA9={ema9:.1f}, EMA20={ema20:.1f}). Blocking.")
                context["allowed_to_trade"] = False
                context["reason"] = f"EMA chop zone detected (spread={chop_band:.3f}%). No clear direction."
                return context
        
        return context
