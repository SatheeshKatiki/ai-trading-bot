"""Regression tests for institutional-filter isolation.

Context (2026-08-09, `ema_rsi` entry-filter ablation): each filter was
measured one at a time — leave-one-out from production, and alone against
the unfiltered path — and the conclusion of that study rests entirely on
each `enable_*_filter` flag controlling ONE mask and nothing else. If a
flag ever starts gating more than its own filter, or a filter runs while
its flag is off, every ablation number silently becomes a measurement of
something else, and the study cannot be redone.

These tests pin that property. They do not assert that any particular
filter is enabled in `config/settings.json` — which filters to run is an
operator decision backed by evidence, not something a unit test should
freeze — only that the flags do exactly what the ablation assumed.

The study's own finding, for whoever revisits this: of the four filters,
only `squeeze` had a statistically defensible effect (it rejects signals
whose edge is negative while the ones it passes are strongly positive,
stable across every tested threshold). The other three could not be
distinguished from noise. See
`validation_harness/results/filter_significance_ema_rsi.md`.
"""
import _bootstrap  # noqa: F401  (side-effect: puts trading-system/ on sys.path)

import numpy as np
import pandas as pd

from shared.filters.institutional import apply_institutional_filters

FLAGS = ("enable_squeeze_filter", "enable_extension_filter",
         "enable_cpr_filter", "enable_aggression_filter")


def _market(bars=260, seed=7):
    """A frame with enough structure that every filter has something to
    act on: real ranges, a trend, and varying volatility."""
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2026-03-02 09:15", periods=bars, freq="5min")
    drift = np.linspace(0, 60, bars)
    noise = rng.normal(0, 12, bars).cumsum()
    close = 24000 + drift + noise
    high = close + rng.uniform(2, 25, bars)
    low = close - rng.uniform(2, 25, bars)
    open_ = close - rng.normal(0, 6, bars)
    return pd.DataFrame({"open": open_, "high": high, "low": low,
                         "close": close, "volume": rng.uniform(1e5, 5e5, bars)},
                        index=idx)


def _signals(df):
    """Alternating long/short candidates so both the bull and bear side of
    the direction-specific filters (CPR, aggression) get exercised."""
    bullish = pd.Series(False, index=df.index)
    bearish = pd.Series(False, index=df.index)
    bullish.iloc[::2] = True
    bearish.iloc[1::2] = True
    return bullish, bearish


def test_all_flags_off_passes_signals_through_untouched():
    """The legacy path. If this ever stops holding, every pre-2026-08-08
    validation report becomes unreproducible."""
    df = _market()
    bull, bear = _signals(df)
    out_bull, out_bear = apply_institutional_filters(df, bull.copy(), bear.copy())
    assert out_bull.equals(bull)
    assert out_bear.equals(bear)


def test_each_flag_alone_only_ever_removes_signals():
    """A filter may reject; it must never create a signal that the strategy
    did not emit."""
    df = _market()
    bull, bear = _signals(df)
    for flag in FLAGS:
        ob, obe = apply_institutional_filters(df, bull.copy(), bear.copy(), **{flag: True})
        assert (ob & ~bull).sum() == 0, f"{flag} invented a bullish signal"
        assert (obe & ~bear).sum() == 0, f"{flag} invented a bearish signal"


def test_flags_are_independent_and_compose_as_intersection():
    """The property the whole ablation rests on: enabling filters together
    removes exactly the union of what each removes alone, so a
    leave-one-out delta is attributable to that one filter."""
    df = _market()
    bull, bear = _signals(df)

    solo_bull, solo_bear = {}, {}
    for flag in FLAGS:
        b, be = apply_institutional_filters(df, bull.copy(), bear.copy(), **{flag: True})
        solo_bull[flag], solo_bear[flag] = b, be

    all_on = {f: True for f in FLAGS}
    combined_bull, combined_bear = apply_institutional_filters(
        df, bull.copy(), bear.copy(), **all_on)

    expect_bull = bull.copy()
    expect_bear = bear.copy()
    for flag in FLAGS:
        expect_bull &= solo_bull[flag]
        expect_bear &= solo_bear[flag]

    assert combined_bull.equals(expect_bull)
    assert combined_bear.equals(expect_bear)


def test_leave_one_out_differs_from_all_on_only_by_that_filter():
    """Directly models how the ablation measures a filter: production minus
    one flag must equal the intersection of the other three."""
    df = _market()
    bull, bear = _signals(df)
    all_on = {f: True for f in FLAGS}

    for dropped in FLAGS:
        loo = dict(all_on, **{dropped: False})
        loo_bull, loo_bear = apply_institutional_filters(df, bull.copy(), bear.copy(), **loo)

        expect_bull, expect_bear = bull.copy(), bear.copy()
        for flag in FLAGS:
            if flag == dropped:
                continue
            b, be = apply_institutional_filters(df, bull.copy(), bear.copy(), **{flag: True})
            expect_bull &= b
            expect_bear &= be

        assert loo_bull.equals(expect_bull), f"dropping {dropped} changed another filter"
        assert loo_bear.equals(expect_bear), f"dropping {dropped} changed another filter"


def test_flags_accept_string_booleans_from_the_dashboard():
    """Settings arrive from a JSON file and from UI query params, so 'true'
    must behave like True — otherwise a filter silently stops running in
    one of the two paths and the backtest diverges from live."""
    df = _market()
    bull, bear = _signals(df)
    for flag in FLAGS:
        b_bool, be_bool = apply_institutional_filters(df, bull.copy(), bear.copy(), **{flag: True})
        b_str, be_str = apply_institutional_filters(df, bull.copy(), bear.copy(), **{flag: "true"})
        assert b_bool.equals(b_str), f"{flag} ignores the string form"
        assert be_bool.equals(be_str), f"{flag} ignores the string form"


def test_squeeze_actually_rejects_something_on_realistic_data():
    """The one filter the ablation found statistically defensible. A silent
    no-op here (e.g. a column rename making the mask all-False) would look
    like 'the filter stopped helping' in the next validation run."""
    df = _market()
    bull, bear = _signals(df)
    out_bull, out_bear = apply_institutional_filters(
        df, bull.copy(), bear.copy(), enable_squeeze_filter=True)
    removed = int((bull & ~out_bull).sum() + (bear & ~out_bear).sum())
    assert removed > 0, "squeeze filter rejected nothing — it may have become inert"
