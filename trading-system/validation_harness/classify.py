"""Production-readiness gating for validated strategies.

=============================================================================
WHY PROFIT FACTOR >= 1.30 WAS REPLACED AS THE PRIMARY GATE (2026-08-08)
=============================================================================

The original criteria used `profit_factor >= 1.30` as the discriminating
test for KEEP. Re-evaluated objectively against all 12 validated
strategies, that gate is both *mechanically redundant* and *blind to
risk*:

1. **PF carries no information beyond win rate and R:R.** For any
   strategy, PF = (WR / (1 - WR)) x (avg_win / avg_loss). Verified
   against actuals on the 123-day window:
       institutional_momentum  (0.727/0.273) x 0.46 = 1.22  (observed 1.22)
       ema_rsi                 (0.721/0.279) x 0.53 = 1.37  (observed 1.38)
       ema_crossover           (0.800/0.200) x 0.43 = 1.72  (observed 1.71)
   Gating on PF is therefore gating on a quantity already fully
   determined by two other reported metrics — it adds no independent
   signal.

2. **PF barely discriminates in this system.** Across all 12 strategies
   it spans only 0.98-1.71, with 8 of 12 inside 1.10-1.41. An
   option-buying system with structurally sub-1.0 realized R:R
   (0.41-0.58 suite-wide, because the premium-banded stop is wider than
   the typical trailing exit) mathematically cannot produce the PF
   values a futures/equity trend system would. A 1.30 bar imported from
   that context is not meaningful here.

3. **PF is silent on risk, which is what actually ends accounts.**
   Under the old gate, `ema_rsi` (PF 1.38) passed with a **47.9%**
   drawdown while `institutional_momentum` (PF 1.22) failed with a
   **16.7%** drawdown — the exact inversion of production-readiness.

The framework below replaces it. Every threshold is derived from a
stated principle, not fitted to make any strategy pass. As evidence of
that: applying it **demotes the two highest-net-profit strategies in the
suite** (`advanced_ai`, `ema_rsi`) on survivability grounds. A gate
reverse-engineered to flatter the portfolio would not do that.

=============================================================================
THE FRAMEWORK
=============================================================================

NECESSARY conditions (all must hold; failing any one blocks KEEP):

  N1. Edge exists: expectancy > 0 AND profit_factor > 1.0.
      Not arbitrary — this is the definition of an edge. Below it, no
      amount of risk management helps.

  N2. Sample sufficiency: trade_count >= 30.
      Standard central-limit minimum for a trustworthy mean estimate.
      Below this, neither KEEP nor REMOVE is supportable.

  N3. No unresolved critical defect.
      Statistics cannot see a broken strategy. `drl_strategy` posts
      PF 1.07 over 1,189 trades while being provably market-blind
      (identical signals for a +7,500pt uptrend and a -7,500pt
      downtrend). A defect gate is what catches that.

  N4. Survivability: max_drawdown <= MAX_DRAWDOWN_PCT (30%).
      Derived from recovery asymmetry, not preference: recovering a
      drawdown D requires a gain of D/(1-D). At 20% that is +25%; at
      30%, +43%; at 50%, +100%; at 60%, +150%. Past roughly 30% the
      arithmetic turns hostile and a single further bad streak becomes
      unrecoverable. This is the survivability line.

QUALITY conditions (all must hold for KEEP; used to rank otherwise):

  Q1. Risk-adjusted return: recovery_factor >= MIN_RECOVERY_FACTOR (2.0).
      recovery_factor = net_profit / max_drawdown. Below 1.0 the worst
      drawdown exceeded total profit. 2.0 means the strategy earned at
      least twice its worst drawdown over the window — the minimum for
      the risk taken to have been worthwhile.

  Q2. Drawdown is explained by the risk model:
      max_drawdown / (max_consecutive_losses x risk_per_trade)
          <= MAX_DRAWDOWN_EXPLAINED_RATIO (2.0).
      A strategy risking R per trade that suffers C consecutive losses
      should see a drawdown near C x R. A ratio near 1.0 means drawdown
      is fully accounted for by ordinary losing streaks at the
      configured risk. A large ratio means drawdown is arriving from
      somewhere the risk model does not describe — correlated or
      overlapping losses, or losses exceeding the designed per-trade
      risk (gap-throughs, slippage). That is a risk-model violation
      regardless of profitability, and it is invisible to PF, net
      profit, and even recovery factor.

  Q3. Regime robustness: profitable in a strict majority of regimes that
      carry an adequate sample (>= MIN_REGIME_TRADES trades).
      A strategy dependent on one market condition is not
      production-ready; it is an unhedged bet on that condition
      persisting.

Anything failing a NECESSARY condition can never be KEEP. REMOVE is
reserved for strategies that fail N1 or N3 *and* have been shown not to
be repairable by evidence-based change — deliberately conservative, per
the project rule that removal must not rest on a single backtest.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from .regimes import REGIME_NAMES

__all__ = [
    "Verdict", "classify_strategy",
    "MIN_TRADES_FOR_VERDICT", "MAX_DRAWDOWN_PCT", "MIN_RECOVERY_FACTOR",
    "MAX_DRAWDOWN_EXPLAINED_RATIO", "MIN_REGIME_TRADES", "DEFAULT_RISK_PER_TRADE",
]

#: N2 — central-limit minimum for a trustworthy mean estimate.
MIN_TRADES_FOR_VERDICT = 30

#: N4 — survivability. Recovering D requires D/(1-D); past ~30% (+43%)
#: the arithmetic turns hostile. See module docstring.
MAX_DRAWDOWN_PCT = 30.0

#: Q1 — must earn at least 2x the worst drawdown for the risk to be worth it.
MIN_RECOVERY_FACTOR = 2.0

#: Q2 — drawdown beyond 2x what consecutive losses at the configured
#: per-trade risk would produce indicates risk arriving from outside the
#: risk model.
MAX_DRAWDOWN_EXPLAINED_RATIO = 2.0

#: A regime needs at least this many trades before it counts as evidence
#: either way (matches the pre-existing convention).
MIN_REGIME_TRADES = 3

#: Live per-trade risk fraction. NOTE: production currently runs the 3.5%
#: high-confidence tier because `enable_ai_filter` is unset, so
#: confidence defaults to 1.0 and clears the 0.85 bar. All validation was
#: run at this tier, so Q2 is computed against it.
DEFAULT_RISK_PER_TRADE = 0.035


@dataclass
class Verdict:
    classification: str  # "KEEP" | "IMPROVE" | "REMOVE"
    reasons: list[str] = field(default_factory=list)
    regimes_profitable: int = 0
    regimes_traded: int = 0
    failed_necessary: list[str] = field(default_factory=list)
    failed_quality: list[str] = field(default_factory=list)


def _as_float(value, default=0.0) -> float:
    if value == "Infinity":
        return float("inf")
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _regime_is_profitable(regime_metrics: dict) -> Optional[bool]:
    """True/False when the regime carries enough trades to judge, None
    when it does not (so it counts neither for nor against)."""
    if regime_metrics.get("trade_count", 0) < MIN_REGIME_TRADES:
        return None
    pf = regime_metrics.get("profit_factor")
    if pf is None:
        return None
    if pf == "Infinity":
        return True
    return bool(_as_float(pf) >= 1.0 and _as_float(regime_metrics.get("expectancy")) > 0)


def classify_strategy(
    overall: dict,
    by_regime: dict,
    has_critical_defect: bool = False,
    defect_note: str = "",
    risk_per_trade: float = DEFAULT_RISK_PER_TRADE,
) -> Verdict:
    trade_count = int(overall.get("trade_count", 0) or 0)
    pf = _as_float(overall.get("profit_factor"))
    expectancy = _as_float(overall.get("expectancy"))
    net_profit = _as_float(overall.get("net_profit"))
    max_dd = _as_float(overall.get("max_drawdown_pct"))
    recovery = _as_float(overall.get("recovery_factor"))
    consec = int(overall.get("max_consecutive_losses", 0) or 0)

    regime_results = {r: _regime_is_profitable(by_regime.get(r, {})) for r in REGIME_NAMES}
    regimes_traded = sum(1 for v in regime_results.values() if v is not None)
    regimes_profitable = sum(1 for v in regime_results.values() if v is True)

    reasons: list[str] = []
    failed_necessary: list[str] = []
    failed_quality: list[str] = []

    # ---- NECESSARY ------------------------------------------------------
    if has_critical_defect:
        failed_necessary.append(f"N3 unresolved critical defect: {defect_note or 'see audit'}")
    if trade_count < MIN_TRADES_FOR_VERDICT:
        failed_necessary.append(
            f"N2 sample too small ({trade_count} trades < {MIN_TRADES_FOR_VERDICT}) — "
            "neither KEEP nor REMOVE is supportable"
        )
    if not (expectancy > 0 and pf > 1.0):
        failed_necessary.append(f"N1 no edge (PF={pf:.2f}, expectancy={expectancy:.2f})")
    if max_dd > MAX_DRAWDOWN_PCT:
        needed = (max_dd / 100.0) / (1 - max_dd / 100.0) * 100.0
        failed_necessary.append(
            f"N4 survivability: {max_dd:.1f}% drawdown exceeds {MAX_DRAWDOWN_PCT:.0f}% "
            f"(recovering it requires +{needed:.0f}%)"
        )

    # ---- QUALITY --------------------------------------------------------
    if recovery < MIN_RECOVERY_FACTOR:
        failed_quality.append(
            f"Q1 recovery factor {recovery:.2f} < {MIN_RECOVERY_FACTOR} "
            "(did not earn twice its worst drawdown)"
        )
    expected_dd = consec * risk_per_trade * 100.0
    if expected_dd > 0:
        ratio = max_dd / expected_dd
        if ratio > MAX_DRAWDOWN_EXPLAINED_RATIO:
            failed_quality.append(
                f"Q2 drawdown unexplained by risk model: {max_dd:.1f}% is {ratio:.2f}x the "
                f"{expected_dd:.1f}% that {consec} consecutive losses at "
                f"{risk_per_trade*100:.1f}%/trade would produce"
            )
    if regimes_traded >= 2 and regimes_profitable * 2 <= regimes_traded:
        failed_quality.append(
            f"Q3 regime robustness: profitable in only {regimes_profitable}/{regimes_traded} "
            "adequately-sampled regimes"
        )

    # ---- VERDICT --------------------------------------------------------
    if not failed_necessary and not failed_quality:
        reasons.append(
            f"Passes all necessary and quality gates: PF={pf:.2f}, expectancy={expectancy:.2f}, "
            f"net={net_profit:.0f}, drawdown={max_dd:.1f}%, recovery={recovery:.2f}, "
            f"profitable in {regimes_profitable}/{regimes_traded} regimes."
        )
        return Verdict("KEEP", reasons, regimes_profitable, regimes_traded, failed_necessary, failed_quality)

    reasons.extend(failed_necessary)
    reasons.extend(failed_quality)

    # REMOVE only for a broken or edgeless strategy — never for risk
    # profile alone, and never on a small sample.
    edgeless = any(r.startswith("N1") for r in failed_necessary)
    defective = any(r.startswith("N3") for r in failed_necessary)
    too_small = any(r.startswith("N2") for r in failed_necessary)
    if defective or (edgeless and not too_small):
        return Verdict("REMOVE", reasons, regimes_profitable, regimes_traded, failed_necessary, failed_quality)

    return Verdict("IMPROVE", reasons, regimes_profitable, regimes_traded, failed_necessary, failed_quality)
