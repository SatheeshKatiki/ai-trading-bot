"""Value types shared by every smc1 detector.

All times are naive Asia/Kolkata wall-clock datetimes, matching every data
source in this repository. A :class:`Bar` is stamped with its START time;
its close time is ``ts + minutes``. Cross-timeframe availability is decided
on close times, never on bar positions, because 1m, 5m, 15m and 60m bars
have different index spaces.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum, IntEnum


class Direction(IntEnum):
    """+1 bullish (a CE setup), -1 bearish (a PE setup)."""

    BULL = 1
    BEAR = -1


class Trend(Enum):
    NEUTRAL = "NEUTRAL"
    BULLISH = "BULLISH"
    BEARISH = "BEARISH"


class StructureKind(Enum):
    BOS = "BOS"
    CHOCH = "CHOCH"


@dataclass(frozen=True)
class Bar:
    """One CLOSED candle. ``ts`` is the bar's start time."""

    ts: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    minutes: int

    def __post_init__(self) -> None:
        for name in ("open", "high", "low", "close", "volume"):
            value = getattr(self, name)
            if not math.isfinite(value):
                raise ValueError(f"Bar {self.ts}: {name} is not finite ({value})")
        if self.high < self.low:
            raise ValueError(f"Bar {self.ts}: high {self.high} < low {self.low}")
        if not (self.low <= self.open <= self.high and self.low <= self.close <= self.high):
            raise ValueError(f"Bar {self.ts}: open/close outside [low, high]")
        if self.volume < 0:
            raise ValueError(f"Bar {self.ts}: negative volume {self.volume}")
        if self.minutes <= 0:
            raise ValueError(f"Bar {self.ts}: minutes must be positive")

    @property
    def close_time(self) -> datetime:
        return self.ts + timedelta(minutes=self.minutes)

    @property
    def body(self) -> float:
        return abs(self.close - self.open)

    @property
    def range(self) -> float:
        return self.high - self.low

    @property
    def is_bullish(self) -> bool:
        return self.close > self.open

    @property
    def is_bearish(self) -> bool:
        return self.close < self.open


@dataclass(frozen=True)
class Pivot:
    """A fractal swing point. Usable only from ``confirmed_index`` on."""

    index: int
    ts: datetime
    price: float
    is_high: bool
    confirmed_index: int
    confirmed_at: datetime


@dataclass(frozen=True)
class StructureEvent:
    """A BOS or CHoCH, fired on the CLOSE of bar ``index``.

    ``origin_index`` / ``origin_price`` is the start of the leg that produced
    the break: for a bullish break, the lowest low between the broken swing
    high and the break bar (inclusive of the break bar). Known at ``index``.
    """

    kind: StructureKind
    direction: Direction
    index: int
    ts: datetime
    confirmed_at: datetime
    level: float
    swing_index: int
    origin_index: int
    origin_price: float
    origin_ts: datetime


@dataclass(frozen=True)
class Zone:
    """A closed price interval ``[low, high]``."""

    low: float
    high: float

    def __post_init__(self) -> None:
        if self.high < self.low:
            raise ValueError(f"Zone high {self.high} < low {self.low}")

    @property
    def mid(self) -> float:
        return (self.low + self.high) / 2.0

    def overlaps(self, other: "Zone", tolerance: float = 0.0) -> bool:
        return self.low - tolerance <= other.high and other.low <= self.high + tolerance

    def contains(self, price: float) -> bool:
        return self.low <= price <= self.high


__all__ = [
    "Bar",
    "Direction",
    "Pivot",
    "StructureEvent",
    "StructureKind",
    "Trend",
    "Zone",
]
