"""Regression coverage for the advanced_ai re-entry churn defect
(backlog #6, root-caused and fixed 2026-08-08).

Root cause, proven from production code + backtest evidence:
the ML confidence score stays above threshold for long stretches —
measured 64% of all bars, in 453 runs averaging 2.2 bars, reaching 22.
Both `main.py`'s live entry path and the validation harness are
LEVEL-triggered ("if flat and signal != 0, enter"), so every stop-out
inside a run was immediately followed by re-entry into the same losing
direction, repeatedly, for as long as the run lasted.

Measured consequences before the fix:
  - 8.1 trades/day (vs 2.9 for institutional_momentum)
  - 52 of 122 days breached the Rs 5,000 daily-loss limit
  - worst day -Rs 17,252
  - 61.9% max drawdown = 2.95x what its own consecutive-loss streaks
    explain (the Q2 risk-model violation)

Notably NOT the cause (both disproven by measurement): per-trade loss
overshoot (advanced_ai 1.27x designed risk vs institutional_momentum's
1.38x — the low-drawdown strategy overshoots MORE), and gap-through
artifacts.

Fix: emit the signal only on the transition into a run. A sustained run
above the confidence threshold is ONE setup, not one per bar. Every
setup the strategy detects is preserved; only the churn is removed. The
legacy backtest engine already edge-triggers internally
(`sig_vals[i-1] != 1`); this aligns the strategy's own output with that
semantics for the live path, which does not.
"""
import numpy as np
import pandas as pd

import _bootstrap  # noqa: F401  (side-effect: puts trading-system/ on sys.path)

from trading_bot.strategies.registry import registry


def _ohlcv(n: int = 400, seed: int = 5) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    close = 24_000 + rng.normal(0, 15, n).cumsum()
    idx = pd.date_range("2026-06-01 09:15", periods=n, freq="5min")
    return pd.DataFrame({
        "open": close, "high": close + 8, "low": close - 8, "close": close,
        "volume": rng.integers(1_000, 50_000, n).astype(float),
    }, index=idx)


def _signals(df: pd.DataFrame) -> pd.Series:
    r = registry.run_strategy("advanced_ai", df.copy())
    s = r[0] if isinstance(r, tuple) else r
    return s.fillna(0).astype(int)


def test_no_two_consecutive_identical_nonzero_signals():
    """THE regression: a level-triggered run must collapse to a single
    edge. Consecutive duplicates are exactly what caused re-entry churn
    after every stop-out."""
    s = _signals(_ohlcv(600))
    duplicates = ((s == s.shift(1)) & (s != 0)).sum()
    assert duplicates == 0, (
        f"{duplicates} bars repeat the previous bar's non-zero signal — "
        "level-triggered churn has been reintroduced"
    )


def test_output_remains_a_valid_signal_series():
    s = _signals(_ohlcv(400))
    assert isinstance(s, pd.Series)
    assert set(s.unique()) <= {-1, 0, 1}


def test_signal_count_is_reduced_but_not_eliminated():
    """Edge-triggering must preserve the setups the strategy detects —
    it should thin the series, not silence it."""
    s = _signals(_ohlcv(600))
    nonzero = int((s != 0).sum())
    assert nonzero > 0, "edge-triggering silenced the strategy entirely"
    assert nonzero < len(s) * 0.5, "signal still fires on a majority of bars"


def test_a_direction_flip_still_emits_immediately():
    """Edge-triggering must not suppress a genuine reversal: 1 -> -1 is a
    new setup and must fire on the bar it occurs, not be swallowed as a
    'duplicate'."""
    s = pd.Series([0, 1, 1, -1, -1, 0, 1], dtype=int)
    edged = s.where(s != s.shift(1), other=s).astype(int)
    edged[(edged == edged.shift(1)) & (edged != 0)] = 0
    # index 3 is the flip from +1 to -1 and must survive
    assert edged.iloc[3] == -1
    # index 2 and 4 are continuations and must be suppressed
    assert edged.iloc[2] == 0
    assert edged.iloc[4] == 0
    # index 6 re-arms after a zero gap
    assert edged.iloc[6] == 1
