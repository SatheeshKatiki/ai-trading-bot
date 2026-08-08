"""Executable spec for the drl_strategy market-blindness defect
(backlog #5, diagnosed 2026-08-08).

FINDING — two independent faults, both proven by execution:

1. **Broken observation pipeline.** `compute_features()` reads
   'rsi'/'macd_hist'/'atr'/'vol_change' off the dataframe via
   `.get(col, default)`. Those columns do not exist on the raw OHLCV
   frame `generate_signals()` receives, so every lookup silently returns
   its hardcoded default. The model's observation is the constant
   `[50, 0, 0, 0]` on every bar of every market.

2. **Collapsed model artifact.** Attaching real, correctly-computed
   RSI/MACD-hist/ATR/volume-change features does NOT fix it — the output
   remains byte-identical across opposite markets and remains 100%
   one-directional (BUY only, zero SELL). The trained model itself has
   degenerated to a single action regardless of input.

Consequence: the strategy's production-validation result (1,189 trades,
PF 1.07 — the largest sample in the suite) is not evidence of any
market edge. It is "buy a call on nearly every bar and let the Smart
Exit Engine manage it."

These tests assert what a CORRECT strategy must do. They are expected to
fail for as long as the current model artifact is in place, so they are
marked xfail — the suite stays green while the defect stays documented
and executable. If the model is ever retrained properly, these flip to
XPASS and surface immediately.
"""
import numpy as np
import pandas as pd
import pytest

import _bootstrap  # noqa: F401  (side-effect: puts trading-system/ on sys.path)

from trading_bot.strategies import drl_strategy as drl


def _series(seed: int, drift: float, n: int = 300) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    close = 24_000 + rng.normal(drift, 25, n).cumsum()
    idx = pd.date_range("2026-06-01 09:15", periods=n, freq="5min")
    return pd.DataFrame({
        "open": close, "high": close + 8, "low": close - 8, "close": close,
        "volume": rng.integers(1_000, 50_000, n).astype(float),
    }, index=idx)


def _signals_for(df: pd.DataFrame) -> pd.Series:
    drl._drl_instance = None  # fresh LSTM state per market
    return drl.generate_signals(df)


@pytest.mark.xfail(
    reason="drl_strategy is market-blind: constant observation + collapsed "
           "model artifact. See module docstring.",
    strict=False,
)
def test_signals_must_differ_between_opposite_markets():
    """A strategy that cannot distinguish a +7,500pt uptrend from a
    -7,500pt downtrend has no market edge by definition."""
    if not drl.HAS_SB3:
        pytest.skip("sb3_contrib not installed")
    bull = _series(seed=1, drift=+25)
    bear = _series(seed=99, drift=-25)
    assert bull["close"].iloc[-1] > bull["close"].iloc[0]
    assert bear["close"].iloc[-1] < bear["close"].iloc[0]

    s_bull = _signals_for(bull)
    s_bear = _signals_for(bear)

    assert not (s_bull.values == s_bear.values).all(), (
        "signal output is byte-identical across opposite markets — the "
        "strategy cannot see market data at all"
    )


@pytest.mark.xfail(
    reason="drl_strategy's model has collapsed to a single action (BUY only).",
    strict=False,
)
def test_strategy_must_be_able_to_emit_both_directions():
    """An option-buying strategy must be able to choose a PUT. Emitting
    only CALLs across every market regime is a permanent directional
    bias, not a signal."""
    if not drl.HAS_SB3:
        pytest.skip("sb3_contrib not installed")
    bear = _series(seed=99, drift=-25)
    s = _signals_for(bear)
    assert (s == -1).sum() > 0, (
        f"strategy emitted {(s == 1).sum()} BUY and 0 SELL signals across a "
        "sustained downtrend — permanently one-directional"
    )


def test_observation_vector_is_currently_constant_regardless_of_market():
    """Pins fault #1 directly (this one asserts the CURRENT broken
    behaviour deliberately, so that fixing the feature pipeline causes a
    visible, intentional test failure rather than passing silently)."""
    s = drl.DRLStrategy()
    bull = _series(seed=1, drift=+25)
    bear = _series(seed=99, drift=-25)

    f_bull = s.compute_features(bull)
    f_bear = s.compute_features(bear)

    assert np.array_equal(f_bull, f_bear), (
        "observation now varies with the market — the feature pipeline has "
        "been fixed; update this test and re-evaluate the strategy's verdict"
    )
    assert np.array_equal(f_bull, np.array([50, 0, 0, 0], dtype=np.float32))
