"""The owner's entry rules, stated 2026-09-22, and the end of the second
implementation that used to contradict them.

Three things were wrong and are fixed here:

1. The chart computed its own BUY CE / BUY PE markers in TypeScript. That
   second implementation carried NO ADX filter and a wider EMA-touch buffer
   (0.08% vs the engine's 0.06%), so it drew entries the bot would never take.
   Checked on real data: NIFTY 2026-09-18 had ADX 10.6-16.7 all session, so
   the engine produced ZERO signals while the chart drew four.

2. The "EMA touch" filter was one-sided -- `low <= max(ema9, ema20) + buffer`.
   It never looked at the lower EMA at all and admitted 90% of NIFTY and 91%
   of SENSEX crossover bars over 2024-01-01..2026-09-21. It was not filtering.
   The owner's rule is that the candle must reach BOTH averages, its body for
   preference and its wick if not.

3. Entries were taken the moment a crossover appeared mid-candle, but a
   crossover is not final until its bar closes -- intrabar EMA9 can cross
   EMA20 and cross back. Entries now wait for the last seconds of the bar
   unless momentum is already strong.

These rules live in the strategy engine, which only ever sees an OHLC frame,
so they apply to every symbol the bot can trade -- indices and stocks alike.
"""

from __future__ import annotations

import datetime
import pathlib

import numpy as np
import pandas as pd
import pytest

import _bootstrap  # noqa: F401  (side-effect: puts trading-system/ on sys.path)

from trading_bot.strategies.ema9_rsi_momentum.config import Ema9RsiMomentumConfig
from trading_bot.strategies.ema9_rsi_momentum.signal_engine import (
    compute_cross_signals,
    ema_cluster_touch,
    entry_timing_gate,
    seconds_to_bar_close,
)


def _cfg(**over) -> Ema9RsiMomentumConfig:
    return Ema9RsiMomentumConfig(**over)


def _frame(rows) -> pd.DataFrame:
    """rows: (open, high, low, close) -- index is irrelevant to the touch test."""
    idx = pd.date_range("2026-09-22 09:15", periods=len(rows), freq="5min")
    return pd.DataFrame(rows, columns=["open", "high", "low", "close"], index=idx)


class _Ind:
    """Just the two EMA arrays `ema_cluster_touch` reads."""

    def __init__(self, fast, slow):
        self.ema_fast = np.asarray(fast, dtype=float)
        self.ema_slow = np.asarray(slow, dtype=float)


# ---------------------------------------------------------------------------
# Rule 2: the candle must reach BOTH moving averages
# ---------------------------------------------------------------------------

def test_a_candle_that_spans_both_emas_with_its_body_is_a_body_touch():
    df = _frame([(100.0, 112.0, 98.0, 110.0)])          # body 100..110
    ind = _Ind([108.0], [102.0])                         # both inside the body
    touch = ema_cluster_touch(df, ind, _cfg())
    assert touch.by_body[0] and touch.by_wick[0]
    assert touch.passes[0]


def test_a_candle_that_reaches_both_only_with_its_wick_is_a_wick_touch():
    df = _frame([(104.0, 112.0, 98.0, 106.0)])          # body 104..106, range 98..112
    ind = _Ind([110.0], [100.0])                         # outside the body, inside the range
    touch = ema_cluster_touch(df, ind, _cfg())
    assert not touch.by_body[0]
    assert touch.by_wick[0]
    assert touch.passes[0], "the owner accepts a wick touch as second preference"


def test_a_candle_floating_entirely_above_both_emas_touches_neither():
    """The real 2026-09-18 11:50 NIFTY bar: low 23306.50, emas 23306.42 /
    23305.58. It touched nothing, and the old 19-point buffer let it through."""
    df = _frame([(23310.0, 23325.40, 23306.50, 23321.30)])
    ind = _Ind([23306.42], [23305.58])
    touch = ema_cluster_touch(df, ind, _cfg())
    assert not touch.by_wick[0]
    assert not touch.by_body[0]
    assert not touch.passes[0]


def test_reaching_only_the_nearer_ema_is_not_enough():
    df = _frame([(104.0, 109.0, 103.0, 108.0)])          # range 103..109
    ind = _Ind([107.0], [99.0])                          # ema20 at 99 is never reached
    assert not ema_cluster_touch(df, ind, _cfg()).passes[0]


def test_body_mode_keeps_only_body_touches():
    df = _frame([(104.0, 112.0, 98.0, 106.0)])
    ind = _Ind([110.0], [100.0])                         # wick touch only
    assert ema_cluster_touch(df, ind, _cfg(ema_touch_mode="body_or_wick")).passes[0]
    assert not ema_cluster_touch(df, ind, _cfg(ema_touch_mode="body")).passes[0]


def test_legacy_mode_still_reproduces_the_old_one_sided_check():
    """Kept so an old run can be reproduced -- and so the gap is visible."""
    df = _frame([(23310.0, 23325.40, 23306.50, 23321.30)])
    ind = _Ind([23306.42], [23305.58])
    assert ema_cluster_touch(df, ind, _cfg(ema_touch_mode="legacy")).passes[0]
    assert not ema_cluster_touch(df, ind, _cfg(ema_touch_mode="body_or_wick")).passes[0]


def test_a_warming_up_ema_never_counts_as_a_touch():
    df = _frame([(100.0, 112.0, 98.0, 110.0)])
    assert not ema_cluster_touch(df, _Ind([np.nan], [102.0]), _cfg()).passes[0]
    assert not ema_cluster_touch(df, _Ind([108.0], [np.nan]), _cfg()).passes[0]


def test_the_rule_is_symbol_agnostic():
    """Same numbers, no symbol anywhere -- so a stock is judged like an index."""
    df = _frame([(1400.0, 1480.0, 1350.0, 1460.0)])      # a RELIANCE-sized bar
    ind = _Ind([1455.0], [1380.0])
    assert ema_cluster_touch(df, ind, _cfg()).passes[0]


# ---------------------------------------------------------------------------
# Rule 3: enter in the last seconds of the bar, or on strength
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("hhmmss,expected", [
    ("09:34:59", 1.0),
    ("09:34:50", 10.0),
    ("09:30:00", 300.0),
    ("09:32:30", 150.0),
])
def test_seconds_to_bar_close_is_measured_from_the_bar_boundary(hhmmss, expected):
    now = datetime.datetime.strptime("2026-09-22 " + hhmmss, "%Y-%m-%d %H:%M:%S")
    assert seconds_to_bar_close(now, 5) == pytest.approx(expected)


def test_seconds_to_bar_close_respects_the_timeframe():
    now = datetime.datetime(2026, 9, 22, 9, 31, 0)
    assert seconds_to_bar_close(now, 15) == pytest.approx(840.0)   # 09:30->09:45


def test_inside_the_confirmation_window_any_entry_is_allowed():
    now = datetime.datetime(2026, 9, 22, 9, 34, 52)                # 8s left
    ok, why = entry_timing_gate(now, "NONE", _cfg())
    assert ok and "confirmation window" in why


def test_the_window_boundary_is_inclusive():
    now = datetime.datetime(2026, 9, 22, 9, 34, 50)                # exactly 10s
    assert entry_timing_gate(now, "NONE", _cfg())[0]


def test_early_in_the_bar_a_weak_signal_waits():
    now = datetime.datetime(2026, 9, 22, 9, 32, 0)                 # 180s left
    ok, why = entry_timing_gate(now, "NORMAL", _cfg())
    assert not ok
    assert "waiting for bar close" in why and "NORMAL" in why


def test_early_in_the_bar_strong_momentum_does_not_wait():
    now = datetime.datetime(2026, 9, 22, 9, 32, 0)
    assert entry_timing_gate(now, "STRONG", _cfg())[0]
    assert entry_timing_gate(now, "VERY_STRONG", _cfg())[0]


def test_the_strength_floor_is_configurable():
    now = datetime.datetime(2026, 9, 22, 9, 32, 0)
    assert entry_timing_gate(now, "NORMAL", _cfg(early_entry_min_strength="NORMAL"))[0]


def test_a_longer_confirmation_window_is_honoured():
    now = datetime.datetime(2026, 9, 22, 9, 34, 30)                # 30s left
    assert not entry_timing_gate(now, "NONE", _cfg())[0]
    assert entry_timing_gate(now, "NONE", _cfg(entry_confirm_seconds=45))[0]


def test_both_books_apply_the_same_gate():
    """The two books must not disagree about when an entry may be taken."""
    observer = pathlib.Path(_bootstrap.TRADING_SYSTEM_ROOT, "paper_observer.py").read_text(
        encoding="utf-8", errors="ignore")
    engine = pathlib.Path(_bootstrap.TRADING_SYSTEM_ROOT, "trading_bot", "main.py").read_text(
        encoding="utf-8", errors="ignore")
    assert "entry_timing_gate(" in observer
    assert "entry_timing_gate(" in engine or "_entry_timing_allows(" in engine
    assert "classify_momentum_strength(" in observer


def test_the_live_gate_fails_open():
    """A broken helper must not silently stop a live book from trading."""
    engine = pathlib.Path(_bootstrap.TRADING_SYSTEM_ROOT, "trading_bot", "main.py").read_text(
        encoding="utf-8", errors="ignore")
    start = engine.index("def _entry_timing_allows")
    body = engine[start:start + 1600]
    assert "except Exception" in body
    assert "return True" in body


# ---------------------------------------------------------------------------
# Rule 1: one implementation, not two
# ---------------------------------------------------------------------------

def _chart_src() -> str:
    root = pathlib.Path(_bootstrap.TRADING_SYSTEM_ROOT).parent
    return (root / "frontend" / "components" / "native-chart.tsx").read_text(
        encoding="utf-8", errors="ignore")


def test_the_chart_no_longer_computes_its_own_signals():
    src = _chart_src()
    assert "computeAutoSignalMarkers" not in src
    assert "isBullishCross" not in src and "isBearishCross" not in src
    assert "function calculateRSI" not in src, "the duplicate RSI went with it"


def test_the_chart_asks_the_engine_instead():
    src = _chart_src()
    assert "/api/strategy-markers" in src
    assert "fetchStrategyMarkers" in src


def test_the_markers_endpoint_runs_the_real_engine():
    api = pathlib.Path(_bootstrap.TRADING_SYSTEM_ROOT, "api_bridge.py").read_text(
        encoding="utf-8", errors="ignore")
    start = api.index('@app.get("/api/strategy-markers")')
    body = api[start:start + 4000]
    assert "compute_cross_signals" in body, "must use the engine, not a copy of it"
    assert "ema_cluster_touch" in body
    assert "Ema9RsiMomentumConfig.from_settings" in body, "same settings the books read"


def test_a_frontend_proxy_route_exists_for_it():
    root = pathlib.Path(_bootstrap.TRADING_SYSTEM_ROOT).parent
    route = root / "frontend" / "app" / "api" / "strategy-markers" / "route.ts"
    assert route.exists()
    assert "/api/strategy-markers" in route.read_text(encoding="utf-8", errors="ignore")


# ---------------------------------------------------------------------------
# End to end on a real frame
# ---------------------------------------------------------------------------

def test_the_stricter_rule_admits_fewer_signals_than_legacy():
    """Synthetic but real-shaped: the ordering legacy > wick >= body must hold."""
    rng = np.random.default_rng(7)
    n = 900
    close = 23000 + np.cumsum(rng.normal(0, 8, n))
    high = close + rng.uniform(2, 18, n)
    low = close - rng.uniform(2, 18, n)
    open_ = close + rng.normal(0, 5, n)
    idx = pd.date_range("2026-01-01 09:15", periods=n, freq="5min")
    df = pd.DataFrame({"open": open_, "high": high, "low": low, "close": close}, index=idx)

    counts = {}
    for mode in ("legacy", "body_or_wick", "body"):
        sig = compute_cross_signals(df, _cfg(ema_touch_mode=mode, enable_time_filter=False))
        counts[mode] = int(sig.bullish.sum() + sig.bearish.sum())

    assert counts["legacy"] >= counts["body_or_wick"] >= counts["body"]
    assert counts["body_or_wick"] < counts["legacy"], "the owner's rule must actually filter"
