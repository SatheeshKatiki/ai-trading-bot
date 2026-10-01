"""smc1: Wilder ATR, causal pivots, BOS/CHoCH, bias and the dealing range."""

from __future__ import annotations

from datetime import datetime

import pandas as pd
import pytest

import _bootstrap  # noqa: F401
from smc1_helpers import bar, bars

from shared.indicators.atr import atr as shared_atr
from trading_bot.strategies.smc_rsi_frvp_options_v1.detectors.atr import WilderATR
from trading_bot.strategies.smc_rsi_frvp_options_v1.detectors.bias import (
    DealingRangeTracker,
    bias,
)
from trading_bot.strategies.smc_rsi_frvp_options_v1.detectors.pivots import PivotTracker
from trading_bot.strategies.smc_rsi_frvp_options_v1.detectors.structure import StructureTracker
from trading_bot.strategies.smc_rsi_frvp_options_v1.types import (
    Bar,
    Direction,
    StructureEvent,
    StructureKind,
    Trend,
    Zone,
)

# ---------------------------------------------------------------- ATR (D6)

ATR_ROWS = [(100, 102, 100, 101), (101, 104, 100, 103), (103, 103, 99, 100), (100, 106, 100, 105)]


def test_wilder_atr_seed_and_recursion_by_hand():
    a = WilderATR(3)
    vals = [a.update(b) for b in bars(ATR_ROWS)]
    # TR = 2, 4, 4, 6. Seed = mean(2, 4, 4) on bar 2; then (10/3 * 2 + 6) / 3.
    assert vals[0] is None and vals[1] is None
    assert vals[2] == pytest.approx(10 / 3)
    assert vals[3] == pytest.approx(38 / 9)
    assert a.value == pytest.approx(38 / 9) and a.count == 4


def test_wilder_atr_is_not_the_shared_ema_atr():
    """D6: the shared atr() is ewm(span=n); smc1 must not silently use it."""
    rows = ATR_ROWS * 5
    a = WilderATR(3)
    mine = [a.update(b) for b in bars(rows)][-1]
    df = pd.DataFrame(rows, columns=["open", "high", "low", "close"])
    assert mine != pytest.approx(float(shared_atr(df, 3).iloc[-1]), rel=1e-3)


def test_atr_rejects_a_zero_length():
    with pytest.raises(ValueError):
        WilderATR(0)


# ---------------------------------------------------------------- pivots

def test_a_pivot_is_emitted_only_after_its_right_bars_close():
    highs = [10, 11, 15, 12, 11, 10]
    rows = [(h - 1, h, h - 2, h - 1) for h in highs]
    t = PivotTracker(2)
    out = [t.update(b) for b in bars(rows)]
    assert out[2] == [] and out[3] == []        # not knowable yet
    assert [(p.index, p.is_high, p.price, p.confirmed_index) for p in out[4]] == [(2, True, 15, 4)]
    assert out[4][0].confirmed_at == bars(rows)[4].close_time


def test_equal_highs_are_not_a_pivot():
    rows = [(9, 10, 8, 9), (9, 12, 8, 9), (9, 12, 8, 9), (9, 10, 8, 9), (9, 10, 8, 9)]
    t = PivotTracker(1)
    assert all(not any(p.is_high for p in t.update(b)) for b in bars(rows))


def test_pivot_low_and_bad_length():
    rows = [(10, 11, 9, 10), (9, 10, 5, 9), (10, 11, 9, 10)]
    t = PivotTracker(1)
    out = [t.update(b) for b in bars(rows)]
    assert [(p.index, p.is_high, p.price) for p in out[2]] == [(1, False, 5)]
    with pytest.raises(ValueError):
        PivotTracker(0)


# ---------------------------------------------------------------- structure

#   i   o      h      l      c
SCENARIO = [
    (100.0, 101.0, 99.0, 100.0),   # 0
    (100.0, 105.0, 99.0, 104.0),   # 1  swing high 105 (confirmed on 2)
    (104.0, 104.0, 101.0, 102.0),  # 2
    (102.0, 103.0, 98.0, 99.0),    # 3  swing low 98 (confirmed on 4)
    (99.0, 104.0, 99.0, 103.5),    # 4  no break: close < 105
    (103.5, 106.0, 103.0, 105.5),  # 5  close > 105 from NEUTRAL -> bullish BOS
    (105.5, 107.0, 105.0, 106.0),  # 6  above the broken swing again: no 2nd event
    (106.0, 106.5, 104.0, 104.5),  # 7  swing high 107 at 6 confirmed; swing low 104 at 7
    (104.5, 106.0, 104.2, 105.5),  # 8  swing low 104 (index 7) confirmed
    (105.5, 105.6, 102.0, 102.5),  # 9  close < 104 while BULLISH -> bearish CHoCH
]


def _run(rows, length=1):
    t = StructureTracker(length)
    ups = [t.update(b) for b in bars(rows)]
    return t, ups


def test_bos_from_neutral_then_choch():
    t, ups = _run(SCENARIO)
    got = [(u.index, u.event.kind, u.event.direction) for u in ups if u.event]
    assert got == [(5, StructureKind.BOS, Direction.BULL), (9, StructureKind.CHOCH, Direction.BEAR)]
    assert t.trend is Trend.BEARISH


def test_event_details_and_leg_origin():
    t, _ = _run(SCENARIO)
    bos, choch = t.events
    assert bos.level == 105.0 and bos.swing_index == 1
    assert (bos.origin_index, bos.origin_price) == (3, 98.0)      # lowest low in (1, 5]
    assert bos.confirmed_at == bars(SCENARIO)[5].close_time
    assert choch.level == 104.0 and choch.swing_index == 7
    assert (choch.origin_index, choch.origin_price) == (8, 106.0)  # highest high in (7, 9]


def test_a_wick_through_a_swing_is_not_a_break():
    rows = SCENARIO[:5] + [(103.5, 108.0, 103.0, 104.9)]   # wick to 108, close below 105
    t, _ = _run(rows)
    assert t.events == []
    assert t.swing_high is not None and t.swing_high.price == 105.0


def test_bullish_bos_continues_in_an_uptrend():
    rows = SCENARIO[:9] + [(105.5, 108.0, 105.0, 107.5)]    # close above swing high 107
    t, _ = _run(rows)
    assert [(e.kind, e.direction) for e in t.events] == [
        (StructureKind.BOS, Direction.BULL), (StructureKind.BOS, Direction.BULL)]


def test_bearish_bos_from_neutral_mirror():
    mirrored = [(200 - o, 200 - lo, 200 - h, 200 - c) for o, h, lo, c in SCENARIO[:6]]
    t, _ = _run(mirrored)
    assert [(e.kind, e.direction) for e in t.events] == [(StructureKind.BOS, Direction.BEAR)]
    assert t.events[0].origin_price == 102.0


# ---------------------------------------------------------------- bias

def _ev(kind, direction, index):
    ts = datetime(2026, 6, 1, 10, 0)
    return StructureEvent(kind, direction, index, ts, ts, 100.0, 0, 0, 100.0, ts)


@pytest.mark.parametrize("events, i, require, h1, use_h1, expected", [
    ([], 10, True, None, True, Trend.NEUTRAL),
    ([_ev(StructureKind.BOS, Direction.BULL, 5)], 10, True, None, True, Trend.BULLISH),
    ([_ev(StructureKind.BOS, Direction.BEAR, 5)], 10, True, None, True, Trend.BEARISH),
    ([_ev(StructureKind.CHOCH, Direction.BULL, 5)], 10, True, None, True, Trend.NEUTRAL),
    ([_ev(StructureKind.CHOCH, Direction.BULL, 5)], 10, False, None, True, Trend.BULLISH),
    ([_ev(StructureKind.CHOCH, Direction.BULL, 3), _ev(StructureKind.BOS, Direction.BULL, 5)],
     10, True, None, True, Trend.BULLISH),
    ([_ev(StructureKind.BOS, Direction.BULL, 5)], 36, True, None, True, Trend.BULLISH),   # 31 bars
    ([_ev(StructureKind.BOS, Direction.BULL, 5)], 37, True, None, True, Trend.NEUTRAL),   # 32 bars
    ([_ev(StructureKind.BOS, Direction.BULL, 5)], 10, True, Trend.BEARISH, True, Trend.NEUTRAL),
    ([_ev(StructureKind.BOS, Direction.BEAR, 5)], 10, True, Trend.BULLISH, True, Trend.NEUTRAL),
    ([_ev(StructureKind.BOS, Direction.BULL, 5)], 10, True, Trend.BEARISH, False, Trend.BULLISH),
    ([_ev(StructureKind.BOS, Direction.BULL, 5)], 10, True, Trend.NEUTRAL, True, Trend.BULLISH),
])
def test_bias_rules(events, i, require, h1, use_h1, expected):
    assert bias(events, i, 32, require, h1, use_h1) is expected


# ---------------------------------------------------------------- dealing range

def test_dealing_range_extends_then_freezes_at_the_leg_top():
    t = StructureTracker(1)
    d = DealingRangeTracker()
    formed = []
    for b in bars(SCENARIO):
        u = t.update(b)
        r = d.update(u.index, b, t.bars, u.event, u.pivots)
        if r is not None:
            formed.append(r.event_index)
    assert formed == [5]                          # the CHoCH at 9 forms no range
    r = d.current
    assert r is not None and r.direction is Direction.BULL
    assert (r.low, r.high, r.frozen) == (98.0, 107.0, True)
    assert r.eq == pytest.approx(102.5)
    assert r.is_discount(102.0) and r.is_premium(103.0)
    assert r.known_at == bars(SCENARIO)[5].close_time


def test_dealing_range_ote_band():
    t = StructureTracker(1)
    d = DealingRangeTracker()
    for b in bars(SCENARIO[:8]):
        u = t.update(b)
        d.update(u.index, b, t.bars, u.event, u.pivots)
    r = d.current
    assert r is not None
    z = r.ote(0.62, 0.79)
    assert z == Zone(107 - 0.79 * 9, 107 - 0.62 * 9)


def test_bearish_dealing_range_and_its_ote():
    mirrored = [(200 - o, 200 - lo, 200 - h, 200 - c) for o, h, lo, c in SCENARIO[:8]]
    t = StructureTracker(1)
    d = DealingRangeTracker()
    for b in bars(mirrored):
        u = t.update(b)
        d.update(u.index, b, t.bars, u.event, u.pivots)
    r = d.current
    assert r is not None and r.direction is Direction.BEAR
    assert (r.low, r.high, r.frozen) == (93.0, 102.0, True)
    assert r.ote(0.62, 0.79) == Zone(93 + 0.62 * 9, 93 + 0.79 * 9)


def test_bar_validation():
    with pytest.raises(ValueError):
        bar(0, 100, 99, 101, 100)             # high < low
    with pytest.raises(ValueError):
        bar(0, 102, 101, 99, 100)             # open above high
    with pytest.raises(ValueError):
        bar(0, 100, 101, 99, 100, v=-1)
    with pytest.raises(ValueError):
        bar(0, float("nan"), 101, 99, 100)
    with pytest.raises(ValueError):
        Bar(datetime(2026, 6, 1, 9, 15), 100, 101, 99, 100, 0, 0)
    with pytest.raises(ValueError):
        Zone(2, 1)
