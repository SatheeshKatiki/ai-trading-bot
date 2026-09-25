"""Two surfaces over one SMC computation: causal, and analytical.

``shared/indicators/smart_money_concepts.py::calculate_smc`` describes a frame
as it stands at its LAST bar. A strategy needs to know what was knowable at
EVERY bar. Those are different questions, and the gap between them is
look-ahead bias.

The answer is NOT to throw the retrospective data away -- it is exactly what a
chart should draw and what research should study. It is to split the output in
two and make the boundary structural:

::

                      MARKET DATA
                           |
                  calculate_smc()  (once per closed bar, cached)
                           |
                  smc_lifecycle: recover every object's
                  origin / confirmation / invalidation bar
                           |
            +--------------+---------------+
            |                              |
            v                              v
        SmcView                     SmcAnalyticalView
     IS_CAUSAL = True             IS_ANALYTICAL = True
     only what was knowable       full lifecycle objects,
     at or before bar i           plus end-of-frame scalars
            |                              |
            v                              v
      STRATEGY ENGINE            CHART / RESEARCH / DEBUG

Nothing here re-implements SMC. ``calculate_smc`` is called once, unmodified;
this module only decides which of its outputs may be read per-bar, and from
which bar onwards.

Confirmation points, derived and then validated
-----------------------------------------------
See :mod:`smc_lifecycle` for the derivation of each. Measured on real NIFTY
5-minute data by recomputing on ``df[:k]`` and finding the first ``k`` at
which each object appears:

===========================  ==========================================
object                       confirmation
===========================  ==========================================
``smc_bos`` / ``smc_choch``  the bar they fire on (prefix-stable, 100%
                             match at k = 300/500/700/850)
Fair Value Gap               its own ``bar_index`` (lag 0)
Order Block                  the first same-direction structure event
                             after its origin bar (derived == measured)
Liquidity pool (EQH/EQL)     ``max(bar_indices) + effective_internal_len``
Swing pivot                  ``pivot_index + swing_length``
===========================  ==========================================

**Order Blocks are available to the strategy**, gated on that confirmation
bar. An earlier draft of this module excluded them on the grounds that their
creation bar was unrecoverable; that was wrong -- the engine emits
``structure_events``, and the block is created in the same loop iteration as
the event that produced it, so the confirmation bar follows directly.

End-of-frame scalars
--------------------
``calculate_smc`` assigns several END-OF-FRAME values into DataFrame columns,
which makes them look per-bar::

    res_df['smc_trend']       = current_trend.value   # final loop value
    res_df['smc_equilibrium'] = equilibrium           # trailing-window scalar

Those, plus ``strong_high``/``weak_high``/``strong_low``/``weak_low``,
``active_swing_high``/``active_swing_low`` and the premium/discount/OTE
zones, describe the frame's last bar only. They are RETAINED on
:class:`SmcAnalyticalView`, carrying an explicit ``as_of`` timestamp, and
raise :class:`LookAheadError` if read from :class:`SmcView`.
"""

from __future__ import annotations

import logging
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from shared.indicators.smart_money_concepts import LuxAlgoSMCConfig, calculate_smc

from . import smc_lifecycle as _lifecycle
from .config import RsiSmcConfig
from .smc_lifecycle import SmcObject, SmcState

logger = logging.getLogger(__name__)


class LookAheadError(RuntimeError):
    """Raised when a non-causal SMC output is read as a per-bar strategy
    feature."""


#: Every ``calculate_smc`` output that describes the frame's LAST bar only.
#: Retained on the analytical surface; refused on the causal one.
FORBIDDEN_PER_BAR_FIELDS: Tuple[str, ...] = (
    "smc_trend",
    "smc_equilibrium",
    "smc_candle_color",
    "trend",
    "equilibrium_price",
    "strong_high",
    "weak_high",
    "strong_low",
    "weak_low",
    "active_swing_high",
    "active_swing_low",
    "premium_zone",
    "discount_zone",
    "ote_zone",
)

_MAX_CACHE_ENTRIES = 8
_CACHE: "OrderedDict[str, Tuple[tuple, _Computation]]" = OrderedDict()
_CACHE_STATS = {"hits": 0, "misses": 0, "evictions": 0}


# ---------------------------------------------------------------------
# The causal surface -- the ONLY thing the strategy may read
# ---------------------------------------------------------------------

@dataclass(frozen=True)
class SmcView:
    """Everything the strategy may legally know at each bar.

    Every array is aligned to the frame passed to :func:`build` and is indexed
    POSITIONALLY. Nothing here is looked up by timestamp label, because the
    live 5-minute cache can accumulate duplicate and non-monotonic labels (the
    defect behind the 2026-08-28 CPU livelock recorded in
    ``_signal_utils.edge_trigger``).
    """

    #: Marker read by :func:`assert_causal`. Never remove.
    IS_CAUSAL = True

    n: int
    #: +1 bullish BOS, -1 bearish BOS, 0 none.
    bos: np.ndarray
    #: +1 bullish CHoCH, -1 bearish CHoCH, 0 none.
    choch: np.ndarray
    #: A bullish / bearish FVG was PRINTED on this bar.
    bull_fvg_printed: np.ndarray
    bear_fvg_printed: np.ndarray
    #: This bar interacted with a CONFIRMED, unmitigated FVG.
    in_bull_fvg: np.ndarray
    in_bear_fvg: np.ndarray
    #: This bar interacted with a CONFIRMED, unmitigated, un-invalidated
    #: Order Block. Gated on the derived confirmation bar.
    in_bull_ob: np.ndarray
    in_bear_ob: np.ndarray
    #: Nearest CONFIRMED buy-side (EQH) / sell-side (EQL) pool price, or NaN.
    pool_high: np.ndarray
    pool_low: np.ndarray
    pool_high_dist: np.ndarray
    pool_low_dist: np.ndarray
    #: Lookbacks ``calculate_smc`` actually used after its own internal clamp.
    effective_swing_len: int
    effective_internal_len: int
    pool_availability_delay: int
    n_pools: int = 0
    n_fvgs: int = 0
    n_order_blocks: int = 0

    def __getattr__(self, name: str) -> Any:  # pragma: no cover - guard path
        """Fail loudly on any non-causal field read as a per-bar feature.

        ``__getattr__`` only runs for names that are NOT real attributes, so
        this cannot shadow anything above.
        """
        if name in FORBIDDEN_PER_BAR_FIELDS:
            raise LookAheadError(
                f"{name!r} is an END-OF-FRAME value in calculate_smc(): it "
                f"describes the last bar of the frame, not bar i. It is "
                f"available on SmcAnalyticalView (chart/research), where it "
                f"carries an explicit `as_of` timestamp. It must not be read "
                f"as a per-bar strategy feature."
            )
        raise AttributeError(name)


# ---------------------------------------------------------------------
# The analytical surface -- chart, research, debugging. NEVER the strategy.
# ---------------------------------------------------------------------

@dataclass(frozen=True)
class SmcAnalyticalView:
    """Full SMC picture including retrospective structure.

    Everything the engine produced, with each object's complete lifecycle and
    the end-of-frame scalars the causal view refuses. A chart may draw an
    Order Block from ``origin_index`` labelled CANDIDATE and re-label it
    CONFIRMED at ``confirmation_index``; research may study whatever it likes.

    This object must never reach the strategy. :func:`assert_causal` is the
    enforcement, and ``signal_engine.build`` calls it.
    """

    #: Marker read by :func:`assert_causal`. Never remove.
    IS_ANALYTICAL = True

    n: int
    objects: List[SmcObject]
    #: The bar every end-of-frame scalar below is "as of".
    as_of_index: int
    as_of_time: Any
    #: End-of-frame scalars, retained deliberately and labelled.
    trend: int = 0
    equilibrium_price: Optional[float] = None
    strong_high: Optional[float] = None
    weak_high: Optional[float] = None
    strong_low: Optional[float] = None
    weak_low: Optional[float] = None
    active_swing_high: Optional[float] = None
    active_swing_low: Optional[float] = None
    premium_zone: Tuple[float, float] = (0.0, 0.0)
    discount_zone: Tuple[float, float] = (0.0, 0.0)
    ote_zone: Tuple[float, float] = (0.0, 0.0)

    def of_kind(self, kind: str) -> List[SmcObject]:
        return [o for o in self.objects if o.kind == kind]

    def states_at(self, index: int) -> Dict[str, SmcState]:
        """Every object's state as of ``index``, for a chart frame."""
        return {o.object_id: o.state_at(index) for o in self.objects}

    def records(self) -> List[Dict[str, Any]]:
        """Flat records for a chart payload or a research table."""
        return _lifecycle.lifecycle_table(self.objects)


def assert_causal(view: Any) -> None:
    """Refuse anything that is not the causal surface.

    The single guard that stops analytical data entering the decision path.
    Called by ``signal_engine.build``; cheap, and it turns a silent
    statistical error into a crash.
    """
    if getattr(view, "IS_ANALYTICAL", False) or not getattr(view, "IS_CAUSAL", False):
        raise LookAheadError(
            f"{type(view).__name__} is not a causal view. Only SmcView may "
            f"reach the strategy decision path; SmcAnalyticalView carries "
            f"retrospective structure and end-of-frame scalars and is for "
            f"charts, research and debugging only."
        )


def assert_no_forbidden_columns(frame: pd.DataFrame) -> None:
    """Raise if a frame carrying end-of-frame SMC scalars is about to be used
    as a per-bar strategy feature source."""
    present = [c for c in getattr(frame, "columns", []) if c in FORBIDDEN_PER_BAR_FIELDS]
    if present:
        raise LookAheadError(
            f"frame carries end-of-frame SMC columns {present}; these must not "
            f"reach the per-bar rule path. Use SmcView for the strategy, or "
            f"SmcAnalyticalView for a chart."
        )


def effective_lengths(n: int, cfg: RsiSmcConfig) -> Tuple[int, int]:
    """The lookbacks ``calculate_smc`` will actually use for ``n`` bars,
    reproducing its own internal clamp.

    The clamp is the reason for the minimum-bars gate: below ``6 x
    swing_points_length`` the engine quietly substitutes a shorter lookback,
    so the structure reported is not the structure configured.
    """
    effective_swing = min(int(cfg.swing_points_length), max(3, n // 6))
    effective_internal = min(int(cfg.internal_length), max(2, effective_swing // 2))
    return effective_swing, effective_internal


# ---------------------------------------------------------------------
# Shared computation + cache
# ---------------------------------------------------------------------

@dataclass(frozen=True)
class _Computation:
    """One ``calculate_smc`` run, projected both ways."""

    causal: SmcView
    analytical: SmcAnalyticalView


def _positional_frame(df: pd.DataFrame) -> pd.DataFrame:
    """A copy safe to hand to ``calculate_smc``.

    Duplicate and non-monotonic timestamps are tolerated: the index is
    replaced with a clean positional RangeIndex and every result is consumed
    positionally, so a repeated or out-of-order label cannot select the wrong
    row.
    """
    columns = [c for c in ("open", "high", "low", "close", "volume") if c in df.columns]
    out = df.loc[:, columns].copy()
    if "volume" not in out.columns:
        out["volume"] = 0.0
    out.index = pd.RangeIndex(len(out))
    return out


def _frame_key(df: pd.DataFrame, cfg: RsiSmcConfig) -> tuple:
    """Identity of this exact series-and-parameters combination."""
    idx = df.index
    first_ts = last_ts = 0
    if len(idx):
        try:
            first_ts = int(pd.Timestamp(idx[0]).value)
            last_ts = int(pd.Timestamp(idx[-1]).value)
        except Exception:
            first_ts, last_ts = 0, len(idx)
    close = df["close"].to_numpy(dtype=float)
    return (
        first_ts, last_ts, len(df),
        float(close[0]) if close.size else 0.0,
        float(close[-1]) if close.size else 0.0,
        int(cfg.swing_points_length), int(cfg.internal_length),
    )


def cache_stats() -> Dict[str, int]:
    """Hit/miss/eviction counters, for the latency measurements."""
    return dict(_CACHE_STATS, size=len(_CACHE))


def clear_cache() -> None:
    """Drop every cached computation. Used by tests and at a session
    boundary."""
    _CACHE.clear()
    for key in ("hits", "misses", "evictions"):
        _CACHE_STATS[key] = 0


def _empty_computation(n: int, cfg: RsiSmcConfig) -> _Computation:
    zeros_i = np.zeros(n, dtype=int)
    zeros_b = np.zeros(n, dtype=bool)
    nans = np.full(n, np.nan, dtype=float)
    swing, internal = effective_lengths(n, cfg)
    causal = SmcView(
        n=n, bos=zeros_i, choch=zeros_i.copy(),
        bull_fvg_printed=zeros_b, bear_fvg_printed=zeros_b.copy(),
        in_bull_fvg=zeros_b.copy(), in_bear_fvg=zeros_b.copy(),
        in_bull_ob=zeros_b.copy(), in_bear_ob=zeros_b.copy(),
        pool_high=nans, pool_low=nans.copy(),
        pool_high_dist=nans.copy(), pool_low_dist=nans.copy(),
        effective_swing_len=swing, effective_internal_len=internal,
        pool_availability_delay=internal,
    )
    analytical = SmcAnalyticalView(n=n, objects=[], as_of_index=max(0, n - 1),
                                   as_of_time=None)
    return _Computation(causal=causal, analytical=analytical)


def _computation(df: pd.DataFrame, cfg: RsiSmcConfig,
                 symbol: Optional[str] = None) -> _Computation:
    """Cached ``calculate_smc`` run for this frame.

    Called at most ONCE per newly closed bar: the cache key is the frame
    identity, which changes only when a bar closes, so the ~180 ms full-frame
    computation does not run on every 200 ms re-evaluation.

    ``symbol`` is optional because ``registry.run_strategy(name, df,
    **settings)`` does not pass one -- the frame fingerprint stands in for it
    and is strictly more discriminating (it separates timeframes as well as
    instruments). When a caller does know the symbol it becomes the bucket
    key, keeping the intended one-entry-per-symbol shape.
    """
    n = len(df)
    if n == 0 or n < cfg.min_bars:
        # Deliberately NOT a best-effort SMC read: below the minimum the
        # engine uses a different lookback than the one configured.
        return _empty_computation(n, cfg)

    bucket = symbol or "frame"
    key = _frame_key(df, cfg)
    cached = _CACHE.get(bucket)
    if cached is not None and cached[0] == key:
        _CACHE_STATS["hits"] += 1
        _CACHE.move_to_end(bucket)
        return cached[1]

    _CACHE_STATS["misses"] += 1
    computed = _compute(df, cfg)

    _CACHE[bucket] = (key, computed)
    _CACHE.move_to_end(bucket)
    while len(_CACHE) > _MAX_CACHE_ENTRIES:
        _CACHE.popitem(last=False)
        _CACHE_STATS["evictions"] += 1
    return computed


def build(df: pd.DataFrame, cfg: RsiSmcConfig,
          symbol: Optional[str] = None) -> SmcView:
    """The CAUSAL view -- the only surface the strategy may read."""
    return _computation(df, cfg, symbol).causal


def build_analytical(df: pd.DataFrame, cfg: RsiSmcConfig,
                     symbol: Optional[str] = None) -> SmcAnalyticalView:
    """The ANALYTICAL view -- charts, research, debugging. Never the strategy.

    Shares the same cached ``calculate_smc`` run as :func:`build`, so asking
    for both costs nothing extra.
    """
    return _computation(df, cfg, symbol).analytical


def _compute(df: pd.DataFrame, cfg: RsiSmcConfig) -> _Computation:
    """The uncached computation: one ``calculate_smc`` call, then both
    projections."""
    frame = _positional_frame(df)
    n = len(frame)

    smc_cfg = LuxAlgoSMCConfig(
        swing_points_length=int(cfg.swing_points_length),
        internal_length=int(cfg.internal_length),
        # "Historical" so the OB/FVG/pool lists are not truncated to the last
        # three active ones -- per-bar projection needs every object that ever
        # existed, then filters each by its own confirmation bar.
        mode="Historical",
        # Candle colouring derives from the end-of-frame trend scalar and
        # nothing here renders, so it is wasted work.
        color_candles=False,
    )
    res_df, analysis = calculate_smc(frame, config=smc_cfg)

    effective_swing, effective_internal = effective_lengths(n, cfg)

    opens = frame["open"].to_numpy(dtype=float)
    highs = frame["high"].to_numpy(dtype=float)
    lows = frame["low"].to_numpy(dtype=float)
    closes = frame["close"].to_numpy(dtype=float)
    timestamps = list(df.index)

    # ---- lifecycle: recover every object's origin / confirmation / death ---
    objects: List[SmcObject] = []
    objects += _lifecycle.derive_structure_events(analysis, timestamps)
    objects += _lifecycle.derive_fvgs(analysis, timestamps)
    objects += _lifecycle.derive_order_blocks(analysis, opens, closes, timestamps)
    objects += _lifecycle.derive_liquidity_pools(analysis, timestamps, effective_internal)
    objects += _lifecycle.derive_swings(highs, lows, timestamps, effective_swing)

    # ---- causal projection -------------------------------------------------
    bos = res_df["smc_bos"].to_numpy(dtype=int) if "smc_bos" in res_df else np.zeros(n, dtype=int)
    choch = res_df["smc_choch"].to_numpy(dtype=int) if "smc_choch" in res_df else np.zeros(n, dtype=int)
    bull_printed = (res_df["smc_bullish_fvg"].to_numpy(dtype=bool)
                    if "smc_bullish_fvg" in res_df else np.zeros(n, dtype=bool))
    bear_printed = (res_df["smc_bearish_fvg"].to_numpy(dtype=bool)
                    if "smc_bearish_fvg" in res_df else np.zeros(n, dtype=bool))

    gaps = [o for o in objects if o.kind == _lifecycle.KIND_FVG]
    blocks = [o for o in objects if o.kind == _lifecycle.KIND_ORDER_BLOCK]
    pools = [o for o in objects if o.kind == _lifecycle.KIND_LIQUIDITY_POOL]

    in_bull_fvg = _lifecycle.zone_interaction_mask(gaps, highs, lows, n, bullish=True)
    in_bear_fvg = _lifecycle.zone_interaction_mask(gaps, highs, lows, n, bullish=False)
    in_bull_ob = _lifecycle.zone_interaction_mask(blocks, highs, lows, n, bullish=True)
    in_bear_ob = _lifecycle.zone_interaction_mask(blocks, highs, lows, n, bullish=False)

    pool_high, pool_high_dist = _lifecycle.nearest_price_mask(pools, closes, n, is_high=True)
    pool_low, pool_low_dist = _lifecycle.nearest_price_mask(pools, closes, n, is_high=False)
    pool_high_dist = np.where(np.isfinite(pool_high_dist), pool_high_dist, np.nan)
    pool_low_dist = np.where(np.isfinite(pool_low_dist), pool_low_dist, np.nan)

    causal = SmcView(
        n=n, bos=bos, choch=choch,
        bull_fvg_printed=bull_printed, bear_fvg_printed=bear_printed,
        in_bull_fvg=in_bull_fvg, in_bear_fvg=in_bear_fvg,
        in_bull_ob=in_bull_ob, in_bear_ob=in_bear_ob,
        pool_high=pool_high, pool_low=pool_low,
        pool_high_dist=pool_high_dist, pool_low_dist=pool_low_dist,
        effective_swing_len=effective_swing,
        effective_internal_len=effective_internal,
        pool_availability_delay=effective_internal,
        n_pools=len(pools), n_fvgs=len(gaps), n_order_blocks=len(blocks),
    )

    # ---- analytical projection --------------------------------------------
    analytical = SmcAnalyticalView(
        n=n,
        objects=objects,
        as_of_index=n - 1,
        as_of_time=timestamps[-1] if timestamps else None,
        trend=int(getattr(analysis.trend, "value", 0)),
        equilibrium_price=analysis.equilibrium_price,
        strong_high=analysis.strong_high,
        weak_high=analysis.weak_high,
        strong_low=analysis.strong_low,
        weak_low=analysis.weak_low,
        active_swing_high=analysis.active_swing_high,
        active_swing_low=analysis.active_swing_low,
        premium_zone=analysis.premium_zone,
        discount_zone=analysis.discount_zone,
        ote_zone=analysis.ote_zone,
    )

    return _Computation(causal=causal, analytical=analytical)


__all__ = [
    "SmcView",
    "SmcAnalyticalView",
    "SmcObject",
    "SmcState",
    "LookAheadError",
    "FORBIDDEN_PER_BAR_FIELDS",
    "assert_causal",
    "assert_no_forbidden_columns",
    "effective_lengths",
    "build",
    "build_analytical",
    "cache_stats",
    "clear_cache",
]
