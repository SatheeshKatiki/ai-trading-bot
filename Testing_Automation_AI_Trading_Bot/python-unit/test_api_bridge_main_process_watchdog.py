"""api_bridge.py -- main.py freeze detection + safe auto-recovery
(main_process_watchdog / _check_and_recover_main_process /
_should_attempt_main_restart).

Root cause (found live, 2026-08-13): main.py went completely unresponsive
for ~39 minutes (all threads, not just the tick-consuming path) with
nothing in the system able to detect it in real time; only a manual
after-the-fact log review found it. main.py now writes an independent
heartbeat (see test_main_heartbeat.py / test_tick_staleness.py's
heartbeat_is_stale coverage); this module's watchdog polls it and, on a
confirmed freeze, alerts and safely restarts main.py.

Policy under test (explicitly confirmed, 2026-08-13): auto-restart
immediately on a confirmed freeze, whether or not a position is open,
always alerting either way.

These tests exercise the REAL _check_and_recover_main_process (not a
reimplementation) with psutil/subprocess/alerter/market-hours stubbed
out and all paths pointed at tmp_path -- no real process is ever
terminated or spawned, and no real Discord webhook is ever called.
"""
import time
from types import SimpleNamespace

import pytest

import _bootstrap  # noqa: F401  (side-effect: puts trading-system/ on sys.path)

import api_bridge
from api_bridge import _should_attempt_main_restart


# ---------------------------------------------------------------------------
# _should_attempt_main_restart -- pure decision logic
# ---------------------------------------------------------------------------

def test_pid_not_alive_never_attempts_restart():
    assert _should_attempt_main_restart(
        pid_alive=False, heartbeat_stale=True, now=1_000.0,
        last_restart_attempt_at=0.0, consecutive_restart_failures=0,
    ) is False


def test_fresh_heartbeat_never_attempts_restart():
    assert _should_attempt_main_restart(
        pid_alive=True, heartbeat_stale=False, now=1_000.0,
        last_restart_attempt_at=0.0, consecutive_restart_failures=0,
    ) is False


def test_first_ever_freeze_attempts_restart_immediately():
    assert _should_attempt_main_restart(
        pid_alive=True, heartbeat_stale=True, now=1_000.0,
        last_restart_attempt_at=0.0, consecutive_restart_failures=0,
    ) is True


def test_backoff_prevents_a_restart_loop_right_after_a_failed_attempt():
    """The core anti-storm guarantee: immediately after one failed
    restart attempt, a second check moments later must NOT try again."""
    assert _should_attempt_main_restart(
        pid_alive=True, heartbeat_stale=True, now=1_005.0,
        last_restart_attempt_at=1_000.0, consecutive_restart_failures=1,
    ) is False


def test_backoff_eventually_allows_a_retry_once_the_cooldown_elapses():
    from trading_bot.main import _compute_retry_delay
    cooldown = _compute_retry_delay(1)
    assert _should_attempt_main_restart(
        pid_alive=True, heartbeat_stale=True, now=1_000.0 + cooldown,
        last_restart_attempt_at=1_000.0, consecutive_restart_failures=1,
    ) is True


# ---------------------------------------------------------------------------
# _check_and_recover_main_process -- end-to-end per-check behavior
# ---------------------------------------------------------------------------

class _FakeProcess:
    """Stands in for psutil.Process -- records terminate()/wait() calls,
    no real OS process involved."""

    def __init__(self, pid):
        self.pid = pid
        self.terminated = False
        self.waited_timeouts = []

    def terminate(self):
        self.terminated = True

    def wait(self, timeout=None):
        self.waited_timeouts.append(timeout)
        return 0


@pytest.fixture
def watchdog_env(tmp_path, monkeypatch):
    """Redirects every path/global the watchdog touches into tmp_path,
    resets its module-level backoff state, and stubs market-hours so
    every test runs "during market hours" unless it overrides it."""
    monkeypatch.setattr(api_bridge, "_MAIN_PID_PATH", tmp_path / "main.pid")
    monkeypatch.setattr(api_bridge, "_MAIN_HEARTBEAT_PATH", tmp_path / "main_heartbeat.txt")
    monkeypatch.setattr(api_bridge, "_MAIN_POSITIONS_PATH", tmp_path / "active_positions.json")
    monkeypatch.setattr(api_bridge, "_last_main_restart_attempt_at", 0.0)
    monkeypatch.setattr(api_bridge, "_main_consecutive_restart_failures", 0)
    # Fast polling so a "successful recovery" test doesn't take ~90s.
    monkeypatch.setattr(api_bridge, "_MAIN_RESTART_HEARTBEAT_POLL_INTERVAL_S", 0.01)
    monkeypatch.setattr(api_bridge, "_MAIN_RESTART_HEARTBEAT_POLL_ATTEMPTS", 3)
    monkeypatch.setattr("shared.market_hours.is_market_open", lambda: True)
    alerts_sent = []
    monkeypatch.setattr("shared.alerts.alerter.send_alert", lambda msg: alerts_sent.append(msg))
    return SimpleNamespace(tmp_path=tmp_path, alerts_sent=alerts_sent)


async def _run(coro):
    return await coro


def test_a_fresh_heartbeat_takes_no_action(watchdog_env, monkeypatch):
    import asyncio
    watchdog_env.tmp_path.joinpath("main.pid").write_text("12345", encoding="utf-8")
    watchdog_env.tmp_path.joinpath("main_heartbeat.txt").write_text(str(time.time()), encoding="utf-8")
    monkeypatch.setattr("psutil.pid_exists", lambda pid: True)

    terminate_called = []
    monkeypatch.setattr("psutil.Process", lambda pid: terminate_called.append(pid) or _FakeProcess(pid))

    asyncio.run(_run(api_bridge._check_and_recover_main_process()))

    assert watchdog_env.alerts_sent == []
    assert terminate_called == []


def test_no_pid_file_yet_takes_no_action(watchdog_env):
    import asyncio
    # main.pid deliberately not written -- simulates "before first boot".
    asyncio.run(_run(api_bridge._check_and_recover_main_process()))
    assert watchdog_env.alerts_sent == []


def test_pid_file_present_but_process_actually_dead_takes_no_action(watchdog_env, monkeypatch):
    """A crash, not a freeze -- out of this watchdog's scope (see its
    docstring); must not be misdiagnosed as a freeze and "restarted"."""
    import asyncio
    watchdog_env.tmp_path.joinpath("main.pid").write_text("12345", encoding="utf-8")
    stale_time = time.time() - 10_000
    watchdog_env.tmp_path.joinpath("main_heartbeat.txt").write_text(str(stale_time), encoding="utf-8")
    monkeypatch.setattr("psutil.pid_exists", lambda pid: False)

    asyncio.run(_run(api_bridge._check_and_recover_main_process()))

    assert watchdog_env.alerts_sent == []


def test_stale_heartbeat_with_a_live_pid_alerts_terminates_and_respawns(watchdog_env, monkeypatch):
    """The actual freeze-recovery path, end to end: alert fires first,
    the frozen process is terminated, a new one is spawned, and a
    success alert fires once the new process's own heartbeat appears."""
    import asyncio
    pid_path = watchdog_env.tmp_path / "main.pid"
    hb_path = watchdog_env.tmp_path / "main_heartbeat.txt"
    pid_path.write_text("12345", encoding="utf-8")
    hb_path.write_text(str(time.time() - 10_000), encoding="utf-8")  # way stale

    monkeypatch.setattr("psutil.pid_exists", lambda pid: True)
    fake_procs = []
    monkeypatch.setattr("psutil.Process", lambda pid: fake_procs.append(_FakeProcess(pid)) or fake_procs[-1])

    respawned = []

    def _fake_popen(args, **kwargs):
        respawned.append(args)
        # Simulate the new process successfully starting and heartbeating.
        hb_path.write_text(str(time.time() + 1), encoding="utf-8")
        return SimpleNamespace(pid=99999)

    monkeypatch.setattr("subprocess.Popen", _fake_popen)

    asyncio.run(_run(api_bridge._check_and_recover_main_process()))

    assert len(fake_procs) == 1 and fake_procs[0].terminated is True
    assert len(respawned) == 1 and respawned[0] == [api_bridge.sys.executable, "trading_bot/main.py"]
    assert any("frozen" in a.lower() for a in watchdog_env.alerts_sent)
    assert any("succeeded" in a.lower() for a in watchdog_env.alerts_sent)
    assert api_bridge._main_consecutive_restart_failures == 0


def test_a_failed_respawn_that_never_heartbeats_is_reported_not_silently_dropped(watchdog_env, monkeypatch):
    """The new process is "spawned" but never writes a heartbeat within
    the grace window -- must alert distinctly, not claim success."""
    import asyncio
    pid_path = watchdog_env.tmp_path / "main.pid"
    hb_path = watchdog_env.tmp_path / "main_heartbeat.txt"
    pid_path.write_text("12345", encoding="utf-8")
    hb_path.write_text(str(time.time() - 10_000), encoding="utf-8")

    monkeypatch.setattr("psutil.pid_exists", lambda pid: True)
    monkeypatch.setattr("psutil.Process", lambda pid: _FakeProcess(pid))
    monkeypatch.setattr("subprocess.Popen", lambda args, **kwargs: SimpleNamespace(pid=99999))

    asyncio.run(_run(api_bridge._check_and_recover_main_process()))

    assert any("did not come up healthy" in a for a in watchdog_env.alerts_sent)
    assert api_bridge._main_consecutive_restart_failures == 1


def test_second_check_right_after_a_failed_restart_does_not_retry_immediately(watchdog_env, monkeypatch):
    """End-to-end proof of the anti-storm guarantee via the real
    function, not just the pure decision helper: after one failed
    restart attempt, calling _check_and_recover_main_process again
    moments later must not attempt a second one."""
    import asyncio
    pid_path = watchdog_env.tmp_path / "main.pid"
    hb_path = watchdog_env.tmp_path / "main_heartbeat.txt"
    pid_path.write_text("12345", encoding="utf-8")
    hb_path.write_text(str(time.time() - 10_000), encoding="utf-8")

    monkeypatch.setattr("psutil.pid_exists", lambda pid: True)
    monkeypatch.setattr("psutil.Process", lambda pid: _FakeProcess(pid))
    respawn_count = []
    monkeypatch.setattr(
        "subprocess.Popen",
        lambda args, **kwargs: respawn_count.append(1) or SimpleNamespace(pid=99999),
    )

    asyncio.run(_run(api_bridge._check_and_recover_main_process()))
    assert len(respawn_count) == 1  # first attempt, failed (no heartbeat written)

    # Still stale, still alive -- but the backoff cooldown just started.
    asyncio.run(_run(api_bridge._check_and_recover_main_process()))
    assert len(respawn_count) == 1, "must not have attempted a second restart within the backoff cooldown"


def test_outside_market_hours_takes_no_action(watchdog_env, monkeypatch):
    import asyncio
    monkeypatch.setattr("shared.market_hours.is_market_open", lambda: False)
    watchdog_env.tmp_path.joinpath("main.pid").write_text("12345", encoding="utf-8")
    watchdog_env.tmp_path.joinpath("main_heartbeat.txt").write_text(str(time.time() - 10_000), encoding="utf-8")
    monkeypatch.setattr("psutil.pid_exists", lambda pid: True)

    asyncio.run(_run(api_bridge._check_and_recover_main_process()))

    assert watchdog_env.alerts_sent == []
