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

#: Momentum-strength labels, weakest to strongest.
NO_MOMENTUM = "NONE"
NORMAL = "NORMAL"
STRONG = "STRONG"
VERY_STRONG = "VERY_STRONG"


@dataclass(frozen=True)
class CrossSignals:
    """Per-bar boolean arrays the entry and exit rules are both built from."""

    bullish: np.ndarray  # EMA9 crossed above EMA20 AND RSI crossed above RSI-EMA20 (same bar)
    bearish: np.ndarray  # EMA9 crossed below EMA20 AND RSI crossed below RSI-EMA20 (same bar)
    indicators: IndicatorSet


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


def _with_anticipation(df: pd.DataFrame, ind: IndicatorSet,
                       cfg: Ema9RsiMomentumConfig,
                       ema_up: np.ndarray, ema_dn: np.ndarray):
    """Optionally treat an imminent crossover as a crossover.

    The owner asked (2026-09-22) for a signal when the lines have not crossed
    yet but look like they will within the next candle or two. It is OFF by
    default, because it measured as the most damaging change tried on this
    strategy: NIFTY +Rs.11,150 -> -Rs.64,551 at one bar of anticipation, and
    -Rs.98,964 at two; SENSEX -Rs.37,841 -> -Rs.56,247 and -Rs.63,470. Every
    tightness setting tried (gap below 0.15 / 0.30 / 0.50 x ATR) and an extra
    RSI-strength requirement were all worse, on both indices.

    The reason is structural and not a tuning problem: EMA9 approaches EMA20
    far more often than it crosses it. Anticipating roughly doubles the trade
    count and nearly all the extra trades are approaches that failed.

    Kept because the owner asked for it and may want to see it on a different
    instrument or timeframe. Guarded so that even when enabled it fires only
    once per approach, only while the lines are genuinely close (a fraction
    of ATR apart), and only while the gap is still narrowing.
    """
    bars = int(getattr(cfg, "anticipate_cross_bars", 0) or 0)
    if bars <= 0:
        return ema_up, ema_dn

    fast = np.asarray(ind.ema_fast, dtype=float)
    slow = np.asarray(ind.ema_slow, dtype=float)
    gap = fast - slow
    step = np.r_[0.0, np.diff(gap)]

    high = np.asarray(df["high"], dtype=float)
    low = np.asarray(df["low"], dtype=float)
    close = np.asarray(df["close"], dtype=float)
    prev = np.r_[close[0], close[:-1]]
    true_range = np.maximum(high - low, np.maximum(np.abs(high - prev), np.abs(low - prev)))
    atr = pd.Series(true_range).ewm(alpha=1 / 14, adjust=False).mean().to_numpy()
    close_enough = np.abs(gap) <= float(getattr(cfg, "anticipate_max_gap_atr", 0.30)) * atr

    soon_up = (gap < 0) & (step > 0) & ((gap + step * bars) > 0) & close_enough
    soon_dn = (gap > 0) & (step < 0) & ((gap + step * bars) < 0) & close_enough
    # once per approach, not on every bar of it
    soon_up &= ~np.r_[False, soon_up[:-1]]
    soon_dn &= ~np.r_[False, soon_dn[:-1]]

    return (np.asarray(ema_up, dtype=bool) | np.nan_to_num(soon_up).astype(bool),
            np.asarray(ema_dn, dtype=bool) | np.nan_to_num(soon_dn).astype(bool))



PRIORITY_BREAKAWAY = "BREAKAWAY"


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


#: Entry priority. HIGH is the owner's first preference (a body touch), MEDIUM
#: a wick touch that earned its place, LOW one that did not.
PRIORITY_HIGH = "HIGH"
PRIORITY_MEDIUM = "MEDIUM"
PRIORITY_LOW = "LOW"
PRIORITY_NONE = "NONE"


@dataclass(frozen=True)
class EntryQuality:
    """Per-bar entry grading: how good the touch is, and whether to take it."""

    priority: np.ndarray      # PRIORITY_* label per bar
    take: np.ndarray          # bool: this bar's signal is worth acting on
    trend_agrees: np.ndarray  # EMA20 sloping with the trade
    rsi_separated: np.ndarray # RSI clear of its own average


def assess_entry_quality(df: pd.DataFrame, ind: IndicatorSet,
                         cfg: Ema9RsiMomentumConfig,
                         direction: np.ndarray) -> EntryQuality:
    """Grade each bar's entry, the way the owner asked the bot to decide.

    A body touch is first preference and is taken on its own -- the candle
    committed through both averages, there is nothing left to confirm.

    A wick touch is second preference: the candle only grazed the cluster, so
    the bot looks for two independent reasons to believe the move anyway --
    the EMA20 sloping the same way as the trade, and RSI genuinely separated
    from its own average rather than hugging it. Both, and the entry is taken
    at MEDIUM. Neither or one, and it is skipped at LOW.

    Measured on the wick-only signals over 2024-01-01..2026-09-21, costs from
    real option premiums: taking every wick cost Rs.268/trade on NIFTY and
    Rs.169 on SENSEX; requiring both confirmations brought that to Rs.17 and
    Rs.44. Against taking every wick it won 11/11 NIFTY and 7/11 SENSEX
    quarters, fixed, with no per-period fitting. It does not make wick trades
    profitable -- it stops them paying for the body trades.
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

    gap = np.abs(np.asarray(ind.rsi, dtype=float) - np.asarray(ind.rsi_ma, dtype=float))
    rsi_separated = np.nan_to_num(gap, nan=0.0) >= float(getattr(cfg, "wick_min_rsi_gap", 3.0))

    wick_only = touch.by_wick & ~touch.by_body
    if getattr(cfg, "wick_requires_confirmation", True):
        wick_ok = wick_only & trend_agrees & rsi_separated
    else:
        wick_ok = wick_only

    # A cross whose candle has left the cluster is normally a chase. A
    # decisive one that closes at its extreme is the exception -- see
    # `_breakaway`. Off unless the owner switches it on.
    breakaway = _breakaway(df, cfg, direction) & ~touch.by_wick

    priority = np.full(n, PRIORITY_NONE, dtype=object)
    priority[wick_only] = PRIORITY_LOW
    priority[breakaway] = PRIORITY_BREAKAWAY
    priority[wick_ok] = PRIORITY_MEDIUM
    priority[touch.by_body] = PRIORITY_HIGH

    # "take" still honours the configured touch mode: in "body" mode a wick
    # never qualifies however well confirmed, and in "legacy" mode the old
    # one-sided check decides and no grading applies.
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
    order = {NO_MOMENTUM: 0, NORMAL: 1, STRONG: 2, VERY_STRONG: 3}
    if order.get(str(strength).upper(), 0) >= order.get(floor, 2):
        return True, (f"early entry on {strength} momentum "
                      f"({left:.0f}s to {timeframe_label(span)} bar close)")

    return False, (f"waiting for {timeframe_label(span)} bar close ({left:.0f}s left); "
                   f"momentum {strength or NO_MOMENTUM} is below {floor}")


def compute_cross_signals(df: pd.DataFrame, cfg: Ema9RsiMomentumConfig) -> CrossSignals:
    ind = compute_indicator_set(df, cfg.ema_fast, cfg.ema_slow, cfg.rsi_length, cfg.rsi_ma_length)

    ema_up = crossed_above(ind.ema_fast, ind.ema_slow)
    ema_dn = crossed_below(ind.ema_fast, ind.ema_slow)
    ema_up, ema_dn = _with_anticipation(df, ind, cfg, ema_up, ema_dn)
    rsi_bullish = np.asarray(ind.rsi > ind.rsi_ma, dtype=bool)
    rsi_bearish = np.asarray(ind.rsi < ind.rsi_ma, dtype=bool)

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

    # ── Time-of-Day Decay Filter (09:25 AM to 15:00 PM) ──
    # Avoids opening fake breakouts (09:15-09:25) and last 30-min theta crush (15:00-15:30).
    if cfg.enable_time_filter:
        try:
            if isinstance(df.index, pd.DatetimeIndex):
                t_str = df.index.strftime("%H:%M")
                time_ok = np.asarray((t_str >= cfg.time_start) & (t_str <= cfg.time_end), dtype=bool)
            else:
                date_cols = [c for c in df.columns if "date" in str(c).lower() or "time" in str(c).lower()]
                if date_cols:
                    t_str = pd.to_datetime(df[date_cols[0]]).dt.strftime("%H:%M")
                    time_ok = np.asarray((t_str >= cfg.time_start) & (t_str <= cfg.time_end), dtype=bool)
                else:
                    time_ok = np.ones(len(df), dtype=bool)
        except Exception:
            time_ok = np.ones(len(df), dtype=bool)
    else:
        time_ok = np.ones(len(df), dtype=bool)

    # ── EMA Touch & No-Chasing Guard ──
    # Prevents late entries where the candle is already flying far away from the EMA line.
    # The breakout candle MUST touch or be rooted in the EMA cluster.
    if cfg.enable_touch_filter and "low" in df.columns and "high" in df.columns:
        # Grade each candidate bar rather than just pass/fail it: a body touch
        # is taken outright, a wick touch only once it has confirmed itself.
        # The direction a bar would trade decides which way "the trend agrees"
        # has to point, so the grading is done per side.
        quality_ce = assess_entry_quality(df, ind, cfg, np.where(ema_up, 1, 0))
        quality_pe = assess_entry_quality(df, ind, cfg, np.where(ema_dn, -1, 0))
        touch_ce = quality_ce.take
        touch_pe = quality_pe.take
    else:
        touch_ce = np.ones(len(df), dtype=bool)
        touch_pe = np.ones(len(df), dtype=bool)

    bullish = ema_up & rsi_bullish & adx_ok & time_ok & touch_ce
    bearish = ema_dn & rsi_bearish & adx_ok & time_ok & touch_pe

    # ── Warm-up guard (found during 1-year NIFTY backtest review) ──────
    # Neither `shared.indicators.rsi()` nor `ema()` pad the warm-up period
    # with NaN when their input has no leading NaN of its own (rsi.py's
    # own docstring: "the first `window` non-NaN values ... come from a
    # still-converging average ... callers that need those excluded must
    # mask them explicitly; this function does not"). `rsi_ma` compounds
    # this: it's an EMA *of* an already-unconverged RSI, so for the first
    # few bars both lines can momentarily collapse toward 0 and "cross"
    # purely from that transient, not a real signal — confirmed live on
    # this exact NIFTY dataset (bar index 3, RSI jumping 0.00 -> 65.29
    # against a still-near-0 rsi_ma). Masking crossovers until RSI has had
    # `rsi_length` bars to compute plus `rsi_ma_length` more for its own
    # EMA to converge (also compared against the EMA20/9 warm-up need)
    # removes exactly this artifact without changing any post-warm-up
    # signal — a bar that would fire once converged still fires.
    warmup_bars = max(cfg.ema_slow, cfg.rsi_length + cfg.rsi_ma_length)
    if len(bullish) > warmup_bars:
        bullish[:warmup_bars] = False
        bearish[:warmup_bars] = False
    else:
        bullish[:] = False
        bearish[:] = False

    return CrossSignals(
        bullish=bullish,
        bearish=bearish,
        indicators=ind,
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
    return edge_trigger(signals), cross
