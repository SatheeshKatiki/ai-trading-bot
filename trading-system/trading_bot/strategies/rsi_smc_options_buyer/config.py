"""Parameters for RSI_SMC_OPTIONS_BUYER_V1.

One dataclass, built from the same flat ``config/settings.json`` dict every
other strategy reads, using the ``rsi_smc_<field>`` key convention that
``Ema9RsiMomentumConfig`` already established. No second configuration
framework is introduced.

Every value here is either

* **structural** -- a definition rather than a tuned number (the opening EMA
  length; the 6x minimum-bars multiple demanded by the SMC engine's own
  internal clamp), or
* **provisional** -- a starting point the research phase is expected to
  replace via ``rules.v1.json``, and which must survive an out-of-sample
  split before it is treated as evidence.

The one number here that is NOT provisional is ``htf_slope_min_pct``. The
0.02% EMA20 slope threshold is the only entry condition measured in this
repository that survived an out-of-sample split on two instruments -- it beat
the plain default in 8/11 NIFTY and 10/11 SENSEX quarters and beat a
trade-count-matched random control, which the other ~15 candidates tried did
not. It is imported as evidence, not swept.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Optional, Sequence, Tuple

#: Registry / package / UI name. The package DIRECTORY must keep this exact
#: spelling: ``shared.entry_gate._grader`` resolves a strategy's own entry
#: grader with ``importlib.import_module(f"trading_bot.strategies.{name}")``.
STRATEGY_NAME = "rsi_smc_options_buyer"

#: Versioned identity for logs, journal rows and results filenames.
STRATEGY_ID = "RSI_SMC_OPTIONS_BUYER_V1"

# ---------------------------------------------------------------------
# Higher timeframe bias
# ---------------------------------------------------------------------
HTF_MINUTES: int = 15
HTF_EMA: int = 20
HTF_SLOPE_LOOKBACK: int = 6
HTF_SLOPE_MIN_PCT: float = 0.02

# ---------------------------------------------------------------------
# SMC engine parameters (passed through to LuxAlgoSMCConfig unchanged)
# ---------------------------------------------------------------------
#: Pivot length the structure engine uses. 5 is LuxAlgo's own
#: ``internal_length`` default -- the INTERNAL structure definition, as
#: opposed to its 50-bar swing structure. This strategy trades intraday
#: internal structure, so that is the matching definition.
#:
#: It is also, measured, the only length in the swept grid that yields a
#: statistically testable number of signals in a year. On 18,766 NIFTY 5-min
#: bars (251 sessions) the whole grid produced:
#:
#:     swing 20 -> 0-9 signals/yr     swing 15 -> 2-18
#:     swing 10 -> 5-24               swing  8 -> 6-22
#:     swing  5 -> 16-51
#:
#: Only ``swing=5, confirm_window=8`` clears the 30-trade minimum that gate
#: N2 needs for a trustworthy mean (NIFTY 51, SENSEX 54, both ~0.20
#: signals/session). THAT IS A MEASURABILITY CHOICE, NOT EVIDENCE OF EDGE --
#: it says the machinery produces enough events to be measured at all, and
#: nothing whatever about whether those events are profitable. The research
#: phase must set this against a pre-registered out-of-sample split before
#: any live consideration, and ``rules.v1.json`` is where that verdict lands.
SWING_POINTS_LENGTH: int = 5
INTERNAL_LENGTH: int = 5

#: ``calculate_smc`` clamps its own lookback with
#: ``effective_swing_len = min(swing_points_length, max(3, n // 6))``, so
#: below 6x the swing length the structure it reports is computed against a
#: DIFFERENT lookback than the one configured, and the prefix-stability the
#: per-bar projection depends on is no longer guaranteed. Hard gate, not a
#: warning. See structure.py.
MIN_BARS_SWING_MULTIPLE: int = 6

# ---------------------------------------------------------------------
# Levels, sweeps and confirmation
# ---------------------------------------------------------------------
#: How close (in ATR) price must be to a key level for it to be in play.
LEVEL_ATR_MULT: float = 1.5
#: Window of bars a sweep is looked for in (the reference detector's
#: ``swing_lookback``).
SWEEP_LOOKBACK: int = 20
#: How many of the most recent bars inside that window may carry the sweep
#: (the reference detector's fixed 5).
SWEEP_RECENT_BARS: int = 5
#: Bars after the structure event within which the entry trigger must land --
#: the retest window. 8 bars is 40 minutes on a 5-minute chart.
#:
#: Chosen for sample adequacy alongside SWING_POINTS_LENGTH above, not for
#: performance: at 3 and 5 the same grid produced 16 and 31 NIFTY signals a
#: year against 51 here. Provisional, pending the research phase.
CONFIRM_WINDOW: int = 8

# ---------------------------------------------------------------------
# RSI -- confirmation only, never a trigger
# ---------------------------------------------------------------------
RSI_LENGTH: int = 14
RSI_MA_LENGTH: int = 20
RSI_MIDLINE: float = 50.0
#: RSI divergence ships OFF. It may only be switched on if the offline
#: research phase shows it separates outcomes OUT OF SAMPLE.
USE_RSI_DIVERGENCE: bool = False

# ---------------------------------------------------------------------
# Price-action trigger
# ---------------------------------------------------------------------
ATR_LENGTH: int = 14
MIN_BODY_ATR: float = 1.0
MAX_CLOSE_FROM_EXTREME: float = 0.35
#: Allow an unmitigated FVG reaction as an alternative trigger.
USE_FVG_TRIGGER: bool = True

#: Allow a CONFIRMED, unmitigated Order Block reaction as an alternative
#: trigger. Order Blocks ARE causally available -- structure.py recovers each
#: block's confirmation bar from the structure event that created it, and the
#: strategy may not read one before that bar.
#:
#: Ships OFF so V1's entry rules are exactly what was measured. It is a
#: research knob, not a default change: turning it on widens the trigger and
#: must earn its place on an out-of-sample split first.
USE_OB_TRIGGER: bool = False

# ---------------------------------------------------------------------
# Regime / no-trade envelope
# ---------------------------------------------------------------------
MIN_REGIME_SCORE: int = 40
CHOPPINESS_MAX: float = 61.8
ATR_PCT_MIN: float = 0.0001
ATR_PCT_MAX: float = 0.025
TIME_START: str = "09:25"
TIME_END: str = "15:00"
MIN_RR: float = 1.5

# ---------------------------------------------------------------------
# Exits (M1). Same shape as the owner's ema9 ladder, which is the exit
# design already ratified for this book: no fixed target, a stop that only
# ratchets up, and the trade ends on the stop, a structure reversal or EOD.
# ---------------------------------------------------------------------
INITIAL_SL_PCT: float = 15.0
PROFIT_LADDER_PCT: Tuple[float, ...] = (15.0, 33.0, 50.0, 75.0, 100.0, 150.0, 200.0)
#: Structural stop: how far past the swept extreme the underlying
#: invalidation sits, in ATR.
SL_ATR_BUFFER: float = 0.5
#: Track the underlying's swept extreme as a structural invalidation, in
#: ADDITION to (never instead of) the premium ladder.
USE_STRUCTURAL_STOP: bool = True

# ---------------------------------------------------------------------
# Contract quality screen (M2). SPREAD / QUOTE / VOLUME ONLY.
#
# Open Interest, OI change, Implied Volatility and Delta are NOT available on
# the live execution path. Their only source in this repository is
# ``api_bridge.py::_fetch_real_option_chain``, an async function inside the
# FastAPI application module, which ``trading_bot/main.py`` cannot import.
# They are BLOCKED for V1 and are deliberately NOT approximated, inferred or
# proxied. Do not add a "close enough" substitute here -- a wrong liquidity
# read is worse than an absent one, because it looks like a safeguard.
# ---------------------------------------------------------------------
MAX_SPREAD_PCT: float = 3.0
MIN_CONTRACT_VOLUME: int = 0
QUOTE_MAX_AGE_S: float = 5.0

#: The four index instruments this strategy may trade. An equity symbol
#: reaches ``main.py``'s entry path with ``option_mapping_required`` False,
#: which would take the trade as EQUITY. This is an options-buying strategy,
#: so anything outside this set emits 0 with a logged reason.
ALLOWED_INSTRUMENTS: Tuple[str, ...] = ("NIFTY", "BANKNIFTY", "SENSEX", "FINNIFTY")

TIMEFRAME_MINUTES: int = 5

#: Per-symbol overrides, same mechanism as ema9's. Empty until measured: an
#: untested override is worse than none.
SYMBOL_OVERRIDES: dict = {}


def _symbol_key(symbol: str) -> str:
    """Canonical instrument key for override lookup and the instrument gate."""
    try:
        from shared.instruments import normalize_instrument
        return normalize_instrument(symbol or "")
    except Exception:
        return (symbol or "").upper()


@dataclass
class RsiSmcConfig:
    """Every knob this strategy reads.

    Field names map to settings keys as ``rsi_smc_<field>``.
    """

    htf_minutes: int = HTF_MINUTES
    htf_ema: int = HTF_EMA
    htf_slope_lookback: int = HTF_SLOPE_LOOKBACK
    htf_slope_min_pct: float = HTF_SLOPE_MIN_PCT

    swing_points_length: int = SWING_POINTS_LENGTH
    internal_length: int = INTERNAL_LENGTH
    min_bars_swing_multiple: int = MIN_BARS_SWING_MULTIPLE

    level_atr_mult: float = LEVEL_ATR_MULT
    sweep_lookback: int = SWEEP_LOOKBACK
    sweep_recent_bars: int = SWEEP_RECENT_BARS
    confirm_window: int = CONFIRM_WINDOW

    rsi_length: int = RSI_LENGTH
    rsi_ma_length: int = RSI_MA_LENGTH
    rsi_midline: float = RSI_MIDLINE
    use_rsi_divergence: bool = USE_RSI_DIVERGENCE

    atr_length: int = ATR_LENGTH
    min_body_atr: float = MIN_BODY_ATR
    max_close_from_extreme: float = MAX_CLOSE_FROM_EXTREME
    use_fvg_trigger: bool = USE_FVG_TRIGGER
    use_ob_trigger: bool = USE_OB_TRIGGER

    min_regime_score: int = MIN_REGIME_SCORE
    choppiness_max: float = CHOPPINESS_MAX
    atr_pct_min: float = ATR_PCT_MIN
    atr_pct_max: float = ATR_PCT_MAX
    time_start: str = TIME_START
    time_end: str = TIME_END
    min_rr: float = MIN_RR

    initial_sl_pct: float = INITIAL_SL_PCT
    profit_ladder_pct: Sequence[float] = PROFIT_LADDER_PCT
    sl_atr_buffer: float = SL_ATR_BUFFER
    use_structural_stop: bool = USE_STRUCTURAL_STOP

    max_spread_pct: float = MAX_SPREAD_PCT
    min_contract_volume: int = MIN_CONTRACT_VOLUME
    quote_max_age_s: float = QUOTE_MAX_AGE_S

    allowed_instruments: Sequence[str] = ALLOWED_INSTRUMENTS
    timeframe_minutes: int = TIMEFRAME_MINUTES

    @property
    def min_bars(self) -> int:
        """Below this the SMC engine silently changes its own lookback.

        See :data:`MIN_BARS_SWING_MULTIPLE`.
        """
        return int(self.min_bars_swing_multiple) * int(self.swing_points_length)

    @classmethod
    def from_settings(cls, settings: Optional[Mapping[str, Any]] = None,
                      symbol: Optional[str] = None, **overrides) -> "RsiSmcConfig":
        """Build from a flat settings dict, then per-symbol overrides, then
        explicit keywords.

        Same precedence order as ``Ema9RsiMomentumConfig.from_settings``, so a
        reader of one already knows the other.
        """
        settings = settings or {}
        kwargs: dict = {}
        for field_name in cls.__dataclass_fields__:
            key = f"rsi_smc_{field_name}"
            if key in settings:
                kwargs[field_name] = settings[key]

        # The chart timeframe belongs to the whole app, not to this strategy,
        # so it is stored unprefixed. An explicit rsi_smc_timeframe_minutes
        # still wins -- that is how a shadow book pins one timeframe.
        if "timeframe_minutes" not in kwargs and settings.get("timeframe") is not None:
            try:
                from shared.timeframes import parse_timeframe
                kwargs["timeframe_minutes"] = parse_timeframe(
                    settings["timeframe"], TIMEFRAME_MINUTES)
            except Exception:
                pass

        if symbol:
            table = settings.get("rsi_smc_symbol_overrides", SYMBOL_OVERRIDES) or {}
            for field_name, value in (table.get(_symbol_key(symbol)) or {}).items():
                if field_name in cls.__dataclass_fields__:
                    kwargs[field_name] = value

        kwargs.update({k: v for k, v in overrides.items() if v is not None})
        return cls(**kwargs)

    def instrument_allowed(self, symbol: str) -> bool:
        """Whether this strategy may trade ``symbol`` at all."""
        return _symbol_key(symbol) in tuple(self.allowed_instruments)


__all__ = [
    "STRATEGY_NAME",
    "STRATEGY_ID",
    "RsiSmcConfig",
    "ALLOWED_INSTRUMENTS",
    "SYMBOL_OVERRIDES",
    "MIN_BARS_SWING_MULTIPLE",
]
