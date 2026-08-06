"""Risk management package."""

from .manager import RiskManager, RiskConfig, TradeRecord
from .option_stop_loss import (
    DEFAULT_BANDS,
    DEFAULT_DYNAMIC_BAND,
    StopLossBand,
    StopLossDecision,
    resolve_initial_stop,
    resolve_stop_points,
)
from .instrument_focus import (
    DEFAULT_FOCUS_INSTRUMENTS,
    DEFAULT_SECONDARY_MIN_CONFIDENCE,
    resolve_min_confidence,
)
from .tick_staleness import (
    DEFAULT_STALENESS_WARNING_S,
    DEFAULT_ENGINE_STALL_WARNING_S,
    StalePosition,
    find_stale_positions,
    seconds_since_any_tick,
)

__all__ = [
    "RiskManager",
    "RiskConfig",
    "TradeRecord",
    "StopLossBand",
    "StopLossDecision",
    "DEFAULT_BANDS",
    "DEFAULT_DYNAMIC_BAND",
    "resolve_initial_stop",
    "resolve_stop_points",
    "DEFAULT_FOCUS_INSTRUMENTS",
    "DEFAULT_SECONDARY_MIN_CONFIDENCE",
    "resolve_min_confidence",
    "DEFAULT_STALENESS_WARNING_S",
    "DEFAULT_ENGINE_STALL_WARNING_S",
    "StalePosition",
    "find_stale_positions",
    "seconds_since_any_tick",
]
