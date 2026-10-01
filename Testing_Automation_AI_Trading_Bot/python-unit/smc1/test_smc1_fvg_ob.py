"""smc1: fair value gaps, displacement candles, order blocks, timeframe wiring."""

from __future__ import annotations

from dataclasses import replace
from datetime import timedelta

import pytest

import _bootstrap  # noqa: F401
from smc1_helpers import bars, random_walk

from trading_bot.strategies.smc_rsi_frvp_options_v1.config import Smc1Config
from trading_bot.strategies.smc_rsi_frvp_options_v1.detectors.fvg import FvgTracker
from trading_bot.strategies.smc_rsi_frvp_options_v1.detectors.order_blocks import OrderBlockTracker
from trading_bot.strategies.smc_rsi_frvp_options_v1.detectors.structure import StructureTracker
from trading_bot.strategies.smc_rsi_frvp_options_v1.detectors.timeframe import TimeframeDetectors
from trading_bot.strategies.smc_rsi_frvp_options_v1.types import Direction, StructureKind, Zone

BOTH = (StructureKind.BOS, StructureKind.CHOCH)

# ---------------------------------------------------------------- FVG

GAP_UP = [
    (100.0, 101.0, 99.0, 100.5),    # 0
    (100.5, 106.0, 100.4, 105.8),   # 1  impulse: body 5.3, range 5.6
    (105.8, 107.0, 103.0, 106.5),   # 2  low 103 > high[0] 101 -> bullish FVG [101, 103]
    (106.5, 106.6, 102.0, 102.5),   # 3  trades to 102: half filled, close above 101
    (102.5, 103.0, 100.0, 100.5),   # 4  close 100.5 < 101 -> invalidated
]


def _fvg(rows, atrs, **kw):
    t = FvgTracker(kw.get("min", 0.25), kw.get("disp", 1.5), kw.get("ratio", 0.6))
    ups = [t.update(b, a) for b, a in zip(bars(rows), atrs)]
    return t, ups


def test_bullish_fvg_fill_and_invalidation():
    _, ups = _fvg(GAP_UP[:4], [3.0, 3.0, 4.0, 4.0])
    (g,) = ups[2].new
    assert g.direction is Direction.BULL and g.zone == Zone(101.0, 103.0) and g.index == 2
    assert g.size_atr == pytest.approx(0.5)
    assert g.fill_pct == pytest.approx(0.5) and g.active      # as of bar 3
    t, ups = _fvg(GAP_UP, [3.0, 3.0, 4.0, 4.0, 4.0])
    g = ups[2].new[0]
    assert ups[4].invalidated == [g] and g.invalidated_index == 4 and not g.active
    assert g.fill_pct == 1.0 and t.active == []


def test_middle_candle_is_the_displacement_and_confirms_on_the_third():
    t, ups = _fvg(GAP_UP, [3.0, 3.0, 4.0, 4.0, 4.0])
    (d,) = ups[2].displacements
    assert (d.index, d.confirmed_index, d.direction, d.fvg_index) == (1, 2, Direction.BULL, 2)
    assert d.body_atr == pytest.approx(5.3 / 3.0) and d.body_ratio == pytest.approx(5.3 / 5.6)


def test_a_gap_smaller_than_the_atr_floor_is_ignored():
    _, ups = _fvg(GAP_UP, [3.0, 3.0, 10.0, 10.0, 10.0])   # 2 < 0.25 x 10
    assert ups[2].new == []


def test_no_fvg_without_an_atr():
    _, ups = _fvg(GAP_UP, [None, None, None, None, None])
    assert all(u.new == [] for u in ups)


def test_weak_or_wrong_direction_candles_are_not_displacement():
    _, ups = _fvg(GAP_UP, [3.0, 4.0, 4.0, 4.0, 4.0], disp=1.5)    # 5.3 / 4 = 1.33 < 1.5
    assert ups[2].new and ups[2].displacements == []
    _, ups = _fvg(GAP_UP, [3.0, 3.0, 4.0, 4.0, 4.0], ratio=0.97)  # body ratio 0.946
    assert ups[2].displacements == []


def test_bearish_fvg_mirror():
    rows = [(200 - o, 200 - lo, 200 - h, 200 - c) for o, h, lo, c in GAP_UP]
    _, ups = _fvg(rows[:4], [3.0, 3.0, 4.0, 4.0])
    (g,) = ups[2].new
    assert g.direction is Direction.BEAR and g.zone == Zone(97.0, 99.0)
    assert ups[2].displacements[0].direction is Direction.BEAR
    assert g.fill_pct == pytest.approx(0.5)
    _, ups = _fvg(rows, [3.0, 3.0, 4.0, 4.0, 4.0])
    assert ups[2].new[0].invalidated_index == 4


# ---------------------------------------------------------------- order blocks

#   i   o      h      l      c
OB_LEG = [
    (100.0, 101.0, 99.0, 100.0),   # 0
    (100.0, 105.0, 99.0, 104.0),   # 1  swing high 105
    (104.0, 104.0, 101.0, 102.0),  # 2
    (102.0, 103.0, 98.0, 99.0),    # 3  last bearish candle at the leg origin -> OB
    (99.0, 104.0, 99.0, 103.5),    # 4  displacement (body 4.5 = 1.8 ATR)
    (104.5, 108.0, 104.0, 107.5),  # 5  FVG [103, 104]; close > 105 -> bullish BOS
    (107.5, 108.0, 104.0, 105.0),  # 6  low 104 > OB top 103: no touch
    (105.0, 105.5, 102.5, 103.0),  # 7  first touch
    (103.0, 103.2, 97.0, 97.5),    # 8  close < 98 -> invalidated
]


def _ob(rows, zone_mode="full", max_age=75, require=True, kinds=BOTH, atr=2.5):
    st = StructureTracker(1)
    fv = FvgTracker(0.25, 1.5, 0.6)
    ob = OrderBlockTracker(zone_mode, max_age, require, kinds)
    ups = []
    for b in bars(rows):
        s = st.update(b)
        fv.update(b, atr)
        ups.append(ob.update(s.index, b, st.bars, s.event, fv.displacements))
    return ob, ups


def test_bullish_ob_is_the_last_bearish_candle_at_the_leg_origin():
    ob, ups = _ob(OB_LEG[:6])
    (o,) = ups[5].new
    assert (o.direction, o.index, o.confirmed_index, o.event_kind) == (
        Direction.BULL, 3, 5, StructureKind.BOS)
    assert o.zone == Zone(98.0, 103.0) and o.fresh and o.active


def test_body_zone_mode():
    ob, ups = _ob(OB_LEG[:6], zone_mode="body")
    assert ups[5].new[0].zone == Zone(99.0, 102.0)


def test_touch_then_invalidation():
    ob, ups = _ob(OB_LEG[:8])                       # as of bar 7
    o = ob.history[0]
    assert ups[6].touched == []
    assert ups[7].touched == [o] and o.first_touch_index == 7 and o.touches == 1 and not o.fresh
    ob, ups = _ob(OB_LEG)                           # bar 8 touches again and closes through
    o = ob.history[0]
    assert ups[8].invalidated == [o] and o.invalidated_index == 8 and not o.active
    assert o.touches == 2 and o.first_touch_index == 7


def test_expiry():
    ob, ups = _ob(OB_LEG, max_age=3)            # OB at 3; 7 - 3 > 3
    o = ob.history[0]
    assert ups[7].expired == [o] and o.expired_index == 7 and o.touches == 0


def test_no_ob_without_displacement_when_required():
    ob, ups = _ob(OB_LEG[:6], atr=4.0)          # 4.5 / 4 = 1.125 < 1.5
    assert ups[5].new == []
    ob, ups = _ob(OB_LEG[:6], atr=4.0, require=False)
    assert len(ups[5].new) == 1


def test_15m_obs_come_from_bos_only_5m_from_choch_too():
    st = StructureTracker(1)
    fv = FvgTracker(0.25, 1.5, 0.6)
    event = None
    for b in bars(OB_LEG[:6]):
        s = st.update(b)
        fv.update(b, 2.5)
        event = s.event or event
    assert event is not None
    choch = replace(event, kind=StructureKind.CHOCH)     # same leg, labelled CHoCH
    m15 = OrderBlockTracker("full", 40, True, (StructureKind.BOS,))
    m5 = OrderBlockTracker("full", 75, True, BOTH)
    last = st.bars[-1]
    assert m15.update(5, last, st.bars, choch, fv.displacements).new == []
    assert len(m5.update(5, last, st.bars, choch, fv.displacements).new) == 1


def test_bearish_ob_mirror():
    rows = [(200 - o, 200 - lo, 200 - h, 200 - c) for o, h, lo, c in OB_LEG]
    ob, ups = _ob(rows)
    o = ob.history[0]
    assert o.direction is Direction.BEAR and o.index == 3 and o.zone == Zone(97.0, 102.0)
    assert o.first_touch_index == 7 and o.invalidated_index == 8


def test_bad_zone_mode():
    with pytest.raises(ValueError):
        OrderBlockTracker("wick", 10, True, BOTH)


# ---------------------------------------------------------------- timeframe wiring

def test_timeframe_detectors_wire_everything_and_validate_input():
    cfg = Smc1Config()
    m5 = TimeframeDetectors("m5", cfg)
    m15 = TimeframeDetectors("m15", cfg)
    h1 = TimeframeDetectors("h1", cfg)
    assert m5.order_blocks is not None and m5.dealing_range is None
    assert m15.order_blocks is not None and m15.dealing_range is not None
    assert h1.order_blocks is None and h1.dealing_range is None
    walk = random_walk(400, seed=7, minutes=15)
    ranges = [u.new_range for u in (m15.update(b) for b in walk) if u.new_range]
    assert ranges and m15.structure.events
    with pytest.raises(ValueError, match="15-minute"):
        m5.update(walk[0])
    first = random_walk(2, seed=1)
    m5.update(first[1])
    with pytest.raises(ValueError, match="not after"):
        m5.update(first[0])
    with pytest.raises(ValueError, match="unknown timeframe"):
        TimeframeDetectors("m3", cfg)


def test_timeframe_update_records_atr_and_bar():
    cfg = Smc1Config()
    m5 = TimeframeDetectors("m5", cfg)
    walk = random_walk(20, seed=3)
    ups = [m5.update(b) for b in walk]
    assert ups[12].atr is None and ups[13].atr is not None
    assert ups[-1].bar is walk[-1] and ups[-1].index == 19
    assert walk[1].ts - walk[0].ts == timedelta(minutes=5)
