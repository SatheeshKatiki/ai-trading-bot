"""Is any entry-filter change statistically defensible?

    python -m validation_harness.run_filter_significance --strategy ema_rsi

The ablation (`run_filter_ablation.py`) reports what each filter does to
the headline metrics. Those differences can look large and still be
noise: `ema_rsi` trades ~145-190 positions over 123 days, option P&L is
heavy-tailed, and a single day can be worth more than a whole
configuration delta. This module asks whether the differences survive.

Three tests, all run symmetrically over all four filters so that no
result is selected after the fact:

1. PAIRED DAY-LEVEL BOOTSTRAP of the change in total P&L. Day-isolated
   runs give each calendar day a fresh RiskManager, so days are
   independent draws and a paired bootstrap over them is valid.

2. BLOCKED-COHORT EXPECTANCY. The trades a filter blocks are isolated by
   (symbol, entry_time) and their mean P&L bootstrapped against zero.
   This is the question a filter actually poses: are the trades it
   removes losers?

3. SIGNAL-POPULATION QUALITY -- the best-powered of the three. The traded
   cohorts are small (13-85), but the unfiltered strategy emits 725
   signals. Each is scored on the UNDERLYING: did the index move +T in
   the signalled direction before -T, in the rest of the day? Then the
   filter's rejections are compared against what it allows through.

   T comes from the system's own geometry rather than being chosen: the
   premium stop is ~15% and measured premium elasticity is ~70x, so one
   risk unit is ~0.21% of index. Every result is reported at 0.15 / 0.21
   / 0.30 so no conclusion can rest on one threshold -- a filter whose
   sign flips across them has no reliable effect, which is itself the
   finding for three of the four.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from shared.filters.institutional import (
    get_aggression_masks,
    get_cpr_rejection_masks,
    get_extension_mask,
    get_squeeze_mask,
)

from .entry_quality import annotate_entries, build_signal_frame
from .production_settings import load_production_settings
from .run_validation import _reset_cross_strategy_singletons, run_strategy_day_isolated

RESULTS_DIR = Path(__file__).parent / "results"

FILTERS = ("enable_squeeze_filter", "enable_extension_filter",
           "enable_cpr_filter", "enable_aggression_filter")
SHORT = {f: f.replace("enable_", "").replace("_filter", "") for f in FILTERS}
THRESHOLDS = (0.15, 0.21, 0.30)
WARMUP_DAYS = 30
SEED = 20260809
N_BOOT = 20_000


def _settings(prod: dict, off: str | None, cap: int) -> dict:
    s = dict(prod)
    for f in FILTERS:
        s[f] = True
    if off:
        s[off] = False
    for k in ("maxDailyTrades", "max_daily_trades", "max_trades_per_day"):
        s.pop(k, None)
    if cap > 0:
        s["max_trades_per_day"] = cap
    return s


def _edge(x: np.ndarray) -> float:
    """win-first minus loss-first, in percentage points."""
    return float(((x == 1).mean() - (x == -1).mean()) * 100)


def _rejection_masks(sig: pd.DataFrame, df: pd.DataFrame) -> dict[str, pd.Series]:
    """Per-signal-bar rejection mask for each filter, computed over the same
    30-day warm-up windows the filters see in a real run."""
    rej = {k: pd.Series(False, index=sig.index) for k in SHORT.values()}
    for day in sorted({d.date() for d in sig.index}):
        w = df.loc[str(pd.Timestamp(day) - pd.Timedelta(days=WARMUP_DAYS)):str(day)]
        idx = sig.index[sig.index.date == day]
        if not len(idx):
            continue
        s = sig.loc[idx, "signal"]
        bull_cpr, bear_cpr = get_cpr_rejection_masks(w)
        bull_agg, bear_agg = get_aggression_masks(w)
        rej["squeeze"].loc[idx] = get_squeeze_mask(w).reindex(idx).fillna(False).values
        rej["extension"].loc[idx] = get_extension_mask(w).reindex(idx).fillna(False).values
        rej["cpr"].loc[idx] = np.where(
            s.values == 1, bull_cpr.reindex(idx).fillna(False).values,
            bear_cpr.reindex(idx).fillna(False).values)
        rej["aggression"].loc[idx] = np.where(
            s.values == 1, bull_agg.reindex(idx).fillna(False).values,
            bear_agg.reindex(idx).fillna(False).values)
    return rej


def _first_touch_underlying(sig: pd.DataFrame, df: pd.DataFrame, thresh: float) -> np.ndarray:
    """+1 if the index moved +thresh% the signalled way before -thresh%,
    -1 if the reverse, 0 if neither happened before the close."""
    out = []
    for ts, row in sig.iterrows():
        rest = df.loc[(df.index > ts) & (df.index.date == ts.date()), "close"]
        if rest.empty:
            out.append(0)
            continue
        fav = ((rest - row.close) / row.close * 100 * row.signal).to_numpy()
        i_up = np.where(fav >= thresh)[0]
        i_dn = np.where(-fav >= thresh)[0]
        if not len(i_up) and not len(i_dn):
            out.append(0)
        elif not len(i_dn) or (len(i_up) and i_up[0] < i_dn[0]):
            out.append(1)
        else:
            out.append(-1)
    return np.array(out)


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
    prod = load_production_settings()
    cap = 3
    rng = np.random.default_rng(SEED)

    sig_cache: dict[tuple, pd.DataFrame] = {}

    def run(off):
        st = _settings(prod, off, cap)
        key = tuple(bool(st.get(f, False)) for f in FILTERS)
        if key not in sig_cache:
            sig_cache[key] = build_signal_frame(df, settings={f: v for f, v in zip(FILTERS, key)})
        _reset_cross_strategy_singletons()
        trades, _ = run_strategy_day_isolated(args.strategy, df, "NIFTY",
                                              args.initial_capital, settings=st)
        return trades, annotate_entries(trades, sig_cache[key], df, settings=st)

    print("running baseline...", file=sys.stderr)
    base_trades, base_entries = run(None)
    base_keys = set(zip(base_entries.symbol, base_entries.entry_time))
    days = sorted({d.date() for d in df.index})

    def daily(trades):
        s = pd.Series(0.0, index=pd.Index(days))
        for t in trades:
            s[pd.Timestamp(t.entry_time).date()] += t.pnl
        return s

    base_daily = daily(base_trades)

    L: list[str] = []
    A = L.append
    A(f"# Are any entry-filter changes statistically defensible? — `{args.strategy}`\n")
    A(f"Window: {df.index.min()} → {df.index.max()} "
      f"({df.index.normalize().nunique()} trading days)  ")
    A(f"Bootstrap: {N_BOOT:,} resamples, seed {SEED}. Baseline is the production "
      f"configuration (all four filters, cap {cap}).\n")
    A("Tests are run symmetrically over all four filters, so no result is "
      "selected after seeing which filter looks good.\n")

    A("## Test 1 — paired day-level bootstrap of total P&L\n")
    A("Day-isolated runs give each day a fresh RiskManager, so days are "
      "independent draws and pairing over them is valid.\n")
    A("| Filter disabled | days changed | better | worse | total Δ P&L | 95% CI | P(Δ>0) |")
    A("|---|---|---|---|---|---|---|")
    per_filter = {}
    for f in FILTERS:
        print(f"running without {SHORT[f]}...", file=sys.stderr)
        trades, entries = run(f)
        per_filter[f] = (trades, entries)
        d = (daily(trades) - base_daily).to_numpy()
        boot = np.array([rng.choice(d, d.size, replace=True).sum() for _ in range(N_BOOT)])
        lo, hi = np.percentile(boot, [2.5, 97.5])
        A(f"| {SHORT[f]} | {(np.abs(d) > 1e-9).sum()} | {(d > 1e-9).sum()} | {(d < -1e-9).sum()} | "
          f"{d.sum():,.0f} | [{lo:,.0f}, {hi:,.0f}] | {(boot > 0).mean()*100:.1f}% |")
    A("")

    A("## Test 2 — do the blocked trades lose money?\n")
    A("The trades a filter blocks, isolated by (symbol, entry_time), with "
      "their mean P&L bootstrapped against zero.\n")
    A("| Filter | blocked | mean P&L | total | 95% CI of mean | P(mean>0) | win-first | loss-first |")
    A("|---|---|---|---|---|---|---|---|")
    for f in FILTERS:
        _t, e = per_filter[f]
        mask = [(s, t) not in base_keys for s, t in zip(e.symbol, e.entry_time)]
        c = e[pd.Series(mask, index=e.index)]
        if c.empty:
            A(f"| {SHORT[f]} | 0 | — | — | — | — | — | — |")
            continue
        v = c.pnl.to_numpy()
        boot = np.array([rng.choice(v, v.size, replace=True).mean() for _ in range(N_BOOT)])
        lo, hi = np.percentile(boot, [2.5, 97.5])
        A(f"| {SHORT[f]} | {len(c)} | {v.mean():,.0f} | {v.sum():,.0f} | "
          f"[{lo:,.0f}, {hi:,.0f}] | {(boot > 0).mean()*100:.1f}% | "
          f"{(c.first_touch=='win_first').mean()*100:.1f}% | "
          f"{(c.first_touch=='loss_first').mean()*100:.1f}% |")
    A("")

    A("## Test 3 — signal-population quality (best powered)\n")
    A("Every signal the unfiltered strategy emits, scored on the underlying. "
      "A filter that works should reject signals whose edge is worse than the "
      "ones it lets through, at every threshold.\n")
    unfiltered = build_signal_frame(df)
    unfiltered = unfiltered[unfiltered.signal != 0]
    A(f"Signal population: **{len(unfiltered)}** bars.\n")
    rej = _rejection_masks(unfiltered, df)
    for thresh in THRESHOLDS:
        ft = _first_touch_underlying(unfiltered, df, thresh)
        A(f"### Threshold ±{thresh:.2f}% of index\n")
        A("| Filter | rejected | edge of rejected | allowed | edge of allowed | difference | 95% CI | P(rejected worse) |")
        A("|---|---|---|---|---|---|---|---|")
        for k, m in rej.items():
            r, a = ft[m.to_numpy()], ft[~m.to_numpy()]
            if len(r) < 10 or len(a) < 10:
                A(f"| {k} | {len(r)} | — | {len(a)} | — | — | — | too few |")
                continue
            diff = _edge(r) - _edge(a)
            boot = np.array([_edge(rng.choice(r, r.size, True)) - _edge(rng.choice(a, a.size, True))
                             for _ in range(8000)])
            lo, hi = np.percentile(boot, [2.5, 97.5])
            A(f"| {k} | {len(r)} | {_edge(r):+.1f}pp | {len(a)} | {_edge(a):+.1f}pp | "
              f"**{diff:+.1f}pp** | [{lo:+.1f}, {hi:+.1f}] | {(boot < 0).mean()*100:.1f}% |")
        A("")

    out = Path(args.out or (RESULTS_DIR / f"filter_significance_{args.strategy}.md"))
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(L), encoding="utf-8")
    print(f"Written {out}", file=sys.stderr)


if __name__ == "__main__":
    main()
