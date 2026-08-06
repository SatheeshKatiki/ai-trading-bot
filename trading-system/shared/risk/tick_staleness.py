"""Tick-staleness detection for open positions.

Root cause / why this exists
-----------------------------
`trading_bot.main.on_tick()` only ever runs when a real tick actually
arrives — there is no independent timer. Every piece of exit management
(trailing stop, hard stop-loss, partial booking, pyramiding) lives inside
that function. If the tick feed goes silent while a position is open —
because the market is closed, or because of a genuine WebSocket outage
during real trading hours — absolutely nothing manages that position for
as long as the silence lasts. In paper mode the "stop loss" is a pure
software comparison against fresh ticks (unlike live mode, where a real
SL-M order sits at the exchange); a silent feed makes it completely inert
either way, since even the live SL-M placement path relies on this same
tick-driven loop to detect the hit and act on it.

Found live, 2026-08-06: a NIFTY position opened at 02:50 IST off a single
tick delivered just after a process restart, then received zero risk
management for 7h49m because no further ticks arrived until the market
reopened at 09:15 IST. The exact same mechanism — silence, then a sudden
large price "jump" the instant ticks resume — would apply equally to a
genuine multi-minute WebSocket outage during real market hours with real
capital at risk, and nothing in the system would have surfaced it.

Scope
-----
This module only detects and reports the condition. It does not change
trading behavior — no auto-halt, no forced exit, no entry gate. Whether
new entries should be blocked outside real exchange hours, or a stale
feed should trigger something more than a warning, are policy decisions
flagged in `docs/paper_trading_validation/anomaly_log.md`'s 2026-08-06
entry rather than decided here.

Engine-wide stall detection (`seconds_since_any_tick`)
-------------------------------------------------------
`find_stale_positions` only ever checks symbols with an open position — by
design, since it exists to protect capital at risk. That leaves a real gap:
if the engine goes quiet while genuinely flat, nothing reports it either,
even though a flat engine that has stopped processing ticks entirely can't
open new positions, and looks perfectly healthy from the outside (process
running, CPU can even be pegged if it's stuck rather than idle).

Found live, 2026-08-06, same session as the position-staleness incident
above: after a routine restart, `main.py` went CPU-bound (~98% of a core,
confirmed via repeated `py-spy dump` snapshots showing progression through
different pandas/indicator code paths — not a deadlock, genuine ongoing
computation) for 22+ minutes with **zero** log output and no open position
at risk. It was only caught by a human manually checking process CPU and
log timestamps side by side; nothing in the system would have surfaced it
on its own. Root cause not fully pinned down (did not reproduce on a clean
restart; likely tied to a burst of Fyers `429` rate-limit responses at that
specific boot, but not confirmed) — `seconds_since_any_tick` exists so the
*next* occurrence, whatever triggers it, is caught automatically instead of
requiring another manual investigation.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Optional

__all__ = [
    "DEFAULT_STALENESS_WARNING_S",
    "DEFAULT_ENGINE_STALL_WARNING_S",
    "StalePosition",
    "find_stale_positions",
    "seconds_since_any_tick",
]

#: Seconds without a tick before an open position's underlying is reported
#: stale. 90s sits above §2.11's baseline reconnect cadence (~1 per 160s
#: observed during idle market-closed hours) — a single missed tick or two
#: during a normal reconnect should not alert; a feed that has genuinely
#: gone quiet for a position-management-relevant span should.
DEFAULT_STALENESS_WARNING_S: float = 90.0

#: Seconds without ANY tick, across every watched symbol, before the whole
#: engine is reported stalled (checked only during market hours — silence
#: outside real trading hours is expected, not a fault). Same default as
#: the per-position threshold; kept as a separate setting since they answer
#: different questions and may need independent tuning.
DEFAULT_ENGINE_STALL_WARNING_S: float = 90.0


def seconds_since_any_tick(last_tick_at: Mapping[str, float], now: float) -> float:
    """How long since ANY watched symbol last ticked, regardless of whether
    a position is open in it.

    Returns `float("inf")` if nothing has ticked yet this process — treated
    as maximally stale rather than "no data yet, assume fine", matching
    `find_stale_positions`'s same choice for the identical reason: a
    process that has never received a tick is the worst case, not one to
    silently skip for lack of a baseline.
    """
    if not last_tick_at:
        return float("inf")
    return now - max(last_tick_at.values())


@dataclass(frozen=True)
class StalePosition:
    """One open position whose underlying hasn't ticked recently enough."""

    underlying_key: str   # active_positions dict key (the underlying symbol)
    traded_symbol: str    # the actual instrument held (may be an option on underlying_key)
    seconds_since_tick: float  # float("inf") if never ticked at all this process


def find_stale_positions(
    last_tick_at: Mapping[str, float],
    open_positions: Mapping[str, str],
    now: float,
    settings: Optional[Mapping[str, Any]] = None,
) -> list[StalePosition]:
    """Which open positions' underlyings haven't ticked within the warning window.

    Parameters
    ----------
    last_tick_at
        Underlying symbol -> `time.monotonic()` timestamp of its most
        recent tick, as observed by the caller (main.py tracks this at the
        top of `on_tick`).
    open_positions
        `active_positions` reduced to `{underlying_key: traded_symbol}` —
        deliberately just the two strings this needs, not the full
        `Position` object, so this stays a pure function over simple data.
    now
        Caller-supplied `time.monotonic()` reading — not read internally,
        so this is trivially testable without mocking the clock.
    settings
        Live settings mapping. Recognised key: `tick_staleness_warning_s`
        (default :data:`DEFAULT_STALENESS_WARNING_S`).

    Returns
    -------
    list[StalePosition]
        One entry per stale open position. A symbol with no entry in
        `last_tick_at` at all (never ticked once this process) is always
        included, with `seconds_since_tick = inf`, rather than silently
        skipped for lack of a baseline.
    """
    settings = settings or {}
    threshold = float(settings.get("tick_staleness_warning_s", DEFAULT_STALENESS_WARNING_S))

    stale: list[StalePosition] = []
    for underlying_key, traded_symbol in open_positions.items():
        last = last_tick_at.get(underlying_key)
        age = (now - last) if last is not None else float("inf")
        if age >= threshold:
            stale.append(StalePosition(underlying_key, traded_symbol, age))
    return stale
