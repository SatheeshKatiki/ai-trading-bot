"""MTM Profit Trailing Engine — Dynamic Mark-to-Market Floor Ratchet.

Implements a non-static daily profit protection system:

1. ACTIVATE when day MTM reaches ₹5,000
2. LOCK a minimum profit floor of ₹3,000
3. RATCHET floor upward by ₹1,500 for every ₹2,000 MTM increment
4. LIQUIDATE all positions if real-time MTM drops to the floor

Example progression:
    MTM ₹5,000 → Floor ₹3,000
    MTM ₹7,000 → Floor ₹4,500
    MTM ₹9,000 → Floor ₹6,000
    MTM ₹11,000 → Floor ₹7,500
    MTM drops to ₹7,500 → LIQUIDATE ALL
"""

from __future__ import annotations

import logging

from .config import (
    MTM_ACTIVATION_THRESHOLD,
    MTM_FLOOR_INITIAL,
    MTM_STEP_INCREMENT,
    MTM_FLOOR_RATCHET,
)

logger = logging.getLogger(__name__)


class MTMTrailingEngine:
    """Day-level Mark-to-Market profit trailing and protection engine.

    Thread-safe. Called on every tick to evaluate if the profit floor
    has been breached.

    Usage::
        mtm_engine = MTMTrailingEngine()

        # On every price update:
        should_liquidate = mtm_engine.update(current_day_mtm=6500.0)
        if should_liquidate:
            # Fire IOC orders to close everything
            ...

        # At start of new day:
        mtm_engine.reset()
    """

    def __init__(
        self,
        activation: float = MTM_ACTIVATION_THRESHOLD,
        floor_initial: float = MTM_FLOOR_INITIAL,
        step_increment: float = MTM_STEP_INCREMENT,
        floor_ratchet: float = MTM_FLOOR_RATCHET,
    ):
        self.activation = activation
        self.floor_initial = floor_initial
        self.step_increment = step_increment
        self.floor_ratchet = floor_ratchet

        # State
        self._is_active: bool = False
        self._current_floor: float = 0.0
        self._peak_mtm: float = 0.0
        self._steps_taken: int = 0

    # ──────────────────────────────────────────────────────────────────
    # Core Update
    # ──────────────────────────────────────────────────────────────────

    def update(self, current_mtm: float) -> bool:
        """Process a new MTM reading and determine if liquidation is needed.

        Parameters
        ----------
        current_mtm : float
            Current total day Mark-to-Market (realized + unrealized).

        Returns
        -------
        bool
            True if MTM has dropped to the floor → LIQUIDATE ALL.
        """
        # Track peak MTM regardless of engine state
        if current_mtm > self._peak_mtm:
            self._peak_mtm = current_mtm

        # Check if activation threshold reached
        if not self._is_active:
            if current_mtm >= self.activation:
                self._activate()
            return False  # Engine not active — no liquidation

        # Engine is active — ratchet the floor upward
        self._ratchet_floor(current_mtm)

        # Check if MTM has dropped to the floor
        if current_mtm <= self._current_floor:
            logger.critical(
                "MTM FLOOR BREACHED: MTM=₹%.0f dropped to floor ₹%.0f — LIQUIDATING ALL",
                current_mtm, self._current_floor,
            )
            return True

        return False

    # ──────────────────────────────────────────────────────────────────
    # Floor Logic
    # ──────────────────────────────────────────────────────────────────

    def _activate(self) -> None:
        """Activate the MTM engine and set initial floor."""
        self._is_active = True
        self._current_floor = self.floor_initial
        self._steps_taken = 0
        logger.info(
            "MTM ENGINE ACTIVATED: Peak=₹%.0f | Floor locked at ₹%.0f",
            self._peak_mtm, self._current_floor,
        )

    def _ratchet_floor(self, current_mtm: float) -> None:
        """Ratchet the floor upward for every step increment above activation.

        At activation (₹5K): floor = ₹3,000
        At ₹7K (1 step): floor = ₹4,500
        At ₹9K (2 steps): floor = ₹6,000
        At ₹11K (3 steps): floor = ₹7,500
        """
        mtm_above_activation = current_mtm - self.activation
        if mtm_above_activation <= 0:
            return

        new_steps = int(mtm_above_activation / self.step_increment)

        if new_steps > self._steps_taken:
            self._steps_taken = new_steps
            new_floor = self.floor_initial + (new_steps * self.floor_ratchet)

            # Floor can only go UP, never down
            if new_floor > self._current_floor:
                old_floor = self._current_floor
                self._current_floor = new_floor
                logger.info(
                    "MTM FLOOR RATCHETED: ₹%.0f → ₹%.0f (step %d, MTM=₹%.0f)",
                    old_floor, new_floor, new_steps, current_mtm,
                )

    # ──────────────────────────────────────────────────────────────────
    # Accessors
    # ──────────────────────────────────────────────────────────────────

    @property
    def is_active(self) -> bool:
        return self._is_active

    @property
    def current_floor(self) -> float:
        return self._current_floor

    @property
    def peak_mtm(self) -> float:
        return self._peak_mtm

    def status(self) -> dict:
        """Return engine status for dashboard display."""
        return {
            "is_active": self._is_active,
            "current_floor": self._current_floor,
            "peak_mtm": self._peak_mtm,
            "steps_taken": self._steps_taken,
        }

    # ──────────────────────────────────────────────────────────────────
    # Daily Reset
    # ──────────────────────────────────────────────────────────────────

    def reset(self) -> None:
        """Reset engine for a new trading day."""
        self._is_active = False
        self._current_floor = 0.0
        self._peak_mtm = 0.0
        self._steps_taken = 0
        logger.info("MTM Engine: Reset for new session")
