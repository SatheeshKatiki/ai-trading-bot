"""Regression tests for shared/singleton_lock.py.

Root-cause fix (found live, 2026-08-05): main.py and api_bridge.py had no
instance guard at all, so an accidental double-launch of either silently ran
two live copies side by side with zero warning. These tests exercise the
real acquire_singleton_lock() against a real lock file and a real second
process (this test's own interpreter, always alive) to prove it actually
blocks a collision and tolerates a stale lock.

Root-cause fix #2 (found live, 2026-08-13): the guard above was itself a
TOCTOU race -- see the module docstring in shared/singleton_lock.py.
`test_real_concurrent_launch_only_one_instance_wins` below is the actual
duplicate-start failure-injection test for that: it spawns real, separate
OS processes as close to simultaneously as this platform allows and proves
exactly one of them wins the lock, closing the gap the five tests above
never covered (they all simulate a *sequential* second call in the same
process via mocked psutil, never a genuine race).
"""
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

import _bootstrap  # noqa: F401  (side-effect: puts trading-system/ on sys.path)

import shared.singleton_lock as singleton_lock


@pytest.fixture
def lock_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(singleton_lock, "_LOCK_DIR", tmp_path)
    return tmp_path


def test_first_acquire_writes_pid_file(lock_dir):
    singleton_lock.acquire_singleton_lock("main", script_hint="main.py")
    assert (lock_dir / "main.pid").read_text(encoding="utf-8").strip() == str(os.getpid())


class _FakeProcess:
    def __init__(self, cmdline):
        self._cmdline = cmdline

    def cmdline(self):
        return self._cmdline


def test_collision_with_a_running_process_exits(lock_dir, monkeypatch):
    other_pid = os.getpid() + 1  # guaranteed different from our own PID
    (lock_dir / "main.pid").write_text(str(other_pid), encoding="utf-8")
    monkeypatch.setattr(singleton_lock.psutil, "pid_exists", lambda pid: pid == other_pid)
    monkeypatch.setattr(
        singleton_lock.psutil, "Process",
        lambda pid: _FakeProcess(["python.exe", "main.py"]) if pid == other_pid else (_ for _ in ()).throw(AssertionError),
    )
    with pytest.raises(SystemExit) as exc_info:
        singleton_lock.acquire_singleton_lock("main", script_hint="main.py")
    assert exc_info.value.code == 1


def test_stale_lock_with_dead_pid_is_ignored(lock_dir):
    # PID 4 is reserved (System Idle/System on Windows, init/kthreadd-ish on
    # Linux) — never a Python process we'd collide with, and if it somehow
    # existed, its cmdline would never contain "main.py".
    (lock_dir / "main.pid").write_text("999999", encoding="utf-8")
    singleton_lock.acquire_singleton_lock("main", script_hint="main.py")
    assert (lock_dir / "main.pid").read_text(encoding="utf-8").strip() == str(os.getpid())


def test_lock_file_with_garbage_contents_is_ignored(lock_dir):
    (lock_dir / "main.pid").write_text("not-a-pid", encoding="utf-8")
    singleton_lock.acquire_singleton_lock("main", script_hint="main.py")
    assert (lock_dir / "main.pid").read_text(encoding="utf-8").strip() == str(os.getpid())


def test_mismatched_cmdline_on_reused_pid_is_treated_as_stale(lock_dir, monkeypatch):
    # Simulates the old PID having been reused by an unrelated process since
    # the lock was written -- alive, but its cmdline doesn't mention main.py.
    other_pid = os.getpid() + 1
    (lock_dir / "main.pid").write_text(str(other_pid), encoding="utf-8")
    monkeypatch.setattr(singleton_lock.psutil, "pid_exists", lambda pid: pid == other_pid)
    monkeypatch.setattr(
        singleton_lock.psutil, "Process",
        lambda pid: _FakeProcess(["some_unrelated_process.exe"]),
    )
    singleton_lock.acquire_singleton_lock("main", script_hint="main.py")
    assert (lock_dir / "main.pid").read_text(encoding="utf-8").strip() == str(os.getpid())


# ---------------------------------------------------------------------------
# Real concurrent-process race (the actual 2026-08-13 failure mode)
# ---------------------------------------------------------------------------

_RACER_SCRIPT = """
import sys
import time
from pathlib import Path
sys.path.insert(0, {trading_system_root!r})
import shared.singleton_lock as sl
sl._LOCK_DIR = Path({lock_dir!r})

# Synchronization barrier: signal we're up and ready, then busy-wait for the
# test harness's "go" file. Import time (this script's own imports, and in
# production main.py/api_bridge.py's much heavier pandas/fastapi/numpy
# imports) is what actually created the 2026-08-13 race window -- without
# this barrier, lightweight racer processes here reach the critical section
# at scattered times and rarely land in that window together, which would
# make this test pass even against the old buggy implementation and prove
# nothing. The barrier forces every racer through the check-then-write
# sequence at as close to the same instant as this platform allows.
ready_marker = Path({lock_dir!r}) / f"ready_{{sys.argv[2]}}"
ready_marker.write_text("1", encoding="utf-8")
go_file = Path({lock_dir!r}) / "go"
while not go_file.exists():
    time.sleep(0.001)

sl.acquire_singleton_lock("racetest", sys.argv[1])
# Stay alive briefly so any still-starting sibling racer that reaches its
# own check sees this PID as genuinely live (psutil.pid_exists) rather than
# racing us for who exits first -- mirrors main.py/api_bridge.py actually
# being long-running processes, not this short-lived test script.
time.sleep(3)
"""


def test_real_concurrent_launch_only_one_instance_wins(tmp_path):
    """Spawns N real OS processes that all call acquire_singleton_lock at
    (as close to) the same instant, mirroring the 2026-08-13 incident where
    Start_AI_Bot.bat got double-launched and all four resulting processes
    passed the old check before any of them had written a PID. With the
    atomic filelock-guarded critical section, exactly one process must win
    (exit 0, and be the one whose PID ends up in the lock file) and every
    other process must lose (exit 1, the existing collision path)."""
    script_hint = "racetest_marker"
    script = _RACER_SCRIPT.format(
        trading_system_root=str(_bootstrap.TRADING_SYSTEM_ROOT),
        lock_dir=str(tmp_path),
    )
    n_racers = 8
    procs = [
        subprocess.Popen(
            [sys.executable, "-c", script, script_hint, str(i)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        for i in range(n_racers)
    ]

    # Wait for every racer to hit the barrier, then release them all at once.
    deadline = time.monotonic() + 20
    while len(list(tmp_path.glob("ready_*"))) < n_racers:
        assert time.monotonic() < deadline, "racers never reached the start barrier"
        time.sleep(0.01)
    (tmp_path / "go").write_text("1", encoding="utf-8")

    results = [p.wait() for p in procs]

    winners = [r for r in results if r == 0]
    losers = [r for r in results if r == 1]
    if len(winners) != 1:
        stderrs = [p.stderr.read().decode("utf-8", "replace") for p in procs]
        raise AssertionError(
            f"expected exactly 1 winner (exit 0) among {n_racers} racers, "
            f"got {len(winners)} (all exit codes: {results})\nstderr:\n"
            + "\n---\n".join(stderrs)
        )
    assert len(losers) == n_racers - 1
    assert (tmp_path / "racetest.pid").is_file()
