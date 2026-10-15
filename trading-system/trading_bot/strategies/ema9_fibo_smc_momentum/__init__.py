"""EMA 9 / Fibo OTE Momentum Pro Strategy — Independent Entry & Exit Logic Module.

Enhanced clone of ema9_rsi_momentum with Pure Price Action as the Primary Driver:
1. Pure Price Action Entry:
   - Market Structure Shift (BOS / MSS) & Swing Detection.
   - Fibonacci Optimal Trade Entry (OTE: 0.62 - 0.705 - 0.79) with Candlestick Rejection Wick Trigger.
   - Opening Noise Filter (09:15 - 09:30 AM blocked).
   - Indicators (EMA 9/20, RSI, ADX) act purely as supportive sanity filters.
2. Pure Price Action Exit:
   - Structural Swing Trailing (Trailing stop anchored to consecutive Higher Lows / Lower Highs).
   - Market Structure Break Exit (Exit when structural swing is violated).
   - Fibonacci Extension Liquidity Targets (1.000, 1.272, 1.618).
   - Resistance Exhaustion Wick Rejection Exit.
   - Supportive Indicator confirmation (RSI Divergence & Volume Climax).
"""

from __future__ import annotations

import logging
from collections import deque
from dataclasses import dataclass
from typing import Optional

import numpy as np
import pandas as pd

from trading_bot.strategies._signal_utils import edge_trigger
from .config import Ema9FiboSmcMomentumConfig
from .indicators import compute_indicator_set
from .premium_health import (
    PremiumHealth,
    ProtectiveExitResult,
    build_premium_health,
    classify_decay,
    evaluate_protective_exit as _evaluate_protective_exit,
)
from .signal_engine import (
    CrossSignals,
    PriceActionExitResult,
    build_entry_signal_series,
    classify_momentum_strength,
    evaluate_price_action_exit,
)

logger = logging.getLogger(__name__)

STRATEGY_NAME = "ema9_fibo_smc_momentum"
STRATEGY_LABEL = "EMA 9 / Fibo OTE Momentum Pro"

__all__ = [
    "STRATEGY_NAME",
    "STRATEGY_LABEL",
    "generate_signals",
    "evaluate_protective_exit",
    "evaluate_price_action_exit",
    "PriceActionExitResult",
    "Ema9FiboSmcMomentumConfig",
    "PremiumHealth",
    "ProtectiveExitResult",
    "build_premium_health",
    "classify_decay",
    "classify_momentum_strength",
    "CrossSignals",
]

_MAX_LOGGED_SIGNALS = 128
_logged_signal_bars: deque = deque(maxlen=_MAX_LOGGED_SIGNALS)
_logged_signal_bars_set: set = set()


def _log_once_per_bar(key) -> bool:
    if key in _logged_signal_bars_set:
        return False
    if len(_logged_signal_bars) == _MAX_LOGGED_SIGNALS:
        _logged_signal_bars_set.discard(_logged_signal_bars[0])
    _logged_signal_bars.append(key)
    _logged_signal_bars_set.add(key)
    return True


def generate_signals(
    df: pd.DataFrame,
    ema_fast: int = 9,
    ema_slow: int = 20,
    rsi_length: int = 14,
    rsi_ma_length: int = 20,
    rsi_band_normal: float = 40.0,
    rsi_band_strong: float = 50.0,
    rsi_band_very_strong: float = 60.0,
    enable_adx_filter: bool = True,
    min_adx: float = 18.0,
    enable_time_filter: bool = True,
    time_start: str = "09:30",
    time_end: str = "15:15",
    enable_touch_filter: bool = True,
    enable_fibo_ote_filter: bool = True,
    fibo_swing_lookback: int = 15,
    enable_anti_whipsaw_guard: bool = True,
    anti_whipsaw_bars: int = 3,
    price_action_primary: bool = True,
    require_rejection_wick: bool = True,
    min_rejection_wick_ratio: float = 0.30,
    enable_momentum_breakout: bool = True,
    **kwargs,
) -> pd.Series:
    """Registry entry point for EMA 9 / Fibo OTE Momentum Pro (Price Action Primary).

    Returns:
        pd.Series of +1 (CE Buy), -1 (PE Buy), or 0 (No trade), aligned to df index.
    """
    cfg = Ema9FiboSmcMomentumConfig(
        ema_fast=ema_fast,
        ema_slow=ema_slow,
        rsi_length=rsi_length,
        rsi_ma_length=rsi_ma_length,
        rsi_band_normal=rsi_band_normal,
        rsi_band_strong=rsi_band_strong,
        rsi_band_very_strong=rsi_band_very_strong,
        enable_adx_filter=enable_adx_filter,
        min_adx=min_adx,
        enable_time_filter=enable_time_filter,
        time_start=time_start,
        time_end=time_end,
        enable_touch_filter=enable_touch_filter,
        enable_fibo_ote_filter=enable_fibo_ote_filter,
        fibo_swing_lookback=fibo_swing_lookback,
        enable_anti_whipsaw_guard=enable_anti_whipsaw_guard,
        anti_whipsaw_bars=anti_whipsaw_bars,
        price_action_primary=price_action_primary,
        require_rejection_wick=require_rejection_wick,
        min_rejection_wick_ratio=min_rejection_wick_ratio,
        enable_momentum_breakout=enable_momentum_breakout,
        **{k: v for k, v in kwargs.items() if k in Ema9FiboSmcMomentumConfig.__dataclass_fields__},
    )

    if df is None or df.empty or "close" not in df.columns:
        return pd.Series(dtype=int)

    signals, cross = build_entry_signal_series(df, cfg, edge_trigger=True)

    latest_direction = int(signals.iloc[-1]) if len(signals) else 0
    if latest_direction != 0:
        bar_key = (df.index[-1], latest_direction)
        if _log_once_per_bar(bar_key):
            ind = cross.indicators
            rsi_now = float(ind.rsi.iloc[-1])
            momentum = classify_momentum_strength(rsi_now, latest_direction, cfg)
            side_label = "CE" if latest_direction == 1 else "PE"
            fibo_info = f" | Fibo Targets: {cross.fibo_targets}" if cross.fibo_targets else ""
            logger.info(
                "ENTRY %s [Price Action Primary OTE] | EMA%d %.2f %s EMA%d %.2f | RSI%d %.2f | Momentum: %s%s",
                side_label,
                cfg.ema_fast, float(ind.ema_fast.iloc[-1]), ">" if latest_direction == 1 else "<",
                cfg.ema_slow, float(ind.ema_slow.iloc[-1]),
                cfg.rsi_length, rsi_now,
                momentum,
                fibo_info,
            )

    return signals


def evaluate_protective_exit(
    df: pd.DataFrame,
    side: int,
    entry_premium: float,
    current_premium: float,
    settings: dict | None = None,
    **overrides,
) -> ProtectiveExitResult:
    """Evaluates Pure Price Action exit first (MSS break, target exhaustion, RSI divergence),
    falling back to base reversal check.
    """
    cfg = Ema9FiboSmcMomentumConfig.from_settings(settings, **overrides)
    return _evaluate_protective_exit(df, side, entry_premium, current_premium, cfg)
