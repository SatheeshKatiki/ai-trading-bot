"""Smart Exit System for managing open positions.

Implements advanced exit strategies including:
- Dynamic trailing stop-loss (ATR-based)
- Partial profit booking
- Time-based exit (EOD square-off)
- Volatility-based exit
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

import pandas as pd

logger = logging.getLogger(__name__)


@dataclass
class Position:
    """Represents an open trade position."""
    symbol: str
    side: int                # 1 for Long, -1 for Short
    entry_price: float
    quantity: int
    entry_time: str
    highest_price: float     # Highest price reached since entry (for long)
    lowest_price: float      # Lowest price reached since entry (for short)
    stop_loss: float         # Current stop-loss price
    target: float            # Current profit target
    is_partially_booked: bool = False
    scales_done: int = 0     # Number of times this position has been scaled into
    lot_size: int = 1        # Lot size for quantity rounding
    is_exiting: bool = False # Lock flag: True while background iceberg exit is in flight
    sl_order_id: str = None  # Exchange ID for the active Hard SL order


class SmartExitEngine:
    """Engine for determining when to exit a position.

    Combines multiple exit strategies:
    1. Hard Stop-Loss / Profit Target
    2. ATR Trailing Stop
    3. Time-based End-of-Day Exit
    4. Partial Profit Booking
    """

    def __init__(
        self,
        atr_multiplier: float = 2.0,
        trailing_activation_pct: float = 1.0,
        eod_exit_time: str = "15:15:00",
        partial_booking_pct: float = 50.0,
        partial_target_reward: float = 1.0,
    ):
        """
        Parameters
        ----------
        atr_multiplier : float
            Multiplier for ATR to set trailing stop distance.
        trailing_activation_pct : float
            Profit percentage required before trailing stop activates.
        eod_exit_time : str
            Time (HH:MM:SS) to square off all intraday positions.
        partial_booking_pct : float
            Percentage of position to close at partial target.
        partial_target_reward : float
            Reward-to-risk ratio at which to take partial profit.
        """
        self.atr_multiplier = atr_multiplier
        self.trailing_activation_pct = trailing_activation_pct
        self.eod_exit_time = eod_exit_time
        self.partial_booking_pct = partial_booking_pct
        self.partial_target_reward = partial_target_reward

    def evaluate_exit(
        self,
        position: Position,
        current_price: float,
        current_time: str,  # HH:MM:SS format expected for intraday
        current_atr: float,
    ) -> tuple[bool, str, Optional[int]]:
        """Evaluate if the position should be exited or partially booked.

        Parameters
        ----------
        position : Position
            The open position to evaluate.
        current_price : float
            Latest price of the asset.
        current_time : str
            Current time (e.g., '14:30:00').
        current_atr : float
            Current Average True Range.

        Returns
        -------
        tuple[bool, str, Optional[int]]
            (Should Exit, Reason, Quantity to Exit).
            If Should Exit is True and Quantity is None, exit full position.
        """
        # 1. Update position extremes for trailing stop
        if position.side == 1:
            position.highest_price = max(position.highest_price, current_price)
        elif position.side == -1:
            position.lowest_price = min(position.lowest_price, current_price)

        # 2. Time-based exit (EOD Square-off)
        # Extract time part if current_time contains date (e.g., "YYYY-MM-DD HH:MM:SS")
        time_only = current_time.split(" ")[-1] if " " in current_time else current_time
        if time_only >= self.eod_exit_time:
            logger.info("EOD Exit triggered for %s at %s", position.symbol, current_time)
            return True, "Time-based EOD Exit", None

        # 3. Hard Stop-Loss and Profit Target
        if position.side == 1:
            if current_price <= position.stop_loss:
                return True, "Stop-Loss Hit", None
            if current_price >= position.target:
                return True, "Profit Target Hit", None
        elif position.side == -1:
            if current_price >= position.stop_loss:
                return True, "Stop-Loss Hit", None
            if current_price <= position.target:
                return True, "Profit Target Hit", None

        # 4. Partial Profit Booking
        if not position.is_partially_booked:
            risk = abs(position.entry_price - position.stop_loss)
            if risk > 0:
                if position.side == 1:
                    unrealized_reward = current_price - position.entry_price
                else:
                    unrealized_reward = position.entry_price - current_price

                if (unrealized_reward / risk) >= self.partial_target_reward:
                    qty_to_book = int(position.quantity * (self.partial_booking_pct / 100))
                    if qty_to_book > 0:
                        position.is_partially_booked = True
                        # Move stop loss to breakeven after partial booking
                        position.stop_loss = position.entry_price
                        return True, f"Partial Profit Booking (1:{self.partial_target_reward})", qty_to_book
                    elif position.quantity == 1:
                        position.is_partially_booked = True
                        position.stop_loss = position.entry_price
                        import logging
                        logging.getLogger(__name__).info("Single lot partial target reached. Trailing SL to breakeven for %s", position.symbol)

        # 5. ATR Trailing Stop (Activates only after a certain profit percentage)
        profit_pct = 0.0
        if position.side == 1:
            profit_pct = (current_price - position.entry_price) / position.entry_price * 100
        else:
            profit_pct = (position.entry_price - current_price) / position.entry_price * 100

        if profit_pct >= self.trailing_activation_pct:
            if position.side == 1:
                # Trailing stop for Long
                trailing_stop = position.highest_price - (current_atr * self.atr_multiplier)
                # Only move stop loss UP
                if trailing_stop > position.stop_loss:
                    position.stop_loss = trailing_stop
            elif position.side == -1:
                # Trailing stop for Short
                trailing_stop = position.lowest_price + (current_atr * self.atr_multiplier)
                # Only move stop loss DOWN
                if trailing_stop < position.stop_loss:
                    position.stop_loss = trailing_stop

            # Check trailing stop immediately after updating
            if position.side == 1 and current_price <= position.stop_loss:
                return True, "Trailing Stop-Loss Hit", None
            if position.side == -1 and current_price >= position.stop_loss:
                return True, "Trailing Stop-Loss Hit", None

        return False, "", None
