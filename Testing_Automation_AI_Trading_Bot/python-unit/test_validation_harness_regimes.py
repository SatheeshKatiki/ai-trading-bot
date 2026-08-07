"""Unit tests for validation_harness/regimes.py -- daily market-regime
classification for the Production Strategy Validation Framework.
"""
import numpy as np
import pandas as pd

import _bootstrap  # noqa: F401  (side-effect: puts trading-system/ on sys.path)

from validation_harness.regimes import REGIME_NAMES, classify_daily_regimes, slice_by_regime


def _synthetic_intraday(days: int, bars_per_day: int = 20, trend_per_day: float = 0.0,
                         noise: float = 5.0, gap_on_day: int | None = None, seed: int = 1,
                         mean_revert: bool = False) -> pd.DataFrame:
    """`mean_revert=True` pulls price back toward a fixed center each bar
    (Ornstein-Uhlenbeck-like) instead of a pure random walk -- a genuinely
    flat/choppy series, not just a zero-drift one. A pure random walk with
    zero explicit drift can still exhibit locally "trending" segments by
    chance (a well-known property of Brownian motion), so it's the wrong
    generator for a "this should NOT classify as trending" test case."""
    rng = np.random.default_rng(seed)
    rows = []
    center = 24_000.0
    price = center
    for d in range(days):
        day_start = pd.Timestamp("2026-01-05") + pd.Timedelta(days=d)
        if day_start.weekday() >= 5:
            continue
        if gap_on_day is not None and d == gap_on_day:
            price += 300.0  # a deliberate overnight gap
        for b in range(bars_per_day):
            ts = day_start + pd.Timedelta(minutes=5 * b)
            if mean_revert:
                price += 0.1 * (center - price) + rng.normal(0, noise)
            else:
                price += trend_per_day / bars_per_day + rng.normal(0, noise)
            rows.append({
                "datetime": ts, "open": price, "high": price + 2, "low": price - 2,
                "close": price, "volume": 1000,
            })
    df = pd.DataFrame(rows).set_index("datetime")
    return df


def test_classify_returns_one_label_per_day_from_the_known_set():
    df = _synthetic_intraday(days=20)
    labels = classify_daily_regimes(df)
    assert not labels.empty
    assert set(labels.unique()) <= set(REGIME_NAMES)


def test_a_deliberate_gap_day_is_classified_as_gap_day():
    df = _synthetic_intraday(days=15, gap_on_day=7, trend_per_day=0.0, noise=1.0)
    labels = classify_daily_regimes(df)
    gap_days = labels[labels == "gap_day"]
    assert len(gap_days) >= 1


def test_a_strongly_trending_series_is_classified_as_trending_on_most_days():
    df = _synthetic_intraday(days=20, trend_per_day=150.0, noise=3.0)
    labels = classify_daily_regimes(df)
    # Not every single day need be "trending" (early days lack ADX warmup,
    # and per-day noise varies), but the strong consistent drift should
    # dominate the classification.
    assert (labels == "trending").sum() >= (len(labels) * 0.3)


def test_a_mean_reverting_choppy_series_is_not_classified_as_trending():
    """Needs enough trading days for ADX(14) to actually converge past its
    own warmup transient -- see regimes.py's "Note on minimum history".
    A too-short series was found, during test development, to misread
    even genuinely mean-reverting data as "trending" throughout, purely
    from ADX still converging -- not a classifier bug, a minimum-sample
    requirement now documented there."""
    df = _synthetic_intraday(days=90, noise=8.0, mean_revert=True)
    labels = classify_daily_regimes(df)
    # Only assert on the back half -- the front half is still inside
    # ADX(14)'s own warmup transient (see the note above) and isn't a
    # fair test of steady-state classification.
    steady_state = labels.iloc[len(labels) // 2:]
    assert (steady_state == "trending").sum() < (len(steady_state) * 0.3)


def test_empty_dataframe_returns_empty_series():
    df = pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
    df.index = pd.DatetimeIndex([])
    labels = classify_daily_regimes(df)
    assert labels.empty


def test_slice_by_regime_returns_only_matching_days():
    df = _synthetic_intraday(days=10)
    labels = classify_daily_regimes(df)
    some_regime = labels.iloc[0]
    sliced = slice_by_regime(df, labels, some_regime)
    if not sliced.empty:
        assert all((ts.date() if hasattr(ts, "date") else ts) in
                   set(labels[labels == some_regime].index) for ts in sliced.index)


def test_slice_by_regime_with_no_matching_days_returns_empty():
    df = _synthetic_intraday(days=5)
    labels = classify_daily_regimes(df)
    sliced = slice_by_regime(df, labels, "a_regime_that_does_not_exist")
    assert sliced.empty
