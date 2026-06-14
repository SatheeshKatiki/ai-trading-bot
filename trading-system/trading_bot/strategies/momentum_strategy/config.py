"""Institutional Momentum Strategy — Configuration & Constants.

All tunable parameters, market constants, and dataclasses live here.
Single source of truth for the entire strategy engine.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import time
from typing import List, Tuple


# ─────────────────────────────────────────────────────────────────────
# MARKET CONSTANTS
# ─────────────────────────────────────────────────────────────────────

NIFTY_LOT_SIZE: int = 65
NIFTY_STRIKE_INTERVAL: int = 50  # Nifty options have 50-point strike gaps

# ─────────────────────────────────────────────────────────────────────
# MACRO ENVIRONMENT FILTERS
# ─────────────────────────────────────────────────────────────────────

VIX_MIN: float = 12.0
VIX_MAX: float = 21.0

# IST time windows where fresh entries are permitted
ENTRY_WINDOWS: List[Tuple[time, time]] = [
    (time(9, 30), time(11, 15)),   # Morning momentum window
    (time(13, 30), time(14, 45)),  # Afternoon trend continuation
]

# Hard EOD square-off time (no new entries after this)
EOD_SQUARE_OFF: time = time(15, 15)

# ─────────────────────────────────────────────────────────────────────
# SIGNAL GENERATION
# ─────────────────────────────────────────────────────────────────────

# 1-Hour trend confirmation EMAs
TREND_EMA_FAST: int = 50
TREND_EMA_SLOW: int = 200

# 5-Minute breakout parameters
BREAKOUT_EMA_FAST: int = 9
BREAKOUT_EMA_SLOW: int = 21

# Volume confirmation multiplier
VOLUME_BREAKOUT_MULT: float = 1.5
VOLUME_SMA_PERIOD: int = 20

# Runner trailing EMA (for Phase 3 exit)
RUNNER_EMA_PERIOD: int = 50

# ─────────────────────────────────────────────────────────────────────
# ATM OPTION SELECTION
# ─────────────────────────────────────────────────────────────────────

ITM_OFFSET_MIN: int = 0  # 0 points deep = ATM
ITM_OFFSET_MAX: int = 0  # 0 points deep = ATM
DELTA_TARGET_MIN: float = 0.45
DELTA_TARGET_MAX: float = 0.55

# ─────────────────────────────────────────────────────────────────────
# EXECUTION & RISK
# ─────────────────────────────────────────────────────────────────────

MAX_TRADES_PER_DAY: int = 4
CIRCUIT_BREAKER_PCT: float = 0.02    # -2% of capital = daily halt
COOLDOWN_MINUTES: int = 30           # Anti-whipsaw directional lock
CONSECUTIVE_SL_HALT: int = 2         # Halt after 2 consecutive SL hits

# Target-based sizing: structure trades for ₹5,000 profit at 1:2 R:R
TARGET_PROFIT_PER_TRADE: float = 5000.0
REWARD_TO_RISK_RATIO: float = 2.0

# ─────────────────────────────────────────────────────────────────────
# TIERED EXIT LOGIC
# ─────────────────────────────────────────────────────────────────────

PARTIAL_BOOK_RATIO: float = 0.35     # Book 35% at Phase 1
PARTIAL_BOOK_RR: float = 3.0         # Trigger at 1:3 Risk:Reward

# ─────────────────────────────────────────────────────────────────────
# MTM PROFIT TRAILING ENGINE
# ─────────────────────────────────────────────────────────────────────

MTM_ACTIVATION_THRESHOLD: float = 10000.0   # Activate engine at ₹10K MTM
MTM_FLOOR_INITIAL: float = 3000.0          # Lock minimum ₹3K profit
MTM_STEP_INCREMENT: float = 3000.0         # Every ₹3K above activation
MTM_FLOOR_RATCHET: float = 1500.0          # Floor moves up by ₹1.5K per step


# ─────────────────────────────────────────────────────────────────────
# DATA CLASSES
# ─────────────────────────────────────────────────────────────────────

@dataclass
class MomentumSignal:
    """Output of the signal engine."""
    direction: int            # 1 = CALL (Long), -1 = PUT (Short), 0 = No Signal
    strength: float           # 0.0 to 1.0 composite confidence
    breakout_price: float     # Price at which breakout was detected
    vwap_price: float         # Current VWAP level
    trend_1hr: int            # 1 = Bullish, -1 = Bearish, 0 = Neutral
    volume_ratio: float       # Current volume / VMA(20)
    reason: str = ""          # Human-readable signal reason


@dataclass
class ITMSelection:
    """Output of the ITM option selector."""
    strike: float             # Selected strike price
    option_type: str          # "CE" or "PE"
    expiry: str               # Expiry date string (e.g., "2026-05-21")
    symbol: str               # Full broker symbol (e.g., "NSE:NIFTY26MAY23500CE")
    estimated_delta: float    # Approximate delta
    itm_depth: float          # Points in-the-money
    is_rollover: bool = False # True if using next week's expiry (Thursday)


@dataclass
class ExitDecision:
    """Output of the exit manager."""
    should_exit: bool = False
    reason: str = ""
    quantity_pct: float = 1.0  # 1.0 = full exit, 0.35 = partial
    move_sl_to_be: bool = False
    phase: int = 0             # 1, 2, or 3


@dataclass
class DayState:
    """Thread-safe daily state tracker for the strategy."""
    trades_today: int = 0
    consecutive_sl: int = 0
    last_sl_direction: int = 0           # Direction of last SL hit (for anti-whipsaw)
    last_sl_time: float = 0.0            # Timestamp of last SL hit
    is_halted: bool = False
    halt_reason: str = ""
    daily_vix: float = 0.0
    mtm_peak: float = 0.0
    mtm_floor: float = 0.0
    mtm_engine_active: bool = False
