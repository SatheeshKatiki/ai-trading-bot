"""Regression tests for the live engine's crash-retry backoff
(trading_bot/main.py's _compute_retry_delay / _should_reset_failure_count).

Root-cause fix (Medium audit finding): the container restart policy
(docker-compose.yml) stacks on top of the engine's own internal
auto-restart loop with no shared backoff/cooldown -- a flat 10s retry
delay regardless of how many times the process had just crashed in a
row could produce a tight restart-storm. These two pure functions
(pulled out of the `if __name__ == "__main__":` block specifically so
they're testable without running the actual live engine) compute an
escalating backoff and decide when to reset it.
"""
import sys
from pathlib import Path

import _bootstrap  # noqa: F401  (side-effect: puts trading-system/ on sys.path)

from trading_bot.main import (
    _compute_retry_delay,
    _should_reset_failure_count,
    _RETRY_BASE_DELAY_S,
    _RETRY_MAX_DELAY_S,
    _RETRY_SUSTAINED_UPTIME_RESET_S,
)


def test_zero_failures_uses_base_delay():
    assert _compute_retry_delay(0) == _RETRY_BASE_DELAY_S


def test_delay_doubles_on_consecutive_fast_failures():
    delays = [_compute_retry_delay(n) for n in range(1, 6)]
    assert delays == [10, 20, 40, 80, 160]


def test_delay_caps_at_max():
    assert _compute_retry_delay(10) == _RETRY_MAX_DELAY_S
    assert _compute_retry_delay(100) == _RETRY_MAX_DELAY_S


def test_reset_threshold_is_inclusive():
    assert _should_reset_failure_count(_RETRY_SUSTAINED_UPTIME_RESET_S) is True
    assert _should_reset_failure_count(_RETRY_SUSTAINED_UPTIME_RESET_S - 1) is False
    assert _should_reset_failure_count(_RETRY_SUSTAINED_UPTIME_RESET_S + 1) is True


def test_reset_then_fresh_failure_uses_base_delay():
    """Simulates the actual loop's logic: a crash after a sustained run
    resets the counter, then increments -- the very next delay should be
    the base delay, not a leftover escalated one."""
    consecutive_fast_failures = 7  # pretend several fast failures already happened
    run_duration = _RETRY_SUSTAINED_UPTIME_RESET_S + 60  # ran fine for a while since
    if _should_reset_failure_count(run_duration):
        consecutive_fast_failures = 0
    consecutive_fast_failures += 1
    assert _compute_retry_delay(consecutive_fast_failures) == _RETRY_BASE_DELAY_S


if __name__ == "__main__":
    test_zero_failures_uses_base_delay()
    test_delay_doubles_on_consecutive_fast_failures()
    test_delay_caps_at_max()
    test_reset_threshold_is_inclusive()
    test_reset_then_fresh_failure_uses_base_delay()
    print("All crash-retry backoff tests passed.")
