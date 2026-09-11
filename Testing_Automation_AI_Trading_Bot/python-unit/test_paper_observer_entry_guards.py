"""The main paper book's entry guards, and closed-candle hygiene (2026-09-11).

Three defects in paper_observer, all measured on the recorded sessions:

1. **A standing bias was bought at startup.** The "new trigger" test compared
   each poll with the previous one -- but at startup there was no previous
   one, so ANY standing bias >= 65 counted as new. 6 of the first 20 paper
   trades were entered at 09:15:1x, on the very first poll, before a single
   5-minute candle had closed. On 2026-09-11 it bought NIFTY and BANKNIFTY PE
   at 09:15:15; both stopped out.

2. **The strategy's trading window was ignored.** ema9_rsi_momentum excludes
   09:15-09:25 and after 15:00; the observer only checked the 15:15 cutoff.
   7 of 20 trades were entered before 09:25, and those 7 account for
   -Rs 4,017 of the -Rs 5,983 recorded.

3. **The reversal exit read the still-forming candle.** /api/history returns
   the open bar last, and ``evaluate_protective_exit`` reads the frame's last
   bar, so a cross that appeared mid-bar and was gone by its close could exit
   the position.
"""

from __future__ import annotations

import datetime
import types

import pandas as pd
import pytest
import pytz

import paper_observer as po
from shared.closed_bars import candles_to_frame, closed_candles

IST = pytz.timezone("Asia/Kolkata")


def _ist(h, m, s=0):
    return IST.localize(datetime.datetime(2026, 9, 11, h, m, s))


def _c(ts, close=100.0):
    return {"datetime": ts, "open": close, "high": close + 1, "low": close - 1,
            "close": close, "volume": 0}


BARS_5M = [_c("2026-09-11 10:20:00"), _c("2026-09-11 10:25:00"), _c("2026-09-11 10:30:00")]


# ---------------------------------------------------------------------------
# Closed bars
# ---------------------------------------------------------------------------

def test_forming_bar_is_dropped():
    kept = closed_candles(BARS_5M, 5, datetime.datetime(2026, 9, 11, 10, 30, 5))
    assert [c["datetime"] for c in kept] == ["2026-09-11 10:20:00", "2026-09-11 10:25:00"]


def test_bar_is_closed_exactly_at_its_end():
    assert len(closed_candles(BARS_5M, 5, datetime.datetime(2026, 9, 11, 10, 35, 0))) == 3


def test_aware_now_is_converted_to_ist():
    utc = pytz.utc.localize(datetime.datetime(2026, 9, 11, 5, 0, 5))     # 10:30:05 IST
    assert len(closed_candles(BARS_5M, 5, utc)) == 2
    assert len(closed_candles(BARS_5M, 5, _ist(10, 30, 5))) == 2


def test_fifteen_minute_bars():
    bars = [_c("2026-09-11 10:00:00"), _c("2026-09-11 10:15:00"), _c("2026-09-11 10:30:00")]
    assert len(closed_candles(bars, 15, datetime.datetime(2026, 9, 11, 10, 31))) == 2


def test_unreadable_timestamp_cannot_be_proven_closed():
    assert closed_candles([{"datetime": "not a time", "close": 1}], 5,
                          datetime.datetime(2030, 1, 1)) == []


def test_zero_timeframe_is_rejected():
    with pytest.raises(ValueError):
        closed_candles(BARS_5M, 0, datetime.datetime(2026, 9, 11, 11, 0))


def test_frame_has_a_datetime_index_so_the_time_filter_works():
    df = candles_to_frame(BARS_5M + [_c("2026-09-11 10:25:00", close=105.0)])
    assert isinstance(df.index, pd.DatetimeIndex)
    assert len(df) == 3 and df.loc["2026-09-11 10:25:00", "close"] == 105.0   # dedup keeps last
    assert df.index.is_monotonic_increasing


# ---------------------------------------------------------------------------
# Startup entry + trading window
# ---------------------------------------------------------------------------

PLACEHOLDER = {"symbol": "NIFTY", "strategy": "ema9_rsi_momentum",
               "confidence": 50, "direction": "CALCULATING"}


def test_placeholder_is_not_an_observation():
    assert po.signal_observation(None) is None
    assert po.signal_observation(PLACEHOLDER) is None
    assert po.signal_observation({"bias": "BEARISH BIAS", "confidence": 85}) == \
        {"bias": "BEARISH BIAS", "confidence": 85}


def _replay(responses):
    """The observer loop's trigger logic, poll by poll."""
    prev, triggers = None, []
    for res in responses:
        obs = po.signal_observation(res)
        triggers.append(po.is_new_entry_trigger(prev, obs))
        if obs is not None:
            prev = obs
    return triggers


def test_a_standing_bias_at_startup_is_not_bought():
    """2026-09-11 09:15:15: BEARISH 85% was already standing when the
    observer started, and it bought NIFTY and BANKNIFTY PE on the first poll."""
    bear = {"bias": "BEARISH BIAS", "confidence": 85}
    assert _replay([bear, bear, bear]) == [False, False, False]
    # ...including when the first answer is the cold-cache placeholder.
    assert _replay([PLACEHOLDER, bear, bear]) == [False, False, False]


def test_a_genuine_change_still_triggers():
    bear = {"bias": "BEARISH BIAS", "confidence": 85}
    bull = {"bias": "BULLISH BIAS", "confidence": 70}
    assert _replay([bear, bull]) == [False, True]
    assert _replay([{"bias": "BULLISH BIAS", "confidence": 50},
                    {"bias": "BULLISH BIAS", "confidence": 66}]) == [False, True]


@pytest.mark.parametrize("t,expected", [
    ((9, 15), False), ((9, 24), False), ((9, 25), True), ((12, 0), True),
    ((15, 0), True), ((15, 1), False), ((15, 15), False),
])
def test_ema9_entries_respect_the_strategy_window(t, expected):
    assert po.entry_window_open("ema9_rsi_momentum", datetime.time(*t)) is expected


def test_other_strategies_keep_only_the_eod_cutoff():
    assert po.entry_window_open("some_other_strategy", datetime.time(9, 15)) is True
    assert po.entry_window_open("some_other_strategy", datetime.time(15, 15)) is False


def test_the_loop_uses_both_guards():
    import inspect

    src = inspect.getsource(po.run_session)
    assert "is_new_entry_trigger(prev_signals.get(symbol), obs)" in src
    assert "entry_window_open(active_strategy)" in src


# ---------------------------------------------------------------------------
# Reversal exit on closed bars
# ---------------------------------------------------------------------------

def test_reversal_exit_never_reads_the_forming_bar(monkeypatch):
    start = datetime.datetime(2026, 9, 11, 9, 15)
    candles = [_c((start + datetime.timedelta(minutes=5 * k)).strftime("%Y-%m-%d %H:%M:%S"),
                  23_300.0 + k) for k in range(61)]                      # 09:15 .. 14:15
    monkeypatch.setattr(po, "fetch_candles", lambda *a, **k: candles)
    monkeypatch.setattr(po, "now_ist", lambda: _ist(14, 17))             # 14:15 bar forming
    seen = {}

    def fake_exit(df, side, entry, current):
        seen["last"], seen["n"] = df.index[-1], len(df)
        return types.SimpleNamespace(should_exit=False, warning=False, premium_health=None)

    import trading_bot.strategies.ema9_rsi_momentum as strat
    monkeypatch.setattr(strat, "evaluate_protective_exit", fake_exit)
    po.check_reversal_exit("NIFTY", "CE", 100.0, 101.0)
    assert seen["last"] == pd.Timestamp("2026-09-11 14:10:00") and seen["n"] == 60
