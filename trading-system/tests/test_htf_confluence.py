"""Unit tests for Multi-Timeframe (MTF) Trend Confluence (Ride vs Scalp mode)."""

import pandas as pd
import numpy as np
import pytest

from shared.indicators.htf_confluence import (
    detect_htf_trend,
    get_trade_holding_mode,
    LADDER_TREND_RIDE,
    LADDER_QUICK_SCALP,
    INITIAL_SL_TREND_RIDE,
    INITIAL_SL_QUICK_SCALP,
)


def _make_sample_5m_df(n: int = 100, trend: str = "bullish") -> pd.DataFrame:
    dates = pd.date_range("2026-10-05 09:15", periods=n, freq="5min")
    rng = np.random.default_rng(42)
    step = 5.0 if trend == "bullish" else -5.0 if trend == "bearish" else 0.0
    base = 24000.0 + np.arange(n) * step + rng.normal(0, 2, n)

    df = pd.DataFrame({
        "open": base - 1.0,
        "high": base + 3.0,
        "low": base - 3.0,
        "close": base,
    }, index=dates)
    return df


def test_detect_htf_trend_bullish():
    df = _make_sample_5m_df(150, trend="bullish")
    htf = detect_htf_trend(df)
    assert htf["trend_15m"] == "BULLISH"
    assert htf["trend_1h"] == "BULLISH"
    assert htf["macro_bias"] == "BULLISH"

    # BUY trade should get TREND RIDE mode
    mode_buy = get_trade_holding_mode("BUY", htf)
    assert mode_buy["mode"] == "RIDE"
    assert mode_buy["is_aligned"] is True
    assert mode_buy["profit_ladder_pct"] == LADDER_TREND_RIDE
    assert mode_buy["initial_sl_pct"] == INITIAL_SL_TREND_RIDE

    # SELL trade should get QUICK SCALP mode (counter-trend)
    mode_sell = get_trade_holding_mode("SELL", htf)
    assert mode_sell["mode"] == "SCALP"
    assert mode_sell["is_aligned"] is False
    assert mode_sell["profit_ladder_pct"] == LADDER_QUICK_SCALP
    assert mode_sell["initial_sl_pct"] == INITIAL_SL_QUICK_SCALP


def test_detect_htf_trend_bearish():
    df = _make_sample_5m_df(150, trend="bearish")
    htf = detect_htf_trend(df)
    assert htf["trend_15m"] == "BEARISH"
    assert htf["trend_1h"] == "BEARISH"

    # SELL trade should get TREND RIDE mode
    mode_sell = get_trade_holding_mode("SELL", htf)
    assert mode_sell["mode"] == "RIDE"
    assert mode_sell["is_aligned"] is True

    # BUY trade should get QUICK SCALP mode
    mode_buy = get_trade_holding_mode("BUY", htf)
    assert mode_buy["mode"] == "SCALP"
    assert mode_buy["is_aligned"] is False
