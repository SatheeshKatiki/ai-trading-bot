"""Phase 11 sec5-sec9 -- timeframe scaling of the frozen prior-day-extreme rule.

PRE-DECLARED BEFORE ANY RESULT WAS INSPECTED
--------------------------------------------
instruments      NIFTY first (sec17). BANKNIFTY / SENSEX only after the NIFTY
                 methodology is fixed. FINNIFTY stays SEALED.
timeframes       5 / 15 / 30 / 60 minutes
rule             UNCHANGED from Phase 10: |close - PDH/PDL| <= 0.25 * ATR(14),
                 near PDL -> long, near PDH -> short. No filters added.
ATR              ATR(14) computed on the RESAMPLED frame, so the band scales
                 with that timeframe's own volatility. Causal.
prior-day levels max high / min low of the previous session. Identical values
                 at every timeframe by construction.
selection        Policy A (frozen Phase 10): first setup of the day.
dedup            episodes = contiguous in-band runs (Phase 10 semantics).
entry            the NEXT bar's OPEN after the signal bar's close.
holding windows  30 / 60 / 120 / 240 MINUTES of wall clock, converted to bars
                 per timeframe, so the comparison is like-for-like on the
                 thing that actually drives theta.
splits           DEV 2024-01-01..2025-06-30, VAL 2025-07-01..2026-03-31.
                 2026-04-01+ is the Phase 8 contaminated window, reported
                 separately and never used to choose anything.

RESAMPLING
----------
Source bars are LEFT-labelled (09:15 covers 09:15-09:20; 75 bars/day ending
15:25). Resampling is done PER DAY with the origin pinned to that day's first
bar, because 30- and 60-minute grids do not divide evenly from midnight
(09:15 = 555 minutes; 555/30 and 555/60 are not integers). Per-day origin is
also what a real session chart shows. The final bar of a day may be partial,
exactly as it is live.
"""
from __future__ import annotations

import os
import sys

SP = os.path.dirname(os.path.abspath(__file__))
if SP not in sys.path:
    sys.path.insert(0, SP)

import numpy as np
import pandas as pd

import p8lib as P  # noqa: E402

AGG = {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}
TIMEFRAMES = (5, 15, 30, 60)
HOLD_MINUTES = (30, 60, 120, 240)


def resample_session(bars: pd.DataFrame, minutes: int) -> pd.DataFrame:
    """Per-day, session-origin resample. Causal: each output bar aggregates
    only source bars inside it."""
    if minutes == 5:
        return bars.copy()
    out = []
    for _day, chunk in bars.groupby(bars.index.normalize()):
        r = chunk.resample(f"{minutes}min", label="left", closed="left",
                           origin=chunk.index[0]).agg(AGG).dropna(subset=["close"])
        out.append(r)
    return pd.concat(out).sort_index()


def bars_for_minutes(minutes_held: int, tf: int) -> int:
    """Holding window in bars for this timeframe. At least one bar."""
    return max(1, int(round(minutes_held / tf)))


def describe(bars: pd.DataFrame, tf: int) -> dict:
    days = bars.index.normalize().nunique()
    return dict(tf=tf, bars=len(bars), days=days,
                bars_per_day=len(bars) / max(1, days))
