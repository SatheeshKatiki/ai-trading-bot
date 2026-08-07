"""Unit tests for validation_harness/classify.py's KEEP/IMPROVE/REMOVE
verdict logic.
"""
import _bootstrap  # noqa: F401  (side-effect: puts trading-system/ on sys.path)

from validation_harness.classify import MIN_TRADES_FOR_VERDICT, classify_strategy
from validation_harness.regimes import REGIME_NAMES


def _regime_metrics(trade_count=10, profit_factor=1.5, expectancy=50.0):
    return {"trade_count": trade_count, "profit_factor": profit_factor, "expectancy": expectancy}


def _all_regimes(profit_factor=1.5, expectancy=50.0, trade_count=10):
    return {r: _regime_metrics(trade_count, profit_factor, expectancy) for r in REGIME_NAMES}


def test_too_few_trades_is_improve_with_insufficient_data_reason():
    overall = {"trade_count": MIN_TRADES_FOR_VERDICT - 1, "profit_factor": 2.0, "expectancy": 100.0, "net_profit": 5000, "max_drawdown_pct": 5.0}
    verdict = classify_strategy(overall, _all_regimes())
    assert verdict.classification == "IMPROVE"
    assert any("insufficient" in r.lower() for r in verdict.reasons)


def test_consistently_profitable_across_regimes_is_keep():
    overall = {"trade_count": 200, "profit_factor": 1.8, "expectancy": 80.0, "net_profit": 20000, "max_drawdown_pct": 10.0}
    by_regime = _all_regimes(profit_factor=1.6, expectancy=60.0, trade_count=20)
    verdict = classify_strategy(overall, by_regime)
    assert verdict.classification == "KEEP"


def test_consistently_losing_across_regimes_is_remove():
    overall = {"trade_count": 200, "profit_factor": 0.6, "expectancy": -30.0, "net_profit": -15000, "max_drawdown_pct": 40.0}
    by_regime = _all_regimes(profit_factor=0.5, expectancy=-25.0, trade_count=20)
    verdict = classify_strategy(overall, by_regime)
    assert verdict.classification == "REMOVE"


def test_single_bad_regime_does_not_force_remove():
    """The explicit 'not from a single backtest' rule: profitable
    everywhere except one regime must not be REMOVE."""
    overall = {"trade_count": 200, "profit_factor": 1.4, "expectancy": 40.0, "net_profit": 12000, "max_drawdown_pct": 12.0}
    by_regime = _all_regimes(profit_factor=1.6, expectancy=60.0, trade_count=20)
    by_regime["gap_day"] = _regime_metrics(trade_count=15, profit_factor=0.5, expectancy=-40.0)
    verdict = classify_strategy(overall, by_regime)
    assert verdict.classification != "REMOVE"


def test_single_good_regime_does_not_force_keep():
    """Symmetric: losing everywhere except one regime must not be KEEP."""
    overall = {"trade_count": 200, "profit_factor": 0.9, "expectancy": -5.0, "net_profit": -2000, "max_drawdown_pct": 20.0}
    by_regime = _all_regimes(profit_factor=0.6, expectancy=-30.0, trade_count=20)
    by_regime["trending"] = _regime_metrics(trade_count=15, profit_factor=2.0, expectancy=80.0)
    verdict = classify_strategy(overall, by_regime)
    assert verdict.classification != "KEEP"


def test_marginal_profit_factor_is_improve_not_keep():
    overall = {"trade_count": 200, "profit_factor": 1.05, "expectancy": 5.0, "net_profit": 1000, "max_drawdown_pct": 15.0}
    by_regime = _all_regimes(profit_factor=1.05, expectancy=5.0, trade_count=20)
    verdict = classify_strategy(overall, by_regime)
    assert verdict.classification == "IMPROVE"


def test_high_drawdown_prevents_keep_even_if_profitable():
    overall = {"trade_count": 200, "profit_factor": 2.0, "expectancy": 100.0, "net_profit": 30000, "max_drawdown_pct": 45.0}
    by_regime = _all_regimes(profit_factor=1.8, expectancy=90.0, trade_count=20)
    verdict = classify_strategy(overall, by_regime)
    assert verdict.classification != "KEEP"
    assert any("drawdown" in r.lower() for r in verdict.reasons)


def test_regimes_with_too_few_trades_are_not_counted_either_way():
    """A regime with 0-2 trades shouldn't push the verdict in any
    direction -- not enough evidence from that regime alone."""
    overall = {"trade_count": 200, "profit_factor": 1.8, "expectancy": 80.0, "net_profit": 20000, "max_drawdown_pct": 10.0}
    by_regime = _all_regimes(profit_factor=1.6, expectancy=60.0, trade_count=20)
    by_regime["gap_day"] = _regime_metrics(trade_count=1, profit_factor=0.1, expectancy=-500.0)
    verdict = classify_strategy(overall, by_regime)
    assert verdict.classification == "KEEP"
    assert verdict.regimes_traded == 4  # gap_day excluded for having <3 trades
