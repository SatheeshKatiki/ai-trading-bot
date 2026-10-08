"""AI Exit Analyzer Agent — Autonomous Multi-Factor Probability Engine.

Monitors open profitable positions to prevent giving back large peak profits
waiting for lagging moving averages (e.g. EMA9/EMA20 crossover lag).

Combines 4 systematic pillars:
1. Pillar 1 (Plan D): Adaptive High-Watermark Retracement Trailing (Tightens giveback as gain scales)
2. Pillar 2: Pure Price Action & Key Support/Resistance (S&R) Proximity & Wick Rejection
3. Pillar 3: Derivative Confirmation (OI Wall or IV Crush Exhaustion Gate)
4. Pillar 4: Time Psychology & Session Regimes (Midday lunch-hour mean-reversion protection)

Outputs a clean `ExitAnalysisResult` containing an Urgency Score (0.0 - 1.0),
an Exit Decision, Mode, and Human/AI Explainable Reason.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence

import numpy as np
import pandas as pd

from shared.indicators import ema, rsi

logger = logging.getLogger(__name__)

TREND_RIDE = "TREND_RIDE"
PEAK_LOCK = "PEAK_LOCK"
ADAPTIVE_PEAK_LOCK = "ADAPTIVE_PEAK_LOCK"
SR_REJECTION = "SR_REJECTION"
DERIVATIVE_EXHAUSTION = "DERIVATIVE_EXHAUSTION"
MIDDAY_EXHAUSTION = "MIDDAY_EXHAUSTION"
FAST_EMA_BREAK = "FAST_EMA_BREAK"
RSI_EXHAUSTION = "RSI_EXHAUSTION"
MOMENTUM_REVERSAL = "MOMENTUM_REVERSAL"


@dataclass(frozen=True)
class ExitAnalysisResult:
    """Detailed verdict and probability metrics returned by ExitAnalyzerAgent."""

    should_exit: bool
    urgency_score: float  # 0.0 to 1.0 (Higher = greater exhaustion / reversal risk)
    mode: str             # TREND_RIDE / PEAK_LOCK / ADAPTIVE_PEAK_LOCK / SR_REJECTION / etc.
    suggested_sl: Optional[float] = None
    reason: str = ""
    factors: Dict[str, Any] = field(default_factory=dict)


class ExitAnalyzerAgent:
    """Autonomous probability evaluator for optimal intraday trade exits."""

    def __init__(
        self,
        min_peak_profit_pts: float = 30.0,
        min_peak_profit_pct: float = 12.0,
        max_giveback_pct: float = 20.0,
        urgency_threshold: float = 0.70,
        w_peak: float = 0.35,
        w_price_action: float = 0.25,
        w_rsi: float = 0.20,
        w_volume: float = 0.20,
        enable_adaptive_tightening: bool = True,
        enable_sr_protection: bool = True,
        enable_derivative_gate: bool = True,
        enable_time_psychology: bool = True,
    ):
        self.min_peak_profit_pts = min_peak_profit_pts
        self.min_peak_profit_pct = min_peak_profit_pct
        self.max_giveback_pct = max_giveback_pct
        self.urgency_threshold = urgency_threshold
        self.w_peak = w_peak
        self.w_price_action = w_price_action
        self.w_rsi = w_rsi
        self.w_volume = w_volume
        self.enable_adaptive_tightening = enable_adaptive_tightening
        self.enable_sr_protection = enable_sr_protection
        self.enable_derivative_gate = enable_derivative_gate
        self.enable_time_psychology = enable_time_psychology

    def evaluate(
        self,
        entry_price: float,
        current_price: float,
        highest_price: float,
        lowest_price: float,
        direction: int,  # P&L-space direction: +1 when the priced instrument rising = profit
        df: Optional[pd.DataFrame] = None,
        is_option_premium: bool = False,
        underlying_direction: Optional[int] = None,
        current_time: Optional[str] = None,
        underlying_price: Optional[float] = None,
        sr_levels: Optional[Sequence[float]] = None,
        iv_change_from_peak: Optional[float] = None,
        oi_resistance_confirmed: Optional[bool] = None,
    ) -> ExitAnalysisResult:
        """Evaluate exit urgency across all 4 pillars."""
        if entry_price <= 0 or current_price <= 0:
            return ExitAnalysisResult(
                should_exit=False,
                urgency_score=0.0,
                mode=TREND_RIDE,
                reason="Invalid price parameters",
            )

        if underlying_direction is None:
            underlying_direction = direction

        significant_peak = (
            entry_price * (self.min_peak_profit_pct / 100.0)
            if is_option_premium
            else self.min_peak_profit_pts
        )

        # ---------------------------------------------------------
        # Factor 1 & Pillar 1: Peak Profit & Adaptive Giveback (Plan D)
        # ---------------------------------------------------------
        score_peak = 0.0
        peak_profit = 0.0
        giveback_pct = 0.0
        peak_gain_pct = 0.0
        effective_max_giveback = self.max_giveback_pct
        suggested_sl = None

        if direction >= 0:  # Bullish / Long / Long Option
            peak_price = max(highest_price, current_price)
            peak_profit = peak_price - entry_price
            giveback_pts = peak_price - current_price
            if entry_price > 0:
                peak_gain_pct = (peak_profit / entry_price) * 100.0

            if peak_profit >= significant_peak and peak_profit > 0:
                giveback_pct = (giveback_pts / peak_profit) * 100.0

                # Plan D: Adaptive tightening as profit expands
                if self.enable_adaptive_tightening:
                    if peak_gain_pct >= 100.0:
                        effective_max_giveback = 8.0   # Locked in >=92% of peak on 2x+ moves
                    elif peak_gain_pct >= 75.0:
                        effective_max_giveback = 10.0  # Locked in >=90% of peak
                    elif peak_gain_pct >= 50.0:
                        effective_max_giveback = 14.0  # Locked in >=86% of peak
                    elif peak_gain_pct >= 33.0:
                        effective_max_giveback = 18.0
                    else:
                        effective_max_giveback = self.max_giveback_pct

                suggested_sl = peak_price - (peak_profit * (effective_max_giveback / 100.0))

                if giveback_pct >= effective_max_giveback:
                    score_peak = min(1.0, 0.70 + (giveback_pct - effective_max_giveback) * 0.03)
                elif giveback_pct >= (effective_max_giveback * 0.5):
                    score_peak = 0.45
        else:  # Bearish / Short
            trough_price = min(lowest_price, current_price)
            peak_profit = entry_price - trough_price
            giveback_pts = current_price - trough_price
            if entry_price > 0:
                peak_gain_pct = (peak_profit / entry_price) * 100.0

            if peak_profit >= significant_peak and peak_profit > 0:
                giveback_pct = (giveback_pts / peak_profit) * 100.0

                if self.enable_adaptive_tightening:
                    if peak_gain_pct >= 100.0:
                        effective_max_giveback = 8.0
                    elif peak_gain_pct >= 75.0:
                        effective_max_giveback = 10.0
                    elif peak_gain_pct >= 50.0:
                        effective_max_giveback = 14.0
                    elif peak_gain_pct >= 33.0:
                        effective_max_giveback = 18.0
                    else:
                        effective_max_giveback = self.max_giveback_pct

                suggested_sl = trough_price + (peak_profit * (effective_max_giveback / 100.0))

                if giveback_pct >= effective_max_giveback:
                    score_peak = min(1.0, 0.70 + (giveback_pct - effective_max_giveback) * 0.03)
                elif giveback_pct >= (effective_max_giveback * 0.5):
                    score_peak = 0.45

        # ---------------------------------------------------------
        # Factor 2 & Pillar 2: Price Action, EMA 9 Break & S&R Proximity
        # ---------------------------------------------------------
        score_pa = 0.0
        has_ema9_break = False
        has_rejection_wick = False
        at_sr_zone = False
        nearest_sr = None

        curr_underlying = underlying_price
        if df is not None and len(df) >= 10 and "close" in df.columns:
            close_series = df["close"]
            ema9_series = ema(close_series, 9)
            last_close = float(close_series.iloc[-1])
            last_ema9 = float(ema9_series.iloc[-1])
            if curr_underlying is None:
                curr_underlying = last_close

            if "high" in df.columns and "low" in df.columns and "open" in df.columns:
                last_open = float(df["open"].iloc[-1])
                last_high = float(df["high"].iloc[-1])
                last_low = float(df["low"].iloc[-1])
                candle_range = max(0.001, last_high - last_low)

                if underlying_direction >= 0:
                    # Close broke below EMA 9
                    if last_close < last_ema9:
                        has_ema9_break = True
                        score_pa = 1.0 if peak_profit >= significant_peak else 0.70
                    # Upper rejection wick > 30% of total candle range
                    upper_wick = last_high - max(last_open, last_close)
                    if (upper_wick / candle_range) >= 0.30:
                        has_rejection_wick = True
                        score_pa = max(score_pa, 0.50)
                else:
                    # Close broke above EMA 9
                    if last_close > last_ema9:
                        has_ema9_break = True
                        score_pa = 1.0 if peak_profit >= significant_peak else 0.70
                    # Lower rejection wick > 30% of total candle range
                    lower_wick = min(last_open, last_close) - last_low
                    if (lower_wick / candle_range) >= 0.30:
                        has_rejection_wick = True
                        score_pa = max(score_pa, 0.50)

        # Check S&R Proximity
        if self.enable_sr_protection and sr_levels and curr_underlying and curr_underlying > 0:
            valid_sr = [float(s) for s in sr_levels if float(s) > 0]
            if valid_sr:
                dist_tuples = [(abs(curr_underlying - s) / curr_underlying * 100.0, s) for s in valid_sr]
                min_dist_pct, nearest_sr = min(dist_tuples, key=lambda x: x[0])
                # Within 0.35% of key S&R level
                if min_dist_pct <= 0.35:
                    at_sr_zone = True
                    if has_rejection_wick or has_ema9_break:
                        score_pa = 1.0
                    else:
                        score_pa = max(score_pa, 0.65)

        score_pa = min(1.0, score_pa)

        # ---------------------------------------------------------
        # Factor 3: RSI Momentum Exhaustion (Weight: 20%)
        # ---------------------------------------------------------
        score_rsi = 0.0
        if df is not None and len(df) >= 15 and "close" in df.columns:
            try:
                rsi_series = rsi(df["close"], window=14)
                rsi_ma_series = ema(rsi_series, window=20)
                curr_rsi = float(rsi_series.iloc[-1])
                curr_rsi_ma = float(rsi_ma_series.iloc[-1])
                prev_rsi = float(rsi_series.iloc[-2])

                if underlying_direction >= 0:
                    # CE: Was overbought (> 65) and hooked down or crossed below RSI-MA
                    if (prev_rsi >= 65.0 or curr_rsi >= 65.0) and curr_rsi < prev_rsi:
                        score_rsi += 0.50
                    if curr_rsi < curr_rsi_ma:
                        score_rsi += 0.50
                else:
                    # PE: Was oversold (< 35) and hooked up or crossed above RSI-MA
                    if (prev_rsi <= 35.0 or curr_rsi <= 35.0) and curr_rsi > prev_rsi:
                        score_rsi += 0.50
                    if curr_rsi > curr_rsi_ma:
                        score_rsi += 0.50

                score_rsi = min(1.0, score_rsi)
            except Exception:
                score_rsi = 0.0

        # ---------------------------------------------------------
        # Factor 4: Volume Deceleration Divergence (Weight: 20%)
        # ---------------------------------------------------------
        score_vol = 0.0
        if df is not None and len(df) >= 10 and "volume" in df.columns:
            try:
                vol_series = df["volume"]
                if vol_series.sum() > 0:
                    vol_ma = float(vol_series.rolling(10).mean().iloc[-1])
                    last_vol = float(vol_series.iloc[-1])
                    if vol_ma > 0 and last_vol < (vol_ma * 0.65):
                        score_vol = 0.80
            except Exception:
                score_vol = 0.0

        # ---------------------------------------------------------
        # Pillar 3: Derivative Confirmation (OI or IV Gate)
        # ---------------------------------------------------------
        has_iv_exhaustion = False
        has_oi_wall = False
        if self.enable_derivative_gate:
            if iv_change_from_peak is not None and iv_change_from_peak <= -1.5:
                has_iv_exhaustion = True
            if oi_resistance_confirmed is not None and bool(oi_resistance_confirmed):
                has_oi_wall = True

        has_deriv_exhaustion = has_iv_exhaustion or has_oi_wall

        # ---------------------------------------------------------
        # Pillar 4: Time Psychology (Session Regime)
        # ---------------------------------------------------------
        time_regime = "STANDARD"
        time_urgency_boost = 0.0
        is_midday_lunch_hour = False
        if self.enable_time_psychology and current_time:
            try:
                t_str = str(current_time).strip().split(" ")[-1]
                t_parts = t_str.split(":")
                hh, mm = int(t_parts[0]), int(t_parts[1])
                t_min = hh * 60 + mm
                # 11:30 (690 min) to 13:30 (810 min) is midday consolidation window
                if 690 <= t_min <= 810:
                    is_midday_lunch_hour = True
                    time_regime = "MIDDAY_CHOP"
                    time_urgency_boost = 0.15
                elif t_min < 630:  # Before 10:30
                    time_regime = "MORNING_MOMENTUM"
                    time_urgency_boost = -0.05
            except Exception:
                pass

        # ---------------------------------------------------------
        # Aggregate Multi-Factor Probability
        # ---------------------------------------------------------
        base_urgency = (
            (score_peak * self.w_peak) +
            (score_pa * self.w_price_action) +
            (score_rsi * self.w_rsi) +
            (score_vol * self.w_volume)
        )
        deriv_boost = 0.15 if has_deriv_exhaustion else 0.0
        total_urgency = float(np.clip(base_urgency + deriv_boost + time_urgency_boost, 0.0, 1.0))
        total_urgency = round(total_urgency, 3)

        factors = {
            "peak_giveback": round(score_peak, 2),
            "price_action": round(score_pa, 2),
            "rsi_momentum": round(score_rsi, 2),
            "volume_decel": round(score_vol, 2),
            "giveback_pct": round(giveback_pct, 1),
            "peak_profit": round(peak_profit, 2),
            "peak_gain_pct": round(peak_gain_pct, 1),
            "adaptive_giveback_limit": round(effective_max_giveback, 1),
            "at_sr_zone": float(at_sr_zone),
            "deriv_exhaustion": float(has_deriv_exhaustion),
            "iv_exhaustion": float(has_iv_exhaustion),
            "oi_wall": float(has_oi_wall),
            "time_regime": time_regime,
            "ema9_break": float(has_ema9_break),
            "rejection_wick": float(has_rejection_wick),
            "significant_peak": round(significant_peak, 2),
        }

        # ---------------------------------------------------------
        # Exit Decision Logic (Ranked Priority)
        # ---------------------------------------------------------
        should_exit = False
        mode = TREND_RIDE
        reason = "Trend intact. Urgency low."

        # Case 1: S&R Rejection + Derivative (OI/IV) Trigger (Structural Wall)
        if at_sr_zone and has_deriv_exhaustion and peak_gain_pct >= 33.0 and giveback_pct >= 5.0:
            should_exit = True
            mode = SR_REJECTION
            deriv_label = "IV Crush" if has_iv_exhaustion else "OI Wall"
            sr_info = f" near S&R level {nearest_sr:.1f}" if nearest_sr is not None else ""
            reason = (
                f"S&R Wall Rejection + {deriv_label} after +{peak_gain_pct:.1f}% peak "
                f"(Gave back {giveback_pct:.1f}%{sr_info})."
            )

        # Case 2: Adaptive Peak Lock Trigger (Plan D: Giveback exceeded adaptive threshold)
        elif giveback_pct >= effective_max_giveback and peak_profit >= significant_peak:
            should_exit = True
            mode = ADAPTIVE_PEAK_LOCK if effective_max_giveback < self.max_giveback_pct else PEAK_LOCK
            reason = (
                f"Adaptive Peak Lock (Plan D): Gave back {giveback_pct:.1f}% >= limit {effective_max_giveback:.1f}% "
                f"from high watermark (Peak +{peak_profit:.1f} pts / +{peak_gain_pct:.1f}%, current {current_price:.1f})."
            )

        # Case 3: Midday Lunch-Hour Reversal Protection
        elif is_midday_lunch_hour and peak_gain_pct >= 50.0 and (giveback_pct >= (effective_max_giveback * 0.75) or has_deriv_exhaustion):
            should_exit = True
            mode = MIDDAY_EXHAUSTION
            reason = (
                f"Midday Lunch-Hour Mean Reversion Protection: +{peak_gain_pct:.1f}% peak, "
                f"giveback {giveback_pct:.1f}% during midday consolidation window."
            )

        # Case 4: Fast EMA 9 Break on Profitable Position with Giveback >= 15%
        elif has_ema9_break and peak_profit >= significant_peak and giveback_pct >= 15.0:
            should_exit = True
            mode = FAST_EMA_BREAK
            reason = f"Fast EMA9 Close Break after +{peak_profit:.1f} pts gain (Gave back {giveback_pct:.1f}%)."

        # Case 5: Multi-Factor High Urgency Score >= Threshold
        elif total_urgency >= self.urgency_threshold:
            should_exit = True
            if has_ema9_break:
                mode = FAST_EMA_BREAK
                reason = f"Fast EMA9 Break with {total_urgency*100:.0f}% Reversal Urgency."
            elif score_rsi >= 0.8:
                mode = RSI_EXHAUSTION
                reason = f"RSI Momentum Exhaustion with {total_urgency*100:.0f}% Reversal Urgency."
            elif at_sr_zone:
                mode = SR_REJECTION
                reason = f"S&R Structure Stall with {total_urgency*100:.0f}% Reversal Urgency."
            elif has_deriv_exhaustion:
                mode = DERIVATIVE_EXHAUSTION
                reason = f"Derivative Exhaustion (OI/IV) with {total_urgency*100:.0f}% Reversal Urgency."
            else:
                mode = MOMENTUM_REVERSAL
                reason = f"Multi-factor Momentum Reversal with {total_urgency*100:.0f}% Urgency."

        # Case 6: Trending Ride with moderate caution
        elif total_urgency >= 0.40:
            mode = PEAK_LOCK
            reason = f"Caution: Urgency {total_urgency*100:.0f}%. Holding with tight trailing stop."

        return ExitAnalysisResult(
            should_exit=should_exit,
            urgency_score=total_urgency,
            mode=mode,
            suggested_sl=suggested_sl,
            reason=reason,
            factors=factors,
        )
