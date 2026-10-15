"""EMA 9 / Fibo OTE Momentum Pro — Configuration & Defaults.

Cloned and enhanced from ema9_rsi_momentum with Pure Price Action as the Primary Driver:
1. Pure Price Action Entry:
   - Market Structure Shift (BOS / MSS) & Swing Detection.
   - Fibonacci Optimal Trade Entry (OTE: 0.62 - 0.705 - 0.79) Discount/Premium Retracement.
   - Candlestick Rejection Wick / Absorption at key level is the primary trigger.
   - Indicators (EMA, RSI, ADX) act purely as secondary confirmation / sanity guards.
2. Pure Price Action Exit:
   - Structural Swing Trailing (Trailing stop anchored to consecutive Higher Lows / Lower Highs).
   - Market Structure Break Exit (Exit when structural swing is violated).
   - Fibonacci Extension Liquidity Targets (1.000, 1.272, 1.618).
   - Resistance Exhaustion Wick Rejection Exit.
   - Supportive Indicator confirmation (RSI Divergence & Volume Climax).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

# ─────────────────────────────────────────────────────────────────────
# Primary Driver: Pure Price Action Engine
# ─────────────────────────────────────────────────────────────────────
PRICE_ACTION_PRIMARY: bool = True
SWING_STRUCTURE_LOOKBACK: int = 5      # Fractal pivot lookback (5 bars each side)
REQUIRE_REJECTION_WICK: bool = True    # Requires wick absorption at Fibo/support
MIN_REJECTION_WICK_RATIO: float = 0.30 # Lower wick >= 30% of range for CE; upper wick for PE

# ─────────────────────────────────────────────────────────────────────
# Pure Price Action Exit Architecture
# ─────────────────────────────────────────────────────────────────────
ENABLE_STRUCTURAL_TRAILING: bool = True # Trail SL behind consecutive Higher Lows (CE) / Lower Highs (PE)
ENABLE_STRUCTURE_BREAK_EXIT: bool = True # Exit on candle body close beyond structural swing
ENABLE_EXHAUSTION_WICK_EXIT: bool = True # Exit on exhaustion pinbar near extension targets
EXHAUSTION_WICK_RATIO: float = 0.40     # Wick >= 40% of range at target signals institutional distribution
ENABLE_RSI_DIVERGENCE_EXIT: bool = True # Exit when RSI divergence confirms momentum exhaustion

# ─────────────────────────────────────────────────────────────────────
# Core Moving Averages & RSI Indicators (Supportive Sanity Checks)
# ─────────────────────────────────────────────────────────────────────
EMA_FAST: int = 9
EMA_SLOW: int = 20
RSI_LENGTH: int = 14
RSI_MA_LENGTH: int = 20  # EMA smoothing of RSI line

# ─────────────────────────────────────────────────────────────────────
# RSI Momentum & Exhaustion Thresholds
# ─────────────────────────────────────────────────────────────────────
RSI_BAND_NORMAL: float = 40.0
RSI_BAND_STRONG: float = 50.0
RSI_BAND_VERY_STRONG: float = 60.0
RSI_OVERBOUGHT_CAP: float = 75.0   # Hard ceiling: CE entry blocked above this to prevent buying tops
RSI_OVERSOLD_FLOOR: float = 25.0   # Hard floor: PE entry blocked below this to prevent buying bottoms

# ─────────────────────────────────────────────────────────────────────
# Pillar 1: Time-of-Day & Opening Noise Filters
# ─────────────────────────────────────────────────────────────────────
ENABLE_TIME_FILTER: bool = True
# 09:30 start eliminates opening 15m whipsaws where win rate historically dropped to 18.8%
TIME_START: str = "09:30"
TIME_END: str = "15:15"
ENABLE_OPENING_RANGE_FILTER: bool = True

LATE_ENTRY_ENABLED: bool = True
LATE_ENTRY_END: str = "15:25"
LATE_ENTRY_MIN_STRENGTH: str = "VERY_STRONG"

# ─────────────────────────────────────────────────────────────────────
# Pillar 2: Trend Strength & Cluster Filters
# ─────────────────────────────────────────────────────────────────────
ENABLE_ADX_FILTER: bool = True
MIN_ADX: float = 18.0

ENABLE_TOUCH_FILTER: bool = True
EMA_TOUCH_MODE: str = "body_or_wick"
WICK_REQUIRES_CONFIRMATION: bool = True
TREND_SLOPE_LOOKBACK: int = 6
TREND_SLOPE_MIN_PCT: float = 0.02

# Flat consolidation suppression
ENABLE_CHOP_FILTER: bool = True
CHOP_ATR_MULT: float = 0.20
CHOP_SLOPE_THRESHOLD: float = 0.15

# ─────────────────────────────────────────────────────────────────────
# Pillar 3: Fibonacci Optimal Trade Entry (OTE) Retracement Engine
# ─────────────────────────────────────────────────────────────────────
ENABLE_FIBO_OTE_FILTER: bool = True
FIBO_SWING_LOOKBACK: int = 15          # Bars to scan for fractal swing high & swing low
FIBO_OTE_LOW: float = 0.62             # OTE entry start (62.0%)
FIBO_OTE_SWEET_SPOT: float = 0.705     # Institutional geometric sweet spot (70.5%)
FIBO_OTE_HIGH: float = 0.79            # Invalidation boundary (79.0%)
FIBO_REQUIRE_DISPLACEMENT: bool = True # Requires previous impulse to break prior candle high/low

# ─────────────────────────────────────────────────────────────────────
# Pillar 4: Anti-Whipsaw Direction Guard & Adaptive SL
# ─────────────────────────────────────────────────────────────────────
ENABLE_ANTI_WHIPSAW_GUARD: bool = True
ANTI_WHIPSAW_BARS: int = 3             # Minimum bars to pause before flipping CE <-> PE
ADAPTIVE_SL_ENABLED: bool = True
LARGE_CANDLE_ATR_MULT: float = 1.0
SL_BUFFER_ATR_MULT: float = 0.20
SL_CANDLE_BUFFER_ATR_MULT: float = 0.05
FIBO_SL_BUFFER_ATR_MULT: float = 0.25   # Buffer beyond 0.79/1.0 when Fibo SL is active

# ─────────────────────────────────────────────────────────────────────
# Pillar 5: Fibonacci Negative Extension Targets
# ─────────────────────────────────────────────────────────────────────
ENABLE_FIBO_EXTENSIONS: bool = True
FIBO_EXTENSION_TP1: float = 1.000      # 100% of swing (Previous high / low)
FIBO_EXTENSION_TP2: float = 1.272      # First external liquidity extension
FIBO_EXTENSION_TP3: float = 1.618      # Golden extension full target

# ─────────────────────────────────────────────────────────────────────
# Momentum Breakout Expansion Setup (Catches Runaway Trend Days)
# ─────────────────────────────────────────────────────────────────────
ENABLE_MOMENTUM_BREAKOUT: bool = True
MIN_BREAKOUT_ADX: float = 20.0
MIN_BREAKOUT_RSI: float = 55.0

# ─────────────────────────────────────────────────────────────────────
# Dual Entry Engine Setup Configuration
# ─────────────────────────────────────────────────────────────────────
ENABLE_PULLBACK_ENTRIES: bool = True
ENTRY_CONFIRM_SECONDS: int = 10
EARLY_ENTRY_MIN_STRENGTH: str = "STRONG"
REQUIRE_BAR_CLOSE_WINDOW: bool = False

ENABLE_EXIT_ANALYZER: bool = True
MIN_PEAK_PROFIT_PTS: float = 30.0
MAX_GIVEBACK_PCT: float = 20.0
URGENCY_THRESHOLD: float = 0.70

# End of day review
EOD_REVIEW_TIME: str = "15:15"
EOD_HARD_TIME: str = "15:25"
EOD_RUNNER_GIVEBACK_PCT: float = 5.0
ALLOW_OVERNIGHT_CARRY: bool = False
OVERNIGHT_MIN_GAIN_PCT: float = 40.0
OVERNIGHT_MIN_STRENGTH: str = "VERY_STRONG"

# Option execution, decay & exit ladder defaults
DECAY_LOW_PCT: float = -10.0
DECAY_MODERATE_PCT: float = -20.0
DECAY_HIGH_PCT: float = -35.0

TIMEFRAME_MINUTES: int = 5
INITIAL_SL_PCT: float = 15.0
PROFIT_LADDER_PCT: tuple = (15.0, 33.0, 50.0, 75.0, 100.0, 150.0, 200.0)
STRIKE_SELECTION: str = "ATM"
ITM_TARGET_DELTA: float = 0.70
MAX_ENTRY_SPREAD_PCT: float = 1.0
ENABLE_OPTION_CHART_GATE: bool = True
REQUIRE_OPTION_ABOVE_VWAP: bool = True
MAX_OPTION_SPREAD_PCT: float = 1.2
MIN_OPTION_VOLUME: int = 50
OPTION_WARMUP_MINUTES: int = 3
LEGACY_TOUCH_BUFFER_PCT: float = 0.05
EXPIRY_LATE_ENTRY: bool = True
EXPIRY_LATE_ENTRY_END: str = "15:25"
EXPIRY_LATE_ENTRY_MIN_STRENGTH: str = "VERY_STRONG"


@dataclass
class Ema9FiboSmcMomentumConfig:
    """Dataclass encapsulating all parameters for EMA 9 / Fibo OTE Momentum Pro."""
    price_action_primary: bool = PRICE_ACTION_PRIMARY
    swing_structure_lookback: int = SWING_STRUCTURE_LOOKBACK
    require_rejection_wick: bool = REQUIRE_REJECTION_WICK
    min_rejection_wick_ratio: float = MIN_REJECTION_WICK_RATIO
    enable_structural_trailing: bool = ENABLE_STRUCTURAL_TRAILING
    enable_structure_break_exit: bool = ENABLE_STRUCTURE_BREAK_EXIT
    enable_exhaustion_wick_exit: bool = ENABLE_EXHAUSTION_WICK_EXIT
    exhaustion_wick_ratio: float = EXHAUSTION_WICK_RATIO
    enable_rsi_divergence_exit: bool = ENABLE_RSI_DIVERGENCE_EXIT

    ema_fast: int = EMA_FAST
    ema_slow: int = EMA_SLOW
    rsi_length: int = RSI_LENGTH
    rsi_ma_length: int = RSI_MA_LENGTH
    rsi_band_normal: float = RSI_BAND_NORMAL
    rsi_band_strong: float = RSI_BAND_STRONG
    rsi_band_very_strong: float = RSI_BAND_VERY_STRONG
    rsi_overbought_cap: float = RSI_OVERBOUGHT_CAP
    rsi_oversold_floor: float = RSI_OVERSOLD_FLOOR
    decay_low_pct: float = DECAY_LOW_PCT
    decay_moderate_pct: float = DECAY_MODERATE_PCT
    decay_high_pct: float = DECAY_HIGH_PCT
    enable_adx_filter: bool = ENABLE_ADX_FILTER
    min_adx: float = MIN_ADX
    enable_time_filter: bool = ENABLE_TIME_FILTER
    time_start: str = TIME_START
    time_end: str = TIME_END
    enable_opening_range_filter: bool = ENABLE_OPENING_RANGE_FILTER
    late_entry_enabled: bool = LATE_ENTRY_ENABLED
    late_entry_end: str = LATE_ENTRY_END
    late_entry_min_strength: str = LATE_ENTRY_MIN_STRENGTH
    expiry_late_entry: bool = EXPIRY_LATE_ENTRY
    expiry_late_entry_end: str = EXPIRY_LATE_ENTRY_END
    expiry_late_entry_min_strength: str = EXPIRY_LATE_ENTRY_MIN_STRENGTH
    enable_touch_filter: bool = ENABLE_TOUCH_FILTER
    ema_touch_mode: str = EMA_TOUCH_MODE
    legacy_touch_buffer_pct: float = LEGACY_TOUCH_BUFFER_PCT
    wick_requires_confirmation: bool = WICK_REQUIRES_CONFIRMATION
    trend_slope_lookback: int = TREND_SLOPE_LOOKBACK
    trend_slope_min_pct: float = TREND_SLOPE_MIN_PCT
    enable_chop_filter: bool = ENABLE_CHOP_FILTER
    chop_atr_mult: float = CHOP_ATR_MULT
    chop_slope_threshold: float = CHOP_SLOPE_THRESHOLD
    enable_fibo_ote_filter: bool = ENABLE_FIBO_OTE_FILTER
    fibo_swing_lookback: int = FIBO_SWING_LOOKBACK
    fibo_ote_low: float = FIBO_OTE_LOW
    fibo_ote_sweet_spot: float = FIBO_OTE_SWEET_SPOT
    fibo_ote_high: float = FIBO_OTE_HIGH
    fibo_require_displacement: bool = FIBO_REQUIRE_DISPLACEMENT
    enable_anti_whipsaw_guard: bool = ENABLE_ANTI_WHIPSAW_GUARD
    anti_whipsaw_bars: int = ANTI_WHIPSAW_BARS
    adaptive_sl_enabled: bool = ADAPTIVE_SL_ENABLED
    large_candle_atr_mult: float = LARGE_CANDLE_ATR_MULT
    sl_buffer_atr_mult: float = SL_BUFFER_ATR_MULT
    sl_candle_buffer_atr_mult: float = SL_CANDLE_BUFFER_ATR_MULT
    fibo_sl_buffer_atr_mult: float = FIBO_SL_BUFFER_ATR_MULT
    enable_fibo_extensions: bool = ENABLE_FIBO_EXTENSIONS
    fibo_extension_tp1: float = FIBO_EXTENSION_TP1
    fibo_extension_tp2: float = FIBO_EXTENSION_TP2
    fibo_extension_tp3: float = FIBO_EXTENSION_TP3
    enable_momentum_breakout: bool = ENABLE_MOMENTUM_BREAKOUT
    min_breakout_adx: float = MIN_BREAKOUT_ADX
    min_breakout_rsi: float = MIN_BREAKOUT_RSI
    enable_pullback_entries: bool = ENABLE_PULLBACK_ENTRIES
    entry_confirm_seconds: int = ENTRY_CONFIRM_SECONDS
    early_entry_min_strength: str = EARLY_ENTRY_MIN_STRENGTH
    require_bar_close_window: bool = REQUIRE_BAR_CLOSE_WINDOW
    enable_exit_analyzer: bool = ENABLE_EXIT_ANALYZER
    min_peak_profit_pts: float = MIN_PEAK_PROFIT_PTS
    max_giveback_pct: float = MAX_GIVEBACK_PCT
    urgency_threshold: float = URGENCY_THRESHOLD
    timeframe_minutes: int = TIMEFRAME_MINUTES
    strike_selection: str = STRIKE_SELECTION
    itm_target_delta: float = ITM_TARGET_DELTA
    max_entry_spread_pct: float = MAX_ENTRY_SPREAD_PCT
    initial_sl_pct: float = INITIAL_SL_PCT
    profit_ladder_pct: tuple = PROFIT_LADDER_PCT
    enable_option_chart_gate: bool = ENABLE_OPTION_CHART_GATE
    require_option_above_vwap: bool = REQUIRE_OPTION_ABOVE_VWAP
    max_option_spread_pct: float = MAX_OPTION_SPREAD_PCT
    min_option_volume: int = MIN_OPTION_VOLUME
    option_warmup_minutes: int = OPTION_WARMUP_MINUTES
    eod_review_time: str = EOD_REVIEW_TIME
    eod_hard_time: str = EOD_HARD_TIME
    eod_runner_giveback_pct: float = EOD_RUNNER_GIVEBACK_PCT
    allow_overnight_carry: bool = ALLOW_OVERNIGHT_CARRY
    overnight_min_gain_pct: float = OVERNIGHT_MIN_GAIN_PCT
    overnight_min_strength: str = OVERNIGHT_MIN_STRENGTH

    @classmethod
    def from_settings(cls, settings: Optional[dict] = None, symbol: Optional[str] = None, **overrides) -> Ema9FiboSmcMomentumConfig:
        """Construct config from dictionary or keyword overrides with full prefix support."""
        cfg = cls()
        settings = settings or {}

        # 1. Direct field matches or prefixed matches
        for field_name in cls.__dataclass_fields__:
            for prefix in ("", "ema9_fibo_", "ema9_rsi_", "ema9_"):
                candidate = f"{prefix}{field_name}"
                if candidate in settings:
                    setattr(cfg, field_name, settings[candidate])
                    break

        # 2. General application timeframe mapping
        if "timeframe" in settings and "timeframe_minutes" not in overrides:
            from shared.timeframes import parse_timeframe
            cfg.timeframe_minutes = parse_timeframe(settings["timeframe"], TIMEFRAME_MINUTES)

        # 3. Explicit overrides
        for k, v in overrides.items():
            if hasattr(cfg, k):
                setattr(cfg, k, v)
        return cfg
