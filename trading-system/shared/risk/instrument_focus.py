"""Per-instrument AI-confidence gating: NIFTY/SENSEX vs BANKNIFTY/FINNIFTY.

Root cause / design
--------------------
The engine previously watched a single instrument (NIFTY). Expanding the
live symbol list to all four tradeable indices (NIFTY, BANKNIFTY, FINNIFTY,
SENSEX) multiplies concurrent exposure and entry-evaluation load, and the
four are not equally liquid or equally well-covered by this system's
strategy tuning — NIFTY and SENSEX are the priority instruments.

Rather than a vague "focus" preference, this applies the exact mechanism
the codebase already uses to gate a stricter strategy: `main.py` raises the
minimum AI confidence from 0.60 to 0.85 for the `enhanced_ai` strategy. The
same lever, applied per-instrument instead of per-strategy, means NIFTY and
SENSEX trade at whatever bar the active strategy already sets, while
BANKNIFTY and FINNIFTY need a stricter one — fewer, higher-conviction
entries on the secondary instruments, with position sizing and every risk
cap left completely uniform across all four (this module makes no sizing or
risk decisions; see shared/risk/manager.py and
shared/risk/option_stop_loss.py for those).

This is deliberately a pure function over ``settings`` rather than a class
holding state: it is called once per symbol per tick-evaluation cycle in
main.py's hot loop, and a stateless resolver is trivial to unit test and
impossible to get out of sync with the settings file.
"""
from __future__ import annotations

from typing import Any, Mapping, Optional

__all__ = [
    "DEFAULT_FOCUS_INSTRUMENTS",
    "DEFAULT_SECONDARY_MIN_CONFIDENCE",
    "resolve_min_confidence",
]

#: Instruments that trade at the strategy's own confidence bar, unmodified.
DEFAULT_FOCUS_INSTRUMENTS: tuple[str, ...] = ("NIFTY", "SENSEX")

#: Floor applied to every instrument NOT in the focus set.
DEFAULT_SECONDARY_MIN_CONFIDENCE: float = 0.85


def resolve_min_confidence(
    instrument: str,
    base_min_confidence: float,
    settings: Optional[Mapping[str, Any]] = None,
) -> float:
    """The AI-confidence floor a signal on ``instrument`` must clear.

    Parameters
    ----------
    instrument
        Canonical instrument key (``"NIFTY"``, ``"BANKNIFTY"``,
        ``"FINNIFTY"``, ``"SENSEX"``) — see
        ``shared.instruments.normalize_instrument``.
    base_min_confidence
        The threshold the active strategy already computed (e.g. 0.60, or
        0.85 for ``enhanced_ai``). This is never *lowered* — a focus
        instrument gets exactly this value back, a secondary instrument
        gets at least this value.
    settings
        Live settings mapping. Recognised keys, both optional:

        ``focus_instruments``
            Iterable of instrument keys that keep ``base_min_confidence``
            unchanged. Defaults to :data:`DEFAULT_FOCUS_INSTRUMENTS`.
        ``secondary_instrument_min_confidence``
            Floor applied to everything else. Defaults to
            :data:`DEFAULT_SECONDARY_MIN_CONFIDENCE`.

    Returns
    -------
    float
        ``base_min_confidence`` for a focus instrument;
        ``max(base_min_confidence, secondary_instrument_min_confidence)``
        otherwise — so a strategy that is already stricter than the
        secondary floor (e.g. ``enhanced_ai`` at 0.85) is never relaxed by
        this function.
    """
    settings = settings or {}
    focus = settings.get("focus_instruments", DEFAULT_FOCUS_INSTRUMENTS)
    focus_set = {str(item).upper() for item in focus}

    if instrument.upper() in focus_set:
        return base_min_confidence

    secondary = float(
        settings.get("secondary_instrument_min_confidence", DEFAULT_SECONDARY_MIN_CONFIDENCE)
    )
    return max(base_min_confidence, secondary)
