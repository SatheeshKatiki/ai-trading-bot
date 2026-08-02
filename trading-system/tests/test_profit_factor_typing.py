"""Regression tests for backtesting_engine/run.py's _compute_profit_factor.

Root-cause fix (Low audit finding): stats["profitFactor"] was sometimes
a float (round(total_profit / total_loss, 2)) and sometimes the literal
string "Infinity" (or the float 0.0) depending on whether there were any
losing trades -- inconsistent typing that any strict consumer (frontend
TypeScript, a future Python caller doing arithmetic) can't rely on.
Fixed by making every branch return a string.
"""
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from backtesting_engine.run import _compute_profit_factor


def test_normal_case_returns_string():
    result = _compute_profit_factor(total_profit=300.0, total_loss=100.0)
    assert isinstance(result, str)
    assert result == "3.0"


def test_zero_loss_positive_profit_returns_infinity_string():
    result = _compute_profit_factor(total_profit=500.0, total_loss=0.0)
    assert isinstance(result, str)
    assert result == "Infinity"


def test_zero_loss_zero_profit_returns_string_zero():
    result = _compute_profit_factor(total_profit=0.0, total_loss=0.0)
    assert isinstance(result, str)
    assert result == "0.0"


def test_rounding_is_preserved():
    result = _compute_profit_factor(total_profit=100.0, total_loss=3.0)
    assert result == str(round(100.0 / 3.0, 2))


if __name__ == "__main__":
    test_normal_case_returns_string()
    test_zero_loss_positive_profit_returns_infinity_string()
    test_zero_loss_zero_profit_returns_string_zero()
    test_rounding_is_preserved()
    print("All profit_factor typing tests passed.")
