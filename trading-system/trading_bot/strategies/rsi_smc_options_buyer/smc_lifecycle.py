"""SMC object lifecycle: CANDIDATE -> CONFIRMED -> INVALIDATED.

The problem this solves
-----------------------
``shared/indicators/smart_money_concepts.py`` returns finished objects. An
``OrderBlock`` says where it is and whether it was ever mitigated; it does not
say WHEN it became knowable. Consuming such an object at its ``bar_index`` is
look-ahead bias, because the engine only discovers it some bars later, when
the structure break that defines it occurs.

Deleting those objects would be the wrong fix -- they are exactly what a chart
should draw and what research should study. The right fix is to recover the
TIMESTAMPS and let each consumer choose its own cut-off:

* the strategy may read an object only at or after ``confirmation_index``
* the chart may draw it from ``origin_index``, labelled CANDIDATE until
  ``confirmation_index`` and CONFIRMED after

How each confirmation point is recovered
----------------------------------------
Every one of these was derived from the engine's source and then VALIDATED
against measurement (recompute on ``df[:k]`` for increasing ``k``, find the
first ``k`` at which the object appears):

``OrderBlock``
    Created inside the main loop at the bar where a structure break fires,
    scanning backwards for the source candle. So confirmation is the
    ``bar_index`` of the FIRST structure event, in the same direction, after
    the block's own origin bar. Validated: derived == measured on every
    sampled block (e.g. OB_BULL_310 origin 310 -> confirmed 313;
    OB_BULL_356 -> 357; OB_BEAR_550 -> 551).

``FairValueGap``
    Printed by the third of the three candles that form it, so confirmation
    IS ``bar_index``. Validated: lag 0.

``LiquidityPool`` (EQH/EQL)
    Built from fractal pivots via ``detect_pivots(length=internal)``, which
    needs ``length`` bars of hindsight, and the EQH/EQL builder applies none
    of the confirmation delay the BOS/CHoCH loop applies. Confirmation is
    ``max(bar_indices) + effective_internal_len``. Validated: lag 5 at
    internal=5, lag 2 at effective internal=2.

Swing pivots
    A pivot at ``p`` is a strict extremum over ``[p-L, p+L]``, so it is
    knowable at ``p + L``.

``SMCStructureEvent`` (BOS / CHoCH)
    Already carries the bar it fired on, and the engine defers pivot
    consumption by ``conf_idx = i - effective_swing_len``. Origin ==
    confirmation; these are causal as emitted.

Invalidation and mitigation
---------------------------
``FairValueGap.mitigated_index`` is recorded by the engine and is the first
bar that filled the gap, so it is directly usable. ``OrderBlock.mitigated_index``
likewise. ``OrderBlock.invalidated`` is a frame-wide BOOLEAN with no index, so
the invalidation bar is re-derived here with the engine's own rule (a close
beyond the far side of the block) -- recomputed rather than guessed, and only
ever used to answer "was this invalidated as of bar i".
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np

logger = logging.getLogger(__name__)


class SmcState(str, Enum):
    """Where an object sits in its life at a given bar."""

    CANDIDATE = "CANDIDATE"      # exists in hindsight, not yet knowable
    CONFIRMED = "CONFIRMED"      # knowable and live
    MITIGATED = "MITIGATED"      # price returned and filled it
    INVALIDATED = "INVALIDATED"  # price closed through it; the idea is dead


#: Object kinds tracked by this module.
KIND_ORDER_BLOCK = "order_block"
KIND_FVG = "fvg"
KIND_LIQUIDITY_POOL = "liquidity_pool"
KIND_SWING = "swing"
KIND_STRUCTURE_EVENT = "structure_event"


@dataclass(frozen=True)
class SmcObject:
    """One SMC structure with its full, explicit timeline.

    Indices are POSITIONAL into the frame the engine was run on. Times are the
    matching index labels, carried so a chart or a stored record does not have
    to re-derive them.

    ``confirmation_index`` is the contract: **no strategy feature may read
    this object at a bar before it.**
    """

    kind: str
    object_id: str
    is_bullish: bool

    origin_index: int
    confirmation_index: int

    origin_time: Any = None
    confirmation_time: Any = None

    mitigation_index: Optional[int] = None
    mitigation_time: Any = None
    invalidation_index: Optional[int] = None
    invalidation_time: Any = None

    #: Zone bounds for blocks and gaps; single price for pools and swings.
    top: Optional[float] = None
    bottom: Optional[float] = None
    price: Optional[float] = None

    extra: Dict[str, Any] = field(default_factory=dict)

    @property
    def confirmation_lag(self) -> int:
        """Bars between the object existing and it becoming knowable."""
        return int(self.confirmation_index) - int(self.origin_index)

    def state_at(self, index: int) -> SmcState:
        """This object's state as of bar ``index``, using only bars <= index."""
        if index < self.origin_index:
            return SmcState.CANDIDATE
        if index < self.confirmation_index:
            return SmcState.CANDIDATE
        if self.invalidation_index is not None and index >= self.invalidation_index:
            return SmcState.INVALIDATED
        if self.mitigation_index is not None and index >= self.mitigation_index:
            return SmcState.MITIGATED
        return SmcState.CONFIRMED

    def usable_at(self, index: int) -> bool:
        """Whether the STRATEGY may read this object at bar ``index``.

        Confirmed, not yet invalidated, not yet mitigated.
        """
        return self.state_at(index) is SmcState.CONFIRMED

    def active_mask(self, n: int) -> np.ndarray:
        """Per-bar mask of :meth:`usable_at` over a frame of ``n`` bars."""
        positions = np.arange(n)
        live = positions >= int(self.confirmation_index)
        if self.invalidation_index is not None:
            live &= positions < int(self.invalidation_index)
        if self.mitigation_index is not None:
            live &= positions < int(self.mitigation_index)
        return live

    def to_record(self) -> Dict[str, Any]:
        """Flat dict for a chart payload, a research table or a log line."""
        return {
            "kind": self.kind,
            "id": self.object_id,
            "is_bullish": self.is_bullish,
            "origin_index": int(self.origin_index),
            "origin_time": self.origin_time,
            "confirmation_index": int(self.confirmation_index),
            "confirmation_time": self.confirmation_time,
            "confirmation_lag": self.confirmation_lag,
            "mitigation_index": self.mitigation_index,
            "mitigation_time": self.mitigation_time,
            "invalidation_index": self.invalidation_index,
            "invalidation_time": self.invalidation_time,
            "top": self.top,
            "bottom": self.bottom,
            "price": self.price,
        }


def _time_at(timestamps: Sequence[Any], index: Optional[int]) -> Any:
    if index is None:
        return None
    index = int(index)
    if 0 <= index < len(timestamps):
        return timestamps[index]
    return None


def derive_structure_events(analysis, timestamps: Sequence[Any]) -> List[SmcObject]:
    """BOS / CHoCH. Origin IS confirmation -- these are causal as emitted."""
    out: List[SmcObject] = []
    for position, event in enumerate(getattr(analysis, "structure_events", []) or []):
        index = int(event.bar_index)
        out.append(SmcObject(
            kind=KIND_STRUCTURE_EVENT,
            object_id=f"{event.event_type.value}_{'BULL' if event.is_bullish else 'BEAR'}_{index}_{position}",
            is_bullish=bool(event.is_bullish),
            origin_index=index,
            confirmation_index=index,
            origin_time=_time_at(timestamps, index),
            confirmation_time=_time_at(timestamps, index),
            price=float(event.broken_level),
            extra={"event_type": event.event_type.value,
                   "is_internal": bool(event.is_internal)},
        ))
    return out


def derive_order_blocks(analysis, opens: np.ndarray, closes: np.ndarray,
                        timestamps: Sequence[Any]) -> List[SmcObject]:
    """Order Blocks, with the confirmation bar recovered from the structure
    event that created each one.

    The engine appends a block inside the same loop iteration as the structure
    break that produced it, scanning backwards for the source candle. So the
    confirmation bar is the first structure event, in the same direction,
    strictly after the block's origin bar. Validated against measurement --
    see the module docstring.

    Invalidation is re-derived with the engine's own rule (a close beyond the
    far side of the block), because ``OrderBlock.invalidated`` carries no
    index.
    """
    events = sorted(
        (e for e in (getattr(analysis, "structure_events", []) or [])),
        key=lambda e: int(e.bar_index),
    )
    bull_events = [int(e.bar_index) for e in events if e.is_bullish]
    bear_events = [int(e.bar_index) for e in events if not e.is_bullish]

    blocks = list(getattr(analysis, "active_bullish_obs", []) or []) + \
        list(getattr(analysis, "active_bearish_obs", []) or [])

    n = closes.shape[0]
    out: List[SmcObject] = []
    for block in blocks:
        origin = int(block.bar_index)
        pool = bull_events if block.is_bullish else bear_events
        later = [index for index in pool if index > origin]
        if not later:
            # No structure event ever confirmed it within this frame: it is
            # a candidate forever, so it can never be used by the strategy.
            confirmation = n
        else:
            confirmation = min(later)

        invalidation = None
        if getattr(block, "invalidated", False) and confirmation < n:
            # Engine rule: bullish block dies on a close below its bottom,
            # bearish on a close above its top.
            after = np.arange(confirmation, n)
            if block.is_bullish:
                hits = after[closes[confirmation:] < float(block.bottom)]
            else:
                hits = after[closes[confirmation:] > float(block.top)]
            invalidation = int(hits[0]) if hits.size else None

        mitigation = block.mitigated_index if block.mitigated else None
        if mitigation is not None and int(mitigation) < confirmation:
            # Filled before anyone could have known it existed: never usable.
            mitigation = confirmation

        out.append(SmcObject(
            kind=KIND_ORDER_BLOCK,
            object_id=str(block.id),
            is_bullish=bool(block.is_bullish),
            origin_index=origin,
            confirmation_index=int(confirmation),
            origin_time=_time_at(timestamps, origin),
            confirmation_time=_time_at(timestamps, confirmation),
            mitigation_index=int(mitigation) if mitigation is not None else None,
            mitigation_time=_time_at(timestamps, mitigation),
            invalidation_index=invalidation,
            invalidation_time=_time_at(timestamps, invalidation),
            top=float(block.top),
            bottom=float(block.bottom),
            price=float(block.midpoint),
            extra={"volume": float(getattr(block, "volume", 0.0))},
        ))
    return out


def derive_fvgs(analysis, timestamps: Sequence[Any]) -> List[SmcObject]:
    """Fair Value Gaps. Confirmation == origin (measured lag 0)."""
    gaps = list(getattr(analysis, "active_bullish_fvgs", []) or []) + \
        list(getattr(analysis, "active_bearish_fvgs", []) or [])
    out: List[SmcObject] = []
    for gap in gaps:
        origin = int(gap.bar_index)
        mitigation = gap.mitigated_index if gap.mitigated else None
        out.append(SmcObject(
            kind=KIND_FVG,
            object_id=str(gap.id),
            is_bullish=bool(gap.is_bullish),
            origin_index=origin,
            confirmation_index=origin,
            origin_time=_time_at(timestamps, origin),
            confirmation_time=_time_at(timestamps, origin),
            mitigation_index=int(mitigation) if mitigation is not None else None,
            mitigation_time=_time_at(timestamps, mitigation),
            top=float(gap.top),
            bottom=float(gap.bottom),
            price=float((gap.top + gap.bottom) / 2.0),
        ))
    return out


def derive_liquidity_pools(analysis, timestamps: Sequence[Any],
                           availability_delay: int) -> List[SmcObject]:
    """EQH / EQL pools, delayed by the measured pivot-detection lag."""
    out: List[SmcObject] = []
    for pool in (getattr(analysis, "active_liquidity_pools", []) or []):
        indices = [int(i) for i in (pool.bar_indices or [])]
        if not indices:
            continue
        origin = max(indices)
        confirmation = origin + int(availability_delay)
        out.append(SmcObject(
            kind=KIND_LIQUIDITY_POOL,
            object_id=str(pool.id),
            is_bullish=not bool(pool.is_high),  # a low pool is swept for longs
            origin_index=origin,
            confirmation_index=confirmation,
            origin_time=_time_at(timestamps, origin),
            confirmation_time=_time_at(timestamps, confirmation),
            price=float(pool.price),
            extra={"is_high": bool(pool.is_high),
                   "tolerance": float(pool.tolerance),
                   "bar_indices": indices},
        ))
    return out


def derive_swings(highs: np.ndarray, lows: np.ndarray, timestamps: Sequence[Any],
                  swing_length: int) -> List[SmcObject]:
    """Swing highs and lows, confirmed ``swing_length`` bars after the pivot.

    Reuses the engine's own ``detect_pivots`` so there is one pivot definition
    in this repository, then applies the delay that its forward-looking window
    implies.
    """
    from shared.indicators.smart_money_concepts import detect_pivots

    pivot_highs, pivot_lows = detect_pivots(highs, lows, length=int(swing_length))
    out: List[SmcObject] = []
    for is_high, mask, prices in ((True, pivot_highs, highs), (False, pivot_lows, lows)):
        for origin in np.flatnonzero(mask):
            origin = int(origin)
            out.append(SmcObject(
                kind=KIND_SWING,
                object_id=f"SWING_{'HIGH' if is_high else 'LOW'}_{origin}",
                is_bullish=not is_high,
                origin_index=origin,
                confirmation_index=origin + int(swing_length),
                origin_time=_time_at(timestamps, origin),
                confirmation_time=_time_at(timestamps, origin + int(swing_length)),
                price=float(prices[origin]),
                extra={"is_high": is_high},
            ))
    return out


def zone_interaction_mask(objects: Sequence[SmcObject], highs: np.ndarray,
                          lows: np.ndarray, n: int, bullish: bool) -> np.ndarray:
    """Per-bar "this bar's range touched a USABLE zone of this direction".

    ``usable`` means confirmed, not invalidated and not mitigated as of that
    bar -- so the mask is causal by construction, whatever the object is.
    """
    out = np.zeros(n, dtype=bool)
    for obj in objects:
        if bool(obj.is_bullish) != bool(bullish):
            continue
        if obj.top is None or obj.bottom is None:
            continue
        touched = (lows <= float(obj.top)) & (highs >= float(obj.bottom))
        out |= obj.active_mask(n) & touched
    return out


def nearest_price_mask(objects: Sequence[SmcObject], reference: np.ndarray,
                       n: int, is_high: bool) -> Tuple[np.ndarray, np.ndarray]:
    """Nearest USABLE object price per bar, and its distance.

    Used for liquidity pools, where the object is a single level rather than a
    zone. NaN where nothing is usable yet.
    """
    best = np.full(n, np.nan, dtype=float)
    best_distance = np.full(n, np.inf, dtype=float)
    for obj in objects:
        if obj.price is None:
            continue
        if bool(obj.extra.get("is_high", False)) != bool(is_high):
            continue
        price = float(obj.price)
        if not np.isfinite(price) or price <= 0:
            continue
        live = obj.active_mask(n)
        distance = np.abs(reference - price)
        better = live & (distance < best_distance)
        best_distance = np.where(better, distance, best_distance)
        best = np.where(better, price, best)
    return best, best_distance


def lifecycle_table(objects: Sequence[SmcObject]) -> List[Dict[str, Any]]:
    """Every object as a flat record, for the chart/research surface."""
    return [obj.to_record() for obj in objects]


__all__ = [
    "SmcState",
    "SmcObject",
    "KIND_ORDER_BLOCK",
    "KIND_FVG",
    "KIND_LIQUIDITY_POOL",
    "KIND_SWING",
    "KIND_STRUCTURE_EVENT",
    "derive_structure_events",
    "derive_order_blocks",
    "derive_fvgs",
    "derive_liquidity_pools",
    "derive_swings",
    "zone_interaction_mask",
    "nearest_price_mask",
    "lifecycle_table",
]
