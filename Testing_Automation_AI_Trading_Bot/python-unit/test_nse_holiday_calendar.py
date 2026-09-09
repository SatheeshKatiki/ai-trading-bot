"""Regression tests for the NSE holiday calendar (2026-09-09).

`auto_daily_session.py` held a single flat `NSE_HOLIDAYS_2026` set and
consulted it unconditionally. From 2027-01-01 every lookup would miss, so
`is_trading_day()` would return True on every NSE holiday and the zero-touch
orchestrator would run a full session -- auto-auth, backend, paper observer --
into a closed exchange, on every holiday, **silently**.

The calendar is now keyed by year so the gap is detectable, and
`assert_holiday_calendar_current()` makes it loud (log + Telegram, once per
year per run) instead of invisible.
"""

from __future__ import annotations

import datetime

import pytest

import auto_daily_session as ads


# ---------------------------------------------------------------------------
# Structure
# ---------------------------------------------------------------------------

def test_calendar_is_keyed_by_year():
    assert isinstance(ads.NSE_HOLIDAYS, dict)
    assert all(isinstance(y, int) for y in ads.NSE_HOLIDAYS)


def test_2026_calendar_is_present_and_complete():
    assert ads.holiday_calendar_covers(2026)
    assert len(ads.NSE_HOLIDAYS[2026]) == 17


def test_backwards_compatible_alias_still_resolves():
    assert ads.NSE_HOLIDAYS_2026 is ads.NSE_HOLIDAYS[2026]


def test_every_date_belongs_to_its_own_year():
    """A date filed under the wrong year would never match."""
    for year, dates in ads.NSE_HOLIDAYS.items():
        for d in dates:
            parsed = datetime.datetime.strptime(d, "%Y-%m-%d").date()
            assert parsed.year == year, f"{d} filed under {year}"


# ---------------------------------------------------------------------------
# is_trading_day
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("day", ["2026-01-26", "2026-08-15", "2026-11-09", "2026-12-25"])
def test_known_holidays_are_not_trading_days(day):
    d = datetime.datetime.strptime(day, "%Y-%m-%d").date()
    if d.weekday() >= 5:
        pytest.skip(f"{day} falls on a weekend anyway")
    assert ads.is_trading_day(d) is False


def test_weekends_are_never_trading_days():
    assert ads.is_trading_day(datetime.date(2026, 9, 12)) is False  # Saturday
    assert ads.is_trading_day(datetime.date(2026, 9, 13)) is False  # Sunday


def test_an_ordinary_weekday_is_a_trading_day():
    assert ads.is_trading_day(datetime.date(2026, 9, 9)) is True    # Wednesday


def test_lookup_uses_the_dates_own_year(monkeypatch):
    """The core defect: a date must be checked against ITS year's list.

    Same month/day, two different years, only one of them a holiday.
    """
    monkeypatch.setitem(ads.NSE_HOLIDAYS, 2027, {"2027-01-26"})
    assert ads.is_trading_day(datetime.date(2027, 1, 26)) is False
    # 2028 has no calendar loaded, so the same date cannot be excluded.
    assert ads.is_trading_day(datetime.date(2028, 1, 26)) is True


def test_uncovered_year_does_not_crash():
    """Must degrade to 'weekday == trading day', never raise."""
    assert ads.is_trading_day(datetime.date(2031, 3, 5)) is True


# ---------------------------------------------------------------------------
# The loud warning
# ---------------------------------------------------------------------------

def test_covered_year_reports_current_and_stays_quiet(monkeypatch):
    sent = []
    monkeypatch.setattr(ads, "send_telegram_notification", lambda m: sent.append(m))
    assert ads.assert_holiday_calendar_current(datetime.date(2026, 6, 1)) is True
    assert sent == []


def test_uncovered_year_alerts(monkeypatch):
    sent = []
    monkeypatch.setattr(ads, "send_telegram_notification", lambda m: sent.append(m))
    monkeypatch.setattr(ads, "_holiday_gap_reported", set())

    assert ads.assert_holiday_calendar_current(datetime.date(2029, 6, 1)) is False
    assert len(sent) == 1
    assert "2029" in sent[0]


def test_the_alert_fires_only_once_per_year(monkeypatch):
    """An orchestrator runs all day; this must not become a notification storm."""
    sent = []
    monkeypatch.setattr(ads, "send_telegram_notification", lambda m: sent.append(m))
    monkeypatch.setattr(ads, "_holiday_gap_reported", set())

    for _ in range(50):
        ads.assert_holiday_calendar_current(datetime.date(2030, 6, 1))

    assert len(sent) == 1
