"""Per-trade risk cap vs. the indivisible option lot.

An option lot cannot be split. With premium-banded stops, one NIFTY lot of a
₹250 contract risks ~₹1,950 — about 2% of a ₹1L account, above the 1%
per-trade cap. Before this, `can_trade` simply returned False and the only
trace was a log line: the engine looked healthy and silently stopped taking
any high-premium signal.

`is_minimum_tradeable_size` makes that case explicit — the trade is allowed
because sizing has no smaller answer, and a RISK-CAP OVERRIDE warning states
the real exposure. Every other gate must remain untouched, which is most of
what these tests check.
"""
import logging

import _bootstrap  # noqa: F401  (side-effect: puts trading-system/ on sys.path)

import pytest

from shared.risk import RiskConfig, RiskManager, TradeRecord


@pytest.fixture
def manager():
    return RiskManager(initial_capital=100_000.0, config=RiskConfig(risk_per_trade=0.01))


# `ai_confidence` matters here: RiskConfig raises the per-trade cap from 1%
# to 3.5% whenever confidence >= 0.85 (the "AI Confidence Override"). These
# tests pass an explicit sub-threshold confidence so they exercise the base
# 1% cap deterministically rather than the elevated tier.
_NORMAL_CONFIDENCE = 0.60


def test_oversized_risk_is_still_rejected_by_default(manager):
    allowed, reason = manager.can_trade(
        symbol="NIFTY", risk_amount=1_950.0, ai_confidence=_NORMAL_CONFIDENCE
    )

    assert allowed is False
    assert "exceeds limit" in reason


def test_one_lot_over_the_cap_is_allowed_with_an_override(manager):
    allowed, reason = manager.can_trade(
        symbol="NIFTY",
        risk_amount=1_950.0,
        ai_confidence=_NORMAL_CONFIDENCE,
        is_minimum_tradeable_size=True,
    )

    assert allowed is True
    assert reason == "OK"


def test_the_override_logs_the_real_exposure(manager, caplog):
    with caplog.at_level(logging.WARNING, logger="shared.risk.manager"):
        manager.can_trade(
            symbol="NSE:NIFTY2580724500CE",
            risk_amount=1_950.0,
            ai_confidence=_NORMAL_CONFIDENCE,
            is_minimum_tradeable_size=True,
        )

    warnings = [r.getMessage() for r in caplog.records if r.levelno >= logging.WARNING]
    assert any("RISK-CAP OVERRIDE" in message for message in warnings)
    # The operator needs the true percentage, not just "over the limit".
    assert any("1.95%" in message for message in warnings)


def test_within_cap_needs_no_override_and_logs_nothing(manager, caplog):
    with caplog.at_level(logging.WARNING, logger="shared.risk.manager"):
        allowed, reason = manager.can_trade(symbol="NIFTY", risk_amount=500.0)

    assert (allowed, reason) == (True, "OK")
    assert not [r for r in caplog.records if "RISK-CAP OVERRIDE" in r.getMessage()]


# ---------------------------------------------------------------------------
# The override relaxes the per-trade cap ONLY. Everything else still applies.
# ---------------------------------------------------------------------------

def test_override_does_not_bypass_risk_off(manager):
    manager._activate_risk_off("test halt")

    allowed, reason = manager.can_trade(
        symbol="NIFTY", risk_amount=1_950.0, is_minimum_tradeable_size=True
    )

    assert allowed is False
    assert "RISK-OFF" in reason


def test_override_does_not_bypass_the_daily_loss_limit(manager):
    manager.daily_pnl = -6_000.0  # beyond 5% of 100k

    allowed, reason = manager.can_trade(
        symbol="NIFTY", risk_amount=1_950.0, is_minimum_tradeable_size=True
    )

    assert allowed is False
    assert "Daily loss limit" in reason


def test_override_does_not_bypass_max_drawdown(manager):
    manager.peak_equity = 100_000.0
    manager.current_equity = 75_000.0  # 25% drawdown, limit is 20%

    allowed, reason = manager.can_trade(
        symbol="NIFTY", risk_amount=100.0, is_minimum_tradeable_size=True
    )

    assert allowed is False
    assert "drawdown" in reason.lower()


def test_override_does_not_bypass_consecutive_losses(manager):
    for index in range(5):
        manager.record_trade(
            TradeRecord("NIFTY", "BUY", 100.0, 90.0, -100.0, f"2026-08-06T10:{index:02d}:00")
        )

    allowed, reason = manager.can_trade(
        symbol="NIFTY", risk_amount=1_950.0, is_minimum_tradeable_size=True
    )

    assert allowed is False
    assert "Consecutive losses" in reason


def test_override_does_not_bypass_the_daily_trade_cap():
    manager = RiskManager(
        initial_capital=100_000.0,
        config=RiskConfig(risk_per_trade=0.01, max_trades_per_day=3),
    )
    for index in range(3):
        manager.record_trade(
            TradeRecord("NIFTY", "BUY", 100.0, 105.0, 50.0, f"2026-08-06T10:{index:02d}:00")
        )

    allowed, reason = manager.can_trade(
        symbol="NIFTY", risk_amount=1_950.0, is_minimum_tradeable_size=True
    )

    assert allowed is False
    assert "Max trades per day" in reason


def test_override_does_not_bypass_the_ai_confidence_floor(manager):
    allowed, reason = manager.can_trade(
        symbol="NIFTY",
        risk_amount=1_950.0,
        ai_confidence=0.10,
        is_minimum_tradeable_size=True,
    )

    assert allowed is False
    assert "AI confidence" in reason


def test_override_does_not_bypass_the_volatility_gate(manager):
    allowed, reason = manager.can_trade(
        symbol="NIFTY",
        risk_amount=1_950.0,
        current_volatility=9.0,
        is_minimum_tradeable_size=True,
    )

    assert allowed is False
    assert "Volatility" in reason


# ---------------------------------------------------------------------------
# Risk-based sizing against banded stops
# ---------------------------------------------------------------------------

def test_sizing_shrinks_as_the_banded_stop_widens(manager):
    """The reason option sizing moved off the fixed `quantity` setting: with
    a fixed size, rupee risk would swing with the band."""
    from shared.risk import resolve_initial_stop

    tight = resolve_initial_stop(25.0)    # ₹20-50 band  → ~₹5 stop
    wide = resolve_initial_stop(240.0)    # ₹150-250 band → ~₹29 stop

    small_qty = manager.calculate_position_size(
        25.0, tight.sl_price, ai_confidence=_NORMAL_CONFIDENCE
    )
    large_qty = manager.calculate_position_size(
        240.0, wide.sl_price, ai_confidence=_NORMAL_CONFIDENCE
    )

    assert small_qty > large_qty
    # Both target the same rupee risk (1% of 100k = ₹1,000).
    assert small_qty * tight.sl_points == pytest.approx(1_000.0, rel=0.02)
    assert large_qty * wide.sl_points == pytest.approx(1_000.0, rel=0.02)
