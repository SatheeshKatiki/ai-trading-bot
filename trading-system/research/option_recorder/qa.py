"""Daily data-completeness report (Phase 12 sec17). RESEARCH ONLY."""
from __future__ import annotations

import argparse
import datetime as dt
import sys
from collections import Counter
from pathlib import Path
from typing import Dict, List, Optional

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from research.option_recorder.schema import Quality  # noqa: E402
from research.option_recorder.store import ResearchStore  # noqa: E402

#: A 5-minute cadence over 09:15-15:30 is 76 snapshots.
EXPECTED_SNAPSHOTS_5MIN = 76


def session_report(store: ResearchStore, instrument: str,
                   session_date: str) -> Dict:
    quotes = list(store.read("normalized", instrument, session_date, "quotes.jsonl"))
    under = list(store.read("derived", instrument, session_date, "underlying.jsonl"))
    events = list(store.read("events", instrument, session_date, "signals.jsonl"))
    raw = list(store.read("raw", instrument, session_date, "chain.jsonl"))

    q = Counter(r.get("quality") for r in quotes)
    snaps = sorted({r.get("event_time") for r in quotes})
    strikes = {r.get("strike") for r in quotes}
    expiries = {r.get("expiry") for r in quotes if r.get("expiry")}

    gaps: List[str] = []
    if len(snaps) > 1:
        for a, b in zip(snaps, snaps[1:]):
            try:
                ta, tb = dt.datetime.fromisoformat(a), dt.datetime.fromisoformat(b)
            except ValueError:
                continue
            mins = (tb - ta).total_seconds() / 60.0
            if mins > 7.5:      # more than 1.5 expected intervals
                gaps.append(f"{a} -> {b} ({mins:.0f}m)")

    verify = store.verify_partition(instrument, session_date)
    return dict(
        instrument=instrument, session_date=session_date,
        raw_payloads=len(raw), snapshots=len(snaps),
        expected_snapshots=EXPECTED_SNAPSHOTS_5MIN,
        completeness_pct=100.0 * len(snaps) / EXPECTED_SNAPSHOTS_5MIN,
        quotes=len(quotes), underlying_rows=len(under), signal_events=len(events),
        distinct_strikes=len(strikes), distinct_expiries=len(expiries),
        quality={k: v for k, v in q.items()},
        valid_pct=(100.0 * q.get(Quality.VALID.value, 0) / len(quotes)) if quotes else 0.0,
        synthetic=q.get(Quality.SYNTHETIC.value, 0),
        gaps=gaps, integrity=verify,
        usable=(q.get(Quality.SYNTHETIC.value, 0) == 0
                and len(snaps) >= 0.8 * EXPECTED_SNAPSHOTS_5MIN
                and verify.get("ok", False)),
    )


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", default=None)
    ap.add_argument("--instrument", default=None)
    ap.add_argument("--session", default=None)
    args = ap.parse_args(argv)
    store = ResearchStore(Path(args.root) if args.root else None)

    instruments = [args.instrument] if args.instrument else store.instruments("normalized")
    if not instruments:
        print("no collected data yet at", store.root)
        return 0

    print(f"{'instrument':<11}{'session':<12}{'snaps':>7}{'compl%':>8}"
          f"{'quotes':>8}{'valid%':>8}{'synth':>7}{'events':>7}{'gaps':>6}{'integrity':>11}{'usable':>8}")
    for inst in instruments:
        sessions = [args.session] if args.session else store.sessions("normalized", inst)
        for sd in sessions:
            r = session_report(store, inst, sd)
            integ = "OK" if r["integrity"].get("ok") else r["integrity"].get("error", "MISMATCH")
            print(f"{inst:<11}{sd:<12}{r['snapshots']:>7}{r['completeness_pct']:>7.0f}%"
                  f"{r['quotes']:>8}{r['valid_pct']:>7.0f}%{r['synthetic']:>7}"
                  f"{r['signal_events']:>7}{len(r['gaps']):>6}{integ:>11}"
                  f"{('YES' if r['usable'] else 'NO'):>8}")
            for g in r["gaps"][:3]:
                print(f"{'':<23}gap: {g}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
