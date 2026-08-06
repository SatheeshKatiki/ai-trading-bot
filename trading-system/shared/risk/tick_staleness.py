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
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Optional

__all__ = ["DEFAULT_STALENESS_WARNING_S", "StalePosition", "find_stale_positions"]

#: Seconds without a tick before an open position's underlying is reported
#: stale. 90s sits above §2.11's baseline reconnect cadence (~1 per 160s
#: observed during idle market-closed hours) — a single missed tick or two
#: during a normal reconnect should not alert; a feed that has genuinely
#: gone quiet for a position-management-relevant span should.
DEFAULT_STALENESS_WARNING_S: float = 90.0


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
