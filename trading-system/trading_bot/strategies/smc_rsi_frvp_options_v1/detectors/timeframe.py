"""One timeframe's detectors, wired in the order the spec needs them.

On each closed bar: ATR (Wilder) -> structure (pivots, BOS/CHoCH) -> FVGs and
displacements -> order blocks (which need the structure event and the
displacements confirmed by this bar) -> dealing range (15m only).

Cross-timeframe wiring (15m levels feeding 5m sweeps, 1m bars feeding FRVP,
the 1H trend feeding the bias) belongs to the replay engine of Phase B2, which
delivers bars of every timeframe in close-time order.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from ..config import Smc1Config
from ..types import Bar, Pivot, StructureEvent, StructureKind
from .atr import WilderATR
from .bias import DealingRange, DealingRangeTracker
from .fvg import FvgTracker, FvgUpdate
from .order_blocks import OrderBlockTracker, OrderBlockUpdate
from .structure import StructureTracker

#: Timeframes the spec uses, with the structure events that create OBs on each.
_OB_EVENTS: dict[str, tuple[StructureKind, ...]] = {
    "m5": (StructureKind.BOS, StructureKind.CHOCH),
    "m15": (StructureKind.BOS,),
}
_MINUTES = {"m5": 5, "m15": 15, "h1": 60}


@dataclass
class TimeframeUpdate:
    index: int
    bar: Bar
    atr: Optional[float]
    pivots: list[Pivot] = field(default_factory=list)
    event: Optional[StructureEvent] = None
    fvg: FvgUpdate = field(default_factory=FvgUpdate)
    order_blocks: Optional[OrderBlockUpdate] = None
    new_range: Optional[DealingRange] = None


class TimeframeDetectors:
    def __init__(self, timeframe: str, cfg: Smc1Config) -> None:
        if timeframe not in _MINUTES:
            raise ValueError(f"unknown timeframe {timeframe!r}")
        self.timeframe = timeframe
        self.minutes = _MINUTES[timeframe]
        self.atr = WilderATR(cfg.regime.atr_length)
        self.structure = StructureTracker(getattr(cfg.pivots, timeframe).left)
        self.fvg = FvgTracker(cfg.fvg.min_atr_mult, cfg.displacement.atr_mult,
                              cfg.displacement.body_ratio)
        self.order_blocks: Optional[OrderBlockTracker] = None
        if timeframe in _OB_EVENTS:
            max_age = (cfg.order_blocks.max_age_bars_5m if timeframe == "m5"
                       else cfg.order_blocks.max_age_bars_15m)
            self.order_blocks = OrderBlockTracker(cfg.order_blocks.zone_mode, max_age,
                                                  cfg.order_blocks.require_displacement,
                                                  _OB_EVENTS[timeframe])
        self.dealing_range: Optional[DealingRangeTracker] = (
            DealingRangeTracker() if timeframe == "m15" else None)

    @property
    def bars(self) -> list[Bar]:
        return self.structure.bars

    def update(self, bar: Bar) -> TimeframeUpdate:
        if bar.minutes != self.minutes:
            raise ValueError(f"{self.timeframe}: got a {bar.minutes}-minute bar")
        if self.bars and bar.ts <= self.bars[-1].ts:
            raise ValueError(f"{self.timeframe}: bar {bar.ts} is not after {self.bars[-1].ts}")
        atr = self.atr.update(bar)
        s = self.structure.update(bar)
        out = TimeframeUpdate(index=s.index, bar=bar, atr=atr, pivots=s.pivots, event=s.event)
        out.fvg = self.fvg.update(bar, atr)
        if self.order_blocks is not None:
            out.order_blocks = self.order_blocks.update(s.index, bar, self.bars, s.event,
                                                        self.fvg.displacements)
        if self.dealing_range is not None:
            out.new_range = self.dealing_range.update(s.index, bar, self.bars, s.event, s.pivots)
        return out


__all__ = ["TimeframeDetectors", "TimeframeUpdate"]
