"""Checkpoint audit across many sessions (Phase 14 sec14, sec19).

    python -m research.option_recorder.audit --target 20

RESEARCH INFRASTRUCTURE. Aggregates session reports. Never trades, and never
looks at strategy performance -- the checkpoint question is whether the DATA
can be trusted, not whether the setup made money.

The counting rule that matters
------------------------------
Only ``COMPLETE`` sessions count toward a checkpoint. ``INCOMPLETE`` and
``UNUSABLE`` sessions are kept, reported and never counted. The temptation at
session 18 is to relax the definition; the definition is therefore applied
here mechanically, from the stored reports, with no override.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from research.option_recorder import incidents as INC  # noqa: E402
from research.option_recorder import session_report as SR  # noqa: E402
from research.option_recorder.schema import SessionStatus  # noqa: E402
from research.option_recorder.store import ResearchStore  # noqa: E402

#: Checkpoint ladder. Phase 15 adds the early 5 and 10 rungs: a systemic
#: recorder defect found at session 5 costs 5 sessions, the same defect found
#: at 20 costs 20, and the whole point of the early rungs is that the cost of
#: looking is one afternoon.
CHECKPOINTS = (5, 10, 20, 60, 125)


def storage_footprint(store: ResearchStore) -> Dict[str, Any]:
    """Bytes and rows on disk, per layer (sec19).

    Tracked so the growth rate is known BEFORE it becomes a problem. Nothing
    here deletes anything: raw history is never removed to save space.
    """
    layers: Dict[str, Dict[str, int]] = {}
    total_bytes = 0
    for layer in ("raw", "normalized", "derived", "events"):
        base = store.root / layer
        if not base.exists():
            continue
        nbytes = nfiles = 0
        for f in base.rglob("*.jsonl"):
            nbytes += f.stat().st_size
            nfiles += 1
        layers[layer] = {"bytes": nbytes, "files": nfiles,
                         "mb": round(nbytes / 1e6, 2)}
        total_bytes += nbytes
    return {"layers": layers, "total_bytes": total_bytes,
            "total_mb": round(total_bytes / 1e6, 2)}


def collect_reports(store: ResearchStore,
                    instruments: Optional[List[str]] = None
                    ) -> List[Dict[str, Any]]:
    out = []
    for inst in (instruments or store.instruments("normalized")):
        for sd in store.sessions("normalized", inst):
            out.append(SR.build(store, inst, sd))
    return sorted(out, key=lambda r: (r["session_metadata"]["session_date"],
                                      r["session_metadata"]["instrument"]))


def audit(store: ResearchStore, target: int = 20,
          instruments: Optional[List[str]] = None) -> Dict[str, Any]:
    reports = collect_reports(store, instruments)
    by_status = Counter(r["session_status"] for r in reports)
    complete = [r for r in reports
                if r["session_status"] == SessionStatus.COMPLETE.value]

    def total(section: str, field: str, rows=None) -> int:
        return sum(int(r[section].get(field) or 0) for r in (rows or reports))

    obs = total("data_quality", "total_observations", complete)
    setups = total("persistence", "distinct_setups", complete)
    snaps = total("data_quality", "observed_snapshots", complete)
    expected = total("data_quality", "expected_snapshots", complete)

    def mean(section: str, field: str, rows) -> Optional[float]:
        vals = [r[section].get(field) for r in rows
                if r[section].get(field) is not None]
        return round(sum(vals) / len(vals), 2) if vals else None

    # sec14 requires these per-quote aggregates by name. They are summed over
    # ALL sessions, not only COMPLETE ones: a defect that disqualified a
    # session is exactly the thing the cumulative summary must keep showing.
    quality_totals = {
        field: total("data_quality", field)
        for field in ("total_observations", "valid", "invalid", "synthetic",
                      "stale", "zero_bid_or_ask", "crossed_quotes",
                      "malformed_rows", "duplicate_observations")
    }
    vix_sessions = [r for r in reports
                    if r["data_quality"].get("india_vix_observations", 0) > 0]
    vix_availability = {
        "sessions_with_vix": len(vix_sessions),
        "sessions_total": len(reports),
        "pct": (round(100.0 * len(vix_sessions) / len(reports), 2)
                if reports else None),
        "observations": total("data_quality", "india_vix_observations"),
    }
    coverage = {
        "avg_strikes": mean("data_quality", "distinct_strikes", reports),
        "min_strikes": min((r["data_quality"]["distinct_strikes"]
                            for r in reports), default=None),
        "avg_expiries": mean("data_quality", "distinct_expiries", reports),
    }

    unresolved: List[str] = []
    for r in reports:
        if r["session_status"] != SessionStatus.COMPLETE.value:
            md = r["session_metadata"]
            unresolved.append(
                f"{md['session_date']} {md['instrument']}: "
                f"{r['session_status']} -- {'; '.join(r['blockers']) or 'no blocker recorded'}")

    incident_summary = INC.summary(store)
    # A session the pre-flight refused never reaches the store, so it exists
    # only in the incident log. Counting attempts without it would understate
    # how many days were actually lost.
    not_collected = incident_summary["sessions_not_collected"]

    integrity_failures = [r for r in reports if not r["integrity"].get("ok")]
    timing_failures = [r for r in reports if not r["time_integrity"]["ok"]]

    complete_count = len(complete)
    # Any recorded alteration of stored data is a lineage problem, which sec19
    # calls blocking regardless of how healthy the counts look.
    if incident_summary["data_modified_events"]:
        unresolved.append(
            f"{len(incident_summary['data_modified_events'])} incident(s) "
            f"record stored data being modified")

    if complete_count >= target and not unresolved:
        decision = "DATA QUALITY PASS"
    elif complete_count >= target:
        decision = "DATA QUALITY CONDITIONAL"
    elif integrity_failures or timing_failures:
        decision = "DATA COLLECTION BLOCKED"
    else:
        decision = "IN PROGRESS"

    return {
        "generated_at": dt.datetime.now(SR.IST).isoformat(timespec="seconds"),
        "target": target,
        "calendar_sessions_attempted": len(reports) + len(not_collected),
        "sessions_with_stored_data": len(reports),
        "sessions_not_collected": len(not_collected),
        "not_collected_dates": not_collected,
        "complete": complete_count,
        "incomplete": by_status.get(SessionStatus.INCOMPLETE.value, 0),
        "unusable": by_status.get(SessionStatus.UNUSABLE.value, 0),
        "empty": by_status.get(SessionStatus.EMPTY.value, 0),
        "instruments": sorted({r["session_metadata"]["instrument"]
                               for r in reports}),
        "totals_over_complete_sessions": {
            "option_observations": obs,
            "setups": setups,
            "snapshots": snaps,
            "expected_snapshots": expected,
            "recorder_uptime_pct": (round(100.0 * snaps / expected, 2)
                                    if expected else None),
        },
        "averages_over_complete_sessions": {
            "chain_coverage_strikes": mean("data_quality", "distinct_strikes", complete),
            "quote_validity_pct": mean("data_quality", "valid_pct", complete),
            "completeness_pct": mean("data_quality", "completeness_pct", complete),
        },
        "restart_recovery": {
            "restarts": total("persistence", "restarts"),
            "reconnects": total("persistence", "reconnects"),
            "storage_errors": total("persistence", "storage_errors"),
            "fetch_failures": total("persistence", "fetch_failures"),
            "duplicates_after_restart": total("data_quality",
                                              "duplicate_observations"),
        },
        "integrity": {
            "sessions_failing_file_integrity": len(integrity_failures),
            "sessions_failing_time_integrity": len(timing_failures),
            "future_timestamp_violations": total("time_integrity",
                                                 "future_timestamp_violations"),
            "availability_violations": total("time_integrity",
                                             "availability_violations"),
        },
        "quote_quality_totals": quality_totals,
        "india_vix_availability": vix_availability,
        "chain_coverage": coverage,
        "incidents": {
            "total": incident_summary["total"],
            "by_type": incident_summary["by_type"],
            "restart_drill_performed": bool(incident_summary["restart_drills"]),
            "data_modified_events": len(incident_summary["data_modified_events"]),
        },
        "storage": storage_footprint(store),
        "unresolved_data_quality_issues": unresolved,
        "decision": decision,
        "next_checkpoint": next((c for c in CHECKPOINTS if c > complete_count),
                                None),
    }


def render(a: Dict[str, Any]) -> str:
    t, av, rr = (a["totals_over_complete_sessions"],
                 a["averages_over_complete_sessions"], a["restart_recovery"])
    ig = a["integrity"]
    lines = [
        f"{a['target']}-SESSION DATA AUDIT        generated {a['generated_at']}",
        "=" * 64,
        f"  calendar sessions attempted   {a['calendar_sessions_attempted']}",
        f"  COMPLETE                      {a['complete']}  / target {a['target']}",
        f"  INCOMPLETE                    {a['incomplete']}",
        f"  UNUSABLE                      {a['unusable']}",
        f"  EMPTY                         {a['empty']}",
        f"  instruments                   {', '.join(a['instruments']) or '-'}",
        "",
        "  OVER COMPLETE SESSIONS",
        f"    option observations         {t['option_observations']}",
        f"    setups observed             {t['setups']}",
        f"    snapshots                   {t['snapshots']} / {t['expected_snapshots']}",
        f"    recorder uptime             {t['recorder_uptime_pct']}%",
        f"    avg chain coverage          {av['chain_coverage_strikes']} strikes",
        f"    avg quote validity          {av['quote_validity_pct']}%",
        f"    avg completeness            {av['completeness_pct']}%",
        "",
        "  RESTART / RECOVERY",
        f"    restarts                    {rr['restarts']}",
        f"    reconnects                  {rr['reconnects']}",
        f"    storage errors              {rr['storage_errors']}",
        f"    fetch failures              {rr['fetch_failures']}",
        f"    duplicates surviving        {rr['duplicates_after_restart']}",
        "",
        "  INTEGRITY",
        f"    file integrity failures     {ig['sessions_failing_file_integrity']}",
        f"    time integrity failures     {ig['sessions_failing_time_integrity']}",
        f"    future timestamps           {ig['future_timestamp_violations']}",
        f"    availability violations     {ig['availability_violations']}",
        "",
        f"  STORAGE                       {a['storage']['total_mb']} MB",
    ]
    for layer, meta in a["storage"]["layers"].items():
        lines.append(f"    {layer:<26}{meta['mb']} MB  ({meta['files']} files)")
    if a["unresolved_data_quality_issues"]:
        lines += ["", "  UNRESOLVED DATA-QUALITY ISSUES"]
        lines += [f"    - {u}" for u in a["unresolved_data_quality_issues"]]
    qt = a["quote_quality_totals"]
    lines += [
        "",
        "  QUOTE QUALITY (all sessions)",
        f"    observations                {qt['total_observations']}",
        f"    valid / invalid             {qt['valid']} / {qt['invalid']}",
        f"    synthetic                   {qt['synthetic']}",
        f"    stale                       {qt['stale']}",
        f"    zero bid/ask                {qt['zero_bid_or_ask']}",
        f"    crossed                     {qt['crossed_quotes']}",
        f"    malformed                   {qt['malformed_rows']}",
        f"    duplicates                  {qt['duplicate_observations']}",
        "",
        f"  INDIA VIX                     "
        f"{a['india_vix_availability']['sessions_with_vix']}"
        f"/{a['india_vix_availability']['sessions_total']} sessions"
        f"  ({a['india_vix_availability']['observations']} observations)",
        f"  CHAIN COVERAGE                avg {a['chain_coverage']['avg_strikes']}"
        f"  min {a['chain_coverage']['min_strikes']} strikes",
        f"  INCIDENTS                     {a['incidents']['total']}"
        f"  (restart drill: "
        f"{'done' if a['incidents']['restart_drill_performed'] else 'NOT DONE'})",
    ]
    if a["not_collected_dates"]:
        lines.append(f"  NOT COLLECTED                 "
                     f"{len(a['not_collected_dates'])} days: "
                     f"{', '.join(a['not_collected_dates'][:5])}")
    lines += ["", f"  DECISION: {a['decision']}"]
    if a["next_checkpoint"]:
        lines.append(f"  next checkpoint at {a['next_checkpoint']} COMPLETE sessions")
    lines += ["", "  TRADING: NO-GO (unchanged -- this is a data verdict only)"]
    return "\n".join(lines)


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", default=None)
    ap.add_argument("--target", type=int, default=20)
    ap.add_argument("--instruments", nargs="*", default=None)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    store = ResearchStore(Path(args.root) if args.root else None)
    a = audit(store, target=args.target, instruments=args.instruments)
    print(json.dumps(a, indent=2, default=str) if args.json else render(a))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
