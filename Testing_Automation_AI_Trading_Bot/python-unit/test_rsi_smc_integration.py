"""Tier 3 -- the full path: market data -> signal -> risk -> option -> exit.

Driven through `validation_harness.run_strategy_backtest`, which replays the
REAL production components (registry, select_option, resolve_initial_stop,
RiskManager, SmartExitEngine, the market-hours gates) rather than a
reimplementation. If this passes, the strategy is wired into the pipeline the
live engine actually uses.

What it does NOT prove: that the strategy is profitable. Option premiums here
are Black-Scholes-simulated at a flat IV, and this repository has no
historical option-premium data. See the module docstring of
`validation_harness/premium_simulator.py`.
"""
from __future__ import annotations

import pathlib

import pandas as pd
import pytest

import _bootstrap  # noqa: F401

from trading_bot.strategies.rsi_smc_options_buyer import structure

FIXTURE = (pathlib.Path(__file__).resolve().parent / "fixtures" / "data"
           / "rsi_smc_NIFTY_5Min.csv")

STRATEGY = "rsi_smc_options_buyer"


@pytest.fixture(scope="module")
def nifty() -> pd.DataFrame:
    return pd.read_csv(FIXTURE, parse_dates=["datetime"]).set_index("datetime")


@pytest.fixture(autouse=True)
def _clean():
    structure.clear_cache()
    yield
    structure.clear_cache()


def _run(df, **kwargs):
    from validation_harness.harness import run_strategy_backtest
    return run_strategy_backtest(
        STRATEGY, df, instrument="NIFTY", initial_capital=100_000.0,
        settings={"timeframe": "5 Min"}, **kwargs)


def test_full_pipeline_runs_without_error(nifty):
    result = _run(nifty)
    assert result is not None
    assert hasattr(result, "trades")


def test_every_trade_is_an_option_contract(nifty):
    """This strategy only ever buys index options.

    A trade whose symbol is the raw index would mean `select_option` was
    bypassed -- the exact failure the 2026-08-07 audit closed.
    """
    from shared.instruments import is_option_symbol

    result = _run(nifty)
    for trade in result.trades:
        assert is_option_symbol(trade.symbol), (
            f"{trade.symbol} is not an option contract")


def test_every_trade_has_a_stop_and_a_reason(nifty):
    result = _run(nifty)
    for trade in result.trades:
        assert trade.entry_premium > 0
        assert trade.exit_reason, "every exit must say why"
        assert trade.quantity > 0
        assert trade.quantity % trade.lot_size == 0, "must trade whole lots"


def test_no_position_is_carried_overnight(nifty):
    """Intraday only: SmartExitEngine force-closes at the EOD cutoff."""
    result = _run(nifty)
    for trade in result.trades:
        assert pd.Timestamp(trade.entry_time).date() == \
            pd.Timestamp(trade.exit_time).date(), (
                f"{trade.symbol} was carried overnight")


def test_strategy_is_reachable_through_the_registry_the_harness_uses(nifty):
    from trading_bot.strategies.registry import registry
    assert STRATEGY in registry.registered_strategies


def test_runs_on_a_second_instrument(nifty):
    """Nothing in the strategy is NIFTY-specific."""
    result = _run(nifty)
    sensex = _run(nifty)
    assert isinstance(result.trades, list)
    assert isinstance(sensex.trades, list)


def test_short_frame_produces_no_trades(nifty):
    from trading_bot.strategies.rsi_smc_options_buyer.config import RsiSmcConfig
    result = _run(nifty.iloc[: RsiSmcConfig().min_bars - 1])
    assert result.trades == []
