"""A history query must return only the range it asked for (2026-09-10).

`_ensure_today_candles()` appended today's bars to **every** history request,
whatever window was asked for. A query for 2026-08-25..2026-08-25 came back
with 75 bars for that day plus 75 bars for today, stitched into one series --
so anything computing a range, an ATR or a return over a historical window
silently spanned a fortnight-wide gap.

Measured before and after on real data:

    2026-08-25    reported range 953.9 pts  ->  actual 219.1 pts
    2026-08-31    reported range 748.0 pts  ->  actual 135.1 pts

The same function also fabricated volume in four places -- appended bars,
updated bars, and a final pass that guaranteed "absolutely zero bars have 0
volume" -- from `avg_vol * ratio`, with `avg_vol` falling back to 2,500,000
when nothing in the window had any. NSE index series legitimately report no
volume, and `ExitAnalyzerAgent`'s Factor 4 reads volume deceleration as a live
exit input, so inventing it feeds a fabricated signal into a real decision.
"""

from __future__ import annotations

import datetime
import inspect

import pytest

import api_bridge as ab


# ---------------------------------------------------------------------------
# The window gate
# ---------------------------------------------------------------------------

def test_a_past_end_date_does_not_want_today():
    assert ab._wants_today("2026-08-25") is False


def test_todays_date_wants_today():
    today = datetime.datetime.now(ab._IST).date().strftime("%Y-%m-%d")
    assert ab._wants_today(today) is True


def test_a_future_end_date_wants_today():
    future = (datetime.datetime.now(ab._IST).date()
              + datetime.timedelta(days=7)).strftime("%Y-%m-%d")
    assert ab._wants_today(future) is True


@pytest.mark.parametrize("value", [None, "", "not-a-date", "2026-13-45"])
def test_unparseable_dates_keep_the_old_permissive_behaviour(value):
    """Callers that do not state a window still get live data."""
    assert ab._wants_today(value) is True


# ---------------------------------------------------------------------------
# Historical windows are left alone
# ---------------------------------------------------------------------------

def test_past_window_returns_the_input_untouched():
    bars = [
        {"datetime": "2026-08-25 09:15:00", "open": 1, "high": 2, "low": 0, "close": 1, "volume": 0},
        {"datetime": "2026-08-25 09:20:00", "open": 1, "high": 3, "low": 1, "close": 2, "volume": 5},
    ]
    out = ab._ensure_today_candles(list(bars), "NSE:NIFTY50-INDEX", "5 Min", "2026-08-25")
    assert len(out) == 2
    assert {b["datetime"] for b in out} == {b["datetime"] for b in bars}


def test_past_window_never_calls_the_live_source(monkeypatch):
    called = []
    monkeypatch.setattr(ab, "_fetch_yfinance_today",
                        lambda *a, **k: called.append(1) or [])
    ab._ensure_today_candles(
        [{"datetime": "2026-08-25 09:15:00", "open": 1, "high": 2, "low": 0, "close": 1, "volume": 1}],
        "NSE:NIFTY50-INDEX", "5 Min", "2026-08-25",
    )
    assert not called, "a historical query must not reach for today's bars"


def test_empty_past_window_stays_empty(monkeypatch):
    monkeypatch.setattr(ab, "_fetch_yfinance_today", lambda *a, **k: [
        {"datetime": "2026-09-10 09:15:00", "open": 1, "high": 2, "low": 0, "close": 1, "volume": 9}
    ])
    assert ab._ensure_today_candles([], "NSE:NIFTY50-INDEX", "5 Min", "2026-08-25") == []


# ---------------------------------------------------------------------------
# Volume is reported, not invented
# ---------------------------------------------------------------------------

def test_zero_volume_bars_are_passed_through(monkeypatch):
    """Index series legitimately carry no volume; that is not a gap to fill."""
    monkeypatch.setattr(ab, "_fetch_yfinance_today", lambda *a, **k: [])
    bars = [{"datetime": "2026-09-10 09:15:00", "open": 1, "high": 2, "low": 0,
             "close": 1, "volume": 0}]
    out = ab._ensure_today_candles(bars, "NSE:NIFTY50-INDEX", "5 Min", None)
    assert out[0]["volume"] == 0


def test_no_synthetic_volume_constants_remain():
    """The function's own docstring documents what was removed, so compare
    against the parsed body rather than raw source -- otherwise the
    explanation trips the assertion it is explaining."""
    import ast
    import textwrap

    tree = ast.parse(textwrap.dedent(inspect.getsource(ab._ensure_today_candles)))
    fn = tree.body[0]
    body = fn.body[1:] if ast.get_docstring(fn) else fn.body
    code = "\n".join(ast.unparse(node) for node in body)

    for banned in ("2500000", "avg_vol", "ratio"):
        assert banned not in code, f"volume fabrication is back: {banned}"


def test_a_real_volume_is_preferred_over_a_zero_from_the_top_up(monkeypatch):
    """If the live source reports 0 for a bar we already hold, keep ours."""
    monkeypatch.setattr(ab, "_fetch_yfinance_today", lambda *a, **k: [
        {"datetime": "2026-09-10 09:15:00", "open": 1, "high": 2, "low": 0, "close": 1, "volume": 0}
    ])
    existing = [{"datetime": "2026-09-10 09:15:00", "open": 1, "high": 2, "low": 0,
                 "close": 1, "volume": 4321}]
    out = ab._ensure_today_candles(existing, "NSE:NIFTY50-INDEX", "5 Min", None)
    assert out[0]["volume"] == 4321


# ---------------------------------------------------------------------------
# Today's window still tops up
# ---------------------------------------------------------------------------

def test_todays_window_appends_new_bars(monkeypatch):
    monkeypatch.setattr(ab, "_fetch_yfinance_today", lambda *a, **k: [
        {"datetime": "2026-09-10 09:20:00", "open": 2, "high": 3, "low": 1, "close": 2, "volume": 7}
    ])
    existing = [{"datetime": "2026-09-10 09:15:00", "open": 1, "high": 2, "low": 0,
                 "close": 1, "volume": 5}]
    out = ab._ensure_today_candles(existing, "NSE:NIFTY50-INDEX", "5 Min", None)
    assert len(out) == 2
