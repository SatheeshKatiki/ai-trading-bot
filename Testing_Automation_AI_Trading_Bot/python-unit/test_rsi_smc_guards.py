"""No-trade vetoes, configuration, and the M2 contract screen.

Every veto carries a name, because a session that took no trades has to be
explainable from the log rather than guessed at. "The bot looks alive and
simply never trades" is the failure mode these tests exist to keep visible.
"""
from __future__ import annotations

import datetime as dt
import pathlib

import numpy as np
import pandas as pd
import pytest

import _bootstrap  # noqa: F401

import trading_bot.strategies.rsi_smc_options_buyer as strategy
from trading_bot.strategies.rsi_smc_options_buyer import no_trade, regime, structure
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


def _atr(df: pd.DataFrame, cfg: RsiSmcConfig) -> np.ndarray:
    from shared.indicators import atr
    return atr(df, cfg.atr_length).to_numpy(dtype=float)


# ---------------------------------------------------------------------
# No-trade vetoes
# ---------------------------------------------------------------------

def test_every_veto_has_a_name(nifty):
    cfg = RsiSmcConfig()
    view = no_trade.evaluate(nifty, cfg, regime.compute(nifty, cfg), _atr(nifty, cfg))
    expected = {"insufficient_history", "regime", "volatility_band",
                "time_window", "invalid_bar", "duplicate_bar"}
    assert expected <= set(view.reasons)


def test_blocked_is_the_union_of_the_reasons(nifty):
    cfg = RsiSmcConfig()
    view = no_trade.evaluate(nifty, cfg, regime.compute(nifty, cfg), _atr(nifty, cfg))
    union = np.zeros(len(nifty), dtype=bool)
    for mask in view.reasons.values():
        union |= mask
    np.testing.assert_array_equal(view.blocked, union)


def test_reason_at_names_what_fired(nifty):
    cfg = RsiSmcConfig()
    view = no_trade.evaluate(nifty, cfg, regime.compute(nifty, cfg), _atr(nifty, cfg))
    blocked = np.flatnonzero(view.blocked)
    assert blocked.size, "the fixture should contain at least one blocked bar"
    assert view.reason_at(int(blocked[0])) != ""
    unblocked = np.flatnonzero(~view.blocked)
    if unblocked.size:
        assert view.reason_at(int(unblocked[0])) == ""


def test_warmup_bars_are_always_blocked(nifty):
    cfg = RsiSmcConfig()
    view = no_trade.evaluate(nifty, cfg, regime.compute(nifty, cfg), _atr(nifty, cfg))
    assert view.blocked[: cfg.min_bars].all()


def test_time_window_blocks_outside_the_session(nifty):
    cfg = RsiSmcConfig(time_start="10:00", time_end="11:00")
    view = no_trade.evaluate(nifty, cfg, regime.compute(nifty, cfg), _atr(nifty, cfg))
    minutes = nifty.index.hour * 60 + nifty.index.minute
    outside = (minutes < 600) | (minutes > 660)
    assert view.reasons["time_window"][outside].all()
    assert not view.reasons["time_window"][~outside].any()


def test_invalid_bars_are_blocked():
    cfg = RsiSmcConfig()
    n = 300
    index = pd.date_range("2026-09-01 09:15", periods=n, freq="5min")
    frame = pd.DataFrame({
        "open": np.full(n, 100.0), "high": np.full(n, 101.0),
        "low": np.full(n, 99.0), "close": np.full(n, 100.0),
        "volume": np.ones(n),
    }, index=index)
    frame.loc[frame.index[50], "close"] = 0.0          # non-positive price
    frame.loc[frame.index[60], "high"] = 1.0           # high below low

    view = no_trade.evaluate(frame, cfg, regime.compute(frame, cfg), _atr(frame, cfg))
    assert view.reasons["invalid_bar"][50]
    assert view.reasons["invalid_bar"][60]


def test_duplicate_timestamps_are_flagged(nifty):
    cfg = RsiSmcConfig()
    duped = nifty.copy()
    index = duped.index.to_list()
    index[100] = index[99]
    duped.index = pd.DatetimeIndex(index)
    view = no_trade.evaluate(duped, cfg, regime.compute(duped, cfg), _atr(duped, cfg))
    assert view.reasons["duplicate_bar"][100]


def test_instrument_reason_only_fires_for_unsupported_symbols():
    cfg = RsiSmcConfig()
    assert no_trade.instrument_reason("NSE:NIFTY50-INDEX", cfg) == ""
    assert no_trade.instrument_reason("BSE:SENSEX-INDEX", cfg) == ""
    assert "RELIANCE" in no_trade.instrument_reason("NSE:RELIANCE-EQ", cfg)
    assert no_trade.instrument_reason(None, cfg) == ""


# ---------------------------------------------------------------------
# Regime -- fails safe, and its borrowed contract is pinned
# ---------------------------------------------------------------------

def test_regime_contract_is_pinned(nifty):
    """rsi_smc borrows `MarketRegimeDetector` from institutional_momentum.

    That is a deliberate reuse, and a deliberate coupling. This pins the
    columns relied on so a change there breaks a test rather than silently
    changing this strategy's live behaviour.
    """
    from trading_bot.strategies.momentum_strategy.regime_detector import (
        MarketRegimeDetector,
    )
    table = MarketRegimeDetector().detect_vectorized(nifty)
    for column in regime.REQUIRED_REGIME_COLUMNS:
        assert column in table.columns, f"MarketRegimeDetector no longer reports {column}"
    assert set(np.unique(table["state"])) <= {"TRENDING", "SIDEWAYS", "UNKNOWN"}


def test_regime_failure_blocks_every_bar(nifty, monkeypatch):
    """If the regime cannot be determined, nothing trades."""
    def boom(*args, **kwargs):
        raise RuntimeError("deliberate")

    import trading_bot.strategies.momentum_strategy.regime_detector as detector
    monkeypatch.setattr(detector.MarketRegimeDetector, "detect_vectorized", boom)
    view = regime.compute(nifty, RsiSmcConfig())
    assert not view.tradeable.any()


def test_choppy_bars_are_not_tradeable(nifty):
    cfg = RsiSmcConfig(choppiness_max=0.0)   # nothing is calm enough
    view = regime.compute(nifty, cfg)
    assert not view.tradeable.any()


# ---------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------

def test_settings_prefix_mapping():
    cfg = RsiSmcConfig.from_settings({
        "rsi_smc_min_rr": 3.0,
        "rsi_smc_level_atr_mult": 2.5,
        "unrelated_key": 1,
    })
    assert cfg.min_rr == 3.0
    assert cfg.level_atr_mult == 2.5


def test_timeframe_comes_from_the_unprefixed_ui_key():
    assert RsiSmcConfig.from_settings({"timeframe": "15 Min"}).timeframe_minutes == 15
    # An explicit prefixed value still wins -- that is how a shadow book pins
    # one timeframe regardless of the UI.
    cfg = RsiSmcConfig.from_settings(
        {"timeframe": "15 Min", "rsi_smc_timeframe_minutes": 5})
    assert cfg.timeframe_minutes == 5


def test_symbol_overrides_apply():
    settings = {"rsi_smc_symbol_overrides": {"SENSEX": {"min_rr": 2.5}}}
    assert RsiSmcConfig.from_settings(settings, symbol="BSE:SENSEX-INDEX").min_rr == 2.5
    assert RsiSmcConfig.from_settings(settings, symbol="NSE:NIFTY50-INDEX").min_rr == \
        RsiSmcConfig().min_rr


def test_min_bars_follows_the_swing_length():
    cfg = RsiSmcConfig(swing_points_length=10, min_bars_swing_multiple=6)
    assert cfg.min_bars == 60


def test_generate_signals_accepts_the_whole_settings_dict(nifty):
    """main.py calls `registry.run_strategy(name, df, **settings)`, so every
    settings key arrives as a kwarg -- including lists and dicts."""
    signals = strategy.generate_signals(
        nifty,
        option_sl_bands=[{"lower": 0, "upper": 10}],
        lot_sizes={"NIFTY": 65},
        active_strategy="rsi_smc_options_buyer",
        enable_squeeze_filter=True,
    )
    assert len(signals) == len(nifty)


# ---------------------------------------------------------------------
# M2 -- contract screen
# ---------------------------------------------------------------------

class _Quote:
    def __init__(self, ltp=120.0, bid=119.5, ask=120.5, volume=5000):
        self.ltp, self.bid, self.ask, self.volume = ltp, bid, ask, volume


def test_good_contract_is_approved():
    verdict = strategy.approve_contract("NSE:NIFTY25O0724900CE", _Quote())
    assert verdict.approved and verdict.reason == ""


def test_missing_quote_is_rejected():
    assert not strategy.approve_contract("X", None).approved


def test_zero_quote_is_rejected():
    verdict = strategy.approve_contract("X", _Quote(bid=0.0, ask=0.0))
    assert not verdict.approved
    assert "two-sided" in verdict.reason


def test_crossed_quote_is_rejected():
    verdict = strategy.approve_contract("X", _Quote(bid=121.0, ask=120.0))
    assert not verdict.approved
    assert "crossed" in verdict.reason


def test_wide_spread_is_rejected():
    verdict = strategy.approve_contract("X", _Quote(ltp=10.0, bid=9.0, ask=10.0))
    assert not verdict.approved
    assert "spread" in verdict.reason


def test_invalid_last_price_is_rejected():
    assert not strategy.approve_contract("X", _Quote(ltp=0.0)).approved


def test_stale_quote_is_rejected():
    verdict = strategy.approve_contract("X", _Quote(), age_s=99.0)
    assert not verdict.approved
    assert "old" in verdict.reason


def test_fresh_quote_passes_the_age_check():
    assert strategy.approve_contract("X", _Quote(), age_s=0.5).approved


def test_volume_floor_is_off_by_default_and_enforceable():
    assert strategy.approve_contract("X", _Quote(volume=0)).approved
    verdict = strategy.approve_contract(
        "X", _Quote(volume=10), {"rsi_smc_min_contract_volume": 100})
    assert not verdict.approved
    assert "volume" in verdict.reason


def test_blocked_fields_are_not_consulted():
    """OI, OI change, IV and Delta are unavailable on the live path and must
    not be approximated from anything else."""
    import inspect
    source = inspect.getsource(strategy.approve_contract)
    body = source.split('"""')[-1]        # skip the docstring
    for forbidden in ("open_interest", ".oi", "implied_vol", ".iv", "delta"):
        assert forbidden not in body, (
            f"approve_contract must not consult {forbidden}: it is not "
            f"available on the live execution path")


def test_entry_grade_is_never_low(nifty):
    """`shared.entry_gate` DROPS a setup graded LOW. By the time a signal
    exists it has passed all nine mandatory conditions, so there is no weak
    survivor left to discard."""
    grade = strategy.assess_entry_quality(nifty, 1)
    if grade is not None:
        assert grade.priority in ("HIGH", "MEDIUM")
        assert grade.take is True


def test_entry_grade_handles_short_frames(nifty):
    cfg = RsiSmcConfig()
    assert strategy.assess_entry_quality(nifty.iloc[: cfg.min_bars - 1], 1) is None
    assert strategy.assess_entry_quality(nifty, 0) is None
