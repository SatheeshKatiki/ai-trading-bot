"""Strategy-agnostic baseline + entry/exit audit on the production path.

    python -m validation_harness.run_strategy_audit --strategy institutional_momentum

Establishes the exact production-path baseline for one strategy and audits
it on the measures that do not depend on which strategy produced the
trades:

  * full metric battery + per-regime + readiness verdict + Q2 ratio
  * first touch of +/-1R (exit-independent false-signal rate)
  * MFE/MAE in units of the position's own risk
  * entry timing by time of day
  * exit-reason mix, holding time, premature exits, trailing behaviour
  * rally/trend capture against a fixed set of underlying moves
  * missed opportunities, classified by CAUSE (no setup / opposite
    position held / signalled but blocked)
  * position sizing, stop bands and the risk actually taken per trade
  * rejection behaviour with the risk gate's own reason strings
  * churn: gap to next entry, same-direction re-entry rate, signal duty
    cycle (level condition vs emitted signals)

The churn block exists to TEST the re-entry mechanism found in `ema_rsi`
and `advanced_ai` rather than assume it: a level-triggered strategy
re-enters the same setup bar after bar, which shows up as a short median
gap between one exit and the next entry plus a high same-direction rate.
Reference points from that earlier measurement: `ema_rsi` pre-fix had a
5-minute median gap and 63% same-direction; `institutional_momentum` had
20 minutes and 49%.

Both the production path (`config/settings.json`) and the legacy path
(no settings) are reported, because for several strategies these are very
different entry paths -- `institutional_momentum` reads seven of its own
filter flags from that same settings dict.

Nothing here modifies strategy or engine code. The one piece of
instrumentation (`_record_risk_reasons`) wraps `RiskManager.can_trade` to
tally its returned reason strings and forwards the real return value
unchanged, so an audited run and a normal run take identical decisions.
"""
from __future__ import annotations

import argparse
import contextlib
import pickle
import sys
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd

from shared.risk import RiskManager

from .classify import DEFAULT_RISK_PER_TRADE, classify_strategy
from .entry_quality import find_missed_runs, position_frame
from .exit_quality import _classify_reason, analyse_exit_quality
from .metrics import compute_metrics
from .production_settings import load_production_settings, resolve_max_trades_per_day
from .regimes import REGIME_NAMES, classify_daily_regimes
from .run_validation import (
    _WARMUP_CALENDAR_DAYS,
    _reset_cross_strategy_singletons,
    run_strategy_day_isolated,
)

RESULTS_DIR = Path(__file__).parent / "results"


def _q2(m: dict) -> float:
    consec = int(m.get("max_consecutive_losses", 0) or 0)
    expected = consec * DEFAULT_RISK_PER_TRADE * 100.0
    return float(m.get("max_drawdown_pct", 0.0)) / expected if expected > 0 else float("nan")


def _fmt(v, nd=2):
    if v is None or isinstance(v, str):
        return "—" if v is None else v
    if isinstance(v, float) and (np.isnan(v) or np.isinf(v)):
        return "—"
    return f"{v:,.{nd}f}"


@contextlib.contextmanager
def _record_risk_reasons(sink: Counter):
    """Tally the risk gate's own reason strings for the duration of a run.

    `harness.run_strategy_backtest` discards `can_trade`'s reason, so the
    `rejected_risk_gate` counter cannot distinguish a daily-loss halt from
    a trade-cap hit — a distinction this audit needs, since one is a
    circuit breaker firing and the other is a throttle binding. The wrapper
    returns the real result untouched; only the reason is observed.
    """
    original = RiskManager.can_trade

    def wrapper(self, *a, **kw):
        allowed, reason = original(self, *a, **kw)
        if not allowed:
            sink[reason] += 1
        return allowed, reason

    RiskManager.can_trade = wrapper
    try:
        yield
    finally:
        RiskManager.can_trade = original


def _signal_frame(strategy: str, df: pd.DataFrame, settings: dict) -> pd.Series:
    """The signals the strategy actually emitted, reproducing
    `run_strategy_day_isolated`'s per-day 30-calendar-day warm-up windowing
    exactly. Computing them over one continuous frame instead would give a
    different series than the run being described."""
    from trading_bot.strategies.registry import registry

    rows = []
    for day in sorted(set(df.index.date)):
        window_start = pd.Timestamp(day) - pd.Timedelta(days=_WARMUP_CALENDAR_DAYS)
        w = df.loc[str(window_start.date()):str(day)]
        if (w.index.date == day).sum() < 5:
            continue
        res = registry.run_strategy(strategy, w, **settings)
        s = res[0] if isinstance(res, tuple) else res
        rows.append(s[s.index.date == day])
    return pd.concat(rows) if rows else pd.Series(dtype=int)


def _coverage(runs: pd.DataFrame, pos: pd.DataFrame) -> tuple[float, float]:
    if runs.empty or pos.empty:
        return float("nan"), float("nan")
    cov, held = [], []
    for r in runs.itertuples():
        e = pos[(pos.direction == r.direction) & (pos.date == r.date)]
        hit = e[(e.entry_time <= r.end) & (e.exit_time >= r.start)]
        cov.append(not hit.empty)
        if hit.empty or r.end == r.start:
            continue
        span = (r.end - r.start).total_seconds()
        h = sum(max(0.0, (min(x.exit_time, r.end) - max(x.entry_time, r.start)).total_seconds())
                for x in hit.itertuples())
        held.append(min(100.0, h / span * 100.0))
    return float(np.mean(cov) * 100), (float(np.median(held)) if held else float("nan"))


def _classify_misses(runs: pd.DataFrame, pos: pd.DataFrame, sig: pd.Series) -> Counter:
    """Why was each uncovered run missed? Distinguishes the strategy's own
    philosophy (no setup existed) from a blocked entry (setup existed, the
    system refused) from an occupancy conflict (holding the other side).
    Only the last two are candidates for a change."""
    out: Counter = Counter()
    if runs.empty:
        return out
    for r in runs.itertuples():
        e = pos[(pos.direction == r.direction) & (pos.date == r.date)]
        if not e[(e.entry_time <= r.end) & (e.exit_time >= r.start)].empty:
            continue
        want = 1 if r.direction == "CE" else -1
        # A signal is "for" this run if it fired from one bar before the run
        # started through to its end — entering after the move has begun is
        # still participating in it.
        lo = r.start - pd.Timedelta(minutes=5)
        window = sig.loc[(sig.index >= lo) & (sig.index <= r.end)]
        if window.empty or not (window == want).any():
            out["no setup"] += 1
            continue
        held = pos[(pos.date == r.date) & (pos.direction != r.direction)
                   & (pos.entry_time <= r.end) & (pos.exit_time >= r.start)]
        out["opposite position held" if not held.empty else "signalled but blocked"] += 1
    return out


def _churn(pos: pd.DataFrame) -> dict:
    """Gap from one position's exit to the next entry on the same day, and
    how often the next entry repeats the direction that just closed."""
    if len(pos) < 2:
        return {}
    gaps, same_dir = [], []
    for _date, g in pos.groupby("date"):
        g = g.sort_values("entry_time")
        for a, b in zip(g.itertuples(), list(g.itertuples())[1:]):
            gaps.append((b.entry_time - a.exit_time).total_seconds() / 60.0)
            same_dir.append(b.direction == a.direction)
    if not gaps:
        return {}
    gaps = np.array(gaps)
    return {
        "n_reentries": len(gaps),
        "median_gap_min": float(np.median(gaps)),
        "p25_gap_min": float(np.percentile(gaps, 25)),
        "same_direction_pct": float(np.mean(same_dir) * 100),
        "immediate_pct": float((gaps <= 5).mean() * 100),
    }


def _duty_cycle(sig: pd.Series) -> dict:
    """How often the strategy's signal is non-zero, and how much of that is
    a repeat of the previous bar's signal (the churn precondition)."""
    if sig.empty:
        return {}
    nz = sig != 0
    repeat = nz & (sig == sig.shift(1))
    return {
        "bars": int(len(sig)),
        "signal_bars": int(nz.sum()),
        "duty_cycle_pct": float(nz.mean() * 100),
        "repeat_bars": int(repeat.sum()),
        "repeat_share_of_signals_pct": (
            float(repeat.sum() / nz.sum() * 100) if nz.sum() else float("nan")),
    }


def _evaluate(strategy, df, settings, capital, runs, regimes, risk_config=None):
    _reset_cross_strategy_singletons()
    reasons: Counter = Counter()
    with _record_risk_reasons(reasons):
        trades, diag = run_strategy_day_isolated(
            strategy, df, "NIFTY", capital, settings=settings, risk_config=risk_config
        )
    m = compute_metrics(trades, capital)
    by_regime = {r: compute_metrics(
        [t for t in trades if pd.Timestamp(t.entry_time).date() in set(regimes[regimes == r].index)],
        capital) for r in REGIME_NAMES}
    verdict = classify_strategy(m, by_regime)
    pos = position_frame(trades, df, settings=settings)
    sig = _signal_frame(strategy, df, settings)
    cov, held = _coverage(runs, pos)
    # A configuration can legitimately take zero trades — that is itself a
    # finding (see `institutional_momentum` on the production path), so the
    # report must be able to say so rather than die on an empty frame.
    legs_q, pos_q = ((pd.DataFrame(), pd.DataFrame()) if not trades
                     else analyse_exit_quality(trades, df))
    return {
        "metrics": m, "by_regime": by_regime, "verdict": verdict, "diag": diag,
        "pos": pos, "trades": trades, "q2": _q2(m), "sig": sig,
        "legs_q": legs_q, "pos_q": pos_q, "risk_reasons": reasons,
        "rally_coverage_pct": cov, "held_pct_of_covered": held,
        "false_signal_pct": (pos.first_touch == "loss_first").mean() * 100 if len(pos) else np.nan,
        "edge_pp": (((pos.first_touch == "win_first").mean()
                     - (pos.first_touch == "loss_first").mean()) * 100) if len(pos) else np.nan,
        "never_rose_pct": (pos.mfe_r <= 0).mean() * 100 if len(pos) else np.nan,
        "churn": _churn(pos), "duty": _duty_cycle(sig),
        "misses": _classify_misses(runs, pos, sig),
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--strategy", default="institutional_momentum")
    ap.add_argument("--data-path", default="data/NSE_NIFTY50-INDEX_5Min.csv")
    ap.add_argument("--start", default="2026-02-01")
    ap.add_argument("--end", default="2026-07-31")
    ap.add_argument("--initial-capital", type=float, default=100_000.0)
    ap.add_argument("--out", default=None)
    # Research options for the clean-sheet programme. Both default to the
    # established behaviour, so every existing invocation is unchanged.
    ap.add_argument("--window", choices=["dev", "oos"], default=None,
                    help="research split from research_config; overrides --start/--end")
    ap.add_argument("--risk-tier", choices=["default", "base"], default="default",
                    help="'base' pins sizing to the 1%% base tier (research only)")
    args = ap.parse_args()

    risk_config = None
    if args.risk_tier == "base":
        from .research_config import BASE_RISK_TIER
        risk_config = BASE_RISK_TIER

    if args.window:
        from .research_config import DEV_END, DEV_START, OOS_END, OOS_START
        args.start, args.end = (
            (DEV_START, DEV_END) if args.window == "dev" else (OOS_START, OOS_END)
        )

    df = pd.read_csv(args.data_path)
    df["datetime"] = pd.to_datetime(df["datetime"])
    df = df.set_index("datetime").sort_index().loc[args.start:args.end]
    regimes = classify_daily_regimes(df)
    prod = load_production_settings()
    runs = find_missed_runs(df, pd.DataFrame(columns=["direction", "date", "entry_time", "exit_time"]))

    paths = [("PRODUCTION (config/settings.json)", prod), ("legacy (no settings)", {})]
    out = {}
    for label, st in paths:
        print(f"running {label}...", file=sys.stderr)
        out[label] = _evaluate(args.strategy, df, st, args.initial_capital, runs,
                               regimes, risk_config=risk_config)

    P = out[paths[0][0]]
    L: list[str] = []
    A = L.append
    A(f"# Strategy audit — `{args.strategy}`\n")
    A(f"Window: {df.index.min()} → {df.index.max()} "
      f"({df.index.normalize().nunique()} trading days)"
      + (f" — **{args.window.upper()}** split" if args.window else "") + "  ")
    A(f"Risk tier: **{args.risk_tier}**"
      + (" (1% base, research)" if args.risk_tier == "base" else " (production defaults)") + "  ")
    A(f"Rally set: **{len(runs)}** sustained underlying moves (≥0.30% within 90 min).  ")
    flags = {k: v for k, v in prod.items() if k.startswith("enable_") and "filter" in k}
    A(f"Production entry flags: `{flags}`, daily cap "
      f"**{resolve_max_trades_per_day(prod) or 'unlimited'}**.\n")

    A("## 1. Baseline — production path vs legacy path\n")
    rows = [("trade_count", "trades (legs)", 0), ("net_profit", "net profit", 0),
            ("expectancy", "expectancy", 2), ("profit_factor", "profit factor", 2),
            ("max_drawdown_pct", "max drawdown %", 2), ("recovery_factor", "recovery factor", 2),
            ("win_rate_pct", "win rate %", 1), ("avg_risk_reward", "realised R:R", 2),
            ("max_consecutive_losses", "consecutive losses", 0),
            ("avg_holding_minutes", "avg holding min", 1)]
    A("| Metric | " + " | ".join(l for l, _s in paths) + " |")
    A("|---|---|---|")
    for key, label, nd in rows:
        A(f"| {label} | " + " | ".join(_fmt(out[l]['metrics'][key], nd) for l, _s in paths) + " |")
    for key, label, nd in [("q2", "Q2 ratio", 2), ("false_signal_pct", "false-signal rate %", 1),
                           ("edge_pp", "first-touch edge pp", 1), ("never_rose_pct", "never-rose %", 1),
                           ("rally_coverage_pct", "rally capture %", 1),
                           ("held_pct_of_covered", "held % of covered run", 1)]:
        A(f"| {label} | " + " | ".join(_fmt(out[l][key], nd) for l, _s in paths) + " |")
    A("| positions | " + " | ".join(str(len(out[l]['pos'])) for l, _s in paths) + " |")
    A("| **verdict** | " + " | ".join(f"**{out[l]['verdict'].classification}**" for l, _s in paths) + " |")
    A("")
    for label, _s in paths:
        v = out[label]["verdict"]
        A(f"`{label}` — {v.classification}: " + "; ".join(v.reasons) + "\n")

    A("## 2. Signal duty cycle and churn\n")
    A("Tests the re-entry mechanism found in `ema_rsi` and `advanced_ai` "
      "rather than assuming it. A level-triggered strategy re-enters the same "
      "setup bar after bar, which shows up as a short median gap between one "
      "exit and the next entry plus a high same-direction rate.\n")
    A("| Measure | " + " | ".join(l for l, _s in paths) + " |")
    A("|---|---|---|")
    for k, lbl, nd in [("bars", "bars evaluated", 0), ("signal_bars", "signal bars", 0),
                       ("duty_cycle_pct", "duty cycle %", 1),
                       ("repeat_share_of_signals_pct", "signals repeating previous bar %", 1)]:
        A(f"| {lbl} | " + " | ".join(_fmt(out[l]['duty'].get(k), nd) for l, _s in paths) + " |")
    for k, lbl, nd in [("n_reentries", "same-day re-entries", 0),
                       ("median_gap_min", "median exit→next entry (min)", 1),
                       ("p25_gap_min", "p25 gap (min)", 1),
                       ("immediate_pct", "re-entries within one bar %", 1),
                       ("same_direction_pct", "same-direction re-entries %", 1)]:
        A(f"| {lbl} | " + " | ".join(_fmt(out[l]['churn'].get(k), nd) for l, _s in paths) + " |")
    A("")

    pos = P["pos"]
    if pos.empty:
        A("## 3-8. Production path takes ZERO trades\n")
        A(f"`{args.strategy}` opened **no positions at all** on the production "
          f"path across {P['diag']['days_run']} trading days "
          f"(`candidate_signals` = {P['diag']['candidate_signals']}), so every "
          "position-level section below is undefined. That is the audit's "
          "headline finding, not a harness failure — the legacy column above "
          "is the only configuration of this strategy that trades.\n")
        outp = Path(args.out or (RESULTS_DIR / f"audit_{args.strategy}.md"))
        outp.parent.mkdir(parents=True, exist_ok=True)
        outp.write_text("\n".join(L), encoding="utf-8")
        print(f"Written {outp}", file=sys.stderr)
        return

    A("## 3. Entry quality (production path, exit-independent)\n")
    wf = (pos.first_touch == "win_first").sum()
    lf = (pos.first_touch == "loss_first").sum()
    nn = (pos.first_touch == "none").sum()
    A("First touch of ±1R, where R is the position's real "
      "`resolve_initial_stop` distance. `false entry` = loss-first.\n")
    A("| Outcome | n | share |")
    A("|---|---|---|")
    A(f"| win-first | {wf} | {wf/len(pos)*100:.1f}% |")
    A(f"| **loss-first (false entry)** | {lf} | **{lf/len(pos)*100:.1f}%** |")
    A(f"| neither within the day | {nn} | {nn/len(pos)*100:.1f}% |")
    A("")
    A("| Excursion (R) | p10 | p25 | median | p75 | p90 |")
    A("|---|---|---|---|---|---|")
    for col in ("mfe_r", "mae_r"):
        q = pos[col].dropna()
        A(f"| {col} | " + " | ".join(_fmt(np.percentile(q, p)) for p in (10, 25, 50, 75, 90)) + " |")
    A("")

    A("### 3b. Entry timing\n")
    A("| Session bucket | n | first-touch edge pp | net P&L | mean P&L |")
    A("|---|---|---|---|---|")
    buckets = [("09:15-10:00", 555, 600), ("10:00-11:00", 600, 660), ("11:00-12:30", 660, 750),
               ("12:30-14:00", 750, 840), ("14:00-15:30", 840, 930)]
    for lbl, lo, hi in buckets:
        g = pos[(pos.minute_of_day >= lo) & (pos.minute_of_day < hi)]
        if g.empty:
            A(f"| {lbl} | 0 | — | — | — |")
            continue
        edge = ((g.first_touch == "win_first").mean() - (g.first_touch == "loss_first").mean()) * 100
        A(f"| {lbl} | {len(g)} | {edge:+.1f} | {g.pnl.sum():,.0f} | {g.pnl.mean():,.0f} |")
    A("")

    A("## 4. Exit behaviour (production path)\n")
    A("Grouped by exit MECHANISM — `TieredExitManager`'s reason strings embed "
      "live numbers, so the raw text would give one bucket per trade.\n")
    A("| Exit mechanism | n | % | net P&L | mean | median hold (min) |")
    A("|---|---|---|---|---|---|")
    pos = pos.assign(exit_class=pos.final_exit_reason.map(_classify_reason))
    for reason, g in pos.groupby("exit_class"):
        A(f"| `{reason}` | {len(g)} | {len(g)/len(pos)*100:.1f}% | {g.pnl.sum():,.0f} | "
          f"{g.pnl.mean():,.0f} | {g.holding_minutes.median():.0f} |")
    A("")
    pq, lq = P["pos_q"], P["legs_q"]
    if not pq.empty:
        A("### 4b. Premature exits and trend capture\n")
        A("Premature = the premium exceeded the exit price within the next 60 "
          "minutes of the same day, i.e. the position was closed into a move "
          "that was still running.\n")
        A("| Measure | value |")
        A("|---|---|")
        A(f"| positions measured | {len(pq)} |")
        A(f"| premature exits | {pq.premature.mean()*100:.1f}% |")
        A(f"| median missed upside after exit | {pq.missed_upside_pct.median():.2f}% |")
        A(f"| p90 missed upside after exit | {pq.missed_upside_pct.quantile(0.90):.2f}% |")
        A(f"| median capture of the in-trade move | {pq.capture_pct.median():.1f}% |")
        A(f"| median trend capture (vs day's best) | {pq.trend_capture_pct.median():.1f}% |")
        for h in (5, 15, 30, 60):
            A(f"| median continuation +{h}min after exit | {pq[f'cont_{h}m_pct'].median():.2f}% |")
        A("")
        A("### 4c. Exit mechanism mix (legs) and trailing behaviour\n")
        A("| Mechanism | legs | % | median realised % | median giveback pp | armed % |")
        A("|---|---|---|---|---|---|")
        for cls, g in lq.groupby("exit_reason_class"):
            A(f"| `{cls}` | {len(g)} | {len(g)/len(lq)*100:.1f}% | {g.realised_pct.median():.2f} | "
              f"{g.giveback_pct.median():.2f} | {g.armed.mean()*100:.0f}% |")
        A("")

    A("## 5. Missed opportunities (production path)\n")
    A("Every rally in the fixed set the strategy was NOT positioned for, "
      "classified by cause. Only `signalled but blocked` and `opposite "
      "position held` are addressable; `no setup` is the strategy's own "
      "philosophy.\n")
    miss = P["misses"]
    total_missed = sum(miss.values())
    A("| Cause | n | share of missed |")
    A("|---|---|---|")
    for cause, n in miss.most_common():
        A(f"| {cause} | {n} | {n/total_missed*100:.1f}% |")
    A(f"| **total missed** | **{total_missed}** | of {len(runs)} runs |")
    A("")

    A("## 6. Position sizing, stops and risk taken (production path)\n")
    A("| Measure | p10 | median | p90 |")
    A("|---|---|---|---|")
    for col, lbl in [("entry_premium", "entry premium"), ("risk", "risk per unit (₹)"),
                     ("risk_pct", "stop distance % of premium")]:
        q = pos[col].dropna()
        A(f"| {lbl} | {np.percentile(q,10):,.2f} | {np.percentile(q,50):,.2f} | "
          f"{np.percentile(q,90):,.2f} |")
    A("")
    A("| Stop band | positions | share | net P&L | false-signal % |")
    A("|---|---|---|---|---|")
    for band, g in pos.groupby("sl_band_label"):
        fs = (g.first_touch == "loss_first").mean() * 100
        A(f"| `{band}` | {len(g)} | {len(g)/len(pos)*100:.1f}% | {g.pnl.sum():,.0f} | {fs:.1f}% |")
    A("")

    A("## 7. Rejection and risk-control behaviour\n")
    A("| Counter | " + " | ".join(l for l, _s in paths) + " |")
    A("|---|---|---|")
    for k in ("days_run", "candidate_signals", "rejected_risk_gate", "rejected_market_hours",
              "rejected_untradeable_sl"):
        A(f"| {k} | " + " | ".join(str(out[l]['diag'].get(k, '—')) for l, _s in paths) + " |")
    A("")
    A("Risk-gate rejections by the gate's own reason string:\n")
    A("| Reason | " + " | ".join(l for l, _s in paths) + " |")
    A("|---|---|---|")
    all_reasons = sorted({r for l, _s in paths for r in out[l]["risk_reasons"]})
    for r in all_reasons:
        A(f"| `{r}` | " + " | ".join(str(out[l]["risk_reasons"].get(r, 0)) for l, _s in paths) + " |")
    A("")
    daily = pos.groupby("date").pnl.sum()
    A(f"Trades/day (production): mean **{len(pos)/max(P['diag']['days_run'],1):.2f}**, "
      f"max **{pos.groupby('date').size().max()}**. "
      f"Worst day **₹{daily.min():,.0f}**, best day **₹{daily.max():,.0f}**, "
      f"days below −₹5,000: **{int((daily < -5000).sum())}** of {len(daily)}.\n")

    A("## 8. Regime detail (production path)\n")
    A("| Regime | days | trades | net | PF | DD% | win% | expectancy |")
    A("|---|---|---|---|---|---|---|---|")
    for r in REGIME_NAMES:
        m = P["by_regime"][r]
        n_days = int((regimes == r).sum())
        if not m["trade_count"]:
            A(f"| {r} | {n_days} | 0 | — | — | — | — | — |")
            continue
        A(f"| {r} | {n_days} | {m['trade_count']} | {m['net_profit']:,.0f} | "
          f"{_fmt(m['profit_factor'])} | {_fmt(m['max_drawdown_pct'])} | "
          f"{_fmt(m['win_rate_pct'],1)} | {_fmt(m['expectancy'])} |")
    A("")

    outp = Path(args.out or (RESULTS_DIR / f"audit_{args.strategy}.md"))
    outp.parent.mkdir(parents=True, exist_ok=True)
    outp.write_text("\n".join(L), encoding="utf-8")
    for label, _s in paths:
        tag = "prod" if label.startswith("PROD") else "legacy"
        with open(RESULTS_DIR / f"trades_{args.strategy}_{tag}.pkl", "wb") as fh:
            pickle.dump(out[label]["trades"], fh)
        out[label]["pos"].to_pickle(RESULTS_DIR / f"pos_{args.strategy}_{tag}.pkl")
    print(f"Written {outp}", file=sys.stderr)


if __name__ == "__main__":
    main()
