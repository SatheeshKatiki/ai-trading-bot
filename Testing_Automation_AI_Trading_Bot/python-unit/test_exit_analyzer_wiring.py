"""Regression tests for the AI Exit Analyzer (2026-09-09).

v3.13.0 shipped `shared/exits/exit_analyzer.py` as a headline feature. It
never ran, and had it run it would have been wrong on options -- the exact
instrument it was written for.

Three distinct defects, all covered here:

A. **Never enabled.** `main.py` built `SmartExitEngine(...)` leaving
   `enable_exit_analyzer` at its `False` default, and nothing ever set it.
   `ema9_rsi_momentum/config.py` declared `ENABLE_EXIT_ANALYZER = True` and a
   matching dataclass field, but no code path read that field.

B. **Never fed.** `main.py` called `evaluate_exit(pos, price, time, atr)` with
   no `df`, so Factors 2-4 (price action, RSI, volume) -- 65% of the scoring
   weight -- were permanently zero and total urgency could never reach the
   0.70 threshold. Only Factor 1 (max 0.35) could contribute.

C. **Unreachable on options, and inverted on puts.**
   - Factor 1 honoured `is_option_premium` (12% of entry premium) while the
     PEAK_LOCK / FAST_EMA_BREAK *decisions* re-tested a hardcoded
     `peak_profit >= 30.0` points. On a Rs.150 premium a 12% (18-point) peak
     scored as significant but could never fire an exit.
   - The same `direction` drove both the premium-space peak maths and the
     underlying-momentum factors. A bought PUT is `direction=+1` in premium
     space, so its confirming down-bars were scored as bullish exhaustion --
     the analyzer would exit a winning put into its own trend.

Tuning was also inert: `ExitAnalyzerAgent()` was constructed with no
arguments, so MIN_PEAK_PROFIT_PTS / MAX_GIVEBACK_PCT / URGENCY_THRESHOLD
reached nothing.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from shared.exits.exit_analyzer import ExitAnalyzerAgent, PEAK_LOCK
from shared.exits.exit_engine import Position, SmartExitEngine


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _trending_frame(start: float, end: float, n: int = 60) -> pd.DataFrame:
    close = pd.Series(np.linspace(start, end, n))
    return pd.DataFrame({
        "open": close + 5, "high": close + 8, "low": close - 8,
        "close": close, "volume": np.full(n, 100_000.0),
    })


def _position(symbol: str, side: int, entry: float, high: float, low: float) -> Position:
    """A position that has already taken its partial profit.

    `evaluate_exit` runs partial booking (step 4) BEFORE the Exit Analyzer
    (step 4b) and returns as soon as it fires. A fresh position sitting at 1:1
    would therefore book partial and never reach the analyzer at all, so these
    tests model the state the analyzer is actually designed for: a runner left
    open after the first target, now at risk of giving back its peak.
    """
    return Position(
        symbol=symbol, side=side, entry_price=entry, quantity=75,
        entry_time="2026-09-09 09:30:00",
        stop_loss=entry * 0.7, target=entry * 1.5,
        highest_price=high, lowest_price=low,
        is_partially_booked=True,
    )


# ---------------------------------------------------------------------------
# Defect C1 -- the option threshold must govern the DECISION, not just scoring
# ---------------------------------------------------------------------------

def test_peak_lock_fires_on_an_option_that_never_reaches_30_points():
    """Rs.150 CE peaks +12% (18 pts) then gives back 25%.

    18 points is a significant peak by the option rule (12% of entry) but is
    below the old hardcoded 30-point decision gate, so PEAK_LOCK could never
    fire. This is the headline "don't give back your peak profit" protection
    being unreachable on the instrument it exists for.
    """
    agent = ExitAnalyzerAgent()
    entry, peak = 150.0, 168.0            # +18.0 pts == +12.0% of entry
    current = peak - (18.0 * 0.25)        # gave back 25% of the peak

    res = agent.evaluate(
        entry_price=entry, current_price=current,
        highest_price=peak, lowest_price=entry,
        direction=1, is_option_premium=True,
    )

    assert res.factors["peak_profit"] == 18.0
    assert res.factors["significant_peak"] == 18.0
    assert res.factors["giveback_pct"] == 25.0
    assert res.should_exit is True
    assert res.mode == PEAK_LOCK


def test_index_positions_still_use_the_absolute_points_threshold():
    """`is_option_premium=False` must keep the 30-point rule unchanged."""
    agent = ExitAnalyzerAgent()
    res = agent.evaluate(
        entry_price=24_000.0, current_price=24_020.0,
        highest_price=24_025.0, lowest_price=24_000.0,
        direction=1, is_option_premium=False,
    )
    assert res.factors["significant_peak"] == 30.0
    assert res.should_exit is False, "a 25-point index peak is below the 30-pt bar"


# ---------------------------------------------------------------------------
# Defect C2 -- premium direction vs underlying direction
# ---------------------------------------------------------------------------

def test_winning_put_is_not_scored_as_a_reversal():
    """Index falling hard, PE premium rising: the thesis is working.

    With the old code the premium-space direction (+1) was reused for the
    momentum factors, so every confirming down-bar read as bullish exhaustion.
    """
    agent = ExitAnalyzerAgent()
    falling = _trending_frame(24_000, 23_700)
    common = dict(
        entry_price=100.0, current_price=130.0, highest_price=134.0,
        lowest_price=100.0, direction=1, df=falling, is_option_premium=True,
    )

    as_put = agent.evaluate(**common, underlying_direction=-1)
    reused_premium_dir = agent.evaluate(**common, underlying_direction=1)

    assert as_put.factors["price_action"] < reused_premium_dir.factors["price_action"], (
        "a falling index must be less alarming for a PUT than for a CALL"
    )
    assert as_put.urgency_score < reused_premium_dir.urgency_score


def test_winning_call_is_not_scored_as_a_reversal():
    """Mirror image: rising index, CE premium rising."""
    agent = ExitAnalyzerAgent()
    rising = _trending_frame(23_700, 24_000)
    common = dict(
        entry_price=100.0, current_price=130.0, highest_price=134.0,
        lowest_price=100.0, direction=1, df=rising, is_option_premium=True,
    )

    as_call = agent.evaluate(**common, underlying_direction=1)
    inverted = agent.evaluate(**common, underlying_direction=-1)

    assert as_call.factors["price_action"] < inverted.factors["price_action"]


def test_underlying_direction_defaults_to_direction():
    """Cash/futures, where the two directions coincide, must be unchanged."""
    agent = ExitAnalyzerAgent()
    frame = _trending_frame(24_000, 23_700)
    kwargs = dict(
        entry_price=23_800.0, current_price=23_900.0, highest_price=23_950.0,
        lowest_price=23_800.0, direction=1, df=frame,
    )
    assert agent.evaluate(**kwargs).factors == agent.evaluate(**kwargs, underlying_direction=1).factors


# ---------------------------------------------------------------------------
# Defect A/B -- the engine must actually enable and feed the analyzer
# ---------------------------------------------------------------------------

def test_engine_passes_the_underlying_direction_for_a_put():
    """SmartExitEngine must translate position.side into thesis direction.

    An option position is evaluated as side=+1 in premium space, so the real
    CE/PE sign has to be forwarded separately or the inversion returns.
    """
    engine = SmartExitEngine(enable_exit_analyzer=True)
    captured = {}

    class _Spy:
        def evaluate(self, **kw):
            captured.update(kw)
            from shared.exits.exit_analyzer import ExitAnalysisResult, TREND_RIDE
            return ExitAnalysisResult(should_exit=False, urgency_score=0.0, mode=TREND_RIDE)

    engine.exit_analyzer = _Spy()
    pe = _position("NSE:NIFTY2691523700PE", side=-1, entry=100.0, high=140.0, low=100.0)

    engine.evaluate_exit(pe, 130.0, "11:00:00", 5.0, df=_trending_frame(24_000, 23_700))

    assert captured["direction"] == 1, "premium space: a bought PE profits when premium rises"
    assert captured["underlying_direction"] == -1, "thesis space: a PE is a bearish bet"
    assert captured["is_option_premium"] is True


def test_engine_forwards_analyzer_tuning():
    """The config knobs were declared but connected to nothing."""
    engine = SmartExitEngine(
        enable_exit_analyzer=True,
        exit_analyzer_kwargs={
            "min_peak_profit_pts": 55.0,
            "max_giveback_pct": 12.5,
            "urgency_threshold": 0.42,
        },
    )
    assert engine.exit_analyzer.min_peak_profit_pts == 55.0
    assert engine.exit_analyzer.max_giveback_pct == 12.5
    assert engine.exit_analyzer.urgency_threshold == 0.42


def test_analyzer_is_off_by_default_and_opt_in():
    """Enabling it changes exit behaviour, so it must be a deliberate choice."""
    assert SmartExitEngine().enable_exit_analyzer is False


def test_evaluate_exit_accepts_a_dataframe():
    """Defect B: without `df`, 65% of the scoring weight is dead."""
    engine = SmartExitEngine(enable_exit_analyzer=True)
    pos = _position("NSE:NIFTY2691524000CE", side=1, entry=100.0, high=140.0, low=100.0)

    should_exit, reason, qty = engine.evaluate_exit(
        pos, 130.0, "11:00:00", 5.0, df=_trending_frame(23_700, 24_000)
    )
    assert isinstance(should_exit, bool) and isinstance(reason, str)


@pytest.mark.parametrize("frame", [None, pd.DataFrame()])
def test_analyzer_tolerates_a_missing_or_empty_frame(frame):
    """Cold start: the engine must not crash before candles exist."""
    engine = SmartExitEngine(enable_exit_analyzer=True)
    pos = _position("NSE:NIFTY2691524000CE", side=1, entry=100.0, high=140.0, low=100.0)
    should_exit, _, _ = engine.evaluate_exit(pos, 130.0, "11:00:00", 5.0, df=frame)
    assert isinstance(should_exit, bool)
