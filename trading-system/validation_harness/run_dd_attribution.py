"""Runner for backlog #3: is max drawdown concentrated in cheap,
near-expiry contracts?

Collects each strategy's simulated trades (day-isolated, the same way
`run_validation.py` does, so the numbers reconcile with the validation
report) and runs `drawdown_attribution` over them.

Trades are cached to `results/trades_<strategy>.pkl`. A full sweep is
~45 minutes; every later diagnostic that needs trade-level data (exit
quality, contract attribution, holding-time studies) can then load the
cache instead of re-running the harness. `--refresh` forces a re-run.

    python -m validation_harness.run_dd_attribution
    python -m validation_harness.run_dd_attribution --strategies ema_rsi drl_strategy
    python -m validation_harness.run_dd_attribution --refresh
"""
from __future__ import annotations

import argparse
import pickle
import sys
from pathlib import Path

import pandas as pd

from .drawdown_attribution import annotate_contracts, attribute_drawdown, cohort_grid
from .run_validation import run_strategy_day_isolated

RESULTS_DIR = Path(__file__).parent / "results"


def load_or_run(strategy: str, df: pd.DataFrame, instrument: str,
                initial_capital: float, refresh: bool) -> list:
    cache = RESULTS_DIR / f"trades_{strategy}.pkl"
    if cache.exists() and not refresh:
        with open(cache, "rb") as f:
            trades = pickle.load(f)
        print(f"  {strategy:24s} {len(trades):5d} trades (cached)", file=sys.stderr)
        return trades

    trades, _diag = run_strategy_day_isolated(
        strategy, df, instrument=instrument, initial_capital=initial_capital,
    )
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    with open(cache, "wb") as f:
        pickle.dump(trades, f)
    print(f"  {strategy:24s} {len(trades):5d} trades (ran)", file=sys.stderr)
    return trades


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-path", default="data/NSE_NIFTY50-INDEX_5Min.csv")
    parser.add_argument("--start", default="2026-02-01")
    parser.add_argument("--end", default="2026-07-31")
    parser.add_argument("--strategies", nargs="+", default=None)
    parser.add_argument("--instrument", default="NIFTY")
    parser.add_argument("--initial-capital", type=float, default=100_000.0)
    parser.add_argument("--refresh", action="store_true",
                        help="re-run the harness even if a trade cache exists")
    parser.add_argument("--out", default="validation_harness/results/dd_attribution.md")
    args = parser.parse_args()

    df = pd.read_csv(args.data_path)
    df["datetime"] = pd.to_datetime(df["datetime"])
    df = df.set_index("datetime")
    if args.start:
        df = df.loc[args.start:]
    if args.end:
        df = df.loc[:args.end]

    from trading_bot.strategies.registry import registry
    # Import for its registration side effect only — "MARL_Ultra" exists
    # solely because harness.py registers it (see that module's comment).
    from . import harness  # noqa: F401
    strategies = args.strategies or sorted(set(registry.registered_strategies))

    lines: list[str] = []
    lines.append("# Drawdown attribution — cheap, near-expiry contracts (backlog #3)\n")
    lines.append(f"Window: {df.index.min()} to {df.index.max()}  ")
    lines.append(f"Capital: Rs {args.initial_capital:,.0f}  ")
    lines.append("Cohort: entry premium < Rs 50 AND days-to-expiry <= 1\n")
    lines.append("`dd_excl` is an attribution, not a filter forecast — see "
                 "`drawdown_attribution.py`'s module docstring.\n")
    lines.append("| Strategy | Trades | Cohort n | % trades | % gross loss | DD % | DD excl % | Delta | Net | Net excl |")
    lines.append("|---|---|---|---|---|---|---|---|---|---|")

    per_strategy: dict[str, pd.DataFrame] = {}

    for name in strategies:
        trades = load_or_run(name, df, args.instrument, args.initial_capital, args.refresh)
        annotated = annotate_contracts(trades)
        if annotated.empty:
            lines.append(f"| {name} | 0 | — | — | — | — | — | — | — | — |")
            continue
        per_strategy[name] = annotated
        a = attribute_drawdown(annotated, args.initial_capital)
        lines.append(
            f"| {name} | {a['trade_count']} | {a['cohort_trades']} | "
            f"{a['share_trades_pct']}% | {a['share_gross_loss_pct']}% | "
            f"{a['dd_pct']}% | {a['dd_pct_excl']}% | {a['dd_pct_delta']}% | "
            f"{a['net_pnl']:,.0f} | {a['net_pnl_excl']:,.0f} |"
        )

    lines.append("\n## Max-drawdown window composition\n")
    lines.append("P&L inside the actual peak-to-trough segment that produced each max DD.\n")
    lines.append("| Strategy | Window trades | Cohort trades | Cohort P&L | Other P&L | Cohort share of the loss |")
    lines.append("|---|---|---|---|---|---|")
    for name, annotated in per_strategy.items():
        a = attribute_drawdown(annotated, args.initial_capital)
        lines.append(
            f"| {name} | {a['dd_window_trades']} | {a['in_window_cohort_trades']} | "
            f"{a['in_window_cohort_pnl']:,.0f} | {a['in_window_rest_pnl']:,.0f} | "
            f"{a['in_window_cohort_share_pct']}% |"
        )

    lines.append("\n## Premium band x DTE grid (threshold check)\n")
    for name, annotated in per_strategy.items():
        grid = cohort_grid(annotated)
        lines.append(f"\n### {name}\n")
        lines.append("| Premium | DTE | n | Net | Gross loss | Win rate |")
        lines.append("|---|---|---|---|---|---|")
        for _, r in grid.iterrows():
            lines.append(
                f"| {r['prem_band']} | {r['dte_bucket']} | {r['n']} | "
                f"{r['net']:,.0f} | {r['gross_loss']:,.0f} | {r['win_rate']}% |"
            )

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"\nWritten to {out_path}", file=sys.stderr)
    print("\n".join(lines[:20]))


if __name__ == "__main__":
    main()
