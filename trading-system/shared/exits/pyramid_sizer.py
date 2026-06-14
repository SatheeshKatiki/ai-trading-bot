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
        points_trigger: float = 40.0,
        max_scales: int = 2,
    ):
        """
        Parameters
        ----------
        points_trigger : float
            Number of points in profit required to trigger the next scale.
        max_scales : int
            Maximum number of times to scale in.
        """
        self.points_trigger = points_trigger
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
        # Scale 1 requires 40 pts, Scale 2 requires 80 pts, etc.
        required_profit = (position.scales_done + 1) * self.points_trigger

        if profit_points >= required_profit:
            reason = f"Profit hit +{profit_points:.1f} pts (Target: {required_profit:.1f} pts)"
            return True, reason

        return False, ""
