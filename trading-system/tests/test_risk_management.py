"""Regression tests for PortfolioRiskEngine (trading_bot/portfolio_risk.py).

Root-cause fix (Medium audit finding): the test suite had zero coverage
for risk management, despite this being one of the areas the original
80-item audit found Critical bugs in this session (the MARL Capital
Protection brake being dead code, the daily-loss circuit breaker never
firing). These tests exercise the real PortfolioRiskEngine class
directly — not mocks — against the actual drawdown/consecutive-loss
math, so a future change that breaks a circuit breaker's threshold
logic, position-size scaling, or daily/weekly reset behavior fails a
test instead of only being discovered live with real capital.
"""
import os
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from trading_bot.portfolio_risk import PortfolioRiskEngine


def test_current_capital_restores_peak_across_a_restart():
    """Root-cause fix (found live, 2026-08-05): previously peak_capital_daily/
    weekly always seeded from the static initial_capital, discarding real
    cumulative equity on every engine restart -- meaning a restart could
    silently reset how much drawdown headroom was left. current_capital
    lets the caller pass the persisted equity back in."""
    engine = PortfolioRiskEngine(max_daily_dd_pct=5.0, initial_capital=100_000.0, current_capital=105_000.0)
    assert engine.peak_capital_daily == 105_000.0
    assert engine.peak_capital_weekly == 105_000.0
    # A drop back toward (but not below) the original initial_capital must
    # NOT be treated as if starting fresh from 100_000 -- it's a real ~4.8%
    # drawdown from the restored 105_000 peak.
    engine.update_pnl(realized_pnl=-4_500.0, capital=100_500.0)
    assert engine.trading_halted is False
    engine.update_pnl(realized_pnl=-1_000.0, capital=99_500.0)
    assert engine.trading_halted is True


def test_current_capital_omitted_defaults_to_initial_capital():
    """Backward compatible: omitting current_capital must behave exactly
    like before this fix (fresh start / existing test constructions)."""
    engine = PortfolioRiskEngine(max_daily_dd_pct=5.0, initial_capital=100_000.0)
    assert engine.peak_capital_daily == 100_000.0
    assert engine.peak_capital_weekly == 100_000.0


def test_no_halt_under_normal_conditions():
    engine = PortfolioRiskEngine(max_daily_dd_pct=5.0, initial_capital=100_000.0)
    engine.update_pnl(realized_pnl=500.0, capital=100_500.0)
    assert engine.trading_halted is False
    assert engine.get_position_multiplier() == 1.0


def test_daily_drawdown_circuit_breaker_trips_at_threshold():
    engine = PortfolioRiskEngine(max_daily_dd_pct=3.0, initial_capital=100_000.0)
    # 3.5% drawdown from peak capital -- must exceed the 3.0% threshold
    engine.update_pnl(realized_pnl=-3500.0, capital=96_500.0)
    assert engine.trading_halted is True
    assert "Daily Drawdown" in engine.halt_reason
    assert engine.get_position_multiplier() == 0.0


def test_daily_drawdown_does_not_trip_below_threshold():
    engine = PortfolioRiskEngine(max_daily_dd_pct=5.0, initial_capital=100_000.0)
    # 2% drawdown -- must NOT trip a 5% threshold
    engine.update_pnl(realized_pnl=-2000.0, capital=98_000.0)
    assert engine.trading_halted is False


def test_weekly_drawdown_circuit_breaker_trips_at_threshold():
    engine = PortfolioRiskEngine(max_daily_dd_pct=50.0, max_weekly_dd_pct=8.0, initial_capital=100_000.0)
    # Daily threshold set unreachably high so only the weekly breaker can fire
    engine.update_pnl(realized_pnl=-9000.0, capital=91_000.0)
    assert engine.trading_halted is True
    assert "Weekly Drawdown" in engine.halt_reason


def test_consecutive_losses_circuit_breaker_trips_at_threshold():
    engine = PortfolioRiskEngine(max_daily_dd_pct=50.0, max_weekly_dd_pct=50.0,
                                  max_consecutive_losses=3, initial_capital=100_000.0)
    capital = 100_000.0
    for _ in range(3):
        capital -= 100.0
        engine.update_pnl(realized_pnl=-100.0, capital=capital)
    assert engine.trading_halted is True
    assert "Consecutive Losses" in engine.halt_reason


def test_consecutive_losses_resets_on_a_win():
    engine = PortfolioRiskEngine(max_daily_dd_pct=50.0, max_weekly_dd_pct=50.0,
                                  max_consecutive_losses=5, initial_capital=100_000.0)
    capital = 100_000.0
    for _ in range(3):
        capital -= 100.0
        engine.update_pnl(realized_pnl=-100.0, capital=capital)
    assert engine.consecutive_losses == 3

    capital += 500.0
    engine.update_pnl(realized_pnl=500.0, capital=capital)
    assert engine.consecutive_losses == 0
    assert engine.trading_halted is False


def test_position_multiplier_scales_down_with_consecutive_losses():
    engine = PortfolioRiskEngine(max_daily_dd_pct=50.0, max_weekly_dd_pct=50.0,
                                  max_consecutive_losses=10, initial_capital=100_000.0)
    capital = 100_000.0

    # 0-2 losses -> full size
    assert engine.get_position_multiplier() == 1.0

    # 3 losses -> half size
    for _ in range(3):
        capital -= 100.0
        engine.update_pnl(realized_pnl=-100.0, capital=capital)
    assert engine.get_position_multiplier() == 0.5

    # 5 losses -> quarter size
    for _ in range(2):
        capital -= 100.0
        engine.update_pnl(realized_pnl=-100.0, capital=capital)
    assert engine.get_position_multiplier() == 0.25

    # 10 losses -> hard halt (multiplier 0.0), matching max_consecutive_losses
    for _ in range(5):
        capital -= 100.0
        engine.update_pnl(realized_pnl=-100.0, capital=capital)
    assert engine.trading_halted is True
    assert engine.get_position_multiplier() == 0.0


def test_daily_halt_lifts_on_a_new_day():
    engine = PortfolioRiskEngine(max_daily_dd_pct=2.0, initial_capital=100_000.0)
    engine.update_pnl(realized_pnl=-3000.0, capital=97_000.0)
    assert engine.trading_halted is True

    # Simulate a new trading day by directly rolling the tracked reset date
    # back (the same field _check_resets() compares against `now`), rather
    # than sleeping in a test -- this exercises the exact reset condition
    # the real day-rollover path checks.
    import datetime
    engine.last_reset_day = engine.last_reset_day - datetime.timedelta(days=1)
    engine.update_pnl(realized_pnl=0.0, capital=97_000.0)
    assert engine.trading_halted is False
    assert engine.consecutive_losses == 0


def test_is_trading_allowed_reflects_halt_state():
    engine = PortfolioRiskEngine(max_daily_dd_pct=2.0, initial_capital=100_000.0)
    allowed, reason = engine.is_trading_allowed(100_000.0)
    assert allowed is True
    assert reason == ""

    engine.update_pnl(realized_pnl=-3000.0, capital=97_000.0)
    allowed2, reason2 = engine.is_trading_allowed(97_000.0)
    assert allowed2 is False
    assert reason2 != ""


def test_daily_loss_hit_audit_event_recorded():
    """Regression test for this session's own earlier fix: the daily
    drawdown circuit breaker previously only logged to the plain
    application logger, with no tamper-evident audit trail entry. Uses a
    scratch audit directory so this test doesn't touch the real
    trading-system/audit/ log."""
    import tempfile
    import shared.security.audit_log as audit_log_mod
    from pathlib import Path as _Path

    scratch_dir = tempfile.mkdtemp(prefix="test_risk_audit_")
    original_dir = audit_log_mod._AUDIT_DIR
    original_audit = audit_log_mod.audit
    try:
        audit_log_mod._AUDIT_DIR = _Path(scratch_dir)
        audit_log_mod.audit = audit_log_mod.AuditLogger()

        # trading_bot.portfolio_risk imported `audit`/`AuditEvent` at
        # module load time, so patch its bound reference too.
        import trading_bot.portfolio_risk as pr_mod
        pr_mod.audit = audit_log_mod.audit

        engine = PortfolioRiskEngine(max_daily_dd_pct=2.0, initial_capital=100_000.0)
        engine.update_pnl(realized_pnl=-3000.0, capital=97_000.0)

        log_files = list(_Path(scratch_dir).glob("*.log"))
        assert len(log_files) == 1
        import json
        with open(log_files[0]) as f:
            entries = [json.loads(line) for line in f if line.strip()]
        events = [e["event"] for e in entries]
        assert "DAILY_LOSS_HIT" in events
    finally:
        audit_log_mod._AUDIT_DIR = original_dir
        audit_log_mod.audit = original_audit
        import trading_bot.portfolio_risk as pr_mod
        pr_mod.audit = original_audit


if __name__ == "__main__":
    test_no_halt_under_normal_conditions()
    test_daily_drawdown_circuit_breaker_trips_at_threshold()
    test_daily_drawdown_does_not_trip_below_threshold()
    test_weekly_drawdown_circuit_breaker_trips_at_threshold()
    test_consecutive_losses_circuit_breaker_trips_at_threshold()
    test_consecutive_losses_resets_on_a_win()
    test_position_multiplier_scales_down_with_consecutive_losses()
    test_daily_halt_lifts_on_a_new_day()
    test_is_trading_allowed_reflects_halt_state()
    test_daily_loss_hit_audit_event_recorded()
    print("All risk management tests passed.")
