"""Exit Ladder & Ratchet Stop Module for EMA 9 / Fibo OTE Momentum Pro.

Re-exports the institutional profit ladder ratchet and stop level helpers.
"""

from __future__ import annotations

from trading_bot.strategies.ema9_rsi_momentum.exit_ladder import (
    DEFAULT_INITIAL_SL_PCT,
    DEFAULT_PROFIT_LADDER_PCT,
    initial_stop,
    ladder_levels,
    ratchet_stop,
    stop_reason,
)

__all__ = [
    "DEFAULT_PROFIT_LADDER_PCT",
    "DEFAULT_INITIAL_SL_PCT",
    "ladder_levels",
    "ratchet_stop",
    "initial_stop",
    "stop_reason",
]
