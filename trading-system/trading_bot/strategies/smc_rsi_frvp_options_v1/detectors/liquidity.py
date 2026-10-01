"""Liquidity levels and sweeps (spec §3.8).

Levels (each typed, each with the time it became known):

* ``EQH`` / ``EQL`` -- two confirmed pivots (5m or 15m) of the same side within
  ``max(eq_tol_pct% x price, eq_tol_atr_mult x ATR)``. The newer pivot is
  compared with the previous ``eq_max_pivots_back`` pivots of its side and
  timeframe; the level is the higher of the two highs (EQH) or the lower of
  the two lows (EQL), known when the newer pivot confirms.
* ``PDH`` / ``PDL`` / ``PDC`` -- the previous completed session, known from
  the first bar of the new session.
* ``ORH`` / ``ORL`` -- the opening range (session open .. opening_range_end),
  known when the last bar inside it closes.
* ``SWING_HIGH_15M`` / ``SWING_LOW_15M`` -- the most recent confirmed 15m
  pivot of each side (a newer one replaces the older).

Sides: highs are buy-side liquidity (resting above price, swept from below,
traded for a PE); lows are sell-side (swept from above, traded for a CE).
``PDC`` is both.

Sweep, evaluated on 5m bars (sell-side shown; buy-side mirrors):

1. a 5m bar trades below the level by at least
   ``sweep_min_atr_mult x ATR5`` -- the sweep candle, bar ``k``;
2. a 5m bar from ``k`` to ``k + sweep_reclaim_bars`` CLOSES back above the
   level -- the reclaim. The sweep candle closing back above counts
   (``sweep_reclaim_bars`` counts bars after it);
3. the sweep event is emitted on the reclaim bar, with the extreme (lowest
   low from ``k`` to the reclaim).

A level must be known before the sweep candle starts. A level is used for at
most one sweep: once swept, or once the reclaim window lapses with price
still beyond it (a break, not a sweep), it is retired.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time
from enum import Enum
from typing import Optional

from ..types import Bar, Direction, Pivot


class LevelType(Enum):
    EQH = "EQH"
    EQL = "EQL"
    PDH = "PDH"
    PDL = "PDL"
    PDC = "PDC"
    ORH = "ORH"
    ORL = "ORL"
    SWING_HIGH_15M = "SWING_HIGH_15M"
    SWING_LOW_15M = "SWING_LOW_15M"


_BUY_SIDE = {LevelType.EQH, LevelType.PDH, LevelType.ORH, LevelType.SWING_HIGH_15M, LevelType.PDC}
_SELL_SIDE = {LevelType.EQL, LevelType.PDL, LevelType.ORL, LevelType.SWING_LOW_15M, LevelType.PDC}


@dataclass
class Level:
    type: LevelType
    price: float
    known_at: datetime
    source: str = ""
    retired_at: Optional[datetime] = None

    @property
    def buy_side(self) -> bool:
        return self.type in _BUY_SIDE

    @property
    def sell_side(self) -> bool:
        return self.type in _SELL_SIDE


@dataclass(frozen=True)
class Sweep:
    """A completed sweep. ``direction`` is the trade it supports:
    BULL for a sell-side sweep (CE), BEAR for a buy-side sweep (PE)."""

    direction: Direction
    level: Level
    sweep_index: int
    sweep_ts: datetime
    reclaim_index: int
    confirmed_at: datetime
    extreme: float
    depth_atr: float


@dataclass
class _Pending:
    level: Level
    direction: Direction
    start_index: int
    start_ts: datetime
    extreme: float
    depth_atr: float


class EqualLevelTracker:
    """EQH / EQL from one timeframe's confirmed pivots."""

    def __init__(self, timeframe: str, tol_pct: float, tol_atr_mult: float,
                 max_pivots_back: int) -> None:
        self.timeframe = timeframe
        self.tol_pct = tol_pct
        self.tol_atr_mult = tol_atr_mult
        self.max_back = max_pivots_back
        self._highs: list[Pivot] = []
        self._lows: list[Pivot] = []

    def tolerance(self, price: float, atr: Optional[float]) -> float:
        return max(self.tol_pct / 100.0 * price, self.tol_atr_mult * (atr or 0.0))

    def update(self, pivot: Pivot, atr: Optional[float]) -> Optional[Level]:
        book = self._highs if pivot.is_high else self._lows
        level: Optional[Level] = None
        tol = self.tolerance(pivot.price, atr)
        for prev in reversed(book[-self.max_back:]):
            if abs(prev.price - pivot.price) <= tol:
                price = max(prev.price, pivot.price) if pivot.is_high else min(prev.price, pivot.price)
                level = Level(LevelType.EQH if pivot.is_high else LevelType.EQL, price,
                              pivot.confirmed_at,
                              f"{self.timeframe} pivots {prev.index}+{pivot.index}")
                break
        book.append(pivot)
        return level


class SessionLevelTracker:
    """PDH / PDL / PDC and the opening range, from intraday bars."""

    def __init__(self, session_open: time, opening_range_end: time) -> None:
        self.session_open = session_open
        self.or_end = opening_range_end
        self._day: Optional[date] = None
        self._hi = float("-inf")
        self._lo = float("inf")
        self._close: Optional[float] = None
        self._or_hi = float("-inf")
        self._or_lo = float("inf")
        self._or_done = False

    def update(self, bar: Bar) -> list[Level]:
        out: list[Level] = []
        day = bar.ts.date()
        if self._day is not None and day != self._day and self._close is not None:
            known = bar.ts
            out += [Level(LevelType.PDH, self._hi, known, str(self._day)),
                    Level(LevelType.PDL, self._lo, known, str(self._day)),
                    Level(LevelType.PDC, self._close, known, str(self._day))]
        if day != self._day:
            self._day = day
            self._hi, self._lo = float("-inf"), float("inf")
            self._or_hi, self._or_lo = float("-inf"), float("inf")
            self._or_done = False
        self._hi = max(self._hi, bar.high)
        self._lo = min(self._lo, bar.low)
        self._close = bar.close
        if not self._or_done and self.session_open <= bar.ts.time() < self.or_end:
            self._or_hi = max(self._or_hi, bar.high)
            self._or_lo = min(self._or_lo, bar.low)
            if bar.close_time.time() >= self.or_end:
                self._or_done = True
                out += [Level(LevelType.ORH, self._or_hi, bar.close_time, str(day)),
                        Level(LevelType.ORL, self._or_lo, bar.close_time, str(day))]
        return out


@dataclass
class SweepUpdate:
    started: list[Level] = field(default_factory=list)
    sweeps: list[Sweep] = field(default_factory=list)
    broken: list[Level] = field(default_factory=list)


class SweepDetector:
    """Holds the live level book and turns 5m bars into sweeps."""

    def __init__(self, min_atr_mult: float, reclaim_bars: int) -> None:
        self.min_atr_mult = min_atr_mult
        self.reclaim_bars = reclaim_bars
        self.levels: list[Level] = []
        self._pending: list[_Pending] = []
        self.sweeps: list[Sweep] = []

    def add_level(self, level: Level) -> None:
        if level.type in (LevelType.SWING_HIGH_15M, LevelType.SWING_LOW_15M):
            for old in self.levels:
                if old.type is level.type and old.retired_at is None:
                    old.retired_at = level.known_at
        self.levels.append(level)

    def active_levels(self) -> list[Level]:
        return [lv for lv in self.levels if lv.retired_at is None]

    def update(self, i: int, bar: Bar, atr: Optional[float]) -> SweepUpdate:
        out = SweepUpdate()
        # 1. Pending sweeps: reclaim, or lapse into a break.
        still: list[_Pending] = []
        for p in self._pending:
            if p.level.retired_at is not None:   # resolved the other way (PDC)
                continue
            if p.direction is Direction.BULL:
                p.extreme = min(p.extreme, bar.low)
                reclaimed = bar.close > p.level.price
            else:
                p.extreme = max(p.extreme, bar.high)
                reclaimed = bar.close < p.level.price
            if reclaimed:
                self._complete(p, i, bar, out)
            elif i - p.start_index >= self.reclaim_bars:
                p.level.retired_at = bar.close_time
                out.broken.append(p.level)
            else:
                still.append(p)
        self._pending = still

        # 2. New sweep candles against levels known before this bar started.
        if atr is None or atr <= 0:
            return out
        threshold = self.min_atr_mult * atr
        pending_keys = {(id(p.level), p.direction) for p in self._pending}
        for lv in self.levels:
            if lv.retired_at is not None or lv.known_at > bar.ts:
                continue
            # Both sides are evaluated before deciding: a two-sided level (PDC)
            # can be pierced on both sides by one bar, and only the side that
            # closed back is a sweep.
            candidates: list[tuple[_Pending, bool]] = []
            if (lv.sell_side and (id(lv), Direction.BULL) not in pending_keys
                    and bar.low <= lv.price - threshold):
                candidates.append((_Pending(lv, Direction.BULL, i, bar.ts, bar.low,
                                            (lv.price - bar.low) / atr), bar.close > lv.price))
            if (lv.buy_side and (id(lv), Direction.BEAR) not in pending_keys
                    and bar.high >= lv.price + threshold):
                candidates.append((_Pending(lv, Direction.BEAR, i, bar.ts, bar.high,
                                            (bar.high - lv.price) / atr), bar.close < lv.price))
            if not candidates:
                continue
            out.started.append(lv)
            done = [p for p, reclaimed in candidates if reclaimed]
            if done:
                self._complete(done[0], i, bar, out)
            elif self.reclaim_bars == 0:
                lv.retired_at = bar.close_time
                out.broken.append(lv)
            else:
                self._pending.extend(p for p, _ in candidates)
        return out

    def _complete(self, p: _Pending, i: int, bar: Bar, out: SweepUpdate) -> None:
        depth = p.depth_atr
        s = Sweep(p.direction, p.level, p.start_index, p.start_ts, i, bar.close_time,
                  p.extreme, depth)
        p.level.retired_at = bar.close_time
        self._pending = [q for q in self._pending if q.level is not p.level]
        self.sweeps.append(s)
        out.sweeps.append(s)


__all__ = [
    "EqualLevelTracker",
    "Level",
    "LevelType",
    "SessionLevelTracker",
    "Sweep",
    "SweepDetector",
    "SweepUpdate",
]
