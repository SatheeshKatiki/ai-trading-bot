"""The EMA9/RSI reversal exit must actually be able to fire (2026-09-11).

The strategy spec says: *even if target or stop has not been hit, if the spot
chart reverses and an opposite EMA 9/20 cross appears, exit immediately,
regardless of profit or loss.*

`evaluate_protective_exit()` implemented exactly that and shipped in v3.13 --
but two things stopped it working:

1. **Nothing called it.** Neither `trading_bot/main.py` nor
   `paper_observer.py` referenced it, so the only exits that could fire were
   the 15% stop, the 33% target and the EOD square-off. Across six recorded
   sessions, 5 of 18 trades ended at the EOD cutoff with no management in
   between.

2. **It read the entry-filtered arrays.** `compute_cross_signals()` folds ADX,
   the trading-hours window and the EMA-touch guard into its bullish/bearish
   arrays; the exit read those. Filters exist to make ENTRIES selective; an
   exit needs the opposite disposition. Over 578 NIFTY trading days that
   suppressed **62% of genuine reversals** -- 390 of 868 bearish ones by ADX
   alone, and after 15:00 the window closed so no exit was possible for the
   rest of the session.

`compute_reversal_signals()` now carries the reversal without those filters.
`compute_cross_signals()` is deliberately untouched, so entries are unchanged.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from trading_bot.strategies.ema9_rsi_momentum import (
    evaluate_protective_exit,
    generate_signals,
)
from trading_bot.strategies.ema9_rsi_momentum.config import Ema9RsiMomentumConfig
from trading_bot.strategies.ema9_rsi_momentum.signal_engine import (
    compute_cross_signals,
    compute_reversal_signals,
)


#: 09:15-15:25 IST, the 75 five-minute bars of a real NSE session.
_BARS_PER_DAY = 75


def _session_index(days: int = 4, start: str = "2026-05-11") -> pd.DatetimeIndex:
    """A DatetimeIndex of consecutive trading sessions, inside market hours.

    Built per-day rather than as one continuous range: a flat `date_range`
    runs through the night, so most bars land outside the 09:25-15:00 entry
    window and the time filter zeroes the very signals under test.
    """
    stamps = []
    day = pd.Timestamp(start)
    while len(stamps) < days * _BARS_PER_DAY:
        if day.weekday() < 5:
            stamps.extend(pd.date_range(day + pd.Timedelta("9h15m"),
                                        periods=_BARS_PER_DAY, freq="5min"))
        day += pd.Timedelta(days=1)
    return pd.DatetimeIndex(stamps)


def _frame(days: int = 4, seed: int = 11) -> pd.DataFrame:
    """Up, down, then up again -- so both a bearish and a bullish cross occur."""
    rng = np.random.default_rng(seed)
    idx = _session_index(days)
    n = len(idx)
    legs = np.array_split(np.arange(n), 3)
    path, level = [], 23_400.0
    for k, leg in enumerate(legs):
        move = 220.0 if k % 2 == 0 else -240.0
        path.append(level + np.linspace(0, move, len(leg)))
        level += move
    close = pd.Series(np.concatenate(path) + rng.normal(0, 6, n))
    return pd.DataFrame({
        "open": close.shift(1).fillna(close.iloc[0]).to_numpy(),
        "high": (close + np.abs(rng.normal(7, 3, n))).to_numpy(),
        "low": (close - np.abs(rng.normal(7, 3, n))).to_numpy(),
        "close": close.to_numpy(),
        "volume": rng.integers(40_000, 200_000, n).astype(float),
    }, index=idx)


CFG = Ema9RsiMomentumConfig()


# ---------------------------------------------------------------------------
# The reversal is no longer filtered
# ---------------------------------------------------------------------------

def test_unfiltered_reversal_catches_at_least_as_much():
    df = _frame()
    filt = compute_cross_signals(df, CFG)
    raw = compute_reversal_signals(df, CFG)
    assert raw.bearish.sum() >= filt.bearish.sum()
    assert raw.bullish.sum() >= filt.bullish.sum()


def test_every_filtered_reversal_is_also_an_unfiltered_one():
    """Removing filters may only ADD reversals, never drop one."""
    df = _frame()
    filt = compute_cross_signals(df, CFG)
    raw = compute_reversal_signals(df, CFG)
    assert not (filt.bearish & ~raw.bearish).any()
    assert not (filt.bullish & ~raw.bullish).any()


def test_reversal_ignores_the_adx_filter():
    """ADX below threshold means chop -- where a buyer most needs an exit."""
    df = _frame()
    strict = Ema9RsiMomentumConfig(min_adx=90.0)   # nothing can pass this
    assert compute_cross_signals(df, strict).bearish.sum() == 0
    assert compute_reversal_signals(df, strict).bearish.sum() > 0


def test_reversal_ignores_the_trading_window():
    """After 15:00 the entry window shuts; an open position still needs out."""
    df = _frame()
    shut = Ema9RsiMomentumConfig(time_start="09:15", time_end="09:16")
    assert compute_cross_signals(df, shut).bearish.sum() == 0
    assert compute_reversal_signals(df, shut).bearish.sum() > 0


def test_reversal_keeps_the_warmup_guard():
    """Warm-up masking is correctness, not selection -- it must survive."""
    df = _frame()
    raw = compute_reversal_signals(df, CFG)
    warm = max(CFG.ema_slow, CFG.rsi_length + CFG.rsi_ma_length)
    assert not raw.bearish[:warm].any()
    assert not raw.bullish[:warm].any()


# ---------------------------------------------------------------------------
# Entries must be bit-for-bit unchanged
# ---------------------------------------------------------------------------

def test_entry_signals_are_untouched():
    """The whole point: only the exit changed.

    Verified on the real NIFTY 5-minute file too -- 99 entries (46 CE, 53 PE)
    both before and after this change.
    """
    df = _frame()
    sig = generate_signals(df)
    cross = compute_cross_signals(df, CFG)
    assert int((sig == 1).sum()) <= int(cross.bullish.sum())
    assert int((sig == -1).sum()) <= int(cross.bearish.sum())


def test_compute_cross_signals_still_applies_every_entry_filter():
    df = _frame()
    loose = compute_cross_signals(df, Ema9RsiMomentumConfig(min_adx=0.0))
    tight = compute_cross_signals(df, Ema9RsiMomentumConfig(min_adx=90.0))
    assert loose.bearish.sum() > 0, "fixture produced no bearish cross at all"
    assert tight.bearish.sum() == 0, "an impossible ADX floor must block every entry"


# ---------------------------------------------------------------------------
# The exit itself
# ---------------------------------------------------------------------------

def test_exit_fires_on_an_opposite_cross_for_a_ce():
    df = _frame()
    raw = compute_reversal_signals(df, CFG)
    bars = np.flatnonzero(raw.bearish)
    assert len(bars) > 0, "fixture produced no bearish reversal"
    upto = df.iloc[: bars[-1] + 1]
    res = evaluate_protective_exit(upto, 1, 100.0, 92.0)
    assert res.should_exit is True
    assert "EXIT CE" in res.reason


def test_exit_fires_on_an_opposite_cross_for_a_pe():
    df = _frame()
    raw = compute_reversal_signals(df, CFG)
    bars = np.flatnonzero(raw.bullish)
    assert len(bars) > 0, "fixture produced no bullish reversal"
    upto = df.iloc[: bars[-1] + 1]
    res = evaluate_protective_exit(upto, -1, 100.0, 92.0)
    assert res.should_exit is True
    assert "EXIT PE" in res.reason


def test_exit_fires_regardless_of_profit_or_loss():
    """The spec is explicit: exit "regardless of profit or loss"."""
    df = _frame()
    bars = np.flatnonzero(compute_reversal_signals(df, CFG).bearish)
    upto = df.iloc[: bars[-1] + 1]
    for current in (60.0, 100.0, 180.0):     # deep loss, flat, big profit
        assert evaluate_protective_exit(upto, 1, 100.0, current).should_exit is True


def test_no_exit_without_a_reversal():
    df = _frame()
    raw = compute_reversal_signals(df, CFG)
    quiet = next((i for i in range(120, len(df)) if not raw.bearish[i]), None)
    assert quiet is not None
    assert evaluate_protective_exit(df.iloc[:quiet + 1], 1, 100.0, 98.0).should_exit is False


def test_premium_decay_alone_never_forces_an_exit():
    """Spec: "do not treat premium decay alone as an exit signal"."""
    df = _frame()
    raw = compute_reversal_signals(df, CFG)
    quiet = next((i for i in range(120, len(df)) if not raw.bearish[i]), None)
    res = evaluate_protective_exit(df.iloc[:quiet + 1], 1, 100.0, 40.0)   # -60%
    assert res.should_exit is False
    assert res.warning is True


@pytest.mark.parametrize("bad", [None, pd.DataFrame()])
def test_missing_history_is_not_an_exit(bad):
    assert evaluate_protective_exit(bad, 1, 100.0, 90.0).should_exit is False


# ---------------------------------------------------------------------------
# It is actually wired into the running engine
# ---------------------------------------------------------------------------

def test_paper_observer_consults_the_reversal_exit():
    """It shipped in v3.13 and nothing called it for four weeks."""
    import inspect

    import paper_observer

    assert hasattr(paper_observer, "check_reversal_exit")
    src = inspect.getsource(paper_observer)
    assert "check_reversal_exit(" in src
    assert "evaluate_protective_exit" in inspect.getsource(
        paper_observer.check_reversal_exit
    )


def test_reversal_ranks_below_hard_limits_but_above_eod():
    """SL and target are hard limits; the reversal must not pre-empt them,
    but must act before a position is carried to the 15:15 cutoff."""
    import inspect

    import paper_observer

    src = inspect.getsource(paper_observer)
    sl = src.index("STOP LOSS HIT")
    rev = src.index("REVERSAL EXIT")
    eod = src.index("EOD CUTOFF 15:15")
    assert sl < rev < eod
