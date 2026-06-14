"""Tiered Exit Manager — 3-Phase Profit Maximization Engine.

Phase 1 (De-Risking):
    At 1:1 R:R → book 35% of lots → move SL to breakeven.

Phase 2 (Uncapped Runner):
    Remaining 65% runs with NO fixed take-profit.

Phase 3 (Mathematical Reversal Exit):
    Trail runners using 5-minute 9 EMA.
    Hard exit when candle CLOSES below 9 EMA (longs) or above (shorts).
"""

from __future__ import annotations

import logging

import pandas as pd

from .config import (
    PARTIAL_BOOK_RATIO, PARTIAL_BOOK_RR,
    RUNNER_EMA_PERIOD, NIFTY_LOT_SIZE,
    ExitDecision,
)

logger = logging.getLogger(__name__)


class TieredExitManager:
    """3-phase exit engine for maximum profit capture.

    Manages the lifecycle of a position through de-risking,
    uncapped running, and mathematical reversal detection.

    State Tracking per Position
    ---------------------------
    - phase: Current phase (1, 2, or 3)
    - entry_price: Original entry premium
    - stop_loss: Current stop-loss level
    - total_lots: Original lot count
    - booked_lots: Lots already exited in Phase 1
    - remaining_lots: Lots still running (Phase 2/3)
    """

    def __init__(
        self,
        partial_ratio: float = PARTIAL_BOOK_RATIO,
        partial_rr: float = PARTIAL_BOOK_RR,
        runner_ema: int = RUNNER_EMA_PERIOD,
    ):
        self.partial_ratio = partial_ratio    # 0.35
        self.partial_rr = partial_rr          # 1.0
        self.runner_ema = runner_ema          # 9

        # Position state (set by orchestrator on entry)
        self.entry_price: float = 0.0
        self.stop_loss: float = 0.0
        self.total_lots: int = 0
        self.booked_lots: int = 0
        self.remaining_lots: int = 0
        self.direction: int = 0  # 1 = CALL, -1 = PUT
        self.phase: int = 0      # 0 = no position, 1/2/3 = active phase
        self._original_sl: float = 0.0

    # ──────────────────────────────────────────────────────────────────
    # Position Lifecycle
    # ──────────────────────────────────────────────────────────────────

    def open_position(
        self,
        entry_price: float,
        stop_loss: float,
        total_lots: int,
        direction: int,
    ) -> None:
        """Initialize a new position for tiered exit management."""
        self.entry_price = entry_price
        self.stop_loss = stop_loss
        self._original_sl = stop_loss
        self.total_lots = total_lots
        self.booked_lots = 0
        self.remaining_lots = total_lots
        self.direction = direction
        self.phase = 1  # Start in Phase 1

        logger.info(
            "EXIT MANAGER: New position — %s %d lots @ ₹%.1f | SL=₹%.1f",
            "CALL" if direction == 1 else "PUT",
            total_lots, entry_price, stop_loss,
        )

    def close_position(self) -> None:
        """Reset all state after full position exit."""
        self.phase = 0
        self.entry_price = 0.0
        self.stop_loss = 0.0
        self.total_lots = 0
        self.booked_lots = 0
        self.remaining_lots = 0
        self.direction = 0

    @property
    def has_position(self) -> bool:
        return self.phase > 0 and self.remaining_lots > 0

    # ──────────────────────────────────────────────────────────────────
    # Main Evaluation
    # ──────────────────────────────────────────────────────────────────

    def evaluate(
        self,
        current_price: float,
        df_5min: pd.DataFrame,
        ai_confidence: float = None,
    ) -> ExitDecision:
        """Evaluate the position against the 3-phase exit logic.

        Parameters
        ----------
        current_price : float
            Current option premium.
        df_5min : pd.DataFrame
            Recent 5-minute candle data (needs 'close' column for 9 EMA).
        ai_confidence : float, optional
            Real-time AI Confidence Score. If < 40%, triggers early exit.

        Returns
        -------
        ExitDecision
        """
        if not self.has_position:
            return ExitDecision()

        # ── STOP-LOSS CHECK (all phases) ──
        sl_hit = self._check_stop_loss(current_price)
        if sl_hit:
            return ExitDecision(
                should_exit=True,
                reason=f"STOP-LOSS HIT @ ₹{current_price:.1f} (SL=₹{self.stop_loss:.1f})",
                quantity_pct=1.0,  # Exit ALL remaining
                phase=self.phase,
            )

        # ── AI CONFIDENCE EARLY EXIT CHECK ──
        if ai_confidence is not None and ai_confidence < 40:
            logger.warning(
                "AI EARLY EXIT TRIGGERED: Confidence dropped to %.1f%% — Force Exiting to protect capital.", 
                ai_confidence
            )
            return ExitDecision(
                should_exit=True,
                reason=f"AI EARLY EXIT: Confidence collapsed to {ai_confidence}%",
                quantity_pct=1.0,  # Exit ALL remaining
                phase=self.phase,
            )

        # ── PHASE 1: De-Risking ──
        if self.phase == 1:
            return self._evaluate_phase1(current_price)

        # ── PHASE 2 → 3: Runner Management ──
        if self.phase >= 2:
            return self._evaluate_runner(current_price, df_5min)

        return ExitDecision()

    # ──────────────────────────────────────────────────────────────────
    # Phase 1: Partial Profit Booking
    # ──────────────────────────────────────────────────────────────────

    def _evaluate_phase1(self, current_price: float) -> ExitDecision:
        """Check if 1:1 R:R has been reached for partial booking."""
        risk = abs(self.entry_price - self._original_sl)
        if risk <= 0:
            return ExitDecision()

        # Unrealized reward
        if self.direction == 1:
            reward = current_price - self.entry_price
        else:
            reward = self.entry_price - current_price

        rr_ratio = reward / risk

        if rr_ratio >= self.partial_rr:
            # Phase 1 triggered: book 35%
            lots_to_book = max(1, int(self.total_lots * self.partial_ratio))
            self.booked_lots += lots_to_book
            self.remaining_lots = self.total_lots - self.booked_lots

            # Move SL to breakeven for remaining
            self.stop_loss = self.entry_price
            self.phase = 2  # Advance to Phase 2

            logger.info(
                "PHASE 1 COMPLETE: Booked %d/%d lots @ ₹%.1f (%.1f:1 RR) | "
                "SL → Breakeven ₹%.1f | %d lots running (Phase 2)",
                lots_to_book, self.total_lots, current_price, rr_ratio,
                self.entry_price, self.remaining_lots,
            )

            return ExitDecision(
                should_exit=True,
                reason=f"Phase 1: Book {lots_to_book} lots @ {rr_ratio:.1f}:1 RR → SL to BE",
                quantity_pct=self.partial_ratio,
                move_sl_to_be=True,
                phase=1,
            )

        return ExitDecision()

    # ──────────────────────────────────────────────────────────────────
    # Phase 2 & 3: Uncapped Runner with 9 EMA Exit
    # ──────────────────────────────────────────────────────────────────

    def _evaluate_runner(
        self,
        current_price: float,
        df_5min: pd.DataFrame,
    ) -> ExitDecision:
        """Phase 2/3: Trail runners using 5-min 9 EMA reversal.

        The runners have NO fixed target. They ride the trend until
        a 5-minute candle CLOSES on the wrong side of the 9 EMA.
        """
        if len(df_5min) < self.runner_ema + 2:
            return ExitDecision()  # Not enough data for 9 EMA

        # Calculate 9 EMA on 5-minute close
        ema_9 = df_5min["close"].ewm(span=self.runner_ema, adjust=False).mean()

        # Phase 3 exit: candle must CLOSE below/above 9 EMA
        # We check the LAST COMPLETED candle (iloc[-2]) to avoid partial candles
        last_close = df_5min["close"].iloc[-1]
        last_ema = ema_9.iloc[-1]

        self.phase = 3  # We're now in Phase 3 (trailing)

        if self.direction == 1 and last_close < last_ema:
            # LONG: candle closed BELOW 9 EMA → exit runners
            logger.info(
                "PHASE 3 EXIT: 5min candle closed ₹%.1f < 9 EMA ₹%.1f — "
                "exiting %d runner lots",
                last_close, last_ema, self.remaining_lots,
            )
            return ExitDecision(
                should_exit=True,
                reason=f"Phase 3: 5min close ₹{last_close:.1f} < 9 EMA ₹{last_ema:.1f}",
                quantity_pct=1.0,
                phase=3,
            )

        if self.direction == -1 and last_close > last_ema:
            # SHORT: candle closed ABOVE 9 EMA → exit runners
            logger.info(
                "PHASE 3 EXIT: 5min candle closed ₹%.1f > 9 EMA ₹%.1f — "
                "exiting %d runner lots",
                last_close, last_ema, self.remaining_lots,
            )
            return ExitDecision(
                should_exit=True,
                reason=f"Phase 3: 5min close ₹{last_close:.1f} > 9 EMA ₹{last_ema:.1f}",
                quantity_pct=1.0,
                phase=3,
            )

        return ExitDecision()

    # ──────────────────────────────────────────────────────────────────
    # Stop-Loss Check
    # ──────────────────────────────────────────────────────────────────

    def _check_stop_loss(self, current_price: float) -> bool:
        """Universal SL check across all phases."""
        if self.direction == 1:
            return current_price <= self.stop_loss
        elif self.direction == -1:
            return current_price >= self.stop_loss
        return False
