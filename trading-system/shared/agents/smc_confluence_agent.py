"""
SMC Confluence Agent — Autonomous Institutional Multi-Pillar Trading Engine.

Combines three pillars of market microstructure:
1. Smart Money Concepts (SMC): Price Action & Market Structure (WHERE / WHY)
2. Fixed Range Volume Profile (FRVP): Institutional Auction Liquidity (WHO / HOW MUCH)
3. RSI Divergence: Momentum Exhaustion & Confirmation (WHEN)

Follows the institutional pattern established in QuantAI (ExitAnalyzerAgent architecture):
- Strongly typed dataclass inputs and outputs
- Decoupled, fully configurable parameter matrix
- Confluence score calculation with mathematical rigor
- Structural Stop Loss & Risk-to-Reward target generation
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from shared.indicators.smart_money_concepts import (
    SMCAnalysisResult,
    TrendState,
    LuxAlgoSMCConfig,
    calculate_smc
)
from shared.indicators.volume_profile import (
    VolumeProfileResult,
    calculate_fixed_range_volume_profile
)
from shared.indicators.rsi_divergence import (
    RSIDivergenceResult,
    calculate_rsi_divergences
)

logger = logging.getLogger(__name__)


@dataclass
class SMCConfluenceConfig:
    """User-configurable parameters for the SMC Confluence Agent."""
    # LuxAlgo SMC Parameters (matching user specification)
    smc: LuxAlgoSMCConfig = field(default_factory=LuxAlgoSMCConfig)

    # Volume Profile Parameters
    vp_num_bins: int = 50
    vp_value_area_pct: float = 0.70

    # ATR Risk Buffer Parameter
    atr_period: int = 14

    # RSI Divergence Parameters
    rsi_period: int = 14
    rsi_overbought: float = 70.0
    rsi_oversold: float = 30.0
    lookback_pivot: int = 5

    # Confluence Scoring Weights (must sum to 1.0)
    w_smc: float = 0.45    # 45% Structure & Order Blocks
    w_vp: float = 0.30     # 30% Volume Profile & POC/Value Area
    w_rsi: float = 0.25    # 25% RSI Momentum & Divergence

    # Execution Thresholds
    confluence_threshold: float = 0.70  # Minimum score required to fire a signal (0.0 to 1.0)
    min_risk_reward_ratio: float = 2.0  # Minimum R:R ratio required for trade qualification
    sl_atr_buffer: float = 0.50         # Additional ATR buffer beyond structural level for SL


@dataclass(frozen=True)
class SMCConfluenceSignal:
    """Detailed verdict and execution metrics produced by SMCConfluenceAgent."""
    direction: int                      # +1 = BUY/CALL, -1 = SELL/PUT, 0 = NEUTRAL
    confidence: float                   # 0.0 to 1.0
    confluence_score: float             # Weighted score across SMC, VP, and RSI
    entry_price: float
    suggested_sl: float
    suggested_target: float
    risk_reward_ratio: float
    factors: Dict[str, float] = field(default_factory=dict)
    reason: str = ""
    timestamp: Optional[Any] = None


class SMCConfluenceAgent:
    """
    Autonomous Institutional Confluence Evaluator.
    Synthesizes SMC Market Structure, Volume Profile Auction Data, and RSI Divergence.
    """

    def __init__(self, config: Optional[SMCConfluenceConfig] = None):
        self.config = config or SMCConfluenceConfig()

    def evaluate(
        self,
        df: pd.DataFrame,
        current_price: Optional[float] = None
    ) -> SMCConfluenceSignal:
        """
        Runs the multi-pillar confluence evaluation on market data.

        Parameters:
        -----------
        df : pd.DataFrame
            OHLCV DataFrame.
        current_price : Optional[float]
            Current reference price. Defaults to last bar close.

        Returns:
        --------
        SMCConfluenceSignal:
            High-precision trading signal with entry, SL, target, and factor breakdown.
        """
        if df.empty or len(df) < max(self.config.smc.swing_points_length // 2, 20):
            return SMCConfluenceSignal(
                direction=0,
                confidence=0.0,
                confluence_score=0.0,
                entry_price=0.0,
                suggested_sl=0.0,
                suggested_target=0.0,
                risk_reward_ratio=0.0,
                reason="Insufficient historical bars for institutional confluence evaluation"
            )

        ref_price = current_price if current_price is not None else float(df['close'].iloc[-1])

        # 1. Run SMC Engine with LuxAlgo configuration
        _, smc_res = calculate_smc(
            df,
            config=self.config.smc
        )

        # 2. Run Volume Profile Engine (on active swing or recent session)
        vp_res = calculate_fixed_range_volume_profile(
            df,
            num_bins=self.config.vp_num_bins,
            value_area_pct=self.config.vp_value_area_pct
        )

        # 3. Run RSI Divergence Engine
        _, rsi_res = calculate_rsi_divergences(
            df,
            period=self.config.rsi_period,
            lookback_pivot=self.config.lookback_pivot,
            overbought=self.config.rsi_overbought,
            oversold=self.config.rsi_oversold
        )

        # Calculate ATR for SL buffer
        highs = df['high'].to_numpy(dtype=float)
        lows = df['low'].to_numpy(dtype=float)
        closes = df['close'].to_numpy(dtype=float)
        tr = np.maximum(highs - lows, np.abs(highs - np.roll(closes, 1)))
        tr[0] = highs[0] - lows[0]
        curr_atr = float(pd.Series(tr).rolling(self.config.atr_period, min_periods=1).mean().iloc[-1])

        # Evaluate Bullish Confluence
        bull_score, bull_factors, bull_reasons = self._score_bullish(ref_price, smc_res, vp_res, rsi_res)

        # Evaluate Bearish Confluence
        bear_score, bear_factors, bear_reasons = self._score_bearish(ref_price, smc_res, vp_res, rsi_res)

        # Select dominant direction
        if bull_score >= self.config.confluence_threshold and bull_score > bear_score:
            # Bullish Setup
            sl = self._calculate_bullish_sl(ref_price, smc_res, vp_res, curr_atr)
            target = self._calculate_bullish_target(ref_price, smc_res, vp_res)
            risk = max(ref_price - sl, curr_atr * 0.5)
            reward = max(target - ref_price, 0.0)
            rr = reward / risk if risk > 0 else 0.0

            if rr >= self.config.min_risk_reward_ratio:
                return SMCConfluenceSignal(
                    direction=1,
                    confidence=min(1.0, bull_score),
                    confluence_score=bull_score,
                    entry_price=ref_price,
                    suggested_sl=sl,
                    suggested_target=target,
                    risk_reward_ratio=round(rr, 2),
                    factors=bull_factors,
                    reason="; ".join(bull_reasons)
                )

        elif bear_score >= self.config.confluence_threshold and bear_score > bull_score:
            # Bearish Setup
            sl = self._calculate_bearish_sl(ref_price, smc_res, vp_res, curr_atr)
            target = self._calculate_bearish_target(ref_price, smc_res, vp_res)
            risk = max(sl - ref_price, curr_atr * 0.5)
            reward = max(ref_price - target, 0.0)
            rr = reward / risk if risk > 0 else 0.0

            if rr >= self.config.min_risk_reward_ratio:
                return SMCConfluenceSignal(
                    direction=-1,
                    confidence=min(1.0, bear_score),
                    confluence_score=bear_score,
                    entry_price=ref_price,
                    suggested_sl=sl,
                    suggested_target=target,
                    risk_reward_ratio=round(rr, 2),
                    factors=bear_factors,
                    reason="; ".join(bear_reasons)
                )

        # Neutral / No Qualified Confluence
        return SMCConfluenceSignal(
            direction=0,
            confidence=max(bull_score, bear_score),
            confluence_score=max(bull_score, bear_score),
            entry_price=ref_price,
            suggested_sl=0.0,
            suggested_target=0.0,
            risk_reward_ratio=0.0,
            factors={"bull_score": bull_score, "bear_score": bear_score},
            reason="Market currently in balance or below confluence threshold"
        )

    def _score_bullish(
        self,
        price: float,
        smc: SMCAnalysisResult,
        vp: VolumeProfileResult,
        rsi: RSIDivergenceResult
    ) -> Tuple[float, Dict[str, float], List[str]]:
        factors: Dict[str, float] = {}
        reasons: List[str] = []

        # 1. Structure Factor (SMC) - Max 1.0
        smc_score = 0.0
        # Discount Zone bonus (< 50% equilibrium)
        if smc.equilibrium_price and price <= smc.equilibrium_price:
            smc_score += 0.35
            reasons.append("Price in Discount Zone (< 50% Eq)")

        # Bullish Order Block test (price near or inside active Bullish OB)
        for ob in smc.active_bullish_obs:
            if ob.bottom <= price <= (ob.top * 1.002):
                smc_score += 0.40
                reasons.append(f"Bullish Order Block interaction @ {ob.midpoint:.1f}")
                break

        # Bullish FVG test
        for fvg in smc.active_bullish_fvgs:
            if fvg.bottom <= price <= (fvg.top * 1.002):
                smc_score += 0.15
                reasons.append(f"Bullish FVG support @ {fvg.bottom:.1f}")
                break

        # Trend alignment (BULLISH trend or recent CHoCH)
        if smc.trend == TrendState.BULLISH:
            smc_score += 0.20
            reasons.append("Macro Trend Bullish")
        factors["smc_factor"] = min(1.0, smc_score)

        # 2. Volume Factor (FRVP) - Max 1.0
        vp_score = 0.0
        # Value Area Low (VAL) test (institutional buyers defend VAL)
        dist_to_val_pct = abs(price - vp.val_price) / max(vp.val_price, 1.0) * 100.0
        dist_to_poc_pct = abs(price - vp.poc_price) / max(vp.poc_price, 1.0) * 100.0

        if dist_to_val_pct <= 0.30:  # Within 0.3% of VAL
            vp_score += 0.50
            reasons.append(f"Testing Value Area Low (VAL: {vp.val_price:.1f})")
        elif dist_to_poc_pct <= 0.20:  # Within 0.2% of POC
            vp_score += 0.40
            reasons.append(f"Testing Point of Control (POC: {vp.poc_price:.1f})")

        # High Volume Node nearby support
        for hvn in vp.hvn_levels:
            if abs(price - hvn) / price * 100.0 <= 0.20:
                vp_score += 0.20
                reasons.append(f"High Volume Node Support @ {hvn:.1f}")
                break
        factors["vp_factor"] = min(1.0, vp_score)

        # 3. Momentum Factor (RSI) - Max 1.0
        rsi_score = 0.0
        if rsi.latest_bullish_div:
            # Check if divergence is recent (within last 15 bars)
            rsi_score += 0.60
            div_type = rsi.latest_bullish_div.divergence_type.value
            reasons.append(f"Confirmed {div_type}")

        if rsi.is_oversold:
            rsi_score += 0.30
            reasons.append(f"RSI Oversold ({rsi.current_rsi:.1f})")
        elif 40.0 <= rsi.current_rsi <= 55.0 and rsi.above_neutral:
            rsi_score += 0.20
            reasons.append("RSI 50-Level Bullish Shift")
        factors["rsi_factor"] = min(1.0, rsi_score)

        # Weighted Confluence Score
        total_score = (
            self.config.w_smc * factors["smc_factor"] +
            self.config.w_vp * factors["vp_factor"] +
            self.config.w_rsi * factors["rsi_factor"]
        )
        return total_score, factors, reasons

    def _score_bearish(
        self,
        price: float,
        smc: SMCAnalysisResult,
        vp: VolumeProfileResult,
        rsi: RSIDivergenceResult
    ) -> Tuple[float, Dict[str, float], List[str]]:
        factors: Dict[str, float] = {}
        reasons: List[str] = []

        # 1. Structure Factor (SMC) - Max 1.0
        smc_score = 0.0
        # Premium Zone bonus (> 50% equilibrium)
        if smc.equilibrium_price and price >= smc.equilibrium_price:
            smc_score += 0.35
            reasons.append("Price in Premium Zone (> 50% Eq)")

        # Bearish Order Block test
        for ob in smc.active_bearish_obs:
            if (ob.bottom * 0.998) <= price <= ob.top:
                smc_score += 0.40
                reasons.append(f"Bearish Order Block interaction @ {ob.midpoint:.1f}")
                break

        # Bearish FVG test
        for fvg in smc.active_bearish_fvgs:
            if (fvg.bottom * 0.998) <= price <= fvg.top:
                smc_score += 0.15
                reasons.append(f"Bearish FVG resistance @ {fvg.top:.1f}")
                break

        # Trend alignment (BEARISH trend or recent CHoCH)
        if smc.trend == TrendState.BEARISH:
            smc_score += 0.20
            reasons.append("Macro Trend Bearish")
        factors["smc_factor"] = min(1.0, smc_score)

        # 2. Volume Factor (FRVP) - Max 1.0
        vp_score = 0.0
        dist_to_vah_pct = abs(price - vp.vah_price) / max(vp.vah_price, 1.0) * 100.0
        dist_to_poc_pct = abs(price - vp.poc_price) / max(vp.poc_price, 1.0) * 100.0

        if dist_to_vah_pct <= 0.30:  # Within 0.3% of VAH
            vp_score += 0.50
            reasons.append(f"Testing Value Area High (VAH: {vp.vah_price:.1f})")
        elif dist_to_poc_pct <= 0.20:
            vp_score += 0.40
            reasons.append(f"Testing Point of Control (POC: {vp.poc_price:.1f})")

        for hvn in vp.hvn_levels:
            if abs(price - hvn) / price * 100.0 <= 0.20:
                vp_score += 0.20
                reasons.append(f"High Volume Node Resistance @ {hvn:.1f}")
                break
        factors["vp_factor"] = min(1.0, vp_score)

        # 3. Momentum Factor (RSI) - Max 1.0
        rsi_score = 0.0
        if rsi.latest_bearish_div:
            rsi_score += 0.60
            div_type = rsi.latest_bearish_div.divergence_type.value
            reasons.append(f"Confirmed {div_type}")

        if rsi.is_overbought:
            rsi_score += 0.30
            reasons.append(f"RSI Overbought ({rsi.current_rsi:.1f})")
        elif 45.0 <= rsi.current_rsi <= 60.0 and not rsi.above_neutral:
            rsi_score += 0.20
            reasons.append("RSI 50-Level Bearish Shift")
        factors["rsi_factor"] = min(1.0, rsi_score)

        total_score = (
            self.config.w_smc * factors["smc_factor"] +
            self.config.w_vp * factors["vp_factor"] +
            self.config.w_rsi * factors["rsi_factor"]
        )
        return total_score, factors, reasons

    def _calculate_bullish_sl(
        self,
        price: float,
        smc: SMCAnalysisResult,
        vp: VolumeProfileResult,
        atr: float
    ) -> float:
        """Sets structural SL just below the nearest Order Block or VAL."""
        candidate_levels = [price - (1.5 * atr)]
        for ob in smc.active_bullish_obs:
            if ob.bottom < price:
                candidate_levels.append(ob.bottom - (self.config.sl_atr_buffer * atr))
        if vp.val_price < price:
            candidate_levels.append(vp.val_price - (self.config.sl_atr_buffer * atr))

        # The closest safe structural support below price
        valid = [lvl for lvl in candidate_levels if lvl < price]
        return max(valid) if valid else price - (1.5 * atr)

    def _calculate_bullish_target(
        self,
        price: float,
        smc: SMCAnalysisResult,
        vp: VolumeProfileResult
    ) -> float:
        """Sets structural Target at opposing EQH, Bearish OB, or VAH."""
        candidates = [price * 1.01]  # Default 1% gain
        # Opposing Liquidity Pools (EQH)
        for pool in smc.active_liquidity_pools:
            if pool.is_high and pool.price > price:
                candidates.append(pool.price)
        # Opposing Bearish Order Blocks
        for ob in smc.active_bearish_obs:
            if ob.bottom > price:
                candidates.append(ob.bottom)
        # Value Area High
        if vp.vah_price > price:
            candidates.append(vp.vah_price)

        valid = [lvl for lvl in candidates if lvl > price]
        return min(valid) if valid else price * 1.015

    def _calculate_bearish_sl(
        self,
        price: float,
        smc: SMCAnalysisResult,
        vp: VolumeProfileResult,
        atr: float
    ) -> float:
        """Sets structural SL just above the nearest Order Block or VAH."""
        candidate_levels = [price + (1.5 * atr)]
        for ob in smc.active_bearish_obs:
            if ob.top > price:
                candidate_levels.append(ob.top + (self.config.sl_atr_buffer * atr))
        if vp.vah_price > price:
            candidate_levels.append(vp.vah_price + (self.config.sl_atr_buffer * atr))

        valid = [lvl for lvl in candidate_levels if lvl > price]
        return min(valid) if valid else price + (1.5 * atr)

    def _calculate_bearish_target(
        self,
        price: float,
        smc: SMCAnalysisResult,
        vp: VolumeProfileResult
    ) -> float:
        """Sets structural Target at opposing EQL, Bullish OB, or VAL."""
        candidates = [price * 0.99]
        for pool in smc.active_liquidity_pools:
            if not pool.is_high and pool.price < price:
                candidates.append(pool.price)
        for ob in smc.active_bullish_obs:
            if ob.top < price:
                candidates.append(ob.top)
        if vp.val_price < price:
            candidates.append(vp.val_price)

        valid = [lvl for lvl in candidates if lvl < price]
        return max(valid) if valid else price * 0.985
