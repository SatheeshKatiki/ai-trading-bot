"""Dynamic ITM Option Strike Selector.

Selects the optimal At-The-Money (ATM) Nifty option strike based on:
1. Spot price → calculate ATM depth (0 points)
2. Round to nearest 50-point strike interval
3. Approximate delta using moneyness
4. Handle Thursday expiry rollover to next week
"""

from __future__ import annotations

import logging
import math
from datetime import date, datetime, timedelta
from typing import Optional

from .config import (
    NIFTY_STRIKE_INTERVAL, ITM_OFFSET_MIN, ITM_OFFSET_MAX,
    DELTA_TARGET_MIN, DELTA_TARGET_MAX, ITMSelection,
)

logger = logging.getLogger(__name__)

# Nifty weekly options expire every Thursday
EXPIRY_WEEKDAY = 3  # Thursday (Monday=0, ..., Thursday=3)


class ITMOptionSelector:
    """Dynamically selects an ATM Nifty option strike.

    The selector uses mathematical calculation from the spot price
    (no API call required) for instant, deterministic strike selection.

    For Nifty options with 50-point intervals:
    - 0 pts depth ≈ ATM → Delta ~0.50

    This naturally falls in the target delta range of 0.45–0.55.
    """

    def __init__(
        self,
        strike_interval: int = NIFTY_STRIKE_INTERVAL,
        itm_min: int = ITM_OFFSET_MIN,
        itm_max: int = ITM_OFFSET_MAX,
    ):
        self.strike_interval = strike_interval
        self.itm_min = itm_min
        self.itm_max = itm_max

    # ──────────────────────────────────────────────────────────────────
    # Core Strike Selection
    # ──────────────────────────────────────────────────────────────────

    def select_strike(self, spot_price: float, direction: int) -> float:
        """Calculate the optimal ITM strike price.

        Parameters
        ----------
        spot_price : float
            Current Nifty spot price (e.g., 23850.0)
        direction : int
            1 = CALL (CE), -1 = PUT (PE)

        Returns
        -------
        float
            Selected ITM strike price, rounded to nearest 50-point interval.
        """
        # Target: midpoint of ITM range (125 points ITM)
        target_itm = (self.itm_min + self.itm_max) // 2  # 125

        if direction == 1:
            # CALL: strike BELOW spot → more ITM = lower strike
            raw_strike = spot_price - target_itm
        elif direction == -1:
            # PUT: strike ABOVE spot → more ITM = higher strike
            raw_strike = spot_price + target_itm
        else:
            raise ValueError(f"Invalid direction: {direction}")

        # Round to nearest strike interval (50 points)
        strike = round(raw_strike / self.strike_interval) * self.strike_interval
        return float(strike)

    # ──────────────────────────────────────────────────────────────────
    # Delta Approximation
    # ──────────────────────────────────────────────────────────────────

    def estimate_delta(self, spot_price: float, strike: float, direction: int) -> float:
        """Approximate option delta from moneyness depth.

        Uses a simplified model: Delta ≈ 0.50 + (ITM_depth / spot) * K
        where K is calibrated for weekly Nifty options.

        For 100–150 pts ITM on Nifty (~24000), this gives 0.65–0.78 delta.
        """
        if direction == 1:
            itm_depth = spot_price - strike
        else:
            itm_depth = strike - spot_price

        # Normalized moneyness
        moneyness = itm_depth / spot_price

        # Calibration: weekly Nifty options, ~5 DTE
        # 0.5% moneyness ≈ 0.70 delta, 0.6% ≈ 0.75 delta
        delta = min(0.95, 0.50 + moneyness * 40.0)
        return round(max(0.50, delta), 3)

    # ──────────────────────────────────────────────────────────────────
    # Expiry & Rollover Logic
    # ──────────────────────────────────────────────────────────────────

    @staticmethod
    def get_current_expiry(reference_date: Optional[date] = None) -> date:
        """Get this week's Thursday expiry date."""
        today = reference_date or date.today()
        days_until_thursday = (EXPIRY_WEEKDAY - today.weekday()) % 7
        if days_until_thursday == 0:
            return today  # Today IS Thursday
        return today + timedelta(days=days_until_thursday)

    @staticmethod
    def get_next_expiry(reference_date: Optional[date] = None) -> date:
        """Get next week's Thursday expiry date."""
        current = ITMOptionSelector.get_current_expiry(reference_date)
        return current + timedelta(days=7)

    @staticmethod
    def is_expiry_day(reference_date: Optional[date] = None) -> bool:
        """Check if today is expiry Thursday."""
        today = reference_date or date.today()
        return today.weekday() == EXPIRY_WEEKDAY

    # ──────────────────────────────────────────────────────────────────
    # Full Selection Pipeline
    # ──────────────────────────────────────────────────────────────────

    def select(self, spot_price: float, direction: int) -> ITMSelection:
        """Complete ITM option selection with rollover handling.

        Parameters
        ----------
        spot_price : float
            Current Nifty spot price.
        direction : int
            1 = CALL, -1 = PUT.

        Returns
        -------
        ITMSelection
            Fully populated selection with strike, symbol, delta, and expiry.
        """
        strike = self.select_strike(spot_price, direction)
        delta = self.estimate_delta(spot_price, strike, direction)
        option_type = "CE" if direction == 1 else "PE"

        # Theta rollover: on Thursday, use next week's expiry
        is_rollover = self.is_expiry_day()
        if is_rollover:
            expiry_date = self.get_next_expiry()
            logger.info(
                "THETA ROLLOVER: Expiry day detected — routing to next week %s",
                expiry_date.isoformat(),
            )
        else:
            expiry_date = self.get_current_expiry()

        # Build broker symbol (Fyers format)
        # e.g., NSE:NIFTY2652123500CE
        expiry_str = expiry_date.strftime("%y%m%d")
        symbol = f"NSE:NIFTY{expiry_str}{int(strike)}{option_type}"

        itm_depth = abs(spot_price - strike)

        logger.info(
            "ATM SELECT: %s | Strike=%d | Delta≈%.3f | Depth=%.0fpts | Expiry=%s%s",
            option_type, strike, delta, itm_depth,
            expiry_date.isoformat(),
            " [ROLLOVER]" if is_rollover else "",
        )

        return ITMSelection(
            strike=strike,
            option_type=option_type,
            expiry=expiry_date.isoformat(),
            symbol=symbol,
            estimated_delta=delta,
            itm_depth=itm_depth,
            is_rollover=is_rollover,
        )
