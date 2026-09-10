#!/usr/bin/env python3
"""Analyse ENTRY behaviour across paper sessions.

Deliberately separated from P&L. Only one recorded session (Day 6,
2026-09-10) was filled at real quoted prices -- see
``scripts/audit_session_fills.py`` -- so any conclusion that depends on
premium, delta, theta or P&L can only be drawn from that one session.

What survives the fill bug in *every* session, because none of it came from
the option chain:

    entry_time / exit_time     the observer's own clock
    contract / strike / type   chosen from the strike ladder
    direction                  the strategy's own decision
    entry_spot                 real index candles via /api/history
    rsi / confidence / quality the strategy's own state
    exit_reason                which rule fired

So questions about *when and what the strategy chose to trade* can be asked
of all six sessions. That is what this script does, and it labels which
conclusions rest on which evidence.

    python scripts/analyze_entry_behaviour.py
"""

from __future__ import annotations

import json
import math
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parent.parent
SESSION_DIR = ROOT / "paper_obs_logs"

#: Re-entering the same contract and direction within this window of being
#: stopped out is the strategy re-taking a thesis the market just rejected.
RE_ENTRY_WINDOW_MIN = 60


def _mins(hhmmss: str) -> float:
    """'HH:MM:SS' -> minutes since midnight. Returns nan if unparseable."""
    try:
        t = datetime.strptime(hhmmss.strip().split(" ")[-1], "%H:%M:%S")
        return t.hour * 60 + t.minute + t.second / 60.0
    except Exception:
        return math.nan


def load_sessions() -> List[Dict[str, Any]]:
    out = []
    for path in sorted(SESSION_DIR.glob("session_*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        data["_name"] = path.stem.replace("session_", "")
        out.append(data)
    return out


# ---------------------------------------------------------------------------
# Hypothesis 1: does the strategy re-take a thesis that was just stopped out?
# ---------------------------------------------------------------------------

def find_re_entries(session: Dict[str, Any]) -> List[Dict[str, Any]]:
    trades = session.get("trades") or []
    hits = []
    for i, first in enumerate(trades):
        if "STOP" not in str(first.get("exit_reason", "")).upper():
            continue
        exit_m = _mins(first.get("exit_time", ""))
        if math.isnan(exit_m):
            continue
        for second in trades[i + 1:]:
            if second.get("contract") != first.get("contract"):
                continue
            if second.get("direction") != first.get("direction"):
                continue
            entry_m = _mins(second.get("entry_time", ""))
            if math.isnan(entry_m):
                continue
            gap = entry_m - exit_m
            if 0 <= gap <= RE_ENTRY_WINDOW_MIN:
                hits.append({
                    "contract": first.get("contract"),
                    "stopped_at": first.get("exit_time"),
                    "re_entered_at": second.get("entry_time"),
                    "gap_min": round(gap, 1),
                    "second_outcome": second.get("outcome"),
                    "second_reason": second.get("exit_reason"),
                })
                break
    return hits


# ---------------------------------------------------------------------------
# Hypothesis 2: does it flip direction inside one session (whipsaw)?
# ---------------------------------------------------------------------------

def find_direction_flips(session: Dict[str, Any]) -> List[Dict[str, Any]]:
    by_symbol: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for t in session.get("trades") or []:
        by_symbol[t.get("symbol", "?")].append(t)

    flips = []
    for symbol, trades in by_symbol.items():
        ordered = sorted(trades, key=lambda t: _mins(t.get("entry_time", "")) or 0)
        for a, b in zip(ordered, ordered[1:]):
            if a.get("opt_type") and b.get("opt_type") and a["opt_type"] != b["opt_type"]:
                flips.append({
                    "symbol": symbol,
                    "from": f"{a['opt_type']} @ {a.get('entry_time')}",
                    "to": f"{b['opt_type']} @ {b.get('entry_time')}",
                    "first_outcome": a.get("outcome"),
                    "second_outcome": b.get("outcome"),
                })
    return flips


# ---------------------------------------------------------------------------
# Hypothesis 3: was the day's realised range big enough to pay for the trade?
# ---------------------------------------------------------------------------

def range_context(session: Dict[str, Any]) -> Dict[str, Any]:
    """Index-point spread of entry spots -- a floor on the day's real range.

    Uses `entry_spot`, which is real in every session (it comes from index
    candles, not the option chain). It understates the true day range, so
    treating it as a floor is the conservative reading.
    """
    spots = [float(t["entry_spot"]) for t in session.get("trades") or []
             if t.get("entry_spot")]
    by_symbol: Dict[str, List[float]] = defaultdict(list)
    for t in session.get("trades") or []:
        if t.get("entry_spot"):
            by_symbol[t.get("symbol", "?")].append(float(t["entry_spot"]))
    return {
        "n_spots": len(spots),
        "per_symbol": {s: (min(v), max(v), max(v) - min(v))
                       for s, v in by_symbol.items() if len(v) > 1},
    }


def exit_reason_mix(sessions: List[Dict[str, Any]]) -> Dict[str, int]:
    counts: Dict[str, int] = defaultdict(int)
    for s in sessions:
        for t in s.get("trades") or []:
            reason = str(t.get("exit_reason", "?")).upper()
            if "STOP" in reason:
                key = "STOP LOSS"
            elif "TARGET" in reason:
                key = "TARGET"
            elif "EOD" in reason or "SQUARE" in reason:
                key = "EOD SQUARE-OFF"
            else:
                key = reason[:28] or "?"
            counts[key] += 1
    return dict(counts)


def main() -> int:
    sessions = load_sessions()
    if not sessions:
        print(f"No sessions in {SESSION_DIR}")
        return 1

    graded = [s for s in sessions if s.get("trades")]
    total_trades = sum(len(s["trades"]) for s in graded)

    print("=" * 74)
    print("ENTRY BEHAVIOUR ACROSS PAPER SESSIONS")
    print("=" * 74)
    print(f"  sessions with trades : {len(graded)} of {len(sessions)}")
    print(f"  trades analysed      : {total_trades}")
    print()
    print("  Note: this reads only decision-level fields (times, contracts,")
    print("  direction, entry_spot, rsi, confidence, exit_reason). None of")
    print("  them came from the option chain, so all six sessions are valid")
    print("  here -- unlike P&L, which is real only for Day 6.")

    # -- exit reasons ----------------------------------------------------
    print("\n" + "-" * 74)
    print("HOW TRADES ENDED (all sessions)")
    print("-" * 74)
    mix = exit_reason_mix(graded)
    for reason, n in sorted(mix.items(), key=lambda kv: -kv[1]):
        pct = n / total_trades * 100 if total_trades else 0
        print(f"  {reason:30s} {n:3d}  ({pct:5.1f}%)")

    # -- re-entries ------------------------------------------------------
    print("\n" + "-" * 74)
    print(f"RE-ENTRY INTO A JUST-STOPPED THESIS (within {RE_ENTRY_WINDOW_MIN} min)")
    print("-" * 74)
    total_re = 0
    for s in graded:
        hits = find_re_entries(s)
        total_re += len(hits)
        for h in hits:
            print(f"  {s['_name'][:26]:28s} {h['contract'][:22]:24s}")
            print(f"      stopped {h['stopped_at']}  ->  re-entered {h['re_entered_at']}"
                  f"  (+{h['gap_min']} min)  second outcome: {h['second_outcome']}")
    if not total_re:
        print("  none found")
    else:
        print(f"\n  total: {total_re}")

    # -- direction flips -------------------------------------------------
    print("\n" + "-" * 74)
    print("DIRECTION FLIPS WITHIN A SESSION (CE <-> PE on the same symbol)")
    print("-" * 74)
    total_flips = 0
    for s in graded:
        flips = find_direction_flips(s)
        total_flips += len(flips)
        for f in flips:
            print(f"  {s['_name'][:26]:28s} {f['symbol']:10s} "
                  f"{f['from']} ({f['first_outcome']})  ->  {f['to']} ({f['second_outcome']})")
    if not total_flips:
        print("  none found")
    else:
        print(f"\n  total: {total_flips}")

    # -- spot spread -----------------------------------------------------
    print("\n" + "-" * 74)
    print("INDEX MOVEMENT BETWEEN ENTRIES (floor on the day's real range)")
    print("-" * 74)
    for s in graded:
        ctx = range_context(s)
        if not ctx["per_symbol"]:
            continue
        parts = [f"{sym} {hi-lo:.0f} pts" for sym, (lo, hi, _) in
                 ((k, v) for k, v in ctx["per_symbol"].items())]
        print(f"  {s['_name'][:26]:28s} " + "   ".join(parts))

    print("\n" + "=" * 74)
    print("Conclusions needing REAL fills (P&L, win rate, R:R) can only come")
    print("from sessions marked USABLE by scripts/audit_session_fills.py.")
    print("=" * 74)
    return 0


if __name__ == "__main__":
    sys.exit(main())
