"""The UI's timeframe must reach every rule (2026-09-22).

The user picks a chart timeframe -- 1m, 3m, 5m, 15m, 30m, 1h, 1w -- and the
whole system is supposed to follow it. It did not:

  * `trading_bot/main.py` read settings["timeframe"] and fetched at that size.
  * `paper_observer.py` hardcoded "5 Min" in two places, so a user on the
    15-minute chart was scanned on 5-minute bars.
  * `Ema9RsiMomentumConfig.timeframe_minutes` sat at its default of 5 no
    matter what was selected -- nothing mapped "timeframe" onto it.
  * The entry-timing gate therefore counted down to a 5-minute bar close on
    every chart, and its arithmetic broke outright above an hour.

`shared.timeframes` is now the single place that knows what a timeframe
string means, and bars are anchored from midnight because that is what
`pandas.resample` -- and so `shared.closed_bars.resample_closed` -- does.
"""

from __future__ import annotations

import datetime
import pathlib

import pytest

import _bootstrap  # noqa: F401  (side-effect: puts trading-system/ on sys.path)

from shared.timeframes import (
    MINUTES_PER_DAY,
    MINUTES_PER_WEEK,
    is_intraday,
    parse_timeframe,
    seconds_to_bar_close,
    settings_timeframe,
    timeframe_label,
)
from trading_bot.strategies.ema9_rsi_momentum.config import Ema9RsiMomentumConfig
from trading_bot.strategies.ema9_rsi_momentum.signal_engine import entry_timing_gate


# ---------------------------------------------------------------------------
# Parsing every spelling the UI and settings files use
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("raw,minutes", [
    ("1 Min", 1), ("3 Min", 3), ("5 Min", 5), ("15 Min", 15), ("30 Min", 30),
    ("1 Hour", 60), ("2 Hour", 120),
    ("1 Day", MINUTES_PER_DAY), ("1 Week", MINUTES_PER_WEEK),
    ("1 Month", 30 * MINUTES_PER_DAY),
])
def test_the_uis_own_labels_parse(raw, minutes):
    assert parse_timeframe(raw) == minutes


@pytest.mark.parametrize("raw,minutes", [
    ("5min", 5), ("5m", 5), ("5", 5), (5, 5), ("  15  MIN  ", 15),
    ("1h", 60), ("1H", 60), ("1d", MINUTES_PER_DAY), ("1w", MINUTES_PER_WEEK),
    ("1mo", 30 * MINUTES_PER_DAY),
])
def test_the_shorthands_parse_too(raw, minutes):
    assert parse_timeframe(raw) == minutes


@pytest.mark.parametrize("raw", [None, "", "abc", "0 Min", "-5", "Min", True, False])
def test_an_unreadable_timeframe_falls_back_rather_than_raising(raw):
    """A malformed setting must not stop a book trading."""
    assert parse_timeframe(raw, default=5) == 5


def test_the_label_round_trips():
    for minutes in (1, 3, 5, 15, 30, 60, MINUTES_PER_DAY, MINUTES_PER_WEEK):
        assert parse_timeframe(timeframe_label(minutes)) == minutes


def test_settings_timeframe_reads_the_uis_key():
    assert settings_timeframe({"timeframe": "15 Min"}) == 15
    assert settings_timeframe({}) == 5
    assert settings_timeframe(None) == 5


@pytest.mark.parametrize("minutes,expected", [
    (1, True), (5, True), (60, True), (MINUTES_PER_DAY, False), (MINUTES_PER_WEEK, False),
])
def test_is_intraday(minutes, expected):
    assert is_intraday(minutes) is expected


# ---------------------------------------------------------------------------
# Bar-close arithmetic, on every size
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("hhmmss,minutes,expected", [
    # 5-minute bars: 09:15, 09:20, ...
    ("09:34:50", 5, 10.0),
    ("09:15:00", 5, 300.0),
    # 1-minute
    ("09:34:50", 1, 10.0),
    # 3-minute: 09:15 is on a boundary (15 % 3 == 0)
    ("09:15:00", 3, 180.0),
    # 15-minute: 09:15, 09:30, ...
    ("09:29:55", 15, 5.0),
    ("09:15:00", 15, 900.0),
    # 30-minute bars run 09:00-09:30, NOT 09:15-09:45 -- pandas anchors at
    # midnight, and resample_closed builds the candles that way.
    ("09:15:00", 30, 900.0),
    ("09:29:50", 30, 10.0),
    # hourly: 09:00-10:00
    ("09:15:00", 60, 2700.0),
    ("09:59:55", 60, 5.0),
])
def test_seconds_to_bar_close_on_each_intraday_size(hhmmss, minutes, expected):
    now = datetime.datetime.strptime("2026-09-22 " + hhmmss, "%Y-%m-%d %H:%M:%S")
    assert seconds_to_bar_close(now, minutes) == pytest.approx(expected)


@pytest.mark.parametrize("minutes", [MINUTES_PER_DAY, MINUTES_PER_WEEK, 30 * MINUTES_PER_DAY])
def test_daily_and_above_have_no_intraday_close(minutes):
    now = datetime.datetime(2026, 9, 22, 11, 0, 0)
    assert seconds_to_bar_close(now, minutes) is None


def test_a_zero_or_negative_bar_size_is_a_programming_error():
    now = datetime.datetime(2026, 9, 22, 11, 0, 0)
    with pytest.raises(ValueError):
        seconds_to_bar_close(now, 0)


# ---------------------------------------------------------------------------
# The entry gate follows the selected timeframe
# ---------------------------------------------------------------------------

def test_the_gate_counts_down_to_the_selected_bar_not_a_five_minute_one():
    """09:34:55 sits 5s from a 5-minute close but 605s from a 15-minute one.

    (The reverse case cannot exist: 15 is a multiple of 5, so every 15-minute
    close is also a 5-minute close.)
    """
    now = datetime.datetime(2026, 9, 22, 9, 34, 55)
    on5 = Ema9RsiMomentumConfig(timeframe_minutes=5)
    on15 = Ema9RsiMomentumConfig(timeframe_minutes=15)
    assert entry_timing_gate(now, "NONE", on5)[0], "5-minute bar is about to close"
    assert not entry_timing_gate(now, "NONE", on15)[0], "15-minute bar has 10 more minutes"


def test_the_reason_names_the_timeframe():
    now = datetime.datetime(2026, 9, 22, 9, 20, 0)
    _, why = entry_timing_gate(now, "NONE", Ema9RsiMomentumConfig(timeframe_minutes=15))
    assert "15 Min" in why


@pytest.mark.parametrize("minutes", [1, 3, 5, 15, 30, 60])
def test_every_intraday_size_still_has_a_confirmation_window(minutes):
    """One second before the close, any signal may enter, whatever the size."""
    cfg = Ema9RsiMomentumConfig(timeframe_minutes=minutes)
    base = datetime.datetime(2026, 9, 22, 10, 0, 0)
    close = base + datetime.timedelta(seconds=seconds_to_bar_close(base, minutes))
    ok, why = entry_timing_gate(close - datetime.timedelta(seconds=1), "NONE", cfg)
    assert ok and "confirmation window" in why


def test_a_weekly_chart_does_not_make_every_entry_wait_forever():
    """A weekly bar closes days away -- blocking on it would block all trading."""
    now = datetime.datetime(2026, 9, 22, 11, 0, 0)
    cfg = Ema9RsiMomentumConfig(timeframe_minutes=MINUTES_PER_WEEK)
    ok, why = entry_timing_gate(now, "NONE", cfg)
    assert ok
    assert "no intraday close" in why


# ---------------------------------------------------------------------------
# The selection actually reaches the strategy config
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("label,minutes", [
    ("1 Min", 1), ("3 Min", 3), ("5 Min", 5), ("15 Min", 15),
    ("30 Min", 30), ("1 Hour", 60), ("1 Week", MINUTES_PER_WEEK),
])
def test_the_config_takes_the_timeframe_the_user_selected(label, minutes):
    cfg = Ema9RsiMomentumConfig.from_settings({"timeframe": label})
    assert cfg.timeframe_minutes == minutes


def test_an_explicit_strategy_override_still_wins():
    """The variant shadow book pins 5 and 15 side by side regardless of the UI."""
    cfg = Ema9RsiMomentumConfig.from_settings(
        {"timeframe": "1 Hour", "ema9_rsi_timeframe_minutes": 15})
    assert cfg.timeframe_minutes == 15


def test_no_timeframe_in_settings_keeps_the_default():
    assert Ema9RsiMomentumConfig.from_settings({}).timeframe_minutes == 5


# ---------------------------------------------------------------------------
# No consumer may quietly go back to hardcoding one size
# ---------------------------------------------------------------------------

def _src(*parts) -> str:
    return pathlib.Path(_bootstrap.TRADING_SYSTEM_ROOT, *parts).read_text(
        encoding="utf-8", errors="ignore")


def test_the_paper_book_no_longer_hardcodes_five_minutes():
    src = _src("paper_observer.py")
    assert 'fetch_candles(symbol, "5 Min"' not in src
    assert "active_timeframe_minutes()" in src
    assert "settings_timeframe" in src


def test_the_paper_book_rereads_the_setting_while_running():
    """Changing the timeframe in Settings must not need a restart."""
    src = _src("paper_observer.py")
    start = src.index("def active_timeframe_minutes")
    body = src[start:start + 1200]
    assert "st_mtime" in body, "cached on the file's mtime, not captured at import"


def test_the_live_engine_reads_the_setting_too():
    src = _src("trading_bot", "main.py")
    assert '_init_settings.get("timeframe"' in src


def test_the_markers_endpoint_uses_the_charts_timeframe():
    src = _src("api_bridge.py")
    start = src.index('@app.get("/api/strategy-markers")')
    body = src[start:start + 4500]
    assert "parse_timeframe(timeframe" in body


def test_the_variant_book_still_pins_its_own_sizes():
    """5m ATM vs 15m ITM is the whole point of that book -- it must not follow the UI."""
    src = _src("ema9_variant_observer.py")
    assert '"timeframe_minutes": 5' in src
    assert '"timeframe_minutes": 15' in src
