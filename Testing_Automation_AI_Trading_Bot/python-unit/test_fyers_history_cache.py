"""The broker's local history cache must hold final, complete bars (2026-09-11).

Most history callers read ``data/<symbol>_<timeframe>.csv``, which
``FyersBroker.get_historical_data`` maintains. Compared bar by bar against an
independent source (yfinance) on 2026-09-11:

  2026-09-04 .. 09-09   0-2 five-minute bars per day off by more than 2 points
  2026-09-10            25 of 75 off, mean |close error| 3.15
  2026-09-11            23 of 23 off, mean |close error| 8.35

and the 15-minute cache held 3 of 2026-09-10's 25 bars. Causes: forming bars
were persisted; ``drop_duplicates`` kept the OLD cached row, so they were
never corrected; the incremental fetch started the day AFTER the last cached
one, so a day first cached mid-session stayed partial; and non-atomic writes
left a truncated ``2026-07-2,,,,,`` row in the file.
"""

from __future__ import annotations

import datetime

import pandas as pd
import pytest

from brokers import history_cache as hc
from brokers.fyers_broker import FyersBroker

COLS = ["datetime", "open", "high", "low", "close", "volume"]
CACHE = "NSE_NIFTY50-INDEX_5Min.csv"
DAY = "2026-09-01"
TODAY = datetime.date.today().isoformat()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def test_truncated_rows_are_dropped():
    df = pd.DataFrame([["2026-07-17 15:25:00", 1.0, 1.0, 1.0, 1.0, 0],
                       ["2026-07-2", None, None, None, None, None],
                       ["2026-07-20 09:15:00", 2.0, 2.0, 2.0, 2.0, 0]], columns=COLS)
    assert list(hc.clean_cache_frame(df)["datetime"]) == ["2026-07-17 15:25:00", "2026-07-20 09:15:00"]


def test_only_finished_intraday_bars_are_kept():
    df = pd.DataFrame({"datetime": ["2026-09-11 10:20:00", "2026-09-11 10:25:00", "2026-09-11 10:30:00"]})
    out = hc.closed_rows(df, "5", now=datetime.datetime(2026, 9, 11, 10, 30, 5))
    assert list(out["datetime"]) == ["2026-09-11 10:20:00", "2026-09-11 10:25:00"]
    out = hc.closed_rows(df, "15", now=datetime.datetime(2026, 9, 11, 10, 39))
    assert list(out["datetime"]) == ["2026-09-11 10:20:00"]      # 10:25 bar ends 10:40
    out = hc.closed_rows(df, "15", now=datetime.datetime(2026, 9, 11, 10, 40))
    assert list(out["datetime"]) == ["2026-09-11 10:20:00", "2026-09-11 10:25:00"]


def test_todays_daily_bar_and_the_open_week_are_not_final():
    df = pd.DataFrame({"datetime": ["2026-09-10 00:00:00", "2026-09-11 00:00:00"]})
    noon = datetime.datetime(2026, 9, 11, 12)
    assert list(hc.closed_rows(df, "D", now=noon)["datetime"]) == ["2026-09-10 00:00:00"]
    assert list(hc.closed_rows(df, "W", now=noon)["datetime"]) == ["2026-09-10 00:00:00"]


def test_atomic_write_leaves_no_temp_file(tmp_path):
    path = tmp_path / "x.csv"
    hc.write_cache_atomic(pd.DataFrame({"a": [1]}), str(path))
    assert path.read_text().startswith("a")
    assert not (tmp_path / "x.csv.tmp").exists()


def test_the_default_cache_dir_is_the_real_data_dir():
    import os

    import brokers
    assert os.path.normpath(hc.CACHE_DIR) == os.path.normpath(
        os.path.join(os.path.dirname(os.path.dirname(brokers.__file__)), "data"))


# ---------------------------------------------------------------------------
# Through get_historical_data
# ---------------------------------------------------------------------------

@pytest.fixture
def cache_dir(tmp_path, monkeypatch):
    """Never touch the live cache."""
    monkeypatch.setattr(hc, "CACHE_DIR", str(tmp_path))
    monkeypatch.setattr("time.sleep", lambda _s: None)          # chunk pacing
    return tmp_path


def _epoch(dt: datetime.datetime) -> int:
    return int(dt.timestamp())


def _day_bars(day: str, close: float = 100.0):
    start = datetime.datetime.strptime(f"{day} 09:15", "%Y-%m-%d %H:%M")
    return [[_epoch(start + datetime.timedelta(minutes=5 * k)), close, close + 1, close - 1, close, 1000]
            for k in range(75)]


class _FakeModel:
    """Fyers' history() over a fixed candle list, honouring range_from/to."""

    def __init__(self, candles):
        self.candles = candles
        self.requests = []

    def history(self, data):
        self.requests.append((data["range_from"], data["range_to"]))
        lo = datetime.datetime.strptime(data["range_from"], "%Y-%m-%d")
        hi = datetime.datetime.strptime(data["range_to"], "%Y-%m-%d") + datetime.timedelta(days=1)
        out = [c for c in self.candles if lo <= datetime.datetime.fromtimestamp(c[0]) < hi]
        return {"s": "ok", "candles": out} if out else {"s": "no_data"}


def _broker(model):
    broker = FyersBroker(credentials={"client_id": "FAKE-100"}, paper_mode=True)
    broker._fyers_model = model
    return broker


def _write_cache(cache_dir, rows):
    pd.DataFrame(rows, columns=COLS).to_csv(cache_dir / CACHE, index=False)


def _read_cache(cache_dir):
    return pd.read_csv(cache_dir / CACHE)


def test_a_partially_cached_day_is_completed(cache_dir):
    """2026-09-10's 15-minute bars: cached at ~10:00, never completed."""
    _write_cache(cache_dir, [[f"{DAY} 09:{m}:00", 100.0, 101.0, 99.0, 100.0, 1000] for m in ("15", "20", "25")])
    model = _FakeModel(_day_bars(DAY))
    _broker(model).get_historical_data("NIFTY", DAY, TODAY, "5 Min")
    assert model.requests[0][0] == DAY                        # the last cached day itself
    assert (_read_cache(cache_dir)["datetime"].str[:10] == DAY).sum() == 75


def test_fresh_bars_replace_stale_cached_ones(cache_dir):
    _write_cache(cache_dir, [[f"{DAY} 09:15:00", 90.0, 90.0, 90.0, 90.0, 5]])   # a forming-bar stub
    _broker(_FakeModel(_day_bars(DAY))).get_historical_data("NIFTY", DAY, TODAY, "5 Min")
    row = _read_cache(cache_dir).set_index("datetime").loc[f"{DAY} 09:15:00"]
    assert (row["high"], row["low"], row["close"]) == (101.0, 99.0, 100.0)


def test_a_forming_bar_is_returned_but_never_persisted(cache_dir):
    now = datetime.datetime.now()
    forming = now.replace(second=0, microsecond=0) - datetime.timedelta(minutes=now.minute % 5)
    closed = forming - datetime.timedelta(minutes=5)
    candles = [[_epoch(closed), 100.0, 101.0, 99.0, 100.0, 1000],
               [_epoch(forming), 100.0, 100.0, 100.0, 100.0, 7]]
    got = _broker(_FakeModel(candles)).get_historical_data("NIFTY", TODAY, TODAY, "5 Min")
    fmt = "%Y-%m-%d %H:%M:%S"
    assert forming.strftime(fmt) in [c["datetime"] for c in got]
    assert list(_read_cache(cache_dir)["datetime"]) == [closed.strftime(fmt)]


def test_a_truncated_row_does_not_survive_a_rewrite(cache_dir):
    _write_cache(cache_dir, [[f"{DAY} 09:15:00", 100.0, 101.0, 99.0, 100.0, 1000]])
    with open(cache_dir / CACHE, "a", encoding="utf-8") as f:
        f.write("2026-07-2,,,,,\n")
    _broker(_FakeModel(_day_bars(DAY))).get_historical_data("NIFTY", DAY, TODAY, "5 Min")
    cached = _read_cache(cache_dir)
    assert "2026-07-2" not in set(cached["datetime"])
    assert cached[["open", "high", "low", "close"]].notna().all().all()
