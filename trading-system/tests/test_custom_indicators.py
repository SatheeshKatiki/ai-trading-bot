"""Unit tests for updated RSI indicator and newly created CM_Ultimate_Moving_Average."""

import numpy as np
import pandas as pd
import pytest

from shared.indicators import (
    rsi,
    calculate_rsi_indicator,
    rsi_indicator,
    DEFAULT_RSI_SETTINGS,
    RSISettings,
    cm_ultimate_moving_average,
    cm_ultimate_ma,
    CM_Ultimate_MA_MTF_V2,
    DEFAULT_CM_ULTIMATE_MA_SETTINGS,
    CMUltimateMASettings,
)


@pytest.fixture
def sample_ohlcv_data():
    """Generates a sample DataFrame with OHLCV data."""
    np.random.seed(42)
    n = 100
    close = 100.0 + np.cumsum(np.random.randn(n) * 1.5)
    open_p = close + np.random.randn(n) * 0.5
    high = np.maximum(open_p, close) + np.abs(np.random.randn(n))
    low = np.minimum(open_p, close) - np.abs(np.random.randn(n))
    volume = np.random.randint(1000, 50000, size=n)

    return pd.DataFrame(
        {
            "open": open_p,
            "high": high,
            "low": low,
            "close": close,
            "volume": volume,
        }
    )


def test_rsi_default_settings():
    """Test that default RSI settings match TradingView specification."""
    assert DEFAULT_RSI_SETTINGS.length == 14
    assert DEFAULT_RSI_SETTINGS.source == "close"
    assert DEFAULT_RSI_SETTINGS.calculate_divergence is False
    assert DEFAULT_RSI_SETTINGS.smoothing_type == "EMA"
    assert DEFAULT_RSI_SETTINGS.smoothing_length == 20
    assert DEFAULT_RSI_SETTINGS.bb_stddev == 2.0
    assert DEFAULT_RSI_SETTINGS.upper_band == 60.0
    assert DEFAULT_RSI_SETTINGS.middle_band == 50.0
    assert DEFAULT_RSI_SETTINGS.lower_band == 40.0
    assert DEFAULT_RSI_SETTINGS.wait_for_timeframe_closes is True


def test_rsi_indicator_calculation(sample_ohlcv_data):
    """Test RSI indicator calculation output columns and properties."""
    df_res = calculate_rsi_indicator(sample_ohlcv_data)

    expected_cols = [
        "rsi",
        "rsi_ma",
        "upper_band",
        "middle_band",
        "lower_band",
        "overbought",
        "oversold",
        "rsi_crossed_above_ma",
        "rsi_crossed_below_ma",
    ]
    for col in expected_cols:
        assert col in df_res.columns, f"Missing column: {col}"

    assert len(df_res) == len(sample_ohlcv_data)
    assert (df_res["upper_band"] == 60.0).all()
    assert (df_res["middle_band"] == 50.0).all()
    assert (df_res["lower_band"] == 40.0).all()

    # Base backward-compatible rsi function check
    raw_rsi = rsi(sample_ohlcv_data["close"], window=14)
    pd.testing.assert_series_equal(df_res["rsi"], raw_rsi, check_names=False)


def test_cm_ultimate_ma_settings():
    """Test default CM Ultimate Moving Average settings."""
    cfg = DEFAULT_CM_ULTIMATE_MA_SETTINGS
    assert cfg.use_current_res is True
    assert cfg.custom_res == "1 day"
    assert cfg.ma1_len == 20
    assert cfg.ma1_type == 2  # EMA
    assert cfg.ma1_factor_t3 == 7.0
    assert cfg.show_price_crossing_ma1 is False
    assert cfg.change_color_ma1 is True
    assert cfg.color_smoothing == 2

    assert cfg.optional_2nd_ma is True
    assert cfg.ma2_len == 9
    assert cfg.ma2_type == 2  # EMA
    assert cfg.ma2_factor_t3 == 7.0
    assert cfg.change_color_ma2 is True
    assert cfg.show_price_crossing_ma2 is True
    assert cfg.show_dots_on_cross is False


def test_cm_ultimate_ma_calculation(sample_ohlcv_data):
    """Test CM Ultimate Moving Average calculations and outputs."""
    df_res = cm_ultimate_moving_average(sample_ohlcv_data)

    expected_cols = [
        "ma1",
        "ma1_dir",
        "ma1_color",
        "ma2",
        "ma2_dir",
        "ma2_color",
        "price_cross_ma1_up",
        "price_cross_ma1_down",
        "price_cross_ma2_up",
        "price_cross_ma2_down",
        "bar_highlight",
        "ma_cross_up",
        "ma_cross_down",
        "ma_cross",
    ]
    for col in expected_cols:
        assert col in df_res.columns, f"Missing column in CM MA output: {col}"

    # Verify lengths
    assert len(df_res) == len(sample_ohlcv_data)

    # MA1 is 20 EMA, MA2 is 9 EMA
    expected_ma1 = sample_ohlcv_data["close"].ewm(span=20, adjust=False).mean()
    expected_ma2 = sample_ohlcv_data["close"].ewm(span=9, adjust=False).mean()

    pd.testing.assert_series_equal(df_res["ma1"], expected_ma1, check_names=False)
    pd.testing.assert_series_equal(df_res["ma2"], expected_ma2, check_names=False)

    # Verify bar highlight reflects price crossing 2nd MA (as spc2=True, spc=False)
    expected_highlight = df_res["price_cross_ma2_up"] | df_res["price_cross_ma2_down"]
    pd.testing.assert_series_equal(df_res["bar_highlight"], expected_highlight, check_names=False)


def test_cm_ultimate_ma_all_types(sample_ohlcv_data):
    """Verify that all 8 MA types calculate without errors."""
    for ma_type in range(1, 9):
        df_out = cm_ultimate_moving_average(
            sample_ohlcv_data,
            ma1_type=ma_type,
            ma2_type=ma_type,
            ma1_len=15,
            ma2_len=7,
        )
        assert not df_out["ma1"].isna().all()
        assert not df_out["ma2"].isna().all()
