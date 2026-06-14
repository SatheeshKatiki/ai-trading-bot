"""Market Environment Filter — VIX Gate & Time Window Enforcement.

Ensures signals are only generated when macro conditions are favorable
and the market clock is within permitted entry windows.
"""

from __future__ import annotations

import logging
from datetime import datetime, time
from typing import Tuple

from .config import VIX_MIN, VIX_MAX, ENTRY_WINDOWS, EOD_SQUARE_OFF

logger = logging.getLogger(__name__)


class MarketEnvironmentFilter:
    """Institutional macro-level filter for trade eligibility.

    Two gates must pass before any signal is considered:
    1. India VIX must be within the safe band [12.0, 21.0]
    2. Current time must fall inside a permitted entry window
    """

    def __init__(self, vix_min: float = VIX_MIN, vix_max: float = VIX_MAX):
        self.vix_min = vix_min
        self.vix_max = vix_max
        self._daily_vix: float = 0.0
        self._vix_fetched: bool = False

    # ──────────────────────────────────────────────────────────────────
    # VIX Gate
    # ──────────────────────────────────────────────────────────────────

    def set_daily_vix(self, vix_value: float) -> None:
        """Set the VIX value once at market open (9:15 AM).

        Called by the orchestrator after fetching VIX from the broker.
        """
        self._daily_vix = vix_value
        self._vix_fetched = True
        logger.info("Daily VIX set to %.2f", vix_value)

    def is_vix_safe(self) -> Tuple[bool, str]:
        """Check if India VIX is within the institutional safe band."""
        if not self._vix_fetched:
            return False, "VIX not yet fetched — awaiting market open data"

        if self._daily_vix < self.vix_min:
            reason = f"VIX {self._daily_vix:.2f} < {self.vix_min} — low volatility, poor premium"
            logger.warning("MACRO-RISK: %s", reason)
            return False, reason

        if self._daily_vix > self.vix_max:
            reason = f"VIX {self._daily_vix:.2f} > {self.vix_max} — extreme fear, high whipsaw risk"
            logger.warning("MACRO-RISK: %s", reason)
            return False, reason

        return True, f"VIX {self._daily_vix:.2f} within safe band"

    # ──────────────────────────────────────────────────────────────────
    # Time Window Gate
    # ──────────────────────────────────────────────────────────────────

    @staticmethod
    def is_entry_window(current_time: time) -> Tuple[bool, str]:
        """Check if the current IST time falls inside a permitted entry window."""
        for window_start, window_end in ENTRY_WINDOWS:
            if window_start <= current_time <= window_end:
                return True, f"Inside entry window {window_start.strftime('%H:%M')}–{window_end.strftime('%H:%M')}"

        return False, f"Outside entry windows — current time {current_time.strftime('%H:%M')}"

    @staticmethod
    def is_eod_squareoff(current_time: time) -> bool:
        """Check if we've crossed the hard EOD square-off deadline."""
        return current_time >= EOD_SQUARE_OFF

    # ──────────────────────────────────────────────────────────────────
    # Combined Check
    # ──────────────────────────────────────────────────────────────────

    def check(self, current_time: time) -> Tuple[bool, str]:
        """Run all environment checks. Both must pass for signal generation.

        Returns
        -------
        (allowed, reason) : tuple[bool, str]
        """
        vix_ok, vix_reason = self.is_vix_safe()
        if not vix_ok:
            return False, vix_reason

        time_ok, time_reason = self.is_entry_window(current_time)
        if not time_ok:
            return False, time_reason

        return True, f"Environment clear — {vix_reason} | {time_reason}"
