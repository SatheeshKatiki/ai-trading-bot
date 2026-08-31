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

def compute_cross_signals(df: pd.DataFrame, cfg: Ema9RsiMomentumConfig) -> CrossSignals:
    ind = compute_indicator_set(df, cfg.ema_fast, cfg.ema_slow, cfg.rsi_length, cfg.rsi_ma_length)

    ema_up = crossed_above(ind.ema_fast, ind.ema_slow)
    ema_dn = crossed_below(ind.ema_fast, ind.ema_slow)
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
        max_ema = np.maximum(ind.ema_fast, ind.ema_slow)
        min_ema = np.minimum(ind.ema_fast, ind.ema_slow)
        buffer = df["close"] * 0.0006  # ~14 pts on Nifty 24000
        touch_ce = np.asarray(df["low"] <= (max_ema + buffer), dtype=bool)
        touch_pe = np.asarray(df["high"] >= (min_ema - buffer), dtype=bool)
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
