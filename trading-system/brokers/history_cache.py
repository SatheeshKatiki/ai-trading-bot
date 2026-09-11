"""Hygiene for the local CSV cache behind ``FyersBroker.get_historical_data``.

Every history request is cached to ``data/<symbol>_<timeframe>.csv`` and the
cache is what most callers actually read. Measured on 2026-09-11 against an
independent source (yfinance), bar by bar:

  2026-09-04 .. 09-09   0-2 bars per day off by more than 2 points
  2026-09-10            25 of 75 5-minute bars off, mean |close error| 3.15
  2026-09-11            23 of 23 off, mean |close error| 8.35

Three defects produced that, plus a fourth that corrupted the file itself:

1. **Forming bars were persisted.** A request at 10:30:05 returns the 10:30
   bar five seconds old; it was written to the cache as if final.
2. **The old row won every merge.** ``drop_duplicates(subset=["datetime"])``
   keeps the FIRST occurrence -- the cached one -- so that five-second-old
   bar was never replaced by its completed version.
3. **A day seen once was never completed.** The incremental fetch started at
   ``cache_max_date + 1 day``, so a day first cached mid-session stayed
   partial for good: 2026-09-10 kept 3 of its 25 fifteen-minute bars.
4. **Writes were not atomic.** A truncated write left a ``2026-07-2,,,,,``
   row, later sorted into the middle of the file.

These helpers fix 1, 4 and the read side of 4; ``fyers_broker`` fixes 2 and 3
at the merge and fetch-window sites.
"""

from __future__ import annotations

import datetime as _dt
import os
from typing import Optional

import pandas as pd

#: Where the cache lives: trading-system/data. A module attribute rather than
#: a path rebuilt at the call site, so a test can point it at tmp_path
#: instead of writing into the live cache.
CACHE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")

#: Bar length in minutes for each intraday Fyers resolution.
_RESOLUTION_MINUTES = {"30S": 0.5, "1": 1, "3": 3, "5": 5, "15": 15, "30": 30, "60": 60}
_OHLC = ("open", "high", "low", "close")


def clean_cache_frame(df: Optional[pd.DataFrame]) -> Optional[pd.DataFrame]:
    """Drop rows with no parseable datetime or no OHLC -- what a truncated
    write leaves behind."""
    if df is None or df.empty or "datetime" not in df.columns:
        return df
    ok = pd.to_datetime(df["datetime"], errors="coerce").notna()
    return df[ok].dropna(subset=[c for c in _OHLC if c in df.columns])


def closed_rows(df: Optional[pd.DataFrame], resolution: str,
                now: Optional[_dt.datetime] = None) -> Optional[pd.DataFrame]:
    """Only the bars that have finished at ``now`` -- a forming bar must never
    be persisted as if it were final.

    Timestamps are naive local (IST) times, as ``get_historical_data`` writes
    them. Intraday: a bar starting at ``t`` is final once ``t + length <=
    now``. Daily: bars before today. Weekly/monthly: all but the latest,
    still-open period.
    """
    if df is None or df.empty:
        return df
    now = now or _dt.datetime.now()
    ts = pd.to_datetime(df["datetime"], errors="coerce")
    minutes = _RESOLUTION_MINUTES.get(str(resolution))
    if minutes is not None:
        keep = ts + pd.Timedelta(minutes=minutes) <= pd.Timestamp(now)
    elif str(resolution) in ("D", "1D"):
        keep = ts.dt.normalize() < pd.Timestamp(now).normalize()
    else:
        keep = ts < ts.max()
    return df[keep.fillna(False)]


def write_cache_atomic(df: pd.DataFrame, path: str) -> None:
    """Write to a sibling temp file, then swap it in, so a reader or a crash
    can never see a half-written cache."""
    tmp = f"{path}.tmp"
    df.to_csv(tmp, index=False)
    os.replace(tmp, path)
