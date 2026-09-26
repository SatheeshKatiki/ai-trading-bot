"""End-of-day close-out for one session (Phase 15 sec9, sec15). RESEARCH ONLY.

    python -m research.option_recorder.eod --session 2026-09-28

Runs the whole documented end-of-day procedure in one step: manifest,
integrity verification, session report, incident review, classification, and
the COMPLETE-session counter.

Why one command
---------------
The procedure is eight steps and has to be repeated on twenty separate
evenings by a person who has just spent a day not being allowed to look at
the results. Eight manual steps times twenty sessions is where a skipped
manifest or an unwritten report comes from, and a session missing its
manifest cannot later prove it was not altered.

**It does not classify anything itself.** The status comes from the existing
QA rules, unchanged and unoverridable -- sec9 forbids a manual override, so
this tool deliberately exposes no flag that could supply one.
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

from research.option_recorder import audit as AU  # noqa: E402
from research.option_recorder import incidents as INC  # noqa: E402
from research.option_recorder import session_report as SR  # noqa: E402
from research.option_recorder.schema import SessionStatus  # noqa: E402
from research.option_recorder.store import ResearchStore  # noqa: E402

IST = dt.timezone(dt.timedelta(hours=5, minutes=30))


def close_session(store: ResearchStore, session_date: str,
                  instruments: Optional[List[str]] = None) -> Dict[str, Any]:
    """Run the sec9 procedure for every instrument of one session."""
    instruments = instruments or [
        i for i in store.instruments("normalized")
        if store.partition("normalized", i, session_date).exists()]

    results = []
    for inst in instruments:
        # 1. manifest -- re-runnable, and required before integrity can be
        #    checked at all.
        manifest = store.write_manifest(inst, session_date)
        # 2. integrity
        verify = store.verify_partition(inst, session_date)
        # 3. report (persisted beside the data)
        path = SR.write(store, inst, session_date)
        rep = json.loads(path.read_text(encoding="utf-8"))
        # 4. incidents already recorded for this session
        inc = INC.read(store, session_date, inst)

        results.append({
            "instrument": inst,
            "status": rep["session_status"],
            "blockers": rep["blockers"],
            "manifest_files": len(manifest["files"]),
            "integrity_ok": verify.get("ok", False),
            "raw_rows": rep["persistence"]["raw_rows"],
            "normalized_rows": rep["persistence"]["normalized_rows"],
            "checkpoint_present": rep["persistence"]["checkpoint_present"],
            "snapshots": rep["data_quality"]["observed_snapshots"],
            "incidents": len(inc),
            "report_path": str(path),
        })

    counts = {s.value: sum(1 for r in results if r["status"] == s.value)
              for s in SessionStatus}
    return {
        "session_date": session_date,
        "closed_at": dt.datetime.now(IST).isoformat(timespec="seconds"),
        "instruments": results,
        "status_counts": counts,
        # sec15: only COMPLETE counts, and it is counted per instrument-session
        # exactly as the audit counts it, so the two can never disagree.
        "complete_added": counts.get(SessionStatus.COMPLETE.value, 0),
    }


def counter(store: ResearchStore) -> Dict[str, Any]:
    """COMPLETE_SESSIONS = N, plus the next rung (sec15, sec16, sec17)."""
    a = AU.audit(store, target=20)
    n = a["complete"]
    return {
        "COMPLETE_SESSIONS": n,
        "incomplete": a["incomplete"],
        "unusable": a["unusable"],
        "not_collected": a["sessions_not_collected"],
        "attempted": a["calendar_sessions_attempted"],
        "next_checkpoint": next((c for c in AU.CHECKPOINTS if c > n), None),
        "checkpoints_reached": [c for c in AU.CHECKPOINTS if c <= n],
        "restart_drill_performed": a["incidents"]["restart_drill_performed"],
    }


def render(res: Dict[str, Any], cnt: Dict[str, Any]) -> str:
    out = [f"END OF DAY  {res['session_date']}        closed {res['closed_at']}",
           "=" * 66]
    if not res["instruments"]:
        out.append("  no stored data for this session date")
    for r in res["instruments"]:
        out += [
            f"  {r['instrument']}",
            f"    status            {r['status']}",
            f"    snapshots         {r['snapshots']}",
            f"    raw / normalized  {r['raw_rows']} / {r['normalized_rows']}",
            f"    manifest files    {r['manifest_files']}",
            f"    integrity         {'OK' if r['integrity_ok'] else 'FAILED'}",
            f"    checkpoint        {'present' if r['checkpoint_present'] else 'MISSING'}",
            f"    incidents logged  {r['incidents']}",
            f"    report            {r['report_path']}",
        ]
        for b in r["blockers"]:
            out.append(f"      BLOCKER: {b}")
    out += [
        "",
        f"  COMPLETE_SESSIONS = {cnt['COMPLETE_SESSIONS']}"
        f"   (+{res['complete_added']} from this session)",
        f"  incomplete {cnt['incomplete']}   unusable {cnt['unusable']}"
        f"   not collected {cnt['not_collected']}",
        f"  next checkpoint at {cnt['next_checkpoint']} COMPLETE sessions",
    ]
    if not cnt["restart_drill_performed"]:
        out.append("  reminder: the sec12 restart drill has not been performed yet")
    out += ["", "  TRADING: NO-GO (unchanged)"]
    return "\n".join(out)


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", default=None)
    ap.add_argument("--session", default=None,
                    help="YYYY-MM-DD (default: today)")
    ap.add_argument("--instruments", nargs="*", default=None)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    store = ResearchStore(Path(args.root) if args.root else None)
    session = args.session or dt.datetime.now(IST).date().isoformat()
    res = close_session(store, session, args.instruments)
    cnt = counter(store)
    print(json.dumps({"close": res, "counter": cnt}, indent=2, default=str)
          if args.json else render(res, cnt))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
