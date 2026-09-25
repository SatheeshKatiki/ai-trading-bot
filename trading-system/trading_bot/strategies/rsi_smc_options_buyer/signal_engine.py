"""The seven-step entry composition.

::

    1. HTF bias            15-min close vs EMA20, with the slope agreeing
    2. Regime              trending -> continuation, ranging -> reversal
    3. Key-level proximity price is near liquidity that actually rests there
    4. Liquidity sweep     that level was run and price closed back inside
    5. BOS / CHoCH         structure confirmed the reversal or the continuation
    6. RSI confirmation    momentum agrees -- CONFIRMATION ONLY
    7. Price-action trigger a decisive candle, or a reaction from an FVG

Every step is a separate boolean array over the whole frame and
:func:`compose` is a pure ``AND`` of all of them. That shape is deliberate:
holding any one condition out and asserting the result is all zeros is then a
two-line test, and RSI's confirmation-only status is a property of the
composition rather than a promise in a comment.

Everything is evaluated on CLOSED bars and addressed positionally. A rule that
reads the bar still forming means "price touched this level at some instant"
live and "the bar closed beyond it" in a backtest -- two different strategies
wearing one name, which is the divergence ``structure_break``'s docstring and
``TieredExitManager``'s history both warn about.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional, Tuple

import numpy as np
import pandas as pd

from shared.indicators import atr as _atr
from shared.indicators import ema as _ema
from shared.indicators import rsi as _rsi

from . import levels as _levels
from . import liquidity as _liquidity
from . import no_trade as _no_trade
from . import regime as _regime
from . import structure as _structure
from .config import RsiSmcConfig

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Conditions:
    """One array per mandatory condition, for both directions.

    Names match the seven steps. ``compose`` ANDs them; a test can zero any
    single field and assert no signal survives.
    """

    htf_bull: np.ndarray
    htf_bear: np.ndarray
    regime_ok: np.ndarray
    level_near_bull: np.ndarray
    level_near_bear: np.ndarray
    sweep_bull: np.ndarray
    sweep_bear: np.ndarray
    struct_bull: np.ndarray
    struct_bear: np.ndarray
    rsi_bull: np.ndarray
    rsi_bear: np.ndarray
    trigger_bull: np.ndarray
    trigger_bear: np.ndarray
    rr_ok_bull: np.ndarray
    rr_ok_bear: np.ndarray
    not_blocked: np.ndarray

    #: Mandatory-condition field names, bull and bear. Used by the holdout
    #: tests so a newly added condition is covered automatically.
    BULL_FIELDS = ("htf_bull", "regime_ok", "level_near_bull", "sweep_bull",
                   "struct_bull", "rsi_bull", "trigger_bull", "rr_ok_bull",
                   "not_blocked")
    BEAR_FIELDS = ("htf_bear", "regime_ok", "level_near_bear", "sweep_bear",
                   "struct_bear", "rsi_bear", "trigger_bear", "rr_ok_bear",
                   "not_blocked")


@dataclass(frozen=True)
class Diagnostics:
    """Per-bar values the exit layer and the logs need. Never a trading input
    on its own."""

    atr: np.ndarray
    rsi: np.ndarray
    rsi_ma: np.ndarray
    swept_level_bull: np.ndarray
    swept_level_bear: np.ndarray
    swept_extreme_bull: np.ndarray
    swept_extreme_bear: np.ndarray
    target_bull: np.ndarray
    target_bear: np.ndarray
    reward_risk_bull: np.ndarray
    reward_risk_bear: np.ndarray


def _recent(mask: np.ndarray, window: int) -> np.ndarray:
    """True at bar ``i`` if ``mask`` was true on any of the last ``window``
    bars, the current bar included.

    Positional shifts only -- no label-based ``Series.shift``.
    """
    values = np.asarray(mask, dtype=bool)
    out = values.copy()
    n = values.shape[0]
    for k in range(1, max(1, int(window))):
        if k >= n:
            break
        shifted = np.zeros(n, dtype=bool)
        shifted[k:] = values[:-k]
        out |= shifted
    return out


def _best_target(close: np.ndarray, risk: np.ndarray, above: bool,
                 candidates) -> Tuple[np.ndarray, np.ndarray]:
    """Most rewarding opposing level per bar, and the R:R it implies.

    Each candidate family contributes its own level; the one giving the
    largest reward-to-risk on the correct side of price wins. NaN where no
    candidate is available or the risk is not positive, which the caller
    treats as "no qualifying target", i.e. no trade.
    """
    n = close.shape[0]
    best_level = np.full(n, np.nan, dtype=float)
    best_rr = np.full(n, np.nan, dtype=float)
    valid_risk = np.isfinite(risk) & (risk > 0)

    for candidate in candidates:
        if candidate is None:
            continue
        values = np.asarray(candidate, dtype=float)
        if values.shape[0] != n:
            continue
        reward = (values - close) if above else (close - values)
        usable = valid_risk & np.isfinite(values) & (reward > 0)
        with np.errstate(divide="ignore", invalid="ignore"):
            rr = np.where(usable, reward / risk, np.nan)
        better = usable & (~np.isfinite(best_rr) | (rr > best_rr))
        best_rr = np.where(better, rr, best_rr)
        best_level = np.where(better, values, best_level)

    return best_level, best_rr


def htf_bias(df: pd.DataFrame, cfg: RsiSmcConfig) -> Tuple[np.ndarray, np.ndarray]:
    """Bullish / bearish higher-timeframe bias per LTF bar.

    Bars are grouped into higher-timeframe buckets positionally, and bar ``i``
    reads the PREVIOUS COMPLETED bucket. A bucket still forming is never
    visible, so the bias cannot change retroactively within a bar -- the same
    guarantee ``momentum_15_5`` gets from ``label='right', closed='right'``,
    obtained here without a label-based reindex that duplicate timestamps
    would break.

    Bias requires BOTH price on the right side of the EMA and the EMA sloping
    that way. The slope term is the one entry condition measured in this
    repository that survived an out-of-sample split on two instruments; the
    price term alone did not.
    """
    n = len(df)
    false_arr = np.zeros(n, dtype=bool)
    if n == 0 or not isinstance(df.index, pd.DatetimeIndex):
        return false_arr, false_arr.copy()

    # Minutes since the epoch, unit-explicit. `index.view("int64")` is NOT
    # safe here: pandas 2.x infers the datetime resolution from the source,
    # so a frame parsed as datetime64[us] yields microseconds while one
    # parsed as datetime64[ns] yields nanoseconds. Dividing by a hard-coded
    # ns-per-minute then silently collapsed every bar into the same bucket
    # (caught on real data: 4000 bars produced 8 buckets instead of 800, and
    # the bias never fired). Asking numpy for datetime64[m] converts once,
    # correctly, whatever the source resolution.
    minutes = df.index.to_numpy(dtype="datetime64[m]").astype(np.int64)
    bucket = minutes // max(1, int(cfg.htf_minutes))
    changes = np.r_[True, bucket[1:] != bucket[:-1]]
    bar_bucket = np.cumsum(changes) - 1
    starts = np.flatnonzero(changes)
    ends = np.r_[starts[1:], n]

    close = df["close"].to_numpy(dtype=float)
    bucket_close = close[ends - 1]
    n_buckets = bucket_close.shape[0]

    lookback = max(1, int(cfg.htf_slope_lookback))
    if n_buckets < int(cfg.htf_ema) + lookback + 1:
        return false_arr, false_arr.copy()

    ema_b = _ema(pd.Series(bucket_close), int(cfg.htf_ema)).to_numpy(dtype=float)

    slope = np.full(n_buckets, np.nan, dtype=float)
    prior = ema_b[:-lookback]
    with np.errstate(divide="ignore", invalid="ignore"):
        slope[lookback:] = np.where(prior > 0, (ema_b[lookback:] - prior) / prior * 100.0, np.nan)

    threshold = float(cfg.htf_slope_min_pct)
    bull_b = (bucket_close > ema_b) & np.isfinite(slope) & (slope > threshold)
    bear_b = (bucket_close < ema_b) & np.isfinite(slope) & (slope < -threshold)

    previous = bar_bucket - 1
    usable = previous >= 0
    safe = np.where(usable, previous, 0)
    return (np.where(usable, bull_b[safe], False),
            np.where(usable, bear_b[safe], False))


def rsi_confirmation(df: pd.DataFrame, cfg: RsiSmcConfig):
    """RSI agreement, and the raw series for diagnostics.

    Two requirements, both directional: RSI is on the right side of its own
    moving average, and it crossed the midline that way within the
    confirmation window. Neither can produce a trade on its own -- this array
    is one of nine ANDed together in :func:`compose`, and
    ``test_rsi_smc_signals.py`` asserts an RSI-only frame yields zero signals.
    """
    close = df["close"]
    rsi = _rsi(close, int(cfg.rsi_length))
    rsi_ma = _ema(rsi, int(cfg.rsi_ma_length))
    rsi_v = rsi.to_numpy(dtype=float)
    rsi_ma_v = rsi_ma.to_numpy(dtype=float)

    mid = float(cfg.rsi_midline)

    # A STATE, not an event. RSI has to be on the right side of its own
    # moving average and of the midline -- that is what "momentum agrees"
    # means. An earlier draft also demanded a midline CROSS inside the
    # confirmation window; measured on 18,766 NIFTY bars that turned RSI into
    # a third independent event stacked on top of the sweep and the structure
    # break, and the conjunction produced 4 signals per YEAR. Confirmation is
    # meant to veto a disagreeing setup, not to be a fourth trigger that has
    # to fire on the same handful of bars.
    bull = (rsi_v > rsi_ma_v) & (rsi_v > mid)
    bear = (rsi_v < rsi_ma_v) & (rsi_v < mid)
    return np.nan_to_num(bull).astype(bool), np.nan_to_num(bear).astype(bool), rsi_v, rsi_ma_v


def price_action_trigger(df: pd.DataFrame, view: _structure.SmcView,
                         atr: np.ndarray, cfg: RsiSmcConfig):
    """A candle that is LEAVING the level, not one chasing a move that left.

    Two conditions, both about conviction: the body is at least
    ``min_body_atr`` x ATR, and the candle closes within
    ``max_close_from_extreme`` of its own extreme in the trade's direction --
    a bar that ran and held, not one that ran and gave it back.

    A reaction from an unmitigated Fair Value Gap is accepted as an
    alternative trigger when ``use_fvg_trigger`` is on. Order Blocks are NOT
    an option here: their availability lag is variable and unrecoverable from
    the engine's output (see :mod:`structure`).
    """
    open_ = df["open"].to_numpy(dtype=float) if "open" in df.columns else None
    high = df["high"].to_numpy(dtype=float)
    low = df["low"].to_numpy(dtype=float)
    close = df["close"].to_numpy(dtype=float)
    n = close.shape[0]
    if open_ is None:
        return np.zeros(n, dtype=bool), np.zeros(n, dtype=bool)

    atr_v = np.asarray(atr, dtype=float)
    decisive = np.abs(close - open_) >= float(cfg.min_body_atr) * atr_v
    span = np.maximum(high - low, 1e-9)
    edge = float(cfg.max_close_from_extreme)

    held_bull = (high - close) <= edge * span
    held_bear = (close - low) <= edge * span

    bull = np.nan_to_num(decisive & held_bull).astype(bool)
    bear = np.nan_to_num(decisive & held_bear).astype(bool)

    if cfg.use_fvg_trigger:
        bull = bull | np.asarray(view.in_bull_fvg, dtype=bool)
        bear = bear | np.asarray(view.in_bear_fvg, dtype=bool)

    if getattr(cfg, "use_ob_trigger", False):
        # Causally gated: `in_bull_ob` / `in_bear_ob` are only true from each
        # block's CONFIRMATION bar (the structure event that created it), and
        # only while it is neither mitigated nor invalidated. Off by default.
        bull = bull | np.asarray(view.in_bull_ob, dtype=bool)
        bear = bear | np.asarray(view.in_bear_ob, dtype=bool)

    return bull, bear


def compose(conditions: Conditions) -> np.ndarray:
    """``{-1, 0, +1}`` per bar: the pure AND of every mandatory condition.

    Bearish is evaluated first so that a (structurally impossible, since the
    HTF bias cannot be bullish and bearish at once) overlap resolves
    deterministically rather than by array order.
    """
    bull = np.ones_like(conditions.htf_bull, dtype=bool)
    for name in Conditions.BULL_FIELDS:
        bull &= np.asarray(getattr(conditions, name), dtype=bool)

    bear = np.ones_like(conditions.htf_bear, dtype=bool)
    for name in Conditions.BEAR_FIELDS:
        bear &= np.asarray(getattr(conditions, name), dtype=bool)

    return np.select([bear, bull], [-1, 1], default=0).astype(int)


def build(df: pd.DataFrame, cfg: RsiSmcConfig, symbol: Optional[str] = None
          ) -> Tuple[np.ndarray, Conditions, Diagnostics, _no_trade.NoTradeView]:
    """Signals plus everything needed to explain them.

    Returns the raw (not yet edge-triggered) signal array, the per-condition
    arrays, per-bar diagnostics, and the no-trade view.
    """
    n = len(df)
    if n == 0:
        empty_b = np.zeros(0, dtype=bool)
        empty_f = np.zeros(0, dtype=float)
        conditions = Conditions(*([empty_b.copy() for _ in range(16)]))
        diagnostics = Diagnostics(*([empty_f.copy() for _ in range(11)]))
        return np.zeros(0, dtype=int), conditions, diagnostics, _no_trade.NoTradeView(empty_b.copy(), {})

    close = df["close"].to_numpy(dtype=float)
    atr_v = _atr(df, int(cfg.atr_length)).to_numpy(dtype=float)

    view = _structure.build(df, cfg, symbol=symbol)
    # The one guard that stops analytical/retrospective SMC data reaching a
    # trading decision. `build()` returns the causal surface; this refuses
    # anything else, including SmcAnalyticalView, which carries objects from
    # before their confirmation bar and end-of-frame scalars.
    _structure.assert_causal(view)
    regime_view = _regime.compute(df, cfg)
    blocks = _no_trade.evaluate(df, cfg, regime_view, atr_v, symbol=symbol)

    daily = _levels.compute_daily_levels(df)

    # 3. Key-level proximity. Only levels that were already AVAILABLE at the
    #    bar take part: structure.build() has applied the measured pool
    #    availability delay, and levels.compute_daily_levels() derives the
    #    daily levels from shifted aggregates.
    level_low = _levels.nearest_level(
        view.pool_low, daily.prev_day_low, daily.session_low,
        reference=close, above=False)
    level_high = _levels.nearest_level(
        view.pool_high, daily.prev_day_high, daily.session_high,
        reference=close, above=True)

    tolerance = float(cfg.level_atr_mult) * atr_v
    level_near_bull = np.isfinite(level_low) & (np.abs(close - level_low) <= tolerance)
    level_near_bear = np.isfinite(level_high) & (np.abs(close - level_high) <= tolerance)

    # 4. Liquidity sweep. Named levels and the reference rolling extreme are
    #    both tested with the SAME core rule (see liquidity.py); a setup may
    #    qualify off either, and neither gets a second vote.
    warmup = int(cfg.sweep_lookback) * 2
    named = _liquidity.key_level_sweeps(
        df, level_low, level_high, int(cfg.sweep_recent_bars), warmup)
    rolling = _liquidity.reference_sweeps(
        df, int(cfg.sweep_lookback), int(cfg.sweep_recent_bars))
    sweeps = _liquidity.combine(named, rolling)

    # 5. Structure confirmation. Regime decides WHICH confirmation counts:
    #    a range reverses (CHoCH), a trend resumes (BOS).
    window = int(cfg.confirm_window)
    choch_up = _recent(view.choch > 0, window)
    choch_dn = _recent(view.choch < 0, window)
    bos_up = _recent(view.bos > 0, window)
    bos_dn = _recent(view.bos < 0, window)

    struct_bull = (regime_view.ranging & choch_up) | (regime_view.trending & bos_up)
    struct_bear = (regime_view.ranging & choch_dn) | (regime_view.trending & bos_dn)

    # 6. RSI -- confirmation only.
    rsi_bull, rsi_bear, rsi_v, rsi_ma_v = rsi_confirmation(df, cfg)

    # 7. Price-action trigger.
    trigger_bull, trigger_bear = price_action_trigger(df, view, atr_v, cfg)

    # Risk/reward, from structure rather than from a fixed percentage: risk is
    # the distance to the invalidation below the swept extreme, reward the
    # distance to the opposing liquidity the move is running at.
    buffer = float(cfg.sl_atr_buffer) * atr_v
    stop_bull = sweeps.bullish_extreme - buffer
    stop_bear = sweeps.bearish_extreme + buffer
    risk_bull = close - stop_bull
    risk_bear = stop_bear - close

    # The target is the BEST-REWARD opposing liquidity among the level
    # families, not the nearest one.
    #
    # Taking the nearest opposing level minimises measured reward by
    # construction -- whichever level happens to sit a few points away caps
    # the R:R of every setup, and on real NIFTY data that alone vetoed every
    # surviving candidate. The question a target has to answer is "is there
    # liquidity far enough away to justify this risk", so each candidate
    # family is scored and the most rewarding qualifying one is taken. The
    # stop is untouched by this: risk is still the structural invalidation
    # below the swept extreme.
    target_bull, rr_bull = _best_target(
        close, risk_bull, above=True,
        candidates=(view.pool_high, daily.prev_day_high, daily.session_high))
    target_bear, rr_bear = _best_target(
        close, risk_bear, above=False,
        candidates=(view.pool_low, daily.prev_day_low, daily.session_low))

    min_rr = float(cfg.min_rr)
    rr_ok_bull = np.isfinite(rr_bull) & (rr_bull >= min_rr)
    rr_ok_bear = np.isfinite(rr_bear) & (rr_bear >= min_rr)

    # 1. HTF bias, last so the whole set is constructed once.
    bull_bias, bear_bias = htf_bias(df, cfg)

    conditions = Conditions(
        htf_bull=bull_bias, htf_bear=bear_bias,
        regime_ok=np.asarray(regime_view.tradeable, dtype=bool),
        level_near_bull=level_near_bull, level_near_bear=level_near_bear,
        sweep_bull=sweeps.bullish, sweep_bear=sweeps.bearish,
        struct_bull=struct_bull, struct_bear=struct_bear,
        rsi_bull=rsi_bull, rsi_bear=rsi_bear,
        trigger_bull=trigger_bull, trigger_bear=trigger_bear,
        rr_ok_bull=rr_ok_bull, rr_ok_bear=rr_ok_bear,
        not_blocked=~blocks.blocked,
    )

    diagnostics = Diagnostics(
        atr=atr_v, rsi=rsi_v, rsi_ma=rsi_ma_v,
        swept_level_bull=sweeps.bullish_level, swept_level_bear=sweeps.bearish_level,
        swept_extreme_bull=sweeps.bullish_extreme, swept_extreme_bear=sweeps.bearish_extreme,
        target_bull=target_bull, target_bear=target_bear,
        reward_risk_bull=rr_bull, reward_risk_bear=rr_bear,
    )

    return compose(conditions), conditions, diagnostics, blocks


def failing_conditions(conditions: Conditions, index: int, direction: int) -> Tuple[str, ...]:
    """Which mandatory conditions were NOT met at ``index``.

    Used for the "why was there no trade" log line and by the diagnostics in
    the shadow book. Pure, so it is directly testable.
    """
    fields = Conditions.BULL_FIELDS if direction > 0 else Conditions.BEAR_FIELDS
    out = []
    for name in fields:
        array = np.asarray(getattr(conditions, name), dtype=bool)
        if index < array.shape[0] and not array[index]:
            out.append(name)
    return tuple(out)


__all__ = ["Conditions", "Diagnostics", "build", "compose", "htf_bias",
           "rsi_confirmation", "price_action_trigger", "failing_conditions"]
