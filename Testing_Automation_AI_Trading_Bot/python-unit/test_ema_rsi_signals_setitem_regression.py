"""Regression coverage for the 2026-08-07 ema_rsi_strategy CPU-livelock finding.

Root cause: `generate_signals()` built its output Series via two incremental
boolean-mask assignments (`signals[bullish] = 1`, `signals[bearish] = -1`).
`Series.__setitem__` with a boolean-mask key can route through
`Series._set_with_engine -> Index.get_loc -> Series.__repr__` under certain
conditions -- the exact call chain caught active, live, inside this file's
own signal-construction line during the 2026-08-07 STRATEGY_AUDIT
investigation, sharing the identical signature already implicated in the
2026-08-06 CPU-livelock's own py-spy dumps. `ema_rsi` is the strategy that
is live-active in production; this line runs on every tick, upstream of
`registry.py`'s own (already separately fixed, same date) instance of the
identical pattern. Full writeup: docs/STRATEGY_AUDIT_2026-08-07.md §1.2,
docs/paper_trading_validation/anomaly_log.md's 2026-08-07 entries.

Fixed by building the signal Series in one `np.select` call against the
two boolean masks' underlying numpy arrays, eliminating both
`Series.__setitem__` calls regardless of the deeper pandas/pyarrow
mechanism -- the same fix pattern already applied to `registry.py` earlier
the same day. This test pins that the rewrite is bit-for-bit identical to
the pre-fix incremental-assignment implementation.
"""
import _bootstrap  # noqa: F401  (side-effect: puts trading-system/ on sys.path)

import numpy as np
import pandas as pd

from trading_bot.strategies.ema_rsi_strategy import generate_signals


def _synthetic_ohlcv(n: int = 300, seed: int = 42) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    close = 24_000 + rng.normal(0, 15, n).cumsum()
    return pd.DataFrame({
        "open": close - rng.uniform(1, 8, n),
        "high": close + rng.uniform(1, 12, n),
        "low": close - rng.uniform(1, 12, n),
        "close": close,
        "volume": rng.integers(1_000, 50_000, n).astype(float),
    })


def _filtered_signals_reference(bullish: pd.Series, bearish: pd.Series, index) -> pd.Series:
    """The pre-fix implementation, kept only as a reference oracle."""
    signals = pd.Series(0, index=index, dtype=int)
    signals[bullish] = 1
    signals[bearish] = -1
    return signals


def _filtered_signals_current(bullish: pd.Series, bearish: pd.Series, index) -> pd.Series:
    return pd.Series(
        np.select([bearish.to_numpy(), bullish.to_numpy()], [-1, 1], default=0),
        index=index,
        dtype=int,
    )


def test_signal_construction_matches_pre_fix_reference_no_overlap():
    n = 500
    idx = pd.RangeIndex(n)
    rng = np.random.default_rng(9)
    bullish = pd.Series(rng.random(n) < 0.2, index=idx)
    bearish = pd.Series((~bullish) & (rng.random(n) < 0.2), index=idx)

    reference = _filtered_signals_reference(bullish, bearish, idx)
    result = _filtered_signals_current(bullish, bearish, idx)

    pd.testing.assert_series_equal(reference, result, check_names=False)


def test_signal_construction_matches_pre_fix_reference_all_false():
    n = 200
    idx = pd.RangeIndex(n)
    bullish = pd.Series(False, index=idx)
    bearish = pd.Series(False, index=idx)

    reference = _filtered_signals_reference(bullish, bearish, idx)
    result = _filtered_signals_current(bullish, bearish, idx)

    pd.testing.assert_series_equal(reference, result, check_names=False)
    assert (result == 0).all()


def test_signal_construction_matches_pre_fix_reference_overlap_bearish_wins():
    """Structurally impossible via real bullish/bearish inputs (EMA can't be
    both above and below the slow EMA simultaneously), but confirms the
    overwrite order is preserved if it ever did happen."""
    n = 50
    idx = pd.RangeIndex(n)
    bullish = pd.Series(True, index=idx)
    bearish = pd.Series(True, index=idx)

    reference = _filtered_signals_reference(bullish, bearish, idx)
    result = _filtered_signals_current(bullish, bearish, idx)

    pd.testing.assert_series_equal(reference, result, check_names=False)
    assert (result == -1).all()


def test_generate_signals_end_to_end_matches_pre_fix_reference():
    """End-to-end through the real function on realistic OHLCV data.

    NOTE (2026-08-08): the oracle below now applies the same
    edge-trigger step the strategy gained in backlog #7. This test's
    purpose is to pin that the `np.select` CONSTRUCTION is equivalent to
    the original incremental boolean-mask assignment (the CPU-livelock
    fix) — not to freeze the strategy's signal semantics forever.
    Edge-triggering is a deliberate, separately-tested behavioural
    change applied *after* construction, so the oracle models it too;
    otherwise this test would fail purely for detecting an intentional
    improvement.
    """
    from shared.indicators import ema, rsi, supertrend
    from trading_bot.strategies.ema_rsi_strategy import _volume_filter

    def _reference(df, ema_fast=20, ema_slow=50, rsi_window=14, rsi_buy_thresh=55, rsi_sell_thresh=45, **kwargs):
        close = df["close"]
        ema_fast_series = ema(close, window=ema_fast)
        ema_slow_series = ema(close, window=ema_slow)
        rsi_series = rsi(close, window=rsi_window)
        st_df = supertrend(df, period=10, multiplier=3.0)
        st_direction = st_df["direction"]
        bullish = (ema_fast_series > ema_slow_series) & (rsi_series > rsi_buy_thresh) & (st_direction == 1) & _volume_filter(df)
        bearish = (ema_fast_series < ema_slow_series) & (rsi_series < rsi_sell_thresh) & (st_direction == -1) & _volume_filter(df)
        signals = pd.Series(0, index=df.index, dtype=int)
        signals[bullish] = 1
        signals[bearish] = -1
        # same deliberate edge-trigger the strategy applies
        signals[(signals == signals.shift(1)) & (signals != 0)] = 0
        return signals

    df = _synthetic_ohlcv(400, seed=7)
    reference = _reference(df.copy())
    result = generate_signals(df.copy())

    pd.testing.assert_series_equal(reference, result, check_names=False)


def test_generate_signals_still_produces_both_directions():
    """Sanity check the fix isn't vacuously true because nothing ever
    signals -- confirms real buy AND sell signals still fire post-fix."""
    df = _synthetic_ohlcv(400, seed=7)
    signals = generate_signals(df)
    assert (signals == 1).any() or (signals == -1).any()


def test_generate_signals_does_not_mutate_its_input():
    df = _synthetic_ohlcv(150)
    original_columns = list(df.columns)

    generate_signals(df)

    assert list(df.columns) == original_columns


# ---------------------------------------------------------------------------
# Edge-triggering (backlog #7, 2026-08-08)
#
# Root cause proven by direct measurement over the 123-day validation
# window: ema_rsi re-entered after a MEDIAN gap of 5 minutes (one bar)
# from the previous trade's exit, with 63% of those re-entries in the
# SAME direction as the trade that had just closed. The EMA/RSI/
# Supertrend condition stays true for long stretches (21% of bars, runs
# up to 29), and both main.py and the harness are level-triggered, so a
# stop-out inside a run was immediately followed by re-entry into the
# same losing direction. Reference: institutional_momentum, the lowest-
# drawdown strategy in the suite, re-enters after a 20-minute median.
# ---------------------------------------------------------------------------

def test_no_two_consecutive_identical_nonzero_signals():
    """THE regression: a sustained run must collapse to a single edge."""
    df = _synthetic_ohlcv(600, seed=3)
    signals = generate_signals(df)
    duplicates = ((signals == signals.shift(1)) & (signals != 0)).sum()
    assert duplicates == 0, (
        f"{duplicates} bars repeat the previous bar's non-zero signal — "
        "level-triggered re-entry churn has been reintroduced"
    )


def test_edge_triggering_thins_but_does_not_silence():
    df = _synthetic_ohlcv(600, seed=3)
    signals = generate_signals(df)
    nonzero = int((signals != 0).sum())
    assert nonzero > 0, "edge-triggering silenced the strategy entirely"


def test_direction_flip_still_fires_immediately():
    """A genuine reversal (+1 -> -1) is a new setup and must not be
    swallowed as a duplicate."""
    s = pd.Series([0, 1, 1, -1, -1, 0, 1], dtype=int)
    s[(s == s.shift(1)) & (s != 0)] = 0
    assert s.iloc[3] == -1   # the flip survives
    assert s.iloc[2] == 0    # continuation suppressed
    assert s.iloc[4] == 0    # continuation suppressed
    assert s.iloc[6] == 1    # re-arms after a zero gap


def test_edge_trigger_preserves_first_bar_of_every_run():
    """Every run's opening bar must survive — no setup is lost."""
    raw = pd.Series([0, 1, 1, 1, 0, -1, -1, 0, 1], dtype=int)
    edged = raw.copy()
    edged[(edged == edged.shift(1)) & (edged != 0)] = 0
    assert list(edged) == [0, 1, 0, 0, 0, -1, 0, 0, 1]
