"""Regression tests for `auto_daily_session.ServiceSupervisor`.

Anchored to a real incident. From `logs/daily_orchestrator.log`, on
2026-09-07 the Paper Observer was relaunched **370 times** between 09:14
and 11:17 IST -- one restart every 20 seconds for the first two hours of
the trading session, during which zero paper trading happened.

The observer was not crashing. It was the pre-v3.13.0 3-day-capped build,
so it printed "[AUDIT COMPLETE] All 3 live trading sessions completed!"
and exited **cleanly (returncode 0)** within ~2 seconds, every time. The
old watchdog only asked ``proc.poll() is not None``, which cannot tell a
deliberate successful exit from a fault, so it fought the child's own
decision to stop until the orchestrator was killed.

`test_clean_exit_is_not_restarted` replays exactly that timeline.
"""

from __future__ import annotations

import types

import pytest

import auto_daily_session as ads


# ---------------------------------------------------------------------------
# Harness
# ---------------------------------------------------------------------------

class _Clock:
    """Monotonic stand-in so a two-hour session runs in microseconds."""

    def __init__(self, start: float = 1_000.0) -> None:
        self.now = start

    def time(self) -> float:
        return self.now

    def sleep(self, _seconds: float) -> None:  # supervisor never sleeps
        pass

    def advance(self, seconds: float) -> None:
        self.now += seconds


class _FakeProc:
    """A child that exits with `rc` after `lifetime` simulated seconds."""

    def __init__(self, rc: int, lifetime: float, born: float, clock: _Clock) -> None:
        self._rc, self._lifetime, self._born, self._clock = rc, lifetime, born, clock
        self.pid = 4242
        self.returncode = None

    def poll(self):
        if self._clock.now - self._born >= self._lifetime:
            self.returncode = self._rc
            return self._rc
        return None

    def terminate(self):
        pass

    def wait(self, timeout=None):
        pass

    def kill(self):
        pass


@pytest.fixture
def harness(monkeypatch):
    """Yield a factory for supervisors wired to a fake clock and fake children.

    Patches the module's `time` and Telegram dispatch so nothing sleeps,
    logs to disk, or hits the network.
    """
    clock = _Clock()
    alerts: list[str] = []

    monkeypatch.setattr(ads, "time", types.SimpleNamespace(time=clock.time, sleep=clock.sleep))
    monkeypatch.setattr(ads, "send_telegram_notification", lambda msg: alerts.append(msg))

    def make(rc: int, lifetime: float, restart_on_clean_exit: bool = False):
        sv = ads.ServiceSupervisor(
            "TestChild", lambda: ["noop"], "test.log",
            restart_on_clean_exit=restart_on_clean_exit,
        )
        launches = []

        def _fake_start() -> bool:
            launches.append(clock.now)
            sv.proc = _FakeProc(rc, lifetime, clock.now, clock)
            sv._started_at = clock.now
            sv.launches = len(launches)
            return True

        sv.start = _fake_start          # type: ignore[method-assign]
        sv.start()
        return sv, launches

    def tick(sv, count: int, seconds: float = 20.0) -> None:
        """Advance the orchestrator's 20-second watchdog loop `count` times."""
        for _ in range(count):
            clock.advance(seconds)
            sv.supervise()

    yield types.SimpleNamespace(make=make, tick=tick, clock=clock, alerts=alerts)


# ---------------------------------------------------------------------------
# The incident
# ---------------------------------------------------------------------------

def test_clean_exit_is_not_restarted(harness):
    """2026-09-07 replay: child exits code 0 in ~2s; watchdog ticks for 2h.

    The old behaviour was 370 launches. Restarting an identical process
    cannot change the decision the child just made, so the supervisor must
    honour a clean exit, escalate once, and stop.
    """
    sv, launches = harness.make(rc=0, lifetime=2)

    harness.tick(sv, count=370)          # 370 * 20s == the real 2h 3m window

    assert len(launches) == 1, "a clean exit must never be restarted"
    assert sv.given_up is True
    assert len(harness.alerts) == 1, "operator must be told exactly once"
    assert "exit code 0" in harness.alerts[0]


def test_clean_exit_alert_is_not_repeated(harness):
    """The give-up latch must not re-fire on every subsequent tick."""
    sv, _ = harness.make(rc=0, lifetime=2)
    harness.tick(sv, count=50)
    harness.tick(sv, count=50)
    assert len(harness.alerts) == 1


# ---------------------------------------------------------------------------
# Genuine faults
# ---------------------------------------------------------------------------

def test_crash_loop_is_capped(harness):
    """A truly broken child costs a bounded number of restarts, not 370."""
    sv, launches = harness.make(rc=1, lifetime=2)

    harness.tick(sv, count=370)

    assert len(launches) == 1 + ads._MAX_RESTARTS_PER_BURST
    assert sv.given_up is True
    assert len(harness.alerts) == 1
    assert "STOPPED restarting" in harness.alerts[0]


def test_restarts_follow_the_backoff_ladder(harness):
    """Consecutive restarts must be spaced by `_RESTART_BACKOFF_S`."""
    sv, launches = harness.make(rc=1, lifetime=1)

    harness.tick(sv, count=400, seconds=1.0)   # 1s ticks resolve the ladder

    # Gap between launches == the child's own lifetime plus the ladder delay.
    # The first restart deliberately uses ladder index 0 (no delay), so a
    # one-off blip recovers instantly and only repeat failures get paced.
    gaps = [round(b - a) - 1 for a, b in zip(launches, launches[1:])]
    assert gaps == list(ads._RESTART_BACKOFF_S[:len(gaps)])


def test_healthy_uptime_resets_the_burst(harness):
    """A crash after a long healthy run is a new incident, not a continuation.

    Otherwise a service that dies once an hour would exhaust its budget by
    lunchtime and be left down for the rest of the session.
    """
    sv, launches = harness.make(rc=1, lifetime=3_600)

    harness.tick(sv, count=400)

    assert sv.given_up is False
    assert len(launches) > 1


def test_server_clean_exit_is_still_a_fault(harness):
    """The API bridge is never "done" -- for it, code 0 is abnormal too."""
    sv, launches = harness.make(rc=0, lifetime=2, restart_on_clean_exit=True)

    harness.tick(sv, count=370)

    assert len(launches) == 1 + ads._MAX_RESTARTS_PER_BURST
    assert sv.given_up is True


def test_reset_clears_the_give_up_latch(harness):
    """--daemon mode reuses these singletons across days.

    Without `reset()` a Monday give-up would silently leave the service
    unsupervised for the rest of the week.
    """
    sv, _ = harness.make(rc=0, lifetime=2)
    harness.tick(sv, count=5)
    assert sv.given_up is True

    sv.reset()

    assert sv.given_up is False
    assert sv._restarts_in_burst == 0
    assert sv._next_restart_allowed_at == 0.0


def test_log_handle_is_released_on_stop():
    """Every restart used to leak an open file handle (372 of them on 09-07)."""
    sv = ads.ServiceSupervisor("HandleTest", lambda: ["noop"], "handle_test.log")

    sv._log_handle = open(ads.LOG_DIR / "handle_test.log", "a", encoding="utf-8")
    handle = sv._log_handle

    sv.stop()

    assert handle.closed is True
    assert sv._log_handle is None
