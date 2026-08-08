"""Renders a `run_validation.run_full_validation()` report dict into the
final ranked markdown comparison report."""
from __future__ import annotations

import json
from pathlib import Path

from .classify import classify_strategy
from .regimes import REGIME_NAMES

__all__ = ["render_markdown_report", "KNOWN_CRITICAL_DEFECTS"]

#: Defects proven by execution that statistics cannot see. Feeds gate N3.
#: See docs/STRATEGY_IMPROVEMENT_BACKLOG.md for the evidence behind each.
KNOWN_CRITICAL_DEFECTS = {
    "drl_strategy": (
        "market-blind — a +7,500pt uptrend and a -7,500pt downtrend produce "
        "byte-identical signals (286 BUY / 0 SELL in both); constant observation "
        "vector plus a collapsed model artifact, and attaching real features "
        "changed nothing"
    ),
}


def _fmt(v):
    if v is None:
        return "—"
    return v


def render_markdown_report(report: dict, title: str = "Production Strategy Validation Report") -> str:
    lines: list[str] = []
    lines.append(f"# {title}\n")
    lines.append(
        f"**Instrument:** {report['instrument']} | **Period:** {report['date_range'][0]} → "
        f"{report['date_range'][1]} | **Trading days:** {report['total_days']} | "
        f"**Initial capital per day-isolated run:** ₹{report['initial_capital']:,.0f}\n"
    )
    lines.append(f"**Regime day counts:** {report['regime_day_counts']}\n")
    lines.append("---\n")

    verdicts = {}
    for name, strat in report["strategies"].items():
        defect = KNOWN_CRITICAL_DEFECTS.get(name)
        verdicts[name] = classify_strategy(
            strat["overall"], strat["by_regime"],
            has_critical_defect=defect is not None,
            defect_note=defect or "",
        )

    order = {"KEEP": 0, "IMPROVE": 1, "REMOVE": 2}
    ranked = sorted(
        report["strategies"].items(),
        key=lambda kv: (
            order.get(verdicts[kv[0]].classification, 3),
            -(kv[1]["overall"].get("net_profit") or -1e18),
        ),
    )

    lines.append("## Ranking (best → worst)\n")
    lines.append("| Rank | Strategy | Verdict | Trades | Net Profit | Profit Factor | Win Rate | Max DD |")
    lines.append("|---|---|---|---|---|---|---|---|")
    for i, (name, strat) in enumerate(ranked, 1):
        m = strat["overall"]
        v = verdicts[name]
        lines.append(
            f"| {i} | {name} | **{v.classification}** | {m['trade_count']} | "
            f"₹{_fmt(m['net_profit'])} | {_fmt(m['profit_factor'])} | {_fmt(m['win_rate_pct'])}% | "
            f"{_fmt(m['max_drawdown_pct'])}% |"
        )
    lines.append("")

    counts = {"KEEP": 0, "IMPROVE": 0, "REMOVE": 0}
    for v in verdicts.values():
        counts[v.classification] += 1
    lines.append("## Summary\n")
    lines.append(f"- Total strategies evaluated: {len(verdicts)}")
    lines.append(f"- KEEP (production-ready): {counts['KEEP']}")
    lines.append(f"- IMPROVE (potential, needs work): {counts['IMPROVE']}")
    lines.append(f"- REMOVE (no sustainable edge): {counts['REMOVE']}")
    lines.append("")
    lines.append("---\n")

    lines.append("## Per-strategy detail\n")
    for name, strat in ranked:
        m = strat["overall"]
        v = verdicts[name]
        lines.append(f"### {name} — {v.classification}\n")
        lines.append(f"**Reasons:** {' '.join(v.reasons)}\n")
        lines.append(
            f"**Overall:** trades={m['trade_count']}, net_profit=₹{_fmt(m['net_profit'])} "
            f"({_fmt(m['net_profit_pct'])}%), profit_factor={_fmt(m['profit_factor'])}, "
            f"win_rate={_fmt(m['win_rate_pct'])}%, expectancy=₹{_fmt(m['expectancy'])}, "
            f"max_drawdown={_fmt(m['max_drawdown_pct'])}%, recovery_factor={_fmt(m['recovery_factor'])}, "
            f"max_consecutive_losses={m['max_consecutive_losses']}, avg_trade=₹{_fmt(m['avg_trade'])}, "
            f"avg_holding={_fmt(m['avg_holding_minutes'])}min, realized_R:R={_fmt(m['avg_risk_reward'])}\n"
        )
        lines.append(
            f"**Diagnostics:** candidate_signals={m.get('candidate_signals', '—')}, "
            f"rejected_untradeable_sl={m.get('rejected_untradeable_sl', '—')}, "
            f"rejected_risk_gate={m.get('rejected_risk_gate', '—')}, "
            f"rejected_market_hours={m.get('rejected_market_hours', '—')}, "
            f"elapsed={strat.get('elapsed_seconds', '—')}s\n"
        )
        lines.append("| Regime | Trades | Net Profit | Profit Factor | Win Rate | Expectancy |")
        lines.append("|---|---|---|---|---|---|")
        for regime in REGIME_NAMES:
            rm = strat["by_regime"].get(regime, {})
            if rm.get("trade_count", 0) == 0:
                lines.append(f"| {regime} | 0 | — | — | — | — |")
            else:
                lines.append(
                    f"| {regime} | {rm['trade_count']} | ₹{_fmt(rm.get('net_profit'))} | "
                    f"{_fmt(rm.get('profit_factor'))} | {_fmt(rm.get('win_rate_pct'))}% | "
                    f"₹{_fmt(rm.get('expectancy'))} |"
                )
        lines.append("")

    return "\n".join(lines)


if __name__ == "__main__":
    import sys

    in_path = sys.argv[1] if len(sys.argv) > 1 else "validation_harness/results/latest_report.json"
    out_path = sys.argv[2] if len(sys.argv) > 2 else "validation_harness/results/latest_report.md"
    with open(in_path, "r", encoding="utf-8") as f:
        report = json.load(f)
    md = render_markdown_report(report)
    Path(out_path).write_text(md, encoding="utf-8")
    print(f"Wrote {out_path}")
