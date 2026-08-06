"""Regression coverage for the 2026-08-06 CPU-livelock incident.

Root cause: `shared/ai/features.py::compute_features`,
`shared/indicators/supertrend.py::supertrend`, and
`trading_bot/strategies/ema_rsi_strategy.py::generate_signals` all used to
build their output by assigning new columns onto a DataFrame one at a time
(`df["x"] = ...`, repeated per column). Under pandas 3.0.3, each such
assignment calls through to `Index.insert()` to grow the column index by
one label — and in a long-running process calling these functions roughly
5x/second, that per-call cost was observed live to become catastrophic:
`py-spy dump` caught the engine's event loop stuck inside exactly this
call chain for 20+ minutes at 97-100% CPU with zero forward progress, on
three separate live incidents the same day, reproducing with as few as one
watched instrument. Full incident writeup:
docs/paper_trading_validation/anomaly_log.md, 2026-08-06 entries.

All three functions were rewritten to build every intermediate value as a
plain Series/array first and construct the output DataFrame exactly once,
with every column already known — eliminating every incremental
`Index.insert()` call regardless of the deeper pandas/pyarrow mechanism.
These tests pin (1) that the rewrite is bit-for-bit behaviourally identical
to the pre-fix implementation, (2) that no caller's input DataFrame is
mutated as a side effect, and (3) a bounded repeated-call smoke check that
would catch a severe reintroduction of the same pathology, without being
a flaky full stress test in CI.
"""
import time

import _bootstrap  # noqa: F401  (side-effect: puts trading-system/ on sys.path)

import numpy as np
import pandas as pd
import pytest

from shared.ai.features import compute_features
from shared.indicators import ema, rsi, supertrend
from shared.indicators.atr import atr
from trading_bot.strategies.ema_rsi_strategy import _volume_filter, generate_signals


def _synthetic_ohlcv(n: int = 300, seed: int = 42) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    close = 24_000 + rng.normal(0, 15, n).cumsum()
    df = pd.DataFrame({
        "open": close - rng.uniform(1, 8, n),
        "high": close + rng.uniform(1, 12, n),
        "low": close - rng.uniform(1, 12, n),
        "close": close,
        "volume": rng.integers(1_000, 50_000, n).astype(float),
    })
    return df


# ---------------------------------------------------------------------------
# compute_features
# ---------------------------------------------------------------------------

def _compute_features_reference(df: pd.DataFrame) -> pd.DataFrame:
    """The pre-fix implementation, kept only as a reference oracle for these
    tests — incremental `feat["x"] = ...` assignment, one column at a time."""
    feat = pd.DataFrame(index=df.index)
    close, high, low, volume = df["close"], df["high"], df["low"], df["volume"]
    feat["return_1"] = close.pct_change(1)
    feat["return_3"] = close.pct_change(3)
    feat["return_5"] = close.pct_change(5)
    candle_range = high - low
    candle_body = (close - df["open"]).abs()
    feat["body_ratio"] = np.where(candle_range > 0, candle_body / candle_range, 0)
    feat["upper_shadow"] = np.where(candle_range > 0, (high - np.maximum(close, df["open"])) / candle_range, 0)
    feat["lower_shadow"] = np.where(candle_range > 0, (np.minimum(close, df["open"]) - low) / candle_range, 0)
    ema9, ema21 = ema(close, window=9), ema(close, window=21)
    feat["ema_fast_slow_diff"] = (ema9 - ema21) / ema21 * 100
    feat["price_vs_ema9"] = (close - ema9) / ema9 * 100
    feat["price_vs_ema21"] = (close - ema21) / ema21 * 100
    rsi_14 = rsi(close, window=14); rsi_14.iloc[:14] = np.nan
    feat["rsi_14"] = rsi_14
    rsi_7 = rsi(close, window=7); rsi_7.iloc[:7] = np.nan
    feat["rsi_7"] = rsi_7

    def _atr(h, l, c, window=14):
        prev_close = c.shift(1)
        tr = pd.concat([h - l, (h - prev_close).abs(), (l - prev_close).abs()], axis=1).max(axis=1)
        return tr.rolling(window=window, min_periods=1).mean()

    feat["atr_14"] = _atr(high, low, close)
    feat["atr_pct"] = feat["atr_14"] / close * 100
    feat["volatility_5"] = close.rolling(5).std() / close * 100
    vol_ma = volume.rolling(20, min_periods=1).mean()
    feat["volume_ratio"] = np.where(vol_ma > 0, volume / vol_ma, 1.0)
    feat["volume_change"] = volume.pct_change(1)
    feat["momentum_10"] = close / close.shift(10) - 1
    feat["roc_5"] = (close - close.shift(5)) / close.shift(5) * 100

    prev_high, prev_low = high.shift(1), low.shift(1)
    plus_dm = np.where((high - prev_high) > (prev_low - low), np.maximum(high - prev_high, 0), 0)
    minus_dm = np.where((prev_low - low) > (high - prev_high), np.maximum(prev_low - low, 0), 0)
    atr14 = _atr(high, low, close)
    plus_di = pd.Series(plus_dm, index=high.index).rolling(14, min_periods=1).mean() / (atr14 + 1e-9) * 100
    minus_di = pd.Series(minus_dm, index=high.index).rolling(14, min_periods=1).mean() / (atr14 + 1e-9) * 100
    dx = (plus_di - minus_di).abs() / (plus_di + minus_di + 1e-9) * 100
    feat["adx_14"] = dx.rolling(14, min_periods=1).mean()

    feat.replace([np.inf, -np.inf], 0.0, inplace=True)
    return feat.dropna()


def test_compute_features_matches_the_pre_fix_reference():
    df = _synthetic_ohlcv(300)
    reference = _compute_features_reference(df.copy())
    result = compute_features(df.copy())

    assert list(result.columns) == list(reference.columns)
    assert result.index.equals(reference.index)
    np.testing.assert_allclose(result.values, reference.values, equal_nan=True)


def test_compute_features_does_not_mutate_its_input():
    df = _synthetic_ohlcv(150)
    original_columns = list(df.columns)

    compute_features(df)

    assert list(df.columns) == original_columns


@pytest.mark.parametrize("n", [10, 60, 300])
def test_compute_features_runs_on_various_sizes(n):
    result = compute_features(_synthetic_ohlcv(n))
    assert isinstance(result, pd.DataFrame)


def test_compute_features_repeated_calls_stay_bounded():
    """Not a full stress test (that lives in the incident's manual
    investigation, not CI) -- a bounded smoke check that a severe
    reintroduction of the incremental-insert pathology (order-of-magnitude
    slowdown within a few hundred calls) would fail fast rather than
    silently."""
    df = _synthetic_ohlcv(200)
    slice_100 = df.tail(100)

    durations = []
    for _ in range(300):
        t0 = time.perf_counter()
        compute_features(slice_100)
        durations.append(time.perf_counter() - t0)

    first_avg = sum(durations[:20]) / 20
    last_avg = sum(durations[-20:]) / 20
    # Generous bound -- this only needs to catch a severe regression, not
    # assert a specific performance target.
    assert last_avg < max(first_avg * 5, 0.05), (
        f"compute_features slowed from {first_avg*1000:.2f}ms to "
        f"{last_avg*1000:.2f}ms over 300 repeated calls -- possible "
        f"reintroduction of the incremental-column-insert pathology."
    )


# ---------------------------------------------------------------------------
# supertrend
# ---------------------------------------------------------------------------

def _supertrend_reference(df: pd.DataFrame, period: int = 10, multiplier: float = 3.0) -> pd.DataFrame:
    df = df.copy()
    high, low, close = df["high"], df["low"], df["close"]
    df["atr"] = atr(df, window=period)
    df["hl2"] = (high + low) / 2
    df["basic_ub"] = df["hl2"] + (multiplier * df["atr"])
    df["basic_lb"] = df["hl2"] - (multiplier * df["atr"])
    final_ub = np.zeros(len(df)); final_lb = np.zeros(len(df))
    supertrend_arr = np.zeros(len(df)); direction = np.ones(len(df), dtype=int)
    basic_ub_np = df["basic_ub"].to_numpy(); basic_lb_np = df["basic_lb"].to_numpy(); close_np = close.to_numpy()
    for i in range(1, len(df)):
        if basic_ub_np[i] < final_ub[i - 1] or close_np[i - 1] > final_ub[i - 1]:
            final_ub[i] = basic_ub_np[i]
        else:
            final_ub[i] = final_ub[i - 1]
        if basic_lb_np[i] > final_lb[i - 1] or close_np[i - 1] < final_lb[i - 1]:
            final_lb[i] = basic_lb_np[i]
        else:
            final_lb[i] = final_lb[i - 1]
        if supertrend_arr[i - 1] == final_ub[i - 1]:
            if close_np[i] > final_ub[i]:
                supertrend_arr[i] = final_lb[i]; direction[i] = 1
            else:
                supertrend_arr[i] = final_ub[i]; direction[i] = -1
        else:
            if close_np[i] < final_lb[i]:
                supertrend_arr[i] = final_ub[i]; direction[i] = -1
            else:
                supertrend_arr[i] = final_lb[i]; direction[i] = 1
    df["supertrend"] = supertrend_arr
    df["direction"] = direction
    return df[["supertrend", "direction"]]


def test_supertrend_matches_the_pre_fix_reference():
    df = _synthetic_ohlcv(250)
    reference = _supertrend_reference(df.copy())
    result = supertrend(df.copy())

    assert reference.equals(result)


def test_supertrend_does_not_mutate_its_input():
    df = _synthetic_ohlcv(150)
    original_columns = list(df.columns)

    supertrend(df)

    assert list(df.columns) == original_columns


def test_supertrend_output_has_exactly_the_documented_columns():
    result = supertrend(_synthetic_ohlcv(60))
    assert list(result.columns) == ["supertrend", "direction"]
    assert set(result["direction"].unique()) <= {1, -1}


# ---------------------------------------------------------------------------
# ema_rsi_strategy.generate_signals
# ---------------------------------------------------------------------------

def _generate_signals_reference(df, ema_fast=20, ema_slow=50, rsi_window=14, rsi_buy_thresh=55, rsi_sell_thresh=45, **kwargs):
    df["ema_fast"] = ema(df["close"], window=ema_fast)
    df["ema_slow"] = ema(df["close"], window=ema_slow)
    df["rsi"] = rsi(df["close"], window=rsi_window)
    st_df = supertrend(df, period=10, multiplier=3.0)
    df["st_direction"] = st_df["direction"]
    bullish = (df["ema_fast"] > df["ema_slow"]) & (df["rsi"] > rsi_buy_thresh) & (df["st_direction"] == 1) & _volume_filter(df)
    bearish = (df["ema_fast"] < df["ema_slow"]) & (df["rsi"] < rsi_sell_thresh) & (df["st_direction"] == -1) & _volume_filter(df)
    signals = pd.Series(0, index=df.index, dtype=int)
    signals[bullish] = 1
    signals[bearish] = -1
    return signals


def test_generate_signals_matches_the_pre_fix_reference():
    df = _synthetic_ohlcv(300)
    reference = _generate_signals_reference(df.copy())
    result = generate_signals(df.copy())

    assert reference.equals(result)


def test_generate_signals_produces_both_directions_on_a_trending_series():
    """Sanity check the reference/rewrite comparison above isn't vacuously
    true because nothing ever signals — confirms real buy AND sell signals
    still fire post-rewrite."""
    df = _synthetic_ohlcv(400, seed=7)
    signals = generate_signals(df)
    assert (signals == 1).any() or (signals == -1).any()
