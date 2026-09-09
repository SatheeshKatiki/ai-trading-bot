#!/usr/bin/env python3
"""Classify the price provenance of recorded paper trades.

Answers one question: **was this trade filled at a price the market actually
quoted?** Until 2026-09-09 the answer was always no, and nothing in the
session record said so.

Three defects made recorded fills fictional, in sequence:

1. The option chain was a Black-Scholes model with a ``deterministic_random()``
   implied vol, so premiums were theoretical.
2. When the chain moved to the broker's real ``ce``/``pe`` shape,
   ``select_best_option()`` was still reading ``call``/``put`` -- so
   ``opt_details`` was ``{}`` and **every** entry filled at the hardcoded
   ``100.0`` default, with delta pinned to +/-0.50 and theta to -10.0.
3. Even once entries were real, open positions were still marked by
   extrapolating from the entry price rather than reading the contract's own
   bid.

Each left a fingerprint in the saved session JSON, which is what this script
reads. Run it before treating any session as evidence:

    python scripts/audit_session_fills.py                  # every session
    python scripts/audit_session_fills.py <session.json>   # just one
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parent.parent
SESSION_DIR = ROOT / "paper_obs_logs"

#: The literal that `opt_details.get("ltp", 100.0)` returned on every trade
#: once the chain keys stopped matching.
HARDCODED_PREMIUM = 100.0

#: `opt_details.get("delta", 0.50 if BUY else -0.50)`. A genuine ATM delta is
#: 0.5091, 0.5093, 0.4907... -- exactly 0.5000 essentially never occurs in a
#: real quote, so exact equality is a reliable fingerprint of the fallback.
FALLBACK_DELTA = 0.50

REAL = "REAL"
MODEL = "MODEL"
FABRICATED = "FABRICATED"

_VERDICT_NOTE = {
    REAL: "filled at a quoted price",
    MODEL: "theoretical or extrapolated price",
    FABRICATED: "hardcoded default -- not a price at all",
}


def classify_trade(trade: Dict[str, Any]) -> tuple[str, List[str]]:
    """Return (verdict, reasons) for one recorded trade."""
    reasons: List[str] = []

    entry = trade.get("entry_premium")
    delta = trade.get("opt_delta")
    ask = trade.get("entry_ask")
    bid = trade.get("entry_bid")
    mark_source = trade.get("mark_source")

    # --- fabricated: the hardcoded fallbacks -----------------------------
    if entry == HARDCODED_PREMIUM and not ask:
        reasons.append(
            f"entry_premium is exactly {HARDCODED_PREMIUM} with no quote recorded "
            "-- the select_best_option() default, not a market price"
        )
    if delta is not None and abs(float(delta)) == FALLBACK_DELTA:
        reasons.append(
            f"opt_delta is exactly {delta} -- the constant fallback; a real ATM "
            "delta is 0.5091-ish, never exactly 0.5000"
        )
    if reasons:
        return FABRICATED, reasons

    # --- model: a plausible price, but not one anyone quoted -------------
    if not ask and not bid:
        reasons.append(
            "no bid/ask recorded -- entry came from the Black-Scholes model "
            "chain, or predates quote capture"
        )
    elif ask and entry is not None and float(entry) < float(ask):
        reasons.append(
            f"entry {entry} is below the ask {ask} -- filled at the mid or "
            "better, which a buyer does not get"
        )
    if mark_source == "model":
        reasons.append("exit was extrapolated from entry, not read from the chain")
    elif mark_source is None:
        reasons.append("no mark_source -- exit pricing provenance unknown")

    if reasons:
        return MODEL, reasons

    return REAL, ["entry at the ask, exit marked from the broker chain"]


def audit_session(path: Path) -> Dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"path": path, "error": str(exc)}

    trades = data.get("trades") or []
    results = [(t, *classify_trade(t)) for t in trades]
    counts = {REAL: 0, MODEL: 0, FABRICATED: 0}
    for _, verdict, _ in results:
        counts[verdict] += 1

    if not trades:
        verdict = "NO TRADES"
    elif counts[FABRICATED]:
        verdict = "UNUSABLE"
    elif counts[MODEL]:
        verdict = "NOT EVIDENCE"
    else:
        verdict = "USABLE"

    return {
        "path": path,
        "date": data.get("date", path.stem),
        "strategy": data.get("strategy_name") or data.get("strategy") or "?",
        "trades": trades,
        "results": results,
        "counts": counts,
        "verdict": verdict,
        "net_pnl": round(sum(float(t.get("net_pnl") or 0) for t in trades), 2),
    }


def _print_session(report: Dict[str, Any], verbose: bool) -> None:
    if "error" in report:
        print(f"  !! {report['path'].name}: {report['error']}")
        return

    c = report["counts"]
    print(f"\n{report['date']}   [{report['verdict']}]")
    print(f"  strategy {report['strategy']}   trades {len(report['trades'])}   "
          f"net P&L Rs.{report['net_pnl']:+,.2f}")
    if report["trades"]:
        print(f"  real {c[REAL]}   model {c[MODEL]}   fabricated {c[FABRICATED]}")

    for trade, verdict, reasons in report["results"]:
        print(f"    [{verdict:10s}] {trade.get('contract','?'):28s} "
              f"entry {trade.get('entry_premium')}  pnl {trade.get('net_pnl')}")
        if verbose or verdict != REAL:
            for r in reasons:
                print(f"                 - {r}")


def main(argv: List[str]) -> int:
    args = [a for a in argv if not a.startswith("-")]
    verbose = "-v" in argv or "--verbose" in argv

    if args:
        paths = [Path(a) for a in args]
    else:
        paths = sorted(SESSION_DIR.glob("session_*.json"))

    if not paths:
        print(f"No session files found in {SESSION_DIR}")
        return 1

    print("=" * 74)
    print("PAPER SESSION FILL AUDIT -- was each trade filled at a quoted price?")
    print("=" * 74)

    reports = [audit_session(p) for p in paths]
    for report in reports:
        _print_session(report, verbose)

    total = {REAL: 0, MODEL: 0, FABRICATED: 0}
    for r in reports:
        if "counts" in r:
            for k in total:
                total[k] += r["counts"][k]
    graded = sum(total.values())

    print("\n" + "=" * 74)
    print("SUMMARY")
    print("=" * 74)
    for key in (REAL, MODEL, FABRICATED):
        pct = (total[key] / graded * 100) if graded else 0.0
        print(f"  {key:11s} {total[key]:4d}  ({pct:5.1f}%)   {_VERDICT_NOTE[key]}")

    usable = [r for r in reports if r.get("verdict") == "USABLE"]
    print(f"\n  Sessions usable as live-performance evidence: "
          f"{len(usable)} of {len(reports)}")
    if not usable:
        print("  -> No session yet contains a trade filled at a real quoted price.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
