"""Ablation of the production entry filters and the daily trade cap.

    python -m validation_harness.run_filter_ablation --strategy ema_rsi

Answers, one variable at a time: for each of the four institutional
filters and for `max_trades_per_day`, what does it actually remove — bad
trades, or opportunities?

Method
------
Every configuration is a full 123-day day-isolated run through the real
production pipeline, so trade sequencing, position sizing and every risk
gate move with the change rather than being held artificially fixed.
Three families, deliberately separated:

  LOO   leave-one-out from production — the direct measure of what one
        filter costs or saves ON TOP of the others it actually runs with.
  SOLO  each filter alone against the unfiltered path — the filter's own
        effect, free of interaction with the other three.
  CAP   the daily trade cap swept with the filters held at production.

For each LOO config the trades that appear when the filter is removed are
isolated by (symbol, entry_time) and scored on their own: that cohort IS
the filter's opportunity cost, and its first-touch record says whether
the filter was removing bad entries or good ones.

Everything shared across configs is computed once so the comparison is
exact: the rally set comes from the underlying alone (identical for every
config — only COVERAGE changes), and signal frames are cached per filter
combination.
"""
from __future__ import annotations

import argparse
import json
import pickle
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from shared.risk import RiskManager

from .classify import DEFAULT_RISK_PER_TRADE, classify_strategy
from .entry_quality import annotate_entries, build_signal_frame, find_missed_runs
from .metrics import compute_metrics
from .production_settings import load_production_settings
from .regimes import REGIME_NAMES, classify_daily_regimes
from .run_validation import _reset_cross_strategy_singletons, run_strategy_day_isolated

RESULTS_DIR = Path(__file__).parent / "results"

FILTERS = ("enable_squeeze_filter", "enable_extension_filter",
           "enable_cpr_filter", "enable_aggression_filter")
SHORT = {"enable_squeeze_filter": "squeeze", "enable_extension_filter": "extension",
         "enable_cpr_filter": "cpr", "enable_aggression_filter": "aggression"}


def _filter_key(settings: dict) -> tuple:
    return tuple(bool(settings.get(f, False)) for f in FILTERS)


def _cap_of(settings: dict) -> int:
    from .production_settings import resolve_max_trades_per_day
    return resolve_max_trades_per_day(settings)


def _run(strategy: str, df: pd.DataFrame, settings: dict, capital: float):
    _reset_cross_strategy_singletons()
    return run_strategy_day_isolated(strategy, df, "NIFTY", capital, settings=settings)


def _q2_ratio(m: dict, risk_per_trade: float = DEFAULT_RISK_PER_TRADE) -> float:
    """Q2 as a number rather than a pass/fail flag: how many times larger
    the realised drawdown is than consecutive losses at the configured
    per-trade risk can explain. The gate trips above 2.0."""
    consec = int(m.get("max_consecutive_losses", 0) or 0)
    expected = consec * risk_per_trade * 100.0
    if expected <= 0:
        return float("nan")
    return float(m.get("max_drawdown_pct", 0.0)) / expected


def _evaluate(strategy, df, settings, capital, runs, sig_cache, regimes):
    trades, diag = _run(strategy, df, settings, capital)
    m = compute_metrics(trades, capital)

    by_regime = {}
    for r in REGIME_NAMES:
        dates = set(regimes[regimes == r].index)
        by_regime[r] = compute_metrics(
            [t for t in trades if pd.Timestamp(t.entry_time).date() in dates], capital)
    verdict = classify_strategy(m, by_regime)

    key = _filter_key(settings)
    if key not in sig_cache:
        sig_cache[key] = build_signal_frame(df, settings={f: v for f, v in zip(FILTERS, key)})
    sig = sig_cache[key]
    entries = annotate_entries(trades, sig, df, settings=settings)

    # Rally coverage against the FIXED run set (runs depend only on the
    # underlying, so every config is scored against identical rallies).
    cov, held = _coverage(runs, entries)

    # Daily concentration — how often the cap could even bind.
    per_day = entries.groupby("date").size() if len(entries) else pd.Series(dtype=int)
    cap = _cap_of(settings)

    row = {
        "positions": len(entries),
        "trade_count": m["trade_count"],
        "net_profit": m["net_profit"],
        "expectancy": m["expectancy"],
        "profit_factor": m["profit_factor"],
        "max_drawdown_pct": m["max_drawdown_pct"],
        "recovery_factor": m["recovery_factor"],
        "win_rate_pct": m["win_rate_pct"],
        "avg_risk_reward": m["avg_risk_reward"],
        "max_consecutive_losses": m["max_consecutive_losses"],
        "q2_ratio": _q2_ratio(m),
        "verdict": verdict.classification,
        "verdict_reasons": verdict.reasons,
        "false_signal_pct": (entries.first_touch == "loss_first").mean() * 100 if len(entries) else np.nan,
        "first_touch_edge_pp": (((entries.first_touch == "win_first").mean()
                                 - (entries.first_touch == "loss_first").mean()) * 100)
                                if len(entries) else np.nan,
        "never_rose_pct": (entries.mfe_r <= 0).mean() * 100 if len(entries) else np.nan,
        "rally_coverage_pct": cov,
        "held_pct_of_covered": held,
        "trades_per_day": per_day.mean() if len(per_day) else 0.0,
        "days_traded": len(per_day),
        "days_at_or_over_cap": int((per_day >= cap).sum()) if cap > 0 else 0,
        "candidate_signals": diag["candidate_signals"],
        "rejected_risk_gate": diag["rejected_risk_gate"],
        "rejected_market_hours": diag["rejected_market_hours"],
        "_entries": entries,
        "_by_regime": by_regime,
    }
    return row


def _coverage(runs: pd.DataFrame, entries: pd.DataFrame) -> tuple[float, float]:
    if runs.empty or entries.empty:
        return float("nan"), float("nan")
    covered, held = [], []
    for r in runs.itertuples():
        e = entries[(entries.direction == r.direction) & (entries.date == r.date)]
        hit = e[(e.entry_time <= r.end) & (e.exit_time >= r.start)]
        covered.append(not hit.empty)
        if hit.empty or r.end == r.start:
            continue
        span = (r.end - r.start).total_seconds()
        h = sum(max(0.0, (min(x.exit_time, r.end) - max(x.entry_time, r.start)).total_seconds())
                for x in hit.itertuples())
        held.append(min(100.0, h / span * 100.0))
    return float(np.mean(covered) * 100), float(np.median(held)) if held else float("nan")


def _cohort_stats(entries_more: pd.DataFrame, entries_base: pd.DataFrame) -> dict:
    """The trades that exist in `entries_more` but not in `entries_base` —
    i.e. what the removed filter was blocking."""
    base_keys = set(zip(entries_base.symbol, entries_base.entry_time)) if len(entries_base) else set()
    mask = [(s, t) not in base_keys for s, t in zip(entries_more.symbol, entries_more.entry_time)]
    c = entries_more[pd.Series(mask, index=entries_more.index)]
    if c.empty:
        return {"n": 0}
    return {
        "n": len(c),
        "net": c.pnl.sum(),
        "mean": c.pnl.mean(),
        "win_first": (c.first_touch == "win_first").mean() * 100,
        "loss_first": (c.first_touch == "loss_first").mean() * 100,
        "edge": ((c.first_touch == "win_first").mean() - (c.first_touch == "loss_first").mean()) * 100,
    }


def _fmt(v, nd=2):
    if v is None:
        return "—"
    if isinstance(v, str):
        return v
    if isinstance(v, float) and (np.isnan(v) or np.isinf(v)):
        return "—"
    return f"{v:,.{nd}f}"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--strategy", default="ema_rsi")
    ap.add_argument("--data-path", default="data/NSE_NIFTY50-INDEX_5Min.csv")
    ap.add_argument("--start", default="2026-02-01")
    ap.add_argument("--end", default="2026-07-31")
    ap.add_argument("--initial-capital", type=float, default=100_000.0)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    df = pd.read_csv(args.data_path)
    df["datetime"] = pd.to_datetime(df["datetime"])
    df = df.set_index("datetime").loc[args.start:args.end]
    regimes = classify_daily_regimes(df)
    cap_val = _cap_of(load_production_settings())
    prod = load_production_settings()

    # Rally set: from the underlying only, so identical for every config.
    base_sig = build_signal_frame(df)
    sig_cache = {_filter_key({}): base_sig}
    runs = find_missed_runs(base_sig, pd.DataFrame(columns=["direction", "date", "entry_time", "exit_time"]))

    def S(filters: dict, cap: int) -> dict:
        s = dict(prod)
        for f in FILTERS:
            s[f] = filters.get(f, False)
        for k in ("max_trades_per_day", "maxDailyTrades", "max_daily_trades"):
            s.pop(k, None)
        if cap > 0:
            s["max_trades_per_day"] = cap
        return s

    all_on = {f: True for f in FILTERS}
    configs: list[tuple[str, dict]] = [
        ("PRODUCTION (all 4 filters, cap 3)", S(all_on, cap_val)),
        ("legacy (no filters, no cap)", S({}, 0)),
    ]
    for f in FILTERS:
        configs.append((f"LOO: production minus {SHORT[f]}",
                        S({x: (x != f) for x in FILTERS}, cap_val)))
    for f in FILTERS:
        configs.append((f"SOLO: {SHORT[f]} only, no cap", S({f: True}, 0)))
    for c in (0, 3, 4, 5, 6, 8):
        if c == cap_val:
            continue
        configs.append((f"CAP: all filters, cap {c if c else 'unlimited'}", S(all_on, c)))

    results: dict[str, dict] = {}
    for label, settings in configs:
        print(f"running: {label}", file=sys.stderr)
        results[label] = _evaluate(args.strategy, df, settings, args.initial_capital,
                                   runs, sig_cache, regimes)

    prod_label = configs[0][0]
    P = results[prod_label]

    L: list[str] = []
    A = L.append
    A(f"# Entry-filter and trade-cap ablation — `{args.strategy}`\n")
    A(f"Window: {df.index.min()} → {df.index.max()} "
      f"({df.index.normalize().nunique()} trading days)  ")
    A(f"Capital: Rs {args.initial_capital:,.0f}  ")
    A(f"Rally set: **{len(runs)}** sustained underlying moves (≥0.30% within 90 min), "
      "identical for every configuration — only coverage changes.\n")
    A("Every row is a full day-isolated run through the production pipeline. "
      "One variable at a time: LOO removes a single filter from production, "
      "SOLO runs a single filter against the unfiltered path, CAP sweeps the "
      "daily cap with filters held at production.\n")

    cols = [("positions", "pos", 0), ("net_profit", "net", 0), ("expectancy", "exp", 0),
            ("profit_factor", "PF", 2), ("max_drawdown_pct", "DD%", 2),
            ("recovery_factor", "recov", 2), ("win_rate_pct", "win%", 1),
            ("avg_risk_reward", "R:R", 2), ("q2_ratio", "Q2", 2),
            ("false_signal_pct", "false%", 1), ("first_touch_edge_pp", "edge pp", 1),
            ("rally_coverage_pct", "rally%", 1)]
    A("## All configurations\n")
    A("| Config | " + " | ".join(c[1] for c in cols) + " | verdict |")
    A("|---" * (len(cols) + 2) + "|")
    for label, _ in configs:
        r = results[label]
        A(f"| {label} | " + " | ".join(_fmt(r[k], nd) for k, _n, nd in cols) +
          f" | {r['verdict']} |")
    A("")

    A("## 1. What each filter blocks (leave-one-out)\n")
    A("The cohort is the set of positions that appear when the filter is "
      "removed from the production configuration — precisely the trades that "
      "filter was blocking. `edge` is win-first minus loss-first on those "
      "trades alone.\n")
    A("| Filter removed | trades it blocks | their net P&L | mean | win-first | loss-first | edge | verdict on the filter |")
    A("|---|---|---|---|---|---|---|---|")
    for f in FILTERS:
        label = f"LOO: production minus {SHORT[f]}"
        c = _cohort_stats(results[label]["_entries"], P["_entries"])
        if not c["n"]:
            A(f"| {SHORT[f]} | 0 | — | — | — | — | — | blocks nothing |")
            continue
        good = c["net"] > 0 and c["edge"] > 0
        A(f"| {SHORT[f]} | {c['n']} | {c['net']:,.0f} | {c['mean']:,.0f} | "
          f"{c['win_first']:.1f}% | {c['loss_first']:.1f}% | **{c['edge']:+.1f}pp** | "
          f"{'removes PROFITABLE trades' if good else 'removes losing/neutral trades'} |")
    A("")

    A("### Full metric impact of removing each filter\n")
    A("| Config | Δ positions | Δ net | Δ PF | Δ DD% | Δ recov | Δ false% | Δ edge pp | Δ rally% |")
    A("|---|---|---|---|---|---|---|---|---|")
    for f in FILTERS:
        label = f"LOO: production minus {SHORT[f]}"
        r = results[label]
        A(f"| minus {SHORT[f]} | {r['positions']-P['positions']:+d} | "
          f"{r['net_profit']-P['net_profit']:+,.0f} | {r['profit_factor']-P['profit_factor']:+.2f} | "
          f"{r['max_drawdown_pct']-P['max_drawdown_pct']:+.2f} | "
          f"{r['recovery_factor']-P['recovery_factor']:+.2f} | "
          f"{r['false_signal_pct']-P['false_signal_pct']:+.1f} | "
          f"{r['first_touch_edge_pp']-P['first_touch_edge_pp']:+.1f} | "
          f"{r['rally_coverage_pct']-P['rally_coverage_pct']:+.1f} |")
    A("")

    A("## 2. Each filter on its own (SOLO, against the unfiltered path)\n")
    legacy = results["legacy (no filters, no cap)"]
    A("| Config | positions | net | PF | DD% | false% | edge pp | rally% |")
    A("|---|---|---|---|---|---|---|---|")
    A(f"| legacy: no filters | {legacy['positions']} | {legacy['net_profit']:,.0f} | "
      f"{_fmt(legacy['profit_factor'])} | {_fmt(legacy['max_drawdown_pct'])} | "
      f"{_fmt(legacy['false_signal_pct'],1)} | {_fmt(legacy['first_touch_edge_pp'],1)} | "
      f"{_fmt(legacy['rally_coverage_pct'],1)} |")
    for f in FILTERS:
        r = results[f"SOLO: {SHORT[f]} only, no cap"]
        A(f"| {SHORT[f]} only | {r['positions']} | {r['net_profit']:,.0f} | "
          f"{_fmt(r['profit_factor'])} | {_fmt(r['max_drawdown_pct'])} | "
          f"{_fmt(r['false_signal_pct'],1)} | {_fmt(r['first_touch_edge_pp'],1)} | "
          f"{_fmt(r['rally_coverage_pct'],1)} |")
    A("")

    A("## 3. The daily trade cap\n")
    A("| Config | positions | trades/day | days at/over cap | net | PF | DD% | recov | rally% |")
    A("|---|---|---|---|---|---|---|---|---|")
    for label, _ in configs:
        if not label.startswith("CAP") and label != prod_label:
            continue
        r = results[label]
        A(f"| {label} | {r['positions']} | {_fmt(r['trades_per_day'])} | "
          f"{r['days_at_or_over_cap']} | {r['net_profit']:,.0f} | {_fmt(r['profit_factor'])} | "
          f"{_fmt(r['max_drawdown_pct'])} | {_fmt(r['recovery_factor'])} | "
          f"{_fmt(r['rally_coverage_pct'],1)} |")
    A("")

    A("## 4. Regime detail for every configuration\n")
    A("| Config | " + " | ".join(REGIME_NAMES) + " |")
    A("|---" * (len(REGIME_NAMES) + 1) + "|")
    for label, _ in configs:
        r = results[label]
        cells = []
        for rg in REGIME_NAMES:
            m = r["_by_regime"][rg]
            cells.append(f"{m['trade_count']}t / {m['net_profit']:,.0f}" if m["trade_count"] else "—")
        A(f"| {label} | " + " | ".join(cells) + " |")
    A("")

    out = Path(args.out or (RESULTS_DIR / f"filter_ablation_{args.strategy}.md"))
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(L), encoding="utf-8")
    with open(RESULTS_DIR / f"filter_ablation_{args.strategy}.pkl", "wb") as fh:
        pickle.dump({k: {kk: vv for kk, vv in v.items() if not kk.startswith("_")}
                     for k, v in results.items()}, fh)
    print(f"Written {out}", file=sys.stderr)


if __name__ == "__main__":
    main()
