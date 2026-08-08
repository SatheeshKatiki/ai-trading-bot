"""Before/after validation for a change to the shared exit engine.

    python -m validation_harness.run_ab_validation --strategies ema_rsi ...

BEFORE comes from the cached day-isolated trade sets in `results/`
(`trades_<strategy>.pkl`, written by `run_dd_attribution.py` before the
change). AFTER is a fresh day-isolated run of the same strategy over the
same window through the changed code.

Using a cache as the baseline is only sound if the harness is
deterministic, so that is not assumed: `--verify-baseline` re-runs a
strategy through the CURRENT code with the change reverted and asserts it
reproduces its cache trade-for-trade. That was checked when this script
was written (5 strategies, all bit-identical), which is what licenses
comparing against the caches here.

Emits a full metric table, the exit-reason mix, and per-regime breakdowns,
using the same `compute_metrics`/`classify_daily_regimes` the standing
validation report uses, so the numbers reconcile with it.
"""
from __future__ import annotations

import argparse
import json
import pickle
import sys
from pathlib import Path

import pandas as pd

from .metrics import compute_metrics
from .regimes import REGIME_NAMES, classify_daily_regimes
from .run_validation import _reset_cross_strategy_singletons, run_strategy_day_isolated

RESULTS_DIR = Path(__file__).parent / "results"

#: (metric, direction) where direction is "up" if a higher value is better,
#: "down" if lower is better, and None if it is neither — descriptive only,
#: so the table does not editorialise about a number that has no good side.
KEY_METRICS = [
    ("trade_count", None), ("net_profit", "up"), ("net_profit_pct", "up"),
    ("profit_factor", "up"), ("win_rate_pct", None), ("expectancy", "up"),
    ("max_drawdown_pct", "down"), ("recovery_factor", "up"),
    ("max_consecutive_losses", "down"), ("avg_trade", "up"),
    ("avg_holding_minutes", None), ("avg_risk_reward", "up"),
    ("gross_profit", "up"), ("gross_loss", "down"),
]


def _fmt(v) -> str:
    if v is None:
        return "—"
    if isinstance(v, bool):
        return str(v)
    if isinstance(v, float):
        return f"{v:,.2f}"
    if isinstance(v, int):
        return f"{v:,}"
    return str(v)


def _delta(before, after, direction) -> str:
    if not isinstance(before, (int, float)) or not isinstance(after, (int, float)):
        return "—"
    d = after - before
    if abs(d) < 1e-9:
        return "unchanged"
    if direction is None:
        return f"{d:+,.2f}"
    better = (d > 0) if direction == "up" else (d < 0)
    return f"{d:+,.2f} {'BETTER' if better else 'WORSE'}"


def _reason_mix(trades) -> pd.Series:
    """Collapse a reason to its mechanism, keeping the two trailing stops
    apart — they are independent mechanisms and which one fires is the
    whole question."""
    def label(r: str) -> str:
        return r if r.startswith("Trailing Stop-Loss Hit (Offset)") else r.split("(")[0].strip()
    return pd.Series([label(t.exit_reason) for t in trades]).value_counts()


def _regime_metrics(trades, df, capital) -> dict:
    labels = classify_daily_regimes(df)
    out = {}
    for regime in REGIME_NAMES:
        dates = set(labels[labels == regime].index)
        if not dates:
            out[regime] = {"trade_count": 0}
            continue
        sel = [t for t in trades if pd.Timestamp(t.entry_time).date() in dates]
        out[regime] = compute_metrics(sel, capital)
    return out


def _same_trades(a, b) -> bool:
    return len(a) == len(b) and all(
        x.symbol == y.symbol and x.entry_time == y.entry_time
        and x.exit_time == y.exit_time and abs(x.pnl - y.pnl) < 1e-9
        and x.exit_reason == y.exit_reason
        for x, y in zip(a, b)
    )


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--strategies", nargs="+", default=["ema_rsi"],
                    help="first one gets the detailed per-regime treatment")
    ap.add_argument("--data-path", default="data/NSE_NIFTY50-INDEX_5Min.csv")
    ap.add_argument("--start", default="2026-02-01")
    ap.add_argument("--end", default="2026-07-31")
    ap.add_argument("--instrument", default="NIFTY")
    ap.add_argument("--initial-capital", type=float, default=100_000.0)
    ap.add_argument("--verify-baseline", action="store_true",
                    help="assert a re-run reproduces the cache (run with the change reverted)")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    df = pd.read_csv(args.data_path)
    df["datetime"] = pd.to_datetime(df["datetime"])
    df = df.set_index("datetime").loc[args.start:args.end]

    from trading_bot.strategies.registry import registry  # noqa: F401
    from . import harness  # noqa: F401  (registers MARL_Ultra)

    cap = args.initial_capital
    results: dict[str, dict] = {}

    for name in args.strategies:
        cache = RESULTS_DIR / f"trades_{name}.pkl"
        if not cache.exists():
            print(f"  skipping {name}: no cached baseline at {cache}", file=sys.stderr)
            continue
        with open(cache, "rb") as f:
            before_trades = pickle.load(f)
        print(f"Running {name} AFTER...", file=sys.stderr)
        # Same cross-strategy singleton hygiene `run_full_validation` applies
        # before every strategy — without it, one strategy's leaked
        # module-level state (notably MARL's RiskAgent) shows up here as a
        # difference this change did not cause.
        _reset_cross_strategy_singletons()
        after_trades, _ = run_strategy_day_isolated(name, df, args.instrument, cap)
        results[name] = {
            "before_trades": before_trades, "after_trades": after_trades,
            "before": compute_metrics(before_trades, cap),
            "after": compute_metrics(after_trades, cap),
            "baseline_reproduced": _same_trades(before_trades, after_trades)
            if args.verify_baseline else None,
        }

    if not results:
        sys.exit("No strategies with cached baselines.")

    L: list[str] = []
    A = L.append
    A("# Validation before/after — partial-booking runner re-baseline\n")
    A(f"Window: {df.index.min()} → {df.index.max()} "
      f"({df.index.normalize().nunique()} trading days)  ")
    A(f"Capital: Rs {cap:,.0f}  ")
    A("Day-isolated, fresh RiskManager per day, full production pipeline. "
      "BEFORE is each strategy's cached pre-change trade set; AFTER is a "
      "fresh run through the changed engine over the same data.\n")

    if args.verify_baseline:
        A("## Baseline reproduction check\n")
        A("| Strategy | Cache reproduced trade-for-trade? |")
        A("|---|---|")
        for name, r in results.items():
            A(f"| {name} | {'YES' if r['baseline_reproduced'] else '**NO**'} |")
        A("")

    A("## Summary across strategies\n")
    A("| Strategy | Trades B→A | Net B | Net A | Net Δ | PF B→A | DD% B→A | Recovery B→A |")
    A("|---|---|---|---|---|---|---|---|")
    for name, r in results.items():
        b, a = r["before"], r["after"]
        A(f"| {name} | {b['trade_count']}→{a['trade_count']} | "
          f"{_fmt(b['net_profit'])} | {_fmt(a['net_profit'])} | "
          f"{a['net_profit'] - b['net_profit']:+,.0f} | "
          f"{b['profit_factor']}→{a['profit_factor']} | "
          f"{b['max_drawdown_pct']}→{a['max_drawdown_pct']} | "
          f"{b['recovery_factor']}→{a['recovery_factor']} |")
    A("")

    primary = args.strategies[0]
    if primary in results:
        r = results[primary]
        A(f"## `{primary}` — full metric detail\n")
        A("| Metric | Before | After | Change |")
        A("|---|---|---|---|")
        for key, direction in KEY_METRICS:
            A(f"| {key} | {_fmt(r['before'].get(key))} | {_fmt(r['after'].get(key))} | "
              f"{_delta(r['before'].get(key), r['after'].get(key), direction)} |")
        A("")

        A(f"### `{primary}` — exit-reason mix\n")
        bm, am = _reason_mix(r["before_trades"]), _reason_mix(r["after_trades"])
        A("| Exit reason | Before | After |")
        A("|---|---|---|")
        for reason in sorted(set(bm.index) | set(am.index)):
            A(f"| `{reason}` | {int(bm.get(reason, 0))} | {int(am.get(reason, 0))} |")
        A("")

        A(f"### `{primary}` — by regime\n")
        br = _regime_metrics(r["before_trades"], df, cap)
        ar = _regime_metrics(r["after_trades"], df, cap)
        A("| Regime | Trades B→A | Net B | Net A | PF B | PF A | DD% B | DD% A |")
        A("|---|---|---|---|---|---|---|---|")
        for regime in REGIME_NAMES:
            b, a = br[regime], ar[regime]
            if not b.get("trade_count") and not a.get("trade_count"):
                continue
            A(f"| {regime} | {b.get('trade_count',0)}→{a.get('trade_count',0)} | "
              f"{_fmt(b.get('net_profit'))} | {_fmt(a.get('net_profit'))} | "
              f"{_fmt(b.get('profit_factor'))} | {_fmt(a.get('profit_factor'))} | "
              f"{_fmt(b.get('max_drawdown_pct'))} | {_fmt(a.get('max_drawdown_pct'))} |")
        A("")

    out = Path(args.out or (RESULTS_DIR / "ab_validation.md"))
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(L), encoding="utf-8")
    (RESULTS_DIR / "ab_validation.json").write_text(
        json.dumps({k: {"before": v["before"], "after": v["after"]} for k, v in results.items()},
                   indent=2, default=str),
        encoding="utf-8",
    )
    for name, r in results.items():
        with open(RESULTS_DIR / f"trades_{name}_after.pkl", "wb") as f:
            pickle.dump(r["after_trades"], f)
    print(f"Written {out}", file=sys.stderr)


if __name__ == "__main__":
    main()
