"""
Unit tests for the MARL ExecutionAgent (Fix 3, 2026-08-16).

Tests cover:
  - Long signal → CE_BUY in low/normal IV
  - Short signal → PE_BUY in low/normal IV
  - High IV regime → ATM strike (no ITM)
  - Extreme IV regime → SELL premium (CE_SELL / PE_SELL) with OTM+2 strike
  - Near-expiry (gamma mode) → ATM only, regardless of IV
  - After 15:00 IST (theta guard) → execution blocked
  - Hold/Close signal → execute=False, no option type
  - Inactive agent → execute=False

Run with:  pytest tests/test_execution_agent.py -v
"""

from __future__ import annotations

import sys
import os
from datetime import datetime, timezone, timedelta
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from drl.marl.execution_agent import ExecutionAgent

_IST = timezone(timedelta(hours=5, minutes=30))


def _make_agent() -> ExecutionAgent:
    return ExecutionAgent()


def _morning_ist():
    """Return a mock IST time safely within session (10:30 AM)."""
    return datetime.now(_IST).replace(hour=10, minute=30, second=0)


def _eod_ist():
    """Return a mock IST time after theta guard cutoff (15:15 PM)."""
    return datetime.now(_IST).replace(hour=15, minute=15, second=0)


# ---------------------------------------------------------------------------
# Test: Long signal → CE_BUY
# ---------------------------------------------------------------------------

class TestLongSignal:
    def test_low_iv_long_returns_ce_buy(self):
        agent = _make_agent()
        with patch.object(agent, "_current_ist", return_value=_morning_ist()):
            result = agent.analyze(signal_action=1, current_spot=24000.0, iv_pct=0.14)
        assert result["execute"] is True
        assert result["option_type"] == "CE_BUY"

    def test_high_iv_long_returns_ce_buy_atm(self):
        agent = _make_agent()
        with patch.object(agent, "_current_ist", return_value=_morning_ist()):
            result = agent.analyze(signal_action=1, current_spot=24000.0, iv_pct=0.25)
        assert result["execute"] is True
        assert result["option_type"] == "CE_BUY"
        assert result["strike_offset"] == 0, "High IV should force ATM (offset=0)"

    def test_extreme_iv_long_returns_ce_sell(self):
        """In extreme IV (>30%), premium selling is the edge — not buying."""
        agent = _make_agent()
        with patch.object(agent, "_current_ist", return_value=_morning_ist()):
            result = agent.analyze(signal_action=1, current_spot=24000.0, iv_pct=0.35)
        assert result["execute"] is True
        assert result["option_type"] == "CE_SELL"
        assert result["strike_offset"] == 2, "Extreme IV should select OTM+2"


# ---------------------------------------------------------------------------
# Test: Short signal → PE_BUY
# ---------------------------------------------------------------------------

class TestShortSignal:
    def test_low_iv_short_returns_pe_buy(self):
        agent = _make_agent()
        with patch.object(agent, "_current_ist", return_value=_morning_ist()):
            result = agent.analyze(signal_action=2, current_spot=24000.0, iv_pct=0.14)
        assert result["execute"] is True
        assert result["option_type"] == "PE_BUY"

    def test_extreme_iv_short_returns_pe_sell(self):
        agent = _make_agent()
        with patch.object(agent, "_current_ist", return_value=_morning_ist()):
            result = agent.analyze(signal_action=2, current_spot=24000.0, iv_pct=0.35)
        assert result["execute"] is True
        assert result["option_type"] == "PE_SELL"


# ---------------------------------------------------------------------------
# Test: Gamma mode (near expiry)
# ---------------------------------------------------------------------------

class TestGammaMode:
    def test_gamma_mode_forces_atm(self):
        """Near expiry (≤2 days), strike must be ATM regardless of IV."""
        agent = _make_agent()
        with patch.object(agent, "_current_ist", return_value=_morning_ist()):
            result = agent.analyze(
                signal_action=1, current_spot=24000.0,
                iv_pct=0.14, days_to_expiry=1,
            )
        assert result["gamma_mode"] is True
        assert result["strike_offset"] == 0, "Gamma mode must force ATM (offset=0)"

    def test_gamma_mode_flag_set_at_boundary(self):
        agent = _make_agent()
        with patch.object(agent, "_current_ist", return_value=_morning_ist()):
            at_boundary = agent.analyze(signal_action=1, current_spot=24000.0, days_to_expiry=2)
            beyond_boundary = agent.analyze(signal_action=1, current_spot=24000.0, days_to_expiry=3)
        assert at_boundary["gamma_mode"] is True
        assert beyond_boundary["gamma_mode"] is False


# ---------------------------------------------------------------------------
# Test: Theta guard (session end)
# ---------------------------------------------------------------------------

class TestThetaGuard:
    def test_theta_guard_blocks_execution_after_1500(self):
        """After 15:00 IST, buying options premium must be blocked."""
        agent = _make_agent()
        with patch.object(agent, "_current_ist", return_value=_eod_ist()):
            result = agent.analyze(signal_action=1, current_spot=24000.0, iv_pct=0.14)
        assert result["execute"] is False
        assert result["theta_guard"] is True

    def test_execution_allowed_before_1500(self):
        agent = _make_agent()
        with patch.object(agent, "_current_ist", return_value=_morning_ist()):
            result = agent.analyze(signal_action=1, current_spot=24000.0, iv_pct=0.14)
        assert result["execute"] is True
        assert result["theta_guard"] is False


# ---------------------------------------------------------------------------
# Test: Hold / Close signals
# ---------------------------------------------------------------------------

class TestHoldCloseSignal:
    @pytest.mark.parametrize("signal_action", [0, 3])
    def test_hold_or_close_does_not_execute(self, signal_action):
        agent = _make_agent()
        with patch.object(agent, "_current_ist", return_value=_morning_ist()):
            result = agent.analyze(signal_action=signal_action, current_spot=24000.0)
        assert result["execute"] is False
        assert result["option_type"] is None


# ---------------------------------------------------------------------------
# Test: Confidence scoring
# ---------------------------------------------------------------------------

class TestConfidenceScore:
    def test_confidence_is_in_valid_range(self):
        agent = _make_agent()
        with patch.object(agent, "_current_ist", return_value=_morning_ist()):
            for iv in [0.10, 0.22, 0.35]:
                result = agent.analyze(signal_action=1, current_spot=24000.0, iv_pct=iv)
                assert 0.0 <= result["confidence"] <= 1.0, (
                    f"Confidence {result['confidence']} out of [0,1] for IV={iv}"
                )

    def test_extreme_iv_reduces_confidence(self):
        agent = _make_agent()
        with patch.object(agent, "_current_ist", return_value=_morning_ist()):
            normal = agent.analyze(signal_action=1, current_spot=24000.0, iv_pct=0.15)
            extreme = agent.analyze(signal_action=1, current_spot=24000.0, iv_pct=0.35)
        assert extreme["confidence"] < normal["confidence"], (
            "Extreme IV should reduce execution confidence vs. normal IV."
        )


# ---------------------------------------------------------------------------
# Test: RiskAgent integration
# ---------------------------------------------------------------------------

class TestRiskAgentIntegration:
    def test_lot_multiplier_deferred_to_risk_agent(self):
        """ExecutionAgent must use whatever RiskAgent.get_position_size_multiplier() returns."""
        from unittest.mock import MagicMock
        agent = _make_agent()
        mock_risk = MagicMock()
        mock_risk.get_position_size_multiplier.return_value = 0.5
        with patch.object(agent, "_current_ist", return_value=_morning_ist()):
            result = agent.analyze(
                signal_action=1, current_spot=24000.0,
                iv_pct=0.14, risk_agent=mock_risk,
            )
        assert result["lot_multiplier"] == 0.5, (
            f"Expected lot_multiplier=0.5 from mock RiskAgent, got {result['lot_multiplier']}"
        )

    def test_fallback_lot_multiplier_is_1_without_risk_agent(self):
        agent = _make_agent()
        with patch.object(agent, "_current_ist", return_value=_morning_ist()):
            result = agent.analyze(signal_action=1, current_spot=24000.0, iv_pct=0.14)
        assert result["lot_multiplier"] == 1.0
