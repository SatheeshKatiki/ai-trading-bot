"""Regression tests for shared/risk/manager.py's IST-aware daily reset.

Root-cause fix (Low audit finding): RiskManager used `date.today()` --
the host machine's local date -- to decide when to roll over
daily_pnl/trades_today/consecutive_losses. The bot only ever trades
NSE/BSE (IST), so a host clocked to any other timezone (e.g. a UTC
cloud server) would roll the daily counters over at the wrong wall-
clock moment relative to the actual Indian trading day. Fixed by
introducing `_today_ist()` (matching the existing `_IST = pytz.timezone
("Asia/Kolkata")` pattern already used in trading_bot/portfolio_risk.py)
and using it everywhere `RiskManager` previously called `date.today()`.
"""
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import pytz

sys.path.append(str(Path(__file__).resolve().parents[1]))

from shared.risk.manager import RiskManager, _today_ist


def test_today_ist_matches_independent_utc_conversion():
    """Deterministic, timezone-independent check: IST is always UTC+5:30,
    so converting a fresh UTC timestamp by hand must agree with
    _today_ist(), regardless of what timezone the host itself is set to."""
    utc_now = datetime.now(pytz.UTC)
    expected = (utc_now + timedelta(hours=5, minutes=30)).date()
    assert _today_ist() == expected


def test_today_ist_ignores_host_local_date():
    """This dev host happens to already be clocked to IST, so a naive
    `date.today() == _today_ist()` check wouldn't catch a regression back
    to host-timezone-dependent behavior here. Patch date.today() to an
    obviously wrong value and confirm _today_ist() doesn't use it at all --
    proving it's computed from datetime.now(_IST), not the host clock's
    notion of "today"."""
    bogus_date = date(2000, 1, 1)
    with patch("shared.risk.manager.date") as mock_date:
        mock_date.today.return_value = bogus_date
        real_today = _today_ist()
    assert real_today != bogus_date
    assert real_today == _today_ist()


def test_risk_manager_init_uses_ist_date():
    rm = RiskManager(initial_capital=100_000.0)
    assert rm.today == _today_ist()


def test_reset_daily_if_needed_uses_ist_not_stale_date():
    rm = RiskManager(initial_capital=100_000.0)
    rm.daily_pnl = -5000.0
    rm.consecutive_losses = 3
    rm.trades_today = [object()]  # type: ignore[list-item]

    # Simulate "yesterday" by backdating the tracked date -- the reset
    # should fire and use today's real IST date, not a host-local one.
    rm.today = _today_ist() - timedelta(days=1)
    rm._reset_daily_if_needed()

    assert rm.today == _today_ist()
    assert rm.daily_pnl == 0.0
    assert rm.consecutive_losses == 0
    assert rm.trades_today == []


if __name__ == "__main__":
    test_today_ist_matches_independent_utc_conversion()
    test_risk_manager_init_uses_ist_date()
    test_reset_daily_if_needed_uses_ist_not_stale_date()
    print("All IST daily-reset tests passed.")
