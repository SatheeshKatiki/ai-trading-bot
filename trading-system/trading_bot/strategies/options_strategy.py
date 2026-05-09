"""Options Trading Strategy.

Implements advanced options strategies:
- Directional (Breakout/Scalping via ATM CE/PE)
- Bull Call Spread
- Bear Put Spread
- Iron Condor
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Dict, List, Optional

import pandas as pd

logger = logging.getLogger(__name__)


@dataclass
class OptionLeg:
    """Represents a single leg in an options strategy."""
    symbol: str
    strike: float
    option_type: str  # "CE" or "PE"
    side: int         # 1 for BUY, -1 for SELL
    quantity: int


@dataclass
class StrategySignal:
    """A generated trading signal."""
    strategy_name: str
    underlying: str
    legs: List[OptionLeg]
    confidence: float = 1.0


class OptionsStrategy:
    """Advanced Options Trading Strategy Engine.

    Supports directional scalping and multi-leg spread strategies.
    """

    def __init__(self, risk_reward_ratio: float = 2.0):
        self.risk_reward_ratio = risk_reward_ratio

    def get_atm_strike(self, current_price: float, strike_step: float = 50.0) -> float:
        """Calculate the At-The-Money strike price."""
        return round(current_price / strike_step) * strike_step

    def generate_directional_scalp(
        self,
        underlying_symbol: str,
        current_price: float,
        signal: int,  # 1 for bullish, -1 for bearish
        strike_step: float = 50.0,
        qty: int = 15,  # e.g., NIFTY lot size is typically 50, BankNifty 15
    ) -> Optional[StrategySignal]:
        """Generate a directional scalp trade using ATM CE or PE."""
        if signal == 0:
            return None

        atm_strike = self.get_atm_strike(current_price, strike_step)
        opt_type = "CE" if signal == 1 else "PE"
        
        # Simplified option symbol format: UNDERLYING + STRIKE + TYPE
        # Real format depends on broker (e.g., NSE:NIFTY24MAY22500CE)
        option_symbol = f"{underlying_symbol}_{int(atm_strike)}_{opt_type}"

        leg = OptionLeg(
            symbol=option_symbol,
            strike=atm_strike,
            option_type=opt_type,
            side=1,  # Option Buying
            quantity=qty,
        )

        return StrategySignal(
            strategy_name="Directional Scalp",
            underlying=underlying_symbol,
            legs=[leg],
        )

    def generate_bull_call_spread(
        self,
        underlying_symbol: str,
        current_price: float,
        strike_step: float = 50.0,
        spread_width: int = 1,
        qty: int = 15,
    ) -> StrategySignal:
        """Generate a Bull Call Spread.
        
        Buy ATM Call, Sell OTM Call.
        """
        atm_strike = self.get_atm_strike(current_price, strike_step)
        otm_strike = atm_strike + (strike_step * spread_width)

        leg_buy = OptionLeg(
            symbol=f"{underlying_symbol}_{int(atm_strike)}_CE",
            strike=atm_strike,
            option_type="CE",
            side=1,
            quantity=qty,
        )
        leg_sell = OptionLeg(
            symbol=f"{underlying_symbol}_{int(otm_strike)}_CE",
            strike=otm_strike,
            option_type="CE",
            side=-1,
            quantity=qty,
        )

        return StrategySignal(
            strategy_name="Bull Call Spread",
            underlying=underlying_symbol,
            legs=[leg_buy, leg_sell],
        )

    def generate_bear_put_spread(
        self,
        underlying_symbol: str,
        current_price: float,
        strike_step: float = 50.0,
        spread_width: int = 1,
        qty: int = 15,
    ) -> StrategySignal:
        """Generate a Bear Put Spread.
        
        Buy ATM Put, Sell OTM Put.
        """
        atm_strike = self.get_atm_strike(current_price, strike_step)
        otm_strike = atm_strike - (strike_step * spread_width)

        leg_buy = OptionLeg(
            symbol=f"{underlying_symbol}_{int(atm_strike)}_PE",
            strike=atm_strike,
            option_type="PE",
            side=1,
            quantity=qty,
        )
        leg_sell = OptionLeg(
            symbol=f"{underlying_symbol}_{int(otm_strike)}_PE",
            strike=otm_strike,
            option_type="PE",
            side=-1,
            quantity=qty,
        )

        return StrategySignal(
            strategy_name="Bear Put Spread",
            underlying=underlying_symbol,
            legs=[leg_buy, leg_sell],
        )

    def generate_iron_condor(
        self,
        underlying_symbol: str,
        current_price: float,
        strike_step: float = 50.0,
        wing_width: int = 2,
        protect_width: int = 1,
        qty: int = 15,
    ) -> StrategySignal:
        """Generate an Iron Condor.
        
        Sell OTM Call & OTM Put (Wings).
        Buy further OTM Call & further OTM Put (Protection).
        Suitable for sideways/range-bound markets.
        """
        atm_strike = self.get_atm_strike(current_price, strike_step)

        # Call Spread (Bearish wing)
        short_call_strike = atm_strike + (strike_step * wing_width)
        long_call_strike = short_call_strike + (strike_step * protect_width)

        # Put Spread (Bullish wing)
        short_put_strike = atm_strike - (strike_step * wing_width)
        long_put_strike = short_put_strike - (strike_step * protect_width)

        legs = [
            OptionLeg(f"{underlying_symbol}_{int(short_call_strike)}_CE", short_call_strike, "CE", -1, qty),
            OptionLeg(f"{underlying_symbol}_{int(long_call_strike)}_CE", long_call_strike, "CE", 1, qty),
            OptionLeg(f"{underlying_symbol}_{int(short_put_strike)}_PE", short_put_strike, "PE", -1, qty),
            OptionLeg(f"{underlying_symbol}_{int(long_put_strike)}_PE", long_put_strike, "PE", 1, qty),
        ]

        return StrategySignal(
            strategy_name="Iron Condor",
            underlying=underlying_symbol,
            legs=legs,
        )
