"""Unit tests verifying the 4 Pillars in SmartExitEngine and ExitAnalyzerAgent.

Pillars:
1. Plan D: Adaptive High-Watermark Retracement Trailing (Tightens as gain scales).
2. Pure Price Action & Key Support/Resistance (S&R) Proximity & Wick Rejection.
3. Derivative Confirmation (OI Wall or IV Crush Gate).
4. Time Psychology (Session Regimes: Midday Lunch-Hour Mean-Reversion Protection).
"""

import numpy as np
import pandas as pd
import pytest

from shared.exits.exit_analyzer import (
    ExitAnalyzerAgent,
    ADAPTIVE_PEAK_LOCK,
    PEAK_LOCK,
    SR_REJECTION,
    MIDDAY_EXHAUSTION,
    FAST_EMA_BREAK,
    TREND_RIDE,
)
from shared.exits.exit_engine import Position, SmartExitEngine


@pytest.fixture
def synthetic_underlying_df():
    """Generates synthetic 5-minute index candles with EMA9 and RSI."""
    n = 30
    base = 24000.0
    times = pd.date_range("2026-10-08 09:15", periods=n, freq="5min")
    close = pd.Series(base - np.arange(n) * 10, index=times)  # Downtrend for PUT
    open_ = close + 5.0
    high = open_ + 3.0
    low = close - 3.0
    volume = pd.Series(50000, index=times)
    return pd.DataFrame({"open": open_, "high": high, "low": low, "close": close, "volume": volume}, index=times)


def test_pillar_1_plan_d_adaptive_tightening_massive_gain():
    """Test 1: Plan D tightens giveback to 8% when gain reaches 100%+."""
    agent = ExitAnalyzerAgent()
    entry_price = 100.0
    peak_price = 200.0   # +100% gain
    current_price = 190.0 # 10 pts giveback / 100 pts profit = 10% giveback

    # Standard giveback was 20%, but Plan D for 100%+ gain is 8%
    result = agent.evaluate(
        entry_price=entry_price,
        current_price=current_price,
        highest_price=peak_price,
        lowest_price=entry_price,
        direction=1,
        is_option_premium=True,
    )

    assert result.should_exit is True
    assert result.mode == ADAPTIVE_PEAK_LOCK
    assert result.factors["adaptive_giveback_limit"] == 8.0
    assert result.factors["giveback_pct"] == 10.0
    assert result.suggested_sl == 200.0 - (100.0 * 0.08) # 192.0


def test_pillar_1_plan_d_moderate_gain_gives_breathing_room():
    """Test 1b: For small gains (<33%), normal 20% room is preserved so trades aren't cut early."""
    agent = ExitAnalyzerAgent()
    entry_price = 100.0
    peak_price = 120.0   # +20% gain (below 33%)
    current_price = 118.0 # 2 pts giveback / 20 pts profit = 10% giveback

    result = agent.evaluate(
        entry_price=entry_price,
        current_price=current_price,
        highest_price=peak_price,
        lowest_price=entry_price,
        direction=1,
        is_option_premium=True,
    )

    # 10% giveback is fine because limit is 20%
    assert result.should_exit is False
    assert result.factors["adaptive_giveback_limit"] == 20.0
    assert result.factors["giveback_pct"] == 10.0


def test_pillar_2_sr_proximity_and_rejection():
    """Test 2: Proximity to key S&R level combined with rejection triggers SR_REJECTION."""
    agent = ExitAnalyzerAgent()
    entry_price = 100.0
    peak_price = 150.0   # +50% gain
    current_price = 142.0 # 8 pts giveback / 50 pts profit = 16% giveback

    # Underlying spot near key support at 24000 (distance = 0.08% <= 0.35%)
    sr_levels = [24000.0, 24500.0]
    underlying_price = 24020.0

    # With derivative confirmation (e.g. IV crush or OI wall)
    result = agent.evaluate(
        entry_price=entry_price,
        current_price=current_price,
        highest_price=peak_price,
        lowest_price=entry_price,
        direction=1,
        underlying_direction=-1, # PUT trade
        is_option_premium=True,
        underlying_price=underlying_price,
        sr_levels=sr_levels,
        iv_change_from_peak=-2.0, # IV dropped by 2.0 pts
    )

    assert result.should_exit is True
    assert result.mode == SR_REJECTION
    assert result.factors["at_sr_zone"] == 1.0
    assert result.factors["iv_exhaustion"] == 1.0


def test_pillar_3_derivative_gate_iv_or_oi():
    """Test 3: Either IV crush (<= -1.5) OR OI wall confirms derivative exhaustion."""
    agent = ExitAnalyzerAgent()

    # Case A: IV crush
    res_iv = agent.evaluate(
        entry_price=100.0, current_price=145.0, highest_price=150.0, lowest_price=100.0,
        direction=1, is_option_premium=True, iv_change_from_peak=-1.8,
    )
    assert res_iv.factors["iv_exhaustion"] == 1.0
    assert res_iv.factors["deriv_exhaustion"] == 1.0

    # Case B: OI wall
    res_oi = agent.evaluate(
        entry_price=100.0, current_price=145.0, highest_price=150.0, lowest_price=100.0,
        direction=1, is_option_premium=True, oi_resistance_confirmed=True,
    )
    assert res_oi.factors["oi_wall"] == 1.0
    assert res_oi.factors["deriv_exhaustion"] == 1.0


def test_pillar_4_time_psychology_lunch_hour_protection():
    """Test 4: Midday Lunch-Hour (11:30 - 13:30) triggers mean-reversion protection on modest giveback."""
    agent = ExitAnalyzerAgent()
    entry_price = 100.0
    peak_price = 160.0    # +60% gain
    current_price = 148.0  # 12 pts giveback / 60 pts profit = 20% giveback

    # During lunch hour (11:45 AM)
    res_lunch = agent.evaluate(
        entry_price=entry_price,
        current_price=current_price,
        highest_price=peak_price,
        lowest_price=entry_price,
        direction=1,
        is_option_premium=True,
        current_time="11:45:00",
    )

    assert res_lunch.should_exit is True
    assert res_lunch.mode in (MIDDAY_EXHAUSTION, ADAPTIVE_PEAK_LOCK)
    assert res_lunch.factors["time_regime"] == "MIDDAY_CHOP"

    # In contrast, morning momentum (09:40 AM) with only 8% giveback holds
    res_morning = agent.evaluate(
        entry_price=entry_price,
        current_price=155.0, # 5 pts giveback = 8.3% giveback
        highest_price=peak_price,
        lowest_price=entry_price,
        direction=1,
        is_option_premium=True,
        current_time="09:40:00",
    )
    assert res_morning.should_exit is False
    assert res_morning.factors["time_regime"] == "MORNING_MOMENTUM"


def test_smart_exit_engine_integration_end_to_end(synthetic_underlying_df):
    """Test 5: Full end-to-end integration via SmartExitEngine.evaluate_exit."""
    engine = SmartExitEngine(enable_exit_analyzer=True)

    pos = Position(
        symbol="SENSEX 72200 PE",
        side=-1, # PUT option
        entry_price=169.60,
        quantity=20,
        entry_time="11:09:35",
        highest_price=395.65, # Peak reached today! (+133% gain)
        lowest_price=148.45,
        stop_loss=296.80,
        target=424.00,
        is_partially_booked=True,
    )

    # Price dropped from peak 395.65 down to 365.00
    # Peak profit = 226.05. Giveback = 30.65 (13.5% giveback >= 8% limit for 100%+ gain)
    current_opt_price = 365.00
    current_time = "11:40:00" # Lunch hour!

    should_exit, reason, qty = engine.evaluate_exit(
        position=pos,
        current_price=current_opt_price,
        current_time=current_time,
        current_atr=15.0,
        underlying_price=72050.0,
        sr_levels=[72000.0, 72500.0],
        iv_change_from_peak=-2.2, # IV dropped after peak
        df=synthetic_underlying_df,
    )

    assert should_exit is True
    assert "AI Exit Analyzer" in reason
    # Position stop_loss ratchets to a tight peak protection level
    assert pos.stop_loss > 360.0
