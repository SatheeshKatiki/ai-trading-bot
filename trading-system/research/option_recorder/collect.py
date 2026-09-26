"""Observed-option-data collector. RESEARCH ONLY -- observes, never trades.

    python -m research.option_recorder.collect --instruments NIFTY BANKNIFTY \
        --interval 300 --dry-run

What it does
------------
Every `--interval` seconds during market hours it takes ONE aligned snapshot
per instrument:

1. the real option chain (`/api/option-chain`, which serves the broker's
   `options-chain-v3` when a session exists),
2. the underlying's recent candles (`/api/history`),
3. the frozen prior-day-extreme signal state computed from (2),

and appends all three to the append-only research store, so a future
researcher can reconstruct exactly what was knowable at that moment.

What it deliberately does NOT do
--------------------------------
* It places no order, paper or real, and imports no execution code.
* It is not wired into `auto_daily_session.py` and nothing starts it
  automatically. It is run by hand.
* It never writes to `state.db`, `config/active_positions.json`, the dashboard
  equity, or any production path.
* It never substitutes a modelled premium for a missing observation. A chain
  that comes back `synthetic: true` is stored and classified SYNTHETIC so the
  gap is visible, and is never counted as evidence.

Why HTTP rather than the broker SDK
-----------------------------------
`api_bridge` already owns the authenticated Fyers session, the rate limiting
and the chain normalisation. Opening a second broker session from a research
tool would contend with the live one for the same token and rate limit. This
reads the same endpoint the dashboard reads.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import logging
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from research.option_recorder.schema import (  # noqa: E402
    DEFAULT_STALE_SECONDS,
    DEFAULT_UNCHANGED_STALE_SECONDS,
    OptionQuote,
    Quality,
    SignalEvent,
    UnderlyingSnapshot,
    classify_quote,
)
from research.option_recorder.store import ResearchStore  # noqa: E402

logger = logging.getLogger("option_recorder")

API_BASE = "http://127.0.0.1:8000"

#: The FROZEN signal definition (Phase 10). Phase 12 must not change it.
BAND_ATR = 0.25
ATR_WINDOW = 14

#: Underlying symbols the chain endpoint understands, per instrument.
UNDERLYING_SYMBOL = {
    "NIFTY": "NSE:NIFTY50-INDEX",
    "BANKNIFTY": "NSE:NIFTYBANK-INDEX",
    "FINNIFTY": "NSE:FINNIFTY-INDEX",
    "SENSEX": "BSE:SENSEX-INDEX",
}

IST = dt.timezone(dt.timedelta(hours=5, minutes=30))


def _now() -> dt.datetime:
    """Current IST time, as a single seam.

    Every timestamp the recorder writes comes through here. It exists so the
    offline rehearsal and the tests can drive a whole session's worth of time
    without sleeping through it -- staleness, day rolls and snapshot spacing
    are all clock-dependent, and none of them can be tested honestly against
    a clock that cannot move.
    """
    return dt.datetime.now(IST)


# ---------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------

#: Transient-failure policy (Phase 13 sec17). A dropped request during
#: market hours is a permanent hole in the record -- the moment does not come
#: back -- so a snapshot is retried briefly before it is given up on. The
#: backoff stays well inside one 5-minute interval so a retry can never push
#: a snapshot into the next bar and mislabel it.
MAX_ATTEMPTS = 3
RETRY_BACKOFF_SECONDS = (1.0, 3.0)


def _get(path: str, timeout: float = 20.0, *,
         attempts: int = MAX_ATTEMPTS,
         sleep=time.sleep) -> Optional[Any]:
    """GET with bounded retries. Returns None only after every attempt failed.

    Failures are logged at WARNING per attempt and ERROR on final give-up, so
    a session with holes says so in its own log rather than looking complete.
    """
    url = f"{API_BASE}{path}"
    last = None
    for attempt in range(1, max(1, attempts) + 1):
        try:
            with urllib.request.urlopen(url, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError,
                json.JSONDecodeError, ConnectionError, OSError) as exc:
            last = exc
            if attempt < attempts:
                delay = RETRY_BACKOFF_SECONDS[min(attempt - 1,
                                                  len(RETRY_BACKOFF_SECONDS) - 1)]
                logger.warning("GET %s failed (attempt %d/%d): %s; retrying in %.0fs",
                               path, attempt, attempts, exc, delay)
                sleep(delay)
            else:
                logger.error("GET %s failed after %d attempts: %s",
                             path, attempts, exc)
    _ = last
    return None


def fetch_chain(instrument: str) -> Optional[Dict[str, Any]]:
    sym = UNDERLYING_SYMBOL.get(instrument, instrument)
    return _get(f"/api/option-chain?symbol={urllib.parse.quote(sym)}")


def fetch_history(instrument: str, days: int = 6,
                  timeframe: str = "5 Min") -> Optional[pd.DataFrame]:
    sym = UNDERLYING_SYMBOL.get(instrument, instrument)
    end = dt.datetime.now(IST).date()
    start = end - dt.timedelta(days=days)
    q = urllib.parse.urlencode({
        "symbol": sym, "start_date": str(start), "end_date": str(end),
        "timeframe": timeframe,
    })
    res = _get(f"/api/history?{q}")
    if not res or "data" not in res or not res["data"]:
        return None
    df = pd.DataFrame(res["data"])
    if "datetime" not in df.columns:
        return None
    df["datetime"] = pd.to_datetime(df["datetime"])
    df = df.set_index("datetime").sort_index()
    for c in ("open", "high", "low", "close", "volume"):
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    return df.dropna(subset=["close"])


# ---------------------------------------------------------------------
# Frozen signal state
# ---------------------------------------------------------------------

def signal_state(df: pd.DataFrame) -> Optional[Dict[str, Any]]:
    """The frozen prior-day-extreme state on the LAST CLOSED bar.

    Reuses the same `compute_daily_levels` and `atr` the research scripts use,
    so there is exactly one definition of the rule in this repository.
    """
    if df is None or len(df) < ATR_WINDOW + 2:
        return None
    from shared.indicators import atr as _atr
    from trading_bot.strategies.rsi_smc_options_buyer import levels as L

    # Drop the still-forming bar: the rule reads a CLOSE.
    closed = df.iloc[:-1] if len(df) > 1 else df
    if len(closed) < ATR_WINDOW + 2:
        return None

    d = L.compute_daily_levels(closed)
    a = _atr(closed, ATR_WINDOW).to_numpy(dtype=float)
    i = len(closed) - 1
    pdh = float(d.prev_day_high[i]) if np.isfinite(d.prev_day_high[i]) else float("nan")
    pdl = float(d.prev_day_low[i]) if np.isfinite(d.prev_day_low[i]) else float("nan")
    close = float(closed["close"].to_numpy(dtype=float)[i])
    atr = float(a[i])
    tol = BAND_ATR * atr

    near_low = np.isfinite(pdl) and abs(close - pdl) <= tol
    near_high = np.isfinite(pdh) and abs(close - pdh) <= tol
    if near_low and not near_high:
        direction, level = 1, pdl
    elif near_high and not near_low:
        direction, level = -1, pdh
    else:
        direction, level = 0, float("nan")

    return dict(bar_time=closed.index[i], close=close, atr=atr,
                pdh=pdh, pdl=pdl, direction=direction, level=level,
                distance=(abs(close - level) if np.isfinite(level) else float("nan")),
                in_band=bool(direction != 0),
                bar=dict(open=float(closed["open"].to_numpy(float)[i]),
                         high=float(closed["high"].to_numpy(float)[i]),
                         low=float(closed["low"].to_numpy(float)[i]),
                         close=close))


# ---------------------------------------------------------------------
# Per-instrument session state (sec6, sec7, sec15, sec21)
# ---------------------------------------------------------------------

class InstrumentState:
    """What the collector must remember between snapshots of one instrument.

    It is keyed by session date and RESET when the date rolls (sec15). Nothing
    here is allowed to leak across a day boundary: a quote unchanged since
    yesterday is not a stale quote today, it is a different session.
    """

    def __init__(self, instrument: str, session_date: str):
        self.instrument = instrument
        self.session_date = session_date
        self.seen_keys: set = set()
        #: contract -> (fingerprint, first ISO time we saw that fingerprint)
        self.fingerprints: Dict[str, Tuple[str, dt.datetime]] = {}
        self.snapshots = 0
        self.written = 0
        self.skipped = 0
        self.failures = 0
        # -- Phase 14 sec7 persistence / integrity counters -------------
        self.storage_errors = 0
        self.reconnects = 0        # recoveries after a failed fetch
        self.restarts = 0          # process starts that found a checkpoint
        self.future_bars_refused = 0
        self.synthetic_snapshots = 0
        self.thin_chains = 0
        self.first_snapshot_at: Optional[str] = None
        self.last_snapshot_at: Optional[str] = None
        self._last_failed = False

    def roll_if_needed(self, session_date: str) -> bool:
        if session_date == self.session_date:
            return False
        self.__init__(self.instrument, session_date)
        return True

    def as_checkpoint(self) -> Dict[str, Any]:
        """Everything the session report needs that only the running process
        knows. Outages, restarts and storage errors leave no trace in the data
        itself, so a report rebuilt from files alone could not see them."""
        return {
            "snapshots": self.snapshots, "written": self.written,
            "skipped": self.skipped, "failures": self.failures,
            "storage_errors": self.storage_errors,
            "reconnects": self.reconnects, "restarts": self.restarts,
            "future_bars_refused": self.future_bars_refused,
            "synthetic_snapshots": self.synthetic_snapshots,
            "thin_chains": self.thin_chains,
            "first_snapshot_at": self.first_snapshot_at,
            "last_snapshot_at": self.last_snapshot_at,
        }


def _contract_key(instrument: str, symbol: str, expiry: str,
                  strike: float, side: str) -> str:
    return f"{instrument}|{symbol}|{expiry}|{float(strike):.2f}|{side}"


def extract_vix(chain: Dict[str, Any]) -> Tuple[Optional[float], Optional[float]]:
    """India VIX from the chain payload (Phase 14 sec3).

    ``api_bridge`` serves this from the broker's ``indiavixData`` and sets it
    to ``None`` when the broker sends nothing. Absent stays absent: carrying
    the last reading forward would silently rewrite the volatility regime a
    later study attributes its result to.
    """
    v = chain.get("indiaVix")
    if not isinstance(v, dict):
        return None, None
    try:
        value = float(v.get("value"))
    except (TypeError, ValueError):
        return None, None
    if value <= 0:
        return None, None
    try:
        chp = float(v.get("chp"))
    except (TypeError, ValueError):
        chp = None
    return value, chp


def chain_coverage(chain: Dict[str, Any]) -> Dict[str, Any]:
    """Structural coverage of one chain payload (Phase 13 sec10).

    A chain that silently returns three strikes is not a chain, and a dataset
    that records it without complaint will look complete months later. This
    reports what arrived; the caller decides whether it is enough.
    """
    rows = chain.get("chain") or []
    spot = float(chain.get("underlying_price") or 0.0)
    strikes = sorted({float(r.get("strike") or 0.0) for r in rows
                      if float(r.get("strike") or 0.0) > 0})
    both = sum(1 for r in rows if (r.get("ce") and r.get("pe")))
    atm = min(strikes, key=lambda k: abs(k - spot)) if strikes and spot > 0 else None
    return {
        "strikes": len(strikes),
        "rows": len(rows),
        "rows_with_both_sides": both,
        "strikes_below_spot": sum(1 for k in strikes if spot > 0 and k < spot),
        "strikes_above_spot": sum(1 for k in strikes if spot > 0 and k > spot),
        "atm_strike": atm,
        "atm_present": atm is not None,
        "spot": spot,
    }


#: Minimum structural coverage for a snapshot to count as COMPLETE.
MIN_STRIKES = 10
MIN_EACH_SIDE = 3


def coverage_ok(cov: Dict[str, Any]) -> Tuple[bool, List[str]]:
    problems = []
    if cov["strikes"] < MIN_STRIKES:
        problems.append(f"only {cov['strikes']} strikes (< {MIN_STRIKES})")
    if cov["strikes_below_spot"] < MIN_EACH_SIDE:
        problems.append(f"only {cov['strikes_below_spot']} strikes below spot")
    if cov["strikes_above_spot"] < MIN_EACH_SIDE:
        problems.append(f"only {cov['strikes_above_spot']} strikes above spot")
    if not cov["atm_present"]:
        problems.append("no ATM strike")
    if cov["spot"] <= 0:
        problems.append("no underlying price")
    return (not problems), problems


# ---------------------------------------------------------------------
# Normalisation
# ---------------------------------------------------------------------

def _expiry_class(expiry: dt.date) -> str:
    """WEEKLY unless it is the last such weekday of its month."""
    nxt = expiry + dt.timedelta(days=7)
    return "MONTHLY" if nxt.month != expiry.month else "WEEKLY"


def normalise_chain(instrument: str, chain: Dict[str, Any], *,
                    retrieved_at: dt.datetime,
                    stale_seconds: float = DEFAULT_STALE_SECONDS,
                    state: Optional["InstrumentState"] = None,
                    unchanged_stale_seconds: float = DEFAULT_UNCHANGED_STALE_SECONDS
                    ) -> Tuple[List[OptionQuote], Dict[str, int]]:
    """Broker chain payload -> OptionQuote records, with quality applied.

    The ENTIRE chain is kept (Phase 12 sec7, sec13): every strike and both
    sides, whether or not the frozen signal would have traded. Storing only
    the contract a later backtest likes is the selection bias this exists to
    avoid.
    """
    out: List[OptionQuote] = []
    counts = {q.value: 0 for q in Quality}

    is_synth = bool(chain.get("synthetic", False))
    spot = float(chain.get("underlying_price") or 0.0)
    expiry_str = (chain.get("expiry") or "")[:10]
    try:
        expiry = dt.date.fromisoformat(expiry_str)
    except ValueError:
        expiry = None

    now_ist = retrieved_at.astimezone(IST)
    session_date = now_ist.date().isoformat()
    ev = now_ist.isoformat(timespec="seconds")
    ev_utc = retrieved_at.astimezone(dt.timezone.utc).isoformat(timespec="seconds")
    dte = (expiry - now_ist.date()).days if expiry else None

    for row in (chain.get("chain") or []):
        strike = float(row.get("strike") or 0.0)
        if strike <= 0:
            continue
        for side in ("ce", "pe"):
            leg = row.get(side) or {}
            if not leg:
                continue
            bid = float(leg.get("bid") or 0.0)
            ask = float(leg.get("ask") or 0.0)
            ltp = float(leg.get("ltp") or 0.0)
            symbol = str(leg.get("symbol") or "")
            volume = int(leg.get("volume") or 0)
            oi = int(leg.get("oi") or 0)

            # Staleness (sec7). The broker sends no quote timestamp, so
            # age_seconds stays None -- inventing one would be exactly the
            # modelled-over-observed substitution this schema forbids. What
            # we CAN measure is how long this contract has been quoting the
            # identical numbers across our own snapshots.
            unchanged_for = None
            if state is not None:
                ck = _contract_key(instrument, symbol,
                                   expiry.isoformat() if expiry else "",
                                   strike, side.upper())
                fp = f"{ltp}|{bid}|{ask}|{volume}|{oi}"
                prev = state.fingerprints.get(ck)
                if prev is not None and prev[0] == fp:
                    unchanged_for = (now_ist - prev[1]).total_seconds()
                else:
                    state.fingerprints[ck] = (fp, now_ist)

            quality, reasons = classify_quote(
                bid, ask, ltp, age_seconds=None, is_synthetic=is_synth,
                stale_seconds=stale_seconds,
                unchanged_for_seconds=unchanged_for,
                unchanged_stale_seconds=unchanged_stale_seconds)
            counts[quality.value] += 1
            out.append(OptionQuote(
                event_time=ev, event_time_utc=ev_utc, session_date=session_date,
                available_at=ev, underlying=instrument,
                option_symbol=symbol,
                expiry=expiry.isoformat() if expiry else "",
                strike=strike, option_type=side.upper(),
                underlying_price=spot, last_price=ltp, bid=bid, ask=ask,
                volume=volume,
                open_interest=oi,
                oi_change=int(leg.get("oichg") or 0),
                implied_volatility=leg.get("iv"),
                delta=leg.get("delta"), gamma=leg.get("gamma"),
                theta=leg.get("theta"), vega=leg.get("vega"),
                dte=dte,
                expiry_class=_expiry_class(expiry) if expiry else None,
                source=str(chain.get("priceSource") or "unknown"),
                retrieved_at=ev,
                original_symbol=UNDERLYING_SYMBOL.get(instrument, instrument),
                quote_age_seconds=None,
                unchanged_for_seconds=unchanged_for,
                quality=quality.value, quality_reasons=tuple(reasons),
            ))
    return out, counts


# ---------------------------------------------------------------------
# One snapshot
# ---------------------------------------------------------------------

def snapshot(store: ResearchStore, instrument: str, *,
             dry_run: bool = False,
             state: Optional[InstrumentState] = None) -> Dict[str, Any]:
    """One aligned observation of one instrument.

    Every write goes through the deduplicating path, so calling this twice
    for the same instant stores the instant once. The returned dict is the
    per-snapshot health record the loop logs and checkpoints.
    """
    retrieved = _now()
    session_date = retrieved.date().isoformat()
    if state is not None and state.roll_if_needed(session_date):
        # sec15. A new session starts with no memory of the last one.
        logger.info("%s: session rolled to %s; state reset",
                    instrument, session_date)

    result = {"instrument": instrument, "session_date": session_date,
              "quotes": 0, "written": 0, "skipped": 0, "quality": {},
              "signal": None, "coverage": None, "coverage_ok": None,
              "ok": False}

    chain = fetch_chain(instrument)
    if chain is None:
        result["error"] = "chain unavailable"
        if state is not None:
            state.failures += 1
            state._last_failed = True
        return result
    if state is not None and state._last_failed:
        # Recovered. Counted so the session report can show that an outage
        # happened and was survived, which a file-only report cannot see.
        state.reconnects += 1
        state._last_failed = False
    if chain.get("synthetic"):
        # Recorded anyway, so the gap is visible in the completeness report --
        # but it can never count as evidence.
        logger.warning("%s: chain came back SYNTHETIC (no broker session); "
                       "recording as SYNTHETIC, not usable for validation.",
                       instrument)
        if state is not None:
            state.synthetic_snapshots += 1

    cov = chain_coverage(chain)
    ok_cov, cov_problems = coverage_ok(cov)
    result["coverage"] = cov
    result["coverage_ok"] = ok_cov
    if not ok_cov:
        # NOT a reason to discard the snapshot: a thin chain is itself an
        # observation, and dropping it would hide the thinness. It is a
        # reason to mark it, so the daily report can see it (sec10).
        logger.warning("%s: thin chain -- %s", instrument, "; ".join(cov_problems))
        result["coverage_problems"] = cov_problems
        if state is not None:
            state.thin_chains += 1

    hist = fetch_history(instrument)
    if hist is None:
        logger.warning("%s: underlying history unavailable; chain still "
                       "recorded, signal state skipped", instrument)
    state_sig = signal_state(hist) if hist is not None else None

    vix, vix_chp = extract_vix(chain)
    result["india_vix"] = vix

    quotes, counts = normalise_chain(instrument, chain, retrieved_at=retrieved,
                                     state=state)
    result["quotes"] = len(quotes)
    result["quality"] = counts

    if dry_run:
        result["ok"] = True
        result["signal"] = None if not state_sig else {
            "direction": state_sig["direction"], "in_band": state_sig["in_band"],
            "distance": state_sig["distance"], "atr": state_sig["atr"]}
        return result

    ev = retrieved.isoformat(timespec="seconds")
    try:
        store.append_raw(instrument, session_date, chain,
                         endpoint="/api/option-chain", retrieved_at=ev)
    except OSError as exc:
        # A storage failure must be counted and surfaced, never swallowed: a
        # session that quietly wrote nothing would otherwise look thin rather
        # than broken.
        logger.error("%s: RAW write failed: %s", instrument, exc)
        if state is not None:
            state.storage_errors += 1
        result["error"] = f"storage failure: {exc}"
        return result

    seen = state.seen_keys if state is not None else None
    try:
        written, skipped, seen = store.append_deduped(
            "normalized", instrument, session_date, "quotes.jsonl", quotes, seen)
    except OSError as exc:
        logger.error("%s: normalized write failed: %s", instrument, exc)
        if state is not None:
            state.storage_errors += 1
        result["error"] = f"storage failure: {exc}"
        return result
    result["written"], result["skipped"] = written, skipped
    if state is not None:
        state.seen_keys = seen
        state.snapshots += 1
        state.written += written
        state.skipped += skipped
    if skipped:
        logger.info("%s: %d duplicate observations skipped", instrument, skipped)

    if state_sig is not None:
        # event_time is when the market state EXISTED -- the close of the last
        # completed bar. available_at is when this process could first have
        # known it, which is strictly later. Keeping them apart is what lets a
        # future backtest filter on availability (sec16); collapsing them would
        # quietly grant the researcher the bar's close at the bar's open.
        bar_time = pd.Timestamp(state_sig["bar_time"])
        if bar_time.tzinfo is None:
            bar_time = bar_time.tz_localize(IST)
        bar_ev = bar_time.isoformat(timespec="seconds")

        # A bar that closes AFTER the moment we fetched it cannot have been
        # observed. It means a timezone fault or a bad history payload, and
        # writing it would put a look-ahead-shaped row into the research data
        # -- available_at earlier than the event it describes. Refuse it and
        # say so; a visible gap is recoverable, a poisoned row is not.
        if bar_time > retrieved:
            logger.error("%s: history returned a bar at %s, after the "
                         "collection time %s -- refusing to record it",
                         instrument, bar_ev, ev)
            result["error"] = "future-dated bar refused"
            if state is not None:
                state.failures += 1
                state.future_bars_refused += 1
            return result

        store.append("derived", instrument, session_date, "underlying.jsonl", [
            UnderlyingSnapshot(
                event_time=bar_ev, session_date=session_date, available_at=ev,
                underlying=instrument, price=state_sig["close"],
                previous_day_high=state_sig["pdh"], previous_day_low=state_sig["pdl"],
                atr=state_sig["atr"], bar_open=state_sig["bar"]["open"],
                bar_high=state_sig["bar"]["high"], bar_low=state_sig["bar"]["low"],
                bar_close=state_sig["bar"]["close"],
                india_vix=vix, india_vix_change_pct=vix_chp)])

        if state_sig["in_band"]:
            # One setup per (session, instrument, direction) -- the Phase 10
            # DAY_SIDE identity, so repeated snapshots of one live setup share
            # an id and cannot later be counted as independent observations.
            setup_id = (f"{instrument}:{bar_time.date().isoformat()}:"
                        f"{'LONG' if state_sig['direction'] > 0 else 'SHORT'}")
            store.append("events", instrument, session_date, "signals.jsonl", [
                SignalEvent(
                    event_time=bar_ev, session_date=session_date, available_at=ev,
                    underlying=instrument, setup_id=setup_id,
                    direction=state_sig["direction"],
                    previous_day_high=state_sig["pdh"], previous_day_low=state_sig["pdl"],
                    level=state_sig["level"], distance_to_level=state_sig["distance"],
                    atr=state_sig["atr"], band_atr=BAND_ATR,
                    underlying_price=state_sig["close"],
                    signal_state="ENTRY_ELIGIBLE", in_band=True)])
            result["signal"] = setup_id

    if state is not None:
        if state.first_snapshot_at is None:
            state.first_snapshot_at = ev
        state.last_snapshot_at = ev
        cp = state.as_checkpoint()
        cp.update({"last_event_time": ev, "last_coverage": cov,
                   "last_coverage_ok": ok_cov})
        store.write_checkpoint(instrument, session_date, cp)

    result["ok"] = True
    return result


# ---------------------------------------------------------------------
# Loop
# ---------------------------------------------------------------------

def market_open(now: Optional[dt.datetime] = None) -> bool:
    now = now or _now()
    if now.weekday() >= 5:
        return False
    return dt.time(9, 15) <= now.time() <= dt.time(15, 30)


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--instruments", nargs="+",
                    default=["NIFTY", "BANKNIFTY", "SENSEX"],
                    help="FINNIFTY is intentionally NOT a default -- its "
                         "holdout is sealed (Phase 12 sec31).")
    ap.add_argument("--interval", type=float, default=300.0,
                    help="seconds between snapshots (default 300 = 5 min, "
                         "matching the frozen signal's bar size)")
    ap.add_argument("--root", default=None, help="research_data root")
    ap.add_argument("--dry-run", action="store_true",
                    help="fetch and classify, write nothing")
    ap.add_argument("--once", action="store_true", help="one snapshot, then exit")
    ap.add_argument("--ignore-market-hours", action="store_true")
    args = ap.parse_args(argv)

    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")
    store = ResearchStore(Path(args.root) if args.root else None)

    logger.info("option_recorder starting. RESEARCH ONLY -- no orders, ever.")
    logger.info("instruments=%s interval=%.0fs root=%s dry_run=%s",
                args.instruments, args.interval, store.root, args.dry_run)
    if "FINNIFTY" in args.instruments:
        logger.warning("FINNIFTY requested. Its Phase 9 holdout is SEALED; "
                       "newly collected data is separate from it, but keep "
                       "the two apart in any later analysis.")

    today = _now().date().isoformat()
    states = {inst: InstrumentState(inst, today) for inst in args.instruments}
    if not args.dry_run:
        # Resume (sec21). Restarting mid-session must not re-record the
        # morning: the keys already on disk are loaded back so the first
        # snapshot after a restart skips what is already there.
        for inst, st in states.items():
            st.seen_keys = store.load_keys(inst, today)
            cp = store.read_checkpoint(inst, today)
            if cp:
                for f in ("snapshots", "written", "skipped", "failures",
                          "storage_errors", "reconnects", "future_bars_refused",
                          "synthetic_snapshots", "thin_chains"):
                    setattr(st, f, int(cp.get(f) or 0))
                st.first_snapshot_at = cp.get("first_snapshot_at")
                st.restarts = int(cp.get("restarts") or 0) + 1
                logger.info("%s: resumed from checkpoint -- %d snapshots, "
                            "%d observations already on disk (restart #%d)",
                            inst, st.snapshots, len(st.seen_keys), st.restarts)
            elif st.seen_keys:
                logger.info("%s: %d observations already on disk for %s",
                            inst, len(st.seen_keys), today)

    seen_sessions = set()
    try:
        while True:
            if args.ignore_market_hours or market_open():
                for inst in args.instruments:
                    r = snapshot(store, inst, dry_run=args.dry_run,
                                 state=states.get(inst))
                    seen_sessions.add((inst, r["session_date"]))
                    logger.info("%s %s quotes=%d new=%d dup=%d quality=%s "
                                "strikes=%s signal=%s%s",
                                r["session_date"], inst, r["quotes"],
                                r.get("written", 0), r.get("skipped", 0),
                                {k: v for k, v in r.get("quality", {}).items() if v},
                                (r.get("coverage") or {}).get("strikes"),
                                r.get("signal"),
                                "" if r["ok"] else f" ERROR={r.get('error')}")
            else:
                logger.debug("market closed; idle")
            if args.once:
                break
            time.sleep(max(1.0, args.interval))
    except KeyboardInterrupt:
        logger.info("interrupted")
    finally:
        if not args.dry_run:
            for inst, sd in sorted(seen_sessions):
                m = store.write_manifest(inst, sd)
                logger.info("manifest %s %s: %d files", inst, sd, len(m["files"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
