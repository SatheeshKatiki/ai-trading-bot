"""Prevents two instances of the same long-running process (main.py's live
engine, api_bridge.py's server) from running concurrently.

Root-cause fix (found live, 2026-08-05): neither process had any instance
guard. An accidental double-launch of main.py at 10:46 IST (and again of
api_bridge.py at 12:09 IST) went completely unnoticed for hours -- one
instance connected and traded normally while its orphaned twin sat retrying
its broker/API-bridge connection forever, invisible unless someone thought
to check `tasklist`. In paper mode the blast radius was wasted CPU and log
noise, but the identical code path with a real broker could silently
double-submit orders with zero warning.

Root-cause fix #2 (found live, 2026-08-13): the guard above was itself a
TOCTOU race -- it checked `lock_path.is_file()` / read the PID, then
*separately* called `lock_path.write_text(...)`, with no atomicity between
the two. `Start_AI_Bot.bat` got double-launched at 09:27:08-09 IST, and
both copies of main.py/api_bridge.py passed the "no live conflicting PID"
check before either had written its own PID -- all four processes started,
collided, and died. Python's own import time (pandas/fastapi/numpy) alone
is easily enough slack to hit this window on a near-simultaneous launch.
Fixed by wrapping the check-then-write critical section in a real OS-level
lock (`filelock.FileLock`, already an unused dependency) so only one
process can be inside it at a time -- the loser waits for the winner to
finish writing its PID, then correctly detects the now-live collision via
the exact same diagnostic path as before. Behavior/diagnostics for every
other scenario (stale lock, garbage PID file, reused PID) are unchanged.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import filelock
import psutil

_LOCK_DIR = Path(__file__).resolve().parents[1] / "run"


def acquire_singleton_lock(name: str, script_hint: str) -> None:
    """Exit the process immediately if another live `name` instance already
    holds this lock. `script_hint` (e.g. "main.py") is matched against the
    candidate's command line so a PID simply reused by an unrelated process
    since the lock was written isn't mistaken for a real collision.
    """
    _LOCK_DIR.mkdir(exist_ok=True)
    lock_path = _LOCK_DIR / f"{name}.pid"
    guard_path = _LOCK_DIR / f"{name}.lock"

    # This OS-level lock makes the check-then-write below atomic across
    # processes. It's held only for the duration of this function, not the
    # process's lifetime -- see the module docstring's second root-cause
    # note for why that's still sufficient to close the actual race.
    try:
        guard = filelock.FileLock(str(guard_path), timeout=10)
        with guard:
            if lock_path.is_file():
                try:
                    old_pid = int(lock_path.read_text(encoding="utf-8").strip())
                except (ValueError, OSError):
                    old_pid = None

                if old_pid is not None and old_pid != os.getpid() and psutil.pid_exists(old_pid):
                    try:
                        cmdline = " ".join(psutil.Process(old_pid).cmdline())
                    except psutil.Error:
                        cmdline = ""
                    if script_hint in cmdline:
                        print(
                            f"FATAL: another {name} instance is already running "
                            f"(PID {old_pid}: {cmdline}). Refusing to start a second "
                            f"instance -- stop it first if this is intentional, or "
                            f"delete {lock_path} if it's a stale lock from a process "
                            f"that no longer exists.",
                            file=sys.stderr,
                        )
                        sys.exit(1)

            lock_path.write_text(str(os.getpid()), encoding="utf-8")
    except filelock.Timeout:
        # Should only happen if the critical section above somehow never
        # completes (e.g. a wedged filesystem) -- 10s is enormous slack for
        # what is normally a single read+write. Fail loudly rather than
        # silently start unguarded.
        print(
            f"FATAL: timed out waiting for the {name} startup lock "
            f"({guard_path}). Refusing to start without it.",
            file=sys.stderr,
        )
        sys.exit(1)
