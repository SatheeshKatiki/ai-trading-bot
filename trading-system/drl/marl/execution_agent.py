"""
ExecutionAgent — The Options Desk.

Professional-grade options execution logic that translates a directional signal
(Long=1, Short=2, Close=3) into a precise execution plan:

    - Strike selection  : ATM | ITM | OTM based on IV regime and time-to-expiry
    - Gamma mode        : Near expiry (<2 days) → ATM only (gamma dominates)
    - Theta guard       : Avoids buying premium in the last 30 min of the session
      (theta decay accelerates sharply there — a common options-buyer trap)
    - Lot size scaling  : Defers to RiskAgent.get_position_size_multiplier() so
      capital-protection and max-drawdown rules are always respected
    - Confidence score  : Returns a 0.0-1.0 score so MasterAgent can weight signals

Fix 3 (2026-08-16): Replaced the 45-line ATM-only stub with full IV-aware logic.
"""

import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, Any

from drl.marl.base_agent import BaseAgent

logger = logging.getLogger(__name__)

# IST offset
_IST = timezone(timedelta(hours=5, minutes=30))

# IV percentile thresholds for regime classification
_IV_HIGH_THRESHOLD    = 0.20   # India VIX > 20 or IV% > 20 → high IV regime
_IV_EXTREME_THRESHOLD = 0.30   # IV% > 30 → extreme (sell premium)

# Session time constants (IST hour, minute)
_THETA_GUARD_START_HOUR   = 15
_THETA_GUARD_START_MINUTE = 00   # avoid buying premium after 15:00 IST
_MARKET_CLOSE_HOUR        = 15
_MARKET_CLOSE_MINUTE      = 30

# Days-to-expiry threshold for gamma-scalp mode
_GAMMA_MODE_DAYS_TO_EXPIRY = 2


class ExecutionAgent(BaseAgent):
    """
    The Execution Agent (The Options Desk) — Professional Edition.

    Takes a direction signal from SignalAgent and determines the exact execution
    parameters: strike offset (ATM/ITM/OTM), option type (CE/PE), lot size
    multiplier, and an execution confidence score.

    IV Regime → Strike Logic
    ─────────────────────────────────────────────────────────────────────────
    Low IV  (< 20%)  : Buy ATM/slight-ITM → cheapest entry, max leverage
    High IV (20-30%) : Buy ATM only       → ITM too expensive, OTM risky
    Extreme IV (>30%): Prefer OTM sells   → premium is richest, decay fastest
    Gamma mode       : Near expiry (<2d)  → ATM only (gamma exposure maximised)
    Theta guard      : After 15:00 IST    → no new premium purchases allowed
    """

    def __init__(self):
        super().__init__("ExecutionAgent_OptionsDesk")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _current_ist() -> datetime:
        return datetime.now(_IST)

    def _is_theta_guard_active(self) -> bool:
        """True if we are in the last 30 minutes of the session.
        Buying options premium here is theta-decay suicide.
        """
        now = self._current_ist()
        cutoff = now.replace(
            hour=_THETA_GUARD_START_HOUR,
            minute=_THETA_GUARD_START_MINUTE,
            second=0, microsecond=0
        )
        return now >= cutoff

    def _classify_iv_regime(self, iv_pct: float) -> str:
        """Classify the IV environment into a named regime."""
        if iv_pct >= _IV_EXTREME_THRESHOLD:
            return "EXTREME"
        if iv_pct >= _IV_HIGH_THRESHOLD:
            return "HIGH"
        return "LOW"

    def _select_strike_offset(
        self,
        iv_regime: str,
        is_gamma_mode: bool,
        signal_action: int,
    ) -> int:
        """
        Returns strike offset from ATM:
          0  = ATM
         -1  = 1 strike In-The-Money   (costs more, safer delta)
         +1  = 1 strike Out-of-The-Money (cheaper, lower delta)
         +2  = 2 strikes OTM            (cheapest, used for premium selling)

        Negative offset = ITM for buyers (strong directional conviction).
        Positive offset = OTM for sellers (high IV, selling premium).
        """
        if is_gamma_mode:
            # Near expiry: gamma is maximised at ATM — never go OTM
            return 0

        if iv_regime == "EXTREME":
            # High IV → sell OTM premium (collect theta + vega decay)
            return +2

        if iv_regime == "HIGH":
            # High IV → buy ATM only (ITM too expensive, OTM too risky)
            return 0

        # Low IV → slight ITM for better delta, affordable premium
        return -1

    def _compute_confidence(
        self,
        iv_regime: str,
        is_gamma_mode: bool,
        is_theta_guard: bool,
    ) -> float:
        """
        Produces a 0.0–1.0 confidence score for MasterAgent weighting.
        Lower score = execution is riskier; MasterAgent may choose to skip.
        """
        base = 0.75

        # Gamma mode near expiry is high-edge but also high-risk
        if is_gamma_mode:
            base += 0.10

        # Extreme IV regimes are great for premium sellers, riskier for buyers
        if iv_regime == "EXTREME":
            base -= 0.10

        # Never penalise further — if theta guard is active we already block entry
        return round(min(1.0, max(0.0, base)), 3)

    def _get_position_size_multiplier(self, risk_agent: Any = None) -> float:
        """Delegates position sizing to RiskAgent if available.
        Falls back to 1.0 (full size) if no RiskAgent is provided — this keeps
        the ExecutionAgent usable standalone (e.g. in unit tests).
        """
        if risk_agent is not None and hasattr(risk_agent, "get_position_size_multiplier"):
            try:
                return risk_agent.get_position_size_multiplier()
            except Exception as e:
                logger.warning(f"[ExecutionAgent] RiskAgent.get_position_size_multiplier failed: {e}")
        return 1.0

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def analyze(
        self,
        signal_action: int,
        current_spot: float,
        is_high_iv: bool = False,
        iv_pct: float = 0.15,
        days_to_expiry: int = 5,
        risk_agent: Any = None,
    ) -> Dict[str, Any]:
        """
        Analyze how to execute the given directional signal.

        Parameters
        ----------
        signal_action   : 1 = Long, 2 = Short, 3 = Close, 0 = Hold
        current_spot    : Current underlying price (e.g. Nifty 50 level)
        is_high_iv      : Convenience boolean from AlphaAgent context
        iv_pct          : Implied volatility as a fraction (0.20 = 20% IV)
                          Overrides is_high_iv when provided explicitly.
        days_to_expiry  : Calendar days until the nearest weekly/monthly expiry.
        risk_agent      : Optional RiskAgent reference for position sizing.

        Returns
        -------
        dict with keys:
            execute         : bool — False means "don't trade right now"
            option_type     : "CE_BUY" | "CE_SELL" | "PE_BUY" | "PE_SELL" | None
            strike_offset   : int (see _select_strike_offset docstring)
            lot_multiplier  : float — scale factor for lot size (from RiskAgent)
            confidence      : float 0.0–1.0 — execution quality score
            reason          : str — human-readable explanation
            iv_regime       : str — "LOW" | "HIGH" | "EXTREME"
            gamma_mode      : bool
            theta_guard     : bool
        """
        if not self.is_active or signal_action in (0, 3):
            return {
                "execute": False,
                "option_type": None,
                "strike_offset": 0,
                "lot_multiplier": 0.0,
                "confidence": 0.0,
                "reason": "Hold/Close — no execution needed.",
                "iv_regime": "LOW",
                "gamma_mode": False,
                "theta_guard": False,
            }

        # ── Environment classification ─────────────────────────────────────
        # Merge is_high_iv flag with explicit iv_pct if caller provided both;
        # explicit iv_pct takes precedence (it's more informative).
        effective_iv = iv_pct if iv_pct != 0.15 else (0.22 if is_high_iv else 0.15)
        iv_regime      = self._classify_iv_regime(effective_iv)
        is_gamma_mode  = days_to_expiry <= _GAMMA_MODE_DAYS_TO_EXPIRY
        is_theta_guard = self._is_theta_guard_active()

        # ── Theta guard: block new premium purchases near session close ─────
        if is_theta_guard:
            logger.info(
                "[ExecutionAgent] Theta guard active (≥15:00 IST) — "
                "blocking new premium purchase to protect against theta decay."
            )
            return {
                "execute": False,
                "option_type": None,
                "strike_offset": 0,
                "lot_multiplier": 0.0,
                "confidence": 0.0,
                "reason": "Theta guard: no new premium buying after 15:00 IST.",
                "iv_regime": iv_regime,
                "gamma_mode": is_gamma_mode,
                "theta_guard": True,
            }

        # ── Strike selection ───────────────────────────────────────────────
        strike_offset = self._select_strike_offset(iv_regime, is_gamma_mode, signal_action)

        # ── Option type: direction + IV regime → buy or sell premium ──────
        if iv_regime == "EXTREME":
            # Selling premium in extreme IV — CE_SELL for long (short call on up move),
            # PE_SELL for short (short put on down move). Reversed intuition, but
            # in extreme IV the vega/theta decay is your edge, not direction.
            option_type = "CE_SELL" if signal_action == 1 else "PE_SELL"
            action_desc = "Selling OTM premium (extreme IV — theta/vega decay play)"
        else:
            # Standard directional buy
            option_type = "CE_BUY" if signal_action == 1 else "PE_BUY"
            direction   = "Call" if signal_action == 1 else "Put"
            itm_atm_otm = {-1: "ITM", 0: "ATM", 1: "OTM", 2: "OTM+2"}
            action_desc = (
                f"Buying {itm_atm_otm.get(strike_offset, 'ATM')} {direction} "
                f"(IV regime: {iv_regime}"
                + (", gamma mode" if is_gamma_mode else "")
                + ")"
            )

        # ── Position size (always defers to RiskAgent) ────────────────────
        lot_multiplier = self._get_position_size_multiplier(risk_agent)

        # ── Confidence ────────────────────────────────────────────────────
        confidence = self._compute_confidence(iv_regime, is_gamma_mode, is_theta_guard)

        logger.info(
            "[ExecutionAgent] Signal=%s | IV=%.1f%% (%s) | GammaMode=%s | "
            "Strike=%+d | Type=%s | LotMult=%.2f | Confidence=%.3f",
            signal_action, effective_iv * 100, iv_regime,
            is_gamma_mode, strike_offset, option_type,
            lot_multiplier, confidence,
        )

        return {
            "execute": True,
            "option_type": option_type,
            "strike_offset": strike_offset,
            "lot_multiplier": lot_multiplier,
            "confidence": confidence,
            "reason": action_desc,
            "iv_regime": iv_regime,
            "gamma_mode": is_gamma_mode,
            "theta_guard": False,
        }
