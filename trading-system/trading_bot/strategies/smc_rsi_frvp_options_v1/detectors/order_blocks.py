"""Order blocks (spec §3.7), per the spec rather than the shared engine.

The shared ``calculate_smc`` picks the last opposite candle with body
>= 0.3 x its own (rolling) ATR and uses ``[low, body-top]`` as the zone.
The spec asks for the last opposite-bodied candle before the displacement
leg, with a ``full`` or ``body`` zone. Changing the engine would change
``rsi_smc_options_buyer`` and the chart overlay, so the spec rule lives here
(DESIGN.md §2, owner decision D1).

Bullish OB, created on the close of a qualifying bullish structure event at
bar ``b`` (15m: BOS only; 5m: BOS or CHoCH, per the spec):

* the leg runs from the broken swing high (exclusive) to ``b``; its origin
  is the leg's lowest low (:class:`StructureEvent.origin_index`);
* the OB candle is the last bearish-bodied candle at or before the origin,
  searching back no further than the swing (exclusive);
* if ``require_displacement``, the leg ``[origin, b]`` must contain a
  bullish displacement candle confirmed by ``b``;
* zone ``full`` = ``[low, high]``, ``body`` = ``[min(o, c), max(o, c)]``.

Lifecycle, evaluated on every later bar:

* invalidated by the first CLOSE below the zone low (bearish: above high);
* expired once ``bar_index - ob.index > max_age``;
* a touch is a bar after ``b`` whose low reaches the zone high (bearish: whose
  high reaches the zone low). ``fresh`` means no touch before the bar being
  evaluated; with ``fresh_only`` only the first touch is tradable.

Bearish OBs mirror all of this.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Sequence

from ..types import Bar, Direction, StructureEvent, StructureKind, Zone
from .fvg import Displacement


@dataclass
class OrderBlock:
    direction: Direction
    zone: Zone
    index: int
    ts: datetime
    confirmed_index: int
    confirmed_at: datetime
    event_kind: StructureKind
    touches: int = 0
    first_touch_index: Optional[int] = None
    invalidated_index: Optional[int] = None
    expired_index: Optional[int] = None

    @property
    def active(self) -> bool:
        return self.invalidated_index is None and self.expired_index is None

    @property
    def fresh(self) -> bool:
        return self.touches == 0


@dataclass
class OrderBlockUpdate:
    new: list[OrderBlock] = field(default_factory=list)
    touched: list[OrderBlock] = field(default_factory=list)
    invalidated: list[OrderBlock] = field(default_factory=list)
    expired: list[OrderBlock] = field(default_factory=list)


class OrderBlockTracker:
    def __init__(self, zone_mode: str, max_age_bars: int, require_displacement: bool,
                 event_kinds: Sequence[StructureKind]) -> None:
        if zone_mode not in ("full", "body"):
            raise ValueError("zone_mode must be 'full' or 'body'")
        self.zone_mode = zone_mode
        self.max_age_bars = max_age_bars
        self.require_displacement = require_displacement
        self.event_kinds = tuple(event_kinds)
        self.active: list[OrderBlock] = []
        self.history: list[OrderBlock] = []

    def update(self, i: int, bar: Bar, bars: Sequence[Bar], event: Optional[StructureEvent],
               displacements: Sequence[Displacement]) -> OrderBlockUpdate:
        """``bars`` is the timeframe's full closed-bar list through ``i``."""
        out = OrderBlockUpdate()

        still: list[OrderBlock] = []
        for ob in self.active:
            if i - ob.index > self.max_age_bars:
                ob.expired_index = i
                out.expired.append(ob)
                continue
            if ob.direction is Direction.BULL:
                touched = bar.low <= ob.zone.high
                broken = bar.close < ob.zone.low
            else:
                touched = bar.high >= ob.zone.low
                broken = bar.close > ob.zone.high
            if touched:
                ob.touches += 1
                if ob.first_touch_index is None:
                    ob.first_touch_index = i
                out.touched.append(ob)
            if broken:
                ob.invalidated_index = i
                out.invalidated.append(ob)
                continue
            still.append(ob)
        self.active = still

        if event is not None and event.kind in self.event_kinds:
            ob_new = self._create(event, bars, displacements)
            if ob_new is not None:
                self.active.append(ob_new)
                self.history.append(ob_new)
                out.new.append(ob_new)
        return out

    def _create(self, ev: StructureEvent, bars: Sequence[Bar],
                displacements: Sequence[Displacement]) -> Optional[OrderBlock]:
        if self.require_displacement and not any(
                d.direction is ev.direction and ev.origin_index <= d.index <= ev.index
                and d.confirmed_index <= ev.index for d in displacements):
            return None
        for k in range(ev.origin_index, ev.swing_index, -1):
            c = bars[k]
            opposite = c.is_bearish if ev.direction is Direction.BULL else c.is_bullish
            if opposite:
                zone = (Zone(c.low, c.high) if self.zone_mode == "full"
                        else Zone(min(c.open, c.close), max(c.open, c.close)))
                if k == ev.index:
                    return None   # the break bar itself cannot be its own OB
                return OrderBlock(ev.direction, zone, k, c.ts, ev.index, ev.confirmed_at, ev.kind)
        return None


__all__ = ["OrderBlock", "OrderBlockTracker", "OrderBlockUpdate"]
