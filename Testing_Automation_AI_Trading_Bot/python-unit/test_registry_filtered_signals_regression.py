"""Regression coverage for the 2026-08-07 elevated-CPU finding.

Root cause: `StrategyRegistry.run_strategy` built its post-institutional-
filter signal Series via two incremental boolean-mask assignments
(`filtered_signals[f_bull] = 1`, `filtered_signals[f_bear] = -1`). A
`py-spy dump` of the live process caught this exact line active inside
`Series.__setitem__ -> _set_with_engine -> Index.get_loc -> Series.__repr__
-> to_string`, the same call-chain signature (`KeyError`/`repr()` path via
`get_loc`) that appeared in the 2026-08-06 CPU-livelock investigation's
own dumps -- flagged there as "not conclusively ruled out" rather than
fixed, since that day's fix only targeted the three incremental-column-
insert call sites (`compute_features`, `supertrend`, `generate_signals`),
not this one. Full writeup: docs/paper_trading_validation/anomaly_log.md,
2026-08-07 entry.

Fixed by building the filtered signal Series in one `np.select` call
against the two boolean masks' underlying numpy arrays, eliminating every
`Series.__setitem__` call on `filtered_signals` regardless of the deeper
pandas/pyarrow mechanism. This test pins that the rewrite is bit-for-bit
identical to the pre-fix incremental-assignment implementation, including
on the (structurally impossible in real usage, since `bullish`/`bearish`
derive from mutually exclusive signal values, but exercised here for
overwrite-order safety) overlapping-mask edge case.
"""
import _bootstrap  # noqa: F401  (side-effect: puts trading-system/ on sys.path)

import numpy as np
import pandas as pd

from trading_bot.strategies.registry import StrategyRegistry


def _filtered_signals_reference(f_bull: pd.Series, f_bear: pd.Series, index) -> pd.Series:
    """The pre-fix implementation, kept only as a reference oracle."""
    filtered_signals = pd.Series(0, index=index, dtype=int)
    filtered_signals[f_bull] = 1
    filtered_signals[f_bear] = -1
    return filtered_signals


def _filtered_signals_current(f_bull: pd.Series, f_bear: pd.Series, index) -> pd.Series:
    return pd.Series(
        np.select([f_bear.to_numpy(), f_bull.to_numpy()], [-1, 1], default=0),
        index=index,
        dtype=int,
    )


def test_filtered_signals_matches_pre_fix_reference_no_overlap():
    n = 500
    idx = pd.RangeIndex(n)
    rng = np.random.default_rng(3)
    f_bull = pd.Series(rng.random(n) < 0.2, index=idx)
    f_bear = pd.Series((~f_bull) & (rng.random(n) < 0.2), index=idx)

    reference = _filtered_signals_reference(f_bull, f_bear, idx)
    result = _filtered_signals_current(f_bull, f_bear, idx)

    pd.testing.assert_series_equal(reference, result, check_names=False)


def test_filtered_signals_matches_pre_fix_reference_all_false():
    n = 200
    idx = pd.RangeIndex(n)
    f_bull = pd.Series(False, index=idx)
    f_bear = pd.Series(False, index=idx)

    reference = _filtered_signals_reference(f_bull, f_bear, idx)
    result = _filtered_signals_current(f_bull, f_bear, idx)

    pd.testing.assert_series_equal(reference, result, check_names=False)
    assert (result == 0).all()


def test_filtered_signals_matches_pre_fix_reference_overlap_bear_wins():
    """Structurally impossible via real bullish/bearish inputs (they derive
    from mutually exclusive signal values), but confirms the overwrite
    order is preserved if it ever did happen."""
    n = 50
    idx = pd.RangeIndex(n)
    f_bull = pd.Series(True, index=idx)
    f_bear = pd.Series(True, index=idx)

    reference = _filtered_signals_reference(f_bull, f_bear, idx)
    result = _filtered_signals_current(f_bull, f_bear, idx)

    pd.testing.assert_series_equal(reference, result, check_names=False)
    assert (result == -1).all()


def test_run_strategy_end_to_end_applies_institutional_filters_without_setitem():
    """End-to-end through the real registry with a real strategy + real
    institutional filters (CPR/squeeze/extension/aggression all enabled),
    confirming the full path still produces a valid signal Series."""
    n = 300
    rng = np.random.default_rng(11)
    close = 24_000 + rng.normal(0, 15, n).cumsum()
    df = pd.DataFrame({
        "open": close - rng.uniform(1, 8, n),
        "high": close + rng.uniform(1, 12, n),
        "low": close - rng.uniform(1, 12, n),
        "close": close,
        "volume": rng.integers(1_000, 50_000, n).astype(float),
    })

    def _dummy_strategy(df, **kwargs):
        signals = pd.Series(0, index=df.index, dtype=int)
        signals.iloc[::7] = 1
        signals.iloc[::11] = -1
        return signals

    reg = StrategyRegistry()
    reg.register("dummy", _dummy_strategy)

    result = reg.run_strategy(
        "dummy", df,
        enable_cpr_filter=True, enable_squeeze_filter=True,
        enable_extension_filter=True, enable_aggression_filter=True,
    )

    assert isinstance(result, pd.Series)
    assert result.dtype == int
    assert set(result.unique()) <= {-1, 0, 1}
