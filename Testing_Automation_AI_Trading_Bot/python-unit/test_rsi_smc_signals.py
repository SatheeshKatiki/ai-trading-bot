"""Tier 2 -- the entry rules.

The load-bearing test here is the holdout: removing any ONE mandatory
condition must leave zero signals. That is what makes "RSI is confirmation
only" a structural property rather than a claim in a docstring, and it is
written so that a condition added later is covered automatically (the
parametrisation reads `Conditions.BULL_FIELDS` / `BEAR_FIELDS`).
"""
from __future__ import annotations

import dataclasses
import pathlib

import numpy as np
import pandas as pd
import pytest

import _bootstrap  # noqa: F401

import trading_bot.strategies.rsi_smc_options_buyer as strategy
from trading_bot.strategies.rsi_smc_options_buyer import signal_engine, structure
from trading_bot.strategies.rsi_smc_options_buyer.config import RsiSmcConfig

FIXTURE = (pathlib.Path(__file__).resolve().parent / "fixtures" / "data"
           / "rsi_smc_NIFTY_5Min.csv")


@pytest.fixture(scope="module")
def nifty() -> pd.DataFrame:
    return pd.read_csv(FIXTURE, parse_dates=["datetime"]).set_index("datetime")


@pytest.fixture(autouse=True)
def _clean():
    structure.clear_cache()
    yield
    structure.clear_cache()


def _all_true(n: int) -> np.ndarray:
    return np.ones(n, dtype=bool)


def _conditions(n: int, **overrides) -> signal_engine.Conditions:
    """A Conditions object with every field True unless overridden."""
    values = {f.name: _all_true(n) for f in dataclasses.fields(signal_engine.Conditions)}
    values.update(overrides)
    return signal_engine.Conditions(**values)


# ---------------------------------------------------------------------
# compose(): the pure AND
# ---------------------------------------------------------------------

def test_valid_ce_setup_produces_a_call_signal():
    n = 10
    conditions = _conditions(n, htf_bear=np.zeros(n, dtype=bool))
    assert (signal_engine.compose(conditions) == 1).all()


def test_valid_pe_setup_produces_a_put_signal():
    n = 10
    conditions = _conditions(n, htf_bull=np.zeros(n, dtype=bool))
    assert (signal_engine.compose(conditions) == -1).all()


@pytest.mark.parametrize("held_out", signal_engine.Conditions.BULL_FIELDS)
def test_holding_out_any_bullish_condition_removes_every_ce_signal(held_out):
    """Each mandatory condition is genuinely mandatory."""
    n = 10
    conditions = _conditions(
        n, htf_bear=np.zeros(n, dtype=bool), **{held_out: np.zeros(n, dtype=bool)})
    assert not (signal_engine.compose(conditions) == 1).any(), (
        f"a CE signal survived without {held_out}")


@pytest.mark.parametrize("held_out", signal_engine.Conditions.BEAR_FIELDS)
def test_holding_out_any_bearish_condition_removes_every_pe_signal(held_out):
    n = 10
    conditions = _conditions(
        n, htf_bull=np.zeros(n, dtype=bool), **{held_out: np.zeros(n, dtype=bool)})
    assert not (signal_engine.compose(conditions) == -1).any(), (
        f"a PE signal survived without {held_out}")


def test_rsi_alone_produces_nothing():
    """RSI is CONFIRMATION ONLY.

    Everything structural absent, RSI maximally bullish: zero signals. This
    is the specification's hard requirement -- RSI must never independently
    trigger a trade.
    """
    n = 10
    false = np.zeros(n, dtype=bool)
    conditions = _conditions(
        n,
        htf_bull=false.copy(), htf_bear=false.copy(),
        regime_ok=false.copy(),
        level_near_bull=false.copy(), level_near_bear=false.copy(),
        sweep_bull=false.copy(), sweep_bear=false.copy(),
        struct_bull=false.copy(), struct_bear=false.copy(),
        trigger_bull=false.copy(), trigger_bear=false.copy(),
        rr_ok_bull=false.copy(), rr_ok_bear=false.copy(),
        rsi_bull=_all_true(n), rsi_bear=_all_true(n),
    )
    assert (signal_engine.compose(conditions) == 0).all()


def test_sweep_without_structure_confirmation_produces_nothing():
    n = 10
    conditions = _conditions(
        n, htf_bear=np.zeros(n, dtype=bool), struct_bull=np.zeros(n, dtype=bool))
    assert (signal_engine.compose(conditions) == 0).all()


def test_structure_without_a_sweep_produces_nothing():
    n = 10
    conditions = _conditions(
        n, htf_bear=np.zeros(n, dtype=bool), sweep_bull=np.zeros(n, dtype=bool))
    assert (signal_engine.compose(conditions) == 0).all()


def test_failing_conditions_names_what_was_missing():
    n = 4
    conditions = _conditions(n, sweep_bull=np.zeros(n, dtype=bool))
    assert "sweep_bull" in signal_engine.failing_conditions(conditions, 0, 1)
    assert "sweep_bull" not in signal_engine.failing_conditions(conditions, 0, -1)


# ---------------------------------------------------------------------
# RSI confirmation is a state, not an event
# ---------------------------------------------------------------------

def test_rsi_confirmation_requires_both_midline_and_moving_average(nifty):
    cfg = RsiSmcConfig()
    bull, bear, rsi, rsi_ma = signal_engine.rsi_confirmation(nifty, cfg)
    assert np.all(rsi[bull] > cfg.rsi_midline)
    assert np.all(rsi[bull] > rsi_ma[bull])
    assert np.all(rsi[bear] < cfg.rsi_midline)
    assert np.all(rsi[bear] < rsi_ma[bear])
    assert not (bull & bear).any()


# ---------------------------------------------------------------------
# HTF bias
# ---------------------------------------------------------------------

def test_htf_bias_never_uses_the_forming_bucket(nifty):
    """Bar i must read the PREVIOUS completed higher-timeframe bucket.

    Appending bars to the CURRENT bucket must not change the bias already
    reported for earlier bars in it.
    """
    cfg = RsiSmcConfig()
    bull_full, bear_full = signal_engine.htf_bias(nifty, cfg)
    cut = len(nifty) - 2
    bull_part, bear_part = signal_engine.htf_bias(nifty.iloc[:cut], cfg)
    np.testing.assert_array_equal(bull_full[:cut], bull_part)
    np.testing.assert_array_equal(bear_full[:cut], bear_part)


def test_htf_bias_is_exclusive(nifty):
    bull, bear = signal_engine.htf_bias(nifty, RsiSmcConfig())
    assert not (bull & bear).any()


def test_htf_bias_without_a_datetime_index_is_empty():
    frame = pd.DataFrame({
        "open": [1.0] * 50, "high": [2.0] * 50, "low": [0.5] * 50,
        "close": [1.5] * 50, "volume": [1] * 50,
    })
    bull, bear = signal_engine.htf_bias(frame, RsiSmcConfig())
    assert not bull.any() and not bear.any()


# ---------------------------------------------------------------------
# Whole-strategy behaviour on real data
# ---------------------------------------------------------------------

def test_signals_are_edge_triggered(nifty):
    """No run of identical consecutive non-zero signals."""
    signals = strategy.generate_signals(nifty).to_numpy()
    repeated = (signals[1:] == signals[:-1]) & (signals[1:] != 0)
    assert not repeated.any()


def test_signal_series_shape_and_domain(nifty):
    signals = strategy.generate_signals(nifty)
    assert len(signals) == len(nifty)
    assert signals.index.equals(nifty.index)
    assert set(np.unique(signals.to_numpy())) <= {-1, 0, 1}


def test_unsupported_instrument_produces_nothing(nifty):
    """An equity symbol must never reach main.py's entry path from here.

    `option_mapping_required` there is False for a non-index symbol, so the
    trade would be taken as EQUITY -- a different instrument class than this
    options-buying strategy was designed or risk-modelled for.
    """
    signals = strategy.generate_signals(nifty, symbol="NSE:RELIANCE-EQ")
    assert (signals == 0).all()

    # Also via the configured symbol set, which is how main.py calls it.
    signals = strategy.generate_signals(nifty, symbols=["NSE:RELIANCE-EQ"])
    assert (signals == 0).all()

    # A mixed set is unverifiable from inside the registry contract, so it
    # must be refused rather than guessed.
    signals = strategy.generate_signals(
        nifty, symbols=["NSE:NIFTY50-INDEX", "NSE:TCS-EQ"])
    assert (signals == 0).all()


@pytest.mark.parametrize("symbol", ["NSE:NIFTY50-INDEX", "BSE:SENSEX-INDEX",
                                    "NSE:NIFTYBANK-INDEX", "NSE:FINNIFTY-INDEX"])
def test_supported_index_instruments_are_allowed(nifty, symbol):
    cfg = RsiSmcConfig()
    assert cfg.instrument_allowed(symbol)


def test_empty_and_malformed_frames_do_not_raise():
    assert strategy.generate_signals(pd.DataFrame()).empty
    assert strategy.generate_signals(None).empty
    frame = pd.DataFrame({"open": [1.0], "high": [1.0], "low": [1.0], "volume": [1]})
    assert strategy.generate_signals(frame).empty


def test_generate_signals_never_raises_on_broken_internals(nifty, monkeypatch):
    """Failure isolation: a raising internal must yield zeros, not an
    exception that the tick loop has to absorb."""
    def boom(*args, **kwargs):
        raise RuntimeError("deliberate")

    monkeypatch.setattr(signal_engine, "build", boom)
    signals = strategy.generate_signals(nifty)
    assert len(signals) == len(nifty)
    assert (signals == 0).all()
