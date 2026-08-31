"""EMA9/RSI Momentum Strategy — Configuration & Defaults.

Single source of truth for every tunable value in this strategy package.
All of these are also exposed as ``generate_signals()`` keyword arguments
(see ``__init__.py``) so they can be overridden per-call from
``config/settings.json`` / the dashboard, exactly like every other strategy
in ``trading_bot/strategies/`` (e.g. ``ema_rsi_strategy.py``).

Nothing here duplicates existing indicator math — ``shared/indicators``
(``ema``, ``rsi``) is reused for every calculation; this module only holds
the periods/thresholds that parametrize those calls.
"""

from __future__ import annotations

from dataclasses import dataclass

# ─────────────────────────────────────────────────────────────────────
# Indicators (spec: EMA 9/20 fast/slow, RSI 14 smoothed by EMA 20)
# ─────────────────────────────────────────────────────────────────────
EMA_FAST: int = 9
EMA_SLOW: int = 20
RSI_LENGTH: int = 14
RSI_MA_LENGTH: int = 20  # EMA smoothing of the RSI line

# ─────────────────────────────────────────────────────────────────────
# RSI momentum-strength bands (informational only — see signal_engine.py)
# ─────────────────────────────────────────────────────────────────────
RSI_BAND_NORMAL: float = 40.0
RSI_BAND_STRONG: float = 50.0
RSI_BAND_VERY_STRONG: float = 60.0

# ─────────────────────────────────────────────────────────────────────
# Premium decay / option-health classification (post-entry monitoring)
# ─────────────────────────────────────────────────────────────────────
# Boundaries are the upper (least-negative) edge of each band:
# 0% to -10% -> LOW
# -10% to -20% -> MODERATE
# -20% to -30% -> HIGH
# < -30% -> CRITICAL
DECAY_LOW_PCT: float = -10.0
DECAY_MODERATE_PCT: float = -20.0
DECAY_HIGH_PCT: float = -30.0

# ─────────────────────────────────────────────────────────────────────
# Entry Decay & Trend Filters (Filters out flat chop and high-decay windows)
# ─────────────────────────────────────────────────────────────────────
ENABLE_ADX_FILTER: bool = True
MIN_ADX: float = 18.0
ENABLE_TIME_FILTER: bool = True
TIME_START: str = "09:25"
TIME_END: str = "15:00"
ENABLE_TOUCH_FILTER: bool = True


@dataclass(frozen=True)
class Ema9RsiMomentumConfig:
    """Bundles every configurable knob for a single call. Constructed once
    per ``generate_signals`` / ``evaluate_protective_exit`` invocation from
    whatever kwargs / settings dict the caller passed in — never mutated,
    never shared across calls (this strategy keeps no cross-call state)."""

    ema_fast: int = EMA_FAST
    ema_slow: int = EMA_SLOW
    rsi_length: int = RSI_LENGTH
    rsi_ma_length: int = RSI_MA_LENGTH
    rsi_band_normal: float = RSI_BAND_NORMAL
    rsi_band_strong: float = RSI_BAND_STRONG
    rsi_band_very_strong: float = RSI_BAND_VERY_STRONG
    decay_low_pct: float = DECAY_LOW_PCT
    decay_moderate_pct: float = DECAY_MODERATE_PCT
    decay_high_pct: float = DECAY_HIGH_PCT
    enable_adx_filter: bool = ENABLE_ADX_FILTER
    min_adx: float = MIN_ADX
    enable_time_filter: bool = ENABLE_TIME_FILTER
    time_start: str = TIME_START
    time_end: str = TIME_END
    enable_touch_filter: bool = ENABLE_TOUCH_FILTER

    @classmethod
    def from_settings(cls, settings: dict | None = None, **overrides) -> "Ema9RsiMomentumConfig":
        """Build from a flat settings dict (as read from ``config/settings.json``)
        using the ``ema9_rsi_<field>`` key convention, then apply any explicit
        keyword overrides (e.g. the values ``generate_signals`` itself already
        received as named kwargs) on top."""
        settings = settings or {}
        kwargs = {}
        for field_name in cls.__dataclass_fields__:
            key = f"ema9_rsi_{field_name}"
            if key in settings:
                kwargs[field_name] = settings[key]
        kwargs.update({k: v for k, v in overrides.items() if v is not None})
        return cls(**kwargs)
