"""Wilder ATR (spec §3.11), incremental.

Owner decision D6: the shared ``shared.indicators.atr.atr`` uses
``ewm(span=n)`` (alpha 2/(n+1)), which is not Wilder's smoothing (alpha
1/n). Other strategies' thresholds were measured with the shared one, so it
stays untouched and Wilder's ATR lives here.

Definition: TR[0] = high - low; TR[i] = max(high - low, |high - close[i-1]|,
|low - close[i-1]|). The first ATR is the simple mean of the first ``n``
TRs, available on bar ``n - 1``; after that
ATR[i] = (ATR[i-1] * (n - 1) + TR[i]) / n.
"""

from __future__ import annotations

from typing import Optional

from ..types import Bar


class WilderATR:
    def __init__(self, length: int) -> None:
        if length < 1:
            raise ValueError("ATR length must be >= 1")
        self.length = length
        self._prev_close: Optional[float] = None
        self._seed: list[float] = []
        self._value: Optional[float] = None
        self.count = 0

    @property
    def value(self) -> Optional[float]:
        """ATR after the last bar, or None during warm-up."""
        return self._value

    def update(self, bar: Bar) -> Optional[float]:
        if self._prev_close is None:
            tr = bar.high - bar.low
        else:
            tr = max(bar.high - bar.low,
                     abs(bar.high - self._prev_close),
                     abs(bar.low - self._prev_close))
        self._prev_close = bar.close
        self.count += 1
        if self._value is None:
            self._seed.append(tr)
            if len(self._seed) == self.length:
                self._value = sum(self._seed) / self.length
                self._seed = []
        else:
            self._value = (self._value * (self.length - 1) + tr) / self.length
        return self._value


__all__ = ["WilderATR"]
