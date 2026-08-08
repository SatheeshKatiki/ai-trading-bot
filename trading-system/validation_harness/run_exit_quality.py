"""Runner for the exit-quality / trend-capture audit.

    python -m validation_harness.run_exit_quality --strategy ema_rsi

Loads the cached day-isolated trade set produced by
`run_dd_attribution.py` (`results/trades_<strategy>.pkl`) — the same
trades the validation report is computed from, so every number here
reconciles with it — and writes a markdown audit to
`results/exit_quality_<strategy>.md`.

Read-only: it re-prices, it never re-trades.
"""
from __future__ import annotations

import argparse
import pickle
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from .exit_quality import (
    PARTIAL_TARGET_REWARD,
    TRAILING_ACTIVATION_PCT,
    TRAILING_OFFSET_PCT,
    analyse_exit_quality,
    verify_reconstruction,
)

RESULTS_DIR = Path(__file__).parent / "results"


def _q(s: pd.Series, q: float) -> float:
    s = s.dropna()
    return float(np.percentile(s, q)) if len(s) else float("nan")


def _fmt(x, nd=2):
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return "—"
    return f"{x:,.{nd}f}"


def _dist_table(df: pd.DataFrame, col: str, by: str, lines: list[str], nd: int = 2) -> None:
    lines.append(f"| {by} | n | mean | p25 | median | p75 | p90 |")
    lines.append("|---|---|---|---|---|---|---|")
    for key, g in df.groupby(by):
        s = g[col].dropna()
        if s.empty:
            continue
        lines.append(
            f"| {key} | {len(s)} | {_fmt(s.mean(), nd)} | {_fmt(_q(s,25), nd)} | "
            f"{_fmt(s.median(), nd)} | {_fmt(_q(s,75), nd)} | {_fmt(_q(s,90), nd)} |"
        )
    s = df[col].dropna()
    lines.append(
        f"| **ALL** | {len(s)} | {_fmt(s.mean(), nd)} | {_fmt(_q(s,25), nd)} | "
        f"{_fmt(s.median(), nd)} | {_fmt(_q(s,75), nd)} | {_fmt(_q(s,90), nd)} |"
    )
    lines.append("")


def _elasticity(trades, underlying: pd.DataFrame, instrument: str = "NIFTY") -> dict:
    """Measure, from the data, how much a 1% move in the underlying moves the
    option premium — the conversion factor between the unit space
    `trailing_offset_pct` was calibrated in and the one it is applied in."""
    from .exit_quality import _premium_series, reconstruct_contract
    from .premium_simulator import DEFAULT_IV

    omegas: list[float] = []
    bar_moves: list[float] = []
    first_down = total = 0
    seen: set = set()
    for t in trades:
        key = (t.symbol, str(t.entry_time))
        if key in seen:
            continue
        seen.add(key)
        contract = reconstruct_contract(t, underlying, instrument)
        if contract is None:
            continue
        entry_t, exit_t = pd.Timestamp(t.entry_time), pd.Timestamp(t.exit_time)
        bars = underlying.loc[(underlying.index >= entry_t) & (underlying.index <= exit_t)]
        if len(bars) < 2:
            continue
        prem = _premium_series(contract, bars, DEFAULT_IV)
        up = bars["close"].pct_change().dropna() * 100
        pp = prem.pct_change().dropna() * 100
        mask = up.abs() > 1e-9
        if mask.any():
            omegas.extend((pp[mask].abs() / up[mask].abs()).tolist())
        bar_moves.extend(pp.abs().tolist())

        if t.exit_reason.startswith("Trailing Stop-Loss Hit (Offset)"):
            profit = (prem - t.entry_premium) / t.entry_premium * 100
            armed = np.where(profit.values >= TRAILING_ACTIVATION_PCT)[0]
            if len(armed):
                seg = prem.values[armed[0]:]
                downs = np.where(seg < np.maximum.accumulate(seg))[0]
                total += 1
                if len(downs) and downs[0] == len(seg) - 1:
                    first_down += 1

    o = np.array([x for x in omegas if np.isfinite(x)])
    b = np.array([x for x in bar_moves if np.isfinite(x)])
    return {
        "n": len(o),
        "median": float(np.median(o)), "p25": _q(pd.Series(o), 25), "p75": _q(pd.Series(o), 75),
        "bar_p10": _q(pd.Series(b), 10), "bar_p25": _q(pd.Series(b), 25),
        "bar_p50": _q(pd.Series(b), 50), "bar_p75": _q(pd.Series(b), 75),
        "bar_p90": _q(pd.Series(b), 90),
        "bar_over_offset": float((b > TRAILING_OFFSET_PCT).mean()),
        "first_down_pct": (first_down / total * 100.0) if total else float("nan"),
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--strategy", default="ema_rsi")
    ap.add_argument("--data-path", default="data/NSE_NIFTY50-INDEX_5Min.csv")
    ap.add_argument("--start", default="2026-02-01")
    ap.add_argument("--end", default="2026-07-31")
    ap.add_argument("--instrument", default="NIFTY")
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

    ver = verify_reconstruction(trades, df, instrument=args.instrument)
    legs, pos = analyse_exit_quality(trades, df, instrument=args.instrument)

    L: list[str] = []
    A = L.append
    A(f"# Exit-quality & trend-capture audit — `{args.strategy}`\n")
    A(f"Window: {df.index.min()} → {df.index.max()}  ")
    A(f"Trading days: {df.index.normalize().nunique()}  ")
    A(f"Legs: {len(legs)}   Positions: {len(pos)}\n")
    A("## 0. Reconstruction fidelity\n")
    A("Every number below is computed from a re-priced premium path. That path "
      "is only trustworthy if it reproduces the premiums the harness itself "
      "recorded, so that is checked first, on every leg:\n")
    A(f"- legs checked: **{ver['legs']}**")
    A(f"- unreconstructable: **{ver['unreconstructable']}**")
    A(f"- worst entry-premium error: **Rs {ver['max_entry_premium_error']:.6f}**\n")

    # ── 1. Exit reason distribution ─────────────────────────────────
    A("## 1. Exit reason distribution\n")
    A("### Legs (every close, including the 50% partial)\n")
    A("| Exit reason | n | % | net P&L | mean P&L | win rate |")
    A("|---|---|---|---|---|---|")
    for reason, g in legs.groupby("exit_reason"):
        A(f"| `{reason}` | {len(g)} | {len(g)/len(legs)*100:.1f}% | "
          f"{g.pnl.sum():,.0f} | {g.pnl.mean():,.0f} | {(g.pnl>0).mean()*100:.1f}% |")
    A(f"| **TOTAL** | {len(legs)} | 100% | {legs.pnl.sum():,.0f} | "
      f"{legs.pnl.mean():,.0f} | {(legs.pnl>0).mean()*100:.1f}% |\n")

    A("### Positions (what finally closed the position)\n")
    A("| Final exit | n | % | net P&L | mean P&L | win rate | median hold (min) |")
    A("|---|---|---|---|---|---|---|")
    for reason, g in pos.groupby("final_exit_reason_class"):
        A(f"| `{reason}` | {len(g)} | {len(g)/len(pos)*100:.1f}% | {g.pnl.sum():,.0f} | "
          f"{g.pnl.mean():,.0f} | {(g.pnl>0).mean()*100:.1f}% | {g.holding_minutes.median():.0f} |")
    A(f"| **TOTAL** | {len(pos)} | 100% | {pos.pnl.sum():,.0f} | {pos.pnl.mean():,.0f} | "
      f"{(pos.pnl>0).mean()*100:.1f}% | {pos.holding_minutes.median():.0f} |\n")

    # ── 2. MFE and capture ──────────────────────────────────────────
    A("## 2. MFE and capture (position level)\n")
    A("`mfe_pct` = best premium reached while the position was open, % of entry. "
      "`capture_pct` = quantity-weighted realised % / mfe_pct.\n")
    A("### MFE % by final exit\n")
    _dist_table(pos, "mfe_pct", "final_exit_reason_class", L)
    A("### Capture % of the in-trade move, by final exit\n")
    _dist_table(pos, "capture_pct", "final_exit_reason_class", L, nd=1)
    A("### Give-back (MFE % − realised %) by final exit\n")
    _dist_table(pos, "giveback_pct", "final_exit_reason_class", L)

    winners = pos[pos.mfe_pct > 0]
    A(f"Positions that were ever in profit: **{len(winners)}/{len(pos)}** "
      f"({len(winners)/len(pos)*100:.1f}%)  ")
    A(f"…of which ended NEGATIVE: **{(winners.realised_pct <= 0).sum()}** "
      f"({(winners.realised_pct <= 0).mean()*100:.1f}%)\n")

    # ── 3. Trend / rally capture ────────────────────────────────────
    A("## 3. Trend / rally capture\n")
    A("`day_best_pct` = best premium available from entry to the END OF THE "
      "ENTRY DAY, whether or not we still held it — the whole intraday move "
      "the strategy could have had without carrying overnight. "
      "`trend_capture_pct` = realised % / day_best_pct.\n")
    A("### Full available move (day_best_pct) by final exit\n")
    _dist_table(pos, "day_best_pct", "final_exit_reason_class", L)
    A("### Trend capture % by final exit\n")
    _dist_table(pos, "trend_capture_pct", "final_exit_reason_class", L, nd=1)

    for band, label in [(10, "10%"), (20, "20%"), (30, "30%")]:
        big = pos[pos.day_best_pct >= band]
        if big.empty:
            continue
        A(f"**Rallies with ≥{label} of premium available on the day** — n={len(big)}, "
          f"median available {big.day_best_pct.median():.1f}%, "
          f"median captured {big.realised_pct.median():.1f}%, "
          f"median trend capture **{big.trend_capture_pct.median():.1f}%**  ")
    A("")

    # ── 4. Post-exit continuation & premature exits ─────────────────
    A("## 4. Post-exit continuation\n")
    A("Best premium in the N minutes AFTER the position was fully closed, "
      "as % of the exit premium. Same trading day only.\n")
    A("| Final exit | n | +5m | +15m | +30m | +60m | median mins to post-exit peak |")
    A("|---|---|---|---|---|---|---|")
    for reason, g in pos.groupby("final_exit_reason_class"):
        A(f"| `{reason}` | {len(g)} | {_fmt(g.cont_5m_pct.median())} | "
          f"{_fmt(g.cont_15m_pct.median())} | {_fmt(g.cont_30m_pct.median())} | "
          f"{_fmt(g.cont_60m_pct.median())} | {_fmt(g.minutes_to_best_after_exit.median(), 0)} |")
    A(f"| **ALL** | {len(pos)} | {_fmt(pos.cont_5m_pct.median())} | "
      f"{_fmt(pos.cont_15m_pct.median())} | {_fmt(pos.cont_30m_pct.median())} | "
      f"{_fmt(pos.cont_60m_pct.median())} | {_fmt(pos.minutes_to_best_after_exit.median(), 0)} |\n")

    A("### Premature exits\n")
    A("Mechanical definition: the premium exceeded the exit price by more than "
      "one tick within 60 minutes of the exit — the position was closed into a "
      "move that was still running.\n")
    A("| Final exit | n | premature | median missed upside % | p90 missed upside % |")
    A("|---|---|---|---|---|")
    for reason, g in pos.groupby("final_exit_reason_class"):
        p = g.premature.dropna()
        A(f"| `{reason}` | {len(p)} | {p.mean()*100:.1f}% | "
          f"{_fmt(g.missed_upside_pct.median())} | {_fmt(_q(g.missed_upside_pct, 90))} |")
    p = pos.premature.dropna()
    A(f"| **ALL** | {len(p)} | {p.mean()*100:.1f}% | {_fmt(pos.missed_upside_pct.median())} | "
      f"{_fmt(_q(pos.missed_upside_pct, 90))} |\n")

    # ── 5. Trailing-stop behaviour ──────────────────────────────────
    A("## 5. Trailing-stop behaviour\n")
    A(f"Engine config in the harness: `trailing_activation_pct={TRAILING_ACTIVATION_PCT}`, "
      f"`trailing_offset_pct={TRAILING_OFFSET_PCT}`, `atr_multiplier=1.5`, "
      f"`partial_target_reward={PARTIAL_TARGET_REWARD}`, `partial_booking_pct=50`.\n")
    A("Two independent trailing mechanisms run side by side and whichever fires "
      "first wins: an ATR trailing stop (`highest − 1.5×ATR`) and a percentage "
      "trailing stop that exits when profit gives back "
      f"`{TRAILING_OFFSET_PCT}` PERCENTAGE POINTS from its peak. Their exit "
      "reasons are kept distinct here.\n")
    trail = legs[legs.exit_reason_class.isin(["trail_offset", "trail_atr"])]
    A("| Mechanism | legs | % of all legs | net P&L | median MFE % | median capture % | median give-back % |")
    A("|---|---|---|---|---|---|---|")
    for k, g in trail.groupby("exit_reason_class"):
        A(f"| `{k}` | {len(g)} | {len(g)/len(legs)*100:.1f}% | {g.pnl.sum():,.0f} | "
          f"{_fmt(g.mfe_pct.median())} | {_fmt(g.capture_pct.median(),1)} | {_fmt(g.giveback_pct.median())} |")
    A("")

    armed = legs[legs.armed]
    A(f"Legs whose profit ever reached the {TRAILING_ACTIVATION_PCT}% activation "
      f"threshold: **{len(armed)}/{len(legs)}** ({len(armed)/len(legs)*100:.1f}%)  ")
    A(f"Median bars from entry to arming: **{_fmt(armed.bars_to_arm.median(),0)}** "
      f"(one bar = 5 min)  ")
    A(f"Median bars held AFTER arming before the exit: "
      f"**{_fmt(armed.bars_armed_before_exit.median(),0)}**\n")

    off = legs[legs.exit_reason_class == "trail_offset"]
    A(f"### Where the percentage trailing stop fires\n")
    A("Peak profit % reached before the offset stop closed the leg:\n")
    A("| n | p10 | p25 | median | p75 | p90 | max |")
    A("|---|---|---|---|---|---|---|")
    A(f"| {len(off)} | {_fmt(_q(off.mfe_pct,10))} | {_fmt(_q(off.mfe_pct,25))} | "
      f"{_fmt(off.mfe_pct.median())} | {_fmt(_q(off.mfe_pct,75))} | "
      f"{_fmt(_q(off.mfe_pct,90))} | {_fmt(off.mfe_pct.max())} |\n")
    A(f"Offset-stop legs whose peak profit never exceeded **2%**: "
      f"**{(off.mfe_pct < 2).sum()}/{len(off)}** ({(off.mfe_pct < 2).mean()*100:.1f}%)  ")
    A(f"Offset-stop legs that were premature: **{off.premature.dropna().mean()*100:.1f}%**, "
      f"median missed upside **{_fmt(off.missed_upside_pct.median())}%**\n")

    # ── 6. Partial booking / runner behaviour ───────────────────────
    A("## 6. Partial profit booking and the 'runner'\n")
    A("Partial booking closes 50% at 1:1 reward:risk and moves the stop to "
      "breakeven. The remaining half is the position's runner — the piece that "
      "is supposed to capture the trend.\n")
    pb = pos[pos.partial_booked]
    A(f"Positions that reached partial booking: **{len(pb)}/{len(pos)}** "
      f"({len(pb)/len(pos)*100:.1f}%)\n")
    if len(pb):
        runner_gap = []
        for _, p in pb.iterrows():
            lg = legs[(legs.symbol == p.symbol) & (legs.entry_time == p.entry_time)]
            partial_leg = lg[lg.exit_reason_class == "partial"]
            if partial_leg.empty:
                continue
            t_partial = partial_leg.exit_time.max()
            if p.exit_time > t_partial:
                runner_gap.append({
                    "minutes": (p.exit_time - t_partial).total_seconds() / 60.0,
                    "final": p.final_exit_reason_class,
                })
        rg = pd.DataFrame(runner_gap)
        if not rg.empty:
            A(f"Time the runner survived after the partial booking:  ")
            A(f"median **{rg.minutes.median():.0f} min** "
              f"({rg.minutes.median()/5:.0f} bars), "
              f"p75 {_q(rg.minutes,75):.0f} min, p90 {_q(rg.minutes,90):.0f} min  ")
            A(f"Runners closed within ONE 5-minute bar of the partial booking: "
              f"**{(rg.minutes <= 5).sum()}/{len(rg)}** ({(rg.minutes<=5).mean()*100:.1f}%)\n")
            A("| What closed the runner | n | % |")
            A("|---|---|---|")
            for k, g in rg.groupby("final"):
                A(f"| `{k}` | {len(g)} | {len(g)/len(rg)*100:.1f}% |")
            A("")

    # ── 7. Target and stop-loss behaviour ───────────────────────────
    A("## 7. Target and stop-loss behaviour\n")
    tgt = (legs.exit_reason_class == "target").sum()
    A(f"`Profit Target Hit` exits: **{tgt}**. Option entries are opened with "
      "`target=0.0` (\"no fixed profit target — unlimited upside, managed by the "
      "trailing stop\"), so this mechanism is inert by design; the number above "
      "confirms it never fires.\n")
    A("### Initial stop-loss band mix\n")
    A("| Band | positions | net P&L | win rate | median MFE % | median realised % |")
    A("|---|---|---|---|---|---|")
    for band, g in pos.groupby("sl_band_label"):
        A(f"| {band} | {len(g)} | {g.pnl.sum():,.0f} | {(g.pnl>0).mean()*100:.1f}% | "
          f"{_fmt(g.mfe_pct.median())} | {_fmt(g.realised_pct.median())} |")
    A("")
    stops = pos[pos.final_exit_reason_class == "stop"]
    if len(stops):
        be = stops[stops.realised_pct.abs() < 1.0]
        A(f"`Stop-Loss Hit` positions: **{len(stops)}**, of which "
          f"**{len(be)}** ({len(be)/len(stops)*100:.1f}%) closed within ±1% of "
          "entry — i.e. they are breakeven-stop exits on a position that had "
          "already partially booked, not initial-stop losses.  ")
        A(f"Median MFE before the stop: **{_fmt(stops.mfe_pct.median())}%**  ")
        A(f"Premature (recovered above the exit within 60 min): "
          f"**{stops.premature.dropna().mean()*100:.1f}%**\n")

    # ── 8. Unit-space check on the percentage trailing offset ───────
    A("## 8. Unit-space check: what is `trailing_offset_pct` actually worth?\n")
    A("`trailing_offset_pct` came from `backtesting_engine/run.py`, which applies "
      "it to the P&L % of the UNDERLYING instrument (its own comment: \"Give 0.35% "
      "room so we don't exit too early on volatility\"). `SmartExitEngine` applies "
      "the same number to the P&L % of an OPTION PREMIUM. Those are different "
      "units. This section measures the conversion factor from the data itself.\n")
    el = _elasticity(trades, df, instrument=args.instrument)
    A(f"Premium elasticity (|premium % move| / |underlying % move|), measured over "
      f"{el['n']:,} held 5-minute bars:  ")
    A(f"median **{el['median']:.1f}x**, p25 {el['p25']:.1f}x, p75 {el['p75']:.1f}x\n")
    spot = float(df['close'].median())
    idx_equiv = TRAILING_OFFSET_PCT / el['median']
    A(f"So a give-back of **{TRAILING_OFFSET_PCT} percentage points of premium** is "
      f"a give-back of **{idx_equiv:.4f}% of the underlying** — about "
      f"**{idx_equiv/100*spot:.1f} NIFTY points** at this window's median index level "
      f"of {spot:,.0f}.  ")
    A(f"The rule was designed to allow {TRAILING_OFFSET_PCT}% of the underlying, i.e. "
      f"~{TRAILING_OFFSET_PCT/100*spot:.0f} points. As ported, it allows about "
      f"**{el['median']:.0f}x less room than its own stated design intent**.\n")
    A("Against the noise floor of a single bar:\n")
    A("| |premium move| in one 5-min bar | p10 | p25 | median | p75 | p90 |")
    A("|---|---|---|---|---|---|")
    A(f"| percentage points | {el['bar_p10']:.2f} | {el['bar_p25']:.2f} | "
      f"{el['bar_p50']:.2f} | {el['bar_p75']:.2f} | {el['bar_p90']:.2f} |\n")
    A(f"**{el['bar_over_offset']*100:.1f}%** of individual 5-minute bars move the "
      f"premium by more than the entire {TRAILING_OFFSET_PCT}pp allowance on their "
      "own. The threshold sits below the noise floor of one bar, so it does not "
      "act as a trailing stop at all — it acts as \"exit on the first close below "
      "the peak\".\n")
    A(f"Measured directly: **{el['first_down_pct']:.1f}%** of offset-stop exits fired "
      "on the FIRST 5-minute close below the running peak. The give-back actually "
      f"realised at those exits has a median of **{off.giveback_pct.median():.2f}pp** "
      f"— {off.giveback_pct.median()/TRAILING_OFFSET_PCT:.0f}x the nominal threshold, "
      "because a 5-minute bar cannot resolve 0.35pp. Live polling is ~1s, so live "
      "fires even closer to the peak: the harness UNDERSTATES this effect.\n")

    out = Path(args.out or (RESULTS_DIR / f"exit_quality_{args.strategy}.md"))
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(L), encoding="utf-8")

    legs.to_pickle(RESULTS_DIR / f"eq_legs_{args.strategy}.pkl")
    pos.to_pickle(RESULTS_DIR / f"eq_pos_{args.strategy}.pkl")
    print(f"Written {out}", file=sys.stderr)
    print("\n".join(L))


if __name__ == "__main__":
    main()
