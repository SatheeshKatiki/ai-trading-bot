"""The breakaway entry (the 2026-09-22 miss), which ships OFF.

The EMA-cluster touch rule refuses a crossover whose candle has already left
both averages, because that is usually a chase. The breakaway exception admits
one kind of non-touching candle: a decisive body (>= `breakaway_min_body_atr`
x ATR) that closes near its own extreme in the trade's direction.

What these tests hold:

* OFF by default, and while OFF nothing about the old grading changes.
* ON, it admits only the decisive, held candle -- never a weak body, never one
  that gave the move back, never the wrong direction.
* It never re-grades a candle that touched the cluster: body and wick touches
  keep HIGH / MEDIUM / LOW exactly as before.
* `body` and `legacy` touch modes ignore it.
* The settings key is ``ema9_rsi_allow_breakaway_entry``.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

import _bootstrap  # noqa: F401  (side-effect: puts trading-system/ on sys.path)

from shared.entry_gate import PRIORITY_LOW
from trading_bot.strategies.ema9_rsi_momentum.config import Ema9RsiMomentumConfig
from trading_bot.strategies.ema9_rsi_momentum.signal_engine import (
    PRIORITY_BREAKAWAY,
    PRIORITY_HIGH,
    _breakaway,
    assess_entry_quality,
)

# 20 quiet bars (range 2, body 1) so ATR settles near 2, then the bar under test.
_QUIET = [(100.0, 101.0, 99.0, 100.5)] * 20


def _frame(last) -> pd.DataFrame:
    rows = _QUIET + [last]
    idx = pd.date_range("2026-09-22 09:15", periods=len(rows), freq="5min")
    return pd.DataFrame(rows, columns=["open", "high", "low", "close"], index=idx)


class _Ind:
    """EMAs far below every candle, so nothing touches the cluster."""

    def __init__(self, n, fast=90.0, slow=89.0):
        self.ema_fast = np.full(n, fast)
        self.ema_slow = np.full(n, slow)
        self.rsi = np.full(n, 50.0)
        self.rsi_ma = np.full(n, 50.0)


def _dir(n, side):
    d = np.zeros(n, dtype=int)
    d[-1] = side
    return d


# A decisive bull candle: body 6 (3x ATR), closes 0.5 below a high 7 above open.
_BULL_BREAKAWAY = (100.0, 107.0, 99.5, 106.5)


def test_off_by_default():
    assert Ema9RsiMomentumConfig().allow_breakaway_entry is False
    df = _frame(_BULL_BREAKAWAY)
    assert not _breakaway(df, Ema9RsiMomentumConfig(), _dir(len(df), 1)).any()


def test_off_means_a_non_touching_cross_is_still_refused():
    df = _frame(_BULL_BREAKAWAY)
    q = assess_entry_quality(df, _Ind(len(df)), Ema9RsiMomentumConfig(), _dir(len(df), 1))
    assert not q.take[-1]
    assert q.priority[-1] != PRIORITY_BREAKAWAY


def test_on_admits_a_decisive_candle_that_held_its_extreme():
    df = _frame(_BULL_BREAKAWAY)
    cfg = Ema9RsiMomentumConfig(allow_breakaway_entry=True)
    q = assess_entry_quality(df, _Ind(len(df)), cfg, _dir(len(df), 1))
    assert q.take[-1]
    assert q.priority[-1] == PRIORITY_BREAKAWAY
    assert q.priority[-1] != PRIORITY_LOW          # the shared entry gate keeps it


def test_bear_mirror():
    df = _frame((100.0, 100.5, 93.0, 93.5))         # body 6.5, closes 0.5 off the low
    cfg = Ema9RsiMomentumConfig(allow_breakaway_entry=True)
    ind = _Ind(len(df), fast=120.0, slow=121.0)
    q = assess_entry_quality(df, ind, cfg, _dir(len(df), -1))
    assert q.take[-1] and q.priority[-1] == PRIORITY_BREAKAWAY


def test_a_weak_body_is_not_a_breakaway():
    df = _frame((100.0, 101.2, 99.8, 101.0))        # body 1 < 1.0 x ATR(~2)
    cfg = Ema9RsiMomentumConfig(allow_breakaway_entry=True)
    assert not _breakaway(df, cfg, _dir(len(df), 1))[-1]


def test_a_candle_that_gave_the_move_back_is_not_a_breakaway():
    df = _frame((100.0, 112.0, 99.5, 106.5))        # body 6.5, but 5.5 below its high
    cfg = Ema9RsiMomentumConfig(allow_breakaway_entry=True)
    assert not _breakaway(df, cfg, _dir(len(df), 1))[-1]


def test_the_wrong_direction_is_not_a_breakaway():
    df = _frame(_BULL_BREAKAWAY)
    cfg = Ema9RsiMomentumConfig(allow_breakaway_entry=True)
    assert not _breakaway(df, cfg, _dir(len(df), -1))[-1]
    assert not _breakaway(df, cfg, _dir(len(df), 0))[-1]


def test_it_never_regrades_a_candle_that_touched_the_cluster():
    df = _frame(_BULL_BREAKAWAY)
    ind = _Ind(len(df), fast=104.0, slow=102.0)     # both EMAs inside the body
    off = assess_entry_quality(df, ind, Ema9RsiMomentumConfig(), _dir(len(df), 1))
    on = assess_entry_quality(df, ind, Ema9RsiMomentumConfig(allow_breakaway_entry=True),
                              _dir(len(df), 1))
    assert off.priority[-1] == on.priority[-1] == PRIORITY_HIGH
    assert bool(off.take[-1]) == bool(on.take[-1])


def test_body_and_legacy_modes_ignore_it():
    df = _frame(_BULL_BREAKAWAY)
    for mode in ("body", "legacy"):
        cfg = Ema9RsiMomentumConfig(allow_breakaway_entry=True, ema_touch_mode=mode)
        q = assess_entry_quality(df, _Ind(len(df)), cfg, _dir(len(df), 1))
        assert not q.take[-1], mode


def test_settings_key():
    cfg = Ema9RsiMomentumConfig.from_settings({"ema9_rsi_allow_breakaway_entry": True,
                                               "ema9_rsi_breakaway_min_body_atr": 1.5})
    assert cfg.allow_breakaway_entry is True
    assert cfg.breakaway_min_body_atr == 1.5
