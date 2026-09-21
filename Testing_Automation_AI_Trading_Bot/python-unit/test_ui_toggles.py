"""The two switches the owner asked for in the UI, wired end to end.

Anticipate Crossover and Overnight Carry both exist because the owner asked
for them, and both are OFF by default because both were measured first:

  * anticipating the cross was the most damaging change tried on this
    strategy (NIFTY +Rs.11,150 -> -Rs.64,551 at one candle of lookahead);
  * an overnight carry changes the risk class rather than the return -- an
    intraday buyer's edge is that no gap can happen while the position is
    open, and no stop order protects against a gap.

The path is: the switch writes an `ema9_rsi_*` key -> POST /api/settings
merges it into config/settings.json -> Ema9RsiMomentumConfig.from_settings
reads it -> the engine behaves differently. These tests pin every link, so a
switch cannot end up looking wired while changing nothing.
"""

from __future__ import annotations

import datetime
import pathlib

import numpy as np
import pandas as pd

import _bootstrap  # noqa: F401  (side-effect: puts trading-system/ on sys.path)

from shared.eod_policy import CARRY, decide_eod
from trading_bot.strategies.ema9_rsi_momentum.config import Ema9RsiMomentumConfig
from trading_bot.strategies.ema9_rsi_momentum.signal_engine import compute_cross_signals

ANTICIPATE_KEY = "ema9_rsi_anticipate_cross_bars"
CARRY_KEY = "ema9_rsi_allow_overnight_carry"
CARRY_GAIN_KEY = "ema9_rsi_overnight_min_gain_pct"


def _frame(n=1200, seed=3) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    legs, filled = [], 0
    while filled < n:
        length = int(rng.integers(30, 80))
        legs.append(rng.normal(rng.normal(0, 6.0), 9.0, min(length, n - filled)))
        filled += length
    close = 24_000 + np.concatenate(legs)[:n].cumsum()
    shape = np.random.default_rng(seed + 1)
    open_ = close - shape.normal(0, 7, n)
    half = shape.uniform(6, 26, n)
    idx = pd.date_range("2026-08-03 09:15", periods=n, freq="5min")
    return pd.DataFrame({"open": open_, "high": np.maximum(close, open_) + half,
                         "low": np.minimum(close, open_) - half, "close": close,
                         "volume": shape.integers(1_000, 50_000, n).astype(float)}, index=idx)


def _count(settings) -> int:
    """Signals with the time and ADX filters out of the way.

    This isolates what the switch itself does. With both filters on, a short
    synthetic frame can produce no signals at all either way, which would
    make the switch look inert when it is not -- on real NIFTY 5-min data it
    takes 200 signals to 465 at one candle of lookahead and 723 at two.
    """
    cfg = Ema9RsiMomentumConfig.from_settings(
        settings, enable_time_filter=False, enable_adx_filter=False)
    sig = compute_cross_signals(_frame(), cfg)
    return int(sig.bullish.sum() + sig.bearish.sum())


# ---------------------------------------------------------------------------
# Switch 1: Anticipate Crossover
# ---------------------------------------------------------------------------

def test_anticipate_is_off_unless_the_switch_writes_it():
    assert Ema9RsiMomentumConfig.from_settings({}).anticipate_cross_bars == 0


def test_the_switch_value_reaches_the_config():
    assert Ema9RsiMomentumConfig.from_settings({ANTICIPATE_KEY: 1}).anticipate_cross_bars == 1
    assert Ema9RsiMomentumConfig.from_settings({ANTICIPATE_KEY: 2}).anticipate_cross_bars == 2


def test_turning_it_on_actually_marks_more_crossovers():
    """A switch that changes a number but not the behaviour is not wired.

    Measured at the point the switch acts -- how many bars are treated as a
    crossover -- rather than at the end of the chain, where the touch, RSI,
    ADX and time filters all get a say and a short synthetic frame can end up
    with the same handful of signals either way. On real NIFTY 5-min the full
    chain goes 200 -> 465 -> 723.
    """
    from trading_bot.strategies.ema9_rsi_momentum.indicators import (
        compute_indicator_set, crossed_above, crossed_below)
    from trading_bot.strategies.ema9_rsi_momentum.signal_engine import _with_anticipation

    df = _frame()
    counts = []
    for bars in (0, 1, 2):
        cfg = Ema9RsiMomentumConfig.from_settings({ANTICIPATE_KEY: bars})
        ind = compute_indicator_set(df, cfg.ema_fast, cfg.ema_slow,
                                    cfg.rsi_length, cfg.rsi_ma_length)
        up, dn = _with_anticipation(
            df, ind, cfg,
            np.asarray(crossed_above(ind.ema_fast, ind.ema_slow), dtype=bool),
            np.asarray(crossed_below(ind.ema_fast, ind.ema_slow), dtype=bool))
        counts.append(int(up.sum() + dn.sum()))

    off, on1, on2 = counts
    assert on1 > off, "one candle of lookahead must mark more bars as crossovers"
    assert on2 > on1, "two candles must mark more again"


def test_the_switch_still_changes_the_signals_the_engine_emits():
    """End to end, not just at the switch: more crossovers, more signals."""
    assert _count({ANTICIPATE_KEY: 2}) > _count({})


def test_turning_it_off_again_restores_the_exact_original_signals():
    assert _count({ANTICIPATE_KEY: 0}) == _count({})


# ---------------------------------------------------------------------------
# Switch 2: Overnight Carry
# ---------------------------------------------------------------------------

def _past_hard_time(settings, gain=100.0, expiry=False):
    cfg = Ema9RsiMomentumConfig.from_settings(settings)
    return decide_eod(datetime.time(15, 26), gain, 0.0, "VERY_STRONG", cfg,
                      is_expiry_day=expiry)


def test_carry_is_off_unless_the_switch_writes_it():
    assert not Ema9RsiMomentumConfig.from_settings({}).allow_overnight_carry
    assert _past_hard_time({}).must_close


def test_the_switch_lets_a_strong_winner_be_carried():
    assert _past_hard_time({CARRY_KEY: True}).action == CARRY


def test_the_minimum_gain_slider_is_honoured():
    on = {CARRY_KEY: True, CARRY_GAIN_KEY: 120}
    assert _past_hard_time(on, gain=100.0).must_close, "below the slider"
    assert _past_hard_time(on, gain=150.0).action == CARRY


def test_the_switch_cannot_override_expiry_day():
    """No setting makes a contract that expires today survive the night."""
    assert _past_hard_time({CARRY_KEY: True}, gain=300.0, expiry=True).must_close


# ---------------------------------------------------------------------------
# The UI actually carries the switches, and says what they cost
# ---------------------------------------------------------------------------

def _tsx(*parts) -> str:
    root = pathlib.Path(_bootstrap.TRADING_SYSTEM_ROOT).parent
    return (root / "frontend").joinpath(*parts).read_text(encoding="utf-8", errors="ignore")


def test_both_switches_exist_in_the_strategy_tab():
    src = _tsx("app", "strategy", "tabs", "strategy-tab.tsx")
    assert ANTICIPATE_KEY in src
    assert CARRY_KEY in src
    assert src.count("CustomSwitch") >= 4


def test_the_switches_write_the_keys_the_engine_reads():
    src = _tsx("app", "strategy", "tabs", "strategy-tab.tsx")
    assert f'updateSetting("{ANTICIPATE_KEY}"' in src
    assert f'updateSetting("{CARRY_KEY}"' in src


def test_the_measured_cost_is_shown_next_to_the_switch():
    """These two are known-harmful; the number belongs on the switch, not in
    a doc nobody opens."""
    src = _tsx("app", "strategy", "tabs", "strategy-tab.tsx")
    assert "64,551" in src, "the anticipation measurement"
    assert "MEASURED WORSE" in src
    assert "gap" in src.lower() and "expiry day" in src.lower()


def test_the_defaults_ship_both_switches_off():
    src = _tsx("app", "strategy", "page.tsx")
    assert f"{ANTICIPATE_KEY}: 0" in src
    assert f"{CARRY_KEY}: false" in src


def test_settings_persist_unknown_keys_so_the_switches_survive_a_save():
    api = pathlib.Path(_bootstrap.TRADING_SYSTEM_ROOT, "api_bridge.py").read_text(
        encoding="utf-8", errors="ignore")
    assert "existing.update(new_settings)" in api


def test_the_chart_markers_use_the_symbols_own_parameters():
    """SENSEX runs a different ADX floor -- the chart must draw what the books
    would take for THAT instrument, not NIFTY's answer."""
    api = pathlib.Path(_bootstrap.TRADING_SYSTEM_ROOT, "api_bridge.py").read_text(
        encoding="utf-8", errors="ignore")
    start = api.index('@app.get("/api/strategy-markers")')
    body = api[start:start + 5000]
    assert "symbol=symbol" in body
