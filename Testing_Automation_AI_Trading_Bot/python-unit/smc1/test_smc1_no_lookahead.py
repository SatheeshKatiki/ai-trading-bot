"""smc1: no look-ahead, as a property.

For every detector, the state after bar ``k`` must be the same whether the
detector was fed the whole history (and snapshotted when it reached ``k``) or
only bars ``0..k``. Any read of a bar after ``k`` -- a centred window, a
frame-level recomputation, a "final" value written back -- breaks the
equality. Checked on seeded random walks and on real NIFTY 5m bars.
"""

from __future__ import annotations

from datetime import time
from typing import Any, Sequence

import pytest

import _bootstrap  # noqa: F401
from smc1_helpers import load_fixture_5m, random_walk

from trading_bot.strategies.smc_rsi_frvp_options_v1.config import Smc1Config
from trading_bot.strategies.smc_rsi_frvp_options_v1.detectors.liquidity import (
    EqualLevelTracker,
    SessionLevelTracker,
    SweepDetector,
)
from trading_bot.strategies.smc_rsi_frvp_options_v1.detectors.momentum import (
    AdxTracker,
    DivergenceTracker,
    RsiTracker,
    is_chop,
)
from trading_bot.strategies.smc_rsi_frvp_options_v1.detectors.timeframe import TimeframeDetectors
from trading_bot.strategies.smc_rsi_frvp_options_v1.types import Bar

CFG = Smc1Config()


class Pipeline:
    """Every detector a timeframe carries, fed one bar at a time."""

    def __init__(self, timeframe: str, momentum: bool = False) -> None:
        self.momentum = momentum
        self.tf = TimeframeDetectors(timeframe, CFG)
        lq = CFG.liquidity
        self.eq = EqualLevelTracker(timeframe, lq.eq_tol_pct, lq.eq_tol_atr_mult, lq.eq_max_pivots_back)
        self.sessions = SessionLevelTracker(time(9, 15), time(9, 45))
        self.sweeps = SweepDetector(lq.sweep_min_atr_mult, lq.sweep_reclaim_bars)
        self.rsi = RsiTracker(CFG.rsi.length)
        self.div = DivergenceTracker(CFG.rsi.div_max_bars)
        self.adx = AdxTracker(CFG.regime.adx_length)
        self.chop: list[Any] = []

    def update(self, b: Bar) -> None:
        for lv in self.sessions.update(b):
            self.sweeps.add_level(lv)
        u = self.tf.update(b)
        for p in u.pivots:
            lv = self.eq.update(p, u.atr)
            if lv is not None:
                self.sweeps.add_level(lv)
        self.sweeps.update(u.index, b, u.atr)
        if self.momentum:
            self.rsi.update(b)
            a = self.adx.update(b)
            self.div.update(u.pivots, self.rsi.values)
            self.chop.append(is_chop(a, self.tf.structure.events, u.index,
                                     CFG.regime.adx_min, CFG.regime.chop_lookback_bars_15m))

    def snapshot(self) -> Any:
        t = self.tf
        r = t.dealing_range.current if t.dealing_range else None
        return (
            t.atr.value,
            t.structure.trend,
            tuple(t.structure.events),
            tuple(t.structure.pivot_history),
            tuple((g.direction, g.zone, g.index, g.fill_pct, g.invalidated_index)
                  for g in t.fvg.history),
            tuple(t.fvg.displacements),
            tuple((o.direction, o.zone, o.index, o.touches, o.first_touch_index,
                   o.invalidated_index, o.expired_index)
                  for o in (t.order_blocks.history if t.order_blocks else [])),
            None if r is None else (r.direction, r.event_index, r.low, r.high, r.frozen),
            tuple((lv.type, lv.price, lv.known_at, lv.retired_at) for lv in self.sweeps.levels),
            tuple((s.direction, s.level.type, s.level.price, s.sweep_index, s.reclaim_index,
                   s.extreme) for s in self.sweeps.sweeps),
            tuple(self.div.history),
            tuple(self.rsi.values),
            tuple(self.adx.values),
            tuple(self.chop),
        )


def _check(timeframe: str, data: Sequence[Bar], cuts: Sequence[int],
           momentum: bool = False) -> int:
    full = Pipeline(timeframe, momentum)
    taken: dict[int, Any] = {}
    for k, b in enumerate(data):
        full.update(b)
        if k in cuts:
            taken[k] = full.snapshot()
    for k in cuts:
        prefix = Pipeline(timeframe, momentum)
        for b in data[:k + 1]:
            prefix.update(b)
        assert prefix.snapshot() == taken[k], f"{timeframe}: state after bar {k} used later bars"
    return len(full.tf.structure.events)


@pytest.mark.parametrize("seed", [1, 2, 3])
@pytest.mark.parametrize("timeframe, minutes", [("m5", 5), ("m15", 15), ("h1", 60)])
def test_no_detector_reads_a_future_bar_random_walk(seed, timeframe, minutes):
    data = random_walk(320, seed=seed, minutes=minutes)
    events = _check(timeframe, data, cuts=[60, 137, 211, 319])
    assert events > 5           # the walk actually exercised structure


def test_no_detector_reads_a_future_bar_real_nifty():
    data = load_fixture_5m()[:700]
    events = _check("m5", data, cuts=[120, 333, 512, 699])
    assert events > 20


@pytest.mark.parametrize("timeframe, minutes, seed", [("m5", 5, 4), ("m15", 15, 2)])
def test_momentum_trackers_have_no_lookahead(timeframe, minutes, seed):
    """RSI, divergence, ADX and chop re-run the shared pandas indicators every
    bar (~12 ms and ~27 ms a call), so they get their own, shorter case. Their
    parity tests against the full-series shared output are a second check."""
    data = random_walk(150, seed=seed, minutes=minutes)
    _check(timeframe, data, cuts=[75, 149], momentum=True)


def test_a_pivot_cannot_be_seen_before_its_right_bars_close():
    """The direct statement of spec §3.1: each pivot's confirmation is exactly
    ``right`` bars after it, never sooner."""
    p = Pipeline("m5")
    for b in random_walk(300, seed=9):
        p.update(b)
    pivots = p.tf.structure.pivot_history
    assert pivots and all(x.confirmed_index - x.index == CFG.pivots.m5.right for x in pivots)
    for e in p.tf.structure.events:
        assert e.swing_index + CFG.pivots.m5.right <= e.index
