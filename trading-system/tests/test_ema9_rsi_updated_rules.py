"""Unit tests verifying the 5 updated rules for ema9_rsi_momentum strategy."""

import datetime
import numpy as np
import pandas as pd
import pytest

from trading_bot.strategies.ema9_rsi_momentum.config import (
    Ema9RsiMomentumConfig,
    LATE_ENTRY_ENABLED,
    LATE_ENTRY_END,
    LATE_ENTRY_MIN_STRENGTH,
)
from trading_bot.strategies.ema9_rsi_momentum.indicators import (
    compute_indicator_set,
    IndicatorSet,
)
from trading_bot.strategies.ema9_rsi_momentum.signal_engine import (
    assess_entry_quality,
    compute_cross_signals,
    classify_momentum_strength,
    PRIORITY_HIGH,
    PRIORITY_MEDIUM,
    PRIORITY_LOW,
    VERY_STRONG,
)
from shared.eod_policy import late_entry_allowed, expiry_late_entry_allowed


@pytest.fixture
def sample_data():
    """Generates synthetic price data for testing."""
    np.random.seed(42)
    n = 60
    base = 24000.0
    # Create timestamps from 15:00 to 15:30 on a 1-min / 5-min step
    times = pd.date_range("2026-10-02 15:00", periods=n, freq="1min")
    close = pd.Series(base + np.cumsum(np.random.randn(n) * 5), index=times)
    open_ = close.shift(1).fillna(base)
    high = np.maximum(open_, close) + 2.0
    low = np.minimum(open_, close) - 2.0
    volume = pd.Series(10000, index=times)

    return pd.DataFrame({"open": open_, "high": high, "low": low, "close": close, "volume": volume}, index=times)


def test_rule_1_rsi_separation_gap_removed(sample_data):
    """Test 1: Wick touch entry does NOT require RSI gap >= 3.0 anymore."""
    cfg = Ema9RsiMomentumConfig()
    # Ensure wick_min_rsi_gap is no longer gating
    assert not hasattr(cfg, "wick_min_rsi_gap") or getattr(cfg, "wick_min_rsi_gap", None) is None

    ind = compute_indicator_set(sample_data)
    quality = assess_entry_quality(sample_data, ind, cfg, np.ones(len(sample_data), dtype=int))

    # Quality evaluates without needing rsi_separated gating
    assert len(quality.take) == len(sample_data)


def test_rule_2_anticipate_cross_removed():
    """Test 2: Anticipate cross parameters and code are removed."""
    cfg = Ema9RsiMomentumConfig()
    assert not hasattr(cfg, "anticipate_cross_bars")
    assert not hasattr(cfg, "anticipate_max_gap_atr")


def test_rule_3_breakaway_entry_removed():
    """Test 3: Breakaway entry parameters and code are removed."""
    cfg = Ema9RsiMomentumConfig()
    assert not hasattr(cfg, "allow_breakaway_entry")
    assert not hasattr(cfg, "breakaway_min_body_atr")


def test_rule_4_late_entry_applies_to_all_days():
    """Test 4: Late entry up to 15:25 on VERY_STRONG momentum applies to ALL days."""
    cfg = Ema9RsiMomentumConfig()
    assert LATE_ENTRY_ENABLED is True
    assert LATE_ENTRY_END == "15:25"
    assert LATE_ENTRY_MIN_STRENGTH == "VERY_STRONG"

    # Test policy function on NON-expiry day (is_expiry_day=False)
    now_time = datetime.time(15, 20)
    allowed, reason = late_entry_allowed(now_time, "VERY_STRONG", cfg, is_expiry_day=False)
    assert allowed is True
    assert "late entry permitted" in reason.lower()

    # Normal or weak momentum in late window is rejected
    allowed_weak, reason_weak = late_entry_allowed(now_time, "NORMAL", cfg, is_expiry_day=False)
    assert allowed_weak is False


def test_rule_5_cm_ultimate_ma_used_in_indicators(sample_data):
    """Test 5: Indicators use CM_Ultimate_MA_MTF_V2 for EMA 9 and 20."""
    ind = compute_indicator_set(sample_data, ema_fast=9, ema_slow=20)
    assert isinstance(ind, IndicatorSet)
    assert ind.cm_ma is not None
    assert "ma1" in ind.cm_ma.columns  # 20 EMA
    assert "ma2" in ind.cm_ma.columns  # 9 EMA

    # Verify that ema_fast matches MA2 and ema_slow matches MA1
    pd.testing.assert_series_equal(ind.ema_fast, ind.cm_ma["ma2"], check_names=False)
    pd.testing.assert_series_equal(ind.ema_slow, ind.cm_ma["ma1"], check_names=False)
