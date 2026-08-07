"""Regression coverage for the 2026-08-07 meta_agent_swarm finding:
the `institutional_momentum` sub-agent was silently failing on every call.

Root cause: `meta_agent_strategy.py`'s sub-agent loop assigned
`registry._strategies[agent](df, **kwargs)`'s raw return value straight
into a DataFrame column. A sub-agent may return either a bare Series or a
`(signals, rejection_logs)` tuple — `institutional_momentum` returns the
tuple form (momentum_strategy/__init__.py:199); every other registered
sub-agent returns a bare Series. Assigning the tuple raised
"Length of values (2) does not match length of index (N)" on every call,
was swallowed by the loop's broad `except Exception`, logged, and skipped.

Net effect: the swarm ran as a 4-of-5-technical-brain consensus rather
than the documented 5, for its entire production life — a consensus
score threshold (>= 3 / <= -3) tuned for the full vote pool being applied
to a permanently smaller one. Found by executing the strategy under the
Production Strategy Validation Harness, not by reading it.

Fixed by unwrapping the tuple the same way main.py's own entry loop
already does. These tests pin that every listed sub-agent actually
contributes a vote column, and that both return shapes are handled.
"""
import numpy as np
import pandas as pd
import pytest

import _bootstrap  # noqa: F401  (side-effect: puts trading-system/ on sys.path)

from trading_bot.strategies import meta_agent_strategy
from trading_bot.strategies.meta_agent_strategy import generate_signals


def _ohlcv(n: int = 260, seed: int = 5) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    close = 24_000 + rng.normal(0, 12, n).cumsum()
    idx = pd.date_range("2026-06-01 09:15", periods=n, freq="5min")
    return pd.DataFrame({
        "open": close, "high": close + 6, "low": close - 6,
        "close": close, "volume": rng.integers(1_000, 50_000, n).astype(float),
        "datetime": idx,
    }, index=idx)


def test_tuple_returning_subagent_contributes_a_vote(monkeypatch):
    """The exact regression: a sub-agent returning (signals, logs) must
    still land in the vote ledger, not be swallowed as an exception."""
    df = _ohlcv()
    tuple_signals = pd.Series(1, index=df.index, dtype=int)
    series_signals = pd.Series(-1, index=df.index, dtype=int)

    fake_registry = {
        "advanced_ai": lambda d, **k: series_signals,
        # returns a TUPLE, like institutional_momentum really does
        "institutional_momentum": lambda d, **k: (tuple_signals, [{"reason": "x"}]),
        "ema_crossover": lambda d, **k: series_signals,
        "ema_rsi": lambda d, **k: series_signals,
        "enhanced_ai": lambda d, **k: series_signals,
    }
    monkeypatch.setattr(meta_agent_strategy.registry, "_strategies", fake_registry)

    errors = []
    monkeypatch.setattr(
        meta_agent_strategy.logger, "error",
        lambda msg, *a, **k: errors.append(str(msg)),
    )

    generate_signals(df)

    assert not any("institutional_momentum" in e for e in errors), (
        f"tuple-returning sub-agent still failing: {errors}"
    )


def test_all_five_technical_subagents_contribute(monkeypatch):
    """Pins the documented architecture: all 5 technical brains vote.
    Before the fix, only 4 ever did."""
    df = _ohlcv()
    called = []

    def _tracked(name, returns_tuple=False):
        def _fn(d, **k):
            called.append(name)
            sig = pd.Series(1, index=d.index, dtype=int)
            return (sig, []) if returns_tuple else sig
        return _fn

    fake_registry = {
        "advanced_ai": _tracked("advanced_ai"),
        "institutional_momentum": _tracked("institutional_momentum", returns_tuple=True),
        "ema_crossover": _tracked("ema_crossover"),
        "ema_rsi": _tracked("ema_rsi"),
        "enhanced_ai": _tracked("enhanced_ai"),
    }
    monkeypatch.setattr(meta_agent_strategy.registry, "_strategies", fake_registry)

    errors = []
    monkeypatch.setattr(
        meta_agent_strategy.logger, "error",
        lambda msg, *a, **k: errors.append(str(msg)),
    )

    generate_signals(df)

    assert set(called) == set(fake_registry.keys())
    assert not errors, f"no sub-agent should error: {errors}"


def test_a_genuinely_broken_subagent_is_still_isolated(monkeypatch):
    """The broad except must still contain a real failure — one bad
    sub-agent cannot take down the whole swarm."""
    df = _ohlcv()
    good = pd.Series(1, index=df.index, dtype=int)

    def _explodes(d, **k):
        raise RuntimeError("genuinely broken")

    fake_registry = {
        "advanced_ai": lambda d, **k: good,
        "institutional_momentum": _explodes,
        "ema_crossover": lambda d, **k: good,
        "ema_rsi": lambda d, **k: good,
        "enhanced_ai": lambda d, **k: good,
    }
    monkeypatch.setattr(meta_agent_strategy.registry, "_strategies", fake_registry)

    result = generate_signals(df)  # must not raise
    assert isinstance(result, pd.Series)
    assert len(result) == len(df)


def test_output_is_a_valid_signal_series(monkeypatch):
    df = _ohlcv()
    sig = pd.Series(1, index=df.index, dtype=int)
    fake_registry = {
        "advanced_ai": lambda d, **k: sig,
        "institutional_momentum": lambda d, **k: (sig, []),
        "ema_crossover": lambda d, **k: sig,
        "ema_rsi": lambda d, **k: sig,
        "enhanced_ai": lambda d, **k: sig,
    }
    monkeypatch.setattr(meta_agent_strategy.registry, "_strategies", fake_registry)

    result = generate_signals(df)
    assert isinstance(result, pd.Series)
    assert set(result.unique()) <= {-1, 0, 1}
