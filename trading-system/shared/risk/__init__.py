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
]
