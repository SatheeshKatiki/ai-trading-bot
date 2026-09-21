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
# Owner's window, 2026-09-22: 09:20 to 15:15 (was 09:25-15:00).
# Measured over 675 sessions with costs from real premiums: NIFTY +Rs.11,150
# -> +Rs.11,150 and SENSEX -Rs.37,841 -> -Rs.37,841. Neutral either way, so
# the owner's preference decides.
TIME_START: str = "09:20"
TIME_END: str = "15:15"

# ─────────────────────────────────────────────────────────────────────
# Expiry-day late entry (owner's rule, 2026-09-22)
# ─────────────────────────────────────────────────────────────────────
# Nothing is entered after TIME_END -- except on an expiry day, where a
# genuinely strong signal may still be taken until EXPIRY_LATE_ENTRY_END.
# 0DTE premium after 15:15 is nearly all delta and no time value, so a real
# move pays quickly; but the same thinness punishes a marginal signal, which
# is why this needs VERY_STRONG momentum and nothing less.
EXPIRY_LATE_ENTRY: bool = True
EXPIRY_LATE_ENTRY_END: str = "15:25"
EXPIRY_LATE_ENTRY_MIN_STRENGTH: str = "VERY_STRONG"

# ─────────────────────────────────────────────────────────────────────
# Anticipating a crossover (owner asked 2026-09-22; OFF by default)
# ─────────────────────────────────────────────────────────────────────
# "If it has not crossed yet but is about to within the next candle or two,
# treat it as a signal." Implemented, and OFF, because it was measured as the
# single most damaging change tried on this strategy:
#
#                                        NIFTY net    SENSEX net
#   exact cross only (today)              +11,150       -37,841
#   + anticipate within 1 bar             -64,551       -56,247
#   + anticipate within 2 bars            -98,964       -63,470
#
# Tried at three tightness settings (gap < 0.15 / 0.30 / 0.50 x ATR) and with
# an added RSI-strength requirement; every variant was worse on both indices.
# The reason is structural: EMA9 approaches EMA20 far more often than it
# crosses it, so anticipating roughly doubles the trade count (178 -> 350+)
# and nearly all of the extra trades are the approaches that failed.
#
# Set `ema9_rsi_anticipate_cross_bars` to 1 or 2 to enable.
ANTICIPATE_CROSS_BARS: int = 0
ANTICIPATE_MAX_GAP_ATR: float = 0.30
ENABLE_TOUCH_FILTER: bool = True

# How the crossover candle must sit against the EMA cluster.
#
#   "body_or_wick"  the owner's rule (2026-09-22): the candle must reach BOTH
#                   EMAs -- its body preferred, its wick accepted. A signal
#                   carries which of the two it was, so the books can log it.
#   "body"          the strict half of that rule: the BODY must reach both.
#   "legacy"        the pre-2026-09-22 one-sided check (low <= upper EMA +
#                   0.06% buffer), kept only so an old run can be reproduced.
#
# Measured on 675 sessions of NIFTY and SENSEX 5-min (2024-01-01..2026-09-21),
# costs calibrated from real option premiums, at the 2,136 / 2,226 crossover
# bars in that history:
#
#              passes  NIFTY net  SENSEX net   beats "legacy" in
#   legacy        90%   -93,739    -1,11,112   --
#   body_or_wick  38%   -28,982      -53,100   7/11 and 9/11 quarters
#   body          22%   +17,534      -37,766   10/11 and 8/11 quarters
#
# "body" is the better performer on both indices; "body_or_wick" is the
# owner's literal instruction and stays the default until the owner chooses.
EMA_TOUCH_MODE: str = "body_or_wick"
LEGACY_TOUCH_BUFFER_PCT: float = 0.0006  # only read when mode == "legacy"

# ─────────────────────────────────────────────────────────────────────
# How a wick touch has to earn its entry (owner's rule, 2026-09-22)
# ─────────────────────────────────────────────────────────────────────
# The owner keeps both kinds of touch but wants them weighted: a body touch
# is first preference, a wick touch second, and the bot decides for itself
# whether a given wick signal is worth taking rather than taking them all.
#
# A body touch is taken on its own (priority HIGH). A wick touch must ALSO
# agree with the trend and show RSI genuinely separated from its own average
# (priority MEDIUM); a wick touch that shows neither is skipped (LOW).
#
# Measured over 2024-01-01..2026-09-21 on NIFTY and SENSEX 5-min, costs
# calibrated from real option premiums, on the wick-only signals alone:
#
#   wick gate                 NIFTY Rs/trade   SENSEX Rs/trade
#   take every wick                     -268              -169
#   trend agrees                         -74               -59
#   RSI gap >= 3                        -266              -181
#   trend agrees AND gap >= 3            -17               -44   <- this
#
# Against taking every wick, that beat the alternative in 11/11 NIFTY and
# 7/11 SENSEX quarters, fixed rule, no per-period fitting. It does not make
# wick trades profitable -- it stops them paying for the body trades.
WICK_REQUIRES_CONFIRMATION: bool = True
WICK_MIN_RSI_GAP: float = 3.0        # |RSI - RSI-MA| the wick signal must show
TREND_SLOPE_LOOKBACK: int = 6        # bars the EMA20 slope is measured over
TREND_SLOPE_MIN_PCT: float = 0.02    # slope, as % of price, to count as agreeing

# ─────────────────────────────────────────────────────────────────────
# Entry timing (owner's rule, 2026-09-22)
# ─────────────────────────────────────────────────────────────────────
# A crossover is only final once its candle closes: intrabar, EMA9 can cross
# EMA20 and cross back before the bar is done. So an entry is taken in the
# last `ENTRY_CONFIRM_SECONDS` of the forming candle, when the bar is all but
# settled. Earlier in the bar an entry is allowed only when momentum is
# already at least `EARLY_ENTRY_MIN_STRENGTH` (see classify_momentum_strength),
# i.e. the move is strong enough not to wait for confirmation.
ENTRY_CONFIRM_SECONDS: int = 10
EARLY_ENTRY_MIN_STRENGTH: str = "STRONG"

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
    anticipate_cross_bars: int = ANTICIPATE_CROSS_BARS
    anticipate_max_gap_atr: float = ANTICIPATE_MAX_GAP_ATR
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
    wick_min_rsi_gap: float = WICK_MIN_RSI_GAP
    trend_slope_lookback: int = TREND_SLOPE_LOOKBACK
    trend_slope_min_pct: float = TREND_SLOPE_MIN_PCT
    entry_confirm_seconds: int = ENTRY_CONFIRM_SECONDS
    early_entry_min_strength: str = EARLY_ENTRY_MIN_STRENGTH
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
