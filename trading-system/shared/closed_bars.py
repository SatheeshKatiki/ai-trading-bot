"""Closed-candle hygiene for anything that acts on a bar's close.

``/api/history`` returns the bar that is still FORMING as its final element:
at 10:30:05 IST the last 5-minute candle is the 10:30 bar, five seconds old,
and its "close" is merely the latest tick. Every rule in
``ema9_rsi_momentum`` -- the entry cross and the reversal exit alike -- is
defined on CLOSED candles, and ``premium_health.evaluate_protective_exit``
reads ``cross.bearish[-1]``: hand it the forming bar and a cross that appears
at 10:31 and is gone by 10:34 still closes the position.

``trading_bot/main.py`` already drops the forming bar for its own resampled
frames (see its "still FORMING" notes); this is the same rule for callers
that read candles over HTTP.
"""

from __future__ import annotations

import datetime as _dt
from typing import Iterable, List, Optional

import pandas as pd

_IST = "Asia/Kolkata"
_TIME_KEYS = ("datetime", "timestamp", "time", "date")


def bar_start(candle: dict) -> Optional[_dt.datetime]:
    """A candle's START time as a naive IST datetime, or None if unreadable.

    Accepts the ``"YYYY-MM-DD HH:MM:SS"`` strings ``/api/history`` returns
    (naive, already IST), tz-aware strings, and epoch seconds.
    """
    raw = next((candle.get(k) for k in _TIME_KEYS if candle.get(k) is not None), None)
    if raw is None:
        return None
    try:
        if isinstance(raw, (int, float)):
            ts = pd.Timestamp(raw, unit="s", tz="UTC")
        else:
            ts = pd.Timestamp(raw)
    except (ValueError, TypeError):
        return None
    if ts is pd.NaT:
        return None
    if ts.tzinfo is not None:
        ts = ts.tz_convert(_IST).tz_localize(None)
    return ts.to_pydatetime()


def _naive_ist(now: _dt.datetime) -> _dt.datetime:
    if now.tzinfo is None:
        return now
    return pd.Timestamp(now).tz_convert(_IST).tz_localize(None).to_pydatetime()


def closed_candles(candles: Iterable[dict], timeframe_minutes: int,
                   now: _dt.datetime) -> List[dict]:
    """Only the candles whose whole interval has elapsed at ``now``.

    A bar starting at ``t`` is closed once ``now >= t + timeframe``. A candle
    whose timestamp cannot be read is dropped: it cannot be proven closed,
    and acting on an unprovable bar is exactly the defect this prevents.
    """
    if timeframe_minutes <= 0:
        raise ValueError(f"timeframe_minutes must be positive, got {timeframe_minutes}")
    span = _dt.timedelta(minutes=timeframe_minutes)
    now = _naive_ist(now)
    out = []
    for candle in candles or ():
        start = bar_start(candle)
        if start is not None and start + span <= now:
            out.append(candle)
    return out


def candles_to_frame(candles: Iterable[dict]) -> pd.DataFrame:
    """OHLC(V) frame indexed by each bar's START time (naive IST).

    The index matters: ``compute_cross_signals``' trading-window filter reads
    ``df.index`` and silently disables itself for a non-datetime index, so a
    frame built with a default RangeIndex would let entries through at any
    hour.
    """
    rows, index = [], []
    for candle in candles or ():
        start = bar_start(candle)
        if start is None:
            continue
        index.append(start)
        rows.append({k: candle.get(k) for k in ("open", "high", "low", "close", "volume")})
    if not rows:
        return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
    df = pd.DataFrame(rows, index=pd.DatetimeIndex(index))
    for col in ("open", "high", "low", "close", "volume"):
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna(subset=["open", "high", "low", "close"])
    return df[~df.index.duplicated(keep="last")].sort_index()


#: NSE's regular session: the first bar starts 09:15, the last 5-minute bar 15:25.
SESSION_FIRST_BAR = "09:15"
SESSION_LAST_5M_BAR = "15:25"


def regular_session(df: pd.DataFrame) -> pd.DataFrame:
    """Only the regular-session bars of a 5-minute (or finer) frame.

    The live 5-minute cache carries pre-open bars (09:05 and 09:10 on
    2026-09-07..09) and the history files a Muhurat evening session
    (2024-11-01 18:20 onward). The backtest never saw either, and one stray
    bar shifts every EMA and RSI value after it.
    """
    if df.empty:
        return df
    t = df.index.strftime("%H:%M")
    return df[(t >= SESSION_FIRST_BAR) & (t <= SESSION_LAST_5M_BAR)]


def resample_closed(df: pd.DataFrame, minutes: int, now: _dt.datetime) -> pd.DataFrame:
    """``minutes``-bars built from a finer frame, keeping only fully closed ones.

    Left-labelled and left-closed -- exactly how the backtest built its
    15-minute bars from 5-minute ones -- so the live series and the measured
    one are the same construction. Feed it CLOSED input bars; an output bar is
    kept only once its whole interval has elapsed at ``now``.
    """
    if minutes <= 0:
        raise ValueError(f"minutes must be positive, got {minutes}")
    if df.empty:
        return df
    out = df.resample(f"{minutes}min", label="left", closed="left").agg(
        {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"})
    out = out.dropna(subset=["open", "high", "low", "close"])
    cutoff = _naive_ist(now) - _dt.timedelta(minutes=minutes)
    return out[out.index <= cutoff]
