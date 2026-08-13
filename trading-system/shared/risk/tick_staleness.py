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
    "DEFAULT_FEED_REBUILD_THRESHOLD_S",
    "DEFAULT_HEARTBEAT_STALE_THRESHOLD_S",
    "StalePosition",
    "find_stale_positions",
    "seconds_since_any_tick",
    "should_rebuild_stale_feed",
    "heartbeat_is_stale",
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


#: Same threshold as DEFAULT_ENGINE_STALL_WARNING_S, for the same reason
#: given there — kept as its own name/constant since it answers a
#: different question (should the upstream feed connection itself be
#: rebuilt) at a different layer (api_bridge.py's Fyers socket, not
#: main.py's tick consumption).
DEFAULT_FEED_REBUILD_THRESHOLD_S: float = 90.0


def should_rebuild_stale_feed(
    last_message_at: float,
    now: float,
    market_open: bool,
    threshold_s: float = DEFAULT_FEED_REBUILD_THRESHOLD_S,
) -> bool:
    """Should api_bridge.py force-rebuild its upstream Fyers WebSocket?

    Root cause (found live, 2026-08-12): the vendored fyers_apiv3 client's
    own `reconnect=True` never fires for a zombie TCP connection — its
    keepalive ping (`data_ws.py`'s `__ping`) is fire-and-forget, sent as
    long as the OS socket merely reports itself `connected`, with no pong
    check. A network blip left the socket in exactly that false-connected
    state for 46 minutes during real market hours, silently starving
    `trading_bot/main.py` of every tick, before a manual process restart
    fixed it. This is the independent, receiving-side check that catches
    what the library itself cannot.

    Parameters
    ----------
    last_message_at
        `time.time()` reading from the last message actually received
        from Fyers (any message — not just a priced tick — proves the
        socket is alive; see api_bridge.py's `on_message`). `0.0` means
        never connected yet this process lifetime.
    now
        Caller-supplied `time.time()` reading — not read internally, so
        this stays trivially testable without mocking the clock.
    market_open
        Caller-supplied result of `shared.market_hours.is_market_open()`.
        Silence outside real trading hours is expected, not a fault —
        same reasoning as the engine-wide stall check above.
    """
    if last_message_at == 0.0:
        return False
    if not market_open:
        return False
    return (now - last_message_at) >= threshold_s


#: Seconds without a fresh heartbeat write before main.py's event loop is
#: considered frozen (not just its tick feed). Deliberately larger than
#: main.py's own ~15s heartbeat-write interval to tolerate normal jitter
#: without false-positiving on a process that's merely busy.
DEFAULT_HEARTBEAT_STALE_THRESHOLD_S: float = 120.0


def heartbeat_is_stale(
    last_heartbeat_at: float,
    now: float,
    threshold_s: float = DEFAULT_HEARTBEAT_STALE_THRESHOLD_S,
) -> bool:
    """Has main.py's own heartbeat gone stale for long enough that its
    event loop should be considered frozen, not just its tick feed?

    Root cause (found live, 2026-08-13): main.py had no signal at all for
    "is the event loop itself still scheduling tasks" independent of
    ticks arriving — a ~39-minute total freeze (not just the tick path,
    but a separate background thread too) was only found by manually
    reviewing logs hours later. main.py now writes `time.time()` to
    `run/main_heartbeat.txt` on a fixed ~15s cadence from a task with no
    dependency on ticks, broker calls, or anything else that could block
    it (see run_live_bot's `heartbeat_writer`). api_bridge.py's
    `main_process_watchdog` reads that file and calls this function —
    the independent, receiving-side check, mirroring
    `should_rebuild_stale_feed`'s relationship to the Fyers feed above,
    but one layer further out (main.py's whole process, not just its
    upstream connection).

    Parameters
    ----------
    last_heartbeat_at
        `time.time()` reading parsed from the heartbeat file. `0.0` means
        no heartbeat has been read yet (e.g. the file doesn't exist) —
        treated as "not stale" here for the same reason
        `should_rebuild_stale_feed` treats a never-connected feed as not
        stale: a process that hasn't had a chance to write its first
        heartbeat yet (just starting up) shouldn't look identical to one
        that has gone silent after running fine for a while. Callers that
        also track how long the process's PID has been alive can layer
        that distinction on top of this function's result.
    now
        Caller-supplied `time.time()` reading — not read internally, so
        this stays trivially testable without mocking the clock.
    """
    if last_heartbeat_at == 0.0:
        return False
    return (now - last_heartbeat_at) >= threshold_s


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
