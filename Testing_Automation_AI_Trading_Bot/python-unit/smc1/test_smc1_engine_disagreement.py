"""D1: where smc1's step-by-step detectors disagree with ``calculate_smc``.

Owner decision D1 (2026-10-01): new detectors per the spec, plus a test that
documents exactly where they and the existing engine
(``shared.indicators.smart_money_concepts.calculate_smc``) disagree. On real
NIFTY 5m bars (June 2026, fixture ``smc1_nifty_5m_2026-06.csv``):

1. **BOS/CHoCH timing: no disagreement.** At the same pivot length, with
   enough history, both find the same structure events on the same bars in the
   same direction (L=3: 115 events; L=5: 84).
2. **First-event label.** The first break out of a NEUTRAL trend is a CHoCH to
   the engine and a BOS to the spec ("neutral establishes bullish").
3. **History-length dependence.** The engine clamps its pivot length to
   ``min(L, max(3, n // 6))``, so the same bars give different events depending
   on how much history the frame holds. The step-by-step tracker does not.
4. **FVG size threshold.** Same gap rule, different ATR: the engine uses a
   14-bar rolling mean of TR (from the first bar, ``min_periods=1``), smc1 uses
   Wilder's ATR (owner decision D6) and finds nothing before it has 14 bars.
   Every disagreement is a gap whose size falls between the two thresholds.
5. **Order blocks** (not diffed here -- the engine only exposes blocks still
   active at the end of the frame): the engine takes the bearish candle
   nearest the break with body >= 0.3 x its ATR, zone ``[low, body top]``; the
   spec takes the last bearish candle at or before the leg origin, zone
   ``full`` or ``body``. See ``detectors/order_blocks.py``.
"""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd
import pytest

import _bootstrap  # noqa: F401
from smc1_helpers import load_fixture_5m

from shared.indicators.smart_money_concepts import LuxAlgoSMCConfig, calculate_smc
from trading_bot.strategies.smc_rsi_frvp_options_v1.config import Smc1Config
from trading_bot.strategies.smc_rsi_frvp_options_v1.detectors.atr import WilderATR
from trading_bot.strategies.smc_rsi_frvp_options_v1.detectors.fvg import FvgTracker
from trading_bot.strategies.smc_rsi_frvp_options_v1.detectors.structure import StructureTracker
from trading_bot.strategies.smc_rsi_frvp_options_v1.types import Direction, StructureKind

logging.getLogger("shared.indicators.smart_money_concepts").setLevel(logging.CRITICAL)

BARS = load_fixture_5m()


def _frame(bars):
    return pd.DataFrame([dict(datetime=b.ts, open=b.open, high=b.high, low=b.low,
                              close=b.close, volume=b.volume) for b in bars]).set_index("datetime")


def _engine_events(bars, length):
    _, res = calculate_smc(_frame(bars), LuxAlgoSMCConfig(swing_points_length=length))
    return {(e.bar_index, 1 if e.is_bullish else -1): e.event_type.value.upper()
            for e in res.structure_events if not e.is_internal}


def _mine(bars, length):
    t = StructureTracker(length)
    for b in bars:
        t.update(b)
    return t


@pytest.mark.parametrize("length, expected_events", [(3, 115), (5, 84)])
def test_structure_events_match_except_the_first_label(length, expected_events):
    eng = _engine_events(BARS, length)
    t = _mine(BARS, length)
    mine = {(e.index, int(e.direction)): e.kind.value for e in t.events}
    assert len(mine) == len(eng) == expected_events
    assert set(mine) == set(eng)                                   # finding 1
    differ = sorted(k for k in mine if mine[k] != eng[k])
    first = (t.events[0].index, int(t.events[0].direction))
    assert differ == [first]                                       # finding 2
    assert mine[first] == "BOS" and eng[first] == "CHOCH"


def test_engine_output_depends_on_history_length_and_smc1_does_not():
    # Bars 25..64 of the fixture: with 40 bars the engine silently uses pivot
    # length 6 (40 // 6) instead of 10 and reports two bearish breaks; with
    # 400 bars of the same history it reports none on those bars.
    length = 10
    short, long = BARS[25:65], BARS[25:425]
    eng_short = {k for k in _engine_events(short, length) if k[0] < 40}
    eng_long = {k for k in _engine_events(long, length) if k[0] < 40}
    assert eng_short == {(21, -1), (30, -1)} and eng_long == set()   # finding 3
    mine_short = {(e.index, int(e.direction)) for e in _mine(short, length).events}
    mine_long = {(e.index, int(e.direction)) for e in _mine(long, length).events if e.index < 40}
    assert mine_short == mine_long


def test_fvg_disagreements_are_only_the_atr_threshold():
    cfg = Smc1Config()
    atr = WilderATR(cfg.regime.atr_length)
    fv = FvgTracker(cfg.fvg.min_atr_mult, cfg.displacement.atr_mult, cfg.displacement.body_ratio)
    wilder: list[float | None] = []
    for b in BARS:
        a = atr.update(b)
        wilder.append(a)
        fv.update(b, a)
    rdf, _ = calculate_smc(_frame(BARS), LuxAlgoSMCConfig(swing_points_length=3))
    eng = {(int(i), 1) for i in np.flatnonzero(rdf["smc_bullish_fvg"].to_numpy().astype(bool))}
    eng |= {(int(i), -1) for i in np.flatnonzero(rdf["smc_bearish_fvg"].to_numpy().astype(bool))}
    mine = {(g.index, int(g.direction)) for g in fv.history}

    # The engine's own ATR, reproduced here only to classify disagreements.
    tr = [BARS[0].high - BARS[0].low] + [
        max(b.high - b.low, abs(b.high - p.close), abs(b.low - p.close))
        for p, b in zip(BARS, BARS[1:])]
    eng_atr = pd.Series(tr).rolling(14, min_periods=1).mean().to_numpy()

    differ = mine ^ eng
    assert 0 < len(differ) < 0.1 * len(mine | eng)
    for i, d in differ:
        gap = (BARS[i].low - BARS[i - 2].high) if d == 1 else (BARS[i - 2].low - BARS[i].high)
        assert gap > 0, f"bar {i}: not a raw gap at all"
        thr_eng = 0.25 * eng_atr[i]
        w = wilder[i]
        if w is None:
            assert (i, d) in eng                                    # smc1 still warming up
            continue
        thr_mine = 0.25 * w
        assert min(thr_eng, thr_mine) <= gap < max(thr_eng, thr_mine), f"bar {i}"   # finding 4


def test_order_block_rule_is_the_spec_not_the_engine():
    """Finding 5, on the engine's own terms: its OB zone top is the BODY top;
    smc1's default ``full`` zone top is the candle HIGH."""
    t = StructureTracker(3)
    from trading_bot.strategies.smc_rsi_frvp_options_v1.detectors.order_blocks import (
        OrderBlockTracker,
    )
    atr = WilderATR(14)
    fv = FvgTracker(0.25, 1.5, 0.6)
    ob = OrderBlockTracker("full", 75, False, (StructureKind.BOS, StructureKind.CHOCH))
    for b in BARS:
        s = t.update(b)
        fv.update(b, atr.update(b))
        ob.update(s.index, b, t.bars, s.event, fv.displacements)
    assert ob.history
    for o in ob.history:
        c = BARS[o.index]
        assert (o.zone.low, o.zone.high) == (c.low, c.high)
        assert c.is_bearish if o.direction is Direction.BULL else c.is_bullish
