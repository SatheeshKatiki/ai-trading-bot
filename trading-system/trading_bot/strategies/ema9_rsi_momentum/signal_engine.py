
"""EMA9/RSI Momentum — core signal engine.

Pure, stateless functions operating on a closed-candle OHLCV DataFrame.
Deliberately separated from ``__init__.py`` (the registry entry point) and
from ``premium_health.py`` (the post-entry monitoring layer) so the three
concerns the task asks to keep distinct — Entry Signal, Momentum Strength,
and Premium Health — are each a small, independently testable module
rather than one large function.

Symmetric by construction: the CE entry condition (EMA9 crosses above
EMA20 AND RSI14 crosses above its RSI-EMA20) is exactly the PE *exit*
condition, and vice versa — so entry and exit both read off the same two
boolean arrays (``bullish_cross`` / ``bearish_cross``) instead of two
independently-maintained rule sets.
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass

import numpy as np
import pandas as pd

from .config import Ema9RsiMomentumConfig
from .indicators import (
    IndicatorSet,
    compute_indicator_set,
    crossed_above,
    crossed_above_level,
    crossed_below,
    crossed_below_level,
)

from typing import Optional

#: Momentum-strength labels, weakest to strongest.
NO_MOMENTUM = "NONE"
NORMAL = "NORMAL"
STRONG = "STRONG"
VERY_STRONG = "VERY_STRONG"


@dataclass(frozen=True)
class CrossSignals:
    """Per-bar boolean arrays the entry and exit rules are both built from."""

    bullish: np.ndarray  # CE entry signals (executed at candle close)
    bearish: np.ndarray  # PE entry signals (executed at candle close)
    indicators: IndicatorSet
    stop_loss: Optional[pd.Series] = None
    is_chop: Optional[np.ndarray] = None


from shared.indicators import adx
from shared.timeframes import seconds_to_bar_close, timeframe_label  # noqa: F401  (re-exported)


BODY = "body"
WICK = "wick"


@dataclass(frozen=True)
class ClusterTouch:
    """Per-bar verdict on how the candle sits against the EMA9/EMA20 pair."""

    passes: np.ndarray   # bar satisfies the configured touch mode
    by_body: np.ndarray  # the BODY reaches both EMAs (the preferred case)
    by_wick: np.ndarray  # the full high-low range reaches both EMAs


def ema_cluster_touch(df: pd.DataFrame, ind: IndicatorSet,
                      cfg: Ema9RsiMomentumConfig) -> ClusterTouch:
    """Does the candle actually reach BOTH moving averages?

    The owner's rule, stated 2026-09-22: at the crossover the candle must
    touch EMA9 *and* EMA20 -- its body for preference, its wick if not.

    "Touching both" means the candle's range contains both EMA values, i.e.
    it spans from at or below the lower EMA to at or above the upper one. A
    body touch therefore implies a wick touch (the body is inside the range),
    so `by_body` is the strict subset -- which is why it is reported
    separately rather than OR-ed in: it is the quality of the signal, and
    "body" mode keeps only those.

    What this replaces: a one-sided test, `low <= max(ema9, ema20) + 0.06%`,
    which asked only whether the candle dipped near the upper EMA and never
    looked at the lower one at all. Over 2024-01-01..2026-09-21 it admitted
    90% of NIFTY and 91% of SENSEX crossover bars -- it was not filtering.
    The owner's rule admits 38% by wick and 22% by body.
    """
    high = np.asarray(df["high"], dtype=float)
    low = np.asarray(df["low"], dtype=float)
    close = np.asarray(df["close"], dtype=float)
    open_ = np.asarray(df["open"], dtype=float) if "open" in df.columns else close

    fast = np.asarray(ind.ema_fast, dtype=float)
    slow = np.asarray(ind.ema_slow, dtype=float)
    upper = np.maximum(fast, slow)
    lower = np.minimum(fast, slow)

    by_wick = (low <= lower) & (high >= upper)
    body_lo = np.minimum(open_, close)
    body_hi = np.maximum(open_, close)
    by_body = (body_lo <= lower) & (body_hi >= upper)

    # NaN in either EMA (warm-up) must not pass as a touch.
    finite = np.isfinite(fast) & np.isfinite(slow)
    by_wick &= finite
    by_body &= finite

    mode = str(getattr(cfg, "ema_touch_mode", "body_or_wick")).lower()
    if mode == BODY:
        passes = by_body
    elif mode == "legacy":
        buffer = close * float(getattr(cfg, "legacy_touch_buffer_pct", 0.0006))
        passes = (low <= (upper + buffer)) & finite
    else:  # "body_or_wick" -- the owner's rule as stated
        passes = by_wick

    return ClusterTouch(passes=passes, by_body=by_body, by_wick=by_wick)


#: Entry priority. HIGH is the owner's first preference (a body touch), MEDIUM
#: a wick touch that earned its place (with trend slope agreement), LOW one that did not.
PRIORITY_HIGH = "HIGH"
PRIORITY_MEDIUM = "MEDIUM"
PRIORITY_LOW = "LOW"
PRIORITY_BREAKAWAY = "BREAKAWAY"
PRIORITY_NONE = "NONE"


def _breakaway(df: pd.DataFrame, cfg: Ema9RsiMomentumConfig,
               direction: np.ndarray) -> np.ndarray:
    """A candle that is LEAVING the level, not chasing one that already left.

    See config.ALLOW_BREAKAWAY_ENTRY for the 2026-09-22 case this exists for
    and the measurements. Two conditions, both about conviction rather than
    position: the body is at least `breakaway_min_body_atr` x ATR, and the
    candle closes within `breakaway_max_close_from_extreme` of its own
    extreme in the trade's direction -- a bar that ran and held, not one that
    ran and gave it back.
    """
    if not bool(getattr(cfg, "allow_breakaway_entry", False)):
        return np.zeros(len(df), dtype=bool)

    open_ = np.asarray(df["open"], dtype=float) if "open" in df.columns else None
    high = np.asarray(df["high"], dtype=float)
    low = np.asarray(df["low"], dtype=float)
    close = np.asarray(df["close"], dtype=float)
    if open_ is None:
        return np.zeros(len(df), dtype=bool)

    prev = np.r_[close[0], close[:-1]]
    true_range = np.maximum(high - low, np.maximum(np.abs(high - prev), np.abs(low - prev)))
    length = max(1, int(getattr(cfg, "breakaway_atr_length", 14)))
    atr = pd.Series(true_range).ewm(alpha=1 / length, adjust=False).mean().to_numpy()

    decisive = np.abs(close - open_) >= float(getattr(cfg, "breakaway_min_body_atr", 1.0)) * atr
    span = np.maximum(high - low, 1e-9)
    edge = float(getattr(cfg, "breakaway_max_close_from_extreme", 0.35))
    held = np.where(np.asarray(direction) > 0, (high - close) <= edge * span,
                    np.where(np.asarray(direction) < 0, (close - low) <= edge * span, False))
    return decisive & np.nan_to_num(held).astype(bool)


@dataclass(frozen=True)
class EntryQuality:
    """Per-bar entry grading: how good the touch is, and whether to take it."""

    priority: np.ndarray      # PRIORITY_* label per bar
    take: np.ndarray          # bool: this bar's signal is worth acting on
    trend_agrees: np.ndarray  # EMA20 sloping with the trade
    rsi_separated: np.ndarray # preserved for backwards compatibility (all True)


def assess_entry_quality(df: pd.DataFrame, ind: IndicatorSet,
                         cfg: Ema9RsiMomentumConfig,
                         direction: np.ndarray) -> EntryQuality:
    """Grade each bar's entry:
    - A body touch is taken outright (priority HIGH).
    - A wick touch requires trend slope agreement (priority MEDIUM).
    - Wick touch without trend agreement is skipped (priority LOW).
    """
    touch = ema_cluster_touch(df, ind, cfg)
    n = len(df)
    direction = np.asarray(direction, dtype=int)

    close = np.asarray(df["close"], dtype=float)
    slow = pd.Series(np.asarray(ind.ema_slow, dtype=float))
    lookback = max(1, int(getattr(cfg, "trend_slope_lookback", 6)))
    slope_pct = ((slow - slow.shift(lookback)) / np.where(close == 0, np.nan, close) * 100).to_numpy()
    floor = float(getattr(cfg, "trend_slope_min_pct", 0.02))
    trend_agrees = np.where(direction > 0, slope_pct > floor,
                            np.where(direction < 0, slope_pct < -floor, False))
    trend_agrees = np.nan_to_num(trend_agrees, nan=0.0).astype(bool)

    # RSI separation gap rule removed per user instruction.
    rsi_separated = np.ones(n, dtype=bool)

    wick_only = touch.by_wick & ~touch.by_body
    if getattr(cfg, "wick_requires_confirmation", True):
        wick_ok = wick_only & trend_agrees
    else:
        wick_ok = wick_only

    breakaway = _breakaway(df, cfg, direction) & ~touch.by_wick

    priority = np.full(n, PRIORITY_NONE, dtype=object)
    priority[wick_only] = PRIORITY_LOW
    priority[breakaway] = PRIORITY_BREAKAWAY
    priority[wick_ok] = PRIORITY_MEDIUM
    priority[touch.by_body] = PRIORITY_HIGH

    # "take" still honours the configured touch mode: in "body" mode a wick
    # never qualifies; otherwise body touch or confirmed wick touch qualifies.
    mode = str(getattr(cfg, "ema_touch_mode", "body_or_wick")).lower()
    if mode == BODY:
        take = touch.by_body
    elif mode == "legacy":
        take = touch.passes
    else:
        take = touch.by_body | wick_ok | breakaway

    return EntryQuality(priority=priority, take=take,
                        trend_agrees=trend_agrees, rsi_separated=rsi_separated)


def entry_timing_gate(now: datetime.datetime, strength: str,
                      cfg: Ema9RsiMomentumConfig,
                      bar_minutes: int | None = None) -> tuple[bool, str]:
    """May an entry be taken *right now*, given how far the candle has to run?

    The owner's rule, stated 2026-09-22: take the entry in the last
    `entry_confirm_seconds` before the candle closes; before that, take it
    only on momentum strength.

    Why: a crossover is not final until its bar closes. Intrabar, EMA9 can
    cross EMA20 and cross back -- buying on that costs a full entry spread
    plus the stop for a signal that never existed. Waiting until the bar is
    all but settled removes that, at the price of a few seconds of slippage.
    The strength escape exists so a decisive move is not made to wait: when
    RSI already sits in the STRONG band for the trade's direction, the
    crossover is very unlikely to un-happen.

    The bar size is whatever the user picked in the UI -- 1, 3, 5, 15, 30
    minutes or an hour -- carried on `cfg.timeframe_minutes`, or passed
    explicitly. On a daily, weekly or monthly chart the next close is days
    away, so there is nothing to wait for; the rule does not apply and the
    entry is allowed, with the reason saying so rather than pretending a
    countdown exists.

    Returns ``(allowed, reason)``; `reason` is logged either way, so a skipped
    entry can be told apart from an absent signal in the books.
    """
    span = int(bar_minutes or getattr(cfg, "timeframe_minutes", 5) or 5)
    left = seconds_to_bar_close(now, span)
    if left is None:
        return True, (f"{timeframe_label(span)} bars have no intraday close -- "
                      f"bar-close confirmation does not apply")

    window = int(getattr(cfg, "entry_confirm_seconds", 10))
    if left <= window:
        return True, f"confirmation window ({left:.0f}s to {timeframe_label(span)} bar close)"

    floor = str(getattr(cfg, "early_entry_min_strength", STRONG)).upper()
    if not getattr(cfg, "require_bar_close_window", False):
        order = {NO_MOMENTUM: 0, NORMAL: 1, STRONG: 2, VERY_STRONG: 3}
        if order.get(str(strength).upper(), 0) >= order.get(floor, 2):
            return True, (f"early entry on {strength} momentum "
                          f"({left:.0f}s to {timeframe_label(span)} bar close)")

    if getattr(cfg, "require_bar_close_window", False):
        return False, (f"waiting for {timeframe_label(span)} bar close ({left:.0f}s left); "
                       f"entry allowed only in final {window}s window of candle")

    return False, (f"waiting for {timeframe_label(span)} bar close ({left:.0f}s left); "
                   f"{strength or NO_MOMENTUM} momentum is below {floor} floor")


# Alias for entry_timing_gate
check_entry_timing = entry_timing_gate


def detect_chop_box(df: pd.DataFrame, ind: IndicatorSet, cfg: Ema9RsiMomentumConfig) -> np.ndarray:
    """Detect flat, sideways EMA squeeze zones (Purple 'No Trade' Box in TradingView).

    A chop box occurs when:
    1. Distance between EMA 9 and EMA 20 is compressed: |EMA9 - EMA20| < chop_atr_mult * ATR.
    2. EMA 20 slope is relatively flat: |EMA20 - EMA20.shift(3)| / ATR < chop_slope_threshold.
    Returns a boolean array where True indicates the bar is inside a sideways chop box.
    """
    n = len(df)
    if not getattr(cfg, "enable_chop_filter", True) or n == 0:
        return np.zeros(n, dtype=bool)

    close_arr = np.asarray(df["close"], dtype=float)
    if ind.atr is not None and len(ind.atr) == n:
        atr_vals = np.asarray(ind.atr, dtype=float)
        atr_arr = np.where(np.isnan(atr_vals) | (atr_vals <= 0), 0.005 * close_arr, atr_vals)
    else:
        atr_arr = 0.005 * close_arr

    ema_diff = np.abs(np.asarray(ind.ema_fast, dtype=float) - np.asarray(ind.ema_slow, dtype=float))
    threshold = float(getattr(cfg, "chop_atr_mult", 0.20)) * atr_arr
    compression = ema_diff < threshold

    # Normalized slope of EMA20 over 3 bars
    slow_s = pd.Series(np.asarray(ind.ema_slow, dtype=float))
    slope = (slow_s - slow_s.shift(3)).abs().to_numpy() / (atr_arr + 1e-9)
    slope_thresh = float(getattr(cfg, "chop_slope_threshold", 0.15))
    flat_slope = np.nan_to_num(slope, nan=0.0) < slope_thresh

    return np.asarray(compression & flat_slope, dtype=bool)


def compute_adaptive_stop_loss_series(
    df: pd.DataFrame,
    ind: IndicatorSet,
    cfg: Ema9RsiMomentumConfig,
    signals: pd.Series | np.ndarray,
) -> pd.Series:
    """Calculate the ATR-normalized adaptive stop loss for each signal bar.

    - Large Candle (range >= large_candle_atr_mult * ATR):
        Anchors SL to the trigger yellow candle's Low (CE) or High (PE) with small buffer.
    - Small Candle (range < large_candle_atr_mult * ATR):
        Anchors SL to 20 EMA +/- (sl_buffer_atr_mult * ATR).
    """
    sl_series = pd.Series(np.nan, index=df.index, dtype=float)
    sig_arr = np.asarray(signals, dtype=int)
    if not getattr(cfg, "adaptive_sl_enabled", True) or not np.any(sig_arr != 0):
        return sl_series

    high_arr = np.asarray(df["high"], dtype=float) if "high" in df.columns else np.asarray(df["close"], dtype=float)
    low_arr = np.asarray(df["low"], dtype=float) if "low" in df.columns else np.asarray(df["close"], dtype=float)
    close_arr = np.asarray(df["close"], dtype=float)

    if ind.atr is not None and len(ind.atr) == len(df):
        atr_vals = np.asarray(ind.atr, dtype=float)
        atr_arr = np.where(np.isnan(atr_vals) | (atr_vals <= 0), 0.005 * close_arr, atr_vals)
    else:
        atr_arr = 0.005 * close_arr

    ema20_arr = np.asarray(ind.ema_slow, dtype=float)

    candle_range = high_arr - low_arr
    large_mult = float(getattr(cfg, "large_candle_atr_mult", 1.0))
    buffer_mult = float(getattr(cfg, "sl_buffer_atr_mult", 0.20))
    candle_buffer_mult = float(getattr(cfg, "sl_candle_buffer_atr_mult", 0.05))

    is_large = candle_range >= (large_mult * atr_arr)

    for i in np.where(sig_arr != 0)[0]:
        d = sig_arr[i]
        a = atr_arr[i]
        c = close_arr[i]
        if d == 1:  # CE
            if is_large[i]:
                sl = low_arr[i] - (candle_buffer_mult * a)
            else:
                sl = ema20_arr[i] - (buffer_mult * a)
            sl_series.iloc[i] = round(min(sl, c - (0.05 * a)), 2)
        elif d == -1:  # PE
            if is_large[i]:
                sl = high_arr[i] + (candle_buffer_mult * a)
            else:
                sl = ema20_arr[i] + (buffer_mult * a)
            sl_series.iloc[i] = round(max(sl, c + (0.05 * a)), 2)

    return sl_series


def compute_cross_signals(df: pd.DataFrame, cfg: Ema9RsiMomentumConfig) -> CrossSignals:
    ind = compute_indicator_set(df, cfg.ema_fast, cfg.ema_slow, cfg.rsi_length, cfg.rsi_ma_length)

    ema_up = crossed_above(ind.ema_fast, ind.ema_slow)
    ema_dn = crossed_below(ind.ema_fast, ind.ema_slow)
    rsi_bullish = np.asarray(ind.rsi > ind.rsi_ma, dtype=bool)
    rsi_bearish = np.asarray(ind.rsi < ind.rsi_ma, dtype=bool)

    # ── CM Ultimate MA Yellow Candle & Cross Detection ──
    cm_df = ind.cm_ma
    if cm_df is not None and "price_cross_ma2_up" in cm_df.columns:
        cr_up2 = np.asarray(cm_df["price_cross_ma2_up"], dtype=bool)
        cr_down2 = np.asarray(cm_df["price_cross_ma2_down"], dtype=bool)
        bar_hl = np.asarray(cm_df.get("bar_highlight", False), dtype=bool)
        close_arr = np.asarray(df["close"], dtype=float)
        open_arr = np.asarray(df["open"], dtype=float) if "open" in df.columns else close_arr
        fast_arr = np.asarray(ind.ema_fast, dtype=float)

        yellow_ce = cr_up2 | (bar_hl & (close_arr > fast_arr) & (close_arr >= open_arr))
        yellow_pe = cr_down2 | (bar_hl & (close_arr < fast_arr) & (close_arr <= open_arr))
    else:
        yellow_ce = np.ones(len(df), dtype=bool)
        yellow_pe = np.ones(len(df), dtype=bool)

    # ── Chop Box / Range Compression Filter (Purple "No Trade" Box) ──
    is_chop = detect_chop_box(df, ind, cfg)
    not_chop = ~is_chop

    # ── Setup A: Reversal Crossovers ──
    reversal_ce = ema_up
    reversal_pe = ema_dn

    # ── Setup B: Pullback / Trend Continuation ──
    if getattr(cfg, "enable_pullback_entries", True):
        pullback_ce = (ind.ema_fast > ind.ema_slow) & yellow_ce & (ind.rsi > 50.0) & rsi_bullish
        pullback_pe = (ind.ema_fast < ind.ema_slow) & yellow_pe & (ind.rsi < 50.0) & rsi_bearish
    else:
        pullback_ce = np.zeros(len(df), dtype=bool)
        pullback_pe = np.zeros(len(df), dtype=bool)

    # ── Trend Strength Filter (ADX >= min_adx) ──
    # Prevents entries in flat, sideways consolidation where option buyers suffer heavy theta decay.
    if cfg.enable_adx_filter and "high" in df.columns and "low" in df.columns and len(df) >= 14:
        try:
            adx_series = adx(df, window=14)
            adx_ok = np.asarray(adx_series >= cfg.min_adx, dtype=bool)
        except Exception:
            adx_ok = np.ones(len(df), dtype=bool)
    else:
        adx_ok = np.ones(len(df), dtype=bool)

    # ── Time-of-Day Decay Filter & Late Entry on ALL days (15:15 to 15:25 on VERY_STRONG) ──
    # Normal window: 09:20 - 15:15. Late window (15:15 - 15:25) allowed on ALL days if momentum is VERY_STRONG.
    if cfg.enable_time_filter:
        try:
            late_end = getattr(cfg, "late_entry_end", getattr(cfg, "expiry_late_entry_end", "15:25"))
            late_enabled = bool(getattr(cfg, "late_entry_enabled", getattr(cfg, "expiry_late_entry", True)))
            rsi_vals = np.asarray(ind.rsi, dtype=float)

            t_str = None
            if isinstance(df.index, pd.DatetimeIndex):
                t_str = df.index.strftime("%H:%M")
            else:
                date_cols = [c for c in df.columns if "date" in str(c).lower() or "time" in str(c).lower()]
                if date_cols:
                    t_str = pd.to_datetime(df[date_cols[0]]).dt.strftime("%H:%M")

            if t_str is not None:
                normal_time_ok = (t_str >= cfg.time_start) & (t_str <= cfg.time_end)
                if late_enabled:
                    in_late_window = (t_str > cfg.time_end) & (t_str <= late_end)
                    time_ok_ce = np.asarray(normal_time_ok | (in_late_window & (rsi_vals >= cfg.rsi_band_very_strong)), dtype=bool)
                    time_ok_pe = np.asarray(normal_time_ok | (in_late_window & (rsi_vals <= cfg.rsi_band_normal)), dtype=bool)
                else:
                    time_ok_ce = np.asarray(normal_time_ok, dtype=bool)
                    time_ok_pe = np.asarray(normal_time_ok, dtype=bool)
            else:
                time_ok_ce = np.ones(len(df), dtype=bool)
                time_ok_pe = np.ones(len(df), dtype=bool)
        except Exception:
            time_ok_ce = np.ones(len(df), dtype=bool)
            time_ok_pe = np.ones(len(df), dtype=bool)
    else:
        time_ok_ce = np.ones(len(df), dtype=bool)
        time_ok_pe = np.ones(len(df), dtype=bool)

    # ── EMA Touch & No-Chasing Guard ──
    if cfg.enable_touch_filter and "low" in df.columns and "high" in df.columns:
        quality_ce = assess_entry_quality(df, ind, cfg, np.where(ema_up, 1, 0))
        quality_pe = assess_entry_quality(df, ind, cfg, np.where(ema_dn, -1, 0))
        touch_ce = quality_ce.take
        touch_pe = quality_pe.take
    else:
        touch_ce = np.ones(len(df), dtype=bool)
        touch_pe = np.ones(len(df), dtype=bool)

    # ── Setup A (HIGHEST PRIORITY): 9 & 20 EMA Directional Crossover ──
    # User Rule (2026-10-02): Fresh 9 & 20 EMA crossovers with RSI confirmation
    # have HIGHEST PRIORITY. They represent the primary momentum initiation point
    # for option buying and execute without being blocked by restrictive touch filters.
    rsi_vals = np.asarray(ind.rsi, dtype=float)
    crossover_ce = ema_up & rsi_bullish & (rsi_vals >= 48.0)
    crossover_pe = ema_dn & rsi_bearish & (rsi_vals <= 52.0)

    # ── Setup B (Secondary Priority): Pullback / Retest with Yellow Candle ──
    if getattr(cfg, "enable_pullback_entries", True):
        pullback_ce = (ind.ema_fast > ind.ema_slow) & yellow_ce & (ind.rsi > 50.0) & rsi_bullish & not_chop & touch_ce & adx_ok
        pullback_pe = (ind.ema_fast < ind.ema_slow) & yellow_pe & (ind.rsi < 50.0) & rsi_bearish & not_chop & touch_pe & adx_ok
    else:
        pullback_ce = np.zeros(len(df), dtype=bool)
        pullback_pe = np.zeros(len(df), dtype=bool)

    # ── Setup C: CM Yellow Candle Breakdown / Breakout ──
    # User Rule (2026-10-02): When price breaks through the EMA cluster with a
    # CM Ultimate MA yellow candle (cr_down2 / cr_up2), this signals a decisive
    # momentum shift. ADX is deliberately excluded because ADX is a LAGGING
    # indicator — at the start of breakdown moves (consolidation → directional),
    # ADX is naturally low. Requiring high ADX misses the exact entry the user
    # expects (e.g. Oct 1 12:00: ADX=16.06, min_adx=18.0, but 350-pt drop
    # followed). Touch filter is also bypassed since the yellow candle crossing
    # through EMA IS the touch/breakdown confirmation.
    if cm_df is not None and "price_cross_ma2_down" in cm_df.columns:
        _rsi_prev = pd.Series(rsi_vals).shift(1).bfill().to_numpy()
        _rsi_falling = rsi_vals < _rsi_prev
        _rsi_rising  = rsi_vals > _rsi_prev

        cm_breakdown_pe = (
            cr_down2
            & (np.asarray(ind.ema_fast) <= np.asarray(ind.ema_slow))
            & (rsi_vals < 50.0)
            & (rsi_bearish | _rsi_falling)
            & not_chop
        )
        cm_breakout_ce = (
            cr_up2
            & (np.asarray(ind.ema_fast) >= np.asarray(ind.ema_slow))
            & (rsi_vals > 50.0)
            & (rsi_bullish | _rsi_rising)
            & not_chop
        )
    else:
        cm_breakdown_pe = np.zeros(len(df), dtype=bool)
        cm_breakout_ce = np.zeros(len(df), dtype=bool)

    # ── Institutional Exhaustion Filter (RSI Guard) ──
    # Option buyers must never buy CE into extreme overbought exhaustion (RSI > 75)
    # or PE into extreme oversold exhaustion (RSI < 25), where mean-reversion & theta crush options.
    not_overbought = rsi_vals <= getattr(cfg, "rsi_overbought_cap", 75.0)
    not_oversold = rsi_vals >= getattr(cfg, "rsi_oversold_floor", 25.0)

    # Valid candidates: Highest priority Crossover | CM Breakdown | Pullback
    candidate_ce = (crossover_ce | cm_breakout_ce | pullback_ce) & not_overbought
    candidate_pe = (crossover_pe | cm_breakdown_pe | pullback_pe) & not_oversold

    bullish = candidate_ce & time_ok_ce
    bearish = candidate_pe & time_ok_pe

    # ── Warm-up guard ──────
    warmup_bars = max(cfg.ema_slow, cfg.rsi_length + cfg.rsi_ma_length)
    if len(bullish) > warmup_bars:
        bullish[:warmup_bars] = False
        bearish[:warmup_bars] = False
    else:
        bullish[:] = False
        bearish[:] = False

    raw_signals = np.select([bearish, bullish], [-1, 1], default=0)
    sl_series = compute_adaptive_stop_loss_series(df, ind, cfg, raw_signals)

    return CrossSignals(
        bullish=bullish,
        bearish=bearish,
        indicators=ind,
        stop_loss=sl_series,
        is_chop=is_chop,
    )


def compute_reversal_signals(df: pd.DataFrame, cfg: Ema9RsiMomentumConfig) -> CrossSignals:
    """The EMA/RSI reversal, WITHOUT the entry-selection filters.

    ``compute_cross_signals`` folds ADX, the trading-hours window and the
    EMA-touch guard into its ``bullish``/``bearish`` arrays. Those three exist
    to make ENTRIES selective -- take only clean setups. An exit needs the
    opposite disposition: leave whenever the thesis breaks.

    Sharing one array gave the exit the entry's reluctance. Measured over 578
    NIFTY trading days, **62% of genuine reversals never reached the exit
    test** -- 390 of 868 bearish ones blocked by ADX alone, and after 15:00 the
    time window made an exit impossible for the rest of the session, precisely
    when an intraday option position most needs closing.

    Worse in kind than in number: ADX below its threshold means sideways chop,
    which is exactly the regime where an option buyer bleeds theta fastest and
    can least afford to be stuck.

    This function keeps only the reversal itself -- the EMA crossover plus RSI
    confirmation, the owner's stated rule -- and the warm-up guard, which is a
    correctness requirement rather than a selection filter. ``compute_cross_signals``
    is deliberately left untouched, so ENTRY behaviour is bit-for-bit unchanged.
    """
    ind = compute_indicator_set(df, cfg.ema_fast, cfg.ema_slow, cfg.rsi_length, cfg.rsi_ma_length)

    ema_up = crossed_above(ind.ema_fast, ind.ema_slow)
    ema_dn = crossed_below(ind.ema_fast, ind.ema_slow)
    rsi_bullish = np.asarray(ind.rsi > ind.rsi_ma, dtype=bool)
    rsi_bearish = np.asarray(ind.rsi < ind.rsi_ma, dtype=bool)

    bullish = ema_up & rsi_bullish
    bearish = ema_dn & rsi_bearish

    # Same warm-up mask as compute_cross_signals: RSI and its EMA are both
    # still converging early on and can "cross" from that transient alone.
    warmup_bars = max(cfg.ema_slow, cfg.rsi_length + cfg.rsi_ma_length)
    if len(bullish) > warmup_bars:
        bullish[:warmup_bars] = False
        bearish[:warmup_bars] = False
    else:
        bullish[:] = False
        bearish[:] = False

    return CrossSignals(bullish=bullish, bearish=bearish, indicators=ind)


def classify_momentum_strength(rsi_value: float, direction: int, cfg: Ema9RsiMomentumConfig) -> str:
    """Current RSI-level momentum-strength label for the given direction.

    Purely descriptive of *where RSI currently sits*, per the spec's own
    framing ("these levels indicate momentum strength, not independent
    entry signals") — not a stateful "has it crossed" tracker. Use
    :func:`momentum_strength_upgrade` for the edge-triggered "just crossed
    a new band" version used in exit-time logging.
    """
    if rsi_value is None or (isinstance(rsi_value, float) and np.isnan(rsi_value)):
        return NO_MOMENTUM

    if direction == 1:  # CE / bullish
        if rsi_value >= cfg.rsi_band_very_strong:
            return VERY_STRONG
        if rsi_value >= cfg.rsi_band_strong:
            return STRONG
        if rsi_value >= cfg.rsi_band_normal:
            return NORMAL
        return NO_MOMENTUM
    elif direction == -1:  # PE / bearish
        if rsi_value <= cfg.rsi_band_normal:
            return VERY_STRONG
        if rsi_value <= cfg.rsi_band_strong:
            return STRONG
        if rsi_value <= cfg.rsi_band_very_strong:
            return NORMAL
        return NO_MOMENTUM
    return NO_MOMENTUM


def momentum_strength_upgrade(rsi_series: pd.Series, direction: int, cfg: Ema9RsiMomentumConfig) -> str | None:
    """Return the label of a momentum-strength band the RSI *just crossed
    into* on the last bar (in the given direction), or ``None`` if no band
    was freshly crossed this bar. Used only for richer "why" logging on an
    already-open position — never gates entry or exit on its own.
    """
    if direction == 1:
        crossings = [
            (cfg.rsi_band_very_strong, VERY_STRONG),
            (cfg.rsi_band_strong, STRONG),
            (cfg.rsi_band_normal, NORMAL),
        ]
        for level, label in crossings:
            if crossed_above_level(rsi_series, level)[-1]:
                return label
    elif direction == -1:
        crossings = [
            (cfg.rsi_band_normal, VERY_STRONG),
            (cfg.rsi_band_strong, STRONG),
            (cfg.rsi_band_very_strong, NORMAL),
        ]
        for level, label in crossings:
            if crossed_below_level(rsi_series, level)[-1]:
                return label
    return None


def build_entry_signal_series(df: pd.DataFrame, cfg: Ema9RsiMomentumConfig, edge_trigger) -> tuple[pd.Series, CrossSignals]:
    """The registry-facing signal series: ``1`` (CE), ``-1`` (PE), ``0``.

    ``edge_trigger`` is injected (rather than imported here) so this module
    stays a pure function of its inputs and shares the exact same
    livelock-safe implementation as every other strategy — see
    ``trading_bot/strategies/_signal_utils.py``.
    """
    cross = compute_cross_signals(df, cfg)
    signals = pd.Series(
        np.select([cross.bearish, cross.bullish], [-1, 1], default=0),
        index=df.index,
        dtype=int,
    )
    edge_signals = edge_trigger(signals)
    sl_series = compute_adaptive_stop_loss_series(df, cross.indicators, cfg, edge_signals)
    updated_cross = CrossSignals(
        bullish=np.asarray(edge_signals == 1),
        bearish=np.asarray(edge_signals == -1),
        indicators=cross.indicators,
        stop_loss=sl_series,
        is_chop=cross.is_chop,
    )
    return edge_signals, updated_cross
