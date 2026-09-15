"""The shadow books must say why a poll did nothing (2026-09-15).

On 2026-09-15 both variant books recorded ``signals: []`` for the whole
session. Replaying that same session's cached bars through these very rules
found a SENSEX PE signal on the 11:15 bar, live for 13 consecutive polls
inside the freshness window. MIN_BARS, is_fresh, the timezone of ``now``,
duplicate bars and cache-write contention were each ruled out afterwards --
but the run had logged nothing, so the cause could only be guessed at.

``consider_entry`` has two silent exits -- a bar that is not fresh, and a bar
carrying no signal -- and from the session file afterwards they are
indistinguishable from "nothing happened". Every exit now records its reason.

The property that matters most is the last test here: a signal is recorded
BEFORE any skip check, so a signal that was seen but not acted on can never
again look like a signal that never existed.
"""

from __future__ import annotations

import datetime

import numpy as np
import pandas as pd
import pytest
import pytz

import ema9_variant_observer as ev
import paper_observer as po
from trading_bot.strategies.ema9_rsi_momentum.config import Ema9RsiMomentumConfig

IST = pytz.timezone("Asia/Kolkata")
DAY = datetime.date(2026, 9, 15)


@pytest.fixture(autouse=True)
def _isolate(monkeypatch, tmp_path):
    """No Telegram, no writes outside tmp, no stale-log bleed between tests."""
    monkeypatch.setattr(po, "alerter", None)
    monkeypatch.setattr(ev, "VARIANTS_DIR", tmp_path / "variants")
    ev._STALE_DATA_LOGGED.clear()
    yield
    ev._STALE_DATA_LOGGED.clear()


def _now(h, m, s=0, day=DAY):
    return IST.localize(datetime.datetime(day.year, day.month, day.day, h, m, s))


def _frame(last_bar_start: datetime.datetime, bars: int = 300, freq_min: int = 5):
    """``bars`` closed bars ending with one that STARTS at last_bar_start."""
    idx = pd.DatetimeIndex(
        sorted(last_bar_start - datetime.timedelta(minutes=freq_min * k) for k in range(bars))
    )
    rng = np.random.default_rng(3)
    close = 23_400 + np.cumsum(rng.normal(0, 3, bars))
    return pd.DataFrame(
        {"open": np.r_[close[0], close[:-1]], "high": close + 5.0,
         "low": close - 5.0, "close": close, "volume": 1e5},
        index=idx,
    )


def _sess(variant="5m_atm"):
    return {"variant": variant, "signals": [], "trades": [], "open_positions": {},
            "last_bar": {}}


def _diag(sess, symbol="NIFTY"):
    return sess["diagnostics"][symbol]


# ---------------------------------------------------------------------------
# Every exit leaves a reason
# ---------------------------------------------------------------------------

def test_empty_frame_is_recorded():
    sess = _sess()
    assert ev.consider_entry(sess, "NIFTY", Ema9RsiMomentumConfig(),
                             pd.DataFrame(), _now(11, 0)) is False
    assert _diag(sess)["outcome"] == "empty frame"
    assert _diag(sess)["frame_len"] == 0


def test_a_bar_from_another_day_is_recorded():
    """The holiday/feed-outage case: the newest bar is not today's."""
    sess = _sess()
    df = _frame(datetime.datetime(2026, 9, 11, 15, 25))
    assert ev.consider_entry(sess, "NIFTY", Ema9RsiMomentumConfig(), df, _now(9, 20)) is False
    d = _diag(sess)
    assert d["outcome"] == "bar is not from today"
    assert d["bar"].startswith("2026-09-11")


def test_a_stale_bar_is_recorded_with_its_age(monkeypatch):
    """Today's bar, but older than the freshness window -- previously silent."""
    monkeypatch.setattr(ev, "latest_closed_signal", lambda df, cfg: 0)
    sess = _sess()
    df = _frame(datetime.datetime(2026, 9, 15, 10, 0))
    # bar closes 10:05; probing at 10:25 makes it 1200s old against a 180s window
    assert ev.consider_entry(sess, "NIFTY", Ema9RsiMomentumConfig(), df, _now(10, 25)) is False
    d = _diag(sess)
    assert d["outcome"] == "bar not fresh"
    assert d["age_s"] == pytest.approx(1200.0)
    assert d["fresh_window_s"] == ev.FRESH_BAR_S


def test_a_short_frame_is_named_as_such(monkeypatch):
    """MIN_BARS suppression must not read as 'the rules saw nothing'."""
    monkeypatch.setattr(ev, "latest_closed_signal", lambda df, cfg: 0)
    sess = _sess()
    df = _frame(datetime.datetime(2026, 9, 15, 10, 0), bars=100)
    assert ev.consider_entry(sess, "NIFTY", Ema9RsiMomentumConfig(), df, _now(10, 6)) is False
    d = _diag(sess)
    assert d["outcome"] == "frame below MIN_BARS"
    assert d["frame_len"] == 100 and d["min_bars"] == ev.MIN_BARS


def test_a_fresh_bar_with_no_signal_is_recorded(monkeypatch):
    monkeypatch.setattr(ev, "latest_closed_signal", lambda df, cfg: 0)
    sess = _sess()
    df = _frame(datetime.datetime(2026, 9, 15, 10, 0))
    assert ev.consider_entry(sess, "NIFTY", Ema9RsiMomentumConfig(), df, _now(10, 6)) is False
    d = _diag(sess)
    assert d["outcome"] == "no signal"
    assert d["age_s"] == pytest.approx(60.0)
    assert d["frame_len"] >= ev.MIN_BARS


# ---------------------------------------------------------------------------
# The 2026-09-15 regression itself
# ---------------------------------------------------------------------------

def test_a_signal_is_recorded_even_when_the_trade_is_skipped(monkeypatch):
    """A seen-but-skipped signal must never look like no signal at all.

    This is the exact shape of the 2026-09-15 gap: the book reported an empty
    signal list, so there was no way to tell a signal it declined from a
    signal it never saw.
    """
    monkeypatch.setattr(ev, "latest_closed_signal", lambda df, cfg: -1)
    monkeypatch.setattr(po, "fetch_option_chain", lambda symbol: None)
    sess = _sess()
    df = _frame(datetime.datetime(2026, 9, 15, 11, 15))

    assert ev.consider_entry(sess, "SENSEX", Ema9RsiMomentumConfig(), df, _now(11, 21)) is True

    d = _diag(sess, "SENSEX")
    assert d["outcome"] == "SIGNAL"
    assert d["side"] == -1
    assert sess["signals"], "the signal must be recorded before any skip check"
    assert sess["signals"][-1]["side"] == "PE"
    assert sess["signals"][-1]["action"] == "skipped: no option chain"


def test_diagnostics_are_kept_per_index(monkeypatch):
    """One index's outcome must not overwrite another's."""
    monkeypatch.setattr(ev, "latest_closed_signal", lambda df, cfg: 0)
    sess = _sess()
    fresh = _frame(datetime.datetime(2026, 9, 15, 10, 0))
    old = _frame(datetime.datetime(2026, 9, 11, 15, 25))

    ev.consider_entry(sess, "NIFTY", Ema9RsiMomentumConfig(), fresh, _now(10, 6))
    ev.consider_entry(sess, "SENSEX", Ema9RsiMomentumConfig(), old, _now(10, 6))

    assert _diag(sess, "NIFTY")["outcome"] == "no signal"
    assert _diag(sess, "SENSEX")["outcome"] == "bar is not from today"
