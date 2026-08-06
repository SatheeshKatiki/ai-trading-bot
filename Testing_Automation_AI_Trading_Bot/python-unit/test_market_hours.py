"""shared/market_hours.py — gates NEW entries to real NSE trading hours.

Root cause: nothing previously stopped a new entry from executing outside
real trading hours. Found live 2026-08-06: a NIFTY position opened at 02:50
IST off a stale post-restart snapshot, then sat unmonitored for 7h49m (see
test_tick_staleness.py and docs/paper_trading_validation/anomaly_log.md).
A real broker enforces this structurally; paper mode did not.

Mirrors frontend/lib/ist-time.ts's isMarketOpenIST() definition exactly
(weekday + 09:15-15:30 IST, no holiday calendar) — these tests pin that
same window on the Python side.
"""
from datetime import datetime

import _bootstrap  # noqa: F401  (side-effect: puts trading-system/ on sys.path)

import pytest

from shared.market_hours import IST, MARKET_CLOSE_TIME, MARKET_OPEN_TIME, is_market_open


def _ist(year, month, day, hour, minute):
    return IST.localize(datetime(year, month, day, hour, minute))


# 2026-08-06 is a Thursday; 2026-08-08/09 are Sat/Sun.
_A_WEEKDAY = (2026, 8, 6)
_A_SATURDAY = (2026, 8, 8)
_A_SUNDAY = (2026, 8, 9)


def test_the_incident_timestamp_is_correctly_reported_as_closed():
    """The exact live incident this module exists to prevent: 02:50 IST is
    hours before market open."""
    assert is_market_open(_ist(*_A_WEEKDAY, 2, 50)) is False


@pytest.mark.parametrize("hour,minute", [(9, 15), (10, 0), (12, 30), (15, 0), (15, 29)])
def test_open_during_trading_hours(hour, minute):
    assert is_market_open(_ist(*_A_WEEKDAY, hour, minute)) is True


@pytest.mark.parametrize("hour,minute", [(0, 0), (9, 14), (15, 30), (15, 31), (18, 0), (23, 59)])
def test_closed_outside_trading_hours(hour, minute):
    assert is_market_open(_ist(*_A_WEEKDAY, hour, minute)) is False


def test_open_boundary_is_inclusive():
    assert is_market_open(_ist(*_A_WEEKDAY, *divmod(MARKET_OPEN_TIME.hour * 60 + MARKET_OPEN_TIME.minute, 60))) is True


def test_close_boundary_is_exclusive():
    hour, minute = MARKET_CLOSE_TIME.hour, MARKET_CLOSE_TIME.minute
    assert is_market_open(_ist(*_A_WEEKDAY, hour, minute)) is False


def test_saturday_is_always_closed():
    assert is_market_open(_ist(*_A_SATURDAY, 12, 0)) is False


def test_sunday_is_always_closed():
    assert is_market_open(_ist(*_A_SUNDAY, 12, 0)) is False


def test_a_naive_datetime_is_treated_as_ist_wall_clock_time():
    """Matches the rest of the codebase's convention (e.g. record_trade's
    timestamps) — a naive datetime is not silently treated as UTC."""
    naive_during_hours = datetime(2026, 8, 6, 10, 0)
    naive_outside_hours = datetime(2026, 8, 6, 2, 50)

    assert is_market_open(naive_during_hours) is True
    assert is_market_open(naive_outside_hours) is False


def test_a_non_ist_timezone_is_converted_correctly():
    import pytz

    utc = pytz.UTC
    # 05:00 UTC = 10:30 IST — during market hours.
    during = utc.localize(datetime(2026, 8, 6, 5, 0))
    # 21:00 UTC = 02:30 IST (next day) — outside market hours.
    outside = utc.localize(datetime(2026, 8, 6, 21, 0))

    assert is_market_open(during) is True
    assert is_market_open(outside) is False


def test_default_now_uses_the_real_clock():
    """Sanity check the no-argument path actually calls through to a real
    clock rather than raising or always returning a fixed value."""
    result = is_market_open()
    assert isinstance(result, bool)


# ---------------------------------------------------------------------------
# market_hours_override
# ---------------------------------------------------------------------------

def test_override_true_forces_open_even_at_night():
    assert is_market_open(_ist(*_A_WEEKDAY, 2, 50), {"market_hours_override": True}) is True


def test_override_false_forces_closed_even_during_hours():
    assert is_market_open(_ist(*_A_WEEKDAY, 10, 0), {"market_hours_override": False}) is False


def test_override_absent_falls_through_to_the_real_check():
    assert is_market_open(_ist(*_A_WEEKDAY, 10, 0), {}) is True
    assert is_market_open(_ist(*_A_WEEKDAY, 10, 0), None) is True


def test_override_none_explicitly_also_falls_through():
    """Distinguish 'key present but None' from 'key absent' — both mean
    'no override', not 'override to falsy'."""
    assert is_market_open(_ist(*_A_WEEKDAY, 10, 0), {"market_hours_override": None}) is True
