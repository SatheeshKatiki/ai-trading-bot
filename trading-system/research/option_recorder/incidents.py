"""Structured incident log (Phase 15 sec11). RESEARCH ONLY.

    python -m research.option_recorder.incidents log \\
        --session 2026-09-28 --instrument NIFTY --type API_OUTAGE \\
        --detected 11:20 --last-valid 11:15 \\
        --cause "api_bridge restarted" --action "recorder restarted 11:24" \\
        --usable INCOMPLETE

    python -m research.option_recorder.incidents list

Why this is a tool and not a markdown file
------------------------------------------
Phase 14 left the incident log as a template in the runbook. A template is
filled in when someone remembers to, and the sessions where something went
wrong are exactly the sessions where the operator is busy dealing with it.

An incident log that is missing its worst entries is worse than none: the
20-session audit would read as clean. So the record is append-only, its
required fields are enforced at write time, and the audit reads it directly
rather than trusting a human to have transcribed it.

Nothing here edits or deletes an entry. A mistaken entry is corrected by
appending a correction that references it, the same way the data layers work.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from research.option_recorder.schema import (  # noqa: E402
    RECORDER_VERSION, record_checksum)
from research.option_recorder.store import ResearchStore  # noqa: E402

IST = dt.timezone(dt.timedelta(hours=5, minutes=30))

#: The failure kinds Phase 15 sec11 enumerates, plus the planned drill.
INCIDENT_TYPES = (
    "TOKEN_UNAVAILABLE",      # no authenticated Fyers session
    "SYNTHETIC_CHAIN",        # model chain served instead of broker data
    "API_OUTAGE",             # bridge or broker unreachable
    "RECORDER_CRASH",
    "STORAGE_FAILURE",
    "TIMEZONE_MISMATCH",
    "DUPLICATE_CORRUPTION",
    "FUTURE_TIMESTAMP",
    "MALFORMED_CHAIN",
    "NOT_COLLECTED",          # pre-flight said NO-GO; no session attempted
    "RESTART_DRILL",          # planned, per sec12
    "OTHER",
)

#: How the session ended up classified. Mirrors SessionStatus plus the case
#: where no session existed at all.
OUTCOMES = ("COMPLETE", "INCOMPLETE", "UNUSABLE", "NOT_COLLECTED")


def _path(store: ResearchStore) -> Path:
    store.root.mkdir(parents=True, exist_ok=True)
    return store.root / "incidents.jsonl"


def log(store: ResearchStore, *, session_date: str, instrument: str,
        incident_type: str, cause: str, action: str, outcome: str,
        detected_at: str = "", last_valid_snapshot: str = "",
        affected_data: str = "", phase: str = "15",
        data_modified: bool = False) -> Dict[str, Any]:
    """Append one incident. Every sec11 field is required or defaulted."""
    if incident_type not in INCIDENT_TYPES:
        raise ValueError(f"unknown incident type {incident_type!r}; "
                         f"expected one of {INCIDENT_TYPES}")
    if outcome not in OUTCOMES:
        raise ValueError(f"unknown outcome {outcome!r}; expected one of {OUTCOMES}")
    if data_modified:
        # sec11/sec13: evidence of a failure is never deleted, and RAW is
        # never rewritten. Recording that a file WAS altered is allowed --
        # doing it silently is what this forbids.
        if not cause or not action:
            raise ValueError("an incident that modified data must state both "
                             "a cause and the action taken")

    entry = {
        "logged_at": dt.datetime.now(IST).isoformat(timespec="seconds"),
        "phase": str(phase),
        "session_date": session_date,
        "instrument": instrument,
        "incident_type": incident_type,
        "detected_at": detected_at,
        "last_valid_snapshot": last_valid_snapshot,
        "suspected_cause": cause,
        "affected_data": affected_data,
        "recovery_action": action,
        "outcome": outcome,
        "data_modified": bool(data_modified),
        "recorder_version": RECORDER_VERSION,
    }
    entry["_checksum"] = record_checksum(entry)

    path = _path(store)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, separators=(",", ":")) + "\n")
        fh.flush()
        import os
        os.fsync(fh.fileno())
    return entry


def read(store: ResearchStore, session_date: Optional[str] = None,
         instrument: Optional[str] = None) -> List[Dict[str, Any]]:
    path = _path(store)
    if not path.exists():
        return []
    out = []
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if session_date and rec.get("session_date") != session_date:
                continue
            if instrument and rec.get("instrument") != instrument:
                continue
            out.append(rec)
    return out


def summary(store: ResearchStore) -> Dict[str, Any]:
    from collections import Counter
    rows = read(store)
    return {
        "total": len(rows),
        "by_type": dict(Counter(r.get("incident_type") for r in rows)),
        "by_outcome": dict(Counter(r.get("outcome") for r in rows)),
        "sessions_not_collected": sorted(
            {r["session_date"] for r in rows
             if r.get("outcome") == "NOT_COLLECTED"}),
        "data_modified_events": [r for r in rows if r.get("data_modified")],
        "restart_drills": [r for r in rows
                           if r.get("incident_type") == "RESTART_DRILL"],
    }


def render(rows: List[Dict[str, Any]]) -> str:
    if not rows:
        return "no incidents recorded"
    out = [f"{'date':<12}{'instrument':<11}{'type':<22}{'outcome':<14}cause"]
    out.append("-" * 88)
    for r in rows:
        out.append(f"{r.get('session_date',''):<12}"
                   f"{r.get('instrument',''):<11}"
                   f"{r.get('incident_type',''):<22}"
                   f"{r.get('outcome',''):<14}"
                   f"{r.get('suspected_cause','')}")
        if r.get("data_modified"):
            out.append(f"{'':<12}** DATA MODIFIED: {r.get('recovery_action')}")
    return "\n".join(out)


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", default=None)
    sub = ap.add_subparsers(dest="cmd", required=True)

    lg = sub.add_parser("log", help="append an incident")
    lg.add_argument("--session", required=True)
    lg.add_argument("--instrument", default="ALL")
    lg.add_argument("--type", dest="itype", required=True, choices=INCIDENT_TYPES)
    lg.add_argument("--detected", default="")
    lg.add_argument("--last-valid", default="")
    lg.add_argument("--cause", required=True)
    lg.add_argument("--action", required=True)
    lg.add_argument("--affected", default="")
    lg.add_argument("--usable", dest="outcome", required=True, choices=OUTCOMES)
    lg.add_argument("--data-modified", action="store_true")

    ls = sub.add_parser("list", help="show incidents")
    ls.add_argument("--session", default=None)
    ls.add_argument("--instrument", default=None)

    sub.add_parser("summary", help="counts by type and outcome")

    args = ap.parse_args(argv)
    store = ResearchStore(Path(args.root) if args.root else None)

    if args.cmd == "log":
        e = log(store, session_date=args.session, instrument=args.instrument,
                incident_type=args.itype, cause=args.cause, action=args.action,
                outcome=args.outcome, detected_at=args.detected,
                last_valid_snapshot=args.last_valid,
                affected_data=args.affected, data_modified=args.data_modified)
        print("logged:", e["incident_type"], e["session_date"], e["outcome"])
    elif args.cmd == "list":
        print(render(read(store, args.session, args.instrument)))
    else:
        print(json.dumps(summary(store), indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
