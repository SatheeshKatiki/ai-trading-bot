"""AI Exit Analyzer Agent — Autonomous Multi-Factor Probability Engine.

Monitors open profitable positions to prevent giving back large peak profits
waiting for lagging moving averages (e.g. EMA9/EMA20 crossover lag).

Evaluates 4 core probability dimensions:
1. Peak Profit Giveback (High-Watermark Retracement) [Weight: 35%]
2. Price Action & Fast EMA 9 Close Break [Weight: 25%]
3. RSI Momentum Exhaustion & Overbought/Oversold Hook [Weight: 20%]
4. Volume Deceleration Divergence [Weight: 20%]

Outputs a clean `ExitAnalysisResult` containing an Urgency Score (0.0 - 1.0),
an Exit Decision, Mode, and Human/AI Explainable Reason.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from shared.indicators import ema, rsi

logger = logging.getLogger(__name__)

TREND_RIDE = "TREND_RIDE"
PEAK_LOCK = "PEAK_LOCK"
FAST_EMA_BREAK = "FAST_EMA_BREAK"
RSI_EXHAUSTION = "RSI_EXHAUSTION"
MOMENTUM_REVERSAL = "MOMENTUM_REVERSAL"


@dataclass(frozen=True)
class ExitAnalysisResult:
    """Detailed verdict and probability metrics returned by ExitAnalyzerAgent."""

    should_exit: bool
    urgency_score: float  # 0.0 to 1.0 (Higher = greater exhaustion / reversal risk)
    mode: str             # TREND_RIDE / PEAK_LOCK / FAST_EMA_BREAK / RSI_EXHAUSTION / MOMENTUM_REVERSAL
    suggested_sl: Optional[float] = None
    reason: str = ""
    factors: Dict[str, float] = field(default_factory=dict)


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
    ):
        self.min_peak_profit_pts = min_peak_profit_pts
        self.min_peak_profit_pct = min_peak_profit_pct
        self.max_giveback_pct = max_giveback_pct
        self.urgency_threshold = urgency_threshold
        self.w_peak = w_peak
        self.w_price_action = w_price_action
        self.w_rsi = w_rsi
        self.w_volume = w_volume

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
    ) -> ExitAnalysisResult:
        """Evaluate exit urgency and determine if an immediate peak exit should fire.

        Two different "directions" are in play and conflating them inverts the
        momentum read on every PUT:

        ``direction``
            P&L space, i.e. the space `entry_price` / `current_price` /
            `highest_price` live in. A *bought* option — CE or PE alike — profits
            when its own premium rises, so this is ``+1`` for any long option.
        ``underlying_direction``
            Thesis space: ``+1`` for a CALL, ``-1`` for a PUT. Defaults to
            ``direction`` for cash/futures, where the two coincide.

        Factor 1 (peak giveback) is a P&L question and uses ``direction``.
        Factors 2-4 (EMA9 break, RSI exhaustion, volume fade) are momentum
        questions about the UNDERLYING and use ``underlying_direction``: for a
        PUT holder a close *below* EMA9 confirms the thesis, it does not
        threaten it. Reading them off ``direction`` would have called every
        winning PUT a reversal.

        ``df`` should therefore be the UNDERLYING index frame, not the option's
        own premium candles — premium is a non-linear function of spot, IV and
        time, so EMA/RSI computed on it is noise. This mirrors the rule the
        Fibonacci trail in SmartExitEngine already follows: the thesis is about
        where the index goes; only the resulting stop is expressed in premium.
        """
        if entry_price <= 0 or current_price <= 0:
            return ExitAnalysisResult(
                should_exit=False,
                urgency_score=0.0,
                mode=TREND_RIDE,
                reason="Invalid price parameters",
            )

        if underlying_direction is None:
            underlying_direction = direction

        # Single definition of "a peak worth protecting", used by BOTH the
        # factor scoring and the exit decisions below. Previously Factor 1
        # honoured `is_option_premium` (12% of entry premium) while the
        # PEAK_LOCK / FAST_EMA_BREAK decisions re-tested a hardcoded
        # `>= self.min_peak_profit_pts` (30 points) -- so on a 150-rupee
        # premium a 12% (18-point) peak scored as significant but could never
        # actually fire an exit. The headline protection was unreachable on
        # exactly the instrument it was written for.
        significant_peak = (
            entry_price * (self.min_peak_profit_pct / 100.0)
            if is_option_premium
            else self.min_peak_profit_pts
        )

        # ---------------------------------------------------------
        # Factor 1: Peak Profit & Giveback (Weight: 35%)
        # ---------------------------------------------------------
        score_peak = 0.0
        peak_profit = 0.0
        giveback_pct = 0.0
        suggested_sl = None

        if direction >= 0:  # Bullish / Long / CALL
            peak_price = max(highest_price, current_price)
            peak_profit = peak_price - entry_price
            giveback_pts = peak_price - current_price
            
            if peak_profit >= significant_peak and peak_profit > 0:
                giveback_pct = (giveback_pts / peak_profit) * 100.0
                # Ratchet suggested SL to lock in 80% of peak profit (giveback of 20%)
                suggested_sl = peak_price - (peak_profit * (self.max_giveback_pct / 100.0))
                
                if giveback_pct >= self.max_giveback_pct:
                    # Linearly scale score between max_giveback_pct (0.70) and 35% giveback (1.0)
                    score_peak = min(1.0, 0.70 + (giveback_pct - self.max_giveback_pct) * 0.02)
                elif giveback_pct >= (self.max_giveback_pct * 0.5):
                    score_peak = 0.40
        else:  # Bearish / Short / PUT
            trough_price = min(lowest_price, current_price)
            peak_profit = entry_price - trough_price
            giveback_pts = current_price - trough_price
            
            if peak_profit >= significant_peak and peak_profit > 0:
                giveback_pct = (giveback_pts / peak_profit) * 100.0
                suggested_sl = trough_price + (peak_profit * (self.max_giveback_pct / 100.0))
                
                if giveback_pct >= self.max_giveback_pct:
                    score_peak = min(1.0, 0.70 + (giveback_pct - self.max_giveback_pct) * 0.02)
                elif giveback_pct >= (self.max_giveback_pct * 0.5):
                    score_peak = 0.40

        # ---------------------------------------------------------
        # Factor 2: Price Action & Fast EMA 9 Break (Weight: 25%)
        # ---------------------------------------------------------
        score_pa = 0.0
        has_ema9_break = False
        has_rejection_wick = False

        if df is not None and len(df) >= 10 and "close" in df.columns:
            close_series = df["close"]
            ema9_series = ema(close_series, 9)
            last_close = float(close_series.iloc[-1])
            last_ema9 = float(ema9_series.iloc[-1])
            
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
                        # Fading volume on exhaustion
                        score_vol = 0.80
            except Exception:
                score_vol = 0.0

        # ---------------------------------------------------------
        # Aggregate Multi-Factor Probability
        # ---------------------------------------------------------
        total_urgency = (
            (score_peak * self.w_peak) +
            (score_pa * self.w_price_action) +
            (score_rsi * self.w_rsi) +
            (score_vol * self.w_volume)
        )
        total_urgency = round(float(np.clip(total_urgency, 0.0, 1.0)), 3)

        factors = {
            "peak_giveback": round(score_peak, 2),
            "price_action": round(score_pa, 2),
            "rsi_momentum": round(score_rsi, 2),
            "volume_decel": round(score_vol, 2),
            "giveback_pct": round(giveback_pct, 1),
            "peak_profit": round(peak_profit, 2),
            # Which sub-signal drove Factor 2. Both were computed but only
            # folded into `score_pa`, leaving `has_rejection_wick` flagged by
            # the linter as dead. They are the explainable part of the verdict,
            # so surface them instead of discarding them.
            "ema9_break": float(has_ema9_break),
            "rejection_wick": float(has_rejection_wick),
            # The bar the peak test was measured against, so a logged exit can
            # be reconciled after the fact without re-deriving it.
            "significant_peak": round(significant_peak, 2),
        }

        # ---------------------------------------------------------
        # Exit Decision Logic
        # ---------------------------------------------------------
        should_exit = False
        mode = TREND_RIDE
        reason = "Trend intact. Urgency low."

        # Case 1: Hard Peak Lock Trigger (Gave back >= max_giveback_pct of significant peak)
        if giveback_pct >= self.max_giveback_pct and peak_profit >= significant_peak:
            should_exit = True
            mode = PEAK_LOCK
            reason = (
                f"Peak Lock Triggered: Gave back {giveback_pct:.1f}% from high watermark "
                f"(Peak +{peak_profit:.1f} pts, current {current_price:.1f})."
            )

        # Case 2: Fast EMA 9 Break on Profitable Position with Giveback >= 15%
        elif has_ema9_break and peak_profit >= significant_peak and giveback_pct >= 15.0:
            should_exit = True
            mode = FAST_EMA_BREAK
            reason = f"Fast EMA9 Close Break after +{peak_profit:.1f} pts gain (Gave back {giveback_pct:.1f}%)."

        # Case 3: Multi-Factor High Urgency Score >= Threshold
        elif total_urgency >= self.urgency_threshold:
            should_exit = True
            if has_ema9_break:
                mode = FAST_EMA_BREAK
                reason = f"Fast EMA9 Break with {total_urgency*100:.0f}% Reversal Urgency."
            elif score_rsi >= 0.8:
                mode = RSI_EXHAUSTION
                reason = f"RSI Momentum Exhaustion with {total_urgency*100:.0f}% Reversal Urgency."
            else:
                mode = MOMENTUM_REVERSAL
                reason = f"Multi-factor Momentum Reversal with {total_urgency*100:.0f}% Urgency."

        # Case 4: Trending Ride with moderate caution
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
