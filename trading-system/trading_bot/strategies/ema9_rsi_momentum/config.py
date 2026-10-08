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
RSI_OVERBOUGHT_CAP: float = 75.0   # Hard ceiling: CE entry blocked above this to prevent buying tops
RSI_OVERSOLD_FLOOR: float = 25.0   # Hard floor: PE entry blocked below this to prevent buying bottoms

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
# Owner's window, 2026-09-22: 09:20 to 15:15 (was 09:25-15:00).
# Measured over 675 sessions with costs from real premiums: NIFTY +Rs.11,150
# -> +Rs.11,150 and SENSEX -Rs.37,841 -> -Rs.37,841. Neutral either way, so
# the owner's preference decides.
TIME_START: str = "09:20"
TIME_END: str = "15:15"

# ─────────────────────────────────────────────────────────────────────
# Late entry (applies to ALL trading days, 15:15 to 15:25)
# ─────────────────────────────────────────────────────────────────────
# Between TIME_END (15:15) and LATE_ENTRY_END (15:25), a strong signal
# may still be taken on ANY trading day (not just expiry) provided momentum
# is at least LATE_ENTRY_MIN_STRENGTH ("VERY_STRONG").
LATE_ENTRY_ENABLED: bool = True
LATE_ENTRY_END: str = "15:25"
LATE_ENTRY_MIN_STRENGTH: str = "VERY_STRONG"

# Backward compatibility aliases
EXPIRY_LATE_ENTRY: bool = LATE_ENTRY_ENABLED
EXPIRY_LATE_ENTRY_END: str = LATE_ENTRY_END
EXPIRY_LATE_ENTRY_MIN_STRENGTH: str = LATE_ENTRY_MIN_STRENGTH

ENABLE_TOUCH_FILTER: bool = True

# How the crossover candle must sit against the EMA cluster.
#
#   "body_or_wick"  the owner's rule: the candle must reach BOTH
#                   EMAs -- its body preferred, its wick accepted. A signal
#                   carries which of the two it was, so the books can log it.
#   "body"          the strict half of that rule: the BODY must reach both.
#   "legacy"        the pre-2026-09-22 one-sided check (low <= upper EMA +
#                   0.06% buffer), kept only so an old run can be reproduced.
EMA_TOUCH_MODE: str = "body_or_wick"
LEGACY_TOUCH_BUFFER_PCT: float = 0.0006  # only read when mode == "legacy"

# ─────────────────────────────────────────────────────────────────────
# How a wick touch has to earn its entry
# ─────────────────────────────────────────────────────────────────────
# A body touch is taken on its own (priority HIGH). A wick touch must
# ALSO agree with the trend slope (priority MEDIUM); a wick touch that
# fails trend agreement is skipped (LOW).
WICK_REQUIRES_CONFIRMATION: bool = True
TREND_SLOPE_LOOKBACK: int = 6        # bars the EMA20 slope is measured over
TREND_SLOPE_MIN_PCT: float = 0.02    # slope, as % of price, to count as agreeing

# ─────────────────────────────────────────────────────────────────────
# Chop Box / Compression Filter (Purple "No Trade" Box)
# ─────────────────────────────────────────────────────────────────────
# Suppresses entries when 9 EMA and 20 EMA are compressed/entangled and flat.
# Fully dynamic across all instruments (NIFTY, BANKNIFTY, SENSEX, Stocks)
# by measuring the EMA separation as a multiple of ATR(14).
ENABLE_CHOP_FILTER: bool = True
CHOP_ATR_MULT: float = 0.20          # If |EMA9 - EMA20| < CHOP_ATR_MULT * ATR, mark as chop box
CHOP_SLOPE_THRESHOLD: float = 0.15   # Max normalized EMA20 slope to count as flat

# ─────────────────────────────────────────────────────────────────────
# Dual Entry Engine: Reversals + Pullback / Trend Continuation
# ─────────────────────────────────────────────────────────────────────
# Enables Setup B: when trending (EMA9 > EMA20 or EMA9 < EMA20), enters on
# 9 EMA pullback/retest yellow candle closing in the trend direction.
ENABLE_PULLBACK_ENTRIES: bool = True

# ─────────────────────────────────────────────────────────────────────
# Adaptive Dynamic Stop Loss (ATR-Normalized for all instruments)
# ─────────────────────────────────────────────────────────────────────
# For Large Candles (range >= LARGE_CANDLE_ATR_MULT * ATR):
#   Anchor SL to the trigger yellow candle's Low (CE) or High (PE).
# For Small Candles (range < LARGE_CANDLE_ATR_MULT * ATR):
#   Anchor SL to 20 EMA +/- (SL_BUFFER_ATR_MULT * ATR).
ADAPTIVE_SL_ENABLED: bool = True
LARGE_CANDLE_ATR_MULT: float = 1.0     # Multiplier to distinguish large momentum candle
SL_BUFFER_ATR_MULT: float = 0.20       # Buffer beyond 20 EMA for small candles
SL_CANDLE_BUFFER_ATR_MULT: float = 0.05 # Buffer beyond candle extreme for large candles

# ─────────────────────────────────────────────────────────────────────
# Entry timing
# ─────────────────────────────────────────────────────────────────────
# A crossover is only final once its candle closes: intrabar, EMA9 can cross
# EMA20 and cross back before the bar is done. So an entry is taken in the
# last `ENTRY_CONFIRM_SECONDS` of the forming candle, when the bar is all but
# settled.
ENTRY_CONFIRM_SECONDS: int = 10
EARLY_ENTRY_MIN_STRENGTH: str = "STRONG"
REQUIRE_BAR_CLOSE_WINDOW: bool = False   # When True, enforces entries strictly in final 10s window

ENABLE_EXIT_ANALYZER: bool = True
MIN_PEAK_PROFIT_PTS: float = 30.0
MAX_GIVEBACK_PCT: float = 20.0
URGENCY_THRESHOLD: float = 0.70

# ─────────────────────────────────────────────────────────────────────
# End of day (owner's rule, 2026-09-22)
# ─────────────────────────────────────────────────────────────────────
# 15:15 stops being a guillotine and becomes a review: a position still
# running -- in profit and within `EOD_RUNNER_GIVEBACK_PCT` of its own best
# premium -- is allowed to keep going to EOD_HARD_TIME. Everything else is
# closed at 15:15 as before, and EVERYTHING is closed at the hard time.
#
# Measured over 675 sessions, costs from real premiums:
#
#                                          NIFTY        SENSEX
#   close everything at 15:15            +11,150       -37,841
#   close everything at 15:25             +7,415       -37,507   <- worse
#   extend only runners within 3%        +12,428       -37,463   <- best
#   extend only runners within 5%        +12,005       -37,297
#   extend only runners within 12%        +7,880       -35,587
#
# Blanket extension loses money; extending only what is still at its high
# makes money. 5% is the default -- 3% scored marginally higher on NIFTY but
# on 8 trades out of 178, which is not a margin worth tuning to.
EOD_REVIEW_TIME: str = "15:15"
EOD_HARD_TIME: str = "15:25"
EOD_RUNNER_GIVEBACK_PCT: float = 5.0

# Carrying a position overnight. OFF, and the owner asked for it to exist
# rather than to be on: it changes the risk class completely. An intraday
# option buyer's whole edge is that no gap can happen while the position is
# open. Held overnight, one gap against a 15%-stop position can exceed every
# stop the ladder would ever apply, and no stop order protects against a gap.
# On an expiry day it is not a choice at all -- the contract expires, so the
# carry logic never runs there.
ALLOW_OVERNIGHT_CARRY: bool = False
OVERNIGHT_MIN_GAIN_PCT: float = 40.0      # must be this far in profit
OVERNIGHT_MIN_STRENGTH: str = "VERY_STRONG"

# ─────────────────────────────────────────────────────────────────────
# Per-symbol overrides
# ─────────────────────────────────────────────────────────────────────
# One global parameter set treated NIFTY and SENSEX as the same instrument.
# They are not: SENSEX carries a wider spread and a different tick and lot
# economy, and it wants a much stronger trend before a crossover is worth
# paying for. Measured quarter by quarter, fixed, no fitting:
#
#   min_adx      18        20        21        22        25
#   NIFTY   +11,150   +17,301   +10,373       -10    -6,148
#   SENSEX  -37,841   -23,318   -18,554   -13,866    -9,602   (best in 8/11 q)
#
# SENSEX improves monotonically all the way to 25 and is best there in 8 of
# 11 quarters -- that is a real effect, not a peak to fit. NIFTY's surface is
# spiky (20 has the best total but is best in only 1 quarter of 11), so it
# stays at 18 rather than chasing a number that does not repeat.
#
# Settings key: "ema9_rsi_symbol_overrides": {"SENSEX": {"min_adx": 25}}
SYMBOL_OVERRIDES: dict = {
    "SENSEX": {"min_adx": 25.0},
}

# ─────────────────────────────────────────────────────────────────────
# Execution: which chart the rules read, and which strike a signal buys
# ─────────────────────────────────────────────────────────────────────
# Defaults are today's behaviour (5-minute chart, ATM strike). The 15-minute
# / ITM combination measured +1.99% of premium per trade over 578 NIFTY
# sessions after costs (n=170) against -3.20% for 5-minute / ATM, but is NOT
# yet proven -- 10- and 20-minute charts lose, 2024 was flat, SENSEX loses.
# It is paper-tested by ema9_variant_observer.py before any default changes.
TIMEFRAME_MINUTES: int = 5
STRIKE_SELECTION: str = "ATM"         # "ATM" | "ITM" -- see strike_selection.py
ITM_TARGET_DELTA: float = 0.70        # |delta| an ITM pick aims for
MAX_ENTRY_SPREAD_PCT: float = 1.0     # refuse a leg whose bid/ask spread is wider
ENABLE_OPTION_CHART_GATE: bool = True
REQUIRE_OPTION_ABOVE_VWAP: bool = True
MAX_OPTION_SPREAD_PCT: float = 1.2
MIN_OPTION_VOLUME: int = 50
OPTION_WARMUP_MINUTES: int = 3

# ─────────────────────────────────────────────────────────────────────
# Exits: the owner's ratcheting ladder -- see exit_ladder.py
# ─────────────────────────────────────────────────────────────────────
INITIAL_SL_PCT: float = 15.0                                            # opening stop, % under entry
PROFIT_LADDER_PCT: tuple = (15.0, 33.0, 50.0, 75.0, 100.0, 150.0, 200.0)  # rungs; stop steps to the rung below


def _symbol_key(symbol: str) -> str:
    """"NSE:NIFTY50-INDEX" / "NIFTY 24500 CE" -> "NIFTY"; "BSE:SENSEX-INDEX" -> "SENSEX".

    Overrides are keyed by the plain instrument name so one entry covers the
    index, its option contracts and every spelling the UI and broker use.
    """
    text = str(symbol or "").upper()
    for name in ("BANKNIFTY", "FINNIFTY", "MIDCPNIFTY", "SENSEX", "BANKEX", "NIFTY"):
        if name in text:
            return name
    return text.split(":")[-1].split("-")[0].strip()


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
    enable_touch_filter: bool = ENABLE_TOUCH_FILTER
    ema_touch_mode: str = EMA_TOUCH_MODE
    legacy_touch_buffer_pct: float = LEGACY_TOUCH_BUFFER_PCT
    late_entry_enabled: bool = LATE_ENTRY_ENABLED
    late_entry_end: str = LATE_ENTRY_END
    late_entry_min_strength: str = LATE_ENTRY_MIN_STRENGTH
    expiry_late_entry: bool = EXPIRY_LATE_ENTRY
    expiry_late_entry_end: str = EXPIRY_LATE_ENTRY_END
    expiry_late_entry_min_strength: str = EXPIRY_LATE_ENTRY_MIN_STRENGTH
    eod_review_time: str = EOD_REVIEW_TIME
    eod_hard_time: str = EOD_HARD_TIME
    eod_runner_giveback_pct: float = EOD_RUNNER_GIVEBACK_PCT
    allow_overnight_carry: bool = ALLOW_OVERNIGHT_CARRY
    overnight_min_gain_pct: float = OVERNIGHT_MIN_GAIN_PCT
    overnight_min_strength: str = OVERNIGHT_MIN_STRENGTH
    wick_requires_confirmation: bool = WICK_REQUIRES_CONFIRMATION
    trend_slope_lookback: int = TREND_SLOPE_LOOKBACK
    trend_slope_min_pct: float = TREND_SLOPE_MIN_PCT
    entry_confirm_seconds: int = ENTRY_CONFIRM_SECONDS
    early_entry_min_strength: str = EARLY_ENTRY_MIN_STRENGTH
    require_bar_close_window: bool = REQUIRE_BAR_CLOSE_WINDOW
    enable_chop_filter: bool = ENABLE_CHOP_FILTER
    chop_atr_mult: float = CHOP_ATR_MULT
    chop_slope_threshold: float = CHOP_SLOPE_THRESHOLD
    enable_pullback_entries: bool = ENABLE_PULLBACK_ENTRIES
    adaptive_sl_enabled: bool = ADAPTIVE_SL_ENABLED
    large_candle_atr_mult: float = LARGE_CANDLE_ATR_MULT
    sl_buffer_atr_mult: float = SL_BUFFER_ATR_MULT
    sl_candle_buffer_atr_mult: float = SL_CANDLE_BUFFER_ATR_MULT
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

    @classmethod
    def from_settings(cls, settings: dict | None = None, symbol: str | None = None,
                      **overrides) -> "Ema9RsiMomentumConfig":
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

        # The chart timeframe the user picked in the UI ("5 Min", "15 Min",
        # "1 Hour", ...) is stored as a plain "timeframe" string, not under
        # the ema9_rsi_ prefix -- it belongs to the whole app, not to this
        # strategy. Before 2026-09-22 nothing mapped it onto
        # `timeframe_minutes`, so the field sat at its default of 5 whatever
        # the user selected: they watched a 15-minute chart while the rules
        # ran on 5-minute bars. An explicit ema9_rsi_timeframe_minutes still
        # wins, which is how the variant shadow book pins 5 and 15 side by
        # side regardless of the UI.
        if "timeframe_minutes" not in kwargs and settings.get("timeframe") is not None:
            from shared.timeframes import parse_timeframe
            kwargs["timeframe_minutes"] = parse_timeframe(
                settings["timeframe"], TIMEFRAME_MINUTES)

        # Per-symbol overrides last but one: SENSEX is not NIFTY, and one
        # global parameter set was costing it real money (see SYMBOL_OVERRIDES).
        # An explicit keyword override still wins over everything.
        if symbol:
            table = settings.get("ema9_rsi_symbol_overrides", SYMBOL_OVERRIDES) or {}
            key = _symbol_key(symbol)
            for field_name, value in (table.get(key) or {}).items():
                if field_name in cls.__dataclass_fields__:
                    kwargs[field_name] = value

        kwargs.update({k: v for k, v in overrides.items() if v is not None})
        return cls(**kwargs)
