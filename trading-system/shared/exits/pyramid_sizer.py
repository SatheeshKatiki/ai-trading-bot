"""Pyramiding (Scaling In) Execution Sizer.

Evaluates open positions to determine if they have moved into enough profit
to warrant adding more size (compounding).
"""

from __future__ import annotations

import logging
from typing import Tuple

from .exit_engine import Position

logger = logging.getLogger(__name__)

class PyramidSizer:
    """Evaluates when to scale into winning positions.
    
    Pyramiding mathematics:
    When a trade moves into profit, you use the unrealized gains ("house money")
    to add to your position. This allows massive upside on trend days without 
    increasing the initial risk on sideways days.
    """

    def __init__(
        self,
        pct_trigger: float = 0.2,
        max_scales: int = 2,
    ):
        """
        Parameters
        ----------
        pct_trigger : float
            Percentage of profit from entry price required to trigger the next scale.
        max_scales : int
            Maximum number of times to scale in.
        """
        self.pct_trigger = pct_trigger
        self.max_scales = max_scales

    def evaluate_scale(self, position: Position, current_price: float) -> Tuple[bool, str]:
        """Evaluate if the position should be scaled into.

        Parameters
        ----------
        position : Position
            The open position to evaluate.
        current_price : float
            Latest price of the asset.

        Returns
        -------
        tuple[bool, str]
            (Should Scale, Reason)
        """
        if position.scales_done >= self.max_scales:
            return False, ""

        # Calculate profit in points
        if position.side == 1:
            profit_points = current_price - position.entry_price
        else:
            profit_points = position.entry_price - current_price

        # Determine how many points are needed for the next scale
        # Scale 1 requires entry * pct_trigger%, Scale 2 requires entry * 2*pct_trigger%, etc.
        pts_per_scale = position.entry_price * (self.pct_trigger / 100.0)
        required_profit = (position.scales_done + 1) * pts_per_scale

        if profit_points >= required_profit:
            profit_pct = (profit_points / position.entry_price) * 100
            reason = f"Profit hit +{profit_pct:.2f}% (Target: {((position.scales_done + 1) * self.pct_trigger):.2f}%)"
            return True, reason

        return False, ""
