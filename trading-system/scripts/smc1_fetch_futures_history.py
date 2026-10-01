#!/usr/bin/env python3
"""One-time, READ-ONLY fetch of NIFTY continuous futures history for smc1.

Owner decisions Q2 and Decision 2 (2026-10-01), DESIGN.md §16.1 / §18.3:

* **When.** On a trading day only from 15:45 IST onward; any time on a
  weekend or exchange holiday.
* **No login, ever.** Uses the access token already cached on disk
  (``brokers.token_cache``) -- the way ``api_bridge.py`` and
  ``trading_bot/main.py`` share one Fyers session. It never logs in, refreshes
  or generates a token. Missing token: stop before any call. A response that
  says the token is invalid or expired: stop immediately.
* **Engine check first.** Refuses while ``trading_bot/main.py`` or the paper
  observer is running with positions in ``config/active_positions.json``, or
  while ``main.py`` runs in LIVE mode (its broker orders cannot be checked
  without calling the order API).
* **Gentle on rate limits.** 30-day chunks, 1 s between calls, and any
  rate-limit response (HTTP 429, "limit", "too many") stops the whole run.
  Other errors are retried twice; a chunk that still fails is named as LOST.
* **Read-only, writes only under ``data/smc1/``.** History calls only
  (``FyersModel.history``); no order, quote or websocket call.

``api_bridge``'s ``/api/history`` is NOT used: it formats any unrecognised
symbol as an equity (``NSE:NIFTY26OCTFUT`` -> ``NSE:NIFTY26OCTFUT-EQ``) and
falls back to local CSVs, so it cannot return futures bars.

Usage (from trading-system/):
    python scripts/smc1_fetch_futures_history.py --dry-run
    python scripts/smc1_fetch_futures_history.py
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time as _time
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any, Callable, Iterable, Optional, Sequence
from zoneinfo import ZoneInfo

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

IST = ZoneInfo("Asia/Kolkata")
SAFE_FROM = time(15, 45)
SESSION_OPEN = time(9, 15)
SESSION_CLOSE = time(15, 30)
RESOLUTIONS = {"1": 1, "5": 5, "15": 15, "60": 60}
CHUNK_DAYS = 30
PAUSE_S = 1.0
ATTEMPTS = 3
OUT_DIR = ROOT / "data" / "smc1"
MONTHS = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"]

History = Callable[[dict[str, Any]], dict[str, Any]]


class StopFetch(RuntimeError):
    """A condition the owner set as a hard stop (token, rate limit)."""


# ---------------------------------------------------------------- guards

def fetch_window_reason(now: datetime, is_trading_day: Callable[[date], bool]) -> Optional[str]:
    """Why a fetch may NOT run at ``now`` (IST), or None if it may."""
    if not is_trading_day(now.date()):
        return None
    if now.time() >= SAFE_FROM:
        return None
    return (f"{now:%Y-%m-%d %H:%M} IST is a trading day before 15:45; the owner's rule is "
            f"to fetch only after 15:45 IST or on a non-trading day")


@dataclass
class EngineState:
    main_running: bool
    observer_running: bool
    live_mode: bool
    positions: int

    def refusal(self) -> Optional[str]:
        if self.main_running and self.live_mode:
            return ("trading_bot/main.py is running in LIVE mode; its broker orders cannot be "
                    "verified without calling the order API")
        if (self.main_running or self.observer_running) and self.positions:
            who = "main.py" if self.main_running else "paper_observer.py"
            return f"{who} is running and config/active_positions.json holds {self.positions} position(s)"
        return None


def engine_state(cmdlines: Iterable[Sequence[str]], settings: dict[str, Any],
                 positions: dict[str, Any]) -> EngineState:
    joined = [" ".join(c).replace("\\", "/") for c in cmdlines]
    return EngineState(
        main_running=any("trading_bot/main.py" in c for c in joined),
        observer_running=any("paper_observer.py" in c for c in joined),
        live_mode=bool(settings.get("live_trading_mode", False)),
        positions=len(positions or {}),
    )


def _read_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def current_engine_state() -> EngineState:
    import psutil
    cmdlines: list[list[str]] = []
    for p in psutil.process_iter(["cmdline"]):
        try:
            cmdlines.append(list(p.info.get("cmdline") or []))
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return engine_state(cmdlines, _read_json(ROOT / "config" / "settings.json"),
                        _read_json(ROOT / "config" / "active_positions.json"))


def classify_error(resp: dict[str, Any]) -> str:
    """'token' and 'rate_limit' are hard stops; anything else may be retried."""
    msg = str(resp.get("message", "")).lower()
    code = resp.get("code")
    if code == 429 or "429" in msg or "limit" in msg or "too many" in msg:
        return "rate_limit"
    if code in (-8, -15, -16, -17) or any(w in msg for w in ("token", "expired", "unauthor",
                                                             "authenticat", "invalid app")):
        return "token"
    return "other"


def futures_symbols(today: date) -> list[str]:
    """This month's and next month's NIFTY futures symbols, in Fyers format."""
    out = []
    for k in (0, 1):
        y, m = today.year + (today.month - 1 + k) // 12, (today.month - 1 + k) % 12 + 1
        out.append(f"NSE:NIFTY{y % 100:02d}{MONTHS[m - 1]}FUT")
    return out


def previous_month_symbol(today: date) -> str:
    y, m = (today.year, today.month - 1) if today.month > 1 else (today.year - 1, 12)
    return f"NSE:NIFTY{y % 100:02d}{MONTHS[m - 1]}FUT"


# ---------------------------------------------------------------- fetch

def call(history: History, req: dict[str, Any], pause_s: float) -> dict[str, Any]:
    """One request with the owner's stop rules: up to ``ATTEMPTS`` tries for an
    ordinary error, an immediate :class:`StopFetch` on a token or rate-limit
    error."""
    resp: dict[str, Any] = {}
    for attempt in range(ATTEMPTS):
        resp = history(req)
        if pause_s:
            _time.sleep(pause_s)
        if resp.get("s") in ("ok", "no_data"):
            return resp
        kind = classify_error(resp)
        if kind != "other":
            raise StopFetch(f"{kind}: {resp.get('message', resp)} (request {req})")
        if pause_s:
            _time.sleep(pause_s * (attempt + 1))
    return resp


def fetch_resolution(history: History, symbol: str, resolution: str, start: date, end: date,
                     pause_s: float = PAUSE_S) -> tuple[pd.DataFrame, list[str]]:
    """All bars for one resolution in ``CHUNK_DAYS`` chunks. A chunk that keeps
    failing with an ordinary error is LOST and named in the notes."""
    rows: list[list[float]] = []
    notes: list[str] = []
    cur = start
    with_oi = True
    while cur <= end:
        stop = min(end, cur + timedelta(days=CHUNK_DAYS - 1))
        req = {"symbol": symbol, "resolution": resolution, "date_format": "1",
               "range_from": cur.isoformat(), "range_to": stop.isoformat(), "cont_flag": "1"}
        if with_oi:
            req["oi_flag"] = "1"
        resp = call(history, req, pause_s)
        if resp.get("s") not in ("ok", "no_data") and with_oi and "oi" in str(resp.get("message", "")).lower():
            with_oi = False
            notes.append(f"{resolution}: oi_flag rejected ({resp.get('message')}); fetched without OI")
            continue
        if resp.get("s") == "ok":
            rows.extend(resp.get("candles", []) or [])
        elif resp.get("s") != "no_data":
            notes.append(f"{resolution} {cur}..{stop}: LOST after {ATTEMPTS} attempts -- "
                         f"{resp.get('message', resp)}")
        cur = stop + timedelta(days=1)
    return to_frame(rows), notes


def to_frame(rows: Sequence[Sequence[float]]) -> pd.DataFrame:
    cols = ["epoch", "open", "high", "low", "close", "volume", "oi"]
    width = max((len(r) for r in rows), default=6)
    frame = pd.DataFrame([list(r) + [None] * (7 - len(r)) for r in rows], columns=cols)
    if width < 7:
        frame = frame.drop(columns=["oi"])
    if frame.empty:
        return frame.drop(columns=["epoch"]).assign(datetime=pd.Series(dtype="datetime64[ns]"))
    frame["datetime"] = (pd.to_datetime(frame["epoch"], unit="s", utc=True)
                         .dt.tz_convert(IST).dt.tz_localize(None))
    frame = frame.drop(columns=["epoch"])
    return frame[["datetime"] + [c for c in frame.columns if c != "datetime"]]


def find_first_year(history: History, symbol: str, resolution: str, first_year: int,
                    end: date, pause_s: float = PAUSE_S) -> Optional[int]:
    """The first year whose first or middle 30 days return any bar."""
    for y in range(first_year, end.year + 1):
        for month in (1, 7):
            a = date(y, month, 1)
            if a > end:
                return None
            req = {"symbol": symbol, "resolution": resolution, "date_format": "1",
                   "range_from": a.isoformat(),
                   "range_to": min(end, a + timedelta(days=CHUNK_DAYS - 1)).isoformat(),
                   "cont_flag": "1"}
            resp = call(history, req, pause_s)
            if resp.get("s") == "ok" and resp.get("candles"):
                return y
    return None


# ---------------------------------------------------------------- quality

@dataclass
class QualityReport:
    resolution_minutes: int
    bars: int = 0
    first: Optional[str] = None
    last: Optional[str] = None
    sessions: int = 0
    expected_bars_per_session: int = 0
    full_sessions: int = 0
    short_sessions: int = 0
    missing_bars: int = 0
    duplicate_timestamps: int = 0
    outside_session_bars: int = 0
    zero_volume_bars: int = 0
    zero_volume_pct: float = 0.0
    oi_present: bool = False
    oi_zero_or_missing_pct: Optional[float] = None
    largest_open_gaps: list[dict[str, Any]] = field(default_factory=list)
    sha256: Optional[str] = None


def expected_bars(minutes: int) -> int:
    """Bars in a full 09:15-15:30 session (the last bar may be partial)."""
    span = (SESSION_CLOSE.hour * 60 + SESSION_CLOSE.minute) - (SESSION_OPEN.hour * 60 + SESSION_OPEN.minute)
    return -(-span // minutes)


def session_gaps(frame: pd.DataFrame) -> pd.Series:
    """Percent gap of each session's first open over the previous session's last close."""
    df = frame.sort_values("datetime").drop_duplicates("datetime")
    days = df.groupby(df["datetime"].dt.date).agg(first_open=("open", "first"),
                                                  last_close=("close", "last"))
    return ((days["first_open"] / days["last_close"].shift(1) - 1.0) * 100.0).dropna()


def quality_report(frame: pd.DataFrame, minutes: int) -> QualityReport:
    q = QualityReport(resolution_minutes=minutes, expected_bars_per_session=expected_bars(minutes))
    if frame.empty:
        return q
    df = frame.sort_values("datetime")
    q.duplicate_timestamps = int(df["datetime"].duplicated().sum())
    df = df.drop_duplicates("datetime")
    q.bars = len(df)
    q.first, q.last = str(df["datetime"].iloc[0]), str(df["datetime"].iloc[-1])
    t = df["datetime"].dt.time
    q.outside_session_bars = int(((t < SESSION_OPEN) | (t >= SESSION_CLOSE)).sum())
    per_day = df.groupby(df["datetime"].dt.date).size()
    q.sessions = int(len(per_day))
    q.full_sessions = int((per_day >= q.expected_bars_per_session).sum())
    q.short_sessions = q.sessions - q.full_sessions
    q.missing_bars = int((q.expected_bars_per_session - per_day).clip(lower=0).sum())
    q.zero_volume_bars = int((df["volume"] <= 0).sum())
    q.zero_volume_pct = round(100.0 * q.zero_volume_bars / q.bars, 3)
    if "oi" in df.columns:
        q.oi_present = True
        q.oi_zero_or_missing_pct = round(
            100.0 * float(((df["oi"].isna()) | (df["oi"] <= 0)).sum()) / q.bars, 3)
    gaps = session_gaps(df)
    top = gaps.abs().sort_values(ascending=False).head(10)
    q.largest_open_gaps = [{"date": str(d), "gap_pct": round(float(gaps[d]), 3)} for d in top.index]
    return q


# ---------------------------------------------------------------- rolls

def last_weekday_of_month(y: int, m: int, weekday: int) -> date:
    d = date(y + (m == 12), m % 12 + 1, 1) - timedelta(days=1)
    while d.weekday() != weekday:
        d -= timedelta(days=1)
    return d


def roll_gap_summary(gaps: pd.Series) -> dict[str, Any]:
    """Compare session-open gaps on the first session after each month's last
    Thursday and last Tuesday (the two NIFTY monthly expiry weekdays seen in
    recent years) with all other sessions. An unadjusted continuous series
    shows the roll as a larger |gap| on one of those days."""
    if gaps.empty:
        return {}
    days = sorted(gaps.index)
    after: dict[str, set[date]] = {"thu": set(), "tue": set()}
    for y, m in sorted({(d.year, d.month) for d in days}):
        for key, wd in (("thu", 3), ("tue", 1)):
            exp = last_weekday_of_month(y, m, wd)
            nxt = next((d for d in days if d > exp), None)
            if nxt is not None:
                after[key].add(nxt)
    out: dict[str, Any] = {"all_sessions_median_abs_gap_pct": round(float(gaps.abs().median()), 3)}
    for key, sel in after.items():
        g = gaps[[d in sel for d in gaps.index]].abs()
        out[f"after_last_{key}_n"] = int(len(g))
        out[f"after_last_{key}_median_abs_gap_pct"] = round(float(g.median()), 3) if len(g) else None
    return out


def compare_series(a: pd.DataFrame, b: pd.DataFrame) -> dict[str, Any]:
    """Overlap of two bar series on timestamp: how often their closes differ."""
    m = a.merge(b, on="datetime", suffixes=("_a", "_b"))
    if m.empty:
        return {"overlap_bars": 0}
    diff = (m["close_a"] - m["close_b"]).abs()
    return {"overlap_bars": int(len(m)), "max_abs_close_diff": float(diff.max()),
            "bars_with_diff": int((diff > 1e-9).sum()),
            "first": str(m["datetime"].iloc[0]), "last": str(m["datetime"].iloc[-1])}


# ---------------------------------------------------------------- output

def write_csv(frame: pd.DataFrame, path: Path) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    frame.to_csv(tmp, index=False)
    tmp.replace(path)
    return hashlib.sha256(path.read_bytes()).hexdigest()


def report_markdown(symbol: str, start: date, end: date, reports: Sequence[QualityReport],
                    notes: Sequence[str], generated: datetime,
                    rolls: Optional[dict[str, Any]] = None) -> str:
    lines = [
        "# smc1 -- NIFTY continuous futures: data quality report",
        "",
        f"Generated {generated:%Y-%m-%d %H:%M} IST by `scripts/smc1_fetch_futures_history.py` "
        f"(read-only, cached token, no login). Symbol `{symbol}`, `cont_flag=1`, "
        f"requested {start} .. {end}.",
        "",
        "| TF | bars | first (earliest available) | last | sessions | full / short | missing bars | "
        "dup | outside session | zero-vol % | OI missing % | SHA-256 (12) |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for q in reports:
        lines.append(
            f"| {q.resolution_minutes}m | {q.bars:,} | {q.first} | {q.last} | {q.sessions} | "
            f"{q.full_sessions} / {q.short_sessions} | {q.missing_bars:,} | {q.duplicate_timestamps} | "
            f"{q.outside_session_bars} | {q.zero_volume_pct} | "
            f"{'n/a' if q.oi_zero_or_missing_pct is None else q.oi_zero_or_missing_pct} | "
            f"`{(q.sha256 or '')[:12]}` |")
    lines += ["", "Largest session-open gaps:", ""]
    for q in reports:
        if q.largest_open_gaps:
            gaps = ", ".join(f"{g['date']} {g['gap_pct']:+.2f}%" for g in q.largest_open_gaps[:5])
            lines.append(f"* {q.resolution_minutes}m: {gaps}")
    if rolls:
        lines += ["", "Roll analysis:", "", "```", json.dumps(rolls, indent=1, default=str), "```"]
    if notes:
        lines += ["", "Notes from the API:", ""] + [f"* {n}" for n in notes]
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------- main

def _history_client() -> History:
    from brokers.credentials import load_credentials
    from brokers.token_cache import load_token
    token = load_token("fyers")
    if not token:
        raise StopFetch("token: no cached Fyers token")
    client_id = load_credentials("fyers").get("client_id", "")
    from fyers_apiv3 import fyersModel
    model = fyersModel.FyersModel(client_id=client_id, token=token, is_async=False,
                                  log_path=str(OUT_DIR))
    return model.history  # type: ignore[no-any-return]


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
    ap.add_argument("--first-year", type=int, default=2015, help="earliest year to probe")
    ap.add_argument("--end", default=None)
    ap.add_argument("--resolutions", default="1,5,15,60")
    ap.add_argument("--symbol", default=None, help="override the futures symbol")
    ap.add_argument("--dry-run", action="store_true", help="check every guard, print the plan, call nothing")
    args = ap.parse_args(argv)

    from shared.market_calendar import is_trading_day
    now = datetime.now(IST).replace(tzinfo=None)
    reason = fetch_window_reason(now, is_trading_day)
    if reason:
        print(f"REFUSED: {reason}")
        return 2
    state = current_engine_state()
    print(f"engine: {asdict(state)}")
    refusal = state.refusal()
    if refusal:
        print(f"REFUSED: {refusal}")
        return 2
    from brokers.token_cache import load_token
    if not load_token("fyers"):
        print("STOP: no cached Fyers token. Fetching would need a login, which the owner's "
              "rule forbids. Nothing fetched.")
        return 2
    end = date.fromisoformat(args.end) if args.end else now.date()
    res = [r.strip() for r in args.resolutions.split(",") if r.strip()]
    if any(r not in RESOLUTIONS for r in res):
        print(f"unknown resolution in {res}")
        return 2
    symbols = [args.symbol] if args.symbol else futures_symbols(now.date())
    print(f"plan: {symbols} {res} probe from {args.first_year} to {end} -> {OUT_DIR}")
    if args.dry_run:
        return 0

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    notes: list[str] = []
    reports: list[QualityReport] = []
    rolls: dict[str, Any] = {}
    frames: dict[str, pd.DataFrame] = {}
    symbol: Optional[str] = None
    try:
        history = _history_client()
        for s in symbols:
            probe = call(history, {"symbol": s, "resolution": "D", "date_format": "1",
                                   "range_from": (end - timedelta(days=10)).isoformat(),
                                   "range_to": end.isoformat(), "cont_flag": "1"}, PAUSE_S)
            if probe.get("s") == "ok" and probe.get("candles"):
                symbol = s
                break
        if symbol is None:
            print(f"STOP: none of {symbols} returned data; check the symbol format.")
            return 2
        for r in res:
            year = find_first_year(history, symbol, r, args.first_year, end)
            if year is None:
                notes.append(f"{r}: no data found from {args.first_year}")
                reports.append(QualityReport(resolution_minutes=RESOLUTIONS[r]))
                continue
            if year > args.first_year:
                start = date(year - 1, 7, 1)
            else:
                start = date(args.first_year, 1, 1)
                notes.append(f"{r}: data exists at the first probed year {args.first_year}; "
                             f"the true earliest date may be older")
            frame, n = fetch_resolution(history, symbol, r, start, end)
            notes += n
            q = quality_report(frame, RESOLUTIONS[r])
            if not frame.empty:
                q.sha256 = write_csv(frame, OUT_DIR / f"NSE_NIFTY_FUT_CONT_{RESOLUTIONS[r]}m.csv")
                frames[r] = frame
            reports.append(q)
            print(f"{r:>3}: {q.bars:,} bars {q.first} .. {q.last}")

        # Rolls: what the continuous series is, and whether expired contracts exist.
        base = frames.get("15") if "15" in frames else next(iter(frames.values()), None)
        if base is not None:
            rolls["open_gaps"] = roll_gap_summary(session_gaps(base))
        recent_from = end - timedelta(days=25)
        own, _ = fetch_resolution(
            lambda q: history({k: v for k, v in q.items() if k not in ("cont_flag", "oi_flag")}),
            symbol, "15", recent_from, end)
        if base is not None and not own.empty:
            rolls["continuous_vs_current_contract_15m"] = compare_series(
                base[base["datetime"] >= pd.Timestamp(recent_from)], own)
        prev = previous_month_symbol(end)
        expired = call(history, {"symbol": prev, "resolution": "15", "date_format": "1",
                                 "range_from": (end - timedelta(days=45)).isoformat(),
                                 "range_to": end.isoformat()}, PAUSE_S)
        rolls["expired_contract_probe"] = {
            "symbol": prev, "status": expired.get("s"),
            "bars": len(expired.get("candles", []) or []),
            "message": expired.get("message")}
    except StopFetch as exc:
        print(f"STOP: {exc}")
        notes.append(f"STOPPED: {exc}")
        (OUT_DIR / "STOPPED.txt").write_text(f"{datetime.now(IST)}: {exc}\n", encoding="utf-8")
        return 3
    finally:
        generated = datetime.now(IST).replace(tzinfo=None)
        if reports or notes:
            (OUT_DIR / "quality_report.json").write_text(
                json.dumps({"symbol": symbol, "end": str(end), "generated": str(generated),
                            "notes": notes, "rolls": rolls,
                            "reports": [asdict(q) for q in reports]}, indent=1, default=str),
                encoding="utf-8")
            (OUT_DIR / "DATA_REPORT.md").write_text(
                report_markdown(symbol or "?", date(args.first_year, 1, 1), end, reports, notes,
                                generated, rolls), encoding="utf-8")
    print(f"report: {OUT_DIR / 'DATA_REPORT.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
