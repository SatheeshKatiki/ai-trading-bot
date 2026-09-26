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

from research.option_recorder.schema import (  # noqa: E402
    Quality, SessionStatus, observation_key)
from research.option_recorder.store import ResearchStore  # noqa: E402

#: A 5-minute cadence over 09:15-15:30 is 76 snapshots.
EXPECTED_SNAPSHOTS_5MIN = 76


#: Structural bounds a session must clear to be called COMPLETE (sec14).
MIN_COMPLETENESS_PCT = 90.0
MIN_VALID_PCT = 80.0
MIN_STRIKES = 10
USABLE_COMPLETENESS_PCT = 60.0


def _grade(value: float, good: float) -> float:
    """0..1 score, capped. Deliberately linear -- a weighted composite that
    hides a zero in one dimension behind nines in the others is how a broken
    feed passes a health check."""
    if good <= 0:
        return 1.0
    return max(0.0, min(1.0, value / good))


def session_report(store: ResearchStore, instrument: str,
                   session_date: str) -> Dict:
    """Full data-health record for one instrument-session (Phase 13 sec14).

    Six dimensions, each reported separately and each able on its own to
    disqualify a session. The composite score is for ranking sessions at a
    glance, never for deciding usability -- ``status`` does that, and it is
    a floor over the dimensions rather than an average of them.
    """
    quotes = list(store.read("normalized", instrument, session_date, "quotes.jsonl"))
    under = list(store.read("derived", instrument, session_date, "underlying.jsonl"))
    events = list(store.read("events", instrument, session_date, "signals.jsonl"))
    raw = list(store.read("raw", instrument, session_date, "chain.jsonl"))

    q = Counter(r.get("quality") for r in quotes)
    # A row with no event_time is corrupt. The report must SAY so, not throw:
    # a QA tool that crashes on bad data is a QA tool that never reports it.
    malformed = sum(1 for r in quotes if not r.get("event_time"))
    snaps = sorted({r.get("event_time") for r in quotes if r.get("event_time")})
    strikes = {r.get("strike") for r in quotes}
    expiries = {r.get("expiry") for r in quotes if r.get("expiry")}

    # -- 6. continuity: gaps between consecutive snapshots ---------------
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

    # -- uniqueness: the dedup guarantee, verified on disk ---------------
    keys = []
    for r in quotes:
        try:
            keys.append(observation_key(
                r.get("underlying"), r.get("event_time"), r.get("option_symbol"),
                r.get("expiry"), r.get("strike") or 0.0, r.get("option_type")))
        except (TypeError, ValueError):
            malformed += 1
    duplicates = len(keys) - len(set(keys))

    verify = store.verify_partition(instrument, session_date)
    n = len(quotes)
    completeness_pct = 100.0 * len(snaps) / EXPECTED_SNAPSHOTS_5MIN
    valid_pct = (100.0 * q.get(Quality.VALID.value, 0) / n) if n else 0.0
    synthetic = q.get(Quality.SYNTHETIC.value, 0)
    stale = q.get(Quality.STALE.value, 0)

    scorecard = {
        "coverage": _grade(len(strikes), MIN_STRIKES),
        "completeness": _grade(completeness_pct, MIN_COMPLETENESS_PCT),
        "freshness": (1.0 - (stale / n)) if n else 0.0,
        "validity": _grade(valid_pct, MIN_VALID_PCT),
        "integrity": 1.0 if verify.get("ok") else 0.0,
        "continuity": 1.0 if not gaps else max(0.0, 1.0 - 0.2 * len(gaps)),
    }
    score = round(sum(scorecard.values()) / len(scorecard), 3)

    # -- status: a floor, not an average (sec13) -------------------------
    blockers = []
    if n == 0:
        status = SessionStatus.EMPTY
    else:
        if synthetic:
            blockers.append(f"{synthetic} SYNTHETIC quotes")
        if not verify.get("ok"):
            blockers.append("integrity check failed")
        if duplicates:
            blockers.append(f"{duplicates} duplicate observations")
        if malformed:
            blockers.append(f"{malformed} malformed rows")
        if completeness_pct < USABLE_COMPLETENESS_PCT:
            blockers.append(f"completeness {completeness_pct:.0f}%"
                            f" < {USABLE_COMPLETENESS_PCT:.0f}%")
        if blockers:
            status = SessionStatus.UNUSABLE
        elif (completeness_pct >= MIN_COMPLETENESS_PCT
              and valid_pct >= MIN_VALID_PCT
              and len(strikes) >= MIN_STRIKES
              and not gaps):
            status = SessionStatus.COMPLETE
        else:
            status = SessionStatus.INCOMPLETE

    return dict(
        instrument=instrument, session_date=session_date,
        raw_payloads=len(raw), snapshots=len(snaps),
        expected_snapshots=EXPECTED_SNAPSHOTS_5MIN,
        completeness_pct=completeness_pct,
        quotes=n, underlying_rows=len(under), signal_events=len(events),
        distinct_strikes=len(strikes), distinct_expiries=len(expiries),
        quality={k: v for k, v in q.items()},
        valid_pct=valid_pct, synthetic=synthetic, stale=stale,
        duplicates=duplicates, malformed=malformed,
        gaps=gaps, integrity=verify,
        scorecard=scorecard, score=score,
        status=status.value, blockers=blockers,
        # Kept for compatibility with the Phase 12 reader; COMPLETE and
        # INCOMPLETE are both real observed data.
        usable=status in (SessionStatus.COMPLETE, SessionStatus.INCOMPLETE),
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
          f"{'quotes':>8}{'valid%':>8}{'synth':>7}{'dup':>5}{'events':>7}"
          f"{'gaps':>6}{'score':>7}{'status':>12}")
    for inst in instruments:
        sessions = [args.session] if args.session else store.sessions("normalized", inst)
        for sd in sessions:
            r = session_report(store, inst, sd)
            print(f"{inst:<11}{sd:<12}{r['snapshots']:>7}{r['completeness_pct']:>7.0f}%"
                  f"{r['quotes']:>8}{r['valid_pct']:>7.0f}%{r['synthetic']:>7}"
                  f"{r['duplicates']:>5}{r['signal_events']:>7}"
                  f"{len(r['gaps']):>6}{r['score']:>7.2f}{r['status']:>12}")
            for b in r["blockers"]:
                print(f"{'':<23}BLOCKER: {b}")
            for g in r["gaps"][:3]:
                print(f"{'':<23}gap: {g}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
