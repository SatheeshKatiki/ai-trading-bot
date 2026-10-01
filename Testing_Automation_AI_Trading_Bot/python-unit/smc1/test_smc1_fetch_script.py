"""smc1 futures-history fetch script: guards, chunking and the quality report.

Offline only -- the broker is replaced by a fake ``history`` callable, so
these tests never touch the network or the token cache.
"""

from __future__ import annotations

import importlib.util
import sys
from datetime import date, datetime, timedelta

import pandas as pd
import pytest

import _bootstrap  # noqa: F401
from _bootstrap import REPO_ROOT

_spec = importlib.util.spec_from_file_location(
    "smc1_fetch", REPO_ROOT / "trading-system" / "scripts" / "smc1_fetch_futures_history.py")
fetch = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
sys.modules["smc1_fetch"] = fetch          # dataclasses resolve their module by name
_spec.loader.exec_module(fetch)


def _trading(_d: date) -> bool:
    return True


def _holiday(_d: date) -> bool:
    return False


@pytest.mark.parametrize("now, trading, allowed", [
    (datetime(2026, 10, 1, 3, 6), True, False),     # before the open: still refused
    (datetime(2026, 10, 1, 12, 0), True, False),    # market hours
    (datetime(2026, 10, 1, 15, 44), True, False),
    (datetime(2026, 10, 1, 15, 45), True, True),    # the owner's line
    (datetime(2026, 10, 1, 22, 0), True, True),
    (datetime(2026, 10, 3, 11, 0), False, True),    # weekend / holiday: any time
])
def test_fetch_window(now, trading, allowed):
    reason = fetch.fetch_window_reason(now, _trading if trading else _holiday)
    assert (reason is None) is allowed
    if not allowed:
        assert "15:45" in reason


def test_futures_symbols_roll_across_the_year():
    assert fetch.futures_symbols(date(2026, 10, 1)) == ["NSE:NIFTY26OCTFUT", "NSE:NIFTY26NOVFUT"]
    assert fetch.futures_symbols(date(2026, 12, 30)) == ["NSE:NIFTY26DECFUT", "NSE:NIFTY27JANFUT"]


def test_expected_bars_per_session():
    assert [fetch.expected_bars(m) for m in (1, 5, 15, 60)] == [375, 75, 25, 7]


def _epoch(ts: datetime) -> int:
    """Unix seconds of a naive IST wall-clock time."""
    return int((ts - timedelta(hours=5, minutes=30) - datetime(1970, 1, 1)).total_seconds())


class FakeHistory:
    """Serves 5m bars for 2026-06-01 and 2026-09-14 only, records every call."""

    def __init__(self, reject_oi: bool = False, error_on: str | None = None, failures: int = 99,
                 error: dict | None = None):
        self.calls: list[dict] = []
        self.reject_oi = reject_oi
        self.error_on = error_on
        self.failures = failures
        self.error = error or {"s": "error", "message": "server busy"}

    def __call__(self, req: dict) -> dict:
        self.calls.append(dict(req))
        if self.reject_oi and "oi_flag" in req:
            return {"s": "error", "message": "invalid oi_flag"}
        if self.error_on and req["range_from"] == self.error_on and self.failures > 0:
            self.failures -= 1
            return dict(self.error)
        lo, hi = date.fromisoformat(req["range_from"]), date.fromisoformat(req["range_to"])
        candles = []
        for day in (date(2026, 6, 1), date(2026, 9, 14)):
            if lo <= day <= hi:
                t0 = datetime.combine(day, datetime.min.time()).replace(hour=9, minute=15)
                for k in range(75):
                    ts = t0 + timedelta(minutes=5 * k)
                    row = [_epoch(ts), 100.0, 101.0, 99.0, 100.5, 0.0 if k == 0 else 500.0]
                    if "oi_flag" in req:
                        row.append(1_000_000.0)
                    candles.append(row)
        return {"s": "ok", "candles": candles} if candles else {"s": "no_data"}


def test_fetch_is_chunked_and_converts_to_ist():
    h = FakeHistory()
    frame, notes = fetch.fetch_resolution(h, "NSE:NIFTY26OCTFUT", "5",
                                          date(2026, 1, 1), date(2026, 10, 1), pause_s=0)
    assert notes == []
    spans = [(date.fromisoformat(c["range_from"]), date.fromisoformat(c["range_to"])) for c in h.calls]
    assert all((b - a).days <= fetch.CHUNK_DAYS for a, b in spans)
    assert spans[0][0] == date(2026, 1, 1) and spans[-1][1] == date(2026, 10, 1)
    assert all(c["cont_flag"] == "1" and c["symbol"] == "NSE:NIFTY26OCTFUT" for c in h.calls)
    assert len(frame) == 150 and frame["datetime"].iloc[0] == pd.Timestamp("2026-06-01 09:15")
    assert "oi" in frame.columns


def test_oi_rejection_falls_back_without_oi():
    h = FakeHistory(reject_oi=True)
    frame, notes = fetch.fetch_resolution(h, "S", "5", date(2026, 1, 1), date(2026, 10, 1), pause_s=0)
    assert "oi" not in frame.columns and len(frame) == 150
    assert any("oi_flag rejected" in n for n in notes)


def test_a_transient_error_is_retried():
    h = FakeHistory(error_on="2026-05-31", failures=2)          # 3rd attempt succeeds
    frame, notes = fetch.fetch_resolution(h, "S", "5", date(2026, 1, 1), date(2026, 10, 1), pause_s=0)
    assert len(frame) == 150 and notes == []


def test_a_chunk_that_keeps_failing_is_named_as_lost():
    h = FakeHistory(error_on="2026-05-31")                     # 2026-06-01 lives in that chunk
    frame, notes = fetch.fetch_resolution(h, "S", "5", date(2026, 1, 1), date(2026, 10, 1), pause_s=0)
    assert len(frame) == 75
    assert notes == ["5 2026-05-31..2026-06-29: LOST after 3 attempts -- server busy"]


@pytest.mark.parametrize("error, kind", [
    ({"s": "error", "code": 429, "message": "Request limit reached"}, "rate_limit"),
    ({"s": "error", "message": "Too many requests"}, "rate_limit"),
    ({"s": "error", "code": -16, "message": "Could not authenticate the user"}, "token"),
    ({"s": "error", "code": -15, "message": "Token is expired"}, "token"),
])
def test_rate_limit_and_token_errors_stop_the_whole_run(error, kind):
    assert fetch.classify_error(error) == kind
    h = FakeHistory(error_on="2026-01-31", error=error)
    with pytest.raises(fetch.StopFetch, match=kind):
        fetch.fetch_resolution(h, "S", "5", date(2026, 1, 1), date(2026, 10, 1), pause_s=0)
    assert h.calls[-1]["range_from"] == "2026-01-31"        # stopped at once, no retry
    assert len(h.calls) == 2


def test_ordinary_errors_are_not_hard_stops():
    assert fetch.classify_error({"s": "error", "message": "server busy"}) == "other"
    assert fetch.classify_error({"s": "error", "message": "invalid oi_flag"}) == "other"


def test_chunks_are_at_most_thirty_days():
    h = FakeHistory()
    fetch.fetch_resolution(h, "S", "1", date(2026, 1, 1), date(2026, 3, 31), pause_s=0)
    spans = [(date.fromisoformat(c["range_from"]), date.fromisoformat(c["range_to"])) for c in h.calls]
    assert spans[:2] == [(date(2026, 1, 1), date(2026, 1, 30)), (date(2026, 1, 31), date(2026, 3, 1))]
    assert all((b - a).days + 1 <= 30 for a, b in spans)


class FakeContinuous:
    """A continuous series: one bar on every day from ``begins`` onward."""

    def __init__(self, begins: date):
        self.begins = begins
        self.calls: list[dict] = []

    def __call__(self, req: dict) -> dict:
        self.calls.append(dict(req))
        lo, hi = date.fromisoformat(req["range_from"]), date.fromisoformat(req["range_to"])
        first = max(lo, self.begins)
        if first > hi:
            return {"s": "no_data"}
        t = datetime.combine(first, datetime.min.time()).replace(hour=9, minute=15)
        return {"s": "ok", "candles": [[_epoch(t), 1.0, 1.0, 1.0, 1.0, 1.0]]}


def test_find_first_year_probes_january_and_july():
    h = FakeContinuous(date(2025, 3, 10))
    assert fetch.find_first_year(h, "S", "5", 2023, date(2026, 10, 1), pause_s=0) == 2025
    probed = [c["range_from"] for c in h.calls]
    assert probed == ["2023-01-01", "2023-07-01", "2024-01-01", "2024-07-01", "2025-01-01",
                      "2025-07-01"]
    assert fetch.find_first_year(FakeContinuous(date(2030, 1, 1)), "S", "5", 2026,
                                 date(2026, 10, 1), pause_s=0) is None


@pytest.mark.parametrize("cmd, settings, positions, refused", [
    ([], {}, {}, None),
    ([["python", r"trading_bot\main.py"]], {"live_trading_mode": False}, {}, None),
    ([["python", "trading_bot/main.py"]], {"live_trading_mode": False}, {"N": {}}, "main.py is running"),
    ([["python", "-u", "D:/x/paper_observer.py"]], {}, {"N": {}}, "paper_observer.py is running"),
    ([["python", "trading_bot/main.py"]], {"live_trading_mode": True}, {}, "LIVE mode"),
    ([], {"live_trading_mode": True}, {"N": {}, "M": {}}, None),   # nothing running: stale file
])
def test_engine_check(cmd, settings, positions, refused):
    state = fetch.engine_state(cmd, settings, positions)
    r = state.refusal()
    assert (r is None) if refused is None else (refused in r)


def test_symbols():
    assert fetch.previous_month_symbol(date(2026, 10, 1)) == "NSE:NIFTY26SEPFUT"
    assert fetch.previous_month_symbol(date(2027, 1, 5)) == "NSE:NIFTY26DECFUT"


def test_last_weekday_and_roll_gap_summary():
    assert fetch.last_weekday_of_month(2026, 9, 1) == date(2026, 9, 29)     # Tuesday
    assert fetch.last_weekday_of_month(2026, 12, 3) == date(2026, 12, 31)   # Thursday
    days = [date(2026, 9, d) for d in (25, 28, 29, 30)] + [date(2026, 10, 1)]
    gaps = pd.Series([0.1, -0.2, 0.1, -0.6, 0.1], index=days)
    out = fetch.roll_gap_summary(gaps)
    assert out["after_last_tue_n"] == 1 and out["after_last_tue_median_abs_gap_pct"] == 0.6
    assert out["all_sessions_median_abs_gap_pct"] == 0.1
    assert fetch.roll_gap_summary(pd.Series(dtype=float)) == {}


def test_compare_series():
    a = pd.DataFrame({"datetime": pd.to_datetime(["2026-09-01 09:15", "2026-09-01 09:30"]),
                      "close": [1.0, 2.0]})
    b = pd.DataFrame({"datetime": pd.to_datetime(["2026-09-01 09:30", "2026-09-01 09:45"]),
                      "close": [2.5, 3.0]})
    out = fetch.compare_series(a, b)
    assert out["overlap_bars"] == 1 and out["max_abs_close_diff"] == 0.5 and out["bars_with_diff"] == 1
    assert fetch.compare_series(a, b.iloc[1:]) == {"overlap_bars": 0}


def test_quality_report_counts_gaps_duplicates_and_zero_volume():
    h = FakeHistory()
    frame, _ = fetch.fetch_resolution(h, "S", "5", date(2026, 5, 30), date(2026, 9, 20), pause_s=0)
    frame = pd.concat([frame, frame.iloc[[3]]])                 # one duplicate
    frame = frame.drop(frame.index[10])                         # one missing bar
    q = fetch.quality_report(frame, 5)
    assert q.bars == 149 and q.duplicate_timestamps == 1
    assert q.sessions == 2 and q.full_sessions == 1 and q.missing_bars == 1
    assert q.zero_volume_bars == 2 and q.outside_session_bars == 0
    assert q.oi_present and q.oi_zero_or_missing_pct == 0.0
    assert q.first == "2026-06-01 09:15:00" and len(q.largest_open_gaps) == 1
    md = fetch.report_markdown("S", date(2026, 5, 30), date(2026, 9, 20), [q], ["note"],
                               datetime(2026, 10, 1, 16, 0))
    assert "| 5m | 149 |" in md and "note" in md


def test_empty_frame_report():
    q = fetch.quality_report(pd.DataFrame(columns=["datetime", "open", "high", "low", "close",
                                                   "volume"]), 15)
    assert q.bars == 0 and q.expected_bars_per_session == 25


def test_csv_write_returns_its_hash(tmp_path):
    frame = pd.DataFrame({"datetime": [pd.Timestamp("2026-06-01 09:15")], "open": [1.0]})
    sha = fetch.write_csv(frame, tmp_path / "x" / "f.csv")
    assert len(sha) == 64 and (tmp_path / "x" / "f.csv").exists()
