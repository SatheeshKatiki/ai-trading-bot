"""Signal & Price Action Engine for EMA 9 / Fibo OTE Momentum Pro Strategy.

Implements Pure Price Action as the Primary Driver:
- Market Structure Shift (BOS / MSS) & Swing Detection.
- Fibonacci Optimal Trade Entry (0.62 - 0.705 - 0.79) with Candlestick Rejection Wick Trigger.
- Indicators (EMA 9/20, RSI, ADX) act purely as supportive sanity filters.
- Structural Swing Trailing, Structure Break Exits, and Exhaustion Wick Target Exits.
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass
from typing import Dict, Optional, Tuple

import numpy as np
import pandas as pd

from shared.indicators import adx
from shared.timeframes import seconds_to_bar_close, timeframe_label
from trading_bot.strategies.ema9_fibo_smc_momentum.config import Ema9FiboSmcMomentumConfig
from trading_bot.strategies.ema9_fibo_smc_momentum.indicators import (
    IndicatorSet,
    calculate_fibonacci_levels,
    compute_indicator_set,
    crossed_above,
    crossed_below,
    detect_exhaustion_wick,
    detect_rejection_wick,
    detect_rsi_divergence,
    detect_structure_swings,
    detect_swing_points,
    is_in_fibo_ote_zone,
)

BODY = "body"
WICK = "wick"

PRIORITY_HIGH = "HIGH"
PRIORITY_MEDIUM = "MEDIUM"
PRIORITY_LOW = "LOW"
PRIORITY_NONE = "NONE"
PRIORITY_BREAKAWAY = "BREAKAWAY"


@dataclass(frozen=True)
class CrossSignals:
    """The raw boolean cross events plus their indicator & price action snapshot."""
    bullish: np.ndarray
    bearish: np.ndarray
    indicators: IndicatorSet
    stop_loss: Optional[pd.Series] = None
    is_chop: Optional[np.ndarray] = None
    fibo_targets: Optional[Dict[str, float]] = None
    higher_lows: Optional[np.ndarray] = None
    lower_highs: Optional[np.ndarray] = None


@dataclass(frozen=True)
class PriceActionExitResult:
    """Verdict from the Price Action Exit Engine."""
    should_exit: bool
    exit_reason: str
    urgency: float = 0.5
    fibo_stage: int = 0


def detect_chop_box(
    df: pd.DataFrame,
    ind: IndicatorSet,
    cfg: Ema9FiboSmcMomentumConfig,
) -> np.ndarray:
    """Suppresses entries when moving averages are compressed and flat."""
    if not getattr(cfg, "enable_chop_filter", True):
        return np.zeros(len(df), dtype=bool)

    close_arr = np.asarray(df["close"], dtype=float)
    if ind.atr is not None and len(ind.atr) == len(df):
        atr_vals = np.asarray(ind.atr, dtype=float)
        atr_arr = np.where(np.isnan(atr_vals) | (atr_vals <= 0), 0.005 * close_arr, atr_vals)
    else:
        atr_arr = 0.005 * close_arr

    ema_diff = np.abs(np.asarray(ind.ema_fast, dtype=float) - np.asarray(ind.ema_slow, dtype=float))
    threshold = float(getattr(cfg, "chop_atr_mult", 0.20)) * atr_arr
    compression = ema_diff < threshold

    slow_s = pd.Series(np.asarray(ind.ema_slow, dtype=float))
    slope = (slow_s - slow_s.shift(3)).abs().to_numpy() / (atr_arr + 1e-9)
    slope_thresh = float(getattr(cfg, "chop_slope_threshold", 0.15))
    flat_slope = np.nan_to_num(slope, nan=0.0) < slope_thresh

    return np.asarray(compression & flat_slope, dtype=bool)


def classify_momentum_strength(
    rsi_val: float,
    direction: int,
    cfg: Ema9FiboSmcMomentumConfig,
) -> str:
    """Labels momentum strength from RSI value and trade direction."""
    if direction == 1:
        if rsi_val >= cfg.rsi_band_very_strong:
            return "VERY_STRONG"
        if rsi_val >= cfg.rsi_band_strong:
            return "STRONG"
        if rsi_val >= cfg.rsi_band_normal:
            return "NORMAL"
        return "WEAK"
    elif direction == -1:
        if rsi_val <= (100.0 - cfg.rsi_band_very_strong):
            return "VERY_STRONG"
        if rsi_val <= (100.0 - cfg.rsi_band_strong):
            return "STRONG"
        if rsi_val <= (100.0 - cfg.rsi_band_normal):
            return "NORMAL"
        return "WEAK"
    return "UNKNOWN"


def compute_adaptive_stop_loss_series(
    df: pd.DataFrame,
    ind: IndicatorSet,
    cfg: Ema9FiboSmcMomentumConfig,
    signals: pd.Series | np.ndarray,
    swing_high: np.ndarray,
    swing_low: np.ndarray,
    rejection_ce: np.ndarray,
    rejection_pe: np.ndarray,
) -> pd.Series:
    """Calculates structural ATR & Fibonacci-anchored stop loss series."""
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
    fibo_buffer_mult = float(getattr(cfg, "fibo_sl_buffer_atr_mult", 0.25))

    for i in np.where(sig_arr != 0)[0]:
        d = sig_arr[i]
        a = atr_arr[i]
        c = close_arr[i]
        sh = swing_high[i]
        sl_val = swing_low[i]

        if d == 1:  # CE
            # If rejection wick is present, anchor SL strictly to the wick low
            if rejection_ce[i]:
                structural_sl = low_arr[i] - (0.10 * a)
            else:
                span = sh - sl_val
                fibo_79 = sh - 0.79 * span if (np.isfinite(span) and span > 0) else sl_val
                structural_sl = min(fibo_79, sl_val) - (fibo_buffer_mult * a)

            ema_sl = ema20_arr[i] - (0.40 * a) if np.isfinite(ema20_arr[i]) else structural_sl
            candidates = [s for s in (structural_sl, ema_sl) if np.isfinite(s)]
            final_sl = max(candidates) if candidates else c - (1.0 * a)
            safe_sl = min(final_sl, c - (0.10 * a))
            sl_series.iloc[i] = round(float(safe_sl), 2)

        elif d == -1:  # PE
            if rejection_pe[i]:
                structural_sl = high_arr[i] + (0.10 * a)
            else:
                span = sh - sl_val
                fibo_79 = sl_val + 0.79 * span if (np.isfinite(span) and span > 0) else sh
                structural_sl = max(fibo_79, sh) + (fibo_buffer_mult * a)

            ema_sl = ema20_arr[i] + (0.40 * a) if np.isfinite(ema20_arr[i]) else structural_sl
            candidates = [s for s in (structural_sl, ema_sl) if np.isfinite(s)]
            final_sl = min(candidates) if candidates else c + (1.0 * a)
            safe_sl = max(final_sl, c + (0.10 * a))
            sl_series.iloc[i] = round(float(safe_sl), 2)

    return sl_series


def compute_cross_signals(
    df: pd.DataFrame,
    cfg: Ema9FiboSmcMomentumConfig,
) -> CrossSignals:
    """Computes high-probability entries with Pure Price Action as the primary driver."""
    ind = compute_indicator_set(df, cfg.ema_fast, cfg.ema_slow, cfg.rsi_length, cfg.rsi_ma_length)

    ema_up = crossed_above(ind.ema_fast, ind.ema_slow)
    ema_dn = crossed_below(ind.ema_fast, ind.ema_slow)
    rsi_bullish = np.asarray(ind.rsi > ind.rsi_ma, dtype=bool)
    rsi_bearish = np.asarray(ind.rsi < ind.rsi_ma, dtype=bool)

    high_arr = np.asarray(df["high"], dtype=float) if "high" in df.columns else np.asarray(df["close"], dtype=float)
    low_arr = np.asarray(df["low"], dtype=float) if "low" in df.columns else np.asarray(df["close"], dtype=float)
    close_arr = np.asarray(df["close"], dtype=float)
    open_arr = np.asarray(df["open"], dtype=float) if "open" in df.columns else close_arr

    # ── CM Ultimate MA Yellow Candle & Cross Detection ──
    cm_df = ind.cm_ma
    if cm_df is not None and "price_cross_ma2_up" in cm_df.columns:
        cr_up2 = np.asarray(cm_df["price_cross_ma2_up"], dtype=bool)
        cr_down2 = np.asarray(cm_df["price_cross_ma2_down"], dtype=bool)
        bar_hl = np.asarray(cm_df.get("bar_highlight", False), dtype=bool)
        fast_arr = np.asarray(ind.ema_fast, dtype=float)

        yellow_ce = cr_up2 | (bar_hl & (close_arr > fast_arr) & (close_arr >= open_arr))
        yellow_pe = cr_down2 | (bar_hl & (close_arr < fast_arr) & (close_arr <= open_arr))
    else:
        cr_up2 = np.zeros(len(df), dtype=bool)
        cr_down2 = np.zeros(len(df), dtype=bool)
        yellow_ce = np.ones(len(df), dtype=bool)
        yellow_pe = np.ones(len(df), dtype=bool)

    # ── Chop Box / Range Compression Filter ──
    is_chop = detect_chop_box(df, ind, cfg)
    not_chop = ~is_chop

    # ── Pillar 1: Time-of-Day & Opening Range Filter (09:30 - 15:15) ──
    time_ok_ce = np.ones(len(df), dtype=bool)
    time_ok_pe = np.ones(len(df), dtype=bool)
    if cfg.enable_time_filter:
        try:
            t_str = None
            if isinstance(df.index, pd.DatetimeIndex):
                t_str = df.index.strftime("%H:%M")
            else:
                date_cols = [c for c in df.columns if "date" in str(c).lower() or "time" in str(c).lower()]
                if date_cols:
                    t_str = pd.to_datetime(df[date_cols[0]]).dt.strftime("%H:%M")

            if t_str is not None:
                normal_time_ok = (t_str >= cfg.time_start) & (t_str <= cfg.time_end)
                late_window = (t_str > cfg.time_end) & (t_str <= cfg.late_entry_end)
                rsi_vals = np.asarray(ind.rsi, dtype=float)
                time_ok_ce = np.asarray(normal_time_ok | (late_window & (rsi_vals >= cfg.rsi_band_very_strong)), dtype=bool)
                time_ok_pe = np.asarray(normal_time_ok | (late_window & (rsi_vals <= cfg.rsi_band_normal)), dtype=bool)
        except Exception:
            pass

    # ── Trend Strength Filter (ADX >= min_adx) ──
    try:
        adx_series = adx(df, window=14)
        adx_ok = np.asarray(adx_series >= cfg.min_adx, dtype=bool)
    except Exception:
        adx_series = pd.Series(25.0, index=df.index)
        adx_ok = np.ones(len(df), dtype=bool)

    # ── Price Action Pillar: Swing Structure & Rejection Wicks ──
    swing_lookback = int(getattr(cfg, "fibo_swing_lookback", 15))
    swing_high, swing_low = detect_swing_points(high_arr, low_arr, lookback=swing_lookback)
    hl_arr, lh_arr, bos_bull, bos_bear = detect_structure_swings(
        high_arr, low_arr, close_arr, lookback=cfg.swing_structure_lookback
    )

    rejection_ce = detect_rejection_wick(high_arr, low_arr, open_arr, close_arr, direction=1, min_wick_ratio=cfg.min_rejection_wick_ratio)
    rejection_pe = detect_rejection_wick(high_arr, low_arr, open_arr, close_arr, direction=-1, min_wick_ratio=cfg.min_rejection_wick_ratio)

    fibo_ote_ce = np.ones(len(df), dtype=bool)
    fibo_ote_pe = np.ones(len(df), dtype=bool)
    if getattr(cfg, "enable_fibo_ote_filter", True):
        for i in range(len(df)):
            sh = swing_high[i]
            sl = swing_low[i]
            fibo_ote_ce[i] = is_in_fibo_ote_zone(
                high_arr[i], low_arr[i], close_arr[i], sh, sl, direction=1,
                ote_low=cfg.fibo_ote_low, ote_high=cfg.fibo_ote_high
            )
            fibo_ote_pe[i] = is_in_fibo_ote_zone(
                high_arr[i], low_arr[i], close_arr[i], sh, sl, direction=-1,
                ote_low=cfg.fibo_ote_low, ote_high=cfg.fibo_ote_high
            )

    rsi_vals = np.asarray(ind.rsi, dtype=float)
    not_overbought = rsi_vals <= getattr(cfg, "rsi_overbought_cap", 75.0)
    not_oversold = rsi_vals >= getattr(cfg, "rsi_oversold_floor", 25.0)

    # ── Setup 1 (Pure Price Action Primary): Fibo OTE + Wick Absorption ──
    if getattr(cfg, "price_action_primary", True):
        # Entry requires testing the OTE zone with rejection wick or yellow continuation candle
        pa_entry_ce = (
            fibo_ote_ce
            & (rejection_ce | yellow_ce)
            & (close_arr >= open_arr)
            & (ind.rsi >= 46.0)
            & (np.asarray(ind.ema_fast) >= np.asarray(ind.ema_slow) - (0.002 * close_arr))
            & not_chop
            & not_overbought
        )
        pa_entry_pe = (
            fibo_ote_pe
            & (rejection_pe | yellow_pe)
            & (close_arr <= open_arr)
            & (ind.rsi <= 54.0)
            & (np.asarray(ind.ema_fast) <= np.asarray(ind.ema_slow) + (0.002 * close_arr))
            & not_chop
            & not_oversold
        )
    else:
        pa_entry_ce = np.zeros(len(df), dtype=bool)
        pa_entry_pe = np.zeros(len(df), dtype=bool)

    # ── Setup 2: Classical 9/20 EMA Crossover with RSI confirmation ──
    crossover_ce = ema_up & rsi_bullish & (rsi_vals >= 48.0)
    crossover_pe = ema_dn & rsi_bearish & (rsi_vals <= 52.0)

    # ── Setup 3: CM Breakdown / Breakout ──
    if cm_df is not None and "price_cross_ma2_down" in cm_df.columns:
        cm_breakdown_pe = cr_down2 & (np.asarray(ind.ema_fast) <= np.asarray(ind.ema_slow)) & (rsi_vals < 50.0) & not_chop
        cm_breakout_ce = cr_up2 & (np.asarray(ind.ema_fast) >= np.asarray(ind.ema_slow)) & (rsi_vals > 50.0) & not_chop
    else:
        cm_breakdown_pe = np.zeros(len(df), dtype=bool)
        cm_breakout_ce = np.zeros(len(df), dtype=bool)

    # ── Setup 4: High-Velocity Momentum Breakout Expansion (Runaway Trend) ──
    # When market enters a vertical runaway expansion (like a 400-pt trend day),
    # price never retraces to Fibo OTE and RSI surges into 75-85+.
    # This setup catches the expansion when ADX is strong and price breaks structure.
    if getattr(cfg, "enable_momentum_breakout", True):
        prev_swing_high = np.r_[high_arr[0], swing_high[:-1]]
        prev_swing_low = np.r_[low_arr[0], swing_low[:-1]]
        min_b_adx = float(getattr(cfg, "min_breakout_adx", 20.0))
        min_b_rsi = float(getattr(cfg, "min_breakout_rsi", 55.0))

        breakout_ce = (
            (bos_bull | (close_arr > prev_swing_high))
            & (close_arr > np.asarray(ind.ema_fast))
            & (np.asarray(ind.ema_fast) >= np.asarray(ind.ema_slow))
            & (rsi_vals >= min_b_rsi)
            & (close_arr >= open_arr)
            & (adx_ok & (adx_series >= min_b_adx))
            & not_chop
        )
        breakout_pe = (
            (bos_bear | (close_arr < prev_swing_low))
            & (close_arr < np.asarray(ind.ema_fast))
            & (np.asarray(ind.ema_fast) <= np.asarray(ind.ema_slow))
            & (rsi_vals <= (100.0 - min_b_rsi))
            & (close_arr <= open_arr)
            & (adx_ok & (adx_series >= min_b_adx))
            & not_chop
        )
    else:
        breakout_ce = np.zeros(len(df), dtype=bool)
        breakout_pe = np.zeros(len(df), dtype=bool)

    # Combine setups
    if getattr(cfg, "price_action_primary", True):
        # When Price Action is primary, prioritize OTE + Rejection Wick, or breakout with rejection wick, plus runaway breakout
        candidate_ce = ((pa_entry_ce | ((crossover_ce | cm_breakout_ce) & (rejection_ce | yellow_ce))) & not_overbought) | breakout_ce
        candidate_pe = ((pa_entry_pe | ((crossover_pe | cm_breakdown_pe) & (rejection_pe | yellow_pe))) & not_oversold) | breakout_pe
    else:
        candidate_ce = ((crossover_ce | cm_breakout_ce) & not_overbought) | breakout_ce
        candidate_pe = ((crossover_pe | cm_breakdown_pe) & not_oversold) | breakout_pe

    bullish = np.array(candidate_ce & time_ok_ce, dtype=bool, copy=True)
    bearish = np.array(candidate_pe & time_ok_pe, dtype=bool, copy=True)

    # ── Resolve simultaneous conflicting triggers ──
    conflicts = bullish & bearish
    bullish[conflicts] = False
    bearish[conflicts] = False

    # ── Warm-up guard: suppress signals during indicator stabilization ──
    warmup_bars = max(cfg.ema_slow, cfg.rsi_length + cfg.rsi_ma_length, swing_lookback)
    if len(bullish) > warmup_bars:
        bullish[:warmup_bars] = False
        bearish[:warmup_bars] = False
    else:
        bullish[:] = False
        bearish[:] = False

    # ── Pillar 4: Anti-Whipsaw Directional Pause Guard ──
    if getattr(cfg, "enable_anti_whipsaw_guard", True):
        whipsaw_bars = int(getattr(cfg, "anti_whipsaw_bars", 3))
        last_sig_dir = 0
        last_sig_idx = -999

        for i in range(len(df)):
            if bullish[i]:
                if last_sig_dir == -1 and (i - last_sig_idx) <= whipsaw_bars:
                    bullish[i] = False
                else:
                    last_sig_dir = 1
                    last_sig_idx = i
            elif bearish[i]:
                if last_sig_dir == 1 and (i - last_sig_idx) <= whipsaw_bars:
                    bearish[i] = False
                else:
                    last_sig_dir = -1
                    last_sig_idx = i

    raw_signals = np.select([bearish, bullish], [-1, 1], default=0)
    sl_series = compute_adaptive_stop_loss_series(
        df, ind, cfg, raw_signals, swing_high, swing_low, rejection_ce, rejection_pe
    )

    fibo_targets = None
    if len(df) > 0 and raw_signals[-1] != 0:
        fibo_targets = calculate_fibonacci_levels(
            swing_high[-1], swing_low[-1], direction=raw_signals[-1],
            tp1_ext=cfg.fibo_extension_tp1,
            tp2_ext=cfg.fibo_extension_tp2,
            tp3_ext=cfg.fibo_extension_tp3,
        )

    return CrossSignals(
        bullish=bullish,
        bearish=bearish,
        indicators=ind,
        stop_loss=sl_series,
        is_chop=is_chop,
        fibo_targets=fibo_targets,
        higher_lows=hl_arr,
        lower_highs=lh_arr,
    )


# ─────────────────────────────────────────────────────────────────────
# Pure Price Action Exit Engine
# ─────────────────────────────────────────────────────────────────────

def evaluate_price_action_exit(
    df: pd.DataFrame,
    direction: int,
    entry_spot: float = 0.0,
    current_spot: float = 0.0,
    cfg: Optional[Ema9FiboSmcMomentumConfig] = None,
    entry_premium: Optional[float] = None,
    current_premium: Optional[float] = None,
) -> PriceActionExitResult:
    """Evaluates whether to exit based on Market Structure, Extension Targets, or Exhaustion Wicks.

    Pillars:
    1. Structural Swing Break: Closed below Higher Low (CE) or above Lower High (PE).
    2. Extension Exhaustion: Formed rejection wick at 1.272 / 1.618 Fibonacci target.
    3. Momentum Divergence: RSI divergence confirms trend exhaustion.
    """
    if cfg is None:
        cfg = Ema9FiboSmcMomentumConfig()

    if df is None or len(df) < 10:
        return PriceActionExitResult(should_exit=False, exit_reason="Warmup insufficient")

    high_arr = np.asarray(df["high"], dtype=float) if "high" in df.columns else np.asarray(df["close"], dtype=float)
    low_arr = np.asarray(df["low"], dtype=float) if "low" in df.columns else np.asarray(df["close"], dtype=float)
    close_arr = np.asarray(df["close"], dtype=float)
    open_arr = np.asarray(df["open"], dtype=float) if "open" in df.columns else close_arr

    if current_spot == 0.0 and len(close_arr) > 0:
        current_spot = float(close_arr[-1])

    # 1. Structural Swing Break Exit (MSS)
    if getattr(cfg, "enable_structure_break_exit", True):
        hl_arr, lh_arr, _, _ = detect_structure_swings(high_arr, low_arr, close_arr, lookback=cfg.swing_structure_lookback)
        if direction == 1:
            recent_hl = hl_arr[-1]
            if recent_hl > 0 and np.isfinite(recent_hl) and close_arr[-1] < recent_hl:
                if (entry_spot == 0.0) or (recent_hl <= entry_spot) or (close_arr[-1] < entry_spot):
                    return PriceActionExitResult(
                        should_exit=True,
                        exit_reason=f"PRICE ACTION: Structural Swing Break (Closed {close_arr[-1]:.2f} < Higher Low {recent_hl:.2f})",
                        urgency=0.85,
                    )
        elif direction == -1:
            recent_lh = lh_arr[-1]
            if recent_lh > 0 and np.isfinite(recent_lh) and close_arr[-1] > recent_lh:
                if (entry_spot == 0.0) or (recent_lh >= entry_spot) or (close_arr[-1] > entry_spot):
                    return PriceActionExitResult(
                        should_exit=True,
                        exit_reason=f"PRICE ACTION: Structural Swing Break (Closed {close_arr[-1]:.2f} > Lower High {recent_lh:.2f})",
                        urgency=0.85,
                    )

    # Helper to check profitability
    if entry_premium is not None and current_premium is not None and entry_premium > 0:
        is_profitable = current_premium > entry_premium
    elif entry_spot > 0 and current_spot > 0:
        is_profitable = (current_spot > entry_spot) if direction == 1 else (current_spot < entry_spot)
    else:
        is_profitable = True

    # 2. Exhaustion Wick Rejection at Target
    if getattr(cfg, "enable_exhaustion_wick_exit", True):
        exhaustion_wicks = detect_exhaustion_wick(
            high_arr, low_arr, open_arr, close_arr, direction=direction, min_ratio=cfg.exhaustion_wick_ratio
        )
        if len(exhaustion_wicks) > 0 and exhaustion_wicks[-1]:
            if is_profitable:
                wick_label = "Shooting Star Rejection" if direction == 1 else "Hammer Rejection"
                return PriceActionExitResult(
                    should_exit=True,
                    exit_reason=f"PRICE ACTION: Target Exhaustion ({wick_label} at resistance)",
                    urgency=0.75,
                )

    # 3. Supportive RSI Divergence Exit
    if getattr(cfg, "enable_rsi_divergence_exit", True):
        ind = compute_indicator_set(df, cfg.ema_fast, cfg.ema_slow, cfg.rsi_length, cfg.rsi_ma_length)
        rsi_vals = np.asarray(ind.rsi, dtype=float)
        div_arr = detect_rsi_divergence(close_arr, rsi_vals, direction=direction, lookback=14)
        if div_arr[-1]:
            is_profitable = (current_spot > entry_spot) if direction == 1 else (current_spot < entry_spot)
            if is_profitable:
                return PriceActionExitResult(
                    should_exit=True,
                    exit_reason="SUPPORTIVE INDICATOR: Bearish RSI Divergence (Momentum Exhaustion)",
                    urgency=0.70,
                )

    return PriceActionExitResult(should_exit=False, exit_reason="Structure intact (Holding Runner)")


def build_entry_signal_series(
    df: pd.DataFrame,
    cfg: Ema9FiboSmcMomentumConfig,
    edge_trigger: bool = True,
) -> Tuple[pd.Series, CrossSignals]:
    """Generates registry-compatible Series of +1, -1, 0 aligned to df index."""
    cross = compute_cross_signals(df, cfg)
    raw = np.select([cross.bearish, cross.bullish], [-1, 1], default=0)

    if edge_trigger:
        prior = np.r_[0, raw[:-1]]
        edges = np.where((raw != 0) & (raw != prior), raw, 0)
        sig_series = pd.Series(edges, index=df.index, dtype=int)
    else:
        sig_series = pd.Series(raw, index=df.index, dtype=int)

    return sig_series, cross
