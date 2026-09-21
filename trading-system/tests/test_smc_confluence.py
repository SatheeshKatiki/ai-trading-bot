"""
Unit and Integration Tests for Institutional SMC, Volume Profile, and RSI Confluence Suite.
"""

import numpy as np
import pandas as pd
import pytest

from shared.indicators.smart_money_concepts import (
    calculate_smc,
    detect_pivots,
    TrendState,
    StructureType,
    LuxAlgoSMCConfig
)
from shared.indicators.volume_profile import (
    calculate_fixed_range_volume_profile,
    VolumeProfileResult
)
from shared.indicators.rsi_divergence import (
    calculate_wilders_rsi,
    calculate_rsi_divergences,
    DivergenceType
)
from shared.agents.smc_confluence_agent import (
    SMCConfluenceAgent,
    SMCConfluenceConfig,
    SMCConfluenceSignal
)


def _generate_synthetic_ohlcv(n: int = 100, trend: str = "up") -> pd.DataFrame:
    """Generates synthetic OHLCV bars with predictable trends and pivots."""
    np.random.seed(42)
    dates = pd.date_range("2026-09-01 09:15", periods=n, freq="5min")

    base = 25000.0
    prices = [base]
    step = 5.0 if trend == "up" else -5.0

    for i in range(1, n):
        noise = np.random.normal(0, 10.0)
        # Introduce occasional swings
        if i % 15 == 0:
            noise = -step * 5
        prices.append(prices[-1] + step + noise)

    closes = np.array(prices)
    highs = closes + np.abs(np.random.normal(5.0, 3.0, n))
    lows = closes - np.abs(np.random.normal(5.0, 3.0, n))
    opens = (highs + lows) / 2.0
    volumes = np.random.uniform(5000, 50000, n)

    return pd.DataFrame({
        "open": opens,
        "high": highs,
        "low": lows,
        "close": closes,
        "volume": volumes
    }, index=dates)


class TestSmartMoneyConcepts:

    def test_pivot_detection(self):
        highs = np.array([10, 12, 15, 20, 14, 11, 8, 9, 7])
        lows = np.array([5, 6, 8, 12, 7, 5, 2, 4, 3])

        p_highs, p_lows = detect_pivots(highs, lows, length=2)
        # Peak should be at index 3 (price 20)
        assert p_highs[3] == True
        # Trough should be at index 6 (price 2)
        assert p_lows[6] == True

    def test_smc_structure_and_order_blocks(self):
        df = _generate_synthetic_ohlcv(n=80, trend="up")
        res_df, analysis = calculate_smc(df, swing_length=4, internal_length=2)

        assert 'smc_bos' in res_df.columns
        assert 'smc_trend' in res_df.columns
        assert analysis.equilibrium_price is not None
        assert analysis.discount_zone[0] <= analysis.discount_zone[1]
        assert analysis.premium_zone[0] <= analysis.premium_zone[1]

    def test_fvg_detection(self):
        # Create clear Bullish FVG: Low of bar 2 > High of bar 0
        dates = pd.date_range("2026-09-01", periods=10, freq="5min")
        df = pd.DataFrame({
            "open": [100, 105, 120, 125, 122, 120, 118, 119, 120, 121],
            "high": [105, 118, 130, 128, 125, 122, 120, 121, 122, 123],
            "low":  [98,  104, 112, 120, 118, 115, 116, 117, 118, 119],
            "close":[104, 117, 127, 123, 120, 118, 119, 120, 121, 122],
            "volume":[1000] * 10
        }, index=dates)

        # Bar 2 low is 112, Bar 0 high is 105 -> Gap between 105 and 112
        res_df, analysis = calculate_smc(df, config=LuxAlgoSMCConfig(internal_length=2))
        assert len(analysis.active_bullish_fvgs) > 0
        fvg = analysis.active_bullish_fvgs[0]
        assert fvg.is_bullish == True
        assert fvg.top == 112
        assert fvg.bottom == 105

    def test_luxalgo_smc_exact_user_configuration(self):
        # Verify LuxAlgoSMCConfig matches all parameters dictated by the user
        cfg = LuxAlgoSMCConfig()
        assert cfg.mode == "Present"
        assert cfg.style == "Colored"
        assert cfg.color_candles == True
        assert cfg.show_internal_structure == True
        assert cfg.internal_bullish_color == "#10b981"
        assert cfg.internal_bearish_color == "#ef4444"
        assert cfg.internal_confluence_filter == True
        assert cfg.internal_label_size == "tiny"

        assert cfg.show_swing_structure == True
        assert cfg.swing_points_length == 50
        assert cfg.swing_bullish_color == "#10b981"
        assert cfg.swing_bearish_color == "#ef4444"
        assert cfg.swing_label_size == "tiny"
        assert cfg.show_swing_points == True
        assert cfg.show_strong_weak_high_low == True

        assert cfg.internal_ob_count == 3
        assert cfg.swing_ob_count == 3
        assert cfg.ob_filter == "ATR"
        assert cfg.ob_mitigation == "High/Low"

        assert cfg.show_equal_high_low == True
        assert cfg.eq_bars_confirmation == 3
        assert cfg.eq_threshold == 0.1
        assert cfg.eq_label_size == "tiny"

        assert cfg.show_fvg == True
        assert cfg.fvg_auto_threshold == True
        assert cfg.fvg_timeframe == "Chart"
        assert cfg.fvg_extend == 20

        assert cfg.mtf_daily == True
        assert cfg.mtf_weekly == True
        assert cfg.mtf_monthly == True
        assert cfg.mtf_color == "#3b82f6"

        assert cfg.show_premium_discount == True
        assert cfg.premium_color == "#ef4444"
        assert cfg.equilibrium_color == "#ec4899"
        assert cfg.discount_color == "#10b981"

        # Style Tab assertions
        assert cfg.plot_candles == True
        assert cfg.show_boxes == True
        assert cfg.show_panel_labels == True
        assert cfg.show_lines == True
        assert cfg.precision == "Default"
        assert cfg.labels_on_price_scale == True
        assert cfg.values_in_status_line == True
        assert cfg.inputs_in_status_line == True

        # Visibility Tab assertions
        assert cfg.vis_ticks == True
        assert cfg.vis_seconds == True and cfg.vis_seconds_min == 1 and cfg.vis_seconds_max == 59
        assert cfg.vis_minutes == True and cfg.vis_minutes_min == 1 and cfg.vis_minutes_max == 59
        assert cfg.vis_hours == True and cfg.vis_hours_min == 1 and cfg.vis_hours_max == 24
        assert cfg.vis_days == True and cfg.vis_days_min == 1 and cfg.vis_days_max == 366
        assert cfg.vis_weeks == True and cfg.vis_weeks_min == 1 and cfg.vis_weeks_max == 52
        assert cfg.vis_months == True and cfg.vis_months_min == 1 and cfg.vis_months_max == 12

        # Visibility helper tests
        assert cfg.is_visible_on_timeframe("1m") == True
        assert cfg.is_visible_on_timeframe("5m") == True
        assert cfg.is_visible_on_timeframe("1h") == True
        assert cfg.is_visible_on_timeframe("1D") == True

        # Test calculation on synthetic data with this exact config
        df = _generate_synthetic_ohlcv(n=120)
        res_df, analysis = calculate_smc(df, config=cfg)
        assert analysis.config.mode == "Present"
        assert 'smc_candle_color' in res_df.columns
        assert len(analysis.active_bullish_obs) <= cfg.swing_ob_count
        assert len(analysis.active_bearish_obs) <= cfg.swing_ob_count


class TestVolumeProfile:

    def test_frvp_poc_and_value_area(self):
        df = _generate_synthetic_ohlcv(n=60)
        vp = calculate_fixed_range_volume_profile(df, num_bins=40, value_area_pct=0.70)

        assert vp.total_volume > 0
        assert vp.range_low <= vp.poc_price <= vp.range_high
        assert vp.val_price <= vp.poc_price <= vp.vah_price
        assert vp.value_area_volume <= vp.total_volume
        assert vp.is_inside_value_area(vp.poc_price) == True

        # Bin check
        assert len(vp.bins) == 40
        poc_bin = next(b for b in vp.bins if b.is_poc)
        assert poc_bin is not None
        assert poc_bin.total_volume == max(b.total_volume for b in vp.bins)


class TestRSIDivergence:

    def test_wilders_rsi(self):
        closes = np.array([100 + i * 2 for i in range(30)], dtype=float)
        rsi = calculate_wilders_rsi(closes, period=14)
        # Consistent uptrend should produce high RSI
        assert rsi[-1] > 70.0

    def test_rsi_divergence_engine(self):
        df = _generate_synthetic_ohlcv(n=80)
        res_df, analysis = calculate_rsi_divergences(df, period=14, lookback_pivot=4)

        assert 'rsi' in res_df.columns
        assert 'rsi_reg_bull_div' in res_df.columns
        assert 0.0 <= analysis.current_rsi <= 100.0


class TestSMCConfluenceAgent:

    def test_agent_evaluation(self):
        df = _generate_synthetic_ohlcv(n=90)
        agent = SMCConfluenceAgent(
            config=SMCConfluenceConfig(
                w_smc=0.40,
                w_vp=0.30,
                w_rsi=0.30,
                confluence_threshold=0.60
            )
        )

        signal = agent.evaluate(df)
        assert isinstance(signal, SMCConfluenceSignal)
        assert signal.direction in (-1, 0, 1)
        assert 0.0 <= signal.confidence <= 1.0
        assert 0.0 <= signal.confluence_score <= 1.0
        assert "smc_factor" in signal.factors or "bull_score" in signal.factors
