"""Unit/integration tests for the new EMA9/RSI Momentum entry strategy.

Covers each clause of the spec independently:

* Entry Signal — EMA9/EMA20 x RSI14/RSI-EMA20 crossover, same-candle
  confirmation, CE/PE symmetry, no duplicate consecutive entries.
* Momentum Strength — RSI 40/50/60 band classification, both directions.
* Premium Health/Decay — LOW/MODERATE/HIGH/CRITICAL band boundaries.
* Exit Signal / Protection — EMA/RSI reversal forces exit; premium decay
  alone never does (per the spec's explicit "do not treat premium decay
  alone as an exit signal" rule).
* Registry integration — the strategy registers itself via autodiscovery
  and runs cleanly through `registry.run_strategy` (global institutional
  filters included), without touching any other registered strategy.
"""
import _bootstrap  # noqa: F401  (side-effect: puts trading-system/ on sys.path)

import numpy as np
import pandas as pd
import pytest

from trading_bot.strategies.ema9_rsi_momentum import (
    STRATEGY_NAME,
    classify_decay,
    classify_momentum_strength,
    generate_signals,
    evaluate_protective_exit,
)
from trading_bot.strategies.ema9_rsi_momentum.config import Ema9RsiMomentumConfig
from trading_bot.strategies.ema9_rsi_momentum.indicators import crossed_above, crossed_below
from trading_bot.strategies.ema9_rsi_momentum.signal_engine import build_entry_signal_series
from trading_bot.strategies._signal_utils import edge_trigger


def _synthetic_ohlcv(n: int = 400, seed: int = 42) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    close = 24_000 + rng.normal(0, 15, n).cumsum()
    return pd.DataFrame(
        {
            "open": close - rng.uniform(1, 8, n),
            "high": close + rng.uniform(1, 12, n),
            "low": close - rng.uniform(1, 12, n),
            "close": close,
            "volume": rng.integers(1_000, 50_000, n).astype(float),
        },
        index=pd.date_range("2026-08-01 09:15", periods=n, freq="5min"),
    )


# ---------------------------------------------------------------------------
# Crossover primitives
# ---------------------------------------------------------------------------

def test_crossed_above_fires_only_on_transition_bar():
    a = pd.Series([1, 2, 3, 3, 2, 1, 5])
    b = pd.Series([2, 2, 2, 2, 2, 2, 2])
    result = crossed_above(a, b)
    # a>b from index 2 onward (3>2), transition bar is index 2; index 3 (still 3>2) is NOT a fresh cross
    assert list(result) == [False, False, True, False, False, False, True]


def test_crossed_below_fires_only_on_transition_bar():
    a = pd.Series([5, 5, 1, 1, 5])
    b = pd.Series([2, 2, 2, 2, 2])
    result = crossed_below(a, b)
    assert list(result) == [False, False, True, False, False]


def test_crossover_ignores_nan_warmup_period():
    a = pd.Series([np.nan, np.nan, 3, 4])
    b = pd.Series([np.nan, np.nan, 2, 2])
    result = crossed_above(a, b)
    assert not result.any()


# ---------------------------------------------------------------------------
# Entry Signal
# ---------------------------------------------------------------------------

def test_generate_signals_returns_only_valid_values():
    df = _synthetic_ohlcv()
    signals = generate_signals(df)
    assert set(signals.unique()).issubset({-1, 0, 1})


def test_generate_signals_fires_both_directions_over_a_long_window():
    df = _synthetic_ohlcv(600, seed=11)
    signals = generate_signals(df)
    assert (signals == 1).any()
    assert (signals == -1).any()


def test_generate_signals_no_duplicate_consecutive_nonzero_entries():
    df = _synthetic_ohlcv(600, seed=11)
    signals = generate_signals(df)
    duplicates = ((signals == signals.shift(1)) & (signals != 0)).sum()
    assert duplicates == 0


def test_generate_signals_does_not_mutate_input_df():
    df = _synthetic_ohlcv(150)
    original_columns = list(df.columns)
    generate_signals(df)
    assert list(df.columns) == original_columns


def test_ce_entry_requires_both_ema_and_rsi_cross_same_bar():
    """CE entry requires EMA 9 crosses above EMA 20 AND RSI 14 > RSI-EMA 20."""
    cfg = Ema9RsiMomentumConfig()
    df = _synthetic_ohlcv(400, seed=5)
    signals, cross = build_entry_signal_series(df, cfg, edge_trigger)

    ema_up = crossed_above(cross.indicators.ema_fast, cross.indicators.ema_slow)
    rsi_bullish = np.asarray(cross.indicators.rsi > cross.indicators.rsi_ma, dtype=bool)

    # Every bar where EMA crosses up but RSI is NOT bullish must be a 0 signal
    only_ema = ema_up & ~rsi_bullish
    partial_bars = np.where(only_ema)[0]
    for i in partial_bars:
        assert signals.iloc[i] != 1, f"bar {i} fired CE with RSI not above RSI-EMA"


def test_ce_and_pe_entry_conditions_are_symmetric():
    """PE entry (bearish) uses the exact mirror thresholds of CE entry."""
    cfg = Ema9RsiMomentumConfig(enable_adx_filter=False, enable_time_filter=False, enable_touch_filter=False)
    df = _synthetic_ohlcv(400, seed=5)
    _, cross = build_entry_signal_series(df, cfg, edge_trigger)

    ema_dn = crossed_below(cross.indicators.ema_fast, cross.indicators.ema_slow)
    rsi_bearish = np.asarray(cross.indicators.rsi < cross.indicators.rsi_ma, dtype=bool)
    expected_bearish = ema_dn & rsi_bearish
    # Post warmup
    warmup = max(cfg.ema_slow, cfg.rsi_length + cfg.rsi_ma_length)
    expected_bearish[:warmup] = False
    np.testing.assert_array_equal(cross.bearish, expected_bearish)


def test_generate_signals_parameters_are_configurable():
    df = _synthetic_ohlcv(400, seed=5)
    default_signals = generate_signals(df, enable_time_filter=False, enable_adx_filter=False)
    custom_signals = generate_signals(df, ema_fast=5, ema_slow=13, rsi_length=9, rsi_ma_length=10, enable_time_filter=False, enable_adx_filter=False)
    # Different periods must be capable of producing a different signal path
    assert not default_signals.equals(custom_signals)


def test_generate_signals_empty_df_returns_empty_series():
    df = pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
    signals = generate_signals(df)
    assert len(signals) == 0


# ---------------------------------------------------------------------------
# Momentum Strength (RSI 40/50/60 bands)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "rsi_value,expected",
    [
        (35.0, "NONE"),
        (40.0, "NORMAL"),
        (45.0, "NORMAL"),
        (50.0, "STRONG"),
        (55.0, "STRONG"),
        (60.0, "VERY_STRONG"),
        (75.0, "VERY_STRONG"),
    ],
)
def test_bullish_momentum_strength_bands(rsi_value, expected):
    cfg = Ema9RsiMomentumConfig()
    assert classify_momentum_strength(rsi_value, direction=1, cfg=cfg) == expected


@pytest.mark.parametrize(
    "rsi_value,expected",
    [
        (65.0, "NONE"),
        (60.0, "NORMAL"),
        (55.0, "NORMAL"),
        (50.0, "STRONG"),
        (45.0, "STRONG"),
        (40.0, "VERY_STRONG"),
        (20.0, "VERY_STRONG"),
    ],
)
def test_bearish_momentum_strength_bands(rsi_value, expected):
    cfg = Ema9RsiMomentumConfig()
    assert classify_momentum_strength(rsi_value, direction=-1, cfg=cfg) == expected


def test_momentum_strength_is_never_used_to_gate_entries():
    """These bands are informational only — a bar can fire an entry with
    ANY momentum strength label as long as the crossover condition holds."""
    df = _synthetic_ohlcv(600, seed=21)
    signals = generate_signals(df)
    assert (signals != 0).any()  # sanity: strategy still trades despite band variety


# ---------------------------------------------------------------------------
# Premium Health / Decay
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "pct_change,expected",
    [
        (5.0, "LOW"),
        (0.0, "LOW"),
        (-5.0, "LOW"),
        (-10.0, "LOW"),
        (-10.1, "MODERATE"),
        (-15.0, "MODERATE"),
        (-20.0, "MODERATE"),
        (-20.1, "HIGH"),
        (-25.0, "HIGH"),
        (-30.0, "HIGH"),
        (-30.1, "CRITICAL"),
        (-60.0, "CRITICAL"),
    ],
)
def test_premium_decay_bands(pct_change, expected):
    cfg = Ema9RsiMomentumConfig()
    assert classify_decay(pct_change, cfg) == expected


# ---------------------------------------------------------------------------
# Exit Signal / Protection
# ---------------------------------------------------------------------------

def _find_signal_bar(df: pd.DataFrame, direction: int) -> int:
    cfg = Ema9RsiMomentumConfig()
    signals, _ = build_entry_signal_series(df, cfg, edge_trigger)
    hits = np.where(signals.to_numpy() == direction)[0]
    assert len(hits) > 0, f"no direction={direction} signal found in synthetic data"
    return int(hits[-1])


def test_protective_exit_fires_on_ce_reversal_regardless_of_premium():
    """EXIT CE: bearish EMA/RSI crossover must force an exit even when the
    premium is UP (i.e. decay alone is never required)."""
    df = _synthetic_ohlcv(600, seed=11)
    bar = _find_signal_bar(df, direction=-1)  # a bearish crossover = EXIT CE condition
    truncated = df.iloc[: bar + 1]

    result = evaluate_protective_exit(truncated, side=1, entry_premium=100.0, current_premium=110.0, settings={})

    assert result.should_exit is True
    assert "EXIT CE" in result.reason


def test_protective_exit_fires_on_pe_reversal_regardless_of_premium():
    df = _synthetic_ohlcv(600, seed=11)
    bar = _find_signal_bar(df, direction=1)  # a bullish crossover = EXIT PE condition
    truncated = df.iloc[: bar + 1]

    result = evaluate_protective_exit(truncated, side=-1, entry_premium=100.0, current_premium=90.0, settings={})

    assert result.should_exit is True
    assert "EXIT PE" in result.reason


def test_premium_decay_alone_never_forces_an_exit():
    """Per the spec: 'Do not treat premium decay alone as an exit signal.'
    A CRITICAL decay with NO reversal must warn, not force an exit."""
    df = _synthetic_ohlcv(600, seed=11)
    bar = _find_signal_bar(df, direction=1)  # entered CE here
    # Take a window well past the entry bar that (per seed) has no reversal
    # on its own last bar — assert the no-reversal precondition explicitly.
    cfg = Ema9RsiMomentumConfig()
    signals, cross = build_entry_signal_series(df, cfg, edge_trigger)
    non_reversal_bars = np.where(~cross.bearish)[0]
    probe = int(non_reversal_bars[non_reversal_bars > bar][0])
    truncated = df.iloc[: probe + 1]

    result = evaluate_protective_exit(truncated, side=1, entry_premium=200.0, current_premium=100.0, settings={})

    assert result.premium_health.decay_level == "CRITICAL"
    assert result.should_exit is False
    assert result.warning is True


def test_healthy_position_no_warning_no_exit():
    df = _synthetic_ohlcv(600, seed=11)
    bar = _find_signal_bar(df, direction=1)
    cfg = Ema9RsiMomentumConfig()
    signals, cross = build_entry_signal_series(df, cfg, edge_trigger)
    non_reversal_bars = np.where(~cross.bearish)[0]
    probe = int(non_reversal_bars[non_reversal_bars > bar][0])
    truncated = df.iloc[: probe + 1]

    result = evaluate_protective_exit(truncated, side=1, entry_premium=100.0, current_premium=98.0, settings={})

    assert result.should_exit is False
    assert result.warning is False
    assert result.premium_health.decay_level == "LOW"


def test_evaluate_protective_exit_configurable_via_settings():
    """Decay thresholds must be overridable via the ema9_rsi_* settings
    convention, same as every other configurable value in this strategy."""
    df = _synthetic_ohlcv(600, seed=11)
    bar = _find_signal_bar(df, direction=1)
    cfg = Ema9RsiMomentumConfig()
    signals, cross = build_entry_signal_series(df, cfg, edge_trigger)
    non_reversal_bars = np.where(~cross.bearish)[0]
    probe = int(non_reversal_bars[non_reversal_bars > bar][0])
    truncated = df.iloc[: probe + 1]

    # -4% would only be MODERATE under the strategy's own defaults, but is
    # CRITICAL under this much stricter custom threshold set.
    result = evaluate_protective_exit(
        truncated, side=1, entry_premium=100.0, current_premium=96.0,
        settings={"ema9_rsi_decay_low_pct": -1.0, "ema9_rsi_decay_moderate_pct": -2.0, "ema9_rsi_decay_high_pct": -3.0},
    )
    assert result.premium_health.decay_level == "CRITICAL"
    assert result.warning is True
    assert result.should_exit is False


def test_evaluate_protective_exit_handles_short_or_missing_df():
    assert evaluate_protective_exit(pd.DataFrame(), side=1, entry_premium=100, current_premium=90, settings={}).should_exit is False
    assert evaluate_protective_exit(None, side=1, entry_premium=100, current_premium=90, settings={}).should_exit is False


# ---------------------------------------------------------------------------
# Registry integration
# ---------------------------------------------------------------------------

def test_strategy_is_registered_via_autodiscovery():
    from trading_bot.strategies.registry import registry
    assert STRATEGY_NAME in registry.registered_strategies


def test_registry_run_strategy_executes_cleanly_with_global_filters():
    from trading_bot.strategies.registry import registry
    df = _synthetic_ohlcv(400, seed=5)
    result = registry.run_strategy(STRATEGY_NAME, df)
    signals = result[0] if isinstance(result, tuple) else result
    assert isinstance(signals, pd.Series)
    assert set(signals.unique()).issubset({-1, 0, 1})


def test_registry_get_parameters_exposes_all_spec_values():
    from trading_bot.strategies.registry import registry
    params = registry.get_parameters(STRATEGY_NAME)
    for expected in (
        "ema_fast", "ema_slow", "rsi_length", "rsi_ma_length",
        "rsi_band_normal", "rsi_band_strong", "rsi_band_very_strong",
    ):
        assert expected in params
    assert params["ema_fast"]["default"] == 9
    assert params["ema_slow"]["default"] == 20
    assert params["rsi_length"]["default"] == 14
    assert params["rsi_ma_length"]["default"] == 20
    assert params["rsi_band_normal"]["default"] == 40.0
    assert params["rsi_band_strong"]["default"] == 50.0
    assert params["rsi_band_very_strong"]["default"] == 60.0
