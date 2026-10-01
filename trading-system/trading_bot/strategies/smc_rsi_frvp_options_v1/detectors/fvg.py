"""Fair value gaps (spec §3.6) and displacement candles (spec §3.5).

FVG at bar ``i`` (formed on its close, so confirmed at ``i``):

* bullish if ``low[i] > high[i-2]``; zone ``[high[i-2], low[i]]``
* bearish if ``high[i] < low[i-2]``; zone ``[high[i], low[i-2]]``
* only if the gap is at least ``min_atr_mult x ATR[i]`` (Wilder).

A bullish FVG is invalidated (mitigated) by the first later CLOSE below its
far edge (the zone low); a bearish one by a close above its zone high.
``fill_pct`` is how far price has traded into the zone from its near edge,
0..1.

Displacement (spec §3.5): bar ``j`` is a displacement candle in direction
``d`` when its body is in direction ``d``, ``body >= atr_mult x ATR[j]``,
``body / range >= body_ratio``, and it "creates or is part of" a qualifying
FVG of direction ``d``. Implemented as: when an FVG forms at ``i``, its
middle candle ``i-1`` and its third candle ``i`` are tested. A displacement
is therefore confirmed on bar ``i`` (for a middle candle, one bar after the
candle itself).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from ..types import Bar, Direction, Zone


@dataclass
class FairValueGap:
    direction: Direction
    zone: Zone
    index: int
    ts: datetime
    confirmed_at: datetime
    size_atr: float
    fill_pct: float = 0.0
    invalidated_index: Optional[int] = None

    @property
    def active(self) -> bool:
        return self.invalidated_index is None


@dataclass(frozen=True)
class Displacement:
    direction: Direction
    index: int
    ts: datetime
    confirmed_index: int
    confirmed_at: datetime
    body_atr: float
    body_ratio: float
    fvg_index: int


@dataclass
class FvgUpdate:
    new: list[FairValueGap] = field(default_factory=list)
    invalidated: list[FairValueGap] = field(default_factory=list)
    displacements: list[Displacement] = field(default_factory=list)


class FvgTracker:
    def __init__(self, min_atr_mult: float, displacement_atr_mult: float,
                 displacement_body_ratio: float) -> None:
        self.min_atr_mult = min_atr_mult
        self.disp_atr_mult = displacement_atr_mult
        self.disp_body_ratio = displacement_body_ratio
        self._bars: list[Bar] = []
        self._atr: list[Optional[float]] = []
        self.active: list[FairValueGap] = []
        self.history: list[FairValueGap] = []
        self.displacements: list[Displacement] = []

    def update(self, bar: Bar, atr: Optional[float]) -> FvgUpdate:
        i = len(self._bars)
        self._bars.append(bar)
        self._atr.append(atr)
        out = FvgUpdate()

        # 1. Existing gaps: fill and invalidation on this bar.
        still: list[FairValueGap] = []
        for g in self.active:
            span = g.zone.high - g.zone.low
            if g.direction is Direction.BULL:
                depth = g.zone.high - bar.low
                broken = bar.close < g.zone.low
            else:
                depth = bar.high - g.zone.low
                broken = bar.close > g.zone.high
            if span > 0 and depth > 0:
                g.fill_pct = max(g.fill_pct, min(1.0, depth / span))
            if broken:
                g.invalidated_index = i
                out.invalidated.append(g)
            else:
                still.append(g)
        self.active = still

        # 2. A new gap formed by bars i-2, i-1, i.
        if i >= 2 and atr is not None and atr > 0:
            first, third = self._bars[i - 2], bar
            gap: Optional[FairValueGap] = None
            if third.low > first.high and third.low - first.high >= self.min_atr_mult * atr:
                gap = FairValueGap(Direction.BULL, Zone(first.high, third.low), i, bar.ts,
                                   bar.close_time, (third.low - first.high) / atr)
            elif third.high < first.low and first.low - third.high >= self.min_atr_mult * atr:
                gap = FairValueGap(Direction.BEAR, Zone(third.high, first.low), i, bar.ts,
                                   bar.close_time, (first.low - third.high) / atr)
            if gap is not None:
                self.active.append(gap)
                self.history.append(gap)
                out.new.append(gap)
                for j in (i - 1, i):
                    d = self._displacement(j, gap, i, bar.close_time)
                    if d is not None:
                        self.displacements.append(d)
                        out.displacements.append(d)
        return out

    def _displacement(self, j: int, gap: FairValueGap, i: int,
                      confirmed_at: datetime) -> Optional[Displacement]:
        b = self._bars[j]
        atr = self._atr[j]
        if atr is None or atr <= 0 or b.range <= 0:
            return None
        if gap.direction is Direction.BULL and not b.is_bullish:
            return None
        if gap.direction is Direction.BEAR and not b.is_bearish:
            return None
        body_atr = b.body / atr
        ratio = b.body / b.range
        if body_atr >= self.disp_atr_mult and ratio >= self.disp_body_ratio:
            return Displacement(gap.direction, j, b.ts, i, confirmed_at, body_atr, ratio, gap.index)
        return None


__all__ = ["Displacement", "FairValueGap", "FvgTracker", "FvgUpdate"]
