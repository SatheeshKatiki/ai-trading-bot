"""Regression tests for trading_bot/main.py's heartbeat write
(_write_heartbeat / _HEARTBEAT_PATH / _HEARTBEAT_WRITE_INTERVAL_S).

Root cause (found live, 2026-08-13): main.py had no signal at all for "is
the event loop itself still scheduling tasks" independent of ticks
arriving -- a ~39-minute total freeze (not just the tick path, a separate
background thread too) was only found by manually reviewing logs hours
later. main.py's run_live_bot now starts a heartbeat_writer task that
calls _write_heartbeat on a fixed ~15s cadence, with no dependency on
ticks/broker calls/anything blockable. _write_heartbeat itself (the
actual atomic-write behavior) is pulled out to module scope specifically
so it's testable without spinning up the real event loop -- same
reasoning as _compute_retry_delay/_should_reset_failure_count in
test_crash_retry_backoff.py.

api_bridge.py's main_process_watchdog reads this file and calls
shared.risk.tick_staleness.heartbeat_is_stale on its contents -- see
test_tick_staleness.py for that side.

Root-cause fix #2 (found live, 2026-08-14): heartbeat_writer's loop
called _write_heartbeat directly, unwrapped, on the event loop -- the
exact same anti-pattern as the 2026-08-13 get_market_data() freeze this
whole mechanism exists to catch, freshly reintroduced here. Strong
circumstantial evidence (a real ~12-hour total freeze, main.py silent
from ~00:37 to 12:34 IST, with a "Heartbeat write failed: [WinError 5]
Access is denied" logged at the exact moment main_process_watchdog's
forced termination finally broke whatever had it stuck) points at this
exact write hanging on a Windows-level file lock and freezing the whole
loop with it -- ironically, the freeze-detector froze itself. Now
wrapped in asyncio.to_thread; see
test_a_hanging_write_does_not_stall_a_concurrent_task below for the
same freeze-injection proof used for get_market_data in
test_engine_freeze_prevention.py, applied to this call site.
"""
import asyncio
import os
import time
from pathlib import Path

import pytest

import _bootstrap  # noqa: F401  (side-effect: puts trading-system/ on sys.path)

from trading_bot.main import _write_heartbeat, _HEARTBEAT_PATH, _HEARTBEAT_WRITE_INTERVAL_S


def test_write_heartbeat_creates_the_file_with_a_current_timestamp(tmp_path):
    path = tmp_path / "run" / "main_heartbeat.txt"
    before = time.time()

    _write_heartbeat(path)

    after = time.time()
    written = float(path.read_text(encoding="utf-8"))
    assert before <= written <= after


def test_write_heartbeat_creates_missing_parent_directories(tmp_path):
    path = tmp_path / "does" / "not" / "exist" / "yet" / "main_heartbeat.txt"
    assert not path.parent.exists()

    _write_heartbeat(path)

    assert path.is_file()


def test_write_heartbeat_overwrites_the_previous_value(tmp_path):
    path = tmp_path / "main_heartbeat.txt"

    _write_heartbeat(path)
    first = path.read_text(encoding="utf-8")
    time.sleep(0.01)
    _write_heartbeat(path)
    second = path.read_text(encoding="utf-8")

    assert float(second) > float(first)


def test_write_heartbeat_leaves_no_temp_file_behind(tmp_path):
    path = tmp_path / "main_heartbeat.txt"

    _write_heartbeat(path)

    leftovers = list(tmp_path.glob("heartbeat_tmp_*"))
    assert leftovers == []


def test_default_heartbeat_path_is_under_the_run_directory():
    """Same directory shared/singleton_lock.py already uses for
    process-lifecycle artifacts (run/{name}.pid, run/{name}.lock) --
    not application config, a fact about this running process."""
    assert _HEARTBEAT_PATH.parent.name == "run"
    assert _HEARTBEAT_PATH.name == "main_heartbeat.txt"


def test_write_interval_is_comfortably_under_the_staleness_threshold():
    """Sanity check on the two constants' relationship: writing every
    _HEARTBEAT_WRITE_INTERVAL_S must leave real margin under
    heartbeat_is_stale's default threshold, or normal write jitter alone
    could trigger false-positive freeze detection."""
    from shared.risk.tick_staleness import DEFAULT_HEARTBEAT_STALE_THRESHOLD_S
    assert _HEARTBEAT_WRITE_INTERVAL_S * 3 <= DEFAULT_HEARTBEAT_STALE_THRESHOLD_S


def _hanging_write(path):
    """Stands in for _write_heartbeat hanging on a real Windows-level
    file lock -- live evidence (a real ~12-hour freeze, a "Heartbeat
    write failed: [WinError 5]" logged the instant
    main_process_watchdog's forced termination finally broke whatever
    had it stuck) points at this exact call as the 2026-08-14 freeze
    mechanism."""
    time.sleep(1.5)


async def _ticking_task(ticks: list, n: int = 6, interval: float = 0.2):
    """Stands in for everything else the event loop needs to keep doing
    while a heartbeat write is in flight -- same role as
    test_engine_freeze_prevention.py's _ticking_task."""
    for _ in range(n):
        await asyncio.sleep(interval)
        ticks.append(time.monotonic())


def test_a_hanging_write_does_not_stall_a_concurrent_task():
    """The actual 2026-08-14 fix, proven the same way
    test_engine_freeze_prevention.py proves it for get_market_data(): a
    synchronous call that genuinely blocks for real wall-clock time must
    not stall a concurrent coroutine on the same event loop, once
    wrapped in asyncio.to_thread -- this is the exact pattern
    heartbeat_writer's loop now uses for _write_heartbeat."""

    async def _run():
        ticks: list = []
        start = time.monotonic()
        await asyncio.gather(
            asyncio.to_thread(_hanging_write, _HEARTBEAT_PATH),
            _ticking_task(ticks),
        )
        return ticks, start

    ticks, start = asyncio.run(_run())

    assert len(ticks) == 6
    assert ticks[-1] - start < 1.4, (
        f"ticking_task's ticks were delayed by the hanging heartbeat "
        f"write -- the event loop was stalled (last tick at "
        f"{ticks[-1] - start:.2f}s, expected ~1.2s)"
    )


# ----------------------------------------------------------------------
# Root-cause fix #3 (found live, 2026-08-26): _write_heartbeat's
# os.replace() had no retry, so every transient WinError 5 "Access is
# denied" -- api_bridge.py's main_process_watchdog reading this same file
# via Path.read_text() every 30s, exactly the race _save_positions'
# 2026-08-03 fix already documented for active_positions.json -- surfaced
# as a logged ERROR for what the design otherwise treats as a harmless
# miss (the next write is <= _HEARTBEAT_WRITE_INTERVAL_S away). Now
# retries os.replace() up to 5 times with the same short backoff
# _save_positions uses, rather than raising on the first transient
# failure.
# ----------------------------------------------------------------------

def test_write_heartbeat_retries_past_a_transient_replace_failure(tmp_path, monkeypatch):
    path = tmp_path / "main_heartbeat.txt"
    real_replace = os.replace
    calls = {"n": 0}

    def flaky_replace(src, dst):
        calls["n"] += 1
        if calls["n"] < 3:
            raise OSError(5, "Access is denied")
        return real_replace(src, dst)

    monkeypatch.setattr(os, "replace", flaky_replace)

    _write_heartbeat(path)  # must not raise

    assert calls["n"] == 3
    assert path.is_file()


def test_write_heartbeat_gives_up_after_five_persistent_replace_failures(tmp_path, monkeypatch):
    path = tmp_path / "main_heartbeat.txt"
    calls = {"n": 0}

    def always_fails(src, dst):
        calls["n"] += 1
        raise OSError(5, "Access is denied")

    monkeypatch.setattr(os, "replace", always_fails)

    with pytest.raises(OSError):
        _write_heartbeat(path)

    assert calls["n"] == 5
    assert not path.exists()
