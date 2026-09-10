#!/usr/bin/env python3
"""Does the entry signal have directional edge?

The question the six paper sessions could not answer. 18 trades gave
MFE/MAE = 1.17 with a median of 1.03 -- indistinguishable from a coin flip,
but on far too small a sample to conclude anything.

This runs the same live strategy over years of 5-minute bars and asks it
again, on hundreds of entries.

Method, deliberately independent of any exit rule:

    For each entry the strategy generates, walk forward a fixed horizon and
    record how far the index travelled IN FAVOUR (MFE) and AGAINST (MAE)
    before that horizon expired.

If the signal has directional edge, MFE must systematically exceed MAE. That
is a property of the *entry* alone -- no stop, no target, no theta, nothing
that a parameter sweep could rescue. If MFE/MAE is ~1.0, changing the exit
rules changes how the strategy loses, not whether it does.

Horizons are expressed in bars so intraday holds of realistic length are
covered (the paper sessions' mean hold was ~1.8 hours = ~22 five-minute bars).

    python scripts/measure_signal_edge.py
    python scripts/measure_signal_edge.py --horizons 6,12,24,48
"""

from __future__ import annotations

import argparse
import statistics
import sys
from pathlib import Path
from typing import Dict, List

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

DATA = ROOT / "data"

#: 5-minute NIFTY files, oldest first. Overlaps are de-duplicated by timestamp.
SOURCES = [
    "NSE_NIFTY50-INDEX_5.csv",      # 2024
    "NIFTY_cache.csv",              # 2025-05 .. 2026-05
    "NSE_NIFTY50-INDEX_5Min.csv",   # 2026-05 .. present
]

DEFAULT_HORIZONS = [6, 12, 24, 48]   # 30m, 1h, 2h, 4h on 5-minute bars


def load_bars() -> pd.DataFrame:
    frames = []
    for name in SOURCES:
        path = DATA / name
        if not path.exists():
            continue
        df = pd.read_csv(path)
        cols = {c.lower(): c for c in df.columns}
        tcol = next((cols[k] for k in ("datetime", "date", "timestamp", "time")
                     if k in cols), df.columns[0])
        df["_ts"] = pd.to_datetime(df[tcol], errors="coerce", format="mixed")
        ren = {}
        for want in ("open", "high", "low", "close", "volume"):
            if want in cols:
                ren[cols[want]] = want
        df = df.rename(columns=ren)
        keep = ["_ts"] + [c for c in ("open", "high", "low", "close", "volume") if c in df.columns]
        frames.append(df[keep])

    if not frames:
        raise SystemExit(f"No 5-minute NIFTY data found in {DATA}")

    bars = pd.concat(frames, ignore_index=True)
    bars = bars.dropna(subset=["_ts"]).drop_duplicates(subset=["_ts"])
    bars = bars.sort_values("_ts").set_index("_ts")
    for col in ("open", "high", "low", "close"):
        bars[col] = pd.to_numeric(bars[col], errors="coerce")
    if "volume" not in bars.columns:
        bars["volume"] = 0.0
    bars["volume"] = pd.to_numeric(bars["volume"], errors="coerce").fillna(0.0)
    return bars.dropna(subset=["close"])


def signals_for(bars: pd.DataFrame, strategy: str) -> np.ndarray:
    """Signal series for `strategy`, via the same registry the engine uses."""
    import trading_bot.main  # noqa: F401  (side-effect: registers strategies)
    from trading_bot.strategies.registry import registry

    out = registry.run_strategy(strategy, bars)
    # Some strategies return (signals, rejection_logs).
    if isinstance(out, tuple):
        out = out[0]
    return np.asarray(pd.Series(out).fillna(0), dtype=int)


def excursions(bars: pd.DataFrame, horizons: List[int],
               strategy: str = "ema9_rsi_momentum") -> Dict[int, List[dict]]:
    """Run `strategy` and measure MFE/MAE at each horizon."""
    sig = signals_for(bars, strategy)
    highs = bars["high"].to_numpy()
    lows = bars["low"].to_numpy()
    closes = bars["close"].to_numpy()
    dates = bars.index.normalize().to_numpy()

    out: Dict[int, List[dict]] = {h: [] for h in horizons}
    n = len(bars)

    for i in range(n - 1):
        s = sig[i]
        if s == 0:
            continue
        # Enter on the NEXT bar's open-equivalent (its close is unknown at i).
        entry_idx = i + 1
        entry = closes[i]
        for h in horizons:
            end = min(entry_idx + h, n)
            if end <= entry_idx:
                continue
            # Never look past the end of the trading day.
            same_day = dates[entry_idx:end] == dates[entry_idx]
            hi = highs[entry_idx:end][same_day]
            lo = lows[entry_idx:end][same_day]
            if len(hi) == 0:
                continue
            if s > 0:                       # CE: favourable is up
                mfe, mae = hi.max() - entry, entry - lo.min()
            else:                           # PE: favourable is down
                mfe, mae = entry - lo.min(), hi.max() - entry
            out[h].append({"mfe": float(mfe), "mae": float(mae), "dir": int(s)})
    return out


def report(results: Dict[int, List[dict]]) -> None:
    print("=" * 78)
    print("SIGNAL EDGE  --  does the entry, on its own, point the right way?")
    print("=" * 78)
    print(f"{'horizon':>9s} {'entries':>8s} {'MFE>MAE':>9s} {'totMFE/totMAE':>14s} "
          f"{'median':>8s} {'mean MFE':>9s} {'mean MAE':>9s}")
    print("-" * 78)

    for h in sorted(results):
        rows = results[h]
        if not rows:
            continue
        n = len(rows)
        wins = sum(1 for r in rows if r["mfe"] > r["mae"])
        tot_mfe = sum(r["mfe"] for r in rows)
        tot_mae = sum(r["mae"] for r in rows)
        ratios = [r["mfe"] / r["mae"] for r in rows if r["mae"] > 0]
        med = statistics.median(ratios) if ratios else float("nan")
        print(f"{h:6d} bar {n:8d} {wins/n*100:8.1f}% {tot_mfe/max(tot_mae,1e-9):14.3f} "
              f"{med:8.3f} {tot_mfe/n:9.1f} {tot_mae/n:9.1f}")

    print("-" * 78)
    print("  MFE>MAE ~50% and a ratio ~1.00 mean the entry carries no")
    print("  directional information. Tuning stops or targets on such a signal")
    print("  changes how it loses, not whether it does.")
    print()

    # Direction split -- a signal can be right one way and wrong the other.
    h = max(results)
    rows = results[h]
    for label, want in (("CE (bullish)", 1), ("PE (bearish)", -1)):
        sub = [r for r in rows if r["dir"] == want]
        if not sub:
            continue
        tm = sum(r["mfe"] for r in sub)
        ta = sum(r["mae"] for r in sub)
        w = sum(1 for r in sub if r["mfe"] > r["mae"])
        print(f"  {label:14s} n={len(sub):5d}  MFE>MAE {w/len(sub)*100:5.1f}%  "
              f"ratio {tm/max(ta,1e-9):.3f}   (at {h}-bar horizon)")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--horizons", default=",".join(str(h) for h in DEFAULT_HORIZONS))
    ap.add_argument("--strategy", default="ema9_rsi_momentum")
    ap.add_argument("--all", action="store_true",
                    help="sweep every registered strategy and rank them")
    args = ap.parse_args()
    horizons = [int(x) for x in args.horizons.split(",") if x.strip()]

    bars = load_bars()
    print(f"Loaded {len(bars):,} five-minute bars: "
          f"{bars.index.min()} .. {bars.index.max()}")
    print(f"Trading days: {bars.index.normalize().nunique():,}")
    print()

    if not args.all:
        report(excursions(bars, horizons, args.strategy))
        return 0

    import trading_bot.main  # noqa: F401
    from trading_bot.strategies.registry import registry

    horizon = max(horizons)
    rows = []
    for name in sorted(registry.registered_strategies):
        try:
            res = excursions(bars, [horizon], name)[horizon]
        except Exception as exc:
            rows.append((name, None, None, None, f"{type(exc).__name__}: {str(exc)[:40]}"))
            continue
        if not res:
            rows.append((name, 0, None, None, "no entries"))
            continue
        n = len(res)
        tm = sum(r["mfe"] for r in res)
        ta = sum(r["mae"] for r in res)
        w = sum(1 for r in res if r["mfe"] > r["mae"]) / n * 100
        rows.append((name, n, w, tm / max(ta, 1e-9), ""))

    print("=" * 78)
    print(f"ALL STRATEGIES  --  MFE/MAE at a {horizon}-bar horizon")
    print("=" * 78)
    print(f"{'strategy':26s} {'entries':>8s} {'MFE>MAE':>9s} {'ratio':>8s}   note")
    print("-" * 78)
    scored = [r for r in rows if r[3] is not None]
    for name, n, w, ratio, note in sorted(
            rows, key=lambda r: (r[3] is None, -(r[3] or 0))):
        if ratio is None:
            print(f"{name:26s} {str(n or '-'):>8s} {'-':>9s} {'-':>8s}   {note}")
        else:
            flag = "  <-- edge?" if ratio > 1.10 and n >= 100 else ""
            print(f"{name:26s} {n:8d} {w:8.1f}% {ratio:8.3f}{flag}")
    print("-" * 78)
    print("  ratio ~1.00 = no directional information in the entry.")
    print("  Flagged only when ratio > 1.10 on at least 100 entries -- below")
    print("  that, the sample cannot separate edge from luck.")
    if scored and not any(r[3] > 1.10 and r[1] >= 100 for r in scored):
        print()
        print("  No strategy shows edge above the noise floor on this data.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
