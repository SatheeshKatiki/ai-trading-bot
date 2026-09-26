"""Pre-session go/no-go check (Phase 14 sec1). RESEARCH ONLY -- writes nothing.

    python -m research.option_recorder.preflight

Every check is executed, not asserted. The Phase 13 runbook asked the
operator to *read* a dry-run log line and judge it; this makes the judgement
mechanical, because the one failure that matters -- a synthetic chain from a
missing broker session -- looks entirely normal at a glance and costs a whole
trading day.

Exit code 0 means GO. Anything else means do not collect this session.
"""

from __future__ import annotations

import argparse
import datetime as dt
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from research.option_recorder import collect as C  # noqa: E402
from research.option_recorder.store import ResearchStore  # noqa: E402

IST = C.IST

#: A check marked critical blocks the session on its own. No averaging.
CRITICAL = True
ADVISORY = False


def _check(name: str, ok: bool, detail: str, critical: bool = CRITICAL):
    return {"name": name, "ok": bool(ok), "detail": detail,
            "critical": bool(critical)}


def run(store: Optional[ResearchStore] = None,
        instruments: Optional[List[str]] = None,
        now: Optional[dt.datetime] = None) -> Dict[str, Any]:
    store = store or ResearchStore()
    instruments = instruments or ["NIFTY", "BANKNIFTY", "SENSEX"]
    now = now or C._now()
    checks: List[Dict[str, Any]] = []

    # -- clock and session date --------------------------------------
    offset = now.utcoffset()
    checks.append(_check(
        "clock is IST (+05:30)", offset == IST.utcoffset(None),
        f"offset {offset}"))
    checks.append(_check(
        "session date is today", now.date() == dt.datetime.now(IST).date(),
        now.date().isoformat()))
    checks.append(_check(
        "it is a weekday", now.weekday() < 5,
        now.strftime("%A"), critical=ADVISORY))
    checks.append(_check(
        "market is open (09:15-15:30)", C.market_open(now),
        now.strftime("%H:%M"), critical=ADVISORY))

    # -- storage ------------------------------------------------------
    writable, detail = _storage_writable(store)
    checks.append(_check("storage path is writable", writable, detail))

    # -- bridge + broker session --------------------------------------
    for inst in instruments:
        chain = C.fetch_chain(inst)
        if chain is None:
            checks.append(_check(f"{inst}: chain endpoint reachable", False,
                                 "no response -- is api_bridge running?"))
            continue
        checks.append(_check(f"{inst}: chain endpoint reachable", True,
                             str(chain.get("priceSource") or "unknown")))

        synthetic = bool(chain.get("synthetic"))
        checks.append(_check(
            f"{inst}: chain is REAL, not synthetic", not synthetic,
            "synthetic=true -- no authenticated Fyers session; a session "
            "collected now is worthless" if synthetic
            else f"priceSource={chain.get('priceSource')}"))

        cov = C.chain_coverage(chain)
        ok_cov, problems = C.coverage_ok(cov)
        checks.append(_check(
            f"{inst}: chain coverage", ok_cov,
            f"{cov['strikes']} strikes, spot {cov['spot']}"
            + ("" if ok_cov else " -- " + "; ".join(problems)),
            critical=ADVISORY))

        quotes, counts = C.normalise_chain(inst, chain, retrieved_at=now)
        valid = counts.get("VALID", 0)
        nonzero = {k: v for k, v in counts.items() if v}
        checks.append(_check(
            f"{inst}: quotes parse and classify", bool(quotes),
            f"{len(quotes)} legs, quality={nonzero}"))
        checks.append(_check(
            f"{inst}: at least some VALID quotes", valid > 0,
            f"{valid} valid", critical=ADVISORY))

        vix, _ = C.extract_vix(chain)
        checks.append(_check(f"{inst}: India VIX present",
                             vix is not None, str(vix), critical=ADVISORY))

        # -- history + timestamp semantics -----------------------------
        hist = C.fetch_history(inst)
        if hist is None or hist.empty:
            checks.append(_check(f"{inst}: underlying history available", False,
                                 "no history", critical=ADVISORY))
        else:
            last = hist.index[-1]
            checks.append(_check(f"{inst}: underlying history available", True,
                                 f"{len(hist)} bars to {last}"))
            import pandas as pd
            naive_now = pd.Timestamp(now.replace(tzinfo=None))
            checks.append(_check(
                f"{inst}: history has no future bars", last <= naive_now,
                f"last bar {last} vs now {naive_now}"))

    failed_critical = [c for c in checks if c["critical"] and not c["ok"]]
    advisories = [c for c in checks if not c["critical"] and not c["ok"]]
    return {"checks": checks, "go": not failed_critical,
            "failed_critical": failed_critical, "advisories": advisories,
            "checked_at": now.isoformat(timespec="seconds")}


def _storage_writable(store: ResearchStore) -> Tuple[bool, str]:
    try:
        store.root.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=store.root, delete=True):
            pass
        return True, str(store.root)
    except OSError as exc:
        return False, f"{store.root}: {exc}"


def render(res: Dict[str, Any]) -> str:
    lines = [f"PRE-FLIGHT  {res['checked_at']}", "=" * 62]
    for c in res["checks"]:
        mark = "PASS" if c["ok"] else ("FAIL" if c["critical"] else "warn")
        lines.append(f"  [{mark}] {c['name']:<42} {c['detail']}")
    lines.append("")
    if res["go"]:
        lines.append("  GO -- start the recorder.")
        if res["advisories"]:
            lines.append("  (advisories above are not blocking)")
    else:
        lines.append("  NO-GO -- do not collect this session:")
        lines.extend(f"    - {c['name']}: {c['detail']}"
                     for c in res["failed_critical"])
    return "\n".join(lines)


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", default=None)
    ap.add_argument("--instruments", nargs="+",
                    default=["NIFTY", "BANKNIFTY", "SENSEX"])
    args = ap.parse_args(argv)
    res = run(ResearchStore(Path(args.root) if args.root else None),
              args.instruments)
    print(render(res))
    return 0 if res["go"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
