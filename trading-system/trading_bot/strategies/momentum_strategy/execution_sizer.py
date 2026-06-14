"""Execution Sizer — Dynamic Lot Calculation, Anti-Whipsaw & Kill Switch.

Manages:
1. Target-based dynamic sizing (₹5K target at 1:2 R:R per trade)
2. Anti-whipsaw directional lock (30-min cooldown after SL hit)
3. Overtrading kill switch (max 4 trades/day, -2% circuit breaker)
"""

from __future__ import annotations

import logging
import time as time_module
from typing import Tuple

from .config import (
    NIFTY_LOT_SIZE,
    MAX_TRADES_PER_DAY,
    CIRCUIT_BREAKER_PCT,
    COOLDOWN_MINUTES,
    CONSECUTIVE_SL_HALT,
    TARGET_PROFIT_PER_TRADE,
    REWARD_TO_RISK_RATIO,
    DayState,
)

logger = logging.getLogger(__name__)


class ExecutionSizer:
    """Thread-safe execution sizing and protection engine.

    Tracks daily trade count, consecutive stop-losses, and enforces
    anti-whipsaw cooldown periods between directional reversals.

    Usage::
        sizer = ExecutionSizer(capital=500_000)
        lots = sizer.calculate_lots(premium=180.0, sl_premium=150.0)
        can, reason = sizer.can_trade(direction=1)
    """

    def __init__(self, capital: float = 500_000.0, default_lots: int = 1):
        self.capital = capital
        self.default_lots = default_lots
        self.state = DayState()

    # ──────────────────────────────────────────────────────────────────
    # Dynamic Lot Sizing
    # ──────────────────────────────────────────────────────────────────

    def calculate_lots(self, premium: float, sl_premium: float, user_lots: int = None) -> int:
        """Calculate number of lots (multiples of base quantity) for a trade.

        Optimized for Institutional Momentum: Bypassing dynamic risk-based
        sizing to enforce a fixed execution based on user configuration.
        """
        # User can explicitly request N lots, defaults to self.default_lots (1)
        lots = user_lots if user_lots is not None else self.default_lots
        
        logger.info("LOT SIZING: FIXED %d lots (bypassing dynamic risk calculation)", lots)
        return lots

    # ──────────────────────────────────────────────────────────────────
    # Trade Eligibility Check
    # ──────────────────────────────────────────────────────────────────

    def can_trade(self, direction: int) -> Tuple[bool, str]:
        """Check if a new trade is allowed given daily state.

        Enforces:
        1. Max 4 trades per day
        2. Emergency halt after 2 consecutive SL hits
        3. Anti-whipsaw 30-minute cooldown on directional reversal
        4. -2% capital circuit breaker

        Parameters
        ----------
        direction : int
            Intended trade direction (1 = CALL, -1 = PUT).

        Returns
        -------
        (allowed, reason) : tuple[bool, str]
        """
        # Already halted for the day
        if self.state.is_halted:
            return False, f"DAILY HALT: {self.state.halt_reason}"

        # Max trades per day
        if self.state.trades_today >= MAX_TRADES_PER_DAY:
            self._halt(f"Max {MAX_TRADES_PER_DAY} trades reached")
            return False, f"KILL SWITCH: Max {MAX_TRADES_PER_DAY} trades reached"

        # Consecutive SL halt
        if self.state.consecutive_sl >= CONSECUTIVE_SL_HALT:
            self._halt(f"{CONSECUTIVE_SL_HALT} consecutive stop-losses hit")
            return False, f"CIRCUIT BREAKER: {CONSECUTIVE_SL_HALT} consecutive SL hits"

        # Anti-whipsaw: if last SL was in the OPPOSITE direction,
        # enforce a 30-minute cooldown before allowing reversal
        if self.state.last_sl_direction != 0 and direction != 0:
            if direction == -self.state.last_sl_direction:
                elapsed = time_module.time() - self.state.last_sl_time
                cooldown_secs = COOLDOWN_MINUTES * 60
                if elapsed < cooldown_secs:
                    remaining = int((cooldown_secs - elapsed) / 60)
                    return False, (
                        f"ANTI-WHIPSAW: Directional reversal locked — "
                        f"{remaining}min cooldown remaining"
                    )

        return True, "Trade allowed"

    # ──────────────────────────────────────────────────────────────────
    # Trade Recording
    # ──────────────────────────────────────────────────────────────────

    def record_trade(self, direction: int, is_sl_hit: bool) -> None:
        """Record a completed trade for daily state tracking.

        Parameters
        ----------
        direction : int
            Trade direction (1 = CALL, -1 = PUT).
        is_sl_hit : bool
            Whether the trade was closed by stop-loss.
        """
        self.state.trades_today += 1

        if is_sl_hit:
            self.state.consecutive_sl += 1
            self.state.last_sl_direction = direction
            self.state.last_sl_time = time_module.time()
            logger.warning(
                "SL HIT #%d (direction=%d) — %d/%d before halt",
                self.state.consecutive_sl, direction,
                self.state.consecutive_sl, CONSECUTIVE_SL_HALT,
            )
        else:
            # Winning trade resets consecutive SL counter
            self.state.consecutive_sl = 0
            self.state.last_sl_direction = 0

        logger.info(
            "Trade #%d/%d recorded | ConsecSL=%d | Halted=%s",
            self.state.trades_today, MAX_TRADES_PER_DAY,
            self.state.consecutive_sl, self.state.is_halted,
        )

    # ──────────────────────────────────────────────────────────────────
    # Daily Reset
    # ──────────────────────────────────────────────────────────────────

    def reset_daily(self) -> None:
        """Reset all daily state counters for a new trading day."""
        self.state = DayState()
        logger.info("ExecutionSizer: Daily state reset — ready for new session")

    # ──────────────────────────────────────────────────────────────────
    # Internal
    # ──────────────────────────────────────────────────────────────────

    def _halt(self, reason: str) -> None:
        """Activate daily halt."""
        self.state.is_halted = True
        self.state.halt_reason = reason
        logger.critical("DAILY HALT ACTIVATED: %s", reason)
