"""KEEP / IMPROVE / REMOVE classification from a strategy's aggregate and
per-regime metrics.

Deliberately conservative per the explicit instruction this framework was
built to satisfy: "Do not recommend removing a strategy based on a single
backtest... supported by robust evidence across multiple historical
periods and market conditions." A strategy only gets REMOVE if it is
losing money BOTH in aggregate AND in most regimes it actually traded in,
with enough trades for that to be a real signal rather than noise. A
strategy with too few trades to judge gets flagged as inconclusive, never
silently forced into KEEP or REMOVE.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .regimes import REGIME_NAMES

__all__ = ["Verdict", "classify_strategy", "MIN_TRADES_FOR_VERDICT"]

#: Below this many aggregate trades, there isn't enough evidence for a
#: confident KEEP or REMOVE call — classified IMPROVE with an explicit
#: "insufficient data" reason instead.
MIN_TRADES_FOR_VERDICT = 30


@dataclass
class Verdict:
    classification: str  # "KEEP" | "IMPROVE" | "REMOVE"
    reasons: list[str] = field(default_factory=list)
    regimes_profitable: int = 0
    regimes_traded: int = 0


def _regime_is_profitable(regime_metrics: dict) -> bool | None:
    """True/False if this regime has enough trades to judge, None if it
    wasn't traded (or barely was) — a regime with 0-2 trades isn't
    evidence of anything, shouldn't count against or for a verdict."""
    if regime_metrics.get("trade_count", 0) < 3:
        return None
    pf = regime_metrics.get("profit_factor")
    expectancy = regime_metrics.get("expectancy")
    if pf == "Infinity":
        return True
    if pf is None:
        return None
    return bool(pf >= 1.0 and (expectancy or 0) > 0)


def classify_strategy(overall: dict, by_regime: dict) -> Verdict:
    trade_count = overall.get("trade_count", 0)
    reasons: list[str] = []

    regime_results = {r: _regime_is_profitable(by_regime.get(r, {})) for r in REGIME_NAMES}
    regimes_traded = sum(1 for v in regime_results.values() if v is not None)
    regimes_profitable = sum(1 for v in regime_results.values() if v is True)
    regimes_unprofitable = sum(1 for v in regime_results.values() if v is False)

    if trade_count < MIN_TRADES_FOR_VERDICT:
        reasons.append(
            f"Only {trade_count} trades in the validated window (need >= "
            f"{MIN_TRADES_FOR_VERDICT} for a confident verdict) — insufficient "
            f"evidence for KEEP or REMOVE either way."
        )
        return Verdict("IMPROVE", reasons, regimes_profitable, regimes_traded)

    pf = overall.get("profit_factor")
    expectancy = overall.get("expectancy", 0) or 0
    net_profit = overall.get("net_profit", 0)
    max_dd = overall.get("max_drawdown_pct", 0) or 0
    pf_numeric = float("inf") if pf == "Infinity" else (pf if pf is not None else 0.0)

    overall_profitable = pf_numeric >= 1.0 and expectancy > 0 and net_profit > 0

    if (
        overall_profitable
        and regimes_traded >= 3
        and regimes_profitable >= max(3, regimes_traded - 1)
        and max_dd < 30.0
        and pf_numeric >= 1.3
    ):
        reasons.append(f"Profitable overall (PF={pf}, expectancy={expectancy}, net={net_profit}).")
        reasons.append(f"Profitable in {regimes_profitable}/{regimes_traded} regimes actually traded.")
        reasons.append(f"Max drawdown {max_dd}% within bounds.")
        return Verdict("KEEP", reasons, regimes_profitable, regimes_traded)

    if (
        not overall_profitable
        and regimes_traded >= 3
        and regimes_unprofitable >= max(3, regimes_traded - 1)
        and pf_numeric < 1.0
    ):
        reasons.append(f"Losing overall (PF={pf}, expectancy={expectancy}, net={net_profit}).")
        reasons.append(f"Unprofitable in {regimes_unprofitable}/{regimes_traded} regimes actually traded — not a single-regime fluke.")
        return Verdict("REMOVE", reasons, regimes_profitable, regimes_traded)

    # Everything in between: profitable overall but not robustly across
    # regimes, or marginal PF, or losing overall but only in a minority
    # of regimes traded — real potential, not yet production-grade.
    reasons.append(f"Overall PF={pf}, expectancy={expectancy}, net={net_profit}.")
    reasons.append(f"Profitable in {regimes_profitable}/{regimes_traded} regimes traded — mixed, not consistent enough for KEEP or REMOVE.")
    if max_dd >= 30.0:
        reasons.append(f"Max drawdown {max_dd}% is a real concern even where profitable.")
    return Verdict("IMPROVE", reasons, regimes_profitable, regimes_traded)
