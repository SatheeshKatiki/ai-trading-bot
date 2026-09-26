"""Observed-option-data research infrastructure (Phase 12).

RESEARCH ONLY. Nothing in this package is imported by `trading_bot/`,
`brokers/`, `api_bridge.py` or the frontend, and nothing in it can place an
order -- it imports no execution code at all.

Phases 8-11 established that this repository holds no historical option data:
the only real option quotes obtainable are LIVE, and they are discarded. This
package records them so the options question can eventually be answered from
observation rather than from a model.
"""
from .schema import (
    REQUIRE_OBSERVED_OPTION_DATA, SCHEMA_VERSION, OptionQuote, Provenance,
    Quality, SignalEvent, UnderlyingSnapshot, classify_quote,
)
from .store import ResearchStore

__all__ = ["REQUIRE_OBSERVED_OPTION_DATA", "SCHEMA_VERSION", "OptionQuote",
           "Provenance", "Quality", "SignalEvent", "UnderlyingSnapshot",
           "classify_quote", "ResearchStore"]
