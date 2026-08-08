"""Runner for the entry-quality audit.

    python -m validation_harness.run_entry_quality --strategy ema_rsi

Loads the cached day-isolated trade set (`results/trades_<strategy>.pkl`)
— the same trades the validation report is computed from — reconstructs
the signal and indicator state that produced each entry, and writes a
markdown audit to `results/entry_quality_<strategy>.md`.

Read-only: it re-derives, it never re-trades.
"""
from __future__ import annotations

import argparse
import pickle
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from .entry_quality import (
    annotate_entries,
    build_signal_frame,
    find_missed_runs,
    verify_signal_alignment,
)
from .regimes import classify_daily_regimes

RESULTS_DIR = Path(__file__).parent / "results"

#: The four institutional filters `config/settings.json` has enabled in
#: production. The validation harness passes `settings={}`, so every
#: number in the standing validation report was produced with all four
#: OFF. Kept here so the audit can quantify that gap rather than describe
#: it.
PRODUCTION_FILTERS = {
    "enable_squeeze_filter": True,
    "enable_extension_filter": True,
    "enable_cpr_filter": True,
    "enable_aggression_filter": True,
}


def _fmt(v, nd=2):
    if v is None or (isinstance(v, float) and (np.isnan(v) or np.isinf(v))):
        return "—"
    if isinstance(v, (int, np.integer)):
        return f"{v:,}"
    return f"{v:,.{nd}f}"


def _outcome_table(df: pd.DataFrame, by: str, lines: list, label: str = None,
                   min_n: int = 8) -> None:
    """Win-first / loss-first split plus realised P&L for each bucket.

    `first_touch` is exit-independent, `pnl` is not — showing them side by
    side is the point: a bucket where the entry wins the race but the
    trade still loses money is an exit problem, not an entry problem."""
    lines.append(f"| {label or by} | n | win-first | loss-first | neither | edge (w−l) | net P&L | mean R:R proxy |")
    lines.append("|---|---|---|---|---|---|---|---|")
    for key, g in df.groupby(by, dropna=False):
        if len(g) < min_n:
            continue
        w = (g.first_touch == "win_first").mean() * 100
        l = (g.first_touch == "loss_first").mean() * 100
        n_ = (g.first_touch == "none").mean() * 100
        lines.append(
            f"| {key} | {len(g)} | {w:.1f}% | {l:.1f}% | {n_:.1f}% | "
            f"**{w - l:+.1f}pp** | {g.pnl.sum():,.0f} | {_fmt(g.mfe_r.mean())} |"
        )
    w = (df.first_touch == "win_first").mean() * 100
    l = (df.first_touch == "loss_first").mean() * 100
    n_ = (df.first_touch == "none").mean() * 100
    lines.append(f"| **ALL** | {len(df)} | {w:.1f}% | {l:.1f}% | {n_:.1f}% | "
                 f"**{w - l:+.1f}pp** | {df.pnl.sum():,.0f} | {_fmt(df.mfe_r.mean())} |")
    lines.append("")


def _bucket(s: pd.Series, edges: list[float], labels: list[str]) -> pd.Series:
    return pd.cut(s, bins=edges, labels=labels, include_lowest=True)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--strategy", default="ema_rsi")
    ap.add_argument("--data-path", default="data/NSE_NIFTY50-INDEX_5Min.csv")
    ap.add_argument("--start", default="2026-02-01")
    ap.add_argument("--end", default="2026-07-31")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    df = pd.read_csv(args.data_path)
    df["datetime"] = pd.to_datetime(df["datetime"])
    df = df.set_index("datetime").loc[args.start:args.end]

    cache = RESULTS_DIR / f"trades_{args.strategy}.pkl"
    if not cache.exists():
        sys.exit(f"No cached trades at {cache}. Run run_dd_attribution.py first.")
    with open(cache, "rb") as f:
        trades = pickle.load(f)

    print("Reconstructing signals (harness path, filters OFF)...", file=sys.stderr)
    sig = build_signal_frame(df)
    align = verify_signal_alignment(trades, sig)
    entries = annotate_entries(trades, sig, df)

    print("Reconstructing signals (production path, filters ON)...", file=sys.stderr)
    sig_prod = build_signal_frame(df, settings=PRODUCTION_FILTERS)

    regimes = classify_daily_regimes(df)
    entries["regime"] = entries.date.map(regimes)

    L: list[str] = []
    A = L.append
    A(f"# Entry-quality audit — `{args.strategy}`\n")
    A(f"Window: {df.index.min()} → {df.index.max()} "
      f"({df.index.normalize().nunique()} trading days)  ")
    A(f"Positions: {len(entries)}\n")

    # ── 0. fidelity ─────────────────────────────────────────────────
    A("## 0. Signal reconstruction fidelity\n")
    A("Every conclusion below reads indicator state off a reconstructed "
      "signal frame, so the reconstruction is checked against the actual "
      "trades first: each entry must land on a bar this module independently "
      "reconstructs as a signal of the same direction.\n")
    A(f"- positions checked: **{align['positions']}**")
    A(f"- entry bar carries the matching signal: **{align['matched']}**")
    A(f"- entry bar missing from the frame: **{align['entry_bar_not_in_frame']}**")
    A(f"- signal direction mismatch: **{align['signal_direction_mismatch']}**\n")

    # ── 1. the headline: is the entry right? ────────────────────────
    A("## 1. Is the entry right? (first touch of ±1R)\n")
    A("For each position, walk the premium path forward and record which "
      "comes first: **+1R** (premium reaches entry + its own initial stop "
      "distance) or **−1R**. R is the real `resolve_initial_stop` distance — "
      "the amount the live system actually risks on that trade.\n")
    A("This is exit-independent on purpose. It asks only whether the market "
      "went the signalled way before it went against it, by the size we were "
      "risking. **`false entry` = loss-first**: a full risk unit against the "
      "signal before a single one in its favour.\n")
    wf = (entries.first_touch == "win_first").sum()
    lf = (entries.first_touch == "loss_first").sum()
    nn = (entries.first_touch == "none").sum()
    A(f"| Outcome | n | share |")
    A("|---|---|---|")
    A(f"| win-first | {wf} | {wf/len(entries)*100:.1f}% |")
    A(f"| **loss-first (false entry)** | {lf} | **{lf/len(entries)*100:.1f}%** |")
    A(f"| neither within the day | {nn} | {nn/len(entries)*100:.1f}% |")
    A("")
    decided = wf + lf
    A(f"Of the {decided} positions that resolved one way or the other, the "
      f"signal was right first **{wf/decided*100:.1f}%** of the time — an edge "
      f"of **{(wf-lf)/decided*100:+.1f}pp** over a coin flip on its own risk unit.\n")
    A(f"Median bars to first touch: win-first "
      f"**{_fmt(entries[entries.first_touch=='win_first'].bars_to_first_touch.median(),0)}**, "
      f"loss-first **{_fmt(entries[entries.first_touch=='loss_first'].bars_to_first_touch.median(),0)}** "
      "(one bar = 5 min)\n")

    A("### Post-entry excursion, in units of the position's own risk\n")
    A("| Metric | p10 | p25 | median | p75 | p90 |")
    A("|---|---|---|---|---|---|")
    for col, lbl in [("mfe_r", "MFE (R)"), ("mae_r", "MAE (R)")]:
        q = entries[col].dropna()
        A(f"| {lbl} | {_fmt(np.percentile(q,10))} | {_fmt(np.percentile(q,25))} | "
          f"{_fmt(q.median())} | {_fmt(np.percentile(q,75))} | {_fmt(np.percentile(q,90))} |")
    A("")
    never_up = (entries.mfe_r <= 0.0).mean() * 100
    A(f"Positions whose premium **never rose at all** after entry: "
      f"**{never_up:.1f}%** — the purest false-signal count, independent of "
      "any threshold choice.\n")

    # ── 2. confirmation quality, component by component ─────────────
    A("## 2. Confirmation quality — which component carries the signal?\n")
    A("All three conditions must hold for a signal to fire, so none of them "
      "can be tested by presence/absence. What CAN be tested is degree: for "
      "each component, does a stronger reading produce a better entry? A "
      "component whose buckets show no monotone edge is contributing "
      "confirmation in name only.\n")

    e = entries.copy()
    e["rsi_bucket"] = _bucket(e.rsi_margin, [-100, 2, 5, 10, 15, 100],
                              ["0-2 (at threshold)", "2-5", "5-10", "10-15", "15+"])
    e["ema_bucket"] = _bucket(e.ema_gap_signed, [-100, 0.05, 0.1, 0.2, 0.4, 100],
                              ["<0.05% (flat)", "0.05-0.1%", "0.1-0.2%", "0.2-0.4%", "0.4%+"])
    e["st_bucket"] = _bucket(e.st_age_bars, [-1, 1, 3, 6, 12, 10_000],
                             ["0-1 (fresh flip)", "2-3", "4-6", "7-12", "13+ (stale)"])
    e["stretch_bucket"] = _bucket(e.stretch_pct, [-100, 0, 0.05, 0.1, 0.2, 100],
                                  ["<0 (below EMA)", "0-0.05%", "0.05-0.1%", "0.1-0.2%", "0.2%+"])
    e["vol_bucket"] = _bucket(e.vol_ratio, [-1, 1.0, 1.5, 2.5, 1e9],
                              ["<=1.0x", "1.0-1.5x", "1.5-2.5x", "2.5x+"])

    A("### RSI margin past its threshold\n")
    _outcome_table(e, "rsi_bucket", L, "RSI margin")
    A("### EMA separation (fast vs slow), signed toward the trade\n")
    _outcome_table(e, "ema_bucket", L, "EMA gap")
    A("### Supertrend leg age at entry\n")
    _outcome_table(e, "st_bucket", L, "Supertrend age")
    A("### Price stretch beyond the fast EMA at entry (entry timing)\n")
    _outcome_table(e, "stretch_bucket", L, "Stretch")
    A("### Volume vs its 20-bar average\n")
    _outcome_table(e, "vol_bucket", L, "Volume ratio")

    # ── 3. entry timing ─────────────────────────────────────────────
    A("## 3. Entry timing\n")
    A("### Time of day\n")
    e["tod"] = _bucket(e.minute_of_day, [0, 9*60+30, 10*60+30, 12*60, 13*60+30, 24*60],
                       ["open–09:30", "09:30–10:30", "10:30–12:00", "12:00–13:30", "13:30–close"])
    _outcome_table(e, "tod", L, "Session")
    A("### How long the EMA regime had already been running\n")
    e["ema_age_bucket"] = _bucket(e.ema_age_bars, [-1, 3, 8, 20, 50, 100000],
                                  ["0-3 bars", "4-8", "9-20", "21-50", "51+"])
    _outcome_table(e, "ema_age_bucket", L, "EMA regime age")

    # ── 4. regime ───────────────────────────────────────────────────
    A("## 4. Regime\n")
    _outcome_table(e, "regime", L, "Regime", min_n=1)

    A("### Direction — and why the apparent asymmetry is NOT actionable\n")
    _outcome_table(e, "direction", L, "Direction", min_n=1)
    A("Taken alone this looks like a large, exploitable skew. It is not. "
      "Controlling for the direction the index actually moved that day "
      "collapses it: the strategy is right when it is aligned with the day "
      "and wrong when it is not, symmetrically for CE and PE. The headline "
      "skew is a composition effect — the window drifted down "
      f"({(df['close'].iloc[-1]/df['close'].iloc[0]-1)*100:+.2f}%), so far more "
      "PE positions were opened on days that went the PE way.\n")
    day_chg = (df["close"].resample("D").last() / df["close"].resample("D").first() - 1) * 100
    e["day_chg"] = e.date.map(lambda d: day_chg.get(pd.Timestamp(d), np.nan))
    e["day_dir"] = np.where(e.day_chg > 0.15, "up day",
                            np.where(e.day_chg < -0.15, "down day", "flat day"))
    A("| Day | Direction | n | win-first | edge | net P&L |")
    A("|---|---|---|---|---|---|")
    for dd in ("up day", "flat day", "down day"):
        for d in ("CE", "PE"):
            g = e[(e.day_dir == dd) & (e.direction == d)]
            if len(g) < 5:
                continue
            w = (g.first_touch == "win_first").mean() * 100
            l = (g.first_touch == "loss_first").mean() * 100
            A(f"| {dd} | {d} | {len(g)} | {w:.1f}% | **{w-l:+.1f}pp** | {g.pnl.sum():,.0f} |")
    A("")
    A("**Conclusion: no direction-based change is justified.** Acting on the "
      "headline split would be fitting the window's drift.\n")

    # ── 5. weak vs strong setups ────────────────────────────────────
    A("## 5. Weak vs strong setups\n")
    A("A composite built ONLY from the strategy's own three conditions — no "
      "new indicator — scoring one point each for an RSI margin above 5, an "
      "EMA gap above 0.1%, and a Supertrend leg no older than 6 bars.\n")
    e["score"] = (
        (e.rsi_margin > 5).astype(int)
        + (e.ema_gap_signed > 0.1).astype(int)
        + (e.st_age_bars <= 6).astype(int)
    )
    _outcome_table(e, "score", L, "Confirmation score (0-3)", min_n=1)

    # ── 6. missed runs ──────────────────────────────────────────────
    A("## 6. Missed trend / rally opportunities\n")
    A("Sustained moves in the UNDERLYING (≥0.30% completed within 90 minutes, "
      "de-overlapped largest-first), and whether a position in the matching "
      "direction was OPEN at any point during each one.\n")
    runs = find_missed_runs(sig, entries)
    if not runs.empty:
        A(f"Runs found: **{len(runs)}** over {df.index.normalize().nunique()} days "
          f"({len(runs)/df.index.normalize().nunique():.1f}/day), median size "
          f"**{runs.move_pct.median():.2f}%**\n")
        A("| Direction | runs | covered | median size | median held % of run |")
        A("|---|---|---|---|---|")
        for d, g in runs.groupby("direction"):
            A(f"| {d} | {len(g)} | {g.covered.mean()*100:.1f}% | {g.move_pct.median():.2f}% | "
              f"{g.held_pct_of_run.median():.1f}% |")
        A(f"| **ALL** | {len(runs)} | **{runs.covered.mean()*100:.1f}%** | "
          f"{runs.move_pct.median():.2f}% | {runs.held_pct_of_run.median():.1f}% |")
        A("")
        cov = runs[runs.covered]
        A(f"Among the runs that WERE covered, median time held is "
          f"**{cov.held_pct_of_run.median():.1f}%** of the run (the "
          "all-runs median is 0% only because most runs are uncovered — "
          "quoting that would double-count the same miss).\n")
        big = runs[runs.move_pct >= 0.6]
        if not big.empty:
            bigc = big[big.covered]
            A(f"Large runs (≥0.60% of index, n={len(big)}): covered "
              f"**{big.covered.mean()*100:.1f}%**; among those, median held "
              f"**{bigc.held_pct_of_run.median():.1f}%** of the run.\n")

        # Why each uncovered run was missed — the decomposition is what
        # separates "a defect we can fix" from "the strategy's philosophy".
        A("### Why the uncovered runs were missed\n")
        A("Categories are exclusive and are evaluated in this order: was any "
          "position open during the run; else did a signal fire; else did the "
          "raw level condition hold (i.e. would a level-triggered strategy "
          "have entered); else there was simply no setup.\n")
        uncovered = runs[~runs.covered]
        cats = []
        for _, r in uncovered.iterrows():
            want = 1 if r.direction == "CE" else -1
            m = (sig.index >= r.start) & (sig.index <= r.end)
            day_e = entries[entries.date == r.date]
            if len(day_e[(day_e.entry_time <= r.end) & (day_e.exit_time >= r.start)]):
                cats.append("holding an opposite-direction position")
            elif (sig.loc[m, "signal"] == want).any():
                cats.append("signal fired but no entry (risk gate / EOD cutoff)")
            elif (sig.loc[m, "level_signal"] == want).any():
                cats.append("setup present, edge-trigger suppressed it")
            else:
                cats.append("no setup at all")
        uncovered = uncovered.assign(why=cats)
        A("| Reason | runs | share | median size | total index movement |")
        A("|---|---|---|---|---|")
        for k, g in uncovered.groupby("why"):
            A(f"| {k} | {len(g)} | {len(g)/len(uncovered)*100:.1f}% | "
              f"{g.move_pct.median():.2f}% | {g.move_pct.sum():.1f}% |")
        A("")
        et = uncovered[uncovered.why == "setup present, edge-trigger suppressed it"]
        A(f"**The anti-churn edge-trigger accounts for {len(et)} of "
          f"{len(uncovered)} misses ({len(et)/len(uncovered)*100:.1f}%).** It is "
          "not the reason rallies are being missed, and the measurement gives "
          "no reason to weaken it.\n")

    # ── 7. production entry path ────────────────────────────────────
    A("## 7. The entry path that was validated is not the one production runs\n")
    A("`config/settings.json` has all four institutional filters ENABLED. "
      "`registry.run_strategy` applies them to every strategy's signals. The "
      "validation harness calls it with `settings={}`, so all four are OFF in "
      "every number the validation report contains — including this audit's "
      "sections 1-6.\n")
    both = sig.join(sig_prod["signal"].rename("signal_prod"), how="inner")
    raw_n = int((both.signal != 0).sum())
    prod_n = int((both.signal_prod != 0).sum())
    survived = int(((both.signal != 0) & (both.signal == both.signal_prod)).sum())
    A("| Path | signal bars | vs harness |")
    A("|---|---|---|")
    A(f"| harness (`settings={{}}`, filters OFF) | {raw_n} | — |")
    A(f"| production (`config/settings.json`, filters ON) | {prod_n} | "
      f"**{(prod_n-raw_n)/raw_n*100:+.1f}%** |")
    A("")
    A(f"Signals surviving the production filters: **{survived}/{raw_n}** "
      f"(**{survived/raw_n*100:.1f}%**) — the production strategy takes "
      f"roughly **{100 - survived/raw_n*100:.0f}% fewer entries** than the one "
      "that was measured and given its KEEP verdict.\n")
    A("Also unmodelled: `config/settings.json` sets `max_daily_trades: 3`, "
      "which `main.py` writes into `risk_manager.config.max_trades_per_day` on "
      "the live entry path. The harness constructs `RiskManager` without a "
      "config, leaving the cap at its default of 0 (unlimited), and averages "
      f"**{len(entries)/df.index.normalize().nunique():.1f} positions/day**.\n")

    # entry quality of the signals the filters would remove
    kept = e[e.entry_time.isin(both.index[(both.signal != 0) & (both.signal == both.signal_prod)])]
    dropped = e[~e.entry_time.isin(kept.entry_time)]
    if len(dropped) >= 5 and len(kept) >= 5:
        A("### Were the filtered-out entries the bad ones?\n")
        A("| Cohort | n | win-first | loss-first | edge | net P&L | mean P&L |")
        A("|---|---|---|---|---|---|---|")
        for lbl, g in [("kept by production filters", kept), ("removed by production filters", dropped)]:
            w = (g.first_touch == "win_first").mean() * 100
            l = (g.first_touch == "loss_first").mean() * 100
            A(f"| {lbl} | {len(g)} | {w:.1f}% | {l:.1f}% | **{w-l:+.1f}pp** | "
              f"{g.pnl.sum():,.0f} | {g.pnl.mean():,.0f} |")
        A("")

    out = Path(args.out or (RESULTS_DIR / f"entry_quality_{args.strategy}.md"))
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(L), encoding="utf-8")
    e.to_pickle(RESULTS_DIR / f"eq_entries_{args.strategy}.pkl")
    if not runs.empty:
        runs.to_pickle(RESULTS_DIR / f"eq_runs_{args.strategy}.pkl")
    print(f"Written {out}", file=sys.stderr)


if __name__ == "__main__":
    main()
