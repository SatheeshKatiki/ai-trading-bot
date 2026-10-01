"""RSI, RSI divergence, ADX and the chop filter (spec §3.10-§3.12).

RSI and ADX reuse the shared implementations unchanged
(``shared.indicators.rsi.rsi`` -- Wilder, ``ewm(alpha=1/n)``;
``shared.indicators.adx.adx`` -- Wilder). Both are causal recursions, so
evaluating them on the history through bar ``i`` and taking the last value is
exactly the value at ``i``. They are re-run on the accumulated history each
bar (O(n) per bar): slower than an O(1) update, but it is the shared code
itself rather than a copy of it.

The recursions start at the first bar the tracker is given, so a value
depends (vanishingly, after warm-up) on where the history starts. Warm-up
values are withheld: RSI for the first ``length`` bars, ADX for the first
``2 x length`` bars.

Divergence uses only CONFIRMED 5m pivots and the RSI value at each pivot bar:
bullish when the newer of the last two pivot lows (at most ``div_max_bars``
apart) is a lower low in price and a higher low in RSI; bearish mirrors on
pivot highs. It is emitted when the newer pivot confirms.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Sequence

import pandas as pd

from shared.indicators.adx import adx as shared_adx
from shared.indicators.rsi import rsi as shared_rsi

from ..types import Bar, Direction, Pivot, StructureEvent, StructureKind


class RsiTracker:
    def __init__(self, length: int) -> None:
        self.length = length
        self._closes: list[float] = []
        self.values: list[Optional[float]] = []

    def update(self, bar: Bar) -> Optional[float]:
        self._closes.append(bar.close)
        if len(self._closes) <= self.length:
            value: Optional[float] = None
        else:
            value = float(shared_rsi(pd.Series(self._closes), window=self.length).iloc[-1])
        self.values.append(value)
        return value


@dataclass(frozen=True)
class Divergence:
    direction: Direction
    first: Pivot
    second: Pivot
    rsi_first: float
    rsi_second: float
    confirmed_index: int
    confirmed_at: datetime


class DivergenceTracker:
    def __init__(self, max_bars: int) -> None:
        self.max_bars = max_bars
        self._last_high: Optional[Pivot] = None
        self._last_low: Optional[Pivot] = None
        self.history: list[Divergence] = []

    def update(self, pivots: Sequence[Pivot], rsi_values: Sequence[Optional[float]]) -> list[Divergence]:
        out: list[Divergence] = []
        for p in pivots:
            prev = self._last_high if p.is_high else self._last_low
            if p.is_high:
                self._last_high = p
            else:
                self._last_low = p
            if prev is None or p.index - prev.index > self.max_bars:
                continue
            r1, r2 = rsi_values[prev.index], rsi_values[p.index]
            if r1 is None or r2 is None:
                continue
            if not p.is_high and p.price < prev.price and r2 > r1:
                d = Divergence(Direction.BULL, prev, p, r1, r2, p.confirmed_index, p.confirmed_at)
            elif p.is_high and p.price > prev.price and r2 < r1:
                d = Divergence(Direction.BEAR, prev, p, r1, r2, p.confirmed_index, p.confirmed_at)
            else:
                continue
            out.append(d)
            self.history.append(d)
        return out


class AdxTracker:
    def __init__(self, length: int) -> None:
        self.length = length
        self._rows: list[tuple[float, float, float]] = []
        self.values: list[Optional[float]] = []

    def update(self, bar: Bar) -> Optional[float]:
        self._rows.append((bar.high, bar.low, bar.close))
        value: Optional[float] = None
        if len(self._rows) > 2 * self.length:
            frame = pd.DataFrame(self._rows, columns=["high", "low", "close"])
            raw = shared_adx(frame, window=self.length).iloc[-1]
            value = None if pd.isna(raw) else float(raw)
        self.values.append(value)
        return value


def is_chop(adx_value: Optional[float], events: Sequence[StructureEvent], i: int,
            adx_min: float, lookback_bars: int) -> Optional[bool]:
    """Spec §3.12 on 15m bar ``i``: ADX below ``adx_min`` AND no BOS within the
    last ``lookback_bars`` bars. ``None`` while ADX is still warming up -- the
    caller decides what an unknown regime means."""
    if adx_value is None:
        return None
    recent_bos = False
    for e in reversed(events):
        if i - e.index >= lookback_bars:
            break
        if e.kind is StructureKind.BOS:
            recent_bos = True
            break
    return adx_value < adx_min and not recent_bos


__all__ = ["AdxTracker", "Divergence", "DivergenceTracker", "RsiTracker", "is_chop"]
