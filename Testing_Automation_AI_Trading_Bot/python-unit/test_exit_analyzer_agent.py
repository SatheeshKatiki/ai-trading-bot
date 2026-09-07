"""Unit tests for ExitAnalyzerAgent and SmartExitEngine AI exit integration."""

import numpy as np
import pandas as pd
import pytest

from shared.exits.exit_analyzer import (
    ExitAnalyzerAgent,
    ExitAnalysisResult,
    TREND_RIDE,
    PEAK_LOCK,
    FAST_EMA_BREAK,
    RSI_EXHAUSTION,
    MOMENTUM_REVERSAL,
)
from shared.exits.exit_engine import Position, SmartExitEngine


def _create_sample_ohlcv(closes: list[float]) -> pd.DataFrame:
    """Helper to build a realistic OHLCV dataframe from a close series."""
    n = len(closes)
    df = pd.DataFrame({
        "open": [c - 2.0 for c in closes],
        "high": [c + 5.0 for c in closes],
        "low": [c - 5.0 for c in closes],
        "close": closes,
        "volume": [100000 + i * 1000 for i in range(n)],
    })
    return df


class TestExitAnalyzerAgent:
    """Test suite for the autonomous AI Exit Analyzer probability engine."""

    def test_initialization_defaults(self):
        agent = ExitAnalyzerAgent()
        assert agent.min_peak_profit_pts == 30.0
        assert agent.max_giveback_pct == 20.0
        assert agent.urgency_threshold == 0.70

    def test_trend_ride_mode_on_strong_trend(self):
        """When price is steadily climbing with no giveback, urgency must be low and no exit."""
        agent = ExitAnalyzerAgent()
        # Price climbed from 24000 to 24050, currently at 24050 (0 giveback)
        res = agent.evaluate(
            entry_price=24000.0,
            current_price=24050.0,
            highest_price=24050.0,
            lowest_price=24000.0,
            direction=1,
        )
        assert res.should_exit is False
        assert res.mode == TREND_RIDE
        assert res.urgency_score < 0.40

    def test_peak_lock_exit_on_20pct_giveback(self):
        """When price gains +75 pts and gives back 20% (15 pts), exit must trigger."""
        agent = ExitAnalyzerAgent(min_peak_profit_pts=30.0, max_giveback_pct=20.0)
        # Entry: 24065, High: 24140 (+75 pts). Current: 24125 (15 pts giveback = 20%)
        res = agent.evaluate(
            entry_price=24065.0,
            current_price=24125.0,
            highest_price=24140.0,
            lowest_price=24065.0,
            direction=1,
        )
        assert res.should_exit is True
        assert res.mode == PEAK_LOCK
        assert "Peak Lock Triggered" in res.reason
        assert res.factors["giveback_pct"] == 20.0

    def test_fast_ema9_break_with_df(self):
        """When candle closes below EMA9 after a rally, price action score increases and fires exit."""
        agent = ExitAnalyzerAgent(min_peak_profit_pts=30.0)
        # 15 bars rising to 24140, then last bar breaking down to 24080 (below EMA9)
        closes = [24000 + i * 10 for i in range(14)] + [24080.0]  # Peak was ~24130, dropped below EMA9
        df = _create_sample_ohlcv(closes)
        
        res = agent.evaluate(
            entry_price=24000.0,
            current_price=24080.0,
            highest_price=24140.0,
            lowest_price=24000.0,
            direction=1,
            df=df,
        )
        assert res.factors["price_action"] > 0
        assert res.should_exit is True

    def test_pe_short_peak_lock_exit(self):
        """Bearish PUT position gains +80 pts on underlying fall, then bounces 25% from trough."""
        agent = ExitAnalyzerAgent(min_peak_profit_pts=30.0, max_giveback_pct=20.0)
        # Entry: 24100, Trough: 24020 (+80 pts gain). Current: 24040 (20 pts bounce = 25% giveback)
        res = agent.evaluate(
            entry_price=24100.0,
            current_price=24040.0,
            highest_price=24100.0,
            lowest_price=24020.0,
            direction=-1,
        )
        assert res.should_exit is True
        assert res.mode == PEAK_LOCK
        assert res.factors["giveback_pct"] == 25.0

    def test_safety_on_invalid_or_zero_price(self):
        """Gracefully handle zero or negative input prices without crashing."""
        agent = ExitAnalyzerAgent()
        res = agent.evaluate(
            entry_price=0.0,
            current_price=100.0,
            highest_price=100.0,
            lowest_price=0.0,
            direction=1,
        )
        assert res.should_exit is False
        assert res.mode == TREND_RIDE


class TestSmartExitEngineAIIntegration:
    """Test suite for SmartExitEngine integrating the ExitAnalyzerAgent."""

    def test_smart_exit_engine_triggers_ai_peak_exit(self):
        engine = SmartExitEngine(enable_exit_analyzer=True)
        pos = Position(
            symbol="NSE:NIFTY26AUG24100CE",
            entry_price=100.0,
            quantity=65,
            side=1,
            stop_loss=80.0,
            target=0.0,
            highest_price=180.0,  # +80 pts peak premium gain
            lowest_price=100.0,
            entry_time="09:30:00",
            is_partially_booked=True,
        )

        # Current price dropped from 180 to 160 (gives back 25% of 80 pt gain)
        should_exit, reason, qty = engine.evaluate_exit(
            position=pos,
            current_price=160.0,
            current_time="11:35:00",
            current_atr=5.0,
        )
        assert should_exit is True
        assert "AI Exit Analyzer" in reason
        assert qty is None  # Exits full position
