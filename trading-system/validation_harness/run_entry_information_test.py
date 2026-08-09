"""Does the entry carry information, or is the exit engine doing the work?

    python -m validation_harness.run_entry_information_test

The control this project needs most
-----------------------------------
`drl_strategy` posted PF 1.07 over 1,189 trades while being *provably
market-blind*: a +7,500-point uptrend and a -7,500-point downtrend
produced byte-identical signals. Its apparent edge belonged entirely to
`SmartExitEngine`. That is the standing proof that **a profitable
backtest is not evidence of entry quality** in this system.

So before any new strategy is believed, its entries must beat entries
chosen at random through the same pipeline.

Method
------
The measure is **first touch of ±1R** — walk the option-premium path
forward from the entry bar and record whether it reaches
`entry + R` before `entry - R`, where R is the real
`resolve_initial_stop` distance. It is **exit-independent** by
construction, so it isolates the entry: no exit rule can flatter or
spoil it. `edge = P(win-first) - P(loss-first)`, in percentage points.

Rather than resampling whole backtests, the first-touch outcome is
computed **once for every eligible (bar, direction) pair** in the window
— the complete signal population. Every null draw is then a lookup, so
the nulls are exact rather than approximated, and the population mean is
available directly as the "what a coin flip gets you here" reference.

Two nulls, answering different questions
----------------------------------------
* **Null A — same days, same directions, random time.** Holds constant
  which sessions were traded, how many times, and which way. Only the
  *moment* of entry is randomised. Answers: does the break LEVEL carry
  timing information, beyond "be in this market on this day"?
* **Null B — random days and times, same direction mix.** Answers the
  broader question: do these entries carry any information at all?

A one-sided p-value is reported as the share of draws whose edge is at
least the strategy's. This tests the ENTRY only; it says nothing about
whether the resulting P&L is tradeable, which is what the full backtest
is for.

Entries are taken from the strategy's raw signals (institutional filters
off) so the test runs on the full 210-entry population rather than the
43 that survive production filtering — a filter question is a separate
experiment, and this one needs the statistical power.
"""
from __future__ import annotations

import argparse
import logging
import sys
from dataclasses import dataclass
from typing import Optional

import numpy as np
import pandas as pd

from shared.risk import resolve_initial_stop
from trading_bot.strategies.premium_selection.options_selector import (
    calculate_option_price,
    select_option,
)

from .premium_simulator import DEFAULT_IV
from .research_config import load_window

logging.disable(logging.CRITICAL)

#: Entries are only eligible where the live engine could actually take
#: one: after the opening range has formed and before the EOD entry
#: cutoff. Using a wider pool would compare the strategy against entries
#: production would have refused.
EOD_CUTOFF = pd.Timestamp("15:15:00").time()


@dataclass(frozen=True)
class Outcome:
    first_touch: str      # "win_first" | "loss_first" | "none"
    mfe_r: float
    mae_r: float


def _first_touch(day_bars: pd.DataFrame, ts: pd.Timestamp, direction: str,
                 vol: float = DEFAULT_IV) -> Optional[Outcome]:
    """First touch of ±1R for an entry at `ts`, on the contract the real
    `select_option` would have picked, priced bar by bar."""
    if ts not in day_bars.index:
        return None
    spot = float(day_bars.at[ts, "close"])
    contract = select_option("NIFTY", spot, direction, itm_strikes=1, from_date=ts.date())
    if contract is None:
        return None

    entry_dte = max((contract.expiry - ts.date()).days, 0)
    entry_premium = calculate_option_price(
        spot, float(contract.strike), entry_dte, vol, contract.option_type
    )
    sl = resolve_initial_stop(entry_premium, {})
    risk = entry_premium - sl.sl_price
    if risk <= 0:
        return None

    forward = day_bars.loc[day_bars.index > ts]
    if forward.empty:
        return None
    prem = np.array([
        calculate_option_price(float(c), float(contract.strike),
                               max((contract.expiry - t.date()).days, 0),
                               vol, contract.option_type)
        for t, c in zip(forward.index, forward["close"])
    ])

    up, dn = entry_premium + risk, entry_premium - risk
    hit_up = np.flatnonzero(prem >= up)
    hit_dn = np.flatnonzero(prem <= dn)
    i_up = hit_up[0] if hit_up.size else None
    i_dn = hit_dn[0] if hit_dn.size else None
    if i_up is None and i_dn is None:
        touch = "none"
    elif i_dn is None or (i_up is not None and i_up < i_dn):
        touch = "win_first"
    else:
        touch = "loss_first"
    return Outcome(touch, (prem.max() - entry_premium) / risk,
                   (prem.min() - entry_premium) / risk)


def _edge(outcomes) -> float:
    if not len(outcomes):
        return float("nan")
    arr = np.asarray(outcomes)
    return (np.mean(arr == "win_first") - np.mean(arr == "loss_first")) * 100.0


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--strategy", default="structure_break")
    ap.add_argument("--window", choices=["dev", "oos"], default="dev")
    ap.add_argument("--draws", type=int, default=2000)
    ap.add_argument("--seed", type=int, default=20260809)
    ap.add_argument("--opening-range-bars", type=int, default=6)
    args = ap.parse_args()

    df = load_window(args.window)
    rng = np.random.default_rng(args.seed)

    from trading_bot.strategies.registry import registry
    raw = registry._strategies[args.strategy](df)
    raw = raw[0] if isinstance(raw, tuple) else raw

    real = [(ts, "CE" if v == 1 else "PE") for ts, v in raw.items() if v != 0]
    if not real:
        print("no signals — nothing to test", file=sys.stderr)
        return

    # ── the eligible population ────────────────────────────────────────
    pool: dict = {}
    by_day: dict = {}
    for day, bars in df.groupby(df.index.normalize()):
        if len(bars) < args.opening_range_bars + 2:
            continue
        eligible = [t for t in bars.index[args.opening_range_bars:] if t.time() < EOD_CUTOFF]
        if eligible:
            by_day[day] = (bars, eligible)

    total = sum(len(e) for _b, e in by_day.values()) * 2
    print(f"pricing the eligible population: {total:,} (bar, direction) pairs...",
          file=sys.stderr)
    done = 0
    for day, (bars, eligible) in by_day.items():
        for ts in eligible:
            for d in ("CE", "PE"):
                o = _first_touch(bars, ts, d)
                if o is not None:
                    pool[(ts, d)] = o.first_touch
                done += 1
        if done % 2000 < 2:
            print(f"  {done:,}/{total:,}", file=sys.stderr)

    real_out = [pool[k] for k in real if k in pool]
    real_edge = _edge(real_out)
    pop_edge = _edge(list(pool.values()))

    print(f"\n# Entry-information test — `{args.strategy}` ({args.window.upper()})\n")
    print(f"Eligible population priced: **{len(pool):,}** (bar, direction) pairs  ")
    print(f"Strategy entries measured : **{len(real_out)}** of {len(real)}\n")
    print("| Set | n | win-first | loss-first | edge (pp) |")
    print("|---|---|---|---|---|")
    for name, outs in (("**strategy entries**", real_out),
                       ("whole eligible population", list(pool.values()))):
        a = np.asarray(outs)
        print(f"| {name} | {len(a)} | {np.mean(a=='win_first')*100:.1f}% | "
              f"{np.mean(a=='loss_first')*100:.1f}% | **{_edge(outs):+.1f}** |")

    # ── Null A: same day, same direction, random time ──────────────────
    real_by_day: dict = {}
    for ts, d in real:
        real_by_day.setdefault(ts.normalize(), []).append(d)

    nullA = []
    for _ in range(args.draws):
        outs = []
        for day, dirs in real_by_day.items():
            if day not in by_day:
                continue
            _bars, eligible = by_day[day]
            for d in dirs:
                ts = eligible[rng.integers(len(eligible))]
                if (ts, d) in pool:
                    outs.append(pool[(ts, d)])
        nullA.append(_edge(outs))

    # ── Null B: random day and time, same direction mix ────────────────
    keys = list(pool.keys())
    dirs_real = [d for _t, d in real]
    by_dir = {d: [k for k in keys if k[1] == d] for d in ("CE", "PE")}
    nullB = []
    for _ in range(args.draws):
        outs = []
        for d in dirs_real:
            cand = by_dir[d]
            outs.append(pool[cand[rng.integers(len(cand))]])
        nullB.append(_edge(outs))

    print()
    print("| Null | mean edge | 5th pct | 95th pct | P(null >= strategy) |")
    print("|---|---|---|---|---|")
    for name, null in (("A — same day/direction, random time", nullA),
                       ("B — random day and time", nullB)):
        a = np.asarray(null, dtype=float)
        a = a[~np.isnan(a)]
        p = float(np.mean(a >= real_edge))
        print(f"| {name} | {a.mean():+.1f} | {np.percentile(a,5):+.1f} | "
              f"{np.percentile(a,95):+.1f} | **{p:.3f}** |")

    print(f"\nStrategy edge: **{real_edge:+.1f}pp**, population baseline "
          f"**{pop_edge:+.1f}pp**, {args.draws:,} draws per null.")


if __name__ == "__main__":
    main()
