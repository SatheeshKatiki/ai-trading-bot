"""Unit tests for validation_harness/classify.py's production-readiness
gating framework (revised 2026-08-08 — see that module's docstring for
the derivation of every threshold).

Framework under test:
  NECESSARY  N1 edge exists · N2 sample >= 30 · N3 no critical defect
             N4 drawdown <= 30% (survivability)
  QUALITY    Q1 recovery >= 2.0 · Q2 drawdown explained by risk model
             Q3 profitable in a majority of sampled regimes
"""
import _bootstrap  # noqa: F401  (side-effect: puts trading-system/ on sys.path)

from validation_harness.classify import (
    MAX_DRAWDOWN_PCT,
    MIN_RECOVERY_FACTOR,
    MIN_TRADES_FOR_VERDICT,
    classify_strategy,
)
from validation_harness.regimes import REGIME_NAMES


def _regime(trade_count=20, profit_factor=1.5, expectancy=50.0):
    return {"trade_count": trade_count, "profit_factor": profit_factor, "expectancy": expectancy}


def _all_regimes(**kw):
    return {r: _regime(**kw) for r in REGIME_NAMES}


def _healthy_overall(**overrides):
    """A strategy that passes every gate; individual tests break one."""
    base = {
        "trade_count": 300, "net_profit": 78_000, "profit_factor": 1.22,
        "expectancy": 245.0, "max_drawdown_pct": 16.7, "recovery_factor": 4.68,
        "max_consecutive_losses": 4,
    }
    base.update(overrides)
    return base


def test_healthy_strategy_is_keep():
    v = classify_strategy(_healthy_overall(), _all_regimes())
    assert v.classification == "KEEP", v.reasons


def test_pf_below_130_no_longer_blocks_keep():
    """The central change: PF 1.22 with strong risk metrics is KEEP.
    PF is mechanically (WR/(1-WR)) x R:R and says nothing about risk."""
    v = classify_strategy(_healthy_overall(profit_factor=1.22), _all_regimes())
    assert v.classification == "KEEP"


def test_high_pf_does_not_rescue_an_unsurvivable_drawdown():
    """The inversion the old gate produced: PF 1.38 with a 47.9%
    drawdown must NOT be KEEP."""
    v = classify_strategy(
        _healthy_overall(profit_factor=1.38, max_drawdown_pct=47.9,
                         recovery_factor=5.16, max_consecutive_losses=5),
        _all_regimes(),
    )
    assert v.classification == "IMPROVE"
    assert any(r.startswith("N4") for r in v.failed_necessary)


def test_drawdown_exactly_at_the_limit_is_allowed():
    v = classify_strategy(_healthy_overall(max_drawdown_pct=MAX_DRAWDOWN_PCT), _all_regimes())
    assert not any(r.startswith("N4") for r in v.failed_necessary)


def test_negative_expectancy_is_remove_when_sample_is_adequate():
    v = classify_strategy(
        _healthy_overall(profit_factor=0.98, expectancy=-27.6, net_profit=-16_160),
        _all_regimes(),
    )
    assert v.classification == "REMOVE"
    assert any(r.startswith("N1") for r in v.failed_necessary)


def test_small_sample_is_never_remove_even_with_no_edge():
    """N2 must dominate N1 — a 25-trade sample cannot support removal."""
    v = classify_strategy(
        _healthy_overall(trade_count=MIN_TRADES_FOR_VERDICT - 5,
                         profit_factor=0.5, expectancy=-100.0),
        _all_regimes(),
    )
    assert v.classification == "IMPROVE"
    assert any(r.startswith("N2") for r in v.failed_necessary)


def test_critical_defect_forces_remove_despite_good_statistics():
    """drl_strategy's case: PF > 1 over 1,189 trades but market-blind."""
    v = classify_strategy(
        _healthy_overall(trade_count=1189, profit_factor=1.07, expectancy=91.8),
        _all_regimes(),
        has_critical_defect=True,
        defect_note="market-blind: identical signals across opposite markets",
    )
    assert v.classification == "REMOVE"
    assert any("market-blind" in r for r in v.reasons)


def test_low_recovery_factor_blocks_keep():
    v = classify_strategy(
        _healthy_overall(net_profit=13_915, recovery_factor=1.21, max_drawdown_pct=11.5),
        _all_regimes(),
    )
    assert v.classification == "IMPROVE"
    assert any(r.startswith("Q1") for r in v.failed_quality)


def test_drawdown_unexplained_by_risk_model_blocks_keep():
    """Q2: 42.7% drawdown from only 4 consecutive losses at 3.5%/trade
    (expected ~14%) is 3.05x — risk arriving from outside the model."""
    v = classify_strategy(
        _healthy_overall(max_drawdown_pct=29.0, max_consecutive_losses=2,
                         recovery_factor=3.0),
        _all_regimes(),
    )
    assert v.classification == "IMPROVE"
    assert any(r.startswith("Q2") for r in v.failed_quality)


def test_drawdown_proportionate_to_streaks_passes_q2():
    """16.7% from 4 consecutive losses at 3.5% (expected 14%) = 1.19x."""
    v = classify_strategy(_healthy_overall(max_drawdown_pct=16.7, max_consecutive_losses=4), _all_regimes())
    assert not any(r.startswith("Q2") for r in v.failed_quality)


def test_single_regime_dependence_blocks_keep():
    regimes = {r: _regime(profit_factor=0.6, expectancy=-40.0) for r in REGIME_NAMES}
    regimes["sideways"] = _regime(profit_factor=2.0, expectancy=200.0)
    v = classify_strategy(_healthy_overall(), regimes)
    assert v.classification == "IMPROVE"
    assert any(r.startswith("Q3") for r in v.failed_quality)


def test_regimes_with_thin_samples_count_neither_way():
    regimes = _all_regimes()
    regimes["gap_day"] = _regime(trade_count=1, profit_factor=0.1, expectancy=-500.0)
    v = classify_strategy(_healthy_overall(), regimes)
    assert v.classification == "KEEP"
    assert v.regimes_traded == len(REGIME_NAMES) - 1


def test_recovery_factor_exactly_at_the_minimum_is_allowed():
    v = classify_strategy(_healthy_overall(recovery_factor=MIN_RECOVERY_FACTOR), _all_regimes())
    assert not any(r.startswith("Q1") for r in v.failed_quality)


def test_infinity_profit_factor_is_handled():
    v = classify_strategy(_healthy_overall(profit_factor="Infinity"), _all_regimes())
    assert v.classification == "KEEP"
