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
"""
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
