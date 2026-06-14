"""Momentum Signal Engine — Multi-Timeframe Breakout + VWAP + Volume.

Generates directional signals using:
1. 1-Hour primary trend alignment (50 EMA & 200 EMA)
2. 5-Minute chart breakout detection
3. Volume surge confirmation (> 1.5x VMA-20)
4. Price vs Daily VWAP positioning
"""

from __future__ import annotations

import logging
from typing import Optional

import numpy as np
import pandas as pd

from .config import (
    TREND_EMA_FAST, TREND_EMA_SLOW,
    BREAKOUT_EMA_FAST, BREAKOUT_EMA_SLOW,
    VOLUME_BREAKOUT_MULT, VOLUME_SMA_PERIOD,
    MomentumSignal,
)

logger = logging.getLogger(__name__)


def _ema(series: pd.Series, period: int) -> pd.Series:
    """Exponential Moving Average."""
    return series.ewm(span=period, adjust=False).mean()


def _vwap(df: pd.DataFrame) -> pd.Series:
    """Intraday Volume Weighted Average Price (resets daily) with zero-volume fallback."""
    typical = (df["high"] + df["low"] + df["close"]) / 3
    
    if "datetime" in df.columns:
        dates = pd.to_datetime(df["datetime"]).dt.date
    elif isinstance(df.index, pd.DatetimeIndex):
        dates = df.index.date
    else:
        dates = None

    if "volume" not in df.columns or df["volume"].nunique() <= 1 or df["volume"].sum() == 0:
        # Fallback: Daily cumulative average typical price
        if dates is not None:
            cum_typical = typical.groupby(dates).cumsum()
            cum_count = typical.groupby(dates).cumcount() + 1
            return cum_typical / cum_count
        else:
            return typical.cumsum() / pd.Series(range(1, len(df) + 1), index=df.index)
    else:
        # Daily resetting VWAP
        if dates is not None:
            tp_vol = typical * df["volume"]
            cum_tp_vol = tp_vol.groupby(dates).cumsum()
            cum_vol = df["volume"].groupby(dates).cumsum()
            return cum_tp_vol / cum_vol.replace(0, 1)
        else:
            return (typical * df["volume"]).cumsum() / df["volume"].cumsum().replace(0, 1)


class MomentumSignalEngine:
    """Multi-timeframe momentum signal generator.

    Usage::
        engine = MomentumSignalEngine()
        signal = engine.generate(df_5min, df_1hr)
    """

    def __init__(
        self,
        trend_ema_fast: int = TREND_EMA_FAST,
        trend_ema_slow: int = TREND_EMA_SLOW,
        breakout_ema_fast: int = BREAKOUT_EMA_FAST,
        breakout_ema_slow: int = BREAKOUT_EMA_SLOW,
        volume_mult: float = VOLUME_BREAKOUT_MULT,
        volume_sma_period: int = VOLUME_SMA_PERIOD,
    ):
        self.trend_ema_fast = trend_ema_fast
        self.trend_ema_slow = trend_ema_slow
        self.breakout_ema_fast = breakout_ema_fast
        self.breakout_ema_slow = breakout_ema_slow
        self.volume_mult = volume_mult
        self.volume_sma_period = volume_sma_period

    # ──────────────────────────────────────────────────────────────────
    # Step 1: 1-Hour Trend Direction
    # ──────────────────────────────────────────────────────────────────

    def compute_1hr_trend(self, df_1hr: pd.DataFrame) -> int:
        """Determine the primary 1-hour trend using 50 & 200 EMA alignment.

        Returns
        -------
        int
            1 = Bullish (price > 50 EMA > 200 EMA)
           -1 = Bearish (price < 50 EMA < 200 EMA)
            0 = Neutral / Choppy
        """
        if len(df_1hr) < self.trend_ema_slow + 5:
            logger.debug("Insufficient 1hr bars for trend calc (%d)", len(df_1hr))
            return 0

        close = df_1hr["close"]
        ema_50 = _ema(close, self.trend_ema_fast)
        ema_200 = _ema(close, self.trend_ema_slow)

        latest_close = close.iloc[-1]
        latest_50 = ema_50.iloc[-1]
        latest_200 = ema_200.iloc[-1]

        if latest_close > latest_50 and latest_50 > latest_200:
            return 1   # Strong bullish alignment
        elif latest_close < latest_50 and latest_50 < latest_200:
            return -1  # Strong bearish alignment
        else:
            return 0   # Mixed / choppy — no trade

    # ──────────────────────────────────────────────────────────────────
    # Step 2: 5-Minute Breakout Detection
    # ──────────────────────────────────────────────────────────────────

    def compute_5min_breakout(self, df_5min: pd.DataFrame) -> int:
        """Detect a 5-minute EMA crossover breakout.

        Returns
        -------
        int
            1 = Bullish breakout (fast EMA crosses above slow)
           -1 = Bearish breakout (fast EMA crosses below slow)
            0 = No breakout
        """
        if len(df_5min) < self.breakout_ema_slow + 5:
            return 0

        close = df_5min["close"]
        ema_fast = _ema(close, self.breakout_ema_fast)
        ema_slow = _ema(close, self.breakout_ema_slow)

        # Current and previous bar crossover check
        curr_fast = ema_fast.iloc[-1]
        curr_slow = ema_slow.iloc[-1]
        prev_fast = ema_fast.iloc[-2]
        prev_slow = ema_slow.iloc[-2]

        # Bullish crossover: fast crosses above slow
        if prev_fast <= prev_slow and curr_fast > curr_slow:
            return 1

        # Bearish crossover: fast crosses below slow
        if prev_fast >= prev_slow and curr_fast < curr_slow:
            return -1

        return 0

    # ──────────────────────────────────────────────────────────────────
    # Step 3: Volume & VWAP Confluence
    # ──────────────────────────────────────────────────────────────────

    def check_volume_surge(self, df_5min: pd.DataFrame) -> tuple[bool, float]:
        """Check if breakout candle volume exceeds 1.5x the 20-period VMA.

        Returns (is_valid, volume_ratio).
        """
        if len(df_5min) < self.volume_sma_period + 1:
            return True, 1.0  # Not enough data — bypass

        vol = df_5min["volume"]
        # Handle zero/constant volume (index data from some feeds)
        if vol.nunique() <= 1:
            return True, 1.0

        vol_sma = vol.rolling(self.volume_sma_period).mean()
        latest_vol = vol.iloc[-1]
        latest_sma = vol_sma.iloc[-1]

        if latest_sma <= 0:
            return True, 1.0

        ratio = latest_vol / latest_sma
        return ratio >= self.volume_mult, round(ratio, 2)

    def check_vwap_position(self, df_5min: pd.DataFrame, direction: int) -> bool:
        """Check if price is on the correct side of VWAP.

        For LONG:  price must be ABOVE VWAP
        For SHORT: price must be BELOW VWAP
        """
        if len(df_5min) < 10:
            return True  # Not enough data — bypass

        vwap_series = _vwap(df_5min)
        latest_close = df_5min["close"].iloc[-1]
        latest_vwap = vwap_series.iloc[-1]

        if pd.isna(latest_vwap):
            return True  # VWAP not calculable — bypass

        if direction == 1:
            return latest_close > latest_vwap
        elif direction == -1:
            return latest_close < latest_vwap

        return False

    # ──────────────────────────────────────────────────────────────────
    # Main Signal Generator
    # ──────────────────────────────────────────────────────────────────

    def generate(
        self,
        df_5min: pd.DataFrame,
        df_1hr: pd.DataFrame,
    ) -> MomentumSignal:
        """Generate a composite momentum signal.

        All 4 conditions must align for a valid signal:
        1. 1-Hour trend direction
        2. 5-Minute breakout in the same direction
        3. Volume surge on the breakout candle
        4. Price on the correct side of VWAP
        """
        # Null signal
        null_signal = MomentumSignal(
            direction=0, strength=0.0, breakout_price=0.0,
            vwap_price=0.0, trend_1hr=0, volume_ratio=0.0,
        )

        # 1. Get 1-Hour trend
        trend = self.compute_1hr_trend(df_1hr)
        if trend == 0:
            null_signal.reason = "1HR trend is neutral/choppy — no trade"
            return null_signal

        # 2. Get 5-Minute breakout
        breakout = self.compute_5min_breakout(df_5min)
        if breakout == 0:
            null_signal.trend_1hr = trend
            null_signal.reason = "No 5MIN breakout detected"
            return null_signal

        # 3. Check alignment: breakout direction must match hourly trend
        if breakout != trend:
            null_signal.trend_1hr = trend
            null_signal.reason = f"Direction mismatch — 1HR={trend}, 5MIN={breakout}"
            return null_signal

        direction = breakout  # Both agree

        # 4. Volume surge check
        vol_ok, vol_ratio = self.check_volume_surge(df_5min)
        if not vol_ok:
            null_signal.trend_1hr = trend
            null_signal.volume_ratio = vol_ratio
            null_signal.reason = f"Volume ratio {vol_ratio}x < {self.volume_mult}x threshold"
            return null_signal

        # 5. VWAP position check
        vwap_ok = self.check_vwap_position(df_5min, direction)
        if not vwap_ok:
            null_signal.trend_1hr = trend
            null_signal.volume_ratio = vol_ratio
            null_signal.reason = "Price on wrong side of VWAP"
            return null_signal

        # All 4 gates passed — generate signal
        vwap_val = _vwap(df_5min).iloc[-1] if len(df_5min) > 10 else 0.0
        breakout_price = df_5min["close"].iloc[-1]

        # Composite strength (0.0 – 1.0)
        strength = min(1.0, 0.5 + (vol_ratio - self.volume_mult) * 0.2)

        side_str = "CALL (Long)" if direction == 1 else "PUT (Short)"
        reason = (
            f"SIGNAL: {side_str} | 1HR trend aligned | "
            f"5MIN breakout confirmed | Vol {vol_ratio}x | VWAP OK"
        )
        logger.info(reason)

        return MomentumSignal(
            direction=direction,
            strength=strength,
            breakout_price=breakout_price,
            vwap_price=float(vwap_val) if not pd.isna(vwap_val) else 0.0,
            trend_1hr=trend,
            volume_ratio=vol_ratio,
            reason=reason,
        )
