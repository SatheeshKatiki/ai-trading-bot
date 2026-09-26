"""Offline end-to-end rehearsal of a full collection session (Phase 13 sec22).

    python -m research.option_recorder.selftest

RESEARCH ONLY. It touches no broker, no network and no production path: the
chain and history fetchers are replaced with generators, and everything is
written to a temporary directory that is deleted on exit.

Why this exists
---------------
The recorder only gets one chance at each trading day. A bug found on
session 40 costs 40 sessions. This replays a whole session -- 76 snapshots,
a restart in the middle, a broker outage, a thin chain, a day roll -- through
the real :func:`snapshot`, the real store and the real scorecard, and prints
what the daily report would say. Everything it exercises is the shipping code
path; only the two fetchers are substituted.

It is a rehearsal, not evidence. Nothing it writes is research data.
"""

from __future__ import annotations

import argparse
import datetime as dt
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Dict, List, Optional

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from research.option_recorder import collect as C  # noqa: E402
from research.option_recorder import qa  # noqa: E402
from research.option_recorder.store import ResearchStore  # noqa: E402

IST = C.IST


def synth_chain(spot: float, *, strikes: int = 21, step: float = 50.0,
                expiry: str = "2026-10-06", frozen: bool = False,
                synthetic: bool = False) -> Dict:
    """A structurally realistic chain. The premiums are obviously fake and
    are never stored anywhere a researcher could mistake them for data --
    this function is only importable from the self-test."""
    atm = round(spot / step) * step
    rows = []
    for k in range(-(strikes // 2), strikes // 2 + 1):
        K = atm + k * step
        ce = max(1.0, spot - K) + 40.0
        pe = max(1.0, K - spot) + 40.0
        jitter = 0.0 if frozen else float(np.random.default_rng(int(K)).normal(0, 2))
        rows.append({
            "strike": K,
            "ce": {"bid": round(ce + jitter, 2), "ask": round(ce + jitter + 0.8, 2),
                   "ltp": round(ce + jitter + 0.4, 2), "oi": 1000, "oichg": 10,
                   "volume": 500, "symbol": f"NSE:X{int(K)}CE"},
            "pe": {"bid": round(pe + jitter, 2), "ask": round(pe + jitter + 0.8, 2),
                   "ltp": round(pe + jitter + 0.4, 2), "oi": 900, "oichg": -5,
                   "volume": 400, "symbol": f"NSE:X{int(K)}PE"},
        })
    return {"underlying_price": spot, "expiry": expiry, "synthetic": synthetic,
            "priceSource": "selftest", "chain": rows}


def synth_history(days: int = 4, bars_per_day: int = 75,
                  start: float = 24000.0) -> pd.DataFrame:
    rng = np.random.default_rng(7)
    idx: List[pd.Timestamp] = []
    day = dt.date(2026, 9, 25)
    for d in range(days):
        while day.weekday() >= 5:
            day += dt.timedelta(days=1)
        base = pd.Timestamp(day.isoformat() + " 09:15")
        idx.extend(base + pd.Timedelta(minutes=5 * i) for i in range(bars_per_day))
        day += dt.timedelta(days=1)
    walk = start + np.cumsum(rng.normal(0, 10, len(idx)))
    return pd.DataFrame({"open": walk, "high": walk + 15, "low": walk - 15,
                         "close": walk, "volume": 1000},
                        index=pd.DatetimeIndex(idx))


def run(snapshots: int = 76, verbose: bool = True) -> Dict:
    root = Path(tempfile.mkdtemp(prefix="recorder_selftest_"))
    orig_chain, orig_hist, orig_now = C.fetch_chain, C.fetch_history, C._now

    # Drive the clock at the real 5-minute cadence. Without this the whole
    # rehearsal happens inside one second, every snapshot is the same instant,
    # and dedup correctly collapses the lot -- which tests nothing.
    clock = {"t": dt.datetime(2026, 9, 30, 9, 15, tzinfo=IST)}
    C._now = lambda: clock["t"]

    def tick(minutes: float = 5.0) -> None:
        clock["t"] = clock["t"] + dt.timedelta(minutes=minutes)
    checks: List[tuple] = []

    def check(name: str, ok: bool, detail: str = "") -> None:
        checks.append((name, bool(ok), detail))
        if verbose:
            print(f"  [{'PASS' if ok else 'FAIL'}] {name}"
                  + (f" -- {detail}" if detail else ""))

    try:
        store = ResearchStore(root / "research_data")
        hist = synth_history()
        # Only bars that have already closed, as a real endpoint would.
        C.fetch_history = (lambda inst, days=6, timeframe="5 Min":
                           hist[hist.index <= pd.Timestamp(
                               clock["t"].replace(tzinfo=None))])

        session = clock["t"].date().isoformat()
        state = C.InstrumentState("NIFTY", session)
        spot = 24000.0

        print(f"\n== rehearsing {snapshots} snapshots ==")
        outage_at, thin_at, frozen_from = 20, 30, 40
        for i in range(snapshots):
            tick()
            spot += float(np.random.default_rng(i).normal(0, 8))
            if i == outage_at:
                C.fetch_chain = lambda inst: None           # broker outage
            elif i == thin_at:
                C.fetch_chain = lambda inst: synth_chain(spot, strikes=3)
            elif i >= frozen_from:
                C.fetch_chain = lambda inst: synth_chain(spot, frozen=True)
            else:
                C.fetch_chain = lambda inst: synth_chain(spot)
            r = C.snapshot(store, "NIFTY", state=state)
            if i == outage_at:
                check("outage is survived and reported, not crashed",
                      (not r["ok"]) and r.get("error") == "chain unavailable")
            if i == thin_at:
                check("thin chain is recorded AND flagged",
                      r["ok"] and r["coverage_ok"] is False,
                      f"{(r.get('coverage') or {}).get('strikes')} strikes")

        # -- duplicate protection -------------------------------------
        C.fetch_chain = lambda inst: synth_chain(spot)
        before = len(list(store.read("normalized", "NIFTY", session, "quotes.jsonl")))
        tick()
        r1 = C.snapshot(store, "NIFTY", state=state)
        r2 = C.snapshot(store, "NIFTY", state=state)   # same instant, re-polled
        after = len(list(store.read("normalized", "NIFTY", session, "quotes.jsonl")))
        check("re-polling one instant stores it once",
              r2["written"] == 0 and r2["skipped"] > 0,
              f"second poll wrote {r2['written']}, skipped {r2['skipped']}")
        _ = (before, after, r1)

        # -- restart ---------------------------------------------------
        store2 = ResearchStore(store.root)
        fresh = C.InstrumentState("NIFTY", session)
        fresh.seen_keys = store2.load_keys("NIFTY", session)
        cp = store2.read_checkpoint("NIFTY", session)
        r3 = C.snapshot(store2, "NIFTY", state=fresh)
        check("a restarted process re-records nothing",
              r3["written"] == 0 and r3["skipped"] > 0,
              f"resumed with {len(fresh.seen_keys)} keys")
        check("checkpoint survives and carries progress",
              bool(cp) and cp.get("snapshots", 0) > 0,
              f"snapshots={None if not cp else cp.get('snapshots')}")

        # -- staleness -------------------------------------------------
        rows = list(store.read("normalized", "NIFTY", session, "quotes.jsonl"))
        stale = [r for r in rows if r.get("quality") == "STALE"]
        check("frozen quotes are eventually marked STALE", bool(stale),
              f"{len(stale)} stale rows")
        check("no row claims an exchange quote age",
              all(r.get("quote_age_seconds") is None for r in rows))

        # -- lineage ---------------------------------------------------
        check("every row carries recorder + normalization version",
              all(r.get("recorder_version") and r.get("normalization_version")
                  for r in rows))

        # -- day roll --------------------------------------------------
        rolled = state.roll_if_needed("2099-01-01")
        check("a new session resets all carried state",
              rolled and not state.seen_keys and not state.fingerprints)

        # -- integrity + scorecard -------------------------------------
        store.write_manifest("NIFTY", session)
        rep = qa.session_report(store, "NIFTY", session)
        check("stored data passes its own integrity check",
              rep["integrity"].get("ok"))
        check("no duplicates survive on disk", rep["duplicates"] == 0)
        check("report assigns an explicit status", bool(rep.get("status")),
              rep.get("status"))

        # -- tamper detection ------------------------------------------
        f = store.partition("normalized", "NIFTY", session) / "quotes.jsonl"
        with f.open("a", encoding="utf-8") as fh:
            fh.write('{"tampered":true}\n')
        check("editing a stored file is detected",
              not store.verify_partition("NIFTY", session).get("ok"))

        print("\n== daily report ==")
        for k in ("snapshots", "completeness_pct", "quotes", "valid_pct",
                  "stale", "synthetic", "duplicates", "distinct_strikes",
                  "score", "status"):
            print(f"  {k:<18} {rep[k]}")
        print("  scorecard:")
        for k, v in rep["scorecard"].items():
            print(f"    {k:<14} {v:.2f}")

        passed = sum(1 for _, ok, _ in checks if ok)
        print(f"\n== {passed}/{len(checks)} rehearsal checks passed ==")
        return {"checks": checks, "passed": passed, "total": len(checks),
                "report": rep, "ok": passed == len(checks)}
    finally:
        C.fetch_chain, C.fetch_history, C._now = orig_chain, orig_hist, orig_now
        shutil.rmtree(root, ignore_errors=True)


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--snapshots", type=int, default=76)
    args = ap.parse_args(argv)
    res = run(snapshots=args.snapshots)
    return 0 if res["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
