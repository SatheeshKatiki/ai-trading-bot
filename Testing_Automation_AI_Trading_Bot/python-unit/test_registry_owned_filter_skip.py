"""Regression tests for the double-applied institutional-filter defect.

Found 2026-08-09 auditing `institutional_momentum` on the real production
entry path. The strategy took **zero trades across all 123 validation
days** while reporting no error of any kind.

Root cause — one flag, two opposite meanings:

* `momentum_strategy.generate_signals` REQUIRES a recent volatility
  squeeze (`if f_squeeze and not squeeze_recent: reject "Not a fresh
  breakout"`). That is the standard TTM Squeeze reading for a breakout
  system: trade the expansion out of a contraction.
* `shared.filters.institutional.apply_institutional_filters`, which
  `StrategyRegistry.run_strategy` runs on top of every strategy's output,
  VETOES a recent squeeze (`bullish & ~squeeze_mask`). That is the correct
  reading for a non-breakout strategy avoiding chop, and it is measurably
  worth keeping for `ema_rsi`.

Both layers read the same `enable_squeeze_filter` key and compute a
byte-identical mask, so with the flag on (as `config/settings.json` has
it) the surviving set is `A & ~A` — provably empty for ANY input, not
merely usually empty. `institutional_momentum` is also `main.py`'s default
`active_strategy`, so this was reachable without editing anything.

Fixed by letting a strategy declare `OWNS_INSTITUTIONAL_FILTERS`; the
registry then skips those filters for that strategy only. The global
filter's own behaviour is deliberately unchanged — flipping its sign would
destroy a control that is proven valuable for other strategies.

These tests pin the fix from both ends: the general registry mechanism,
and the specific `A & ~A` contradiction that must never come back.
"""
import _bootstrap  # noqa: F401  (side-effect: puts trading-system/ on sys.path)

import sys
import types

import numpy as np
import pandas as pd

from shared.filters.institutional import get_squeeze_mask
from trading_bot.strategies.registry import StrategyRegistry, registry


def _market(bars=300, seed=5):
    """Real intraday-shaped data with a DatetimeIndex — the CPR filter
    needs one, and the squeeze/extension masks need genuine ranges."""
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2026-03-02 09:15", periods=bars, freq="5min")
    close = 24_000 + np.linspace(0, 80, bars) + rng.normal(0, 12, bars).cumsum()
    return pd.DataFrame(
        {"open": close - rng.normal(0, 6, bars),
         "high": close + rng.uniform(2, 25, bars),
         "low": close - rng.uniform(2, 25, bars),
         "close": close,
         "volume": rng.uniform(1e5, 5e5, bars)},
        index=idx,
    )


def _register_in_module(reg, name, func, owns=None):
    """Register `func` as if it were defined in its own strategy module,
    so the registry's module-constant lookup sees what it would see for a
    real strategy package."""
    mod_name = f"_test_strategy_mod_{name}"
    module = types.ModuleType(mod_name)
    if owns is not None:
        module.OWNS_INSTITUTIONAL_FILTERS = owns
    sys.modules[mod_name] = module
    func.__module__ = mod_name
    reg.register(name, func)
    return mod_name


# ─────────────────────────────────────────────────────────────────────
# The specific defect: a strategy REQUIRING what the global layer VETOES
# ─────────────────────────────────────────────────────────────────────

def test_squeeze_requiring_strategy_is_not_annihilated_by_the_global_veto():
    """The exact `institutional_momentum` shape: a strategy that only fires
    inside a squeeze. Without the ownership declaration the global veto
    removes 100% of its signals; with it, every signal survives."""
    df = _market()
    squeeze = get_squeeze_mask(df)
    assert squeeze.any(), "fixture must contain squeezes for this to test anything"

    def _breakout(df, **kwargs):
        # Mirrors momentum_strategy: a signal REQUIRES a recent squeeze.
        sig = pd.Series(0, index=df.index, dtype=int)
        sig[get_squeeze_mask(df)] = 1
        return sig

    reg = StrategyRegistry()
    _register_in_module(reg, "breakout", _breakout, owns={"squeeze"})
    owned = reg.run_strategy("breakout", df, enable_squeeze_filter=True)

    def _breakout_unowned(df, **kwargs):
        sig = pd.Series(0, index=df.index, dtype=int)
        sig[get_squeeze_mask(df)] = 1
        return sig

    reg2 = StrategyRegistry()
    _register_in_module(reg2, "breakout2", _breakout_unowned)
    unowned = reg2.run_strategy("breakout2", df, enable_squeeze_filter=True)

    assert (unowned != 0).sum() == 0, "pre-fix behaviour: the veto annihilates every signal"
    assert (owned != 0).sum() == int(squeeze.sum()), "post-fix: every signal survives"


def _breakout_market(seed=9, ramp=35):
    """A market this strategy will actually trade: a sustained uptrend
    (EMA stack, RSI, VWAP all bullish) followed by consolidation-then-
    breakout episodes, so a Donchian breakout genuinely fires OUT OF a
    volatility squeeze — the exact setup the strategy is built for.

    Hand-built rather than random because a generic random walk produces
    zero `institutional_momentum` signals, which would let the end-to-end
    test below pass while asserting nothing.
    """
    rng = np.random.default_rng(seed)
    n1 = 260
    parts = [24_000 + np.linspace(0, 260, n1) + rng.normal(0, 3, n1)]
    for _ in range(3):
        flat = parts[-1][-1] + rng.normal(0, 1.2, 40)
        parts += [flat, flat[-1] + np.linspace(3, ramp, 18) + rng.normal(0, 1.0, 18)]
    close = np.concatenate(parts)
    n = len(close)
    df = pd.DataFrame(
        {"open": close - rng.normal(0, 1.0, n),
         "high": close + 0.3,          # closes at the high: aggression-compliant
         "low": close - 6.0,
         "close": close,
         "volume": rng.uniform(2e5, 4e5, n)},
        index=pd.date_range("2026-03-02 09:15", periods=n, freq="5min"),
    )
    return df


def test_real_institutional_momentum_emits_signals_with_production_flags():
    """End-to-end against the REAL registered strategy and the real
    production flag combination. This is the assertion that would have
    caught the zero-trade window."""
    df = _breakout_market()
    flags = dict(enable_squeeze_filter=True, enable_extension_filter=True,
                 enable_cpr_filter=True, enable_aggression_filter=True)

    raw = registry._strategies["institutional_momentum"](df, **flags)
    raw_signals = (raw[0] if isinstance(raw, tuple) else raw).astype(int)

    # Guards against a vacuous pass: the strategy must really signal here,
    # and those signals must sit inside a squeeze — which is precisely what
    # made the global veto annihilate them before the fix.
    assert (raw_signals != 0).sum() > 0, "fixture must produce real signals"
    assert get_squeeze_mask(df)[raw_signals != 0].all()

    result = registry.run_strategy("institutional_momentum", df, **flags)
    signals = (result[0] if isinstance(result, tuple) else result).astype(int)

    # The strategy owns all four, so the global layer must be a pure no-op.
    pd.testing.assert_series_equal(signals, raw_signals, check_names=False)
    assert (signals != 0).sum() > 0, "production flags must not zero the strategy"


def test_momentum_declares_ownership_of_the_filters_it_applies_itself():
    """Ownership must match what `generate_signals` actually consumes — a
    filter applied internally but not declared is the defect returning."""
    from trading_bot.strategies import momentum_strategy

    assert momentum_strategy.OWNS_INSTITUTIONAL_FILTERS == {
        "squeeze", "extension", "cpr", "aggression"
    }


# ─────────────────────────────────────────────────────────────────────
# The general mechanism, and its blast radius
# ─────────────────────────────────────────────────────────────────────

def test_strategy_declaring_nothing_is_bit_identical_to_before():
    """The default path must be untouched: a strategy with no declaration
    still gets every enabled global filter, exactly as it did before."""
    df = _market(seed=13)

    def _alternating(df, **kwargs):
        sig = pd.Series(0, index=df.index, dtype=int)
        sig.iloc[::3] = 1
        sig.iloc[1::3] = -1
        return sig

    reg = StrategyRegistry()
    _register_in_module(reg, "plain", _alternating)

    flags = dict(enable_squeeze_filter=True, enable_extension_filter=True,
                 enable_cpr_filter=True, enable_aggression_filter=True)
    filtered = reg.run_strategy("plain", df, **flags)
    unfiltered = reg.run_strategy("plain", df)

    # Something must actually have been filtered, or this proves nothing.
    assert (filtered != 0).sum() < (unfiltered != 0).sum()


def test_only_the_declared_filters_are_skipped():
    """Declaring one filter must not disable the other three."""
    df = _market(seed=21)

    def _all_bull(df, **kwargs):
        return pd.Series(1, index=df.index, dtype=int)

    reg = StrategyRegistry()
    _register_in_module(reg, "owns_squeeze", _all_bull, owns={"squeeze"})

    only_squeeze = reg.run_strategy("owns_squeeze", df, enable_squeeze_filter=True)
    assert (only_squeeze != 0).all(), "the owned filter must be skipped entirely"

    plus_aggression = reg.run_strategy(
        "owns_squeeze", df, enable_squeeze_filter=True, enable_aggression_filter=True
    )
    assert (plus_aggression != 0).sum() < len(df), "an undeclared filter must still apply"


def test_ownership_is_inert_when_the_flag_is_off():
    """Skipping a filter that was never going to run must change nothing."""
    df = _market(seed=33)

    def _alternating(df, **kwargs):
        sig = pd.Series(0, index=df.index, dtype=int)
        sig.iloc[::4] = 1
        sig.iloc[2::4] = -1
        return sig

    reg_owned = StrategyRegistry()
    _register_in_module(reg_owned, "o", _alternating, owns={"squeeze", "cpr"})
    reg_plain = StrategyRegistry()
    _register_in_module(reg_plain, "p", _alternating)

    pd.testing.assert_series_equal(
        reg_owned.run_strategy("o", df).astype(int),
        reg_plain.run_strategy("p", df).astype(int),
        check_names=False,
    )


def test_tuple_returning_strategy_keeps_its_rejection_logs():
    """`institutional_momentum` returns `(signals, rejection_logs)`; the
    ownership branch must not disturb that contract."""
    df = _market(seed=41)

    def _with_logs(df, **kwargs):
        return pd.Series(1, index=df.index, dtype=int), [{"reason": "x"}]

    reg = StrategyRegistry()
    _register_in_module(reg, "tup", _with_logs, owns={"squeeze"})
    result = reg.run_strategy("tup", df, enable_squeeze_filter=True)

    assert isinstance(result, tuple)
    signals, logs = result
    assert logs == [{"reason": "x"}]
    assert (signals != 0).all()
