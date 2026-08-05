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
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

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
