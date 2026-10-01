"""Causal fractal pivots (spec §3.1), reusing the shared ``detect_pivots``.

``shared.indicators.smart_money_concepts.detect_pivots`` marks bar ``p`` as a
pivot high when ``high[p]`` is the strict, unique maximum of
``high[p-L .. p+L]``. Here it is applied to exactly that window, at the bar
``i = p + L`` that completes it, so a pivot is emitted on the close of its
L-th right-hand bar and never earlier. The spec's strict ">" against every
neighbour is the same condition.
"""

from __future__ import annotations

from collections import deque
from datetime import datetime

import numpy as np

from shared.indicators.smart_money_concepts import detect_pivots

from ..types import Bar, Pivot


class PivotTracker:
    def __init__(self, length: int) -> None:
        if length < 1:
            raise ValueError("pivot length must be >= 1")
        self.length = length
        self._window: deque[Bar] = deque(maxlen=2 * length + 1)
        self.count = 0

    def update(self, bar: Bar) -> list[Pivot]:
        """Add one closed bar; return the pivots (0, 1 or 2) confirmed by it."""
        self._window.append(bar)
        i = self.count
        self.count += 1
        if len(self._window) < 2 * self.length + 1:
            return []
        highs = np.fromiter((b.high for b in self._window), dtype=float)
        lows = np.fromiter((b.low for b in self._window), dtype=float)
        is_high, is_low = detect_pivots(highs, lows, length=self.length)
        centre = self._window[self.length]
        p = i - self.length
        confirmed_at: datetime = bar.close_time
        out: list[Pivot] = []
        if bool(is_high[self.length]):
            out.append(Pivot(p, centre.ts, centre.high, True, i, confirmed_at))
        if bool(is_low[self.length]):
            out.append(Pivot(p, centre.ts, centre.low, False, i, confirmed_at))
        return out


__all__ = ["PivotTracker"]
