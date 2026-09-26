"""Per-session evidence report (Phase 14 sec7) and the 20-session audit (sec14).

RESEARCH INFRASTRUCTURE. Reads the store, writes reports. Never trades.

Why a separate report from ``qa``
---------------------------------
``qa`` answers "is today's data usable?" in one line per session. This answers
"what exactly happened during that session, and can a stranger six months from
now verify it?" -- which needs the things that leave no trace in the data
itself: outages, restarts, storage errors, refused bars. Those live in the
checkpoint the running process wrote, so a report rebuilt from data files
alone would silently show a clean session.

Nothing here judges the strategy. A session report says whether the DATA is
trustworthy, never whether the setup made money.
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

from research.option_recorder import qa  # noqa: E402
from research.option_recorder.schema import (  # noqa: E402
    NORMALIZATION_VERSION, RECORDER_VERSION, SCHEMA_VERSION, Quality,
    SessionStatus)
from research.option_recorder.store import ResearchStore  # noqa: E402

IST = dt.timezone(dt.timedelta(hours=5, minutes=30))


# ---------------------------------------------------------------------
# time integrity (sec7)
# ---------------------------------------------------------------------

def _time_integrity(quotes: List[Dict], under: List[Dict],
                    events: List[Dict]) -> Dict[str, Any]:
    """Re-derive the timestamp guarantees FROM THE STORED DATA.

    The recorder enforces these at write time; this checks them again at read
    time. A guarantee that is only ever asserted by the writer is not a
    guarantee -- if a future normalisation bug breaks it, this is what notices.
    """
    bad_tz, future, availability = 0, 0, 0
    now = dt.datetime.now(IST)

    def parsed(rec, field):
        v = rec.get(field)
        if not v:
            return None
        try:
            return dt.datetime.fromisoformat(v)
        except (TypeError, ValueError):
            return None

    for rec in list(quotes) + list(under) + list(events):
        ev, av = parsed(rec, "event_time"), parsed(rec, "available_at")
        for t in (ev, av):
            if t is not None and t.utcoffset() != IST.utcoffset(None):
                bad_tz += 1
        if ev is not None and ev > now:
            future += 1
        if ev is not None and av is not None and av < ev:
            # available_at before the event it describes is look-ahead.
            availability += 1

    return {
        "timezone_ok": bad_tz == 0,
        "non_ist_timestamps": bad_tz,
        "future_timestamp_violations": future,
        "availability_violations": availability,
        "ok": bad_tz == 0 and future == 0 and availability == 0,
    }


def _quote_defects(quotes: List[Dict]) -> Dict[str, int]:
    """Count the specific defect kinds sec7 asks for, from the reasons the
    classifier recorded rather than by re-deriving them."""
    zero, crossed, other = 0, 0, 0
    for r in quotes:
        if r.get("quality") != Quality.INVALID.value:
            continue
        reasons = " ".join(r.get("quality_reasons") or [])
        if "two-sided" in reasons or "zero bid" in reasons:
            zero += 1
        elif "crossed" in reasons:
            crossed += 1
        else:
            other += 1
    return {"zero_bid_or_ask": zero, "crossed_quotes": crossed,
            "other_invalid": other}


# ---------------------------------------------------------------------
# the report (sec7)
# ---------------------------------------------------------------------

def build(store: ResearchStore, instrument: str,
          session_date: str) -> Dict[str, Any]:
    base = qa.session_report(store, instrument, session_date)

    quotes = list(store.read("normalized", instrument, session_date, "quotes.jsonl"))
    under = list(store.read("derived", instrument, session_date, "underlying.jsonl"))
    events = list(store.read("events", instrument, session_date, "signals.jsonl"))
    raw = list(store.read("raw", instrument, session_date, "chain.jsonl"))
    cp = store.read_checkpoint(instrument, session_date) or {}

    sources = sorted({r.get("source") for r in quotes if r.get("source")})
    versions = {
        "recorder_version": sorted({r.get("recorder_version") for r in quotes
                                    if r.get("recorder_version")}) or [RECORDER_VERSION],
        "schema_version": sorted({r.get("schema_version") for r in quotes
                                  if r.get("schema_version")}) or [SCHEMA_VERSION],
        "normalization_version": sorted({r.get("normalization_version")
                                         for r in quotes
                                         if r.get("normalization_version")})
                                 or [NORMALIZATION_VERSION],
    }

    times = sorted(r["event_time"] for r in quotes if r.get("event_time"))
    timing = _time_integrity(quotes, under, events)
    defects = _quote_defects(quotes)

    setups = {e.get("setup_id") for e in events if e.get("setup_id")}
    vix = [u.get("india_vix") for u in under if u.get("india_vix") is not None]

    report = {
        "session_metadata": {
            "session_date": session_date,
            "instrument": instrument,
            "recorder_version": versions["recorder_version"],
            "schema_version": versions["schema_version"],
            "normalization_version": versions["normalization_version"],
            "source": sources,
            "start_time": times[0] if times else None,
            "end_time": times[-1] if times else None,
            "report_generated_at": dt.datetime.now(IST).isoformat(timespec="seconds"),
        },
        "data_quality": {
            "expected_snapshots": base["expected_snapshots"],
            "observed_snapshots": base["snapshots"],
            "completeness_pct": round(base["completeness_pct"], 2),
            "total_observations": base["quotes"],
            "valid": base["quality"].get(Quality.VALID.value, 0),
            "invalid": base["quality"].get(Quality.INVALID.value, 0),
            "synthetic": base["synthetic"],
            "stale": base["stale"],
            "missing": base["quality"].get(Quality.MISSING.value, 0),
            "zero_bid_or_ask": defects["zero_bid_or_ask"],
            "crossed_quotes": defects["crossed_quotes"],
            "other_invalid": defects["other_invalid"],
            "duplicate_observations": base["duplicates"],
            "malformed_rows": base.get("malformed", 0),
            "missing_intervals": base["gaps"],
            "valid_pct": round(base["valid_pct"], 2),
            "distinct_strikes": base["distinct_strikes"],
            "distinct_expiries": base["distinct_expiries"],
            "india_vix_observations": len(vix),
            "india_vix_range": [min(vix), max(vix)] if vix else None,
        },
        "persistence": {
            "raw_rows": len(raw),
            "normalized_rows": len(quotes),
            "underlying_rows": len(under),
            "setup_event_rows": len(events),
            "distinct_setups": len(setups),
            "setup_ids": sorted(setups),
            "storage_errors": int(cp.get("storage_errors") or 0),
            "reconnects": int(cp.get("reconnects") or 0),
            "restarts": int(cp.get("restarts") or 0),
            "fetch_failures": int(cp.get("failures") or 0),
            "thin_chains": int(cp.get("thin_chains") or 0),
            "synthetic_snapshots": int(cp.get("synthetic_snapshots") or 0),
            "checkpoint_present": bool(cp),
        },
        "time_integrity": dict(
            timing,
            future_bars_refused=int(cp.get("future_bars_refused") or 0)),
        "integrity": base["integrity"],
        "scorecard": base["scorecard"],
        "score": base["score"],
        "session_status": base["status"],
        "blockers": list(base["blockers"]),
    }

    # Time integrity is its own gate. The scorecard cannot see it, so a
    # session that passes every other bound must still fail on look-ahead.
    if report["session_status"] != SessionStatus.EMPTY.value and not timing["ok"]:
        report["session_status"] = SessionStatus.UNUSABLE.value
        if not timing["timezone_ok"]:
            report["blockers"].append(
                f"{timing['non_ist_timestamps']} non-IST timestamps")
        if timing["future_timestamp_violations"]:
            report["blockers"].append(
                f"{timing['future_timestamp_violations']} future timestamps")
        if timing["availability_violations"]:
            report["blockers"].append(
                f"{timing['availability_violations']} rows where available_at "
                f"precedes event_time (look-ahead)")
    return report


def write(store: ResearchStore, instrument: str, session_date: str) -> Path:
    """Persist the report beside the data it describes."""
    rep = build(store, instrument, session_date)
    d = store.root / "reports" / instrument
    d.mkdir(parents=True, exist_ok=True)
    path = d / f"{session_date}.json"
    path.write_text(json.dumps(rep, indent=2, default=str), encoding="utf-8")
    return path


def render(rep: Dict[str, Any]) -> str:
    m, q = rep["session_metadata"], rep["data_quality"]
    p, t = rep["persistence"], rep["time_integrity"]
    out = [
        f"SESSION REPORT  {m['instrument']}  {m['session_date']}",
        "=" * 58,
        f"  status              {rep['session_status']}   (score {rep['score']:.2f})",
        f"  window              {m['start_time']}  ->  {m['end_time']}",
        f"  source              {', '.join(m['source']) or '-'}",
        f"  versions            recorder {','.join(m['recorder_version'])}"
        f"  schema {','.join(m['schema_version'])}",
        "",
        "  DATA QUALITY",
        f"    snapshots         {q['observed_snapshots']}/{q['expected_snapshots']}"
        f"  ({q['completeness_pct']:.0f}%)",
        f"    observations      {q['total_observations']}",
        f"    valid             {q['valid']}  ({q['valid_pct']:.0f}%)",
        f"    invalid           {q['invalid']}"
        f"   [zero bid/ask {q['zero_bid_or_ask']}, crossed {q['crossed_quotes']}]",
        f"    stale             {q['stale']}",
        f"    synthetic         {q['synthetic']}",
        f"    duplicates        {q['duplicate_observations']}",
        f"    malformed         {q['malformed_rows']}",
        f"    missing intervals {len(q['missing_intervals'])}",
        f"    strikes/expiries  {q['distinct_strikes']} / {q['distinct_expiries']}",
        f"    india vix obs     {q['india_vix_observations']}"
        f"  range {q['india_vix_range']}",
        "",
        "  PERSISTENCE",
        f"    raw / normalized  {p['raw_rows']} / {p['normalized_rows']}",
        f"    underlying rows   {p['underlying_rows']}",
        f"    setup events      {p['setup_event_rows']}"
        f"  ({p['distinct_setups']} distinct setups)",
        f"    storage errors    {p['storage_errors']}",
        f"    reconnects        {p['reconnects']}",
        f"    restarts          {p['restarts']}",
        f"    fetch failures    {p['fetch_failures']}",
        "",
        "  TIME INTEGRITY",
        f"    timezone ok       {t['timezone_ok']}",
        f"    future timestamps {t['future_timestamp_violations']}"
        f"  (refused at write: {t['future_bars_refused']})",
        f"    availability      {t['availability_violations']} violations",
        "",
        f"  FILE INTEGRITY      {'OK' if rep['integrity'].get('ok') else 'FAILED'}",
    ]
    if rep["blockers"]:
        out.append("")
        out.append("  BLOCKERS")
        out.extend(f"    - {b}" for b in rep["blockers"])
    return "\n".join(out)


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", default=None)
    ap.add_argument("--instrument", required=True)
    ap.add_argument("--session", required=True)
    ap.add_argument("--write", action="store_true",
                    help="persist the report as JSON beside the data")
    args = ap.parse_args(argv)
    store = ResearchStore(Path(args.root) if args.root else None)
    rep = build(store, args.instrument, args.session)
    print(render(rep))
    if args.write:
        print("\nwritten:", write(store, args.instrument, args.session))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
