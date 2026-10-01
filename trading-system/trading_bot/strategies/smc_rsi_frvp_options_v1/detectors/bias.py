"""HTF bias (spec §3.3) and the dealing range (spec §3.4).

Bias, read on a 15m bar ``i`` from the 15m structure tracker:

* no event yet, or the latest event is ``bias_max_age_bars_15m`` or more bars
  old -> NEUTRAL;
* latest event a BOS -> its direction (this covers "a CHoCH followed by a
  BOS": the BOS is then the latest event);
* latest event a CHoCH -> NEUTRAL when ``require_bos_after_choch``, else its
  direction;
* with ``use_1h_filter``, a 1H trend OPPOSITE to that bias -> NEUTRAL. A 1H
  trend that is still NEUTRAL (or unknown) is not opposite and passes.

Dealing range: the 15m leg that produced the latest BOS (CHoCH does not form
one). Bullish: low = the leg origin (lowest low between the broken swing and
the BOS bar), high = the highest high from the origin onward. The high keeps
extending while the leg runs and FREEZES at the first 15m swing high
confirmed after the BOS -- that swing is the top of the leg. Bearish mirrors.
``EQ = low + 0.5 x (high - low)``. Discount is below EQ, premium above. The
OTE band (62-79 % retracement of the leg) is a tag only.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Sequence

from ..types import Bar, Direction, Pivot, StructureEvent, StructureKind, Trend, Zone


@dataclass
class DealingRange:
    direction: Direction
    event_index: int
    origin_index: int
    origin_ts: datetime
    known_at: datetime
    low: float
    high: float
    frozen: bool = False

    @property
    def eq(self) -> float:
        return self.low + 0.5 * (self.high - self.low)

    def is_discount(self, price: float) -> bool:
        return price < self.eq

    def is_premium(self, price: float) -> bool:
        return price > self.eq

    def ote(self, ote_low: float, ote_high: float) -> Zone:
        span = self.high - self.low
        if self.direction is Direction.BULL:
            return Zone(self.high - ote_high * span, self.high - ote_low * span)
        return Zone(self.low + ote_low * span, self.low + ote_high * span)


class DealingRangeTracker:
    def __init__(self) -> None:
        self.current: Optional[DealingRange] = None

    def update(self, i: int, bar: Bar, bars: Sequence[Bar], event: Optional[StructureEvent],
               new_pivots: Sequence[Pivot]) -> Optional[DealingRange]:
        """Returns the range if a NEW one formed on this bar."""
        r = self.current
        if r is not None and not r.frozen:
            if r.direction is Direction.BULL:
                r.high = max(r.high, bar.high)
            else:
                r.low = min(r.low, bar.low)
            for p in new_pivots:
                if p.index >= r.event_index and p.is_high == (r.direction is Direction.BULL):
                    r.frozen = True
                    break
        if event is not None and event.kind is StructureKind.BOS:
            leg = bars[event.origin_index:i + 1]
            if event.direction is Direction.BULL:
                low, high = event.origin_price, max(b.high for b in leg)
            else:
                low, high = min(b.low for b in leg), event.origin_price
            self.current = DealingRange(event.direction, i, event.origin_index, event.origin_ts,
                                        event.confirmed_at, low, high)
            return self.current
        return None


def bias(events: Sequence[StructureEvent], i: int, max_age_bars: int,
         require_bos_after_choch: bool, h1_trend: Optional[Trend], use_1h_filter: bool) -> Trend:
    if not events:
        return Trend.NEUTRAL
    e = events[-1]
    if i - e.index >= max_age_bars:
        return Trend.NEUTRAL
    if e.kind is StructureKind.CHOCH and require_bos_after_choch:
        return Trend.NEUTRAL
    out = Trend.BULLISH if e.direction is Direction.BULL else Trend.BEARISH
    if use_1h_filter and h1_trend is not None:
        if (out is Trend.BULLISH and h1_trend is Trend.BEARISH) or \
           (out is Trend.BEARISH and h1_trend is Trend.BULLISH):
            return Trend.NEUTRAL
    return out


__all__ = ["DealingRange", "DealingRangeTracker", "bias"]
