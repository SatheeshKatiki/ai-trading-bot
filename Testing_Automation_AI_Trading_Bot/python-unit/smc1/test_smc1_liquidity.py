"""smc1: liquidity levels (EQH/EQL, PDH/PDL/PDC, opening range, 15m swings)
and the sweep-and-reclaim rule."""

from __future__ import annotations

from datetime import datetime, time, timedelta

import pytest

import _bootstrap  # noqa: F401
from smc1_helpers import bar

from trading_bot.strategies.smc_rsi_frvp_options_v1.detectors.liquidity import (
    EqualLevelTracker,
    Level,
    LevelType,
    SessionLevelTracker,
    SweepDetector,
)
from trading_bot.strategies.smc_rsi_frvp_options_v1.types import Direction, Pivot

DAY1 = datetime(2026, 6, 1, 9, 15)
DAY2 = datetime(2026, 6, 2, 9, 15)
EARLY = datetime(2026, 6, 1, 9, 0)


def _pivot(index, price, is_high=True):
    ts = DAY1 + timedelta(minutes=5 * index)
    return Pivot(index, ts, price, is_high, index + 3, ts + timedelta(minutes=20))


# ---------------------------------------------------------------- equal levels

def test_equal_highs_within_tolerance_form_an_eqh_at_the_higher_high():
    t = EqualLevelTracker("5m", tol_pct=0.03, tol_atr_mult=0.1, max_pivots_back=10)
    assert t.tolerance(20000.0, 50.0) == pytest.approx(6.0)       # max(6.0, 5.0)
    assert t.tolerance(20000.0, 100.0) == pytest.approx(10.0)     # ATR term wins
    assert t.update(_pivot(10, 20010.0), 50.0) is None
    lv = t.update(_pivot(20, 20015.0), 50.0)
    assert lv is not None and lv.type is LevelType.EQH and lv.price == 20015.0
    assert lv.known_at == _pivot(20, 20015.0).confirmed_at and "10+20" in lv.source


def test_highs_too_far_apart_and_lows():
    t = EqualLevelTracker("15m", 0.03, 0.1, 10)
    t.update(_pivot(1, 20010.0), 50.0)
    assert t.update(_pivot(2, 20020.0), 50.0) is None              # 10 > 6
    t.update(_pivot(3, 19990.0, False), 50.0)
    lv = t.update(_pivot(4, 19986.0, False), 50.0)
    assert lv is not None and lv.type is LevelType.EQL and lv.price == 19986.0


def test_pairing_looks_back_only_max_pivots_back():
    t = EqualLevelTracker("5m", 0.03, 0.1, 1)
    t.update(_pivot(1, 20010.0), 50.0)
    t.update(_pivot(2, 20100.0), 50.0)
    assert t.update(_pivot(3, 20012.0), 50.0) is None              # pivot 1 is out of reach


# ---------------------------------------------------------------- session levels

def _session(day_start, n, base=100.0, minutes=5):
    out = []
    for i in range(n):
        p = base + i * 0.1
        out.append(bar(i, p, p + 1, p - 1, p + 0.5, minutes=minutes, start=day_start))
    return out


def test_previous_day_levels_appear_on_the_first_bar_of_the_next_session():
    t = SessionLevelTracker(time(9, 15), time(9, 45))
    day1 = _session(DAY1, 75)
    emitted = [lv for b in day1 for lv in t.update(b) if lv.type in (LevelType.PDH, LevelType.PDL, LevelType.PDC)]
    assert emitted == []                                            # no previous day yet
    first = _session(DAY2, 1, base=110.0)[0]
    got = {lv.type: lv for lv in t.update(first)}
    assert got[LevelType.PDH].price == pytest.approx(max(b.high for b in day1))
    assert got[LevelType.PDL].price == pytest.approx(min(b.low for b in day1))
    assert got[LevelType.PDC].price == pytest.approx(day1[-1].close)
    assert got[LevelType.PDH].known_at == first.ts


def test_opening_range_is_known_when_its_last_bar_closes():
    t = SessionLevelTracker(time(9, 15), time(9, 45))
    day = _session(DAY1, 8)
    out = [t.update(b) for b in day]
    assert all(o == [] for o in out[:5])                            # 09:15 .. 09:35
    got = {lv.type: lv for lv in out[5]}                            # the 09:40 bar
    assert got[LevelType.ORH].price == pytest.approx(max(b.high for b in day[:6]))
    assert got[LevelType.ORL].price == pytest.approx(min(b.low for b in day[:6]))
    assert got[LevelType.ORH].known_at == datetime(2026, 6, 1, 9, 45)
    assert out[6] == [] and out[7] == []


def test_opening_range_from_15m_bars():
    t = SessionLevelTracker(time(9, 15), time(9, 45))
    out = [t.update(b) for b in _session(DAY1, 3, minutes=15)]
    assert out[0] == [] and {lv.type for lv in out[1]} == {LevelType.ORH, LevelType.ORL}


# ---------------------------------------------------------------- sweeps

def _det(level_type=LevelType.PDL, price=100.0, reclaim=2, known=EARLY):
    d = SweepDetector(min_atr_mult=0.05, reclaim_bars=reclaim)
    d.add_level(Level(level_type, price, known))
    return d


ATR = 2.0   # threshold 0.1


def test_wick_below_and_close_back_above_is_an_immediate_sweep():
    d = _det()
    u = d.update(0, bar(0, 100.5, 101.0, 99.8, 100.2), ATR)
    (s,) = u.sweeps
    assert s.direction is Direction.BULL and s.level.type is LevelType.PDL
    assert (s.sweep_index, s.reclaim_index, s.extreme) == (0, 0, 99.8)
    assert s.depth_atr == pytest.approx(0.1)
    assert s.level.retired_at is not None and d.active_levels() == []


def test_a_probe_shallower_than_the_threshold_is_nothing():
    d = _det()
    u = d.update(0, bar(0, 100.5, 101.0, 99.95, 100.2), ATR)
    assert u.sweeps == [] and u.started == [] and len(d.active_levels()) == 1


def test_reclaim_within_the_window():
    d = _det()
    d.update(0, bar(0, 100.0, 100.2, 99.0, 99.5), ATR)
    d.update(1, bar(1, 99.5, 99.9, 98.5, 99.7), ATR)
    (s,) = d.update(2, bar(2, 99.7, 100.8, 99.6, 100.5), ATR).sweeps
    assert (s.sweep_index, s.reclaim_index, s.extreme) == (0, 2, 98.5)


def test_no_reclaim_in_time_is_a_break_not_a_sweep():
    d = _det()
    d.update(0, bar(0, 100.0, 100.2, 99.0, 99.5), ATR)
    d.update(1, bar(1, 99.5, 99.8, 99.0, 99.6), ATR)
    u = d.update(2, bar(2, 99.6, 99.9, 99.2, 99.7), ATR)
    assert u.sweeps == [] and [lv.type for lv in u.broken] == [LevelType.PDL]
    assert d.update(3, bar(3, 99.7, 101.0, 99.5, 100.6), ATR).sweeps == []   # retired


def test_zero_reclaim_bars_requires_the_sweep_candle_itself_to_close_back():
    d = _det(reclaim=0)
    u = d.update(0, bar(0, 100.0, 100.2, 99.0, 99.5), ATR)
    assert u.sweeps == [] and len(u.broken) == 1


def test_a_level_not_yet_known_cannot_be_swept():
    d = _det(known=datetime(2026, 6, 1, 9, 20))
    assert d.update(0, bar(0, 100.5, 101.0, 99.0, 100.2), ATR).sweeps == []     # 09:15 bar
    assert len(d.update(1, bar(1, 100.5, 101.0, 99.0, 100.2), ATR).sweeps) == 1  # 09:20 bar


def test_no_atr_no_new_sweeps():
    d = _det()
    assert d.update(0, bar(0, 100.5, 101.0, 99.0, 100.2), None).sweeps == []


def test_buy_side_sweep_mirror():
    d = _det(LevelType.PDH, 100.0)
    (s,) = d.update(0, bar(0, 99.5, 100.6, 99.0, 99.8), ATR).sweeps
    assert s.direction is Direction.BEAR and s.extreme == 100.6


def test_previous_day_close_is_liquidity_on_both_sides():
    up = _det(LevelType.PDC, 100.0)
    assert up.update(0, bar(0, 99.5, 100.6, 99.4, 99.8), ATR).sweeps[0].direction is Direction.BEAR
    down = _det(LevelType.PDC, 100.0)
    assert down.update(0, bar(0, 100.5, 100.6, 99.4, 100.2), ATR).sweeps[0].direction is Direction.BULL


def test_a_newer_15m_swing_level_retires_the_older_one():
    d = SweepDetector(0.05, 2)
    a = Level(LevelType.SWING_LOW_15M, 95.0, EARLY)
    b = Level(LevelType.SWING_LOW_15M, 97.0, EARLY + timedelta(minutes=15))
    d.add_level(a)
    d.add_level(b)
    assert a.retired_at == b.known_at and d.active_levels() == [b]
    assert b.sell_side and not b.buy_side
