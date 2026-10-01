"""Fixed range volume profile (spec §3.9), computed here from scratch.

Owner decision (2026-10-01): smc1's FRVP must NOT use the shared
``shared.indicators.volume_profile`` function. That function silently weights
bars by their candle range when volume is zero (DESIGN.md §18.6), which makes
a profile of volume-less data look real. This module has no such path.

Definition:

* **Bins** are an exact ``bin_points`` grid aligned to multiples of
  ``bin_points``: from ``floor(low / bin_points) x bin_points`` to
  ``ceil(high / bin_points) x bin_points``. Every bin is exactly
  ``bin_points`` wide.
* **Distribution.** Each bar's volume is spread uniformly over its
  ``[low, high]``: a bin receives ``volume x overlap / (high - low)``. A bar
  with ``high == low`` puts all of its volume in the bin containing that price
  (the upper bin when the price sits on an interior edge, the top bin when it
  is the range's top edge).
* **Volume is never invented.** A bar with zero volume contributes nothing
  and is COUNTED (``Profile.zero_volume_bars``). If every bar has zero volume,
  :class:`ZeroVolumeError` is raised -- there is no profile to build.
* **POC** is the bin with the most volume (on an exact tie, the lowest-priced
  of the tied bins); its price is the bin's midpoint.
* **Value area** starts at the POC bin and adds one adjacent bin at a time,
  the fuller of the next bin above and the next bin below (above on a tie),
  until it holds ``value_area_pct`` of the total. VAL / VAH are its outer
  edges.
* **HVN / LVN.** Bin volumes are smoothed with a centred ``smooth_bins``
  moving average (edge bins average the neighbours that exist). An HVN is a
  local maximum of the smoothed series (``> left`` and ``>= right``) with
  smoothed volume ``>= hvn_mult x mean(smoothed)``; an LVN is an INTERIOR
  local minimum (``< left`` and ``<= right``) with smoothed volume
  ``<= lvn_mult x mean(smoothed)``. Edge bins are never LVNs -- a profile's
  thin tails are not a gap inside it.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime
from typing import Sequence

from ..types import Bar, Zone


class ZeroVolumeError(ValueError):
    """The range has no traded volume; a profile would be fabricated."""


@dataclass(frozen=True)
class Profile:
    anchor: str
    start: datetime
    end: datetime
    bars: int
    zero_volume_bars: int
    poc: float
    vah: float
    val: float
    bin_width: float
    bins: tuple[Zone, ...]
    volumes: tuple[float, ...]
    smoothed: tuple[float, ...]
    hvn: tuple[Zone, ...]
    lvn: tuple[Zone, ...]
    total_volume: float

    def in_lvn(self, price: float) -> bool:
        return any(z.contains(price) for z in self.lvn)

    def levels(self) -> dict[str, float]:
        """Every price this profile offers as a confluence or target level."""
        out = {"POC": self.poc, "VAH": self.vah, "VAL": self.val}
        for k, z in enumerate(self.hvn):
            out[f"HVN{k}"] = z.mid
        return out


def _smooth(values: Sequence[float], width: int) -> list[float]:
    half = width // 2
    out: list[float] = []
    for k in range(len(values)):
        lo, hi = max(0, k - half), min(len(values), k + half + 1)
        window = values[lo:hi]
        out.append(sum(window) / len(window))
    return out


def _distribute(bars: Sequence[Bar], base: float, step: float, n: int) -> list[float]:
    vols = [0.0] * n
    for b in bars:
        if b.volume <= 0:
            continue
        if b.high <= b.low:
            k = min(n - 1, max(0, int(math.floor((b.low - base) / step))))
            vols[k] += b.volume
            continue
        first = max(0, int(math.floor((b.low - base) / step)))
        last = min(n - 1, int(math.floor((b.high - base) / step)))
        span = b.high - b.low
        for k in range(first, last + 1):
            lo_edge = base + k * step
            overlap = min(b.high, lo_edge + step) - max(b.low, lo_edge)
            if overlap > 0:
                vols[k] += b.volume * overlap / span
    return vols


def _value_area(vols: Sequence[float], poc: int, pct: float) -> tuple[int, int]:
    target = pct * sum(vols)
    lo = hi = poc
    acc = vols[poc]
    while acc < target and (lo > 0 or hi < len(vols) - 1):
        up = vols[hi + 1] if hi < len(vols) - 1 else -1.0
        down = vols[lo - 1] if lo > 0 else -1.0
        if up >= down:
            hi += 1
            acc += up
        else:
            lo -= 1
            acc += down
    return lo, hi


def build_profile(bars: Sequence[Bar], anchor: str, bin_points: float, value_area_pct: float,
                  hvn_mult: float, lvn_mult: float, smooth_bins: int) -> Profile:
    """Profile of ``bars`` (normally 1m futures bars). Raises
    :class:`ZeroVolumeError` if they carry no volume, ``ValueError`` if empty."""
    if not bars:
        raise ValueError(f"{anchor}: no bars to profile")
    zero = sum(1 for b in bars if b.volume <= 0)
    total = sum(b.volume for b in bars)
    if total <= 0:
        raise ZeroVolumeError(f"{anchor}: all {len(bars)} bars carry zero volume")
    lo = min(b.low for b in bars)
    hi = max(b.high for b in bars)
    base = math.floor(lo / bin_points) * bin_points
    top = math.ceil(hi / bin_points) * bin_points
    n = max(1, int(round((top - base) / bin_points)))
    vols = _distribute(bars, base, bin_points, n)
    zones = tuple(Zone(base + k * bin_points, base + (k + 1) * bin_points) for k in range(n))

    peak = max(vols)
    poc_k = vols.index(peak)
    va_lo, va_hi = _value_area(vols, poc_k, value_area_pct)

    sm = _smooth(vols, smooth_bins)
    mean = sum(sm) / len(sm)
    hvn: list[Zone] = []
    lvn: list[Zone] = []
    for k in range(n):
        left = sm[k - 1] if k > 0 else float("-inf")
        right = sm[k + 1] if k < n - 1 else float("-inf")
        if sm[k] > left and sm[k] >= right and sm[k] >= hvn_mult * mean:
            hvn.append(zones[k])
        if 0 < k < n - 1 and sm[k] < sm[k - 1] and sm[k] <= sm[k + 1] and sm[k] <= lvn_mult * mean:
            lvn.append(zones[k])
    return Profile(
        anchor=anchor, start=bars[0].ts, end=bars[-1].close_time, bars=len(bars),
        zero_volume_bars=zero, poc=zones[poc_k].mid, vah=zones[va_hi].high, val=zones[va_lo].low,
        bin_width=bin_points, bins=zones, volumes=tuple(vols), smoothed=tuple(sm),
        hvn=tuple(hvn), lvn=tuple(lvn), total_volume=float(sum(vols)),
    )


class FrvpTracker:
    """Keeps the 1m buffer and the two profiles the spec uses.

    * ``previous_day`` -- rebuilt on the first 1m bar of each new session from
      the previous session's bars.
    * ``impulse_leg`` -- rebuilt by :meth:`on_dealing_range` when a new 15m
      dealing range forms, over the 1m bars from the leg origin's start to the
      range's confirmation time.

    Only CLOSED 1m bars that ended by the requested time are used, so a profile
    never contains a minute that had not finished when it was built. A
    zero-volume range leaves that profile ``None`` and records why in
    :attr:`last_error` (never a synthetic profile).
    """

    def __init__(self, bin_points: float, value_area_pct: float, hvn_mult: float,
                 lvn_mult: float, smooth_bins: int, history_sessions: int) -> None:
        self.params = (bin_points, value_area_pct, hvn_mult, lvn_mult, smooth_bins)
        self.history_sessions = history_sessions
        self._bars: list[Bar] = []
        self.previous_day: Profile | None = None
        self.impulse_leg: Profile | None = None
        self.last_error: str | None = None

    def _build(self, bars: Sequence[Bar], anchor: str) -> Profile | None:
        bp, va, hm, lm, sb = self.params
        try:
            return build_profile(bars, anchor, bp, va, hm, lm, sb)
        except ValueError as exc:   # ZeroVolumeError is a ValueError
            self.last_error = str(exc)
            return None

    def update(self, bar: Bar) -> Profile | None:
        """Add one closed 1m bar. Returns the new previous-day profile when this
        bar opens a new session, else None."""
        built: Profile | None = None
        if self._bars and bar.ts.date() != self._bars[-1].ts.date():
            prev_day = self._bars[-1].ts.date()
            prev = [b for b in self._bars if b.ts.date() == prev_day]
            self.previous_day = built = self._build(prev, "previous_day")
            days = sorted({b.ts.date() for b in self._bars})
            keep = set(days[-(self.history_sessions - 1):]) if self.history_sessions > 1 else set()
            self._bars = [b for b in self._bars if b.ts.date() in keep]
        self._bars.append(bar)
        return built

    def on_dealing_range(self, origin_start: datetime, known_at: datetime) -> Profile | None:
        bars = [b for b in self._bars if b.ts >= origin_start and b.close_time <= known_at]
        if not bars:
            self.last_error = (f"impulse_leg: no 1m bars between {origin_start} and {known_at} "
                               f"(buffer holds {self.history_sessions} sessions)")
            self.impulse_leg = None
            return None
        self.impulse_leg = self._build(bars, "impulse_leg")
        return self.impulse_leg

    def session_to_date(self, now: datetime) -> Profile | None:
        if not self._bars:
            return None
        day = self._bars[-1].ts.date()
        bars = [b for b in self._bars if b.ts.date() == day and b.close_time <= now]
        return self._build(bars, "session_to_date") if bars else None


__all__ = ["FrvpTracker", "Profile", "ZeroVolumeError", "build_profile"]
