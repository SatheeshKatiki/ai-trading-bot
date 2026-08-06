"""momentum_strategy/itm_selector.py — expiry weekday correction.

This module is currently dormant (only trading_bot/strategies/momentum_
strategy wires it up, and the live active_strategy is ema_rsi), but it
hardcoded EXPIRY_WEEKDAY=3 (Thursday) — stale since NSE consolidated weekly
NIFTY/BANKNIFTY options expiry to Tuesday. Had institutional_momentum ever
been activated, this would have built an option symbol for a non-existent
Thursday contract on every single entry. Root-caused and fixed alongside the
identical, already-corrected constant in
trading_bot/strategies/premium_selection/options_selector.py.
"""
from datetime import date

import _bootstrap  # noqa: F401  (side-effect: puts trading-system/ on sys.path)

from trading_bot.strategies.momentum_strategy.itm_selector import (
    EXPIRY_WEEKDAY,
    ITMOptionSelector,
)


def test_expiry_weekday_is_tuesday_not_thursday():
    assert EXPIRY_WEEKDAY == 1  # Monday=0 ... Tuesday=1 ... Thursday=3


def test_current_expiry_resolves_to_the_nearest_tuesday():
    # 2026-08-03 is a Monday.
    monday = date(2026, 8, 3)
    expiry = ITMOptionSelector.get_current_expiry(monday)
    assert expiry == date(2026, 8, 4)  # the next day, a Tuesday
    assert expiry.weekday() == 1


def test_on_expiry_day_itself_current_expiry_is_today():
    tuesday = date(2026, 8, 4)
    assert ITMOptionSelector.get_current_expiry(tuesday) == tuesday


def test_next_expiry_is_exactly_one_week_after_current():
    monday = date(2026, 8, 3)
    current = ITMOptionSelector.get_current_expiry(monday)
    nxt = ITMOptionSelector.get_next_expiry(monday)
    assert (nxt - current).days == 7
    assert nxt.weekday() == 1


def test_is_expiry_day_matches_tuesday_only():
    assert ITMOptionSelector.is_expiry_day(date(2026, 8, 4)) is True   # Tuesday
    assert ITMOptionSelector.is_expiry_day(date(2026, 8, 3)) is False  # Monday
    assert ITMOptionSelector.is_expiry_day(date(2026, 8, 6)) is False  # Thursday


def test_select_builds_a_symbol_dated_on_a_tuesday():
    selector = ITMOptionSelector()
    selection = selector.select(24_500.0, direction=1)
    # select() uses date.today() internally (no override param), so just
    # check the invariant that holds regardless of when the suite runs:
    # whatever expiry it picked, it must be a Tuesday.
    assert selection.expiry  # non-empty
    resolved = date.fromisoformat(selection.expiry)
    assert resolved.weekday() == 1, (
        f"select() produced expiry {selection.expiry} (weekday "
        f"{resolved.weekday()}), expected Tuesday (1)"
    )
