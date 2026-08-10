"""Unit tests for `momentum_15_5`'s entry rules.

Each test pins one clause of the specification, or one failure class this
repository has actually suffered (look-ahead, forming-bar semantics,
churn, silent zero-signal conditions).
"""
import _bootstrap  # noqa: F401  (side-effect: puts trading-system/ on sys.path)

import numpy as np
import pandas as pd
import pytest

from trading_bot.strategies.momentum_15_5 import (
    ADX_MIN,
    CONFIRM_WINDOW,
    MIN_DTE,
    RSI_MIDLINE,
    STRATEGY_NAME,
    generate_signals,
)

# 2026-03-20 is a Friday: nearest NIFTY weekly expiry is Tuesday
# 2026-03-24, i.e. 4 DTE, so the DTE gate is open.
ELIGIBLE_DAY = "2026-03-20"
#: 2026-03-17 is a Tuesday — expiry day, 0 DTE, gate closed.
EXPIRY_DAY = "2026-03-17"


def _session(closes, date=ELIGIBLE_DAY, spread=6.0, start="09:15"):
    idx = pd.date_range(f"{date} {start}", periods=len(closes), freq="5min")
    c = np.asarray(closes, dtype=float)
    return pd.DataFrame(
        {"open": c, "high": c + spread, "low": c - spread, "close": c,
         "volume": np.full(len(c), 2e5)},
        index=idx,
    )


def _thrust(seed, slope, sign=1, base_bars=120, thrust_bars=140):
    """A settled, choppy base followed by a sharp sustained thrust.

    A plain linear ramp is NOT usable as a fixture: its only EMA9/20
    crossover happens at bar ~2, inside indicator warm-up, so nothing can
    confirm. More importantly, the specification requires the RSI/RSI-EMA
    cross to land within +/-1 candle of the price crossover, and measured
    on the real development window that coincidence happens for only
    16.3% of crossovers (median lag +16 candles). So a fixture has to be
    a genuine sharp reversal, and the specific (seed, slope) pairs below
    were verified to produce exactly the specified condition sequence
    rather than assumed to.
    """
    rng = np.random.default_rng(seed)
    base = 24_000.0 + rng.normal(0, 10, base_bars).cumsum() * 0.3
    tail = base[-1] + sign * np.arange(1, thrust_bars + 1) * slope + rng.normal(0, 2.0, thrust_bars)
    return np.r_[base, tail]


#: Verified fixtures — each fires exactly one signal under the literal rule.
CE_FIXTURE = dict(seed=28, slope=12.0, sign=1)
PE_FIXTURE = dict(seed=10, slope=6.0, sign=-1)
BOTH_FIXTURE = dict(seed=34, slope=9.0, sign=1)   # one CE and one PE


def _uptrend(n=260, base=24_000.0, slope=4.0, seed=3, noise=1.5):
    """A plain ramp — used only where the test needs a trend WITHOUT
    expecting a signal (warm-up, contract, degenerate-input cases)."""
    rng = np.random.default_rng(seed)
    return base + np.arange(n) * slope + rng.normal(0, noise, n)


def _chop(n=260, base=24_000.0, amp=8.0, seed=5):
    rng = np.random.default_rng(seed)
    return base + amp * np.sin(np.arange(n) / 3.0) + rng.normal(0, 1.0, n)


# ─────────────────────────────────────────────────────────────────────
# Core rule behaviour
# ─────────────────────────────────────────────────────────────────────

def test_sharp_bullish_reversal_produces_a_call_signal():
    sig = generate_signals(_session(_thrust(**CE_FIXTURE)))
    assert (sig == 1).sum() == 1
    assert (sig == -1).sum() == 0


def test_sharp_bearish_reversal_produces_a_put_signal():
    sig = generate_signals(_session(_thrust(**PE_FIXTURE)))
    assert (sig == -1).sum() == 1
    assert (sig == 1).sum() == 0


def test_choppy_session_with_no_trend_produces_nothing_or_very_little():
    """ADX>20-and-rising plus the 15-min bias should mostly refuse chop."""
    sig = generate_signals(_session(_chop()))
    assert (sig != 0).sum() <= 2


# ─────────────────────────────────────────────────────────────────────
# Event semantics and duplicate prevention
# ─────────────────────────────────────────────────────────────────────

def test_one_entry_per_direction_per_session():
    """A sustained trend keeps every level condition true for hundreds of
    bars. The crossover is the event, so only the first counts."""
    sig = generate_signals(_session(_thrust(**CE_FIXTURE, thrust_bars=260)))
    assert (sig == 1).sum() == 1


def test_opposite_direction_is_still_allowed_in_the_same_session():
    """Duplicate suppression must not swallow a genuine reversal."""
    sig = generate_signals(_session(_thrust(**BOTH_FIXTURE)))
    assert (sig == 1).sum() == 1
    assert (sig == -1).sum() == 1


def test_each_session_is_independent():
    a = _session(_thrust(**CE_FIXTURE), date="2026-03-19")   # Thursday, 5 DTE
    b = _session(_thrust(**CE_FIXTURE), date=ELIGIBLE_DAY)   # Friday, 4 DTE
    sig = generate_signals(pd.concat([a, b]))
    nz = sig[sig != 0]
    # The rule is one entry per DIRECTION per session, so a day may
    # legitimately carry one CE and one PE.
    per_day_dir = nz.groupby([nz.index.normalize(), nz]).count()
    assert (per_day_dir <= 1).all()
    assert len(nz) >= 1


def test_confirmation_window_is_bounded():
    """A crossover whose conditions never confirm inside the window must
    not fire later — that would make it a level trigger again."""
    src = _session(_thrust(**CE_FIXTURE))
    sig = generate_signals(src)
    assert (sig == 1).sum() == 1
    entry = int(np.flatnonzero(sig.to_numpy() == 1)[0])
    ema_f = src["close"].ewm(span=9, adjust=False).mean().to_numpy()
    ema_s = src["close"].ewm(span=20, adjust=False).mean().to_numpy()
    above = ema_f > ema_s
    crosses = np.flatnonzero(np.r_[False, above[1:] & ~above[:-1]])
    nearest = crosses[crosses <= entry].max()
    # entry = j+1 where j <= k + CONFIRM_WINDOW - 1
    assert entry - nearest <= CONFIRM_WINDOW


# ─────────────────────────────────────────────────────────────────────
# No look-ahead / live-backtest identity
# ─────────────────────────────────────────────────────────────────────

def test_signals_do_not_depend_on_future_bars():
    """Truncating the future must never change an already-emitted signal.
    This is what makes the +/-1 candle RSI tolerance safe."""
    src = _session(_thrust(**CE_FIXTURE))
    full = generate_signals(src)
    for cut in range(120, len(src)):
        prefix = generate_signals(src.iloc[:cut])
        pd.testing.assert_series_equal(
            prefix, full.iloc[:cut], check_names=False,
            obj=f"signals changed when truncated at bar {cut}",
        )


def test_signal_lands_after_the_confirming_candle_not_on_it():
    """Live reads `signals.iloc[-1]` on the forming bar, so a signal must
    never be keyed to the candle whose close confirmed it."""
    src = _session(_thrust(**CE_FIXTURE))
    sig = generate_signals(src).to_numpy()
    assert (sig == 1).sum() == 1
    entry = int(np.flatnonzero(sig == 1)[0])
    assert entry >= 1
    # The bar before the entry is the confirmation bar; the entry bar's
    # own close plays no part in the decision.
    assert sig[entry - 1] == 0


# ─────────────────────────────────────────────────────────────────────
# DTE gate
# ─────────────────────────────────────────────────────────────────────

def test_no_signal_on_an_expiry_day_because_dte_gate_is_closed():
    """0 DTE: a day of theta is ~851% of the banded stop. The gate is
    mechanical, not fitted."""
    assert (generate_signals(_session(_thrust(**CE_FIXTURE), date=EXPIRY_DAY)) != 0).sum() == 0


def test_dte_gate_is_configurable_and_defaults_to_two():
    assert MIN_DTE == 2
    relaxed = generate_signals(_session(_thrust(**CE_FIXTURE), date=EXPIRY_DAY), min_dte=0)
    assert (relaxed != 0).sum() >= 1, "gate must be what suppressed it, not the rules"


# ─────────────────────────────────────────────────────────────────────
# Individual conditions are load-bearing
# ─────────────────────────────────────────────────────────────────────

def test_bias_disagreement_blocks_the_entry():
    """A 5-min bullish crossover under a bearish 15-min bias must not
    fire. Built as a long downtrend with a short late bounce: the bounce
    crosses EMA9/20 while the 15-min close is still under its EMA20."""
    down = 24_000.0 - np.arange(220) * 6.0
    bounce = down[-1] + np.arange(24) * 7.0
    sig = generate_signals(_session(np.r_[down, bounce]))
    assert (sig == 1).sum() == 0


def test_adx_is_scale_invariant_and_does_not_gate_on_move_size():
    """DOCUMENTED LIMITATION, encoded rather than hidden.

    I first asserted that a flat tape could not satisfy `ADX > 20 and
    rising`. That is false, and measuring it is the point: over a series
    whose ENTIRE range is 1.67 index points, ADX reaches 100 and exceeds
    20 on 12% of bars, because ADX normalises directional movement by ATR
    and is therefore scale-invariant.

    Consequence for this strategy: the ADX condition filters for
    *directional persistence*, NOT for a move large enough to pay for an
    option's spread and theta. Nothing in the current rule set gates on
    absolute move size. If the entry edge turns out to be weak, this is
    the first place to look — but it must be fixed on evidence, not by
    bolting on a minimum-range filter because it improves a backtest."""
    from shared.indicators import adx as _adx

    flat = np.full(260, 24_000.0) + np.random.default_rng(1).normal(0, 0.3, 260)
    src = _session(flat)
    assert flat.max() - flat.min() < 5.0, "fixture must genuinely be flat"
    assert (_adx(src, 14) > 20).mean() > 0.05, "ADX does exceed 20 on a flat tape"
    # So the strategy is not structurally prevented from signalling here.
    assert (generate_signals(src) != 0).sum() <= 1


def test_thresholds_match_the_specification():
    assert (RSI_MIDLINE, ADX_MIN, CONFIRM_WINDOW) == (50.0, 20.0, 3)


# ─────────────────────────────────────────────────────────────────────
# Contract and robustness
# ─────────────────────────────────────────────────────────────────────

def test_signal_contract():
    sig = generate_signals(_session(_thrust(**CE_FIXTURE)))
    assert isinstance(sig, pd.Series)
    assert sig.dtype == int
    assert set(sig.unique()) <= {-1, 0, 1}


def test_registry_autodiscovers_the_strategy():
    from trading_bot.strategies.registry import registry

    assert STRATEGY_NAME in registry.registered_strategies
    out = registry.run_strategy(STRATEGY_NAME, _session(_thrust(**CE_FIXTURE)))
    assert isinstance(out[0] if isinstance(out, tuple) else out, pd.Series)


@pytest.mark.parametrize("n", [0, 1, 30, 100])
def test_insufficient_history_returns_zeros_not_an_exception(n):
    src = _session(_uptrend(n=n)) if n else _session([])
    sig = generate_signals(src)
    assert len(sig) == n
    assert (sig == 0).all()


def test_missing_columns_raise_rather_than_silently_emitting_nothing():
    src = _session(_thrust(**CE_FIXTURE)).drop(columns=["high"])
    with pytest.raises(KeyError):
        generate_signals(src)


def test_strategy_declares_the_institutional_filters_inapplicable():
    """Phase 2.1 decision. The strategy does not implement these filters,
    it declares them inapplicable — hence SKIP_, not OWNS_. Measured: they
    passed only 4 of 23 signals (17%), the same interaction that reduced
    `institutional_momentum` to zero trades."""
    from trading_bot.strategies import momentum_15_5

    assert not hasattr(momentum_15_5, "OWNS_INSTITUTIONAL_FILTERS"), (
        "this strategy applies no filters itself — OWNS_ would misstate that"
    )
    assert momentum_15_5.SKIP_INSTITUTIONAL_FILTERS == {
        "squeeze", "extension", "cpr", "aggression"
    }


def test_registry_actually_bypasses_the_filters_for_this_strategy():
    """The declaration must have teeth: with every institutional filter
    enabled, the registry output must equal the raw strategy output."""
    from trading_bot.strategies.registry import registry

    src = _session(_thrust(**CE_FIXTURE))
    flags = dict(enable_squeeze_filter=True, enable_extension_filter=True,
                 enable_cpr_filter=True, enable_aggression_filter=True)

    raw = registry._strategies[STRATEGY_NAME](src, **flags)
    raw = (raw[0] if isinstance(raw, tuple) else raw).astype(int)
    via = registry.run_strategy(STRATEGY_NAME, src, **flags)
    via = (via[0] if isinstance(via, tuple) else via).astype(int)

    assert (raw != 0).sum() >= 1, "fixture must produce a signal to test bypass"
    pd.testing.assert_series_equal(via, raw, check_names=False)


def test_rsi_confirmation_is_a_state_test_not_a_cross_event():
    """Phase 2.1: RSI must be on the correct side of its EMA20 at
    confirmation. A strategy still requiring a *fresh cross* within one
    candle would reject the vast majority of setups (measured: 16.3% of
    crossovers coincide; median lag +16 candles)."""
    import inspect

    from trading_bot.strategies import momentum_15_5

    src = inspect.getsource(momentum_15_5.generate_signals)
    assert "rsi_side" in src
    assert not hasattr(momentum_15_5, "RSI_CROSS_TOLERANCE"), (
        "the +/-1 cross tolerance was replaced, not merely widened"
    )
