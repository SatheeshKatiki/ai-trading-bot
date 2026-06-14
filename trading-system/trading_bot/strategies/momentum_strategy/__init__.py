"""Institutional Momentum Strategy — Master Orchestrator.

Combines technical breakouts with institutional filters (EMA Trend, Volume, ADX, VWAP).
Provides signal generation for backtesting and a strategy class for live trading.
"""

from __future__ import annotations

import logging
from datetime import datetime
import pandas as pd
import numpy as np
from typing import Tuple

# Sub-components
from .config import NIFTY_LOT_SIZE
from .environment_filter import MarketEnvironmentFilter
from .signal_engine import MomentumSignalEngine
from .itm_selector import ITMOptionSelector
from .execution_sizer import ExecutionSizer
from .exit_manager import TieredExitManager
from .mtm_trailing import MTMTrailingEngine
from .regime_detector import MarketRegimeDetector
from .trade_scorer import TradeQualityScorer

logger = logging.getLogger(__name__)

STRATEGY_NAME = "institutional_momentum"

__all__ = [
    "STRATEGY_NAME",
    "MomentumStrategy",
    "generate_signals",
]

class MomentumStrategy:
    """Institutional Momentum Strategy orchestrator."""

    def __init__(
        self, 
        capital: float = 500_000.0,
        target_pct: float = 2.0,
        stoploss_pct: float = 1.0,
        default_lots: int = 1
    ):
        self.capital = capital
        self.target_pct = target_pct
        self.stoploss_pct = stoploss_pct
        self.default_lots = default_lots

        # Sub-engines
        self.env_filter = MarketEnvironmentFilter()
        self.signal_engine = MomentumSignalEngine()
        self.itm_selector = ITMOptionSelector()
        self.exec_sizer = ExecutionSizer(capital=capital, default_lots=self.default_lots)
        self.exit_manager = TieredExitManager()
        self.mtm_engine = MTMTrailingEngine()
        self.regime_detector = MarketRegimeDetector()
        self.trade_scorer = TradeQualityScorer()

        logger.info(
            "MomentumStrategy initialized | Capital=₹%.0f | Target=%.1f%% | SL=%.1f%%",
            capital, target_pct, stoploss_pct,
        )

    def check_signals(self, df_1min: pd.DataFrame, df_1hr: pd.DataFrame, vix: float) -> dict | None:
        """Evaluate the strategy at the current minute."""
        # 1. Macro Filter
        self.env_filter.set_daily_vix(vix)
        
        if "datetime" in df_1min.columns:
            last_dt = pd.to_datetime(df_1min["datetime"].iloc[-1])
        elif isinstance(df_1min.index, pd.DatetimeIndex):
            last_dt = pd.to_datetime(df_1min.index[-1])
        else:
            last_dt = datetime.now()
            
        current_time = last_dt.time()
        allowed, reason = self.env_filter.check(current_time)
        if not allowed:
            return None

        # 2. Market Regime Intelligence
        regime = self.regime_detector.detect(df_1min, vix)
        if regime["action"] == "NO_TRADE":
            logger.info(f"Regime filter blocked trade: Score {regime['regime_score']}, State: {regime['state']}")
            return None

        # 3. Signal Generation
        signal = self.signal_engine.generate(df_1min, df_1hr)
        if signal.direction == 0:
            return None

        # 4. Trade Quality Scoring
        # We pass idx=-1 to score the current latest state
        quality = self.trade_scorer.score(df_1min, -1, signal.direction, regime["regime_score"])
        if quality["conviction"] == "REJECT":
            logger.info(f"Trade Quality Scorer rejected trade: Score {quality['trade_score']}")
            return None

        # 5. Option Selection
        spot_price = float(df_1min["close"].iloc[-1])
        contract = self.itm_selector.select(spot_price, signal.direction)

        # 6. Sizing and Smart AI Stoploss (ATR Based)
        # Calculate ATR for dynamic stoploss
        high = df_1min["high"]
        low = df_1min["low"]
        close_series = df_1min["close"]
        tr = pd.concat([high - low, abs(high - close_series.shift()), abs(low - close_series.shift())], axis=1).max(axis=1)
        atr = tr.rolling(window=14).mean().iloc[-1]
        
        # Calculate standard % drop vs ATR dynamic drop
        fixed_drop = spot_price * (self.stoploss_pct / 100.0)
        atr_drop = 1.5 * atr
        
        # Use tighter of the two drops for safety
        actual_spot_drop = min(fixed_drop, atr_drop)

        # Approximate option entry premium and SL premium for sizer
        entry_premium = spot_price * 0.02
        sl_premium = entry_premium - (contract.estimated_delta * actual_spot_drop)
        
        # Base lots
        base_lots = self.exec_sizer.calculate_lots(entry_premium, sl_premium, user_lots=self.default_lots)
        
        # Apply Regime sizing (Reduced Exposure vs Full Allocation)
        if regime["action"] == "REDUCED_EXPOSURE":
            lots = max(1, base_lots // 2)
            logger.info(f"Reduced exposure due to regime. Base: {base_lots}, Adjusted: {lots}")
        else:
            lots = base_lots

        return {
            "type": "BUY" if signal.direction == 1 else "SELL",
            "symbol": contract.symbol,
            "lots": lots,
            "entry_price": spot_price,
            "reason": f"{signal.reason} | Regime Score: {regime['regime_score']} | Trade Quality: {quality['trade_score']}"
        }

    def open_trade(self, entry_price: float, stop_loss: float, total_lots: int, direction: int) -> None:
        """Register a new trade with the exit manager."""
        self.exit_manager.open_position(entry_price, stop_loss, total_lots, direction)

    def manage_active_trades(self, current_price: float, df_5min: pd.DataFrame, ai_confidence: float = None) -> dict | None:
        """Check for exit conditions on the active position."""
        decision = self.exit_manager.evaluate(current_price, df_5min, ai_confidence=ai_confidence)
        if decision.should_exit:
            return {
                "exit": True,
                "reason": decision.reason,
                "quantity_pct": decision.quantity_pct
            }
        return None

    def trail_mtm(self, current_day_mtm: float) -> bool:
        """Update MTM trailing and return True if hard-exit is triggered."""
        return self.mtm_engine.update(current_day_mtm)

def generate_signals(
    df: pd.DataFrame,
    **kwargs,
) -> tuple[pd.Series, list]:
    """Registry-compatible signal generator with modular filters and rejection logging.

    Upgraded: Institutional Range Breakout + EMA Trend + RSI Momentum + Volume Confirmation + VWAP.
    """
    signals = pd.Series(0, index=df.index, dtype=int)
    rejection_logs = []

    # Phase 6: Adaptive Donchian Intelligence (Dynamic Lookback)
    daily_vix = kwargs.get("daily_vix", 15.0)
    enable_adaptive_donchian = kwargs.get("enable_adaptive_donchian", True)
    donchian_period = kwargs.get("donchian_period", 10)
    
    if enable_adaptive_donchian:
        if daily_vix > 25.0:
            donchian_period = int(donchian_period * 1.5)  # Longer lookback for high VIX to avoid chop
        elif daily_vix < 12.0:
            donchian_period = int(donchian_period * 0.7)  # Shorter lookback for low VIX to catch tight breakouts

    donchian_period = max(3, donchian_period) # Ensure minimum period

    if len(df) < donchian_period + 10:
        return signals, []

    close = df["close"]
    volume = df["volume"]
    high = df["high"]
    low = df["low"]

    # 1. Indicator Calculations
    ema_20 = close.ewm(span=20, adjust=False).mean()
    ema_50 = close.ewm(span=50, adjust=False).mean()
    ema_200 = close.ewm(span=200, adjust=False).mean()
    
    # Export 21 EMA trailing stop for the backtester (matches live TieredExitManager)
    from .config import RUNNER_EMA_PERIOD
    ema_runner = close.ewm(span=RUNNER_EMA_PERIOD, adjust=False).mean()
    df["st_direction"] = np.where(close > ema_runner, 1, -1)
    
    tr = pd.concat([high - low, abs(high - close.shift()), abs(low - close.shift())], axis=1).max(axis=1)
    atr = tr.rolling(window=14).mean()
    vol_sma = volume.rolling(20).mean()
    typical = (high + low + close) / 3
    
    # Intraday resetting VWAP with zero-volume fallback
    if "datetime" in df.columns:
        dates = pd.to_datetime(df["datetime"]).dt.date
    elif isinstance(df.index, pd.DatetimeIndex):
        dates = df.index.date
    else:
        dates = None

    if "volume" not in df.columns or volume.nunique() <= 1 or volume.sum() == 0:
        # Fallback: Daily cumulative average typical price
        if dates is not None:
            cum_typical = typical.groupby(dates).cumsum()
            cum_count = typical.groupby(dates).cumcount() + 1
            vwap = cum_typical / cum_count
        else:
            vwap = typical.cumsum() / pd.Series(range(1, len(df) + 1), index=df.index)
    else:
        # Daily resetting VWAP
        if dates is not None:
            tp_vol = typical * volume
            cum_tp_vol = tp_vol.groupby(dates).cumsum()
            cum_vol = volume.groupby(dates).cumsum()
            vwap = cum_tp_vol / cum_vol.replace(0, 1)
        else:
            vwap = (typical * volume).cumsum() / volume.cumsum().replace(0, 1)

    # Simplified ADX
    plus_dm = high.diff().clip(lower=0)
    minus_dm = low.diff().clip(upper=0).abs()
    tr14 = tr.rolling(window=14).sum()
    plus_di = 100 * (plus_dm.rolling(window=14).sum() / tr14)
    minus_di = 100 * (minus_dm.rolling(window=14).sum() / tr14)
    adx = (100 * abs(plus_di - minus_di) / (plus_di + minus_di)).rolling(window=14).mean()

    # Premium RSI Momentum
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = delta.clip(upper=0).abs()
    avg_gain = gain.rolling(window=14).mean()
    avg_loss = loss.rolling(window=14).mean()
    rs = avg_gain / avg_loss.replace(0, 0.00001)
    rsi = 100 - (100 / (1 + rs))

    # Premium Donchian Channels
    donchian_high = high.shift(1).rolling(donchian_period).max()
    donchian_low = low.shift(1).rolling(donchian_period).min()

    # Volatility Squeeze (TTM Squeeze)
    std_20 = close.rolling(20).std()
    bb_upper = ema_20 + (2 * std_20)
    bb_lower = ema_20 - (2 * std_20)
    atr_20 = tr.rolling(20).mean()
    kc_upper = ema_20 + (1.5 * atr_20)
    kc_lower = ema_20 - (1.5 * atr_20)
    squeeze_on = (bb_upper < kc_upper) & (bb_lower > kc_lower)
    squeeze_recent = squeeze_on.rolling(5).max() > 0

    # Daily CPR and Pivots
    if dates is not None:
        daily_df = df.groupby(dates).agg({'high':'max', 'low':'min', 'close':'last'})
        daily_df['pdh'] = daily_df['high'].shift(1)
        daily_df['pdl'] = daily_df['low'].shift(1)
        daily_df['pdc'] = daily_df['close'].shift(1)
        
        # We must align with df.index
        # If dates is a numpy array of dates, we can map it.
        # Ensure we align properly by using df's index or a parallel series.
        date_series = pd.Series(dates, index=df.index)
        pdh = date_series.map(daily_df['pdh'])
        pdl = date_series.map(daily_df['pdl'])
        pdc = date_series.map(daily_df['pdc'])
    else:
        pdh = high.rolling(75).max().shift(1)
        pdl = low.rolling(75).min().shift(1)
        pdc = close.shift(1)

    pivot = (pdh + pdl + pdc) / 3
    bc = (pdh + pdl) / 2
    tc = (pivot - bc) + pivot
    
    # Identify which is higher tc or bc
    top_cpr = pd.concat([tc, bc], axis=1).max(axis=1)
    bottom_cpr = pd.concat([tc, bc], axis=1).min(axis=1)
    
    r1 = (2 * pivot) - pdl
    s1 = (2 * pivot) - pdh

    # Candle Close Strength (Aggression)
    candle_range = high - low
    close_strength = (close - low) / candle_range.replace(0, 0.00001)

    # EMA Extension
    ema_extension = abs(close - ema_20) / ema_20

    # 2. Modular Filter Flags (Task 2 & 4)
    f_ema = kwargs.get("enable_ema_filter", True)
    f_vol = kwargs.get("enable_volume_filter", False)
    f_adx = kwargs.get("enable_adx_filter", False)
    f_vwap = kwargs.get("enable_vwap_filter", True)
    f_rsi = kwargs.get("enable_rsi_filter", True)
    
    # Advanced Institutional Filters
    f_squeeze = kwargs.get("enable_squeeze_filter", False)
    f_extension = kwargs.get("enable_extension_filter", False)
    f_cpr = kwargs.get("enable_cpr_filter", False)
    f_aggression = kwargs.get("enable_aggression_filter", False)
    
    # Dynamic RSI Thresholds
    rsi_long = kwargs.get("rsi_long", kwargs.get("rsi_buy_thresh", 50))
    rsi_short = kwargs.get("rsi_short", kwargs.get("rsi_sell_thresh", 50))
    
    # Init Regime Detector
    regime_detector = MarketRegimeDetector()
    df_indicators = df.copy()
    df_indicators['ema_20'] = ema_20
    df_indicators['ema_50'] = ema_50
    df_indicators['ema_200'] = ema_200
    df_indicators['vwap'] = vwap
    df_indicators['rsi'] = rsi
    
    # Vectorized Regime Detection
    regimes = regime_detector.detect_vectorized(df_indicators)

    # 3. Iterative Signal Generation with Rejection Logging (Task 3)
    for i in range(donchian_period + 1, len(df)):
        if 'datetime' in df.columns:
            timestamp = str(df['datetime'].iloc[i])
            if len(timestamp) >= 16:
                timestamp = timestamp[:16]
        else:
            timestamp = str(df.index[i]).split(' ')[1][:5] if ' ' in str(df.index[i]) else str(i)
        
        # Base Setup: 10-candle Donchian Breakout + Price > EMA 20
        is_bull_setup = (close.iloc[i] > donchian_high.iloc[i]) and (close.iloc[i] > ema_20.iloc[i])
        is_bear_setup = (close.iloc[i] < donchian_low.iloc[i]) and (close.iloc[i] < ema_20.iloc[i])

        # Regime Check
        regime = regimes.iloc[i]
        is_chop_zone = regime['state'] == 'CHOP'
        req_adx = 25 if is_chop_zone else 20
        req_vol_mult = 1.5 if is_chop_zone else 1.2

        if regime["action"] == "NO_TRADE":
            if is_bull_setup or is_bear_setup:
                rejection_logs.append({"time": timestamp, "reason": f"REJECTED: Regime Score too low ({regime['regime_score']} - {regime['state']})"})
            continue
        if is_bull_setup:
            # Check Filters
            if f_ema and not (close.iloc[i] > ema_200.iloc[i] and ema_20.iloc[i] > ema_50.iloc[i]):
                rejection_logs.append({"time": timestamp, "reason": "REJECTED: EMA Trend structure is bearish/choppy"})
                continue
            
            if f_vwap and not (close.iloc[i] > vwap.iloc[i]):
                rejection_logs.append({"time": timestamp, "reason": "REJECTED: Price is below Daily VWAP (Negative Bias)"})
                continue

            if f_adx and not (adx.iloc[i] > req_adx):
                rejection_logs.append({"time": timestamp, "reason": f"REJECTED: Low ADX Trend Strength ({adx.iloc[i]:.1f} < {req_adx}){' (Chop Zone)' if is_chop_zone else ''}"})
                continue

            if f_vol and not (volume.iloc[i] > vol_sma.iloc[i] * req_vol_mult):
                v_ratio = volume.iloc[i] / vol_sma.iloc[i] if vol_sma.iloc[i] > 0 else 0
                rejection_logs.append({"time": timestamp, "reason": f"REJECTED: Volume surge is insufficient ({v_ratio:.1f}x < {req_vol_mult}x){' (Chop Zone)' if is_chop_zone else ''}"})
                continue

            if f_rsi and not (rsi.iloc[i] >= rsi_long):
                rejection_logs.append({"time": timestamp, "reason": f"REJECTED: RSI Momentum ({rsi.iloc[i]:.1f}) is below bullish threshold ({rsi_long})"})
                continue
            
            if f_squeeze and not squeeze_recent.iloc[i]:
                rejection_logs.append({"time": timestamp, "reason": "REJECTED: No recent Volatility Squeeze (Not a fresh breakout)"})
                continue
                
            if f_extension and (ema_extension.iloc[i] > 0.006):
                rejection_logs.append({"time": timestamp, "reason": f"REJECTED: Price is over-extended from 20 EMA (Distance: {ema_extension.iloc[i]*100:.2f}%)"})
                continue
                
            if f_aggression and (close_strength.iloc[i] < 0.6):
                rejection_logs.append({"time": timestamp, "reason": f"REJECTED: Weak Bullish Candle Close ({close_strength.iloc[i]*100:.0f}% < 60%)"})
                continue
                
            if f_cpr:
                c_price = close.iloc[i]
                r1_val = r1.iloc[i]
                tc_val = top_cpr.iloc[i]
                # Reject if price is within 0.15% below R1 or Top CPR
                if (r1_val > c_price and (r1_val - c_price)/c_price < 0.0015):
                    rejection_logs.append({"time": timestamp, "reason": "REJECTED: Approaching R1 Resistance"})
                    continue
                if (tc_val > c_price and (tc_val - c_price)/c_price < 0.0015):
                    rejection_logs.append({"time": timestamp, "reason": "REJECTED: Approaching Top CPR Resistance"})
                    continue

            signals.iloc[i] = 1

        elif is_bear_setup:
            if f_ema and not (close.iloc[i] < ema_200.iloc[i] and ema_20.iloc[i] < ema_50.iloc[i]):
                rejection_logs.append({"time": timestamp, "reason": "REJECTED: EMA Trend structure is bullish/choppy"})
                continue
            
            if f_vwap and not (close.iloc[i] < vwap.iloc[i]):
                rejection_logs.append({"time": timestamp, "reason": "REJECTED: Price is above Daily VWAP (Positive Bias)"})
                continue

            if f_adx and not (adx.iloc[i] > req_adx):
                rejection_logs.append({"time": timestamp, "reason": f"REJECTED: Low ADX Trend Strength ({adx.iloc[i]:.1f} < {req_adx}){' (Chop Zone)' if is_chop_zone else ''}"})
                continue

            if f_vol and not (volume.iloc[i] > vol_sma.iloc[i] * req_vol_mult):
                v_ratio = volume.iloc[i] / vol_sma.iloc[i] if vol_sma.iloc[i] > 0 else 0
                rejection_logs.append({"time": timestamp, "reason": f"REJECTED: Volume surge is insufficient ({v_ratio:.1f}x < {req_vol_mult}x){' (Chop Zone)' if is_chop_zone else ''}"})
                continue

            if f_rsi and not (rsi.iloc[i] <= rsi_short):
                rejection_logs.append({"time": timestamp, "reason": f"REJECTED: RSI Momentum ({rsi.iloc[i]:.1f}) is above bearish threshold ({rsi_short})"})
                continue
            
            if f_squeeze and not squeeze_recent.iloc[i]:
                rejection_logs.append({"time": timestamp, "reason": "REJECTED: No recent Volatility Squeeze (Not a fresh breakdown)"})
                continue
                
            if f_extension and (ema_extension.iloc[i] > 0.006):
                rejection_logs.append({"time": timestamp, "reason": f"REJECTED: Price is over-extended from 20 EMA (Distance: {ema_extension.iloc[i]*100:.2f}%)"})
                continue
                
            if f_aggression and (close_strength.iloc[i] > 0.4):
                rejection_logs.append({"time": timestamp, "reason": f"REJECTED: Weak Bearish Candle Close ({close_strength.iloc[i]*100:.0f}% > 40%)"})
                continue
                
            if f_cpr:
                c_price = close.iloc[i]
                s1_val = s1.iloc[i]
                bc_val = bottom_cpr.iloc[i]
                # Reject if price is within 0.15% above S1 or Bottom CPR
                if (s1_val < c_price and (c_price - s1_val)/c_price < 0.0015):
                    rejection_logs.append({"time": timestamp, "reason": "REJECTED: Approaching S1 Support"})
                    continue
                if (bc_val < c_price and (c_price - bc_val)/c_price < 0.0015):
                    rejection_logs.append({"time": timestamp, "reason": "REJECTED: Approaching Bottom CPR Support"})
                    continue
            
            signals.iloc[i] = -1

    # Task: Automatic Swing Low/High (ATR based) Stoploss calculation
    df['custom_sl_pct'] = 0.0
    
    # If the user sets Stoploss % to 0.0, we automatically activate the Swing/ATR SL
    stoploss_pct = kwargs.get("stoploss_pct", 2.0)
    enable_swing_sl = kwargs.get("enable_swing_sl", False)
    
    if stoploss_pct <= 0.0 or enable_swing_sl:
        # Vectorized calculation for performance
        # Bull SL: Distance from close down to Donchian Low, minimum 1.5x ATR
        bull_sl_dist = (close - donchian_low).clip(lower=atr * 1.5)
        bull_sl_pct = (bull_sl_dist / close) * 100
        
        # Bear SL: Distance from Donchian High down to close, minimum 1.5x ATR
        bear_sl_dist = (donchian_high - close).clip(lower=atr * 1.5)
        bear_sl_pct = (bear_sl_dist / close) * 100
        
        signals_np = signals.to_numpy()
        bull_mask = signals_np == 1
        bear_mask = signals_np == -1
        
        custom_sl = np.zeros(len(df))
        custom_sl[bull_mask] = bull_sl_pct[bull_mask]
        custom_sl[bear_mask] = bear_sl_pct[bear_mask]
        
        df['custom_sl_pct'] = custom_sl

    return signals, rejection_logs
