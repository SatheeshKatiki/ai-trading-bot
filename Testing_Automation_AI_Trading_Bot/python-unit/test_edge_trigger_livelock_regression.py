"""Regression coverage for the 2026-08-28 edge-trigger CPU-livelock.

Root cause (caught live with py-spy on the production engine, PID pegged at
~50% of a core, engine log silent for a whole trading session): the
edge-trigger step added to three strategies on 2026-08-08 was written as a
boolean-mask ``Series.__setitem__``::

    signals[(signals == signals.shift(1)) & (signals != 0)] = 0

This is the *exact* signature the 2026-08-06/07 audit rewrote
``registry.py`` and ``ema_rsi_strategy.py``'s signal *construction* to
avoid — under a ``DatetimeIndex`` carrying duplicate or non-monotonic
timestamps (which the live 5-minute candle cache accumulates when Fyers
re-serves overlapping ranges) the mask stops being treated as boolean and
routes through ``Series._set_with_engine -> Index.get_loc ->
Series.__repr__``: one label lookup plus a full-Series repr per row.

Fixed by moving all three call sites onto
``trading_bot.strategies._signal_utils.edge_trigger``, which computes the
same result on the underlying numpy array. Full writeup:
``docs/paper_trading_validation/anomaly_log.md``'s 2026-08-28 entry.
"""
import time

import numpy as np
import pandas as pd

import _bootstrap  # noqa: F401  (side-effect: puts trading-system/ on sys.path)

from trading_bot.strategies._signal_utils import edge_trigger


# --- the pre-fix implementation, kept only as a correctness oracle ----------

def _setitem_oracle(signals: pd.Series) -> pd.Series:
    s = signals.copy()
    s[(s == s.shift(1)) & (s != 0)] = 0
    return s


def _random_signal_series(n, index, seed=0):
    rng = np.random.default_rng(seed)
    return pd.Series(rng.choice([-1, 0, 0, 1], size=n), index=index, dtype=int)


# --- equivalence ----------------------------------------------------------

def test_matches_setitem_oracle_on_clean_index():
    idx = pd.RangeIndex(500)
    s = _random_signal_series(500, idx, seed=1)
    pd.testing.assert_series_equal(edge_trigger(s), _setitem_oracle(s), check_names=False)


def test_matches_hand_worked_example():
    raw = pd.Series([0, 1, 1, 1, 0, -1, -1, 0, 1], dtype=int)
    assert list(edge_trigger(raw)) == [0, 1, 0, 0, 0, -1, 0, 0, 1]


def test_direction_flip_is_not_swallowed():
    raw = pd.Series([0, 1, 1, -1, -1, 0, 1], dtype=int)
    assert list(edge_trigger(raw)) == [0, 1, 0, -1, 0, 0, 1]


def test_first_bar_preserved_and_dtype_and_index_kept():
    idx = pd.date_range("2026-08-28 09:15", periods=6, freq="5min")
    raw = pd.Series([1, 1, 0, -1, -1, -1], index=idx, dtype=int)
    out = edge_trigger(raw)
    assert out.iloc[0] == 1
    assert out.dtype == np.dtype("int64") or out.dtype == int
    assert out.index.equals(idx)
    assert list(out) == [1, 0, 0, -1, 0, 0]


def test_single_row_and_empty_are_safe():
    assert list(edge_trigger(pd.Series([1], dtype=int))) == [1]
    assert list(edge_trigger(pd.Series([], dtype=int))) == []


# --- the actual livelock: a duplicate / non-monotonic DatetimeIndex --------

def _duplicate_datetime_index(n):
    base = pd.date_range("2026-08-28 09:15", periods=n, freq="5min")
    # re-serve the last 40% of the range on top of itself, out of order —
    # the shape the live 5-min cache takes after overlapping Fyers pulls
    overlap = base[int(n * 0.6):]
    idx = base.append(overlap)[:n]
    return idx


def test_edge_trigger_is_fast_under_a_duplicate_index():
    n = 1500
    idx = _duplicate_datetime_index(n)
    s = _random_signal_series(n, idx, seed=7)

    start = time.perf_counter()
    out = edge_trigger(s)
    elapsed = time.perf_counter() - start

    # the setitem form takes many seconds → minutes on this input; the
    # numpy form is sub-millisecond. One second is a very loose ceiling.
    assert elapsed < 1.0, f"edge_trigger took {elapsed:.2f}s on a duplicate index"
    assert len(out) == n
    assert set(np.unique(out)).issubset({-1, 0, 1})


def test_no_strategy_keeps_a_boolean_mask_edge_trigger_in_code():
    """None of the three edge-triggering strategies may keep a live
    boolean-mask setitem — comments explaining the history are fine, an
    actual executable statement is not."""
    import inspect

    from trading_bot.strategies import (
        ema_rsi_strategy,
        advanced_ai_ml_strategy,
        ultra_meta_dip_swarm,
    )

    for mod in (ema_rsi_strategy, advanced_ai_ml_strategy, ultra_meta_dip_swarm):
        code_lines = [
            ln for ln in inspect.getsource(mod).splitlines()
            if ln.strip() and not ln.lstrip().startswith("#")
        ]
        offenders = [ln for ln in code_lines if "shift(1))" in ln and "] = 0" in ln]
        assert not offenders, f"{mod.__name__} still runs a boolean-mask edge-trigger: {offenders}"


def test_each_strategy_completes_fast_on_a_duplicate_datetime_index():
    """End-to-end: the real strategies must not livelock on the index shape
    that triggered the 2026-08-28 incident."""
    from trading_bot.strategies.registry import registry
    import trading_bot.strategies  # noqa: F401  (registers all strategies)

    n = 800
    idx = _duplicate_datetime_index(n)
    rng = np.random.default_rng(3)
    close = 24_000 + rng.normal(0, 15, n).cumsum()
    df = pd.DataFrame(
        {
            "open": close - rng.uniform(1, 8, n),
            "high": close + rng.uniform(1, 12, n),
            "low": close - rng.uniform(1, 12, n),
            "close": close,
            "volume": rng.integers(1_000, 50_000, n).astype(float),
        },
        index=idx,
    )

    for name in ("ema_rsi", "advanced_ai", "ultra_meta_dip_swarm"):
        if name not in registry._strategies:
            continue
        start = time.perf_counter()
        result = registry._strategies[name](df.copy())
        elapsed = time.perf_counter() - start
        signals = result[0] if isinstance(result, tuple) else result
        assert elapsed < 20.0, f"{name} took {elapsed:.1f}s on a duplicate index"
        assert set(np.unique(np.asarray(signals, dtype=int))).issubset({-1, 0, 1})
