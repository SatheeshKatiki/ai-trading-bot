"""Regression coverage for the MARL_Ultra Capital Protection deadlock
(found, measured, and fixed 2026-08-07).

Root cause: RiskAgent's 3-consecutive-loss block was PERMANENT rather
than per-session as its own docstring states ("stop trading for the
session"). Chain: 3 losses -> get_position_size_multiplier() returns 0.0
-> marl_strategy.generate_signals() blocks every new entry -> no entries
means no closes -> record_trade_result() never fires again -> the streak
can never reach the win that would clear it. RiskAgent had no session
boundary of any kind, and _marl_instance is a process-global singleton.

Measured impact before the fix: over a 123-day validation window
MARL_Ultra traded on 14 days, all in February, and never again after
2026-02-19 — silently dead for ~104 of 123 days while still reporting
healthy at the process level.

Fixed with an IST-anchored daily reset mirroring
shared/risk/manager.py::RiskManager, checked on BOTH the read path
(get_position_size_multiplier) and the write path (record_trade_result).
Read-path placement is the load-bearing part: once entries are blocked
the write path is unreachable by construction.
"""
from datetime import date

import _bootstrap  # noqa: F401  (side-effect: puts trading-system/ on sys.path)

import pytest

from drl.marl import risk_agent as risk_agent_module
from drl.marl.risk_agent import RiskAgent


@pytest.fixture
def agent():
    return RiskAgent()


def _force_three_losses(a: RiskAgent) -> None:
    for _ in range(3):
        a.record_trade_result(-100.0)


def test_three_losses_still_stops_trading(agent):
    """The protection itself must be unchanged in strength."""
    _force_three_losses(agent)
    assert agent.get_position_size_multiplier() == 0.0


def test_two_losses_still_halves_size(agent):
    agent.record_trade_result(-100.0)
    agent.record_trade_result(-100.0)
    assert agent.get_position_size_multiplier() == 0.5


def test_a_win_still_clears_the_streak_within_the_same_session(agent):
    agent.record_trade_result(-100.0)
    agent.record_trade_result(-100.0)
    agent.record_trade_result(+50.0)
    assert agent.get_position_size_multiplier() == 1.0


def test_the_deadlock_breaks_on_a_new_session(agent, monkeypatch):
    """THE regression: a blocked agent must recover on the next trading
    day WITHOUT needing a winning trade (which the block itself makes
    unreachable)."""
    _force_three_losses(agent)
    assert agent.get_position_size_multiplier() == 0.0, "should be blocked on day 1"

    # Next trading day, with NO intervening trade of any kind.
    monkeypatch.setattr(risk_agent_module, "_today_ist", lambda: date(2099, 1, 2))
    agent._session_date = date(2099, 1, 1)

    assert agent.get_position_size_multiplier() == 1.0, (
        "Capital Protection must expire with its session — this is the "
        "permanent-deadlock regression."
    )


def test_reset_happens_on_the_read_path_specifically(agent, monkeypatch):
    """Load-bearing detail: once blocked, record_trade_result() is
    unreachable in production, so the reset must fire from the read path
    alone. Asserts recovery with zero writes after the rollover."""
    _force_three_losses(agent)
    monkeypatch.setattr(risk_agent_module, "_today_ist", lambda: date(2099, 6, 2))
    agent._session_date = date(2099, 6, 1)

    # Only a read. No record_trade_result() call at all.
    assert agent.get_position_size_multiplier() == 1.0
    assert agent._consecutive_losses == 0


def test_streak_persists_within_the_same_session(agent, monkeypatch):
    """A same-day rollover check must NOT clear a legitimate streak —
    the protection has to survive intraday."""
    monkeypatch.setattr(risk_agent_module, "_today_ist", lambda: date(2099, 3, 3))
    agent._session_date = date(2099, 3, 3)
    _force_three_losses(agent)

    assert agent.get_position_size_multiplier() == 0.0
    assert agent.get_position_size_multiplier() == 0.0  # repeated reads don't clear it
    assert agent._consecutive_losses == 3


def test_analyze_also_recovers_after_a_session_rollover(agent, monkeypatch):
    """analyze() reads _consecutive_losses directly for its HOLD veto; it
    calls get_position_size_multiplier() first, so the reset covers it."""
    _force_three_losses(agent)
    assert agent.analyze(current_pnl_pct=0.0)["override"] is True

    monkeypatch.setattr(risk_agent_module, "_today_ist", lambda: date(2099, 9, 2))
    agent._session_date = date(2099, 9, 1)

    plan = agent.analyze(current_pnl_pct=0.0)
    assert plan["override"] is False
    assert plan["position_size_multiplier"] == 1.0


def test_capital_protection_flag_also_clears_on_rollover(agent, monkeypatch):
    _force_three_losses(agent)
    assert agent._capital_protection_mode is True

    monkeypatch.setattr(risk_agent_module, "_today_ist", lambda: date(2099, 4, 2))
    agent._session_date = date(2099, 4, 1)
    agent.get_position_size_multiplier()

    assert agent._capital_protection_mode is False
    assert agent._last_trade_result is None


def test_session_date_initialized_to_today_ist():
    a = RiskAgent()
    assert a._session_date == risk_agent_module._today_ist()
