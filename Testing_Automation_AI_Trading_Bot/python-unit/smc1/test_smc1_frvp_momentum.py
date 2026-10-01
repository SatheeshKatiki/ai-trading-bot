"""smc1: fixed range volume profile wrapper; RSI, divergence, ADX, chop."""

from __future__ import annotations

from datetime import datetime, timedelta

import pandas as pd
import pytest

import _bootstrap  # noqa: F401
from smc1_helpers import bar, bars, random_walk

from shared.indicators.adx import adx as shared_adx
from shared.indicators.rsi import rsi as shared_rsi
from trading_bot.strategies.smc_rsi_frvp_options_v1.detectors.frvp import (
    FrvpTracker,
    ZeroVolumeError,
    build_profile,
)
from trading_bot.strategies.smc_rsi_frvp_options_v1.detectors.momentum import (
    AdxTracker,
    DivergenceTracker,
    RsiTracker,
    is_chop,
)
from trading_bot.strategies.smc_rsi_frvp_options_v1.types import (
    Bar,
    Direction,
    Pivot,
    StructureEvent,
    StructureKind,
    Zone,
)

PARAMS = dict(bin_points=5.0, value_area_pct=0.70, hvn_mult=1.3, lvn_mult=0.5, smooth_bins=3)


def _one_bin_bars(volumes, base=100.0, width=5.0):
    """One 1m bar per bin, each spanning exactly that bin."""
    return [bar(k, base + width * k, base + width * (k + 1), base + width * k,
                base + width * k + 1, v=float(vol), minutes=1) for k, vol in enumerate(volumes)]


# ---------------------------------------------------------------- FRVP

def test_profile_poc_and_value_area_by_hand():
    b = [bar(0, 101, 110, 100, 109, v=100, minutes=1),     # half in each bin
         bar(1, 106, 110, 105, 109, v=300, minutes=1),     # upper bin
         bar(2, 101, 105, 100, 104, v=50, minutes=1)]      # lower bin
    p = build_profile(b, "test", **PARAMS)
    assert p.bins == (Zone(100, 105), Zone(105, 110)) and p.bin_width == 5.0
    assert p.volumes == pytest.approx((100.0, 350.0))
    assert p.poc == 107.5 and (p.val, p.vah) == (105.0, 110.0)    # 350 of 450 >= 70 %
    assert p.total_volume == pytest.approx(450.0) and p.bars == 3


def test_hvn_is_a_smoothed_peak_and_lvn_an_interior_trough():
    p = build_profile(_one_bin_bars([10, 10, 60, 100, 60, 10, 10, 10, 10, 10]), "t", **PARAMS)
    assert len(p.bins) == 10
    assert p.hvn == (Zone(115.0, 120.0),)                       # bin 3
    assert p.lvn == (Zone(130.0, 135.0),)                       # bin 6; edge bins never LVN
    assert p.in_lvn(132.0) and not p.in_lvn(117.0)
    assert set(p.levels()) == {"POC", "VAH", "VAL", "HVN0"}
    assert p.smoothed[3] == pytest.approx(220 / 3)


def test_bins_are_an_exact_grid_aligned_to_bin_points():
    b = [bar(0, 101.5, 123.0, 101.5, 120, v=21.5, minutes=1)]   # 101.5 .. 123
    p = build_profile(b, "t", **PARAMS)
    assert p.bins == (Zone(100, 105), Zone(105, 110), Zone(110, 115), Zone(115, 120), Zone(120, 125))
    assert p.bin_width == 5.0
    # uniform spread over 21.5 points: 3.5, 5, 5, 5, 3 points of range
    assert p.volumes == pytest.approx((3.5, 5.0, 5.0, 5.0, 3.0))


def test_zero_volume_is_refused_not_faked():
    b = [bar(0, 100, 110, 100, 105, v=0.0, minutes=1)]
    with pytest.raises(ZeroVolumeError):
        build_profile(b, "t", **PARAMS)
    with pytest.raises(ValueError):
        build_profile([], "t", **PARAMS)


def test_zero_volume_bars_are_counted_and_add_nothing():
    """A zero-volume bar spanning a wide range must not put volume anywhere:
    no candle-range substitute (the shared function's behaviour)."""
    b = [bar(0, 101, 104, 100, 103, v=100, minutes=1),        # [100, 105) bin only
         bar(1, 120, 150, 100, 130, v=0.0, minutes=1)]        # 50-point range, no volume
    p = build_profile(b, "t", **PARAMS)
    assert p.zero_volume_bars == 1
    assert p.volumes[0] == pytest.approx(100.0) and sum(p.volumes[1:]) == 0.0
    assert p.total_volume == pytest.approx(100.0) and p.poc == 102.5


def test_smc1_frvp_never_uses_the_shared_volume_profile():
    """Owner decision 2026-10-01: no import of, and no object from, the shared
    volume-profile module (it substitutes candle range for missing volume)."""
    import inspect
    from trading_bot.strategies.smc_rsi_frvp_options_v1.detectors import frvp as module
    source = inspect.getsource(module)
    assert "import" not in "\n".join(
        line for line in source.splitlines() if "volume_profile" in line)
    assert "from shared" not in source and "import shared" not in source
    assert not any(getattr(v, "__module__", "") == "shared.indicators.volume_profile"
                   for v in vars(module).values())


def test_single_price_range_and_ties():
    b = [bar(0, 100, 100, 100, 100, v=10, minutes=1)]
    p = build_profile(b, "t", **PARAMS)
    assert p.bins == (Zone(100, 105),) and p.poc == 102.5 and p.total_volume == 10
    # equal bins: POC is the lowest-priced; the value area grows upward on a tie
    p = build_profile(_one_bin_bars([10, 10, 10, 10]), "t", **PARAMS)
    assert p.poc == 102.5 and (p.val, p.vah) == (100.0, 115.0)        # 30 of 40 >= 70 %


def test_tracker_previous_day_impulse_leg_and_buffer():
    day1 = datetime(2026, 6, 1, 9, 15)
    day2 = datetime(2026, 6, 2, 9, 15)
    t = FrvpTracker(5.0, 0.7, 1.3, 0.5, 3, history_sessions=2)
    d1 = [bar(i, 100 + i, 102 + i, 99 + i, 101 + i, v=100, minutes=1, start=day1) for i in range(30)]
    assert all(t.update(b) is None for b in d1)
    first = bar(0, 200, 201, 199, 200, v=100, minutes=1, start=day2)
    prev = t.update(first)
    assert prev is not None and prev is t.previous_day and prev.bars == 30
    assert prev.start == d1[0].ts and prev.end == d1[-1].close_time
    # impulse leg: only minutes that had CLOSED by known_at
    leg = t.on_dealing_range(d1[10].ts, d1[19].close_time)
    assert leg is not None and leg.bars == 10 and leg.end == d1[19].close_time
    std = t.session_to_date(first.close_time)
    assert std is not None and std.bars == 1
    # buffer keeps the last `history_sessions` sessions
    day3 = datetime(2026, 6, 3, 9, 15)
    t.update(bar(0, 300, 301, 299, 300, v=1, minutes=1, start=day3))
    assert t.on_dealing_range(d1[0].ts, d1[-1].close_time) is None    # day 1 dropped
    assert t.last_error is not None and "no 1m bars" in t.last_error


def test_tracker_records_a_zero_volume_day_instead_of_faking_it():
    t = FrvpTracker(5.0, 0.7, 1.3, 0.5, 3, 5)
    for i in range(5):
        t.update(bar(i, 100, 101, 99, 100, v=0.0, minutes=1))
    assert t.update(bar(0, 100, 101, 99, 100, v=5, minutes=1, start=datetime(2026, 6, 2, 9, 15))) is None
    assert t.previous_day is None and "zero volume" in (t.last_error or "")
    assert FrvpTracker(5.0, 0.7, 1.3, 0.5, 3, 5).session_to_date(datetime(2026, 6, 1)) is None


# ---------------------------------------------------------------- RSI

def test_rsi_is_the_shared_rsi_with_warm_up_withheld():
    walk = random_walk(120, seed=11)
    t = RsiTracker(14)
    mine = [t.update(b) for b in walk]
    ref = shared_rsi(pd.Series([b.close for b in walk]), window=14)
    assert mine[:14] == [None] * 14
    for k in range(14, 120):
        assert mine[k] == pytest.approx(float(ref.iloc[k]), abs=1e-9)


# ---------------------------------------------------------------- divergence

def _p(index, price, is_high):
    ts = datetime(2026, 6, 1, 9, 15) + timedelta(minutes=5 * index)
    return Pivot(index, ts, price, is_high, index + 3, ts + timedelta(minutes=20))


def test_bullish_divergence_lower_low_higher_rsi():
    rsi = [None] * 40
    rsi[10], rsi[25] = 28.0, 35.0
    d = DivergenceTracker(30)
    assert d.update([_p(10, 100.0, False)], rsi) == []
    (dv,) = d.update([_p(25, 98.0, False)], rsi)
    assert dv.direction is Direction.BULL and (dv.rsi_first, dv.rsi_second) == (28.0, 35.0)
    assert dv.confirmed_index == 28


def test_bearish_divergence_and_the_non_cases():
    rsi = [None] * 80
    rsi[10], rsi[25], rsi[40], rsi[75] = 72.0, 66.0, 60.0, 50.0
    d = DivergenceTracker(30)
    d.update([_p(10, 100.0, True)], rsi)
    assert d.update([_p(25, 101.0, True)], rsi)[0].direction is Direction.BEAR
    assert d.update([_p(40, 99.0, True)], rsi) == []          # lower high: no divergence
    assert d.update([_p(75, 105.0, True)], rsi) == []         # 35 bars apart > 30
    rsi2 = [None] * 30
    d2 = DivergenceTracker(30)
    d2.update([_p(5, 100.0, False)], rsi2)
    assert d2.update([_p(15, 99.0, False)], rsi2) == []       # RSI not available


# ---------------------------------------------------------------- ADX and chop

def test_adx_is_the_shared_adx_with_warm_up_withheld():
    walk = random_walk(90, seed=5, minutes=15)
    t = AdxTracker(14)
    mine = [t.update(b) for b in walk]
    frame = pd.DataFrame([(b.high, b.low, b.close) for b in walk], columns=["high", "low", "close"])
    ref = shared_adx(frame, window=14)
    assert mine[:28] == [None] * 28
    for k in range(28, 90):
        assert mine[k] == pytest.approx(float(ref.iloc[k]), abs=1e-9)


def _event(kind, index):
    ts = datetime(2026, 6, 1, 9, 15)
    return StructureEvent(kind, Direction.BULL, index, ts, ts, 1.0, 0, 0, 1.0, ts)


@pytest.mark.parametrize("adx, events, i, expected", [
    (None, [], 50, None),
    (15.0, [], 50, True),
    (25.0, [], 50, False),
    (15.0, [_event(StructureKind.BOS, 40)], 50, False),      # BOS 10 bars ago
    (15.0, [_event(StructureKind.BOS, 38)], 50, True),       # 12 bars ago: outside
    (15.0, [_event(StructureKind.CHOCH, 45)], 50, True),     # a CHoCH is not a BOS
    (15.0, [_event(StructureKind.BOS, 44), _event(StructureKind.CHOCH, 48)], 50, False),
])
def test_chop_filter(adx, events, i, expected):
    assert is_chop(adx, events, i, adx_min=18.0, lookback_bars=12) is expected


def test_bar_close_time_and_shape():
    b: Bar = bars([(100, 101, 99, 100.5)])[0]
    assert b.close_time - b.ts == timedelta(minutes=5)
    assert b.body == 0.5 and b.range == 2 and b.is_bullish and not b.is_bearish
