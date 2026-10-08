"""
Unit tests for the Universal Option Chart Confluence Gate (shared/option_gate.py).
Verifies the 4 pillars:
  1. Strategy Isolation Guarantee (Other strategies are 100% bypassed and untouched)
  2. Option VWAP Gate (Rejects when LTP < VWAP, Passes when LTP >= VWAP)
  3. Spread & Liquidity Gate (Rejects when Spread > 1.2%)
  4. Market Opening Warmup Guard (09:15-09:18 IST low volume bypass)
  5. Option Candle VWAP Derivation
"""

import datetime as dt
import pytz
import pytest

from shared.option_gate import (
    validate_option_entry,
    calculate_option_vwap,
    is_market_opening_warmup,
    OptionGateResult,
)

IST = pytz.timezone("Asia/Kolkata")


def test_strategy_bypass_isolation():
    """
    CRITICAL USER REQUIREMENT:
    Other strategies (SMC, Momentum, etc.) must NEVER be blocked or impacted by this gate.
    Even with bad option metrics (LTP < VWAP and massive spread), non-targeted strategies
    must pass unconditionally with 'STRATEGY_BYPASS'.
    """
    bad_opt = {
        "strike": 22700.0,
        "type": "CE",
        "ltp": 25.0,
        "vwap": 50.0,         # Heavy breakdown under VWAP (-50%)
        "bid": 20.0,
        "ask": 28.0,          # 28.5% spread (horrible)
        "spread_pct": 28.5,
        "volume": 10000,
    }

    # Test with SMC strategy
    smc_result = validate_option_entry(
        symbol="NIFTY",
        direction="BUY",
        opt_info=bad_opt,
        strategy_name="smc_rsi_frvp_options_v1",
    )
    assert smc_result.passed is True
    assert smc_result.status == "STRATEGY_BYPASS"
    assert "strict isolation guarantee" in smc_result.reason.lower()

    # Test with Momentum strategy
    mom_result = validate_option_entry(
        symbol="NIFTY",
        direction="BUY",
        opt_info=bad_opt,
        strategy_name="momentum_strategy",
    )
    assert mom_result.passed is True
    assert mom_result.status == "STRATEGY_BYPASS"


def test_ema9_rsi_vwap_rejection():
    """For ema9_rsi_momentum, LTP < VWAP must be rejected as seller absorption."""
    bad_vwap_opt = {
        "strike": 22700.0,
        "type": "CE",
        "ltp": 38.0,
        "vwap": 44.0,         # LTP is below VWAP
        "bid": 37.9,
        "ask": 38.0,
        "spread_pct": 0.26,   # Good spread
        "volume": 5000,
    }

    res = validate_option_entry(
        symbol="NIFTY",
        direction="BUY",
        opt_info=bad_vwap_opt,
        strategy_name="ema9_rsi_momentum",
        current_time=dt.datetime(2026, 10, 6, 11, 30, tzinfo=IST),
    )
    assert res.passed is False
    assert res.status == "REJECT"
    assert "BELOW intraday VWAP" in res.reason
    assert "writers are in control" in res.reason


def test_ema9_rsi_vwap_pass():
    """For ema9_rsi_momentum, LTP >= VWAP must pass cleanly."""
    good_opt = {
        "strike": 22700.0,
        "type": "CE",
        "ltp": 46.50,
        "vwap": 42.00,        # LTP is above VWAP
        "bid": 46.30,
        "ask": 46.50,
        "spread_pct": 0.43,
        "volume": 8500,
    }

    res = validate_option_entry(
        symbol="NIFTY",
        direction="BUY",
        opt_info=good_opt,
        strategy_name="ema9_rsi_momentum",
        current_time=dt.datetime(2026, 10, 6, 11, 30, tzinfo=IST),
    )
    assert res.passed is True
    assert res.status == "PASS"
    assert "Option Chart Confluence Confirmed" in res.reason


def test_ema9_rsi_spread_rejection():
    """Wide bid-ask spread (> 1.2%) must be rejected to prevent slippage traps."""
    wide_spread_opt = {
        "strike": 22700.0,
        "type": "CE",
        "ltp": 45.0,
        "vwap": 40.0,         # Good VWAP
        "bid": 42.0,
        "ask": 45.0,          # Spread is 6.67%
        "spread_pct": 6.67,
        "volume": 2000,
    }

    res = validate_option_entry(
        symbol="NIFTY",
        direction="BUY",
        opt_info=wide_spread_opt,
        strategy_name="ema9_rsi_momentum",
        current_time=dt.datetime(2026, 10, 6, 11, 30, tzinfo=IST),
    )
    assert res.passed is False
    assert res.status == "REJECT"
    assert "spread too wide" in res.reason.lower()


def test_market_opening_warmup_guard():
    """During 09:15-09:18 IST, if volume is low, VWAP is bypassed gracefully."""
    early_opt = {
        "strike": 22700.0,
        "type": "CE",
        "ltp": 38.0,
        "vwap": 42.0,         # Normally rejected
        "bid": 37.9,
        "ask": 38.0,
        "spread_pct": 0.26,
        "volume": 15,         # Low initial volume (< 50)
    }

    # 09:16:15 IST (within 3 min warmup)
    warmup_time = dt.datetime(2026, 10, 6, 9, 16, 15, tzinfo=IST)
    res = validate_option_entry(
        symbol="NIFTY",
        direction="BUY",
        opt_info=early_opt,
        strategy_name="ema9_rsi_momentum",
        current_time=warmup_time,
    )
    assert res.passed is True
    assert res.status == "WARMUP_BYPASS"
    assert "warmup active" in res.reason.lower()


def test_option_candles_vwap_derivation():
    """Option VWAP calculation from intraday candles."""
    candles = [
        {"high": 40.0, "low": 30.0, "close": 35.0, "volume": 100},  # typical = 35.0
        {"high": 50.0, "low": 40.0, "close": 45.0, "volume": 200},  # typical = 45.0
    ]
    # Total PV = 35*100 + 45*200 = 3500 + 9000 = 12500
    # Total Vol = 300
    # Expected VWAP = 12500 / 300 = 41.67
    vwap = calculate_option_vwap({}, option_candles=candles)
    assert vwap == 41.67


def test_market_opening_warmup_utc_conversion():
    """Verify that UTC timezone-aware datetime is correctly converted to IST."""
    # 03:46:15 UTC is 09:16:15 IST (which is within 09:15-09:18 IST)
    utc_time = dt.datetime(2026, 10, 6, 3, 46, 15, tzinfo=dt.timezone.utc)
    assert is_market_opening_warmup(utc_time) is True

    # 04:00:00 UTC is 09:30:00 IST (outside warmup)
    utc_outside = dt.datetime(2026, 10, 6, 4, 0, 0, tzinfo=dt.timezone.utc)
    assert is_market_opening_warmup(utc_outside) is False

