"""Unit tests for shared/risk/option_atr.py -- the option-premium-scale ATR
resolver that replaces the index-scale ATR previously fed into every
option position's trailing stop (2026-08-07 audit §2.1, design doc
docs/ATR_TRAILING_STOP_DESIGN_2026-08-07.md, Approach 4 with a
premium-banded cold-start bridge).
"""
import _bootstrap  # noqa: F401  (side-effect: puts trading-system/ on sys.path)

import numpy as np
import pandas as pd
import pytest

from shared.risk.option_atr import (
    MIN_CANDLES_FOR_OPTION_ATR,
    resolve_option_atr,
)
from shared.risk.option_stop_loss import resolve_stop_points


def _option_candles(n: int, base_premium: float = 120.0, seed: int = 3) -> pd.DataFrame:
    """Synthetic option premium candles with realistic-looking noise --
    premiums never go negative, unlike an index series shifted by a fixed
    offset."""
    rng = np.random.default_rng(seed)
    close = base_premium + rng.normal(0, base_premium * 0.01, n).cumsum()
    close = np.clip(close, 1.0, None)
    high = close + rng.uniform(0.1, base_premium * 0.01, n)
    low = np.clip(close - rng.uniform(0.1, base_premium * 0.01, n), 0.05, None)
    idx = pd.date_range("2026-08-07 09:15", periods=n, freq="1min")
    return pd.DataFrame({
        "open": close,
        "high": high,
        "low": low,
        "close": close,
        "volume": np.zeros(n),
    }, index=idx)


# ---------------------------------------------------------------------------
# Cold start (no / insufficient candle history)
# ---------------------------------------------------------------------------

def test_none_candles_falls_back_to_premium_proxy():
    decision = resolve_option_atr(None, current_premium=120.0)
    assert decision.source == "premium_proxy"
    assert decision.candles_available == 0
    assert decision.atr_value == pytest.approx(resolve_stop_points(120.0))


def test_empty_dataframe_falls_back_to_premium_proxy():
    decision = resolve_option_atr(pd.DataFrame(columns=["open", "high", "low", "close", "volume"]), current_premium=45.0)
    assert decision.source == "premium_proxy"
    assert decision.candles_available == 0


def test_below_minimum_candle_count_falls_back_to_premium_proxy():
    df = _option_candles(MIN_CANDLES_FOR_OPTION_ATR - 1)
    decision = resolve_option_atr(df, current_premium=120.0)
    assert decision.source == "premium_proxy"
    assert decision.candles_available == MIN_CANDLES_FOR_OPTION_ATR - 1


def test_cold_start_never_touches_index_scale_values():
    """The fallback must be a premium-rupee quantity, never anything close
    to an index-point scale (~100-375 for NIFTY in real data)."""
    decision = resolve_option_atr(None, current_premium=15.0)
    # A cheap, sub-₹20 premium's proxy stop must itself be a small rupee
    # figure -- nowhere near index-point magnitude.
    assert decision.atr_value < 15.0


# ---------------------------------------------------------------------------
# Warm (enough real option candle history)
# ---------------------------------------------------------------------------

def test_sufficient_candles_uses_real_option_atr():
    df = _option_candles(50, base_premium=120.0)
    decision = resolve_option_atr(df, current_premium=120.0)
    assert decision.source == "option_atr"
    assert decision.candles_available == 50
    assert decision.atr_value > 0


def test_option_atr_is_premium_scale_not_index_scale():
    """Root-cause regression: the whole point of this module is that the
    ATR distance must be commensurate with the option's own premium, not
    with the underlying index's point range (which today, empirically, is
    ~100-375 for NIFTY -- wildly larger than any of these synthetic
    low-premium contracts' own realistic ATR)."""
    for premium in (15.0, 45.0, 120.0, 400.0):
        df = _option_candles(30, base_premium=premium)
        decision = resolve_option_atr(df, current_premium=premium)
        assert decision.source == "option_atr"
        # A contract's own ATR should be a modest fraction of its own
        # premium, not multiple times larger than the premium itself
        # (which is what an index-point value would produce for a cheap
        # option).
        assert decision.atr_value < premium


def test_matches_shared_atr_indicator_directly():
    """Pins that this module doesn't reimplement ATR math -- it must
    produce exactly what shared/indicators/atr.py::atr() would for the
    same input, at the same window."""
    from shared.indicators.atr import atr as shared_atr

    df = _option_candles(40, base_premium=200.0)
    decision = resolve_option_atr(df, current_premium=200.0)
    expected = shared_atr(df, window=MIN_CANDLES_FOR_OPTION_ATR).iloc[-1]
    assert decision.atr_value == pytest.approx(float(expected))


def test_degenerate_flat_premium_falls_back_to_proxy():
    """A completely flat premium run produces a zero real ATR -- must
    still fall back to the (positive) premium-proxy rather than returning
    a zero/negative trailing cushion."""
    n = 30
    idx = pd.date_range("2026-08-07 09:15", periods=n, freq="1min")
    flat = pd.DataFrame({
        "open": [100.0] * n, "high": [100.0] * n, "low": [100.0] * n,
        "close": [100.0] * n, "volume": [0.0] * n,
    }, index=idx)
    decision = resolve_option_atr(flat, current_premium=100.0)
    assert decision.source == "premium_proxy"
    assert decision.atr_value > 0


# ---------------------------------------------------------------------------
# settings passthrough
# ---------------------------------------------------------------------------

def test_settings_forwarded_to_the_proxy_fallback():
    custom_bands = [{"lower": 0, "upper": 10_000, "min_points": 7.0, "max_points": 7.0}]
    decision = resolve_option_atr(None, current_premium=50.0, settings={"option_sl_bands": custom_bands})
    assert decision.atr_value == pytest.approx(7.0)
