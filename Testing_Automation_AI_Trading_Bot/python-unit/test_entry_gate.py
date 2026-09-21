"""The bot grades its own entries, for whichever strategy is selected.

The owner's instruction, 2026-09-22: keep both kinds of EMA touch, but give
a body touch maximum preference and a wick touch low-to-medium -- and let the
bot work out for itself whether a given wick signal is worth taking, rather
than taking every one. And all of it must follow whichever strategy and
timeframe the user picked in the UI.

So there are two layers:

  * `shared.entry_gate` is strategy-neutral. It always applies the bar-close
    timing rule on the user's selected timeframe, and asks the SELECTED
    strategy for its own entry grade. A strategy that publishes no grader is
    UNGRADED -- gated on timing alone, never penalised for having no view.
  * `ema9_rsi_momentum` publishes a grader: HIGH for a body touch, MEDIUM for
    a wick touch that also agrees with the trend and shows RSI clear of its
    own average, LOW for a wick touch with neither.

Measured on wick-only signals over 2024-01-01..2026-09-21 with costs from
real option premiums: taking every wick cost Rs.268/trade on NIFTY and
Rs.169 on SENSEX; requiring both confirmations brought those to Rs.17 and
Rs.44, and beat taking-every-wick in 11/11 NIFTY and 7/11 SENSEX quarters.
"""

from __future__ import annotations

import datetime
import pathlib

import numpy as np
import pandas as pd
import pytest

import _bootstrap  # noqa: F401  (side-effect: puts trading-system/ on sys.path)

from shared.entry_gate import UNGRADED, decide, grade_entry
from trading_bot.strategies.ema9_rsi_momentum import assess_entry_quality
from trading_bot.strategies.ema9_rsi_momentum.config import Ema9RsiMomentumConfig
from trading_bot.strategies.ema9_rsi_momentum.indicators import compute_indicator_set
from trading_bot.strategies.ema9_rsi_momentum.signal_engine import (
    PRIORITY_HIGH,
    PRIORITY_LOW,
    PRIORITY_MEDIUM,
    PRIORITY_NONE,
    assess_entry_quality as assess_array,
)


def _cfg(**over) -> Ema9RsiMomentumConfig:
    return Ema9RsiMomentumConfig(**over)


class _Ind:
    """The four series the grader reads."""

    def __init__(self, fast, slow, rsi, rsi_ma):
        self.ema_fast = np.asarray(fast, dtype=float)
        self.ema_slow = np.asarray(slow, dtype=float)
        self.rsi = np.asarray(rsi, dtype=float)
        self.rsi_ma = np.asarray(rsi_ma, dtype=float)


def _one_bar(o, h, l, c, e9, e20, rsi, rsi_ma, slope_up=True, n=10):
    """A frame whose LAST bar is the one under test, with a chosen EMA20 slope."""
    idx = pd.date_range("2026-09-22 09:15", periods=n, freq="5min")
    df = pd.DataFrame({"open": [o] * n, "high": [h] * n, "low": [l] * n, "close": [c] * n},
                      index=idx)
    drift = 1.0 if slope_up else -1.0
    slow = [e20 - drift * (n - 1 - i) * 2.0 for i in range(n)]
    ind = _Ind([e9] * n, slow, [rsi] * n, [rsi_ma] * n)
    return df, ind


# ---------------------------------------------------------------------------
# A body touch is first preference and needs nothing else
# ---------------------------------------------------------------------------

def test_a_body_touch_is_high_priority_and_taken():
    df, ind = _one_bar(100.0, 112.0, 98.0, 110.0, 108.0, 102.0, rsi=50.0, rsi_ma=50.0)
    q = assess_array(df, ind, _cfg(), np.ones(len(df), dtype=int))
    assert q.priority[-1] == PRIORITY_HIGH
    assert q.take[-1]


def test_a_body_touch_is_taken_even_against_the_trend_and_with_rsi_flat():
    """Nothing left to confirm: the candle committed through both averages."""
    df, ind = _one_bar(100.0, 112.0, 98.0, 110.0, 108.0, 102.0,
                       rsi=50.0, rsi_ma=50.0, slope_up=False)
    q = assess_array(df, ind, _cfg(), np.ones(len(df), dtype=int))
    assert q.priority[-1] == PRIORITY_HIGH and q.take[-1]


# ---------------------------------------------------------------------------
# A wick touch has to earn it
# ---------------------------------------------------------------------------

def _wick_bar(rsi, rsi_ma, slope_up):
    # body 104..106 misses both EMAs; range 98..112 reaches both
    return _one_bar(104.0, 112.0, 98.0, 106.0, 110.0, 100.0,
                    rsi=rsi, rsi_ma=rsi_ma, slope_up=slope_up)


def test_a_wick_touch_with_both_confirmations_is_medium_and_taken():
    df, ind = _wick_bar(rsi=60.0, rsi_ma=50.0, slope_up=True)
    q = assess_array(df, ind, _cfg(), np.ones(len(df), dtype=int))
    assert q.trend_agrees[-1] and q.rsi_separated[-1]
    assert q.priority[-1] == PRIORITY_MEDIUM
    assert q.take[-1]


def test_a_wick_touch_against_the_trend_is_low_and_dropped():
    df, ind = _wick_bar(rsi=60.0, rsi_ma=50.0, slope_up=False)
    q = assess_array(df, ind, _cfg(), np.ones(len(df), dtype=int))
    assert not q.trend_agrees[-1]
    assert q.priority[-1] == PRIORITY_LOW
    assert not q.take[-1]


def test_a_wick_touch_with_rsi_hugging_its_average_is_low_and_dropped():
    df, ind = _wick_bar(rsi=50.5, rsi_ma=50.0, slope_up=True)      # gap 0.5 < 3
    q = assess_array(df, ind, _cfg(), np.ones(len(df), dtype=int))
    assert not q.rsi_separated[-1]
    assert q.priority[-1] == PRIORITY_LOW
    assert not q.take[-1]


def test_the_rsi_gap_threshold_is_configurable():
    df, ind = _wick_bar(rsi=52.0, rsi_ma=50.0, slope_up=True)      # gap 2.0
    assert not assess_array(df, ind, _cfg(), np.ones(len(df), int)).take[-1]
    assert assess_array(df, ind, _cfg(wick_min_rsi_gap=1.5), np.ones(len(df), int)).take[-1]


def test_confirmation_can_be_switched_off_entirely():
    df, ind = _wick_bar(rsi=50.5, rsi_ma=50.0, slope_up=False)
    q = assess_array(df, ind, _cfg(wick_requires_confirmation=False),
                     np.ones(len(df), dtype=int))
    assert q.take[-1], "off means every wick touch is taken again"


def test_a_short_wants_the_trend_sloping_the_other_way():
    """The same bar grades differently for a PE than for a CE."""
    df, ind = _wick_bar(rsi=40.0, rsi_ma=50.0, slope_up=False)
    ce = assess_array(df, ind, _cfg(), np.ones(len(df), dtype=int))
    pe = assess_array(df, ind, _cfg(), -np.ones(len(df), dtype=int))
    assert not ce.take[-1]
    assert pe.take[-1]


def test_no_touch_at_all_is_never_graded_or_taken():
    df, ind = _one_bar(120.0, 125.0, 118.0, 123.0, 108.0, 102.0, rsi=60.0, rsi_ma=50.0)
    q = assess_array(df, ind, _cfg(), np.ones(len(df), dtype=int))
    assert q.priority[-1] == PRIORITY_NONE
    assert not q.take[-1]


def test_body_mode_still_refuses_a_wick_however_well_confirmed():
    df, ind = _wick_bar(rsi=60.0, rsi_ma=50.0, slope_up=True)
    q = assess_array(df, ind, _cfg(ema_touch_mode="body"), np.ones(len(df), dtype=int))
    assert q.priority[-1] == PRIORITY_MEDIUM, "still graded honestly"
    assert not q.take[-1], "but the configured mode has the last word"


# ---------------------------------------------------------------------------
# The strategy publishes its grade to the shared gate
# ---------------------------------------------------------------------------

def _real_frame(n=400, seed=5) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    close = 24_000 + rng.normal(0, 12, n).cumsum()
    open_ = close - rng.normal(0, 6, n)
    half = rng.uniform(5, 22, n)
    return pd.DataFrame(
        {"open": open_, "high": np.maximum(close, open_) + half,
         "low": np.minimum(close, open_) - half, "close": close,
         "volume": rng.integers(1_000, 50_000, n).astype(float)},
        index=pd.date_range("2026-08-03 09:15", periods=n, freq="5min"))


def test_the_strategy_publishes_a_grader_for_the_shared_gate():
    grade = assess_entry_quality(_real_frame(), 1, {})
    assert grade is not None
    assert grade.priority in (PRIORITY_HIGH, PRIORITY_MEDIUM, PRIORITY_LOW, PRIORITY_NONE)
    assert grade.touch in ("body", "wick", "none")


def test_the_grader_declines_on_too_little_history():
    assert assess_entry_quality(_real_frame(n=10), 1, {}) is None
    assert assess_entry_quality(_real_frame(), 0, {}) is None


# ---------------------------------------------------------------------------
# The shared gate works for whichever strategy the user selected
# ---------------------------------------------------------------------------

def test_the_selected_strategys_own_grade_is_used():
    priority, _ = grade_entry("ema9_rsi_momentum", _real_frame(), 1, {})
    assert priority != UNGRADED


@pytest.mark.parametrize("strategy", [
    "ema_crossover_pro_strategy", "buy_the_dip_strategy", "not_a_real_strategy",
])
def test_a_strategy_without_a_grader_is_ungraded_not_blocked(strategy):
    """No opinion is not a reason to refuse a signal the strategy produced."""
    priority, _ = grade_entry(strategy, _real_frame(), 1, {})
    assert priority == UNGRADED
    at_close = datetime.datetime(2026, 9, 22, 9, 34, 55)
    assert decide(strategy, _real_frame(), 1, "NONE", {"timeframe": "5 Min"}, at_close).take


def test_a_low_graded_setup_is_dropped_even_inside_the_confirmation_window():
    """Quality is judged before timing: a bad setup is not saved by waiting."""
    df, ind = _wick_bar(rsi=50.5, rsi_ma=50.0, slope_up=True)
    assert not assess_array(df, ind, _cfg(), np.ones(len(df), int)).take[-1]
    src = pathlib.Path(_bootstrap.TRADING_SYSTEM_ROOT, "shared", "entry_gate.py").read_text(
        encoding="utf-8", errors="ignore")
    body = src[src.index("def decide("):]
    assert body.index("PRIORITY_LOW") < body.index("_timing("), \
        "quality must be checked before the timing gate"


@pytest.mark.parametrize("label,minutes", [("5 Min", 5), ("15 Min", 15), ("1 Hour", 60)])
def test_the_decision_carries_the_users_timeframe(label, minutes):
    d = decide("ema9_rsi_momentum", _real_frame(), 1, "NONE",
               {"timeframe": label}, datetime.datetime(2026, 9, 22, 10, 20, 0))
    assert d.timeframe_minutes == minutes


def test_the_decision_reads_as_one_log_line():
    d = decide("ema9_rsi_momentum", _real_frame(), 1, "NONE",
               {"timeframe": "15 Min"}, datetime.datetime(2026, 9, 22, 10, 20, 0))
    text = str(d)
    assert text.startswith(("take ", "hold "))
    assert "15 Min" in text or "LOW" in text


def test_the_gate_never_raises_on_a_broken_strategy_module():
    """A live book must not stop trading because a grader threw."""
    d = decide("definitely_not_a_module", _real_frame(), 1, "STRONG",
               {"timeframe": "5 Min"}, datetime.datetime(2026, 9, 22, 10, 20, 0))
    assert d.take


# ---------------------------------------------------------------------------
# Both books go through the shared gate
# ---------------------------------------------------------------------------

def _src(*parts) -> str:
    return pathlib.Path(_bootstrap.TRADING_SYSTEM_ROOT, *parts).read_text(
        encoding="utf-8", errors="ignore")


def test_both_books_use_the_shared_gate_with_the_selected_strategy():
    observer = _src("paper_observer.py")
    engine = _src("trading_bot", "main.py")
    assert "entry_decision(" in observer and "active_strategy" in observer
    assert "from shared.entry_gate import decide" in engine
    assert "_entry_timing_allows(\n" in engine or "_entry_timing_allows(" in engine
    assert "strategy_name)" in engine, "the live engine passes the selected strategy"
