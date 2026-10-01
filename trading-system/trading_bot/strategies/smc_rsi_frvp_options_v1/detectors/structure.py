"""Market structure: BOS and CHoCH (spec §3.2), one tracker per timeframe.

Rules, applied on each bar's CLOSE:

* The tracker holds the most recent CONFIRMED swing high and swing low
  (:class:`PivotTracker`). A newly confirmed pivot replaces the previous one
  of its side, broken or not.
* Bullish break: ``close > swing_high``. If the trend was BEARISH it is a
  CHoCH; otherwise (BULLISH or NEUTRAL) it is a BOS -- "neutral establishes
  bullish" is a BOS per the spec. The trend becomes BULLISH and that swing
  can never be broken again. Bearish breaks mirror this.
* A wick through a swing with a close back inside is NOT a break.
* In a bearish trend the most recent confirmed swing high is the lower high
  the spec's CHoCH refers to.

The leg origin of a bullish break is the lowest low over
``(swing_index, break_index]``; of a bearish break the highest high. Both are
known on the break bar.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from ..types import Bar, Direction, Pivot, StructureEvent, StructureKind, Trend
from .pivots import PivotTracker


@dataclass
class StructureUpdate:
    index: int
    pivots: list[Pivot] = field(default_factory=list)
    event: Optional[StructureEvent] = None


class StructureTracker:
    def __init__(self, pivot_length: int) -> None:
        self.pivots = PivotTracker(pivot_length)
        self.bars: list[Bar] = []
        self.trend = Trend.NEUTRAL
        self.swing_high: Optional[Pivot] = None
        self.swing_low: Optional[Pivot] = None
        self.events: list[StructureEvent] = []
        self.pivot_history: list[Pivot] = []

    @property
    def last_event(self) -> Optional[StructureEvent]:
        return self.events[-1] if self.events else None

    def update(self, bar: Bar) -> StructureUpdate:
        i = len(self.bars)
        self.bars.append(bar)
        out = StructureUpdate(index=i)
        for p in self.pivots.update(bar):
            out.pivots.append(p)
            self.pivot_history.append(p)
            if p.is_high:
                self.swing_high = p
            else:
                self.swing_low = p

        if self.swing_high is not None and bar.close > self.swing_high.price:
            out.event = self._break(i, bar, self.swing_high, Direction.BULL)
            self.swing_high = None
        elif self.swing_low is not None and bar.close < self.swing_low.price:
            out.event = self._break(i, bar, self.swing_low, Direction.BEAR)
            self.swing_low = None
        if out.event is not None:
            self.events.append(out.event)
        return out

    def _break(self, i: int, bar: Bar, swing: Pivot, direction: Direction) -> StructureEvent:
        opposite = Trend.BEARISH if direction is Direction.BULL else Trend.BULLISH
        kind = StructureKind.CHOCH if self.trend is opposite else StructureKind.BOS
        leg = range(swing.index + 1, i + 1)
        if direction is Direction.BULL:
            o = min(leg, key=lambda k: (self.bars[k].low, -k))
            origin_price = self.bars[o].low
            self.trend = Trend.BULLISH
        else:
            o = max(leg, key=lambda k: (self.bars[k].high, k))
            origin_price = self.bars[o].high
            self.trend = Trend.BEARISH
        return StructureEvent(
            kind=kind,
            direction=direction,
            index=i,
            ts=bar.ts,
            confirmed_at=bar.close_time,
            level=swing.price,
            swing_index=swing.index,
            origin_index=o,
            origin_price=origin_price,
            origin_ts=self.bars[o].ts,
        )


__all__ = ["StructureTracker", "StructureUpdate"]
