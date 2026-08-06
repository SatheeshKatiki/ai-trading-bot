"""shared/risk/tick_staleness.py — detecting an unmonitored open position,
and a stalled engine even when flat.

Root cause: on_tick() (and everything inside it, including all exit
management) only ever runs when a real tick arrives. If the feed goes
silent while a position is open, nothing manages that position for as long
as the silence lasts, and nothing previously reported this. Found live
2026-08-06: a position opened at 02:50 IST off one post-restart snapshot
tick, then received zero risk management for 7h49m.

find_stale_positions() is the pure detection logic behind the watchdog
task in main.py — these tests cover it directly since the watchdog itself
is an infinite asyncio loop that isn't practical to unit test.

seconds_since_any_tick() covers a second, related incident from the same
session: main.py went CPU-bound for 22+ minutes with zero log output while
genuinely flat (no open position for find_stale_positions to protect).
Nothing reported it; it was only caught by a human cross-checking process
CPU against log timestamps. This is the engine-wide counterpart, checked
regardless of whether any position is open.
"""
import _bootstrap  # noqa: F401  (side-effect: puts trading-system/ on sys.path)

import pytest

from shared.risk.tick_staleness import (
    DEFAULT_ENGINE_STALL_WARNING_S,
    DEFAULT_STALENESS_WARNING_S,
    StalePosition,
    find_stale_positions,
    seconds_since_any_tick,
)


def test_a_recently_ticked_position_is_not_stale():
    last_tick_at = {"NSE:NIFTY50-INDEX": 1_000.0}
    open_positions = {"NSE:NIFTY50-INDEX": "NSE:NIFTY2681124600CE"}

    result = find_stale_positions(last_tick_at, open_positions, now=1_010.0)

    assert result == []


def test_a_position_silent_past_the_threshold_is_reported():
    last_tick_at = {"NSE:NIFTY50-INDEX": 1_000.0}
    open_positions = {"NSE:NIFTY50-INDEX": "NSE:NIFTY2681124600CE"}

    result = find_stale_positions(last_tick_at, open_positions, now=1_000.0 + DEFAULT_STALENESS_WARNING_S)

    assert result == [
        StalePosition("NSE:NIFTY50-INDEX", "NSE:NIFTY2681124600CE", DEFAULT_STALENESS_WARNING_S)
    ]


def test_exactly_at_the_threshold_counts_as_stale():
    """>= threshold, not >, matching the docstring's "at least this many
    seconds" framing — a position exactly at the boundary should not be
    silently excluded by an off-by-one."""
    last_tick_at = {"SYM": 0.0}
    open_positions = {"SYM": "SYM-OPT"}

    result = find_stale_positions(last_tick_at, open_positions, now=90.0, settings={"tick_staleness_warning_s": 90.0})

    assert len(result) == 1


def test_a_symbol_that_never_ticked_is_always_reported_as_infinitely_stale():
    """No baseline to measure from is not the same as "fine" — a position
    whose underlying never once ticked this process is the worst case, not
    one to silently skip for lack of data."""
    open_positions = {"NSE:FINNIFTY-INDEX": "NSE:FINNIFTY2681123750CE"}

    result = find_stale_positions({}, open_positions, now=100_000.0)

    assert len(result) == 1
    assert result[0].seconds_since_tick == float("inf")


def test_only_open_positions_are_considered_not_every_tracked_symbol():
    """A symbol with no open position (e.g. one that's ticking fine but has
    nothing riding on it) must not be reported — this only matters for
    positions actually at risk."""
    last_tick_at = {"NSE:NIFTY50-INDEX": 0.0, "BSE:SENSEX-INDEX": 0.0}
    open_positions = {"NSE:NIFTY50-INDEX": "NSE:NIFTY2681124600CE"}  # SENSEX has no position

    result = find_stale_positions(last_tick_at, open_positions, now=100_000.0)

    assert len(result) == 1
    assert result[0].underlying_key == "NSE:NIFTY50-INDEX"


def test_no_open_positions_means_nothing_is_ever_reported():
    result = find_stale_positions({"NSE:NIFTY50-INDEX": 0.0}, {}, now=100_000.0)
    assert result == []


def test_multiple_stale_positions_are_all_reported():
    last_tick_at = {"NSE:NIFTY50-INDEX": 0.0, "BSE:SENSEX-INDEX": 0.0}
    open_positions = {
        "NSE:NIFTY50-INDEX": "NSE:NIFTY2681124600CE",
        "BSE:SENSEX-INDEX": "BSE:SENSEX2680678600CE",
    }

    result = find_stale_positions(last_tick_at, open_positions, now=1_000.0)

    assert {s.underlying_key for s in result} == {"NSE:NIFTY50-INDEX", "BSE:SENSEX-INDEX"}


def test_custom_threshold_is_honoured():
    last_tick_at = {"SYM": 1_000.0}
    open_positions = {"SYM": "SYM-OPT"}

    # 5s gap: stale under a 2s threshold, fine under a 10s threshold.
    assert find_stale_positions(last_tick_at, open_positions, now=1_005.0, settings={"tick_staleness_warning_s": 2.0})
    assert not find_stale_positions(last_tick_at, open_positions, now=1_005.0, settings={"tick_staleness_warning_s": 10.0})


def test_missing_settings_falls_back_to_the_default_threshold():
    last_tick_at = {"SYM": 0.0}
    open_positions = {"SYM": "SYM-OPT"}

    just_under = find_stale_positions(last_tick_at, open_positions, now=DEFAULT_STALENESS_WARNING_S - 1, settings=None)
    at_threshold = find_stale_positions(last_tick_at, open_positions, now=DEFAULT_STALENESS_WARNING_S, settings={})

    assert just_under == []
    assert len(at_threshold) == 1


def test_the_docstring_scenario_is_reproduced():
    """The exact live incident this module was built from: a position
    entered, then silent for 7h49m (28,140s) — must be reported, and the
    reported age must reflect the real gap, not be clamped or rounded away."""
    entry_tick_time = 0.0
    seven_hours_49_min_later = 7 * 3600 + 49 * 60

    result = find_stale_positions(
        {"NSE:NIFTY50-INDEX": entry_tick_time},
        {"NSE:NIFTY50-INDEX": "NSE:NIFTY2681124600CE"},
        now=float(seven_hours_49_min_later),
    )

    assert len(result) == 1
    assert result[0].seconds_since_tick == pytest.approx(28_140.0)


# ---------------------------------------------------------------------------
# seconds_since_any_tick — engine-wide stall, independent of open positions
# ---------------------------------------------------------------------------

def test_no_ticks_ever_is_infinitely_stale():
    assert seconds_since_any_tick({}, now=100_000.0) == float("inf")


def test_recent_tick_on_any_symbol_means_the_engine_is_alive():
    last_tick_at = {"NSE:NIFTY50-INDEX": 995.0, "BSE:SENSEX-INDEX": 990.0}
    assert seconds_since_any_tick(last_tick_at, now=1_000.0) == pytest.approx(5.0)


def test_uses_the_most_recent_tick_across_all_symbols_not_the_oldest():
    """One symbol ticking is enough to prove the feed/event-loop is alive —
    this must not be dragged down by a different symbol that happens to be
    individually quiet (that's find_stale_positions's job, not this one's)."""
    last_tick_at = {
        "NSE:NIFTY50-INDEX": 500.0,     # stale on its own
        "BSE:SENSEX-INDEX": 999.0,      # just ticked
        "NSE:NIFTYBANK-INDEX": 700.0,
    }
    assert seconds_since_any_tick(last_tick_at, now=1_000.0) == pytest.approx(1.0)


def test_the_live_incident_is_reproduced():
    """The exact scenario this function was built from: 22+ minutes of
    silence across every watched symbol, engine otherwise flat."""
    last_tick_at = {
        "NSE:NIFTY50-INDEX": 0.0,
        "BSE:SENSEX-INDEX": 0.0,
        "NSE:NIFTYBANK-INDEX": 0.0,
        "NSE:FINNIFTY-INDEX": 0.0,
    }
    twenty_two_minutes = 22 * 60

    age = seconds_since_any_tick(last_tick_at, now=float(twenty_two_minutes))

    assert age == pytest.approx(1_320.0)
    assert age >= DEFAULT_ENGINE_STALL_WARNING_S


def test_default_engine_stall_threshold_matches_the_position_threshold():
    """Not load-bearing behavior, just documents the deliberate choice that
    both default to the same value even though they're independently
    configurable — see the module docstring."""
    assert DEFAULT_ENGINE_STALL_WARNING_S == DEFAULT_STALENESS_WARNING_S
