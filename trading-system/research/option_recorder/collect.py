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


# ---------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------

def _get(path: str, timeout: float = 20.0) -> Optional[Any]:
    url = f"{API_BASE}{path}"
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError,
            json.JSONDecodeError, ConnectionError) as exc:
        logger.warning("GET %s failed: %s", path, exc)
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
# Normalisation
# ---------------------------------------------------------------------

def _expiry_class(expiry: dt.date) -> str:
    """WEEKLY unless it is the last such weekday of its month."""
    nxt = expiry + dt.timedelta(days=7)
    return "MONTHLY" if nxt.month != expiry.month else "WEEKLY"


def normalise_chain(instrument: str, chain: Dict[str, Any], *,
                    retrieved_at: dt.datetime,
                    stale_seconds: float = DEFAULT_STALE_SECONDS
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
            quality, reasons = classify_quote(
                bid, ask, ltp, age_seconds=None, is_synthetic=is_synth,
                stale_seconds=stale_seconds)
            counts[quality.value] += 1
            out.append(OptionQuote(
                event_time=ev, event_time_utc=ev_utc, session_date=session_date,
                available_at=ev, underlying=instrument,
                option_symbol=str(leg.get("symbol") or ""),
                expiry=expiry.isoformat() if expiry else "",
                strike=strike, option_type=side.upper(),
                underlying_price=spot, last_price=ltp, bid=bid, ask=ask,
                volume=int(leg.get("volume") or 0),
                open_interest=int(leg.get("oi") or 0),
                oi_change=int(leg.get("oichg") or 0),
                implied_volatility=leg.get("iv"),
                delta=leg.get("delta"), gamma=leg.get("gamma"),
                theta=leg.get("theta"), vega=leg.get("vega"),
                dte=dte,
                expiry_class=_expiry_class(expiry) if expiry else None,
                source=str(chain.get("priceSource") or "unknown"),
                retrieved_at=ev,
                original_symbol=UNDERLYING_SYMBOL.get(instrument, instrument),
                quality=quality.value, quality_reasons=tuple(reasons),
            ))
    return out, counts


# ---------------------------------------------------------------------
# One snapshot
# ---------------------------------------------------------------------

def snapshot(store: ResearchStore, instrument: str, *,
             dry_run: bool = False) -> Dict[str, Any]:
    retrieved = dt.datetime.now(IST)
    session_date = retrieved.date().isoformat()
    result = {"instrument": instrument, "session_date": session_date,
              "quotes": 0, "quality": {}, "signal": None, "ok": False}

    chain = fetch_chain(instrument)
    if chain is None:
        result["error"] = "chain unavailable"
        return result
    if chain.get("synthetic"):
        # Recorded anyway, so the gap is visible in the completeness report --
        # but it can never count as evidence.
        logger.warning("%s: chain came back SYNTHETIC (no broker session); "
                       "recording as SYNTHETIC, not usable for validation.",
                       instrument)

    hist = fetch_history(instrument)
    state = signal_state(hist) if hist is not None else None

    quotes, counts = normalise_chain(instrument, chain, retrieved_at=retrieved)
    result["quotes"] = len(quotes)
    result["quality"] = counts

    if dry_run:
        result["ok"] = True
        result["signal"] = None if not state else {
            "direction": state["direction"], "in_band": state["in_band"],
            "distance": state["distance"], "atr": state["atr"]}
        return result

    ev = retrieved.isoformat(timespec="seconds")
    store.append_raw(instrument, session_date, chain,
                     endpoint="/api/option-chain", retrieved_at=ev)
    store.append("normalized", instrument, session_date, "quotes.jsonl", quotes)

    if state is not None:
        # event_time is when the market state EXISTED -- the close of the last
        # completed bar. available_at is when this process could first have
        # known it, which is strictly later. Keeping them apart is what lets a
        # future backtest filter on availability (sec16); collapsing them would
        # quietly grant the researcher the bar's close at the bar's open.
        bar_time = pd.Timestamp(state["bar_time"])
        if bar_time.tzinfo is None:
            bar_time = bar_time.tz_localize(IST)
        bar_ev = bar_time.isoformat(timespec="seconds")

        store.append("derived", instrument, session_date, "underlying.jsonl", [
            UnderlyingSnapshot(
                event_time=bar_ev, session_date=session_date, available_at=ev,
                underlying=instrument, price=state["close"],
                previous_day_high=state["pdh"], previous_day_low=state["pdl"],
                atr=state["atr"], bar_open=state["bar"]["open"],
                bar_high=state["bar"]["high"], bar_low=state["bar"]["low"],
                bar_close=state["bar"]["close"])])

        if state["in_band"]:
            # One setup per (session, instrument, direction) -- the Phase 10
            # DAY_SIDE identity, so repeated snapshots of one live setup share
            # an id and cannot later be counted as independent observations.
            setup_id = (f"{instrument}:{bar_time.date().isoformat()}:"
                        f"{'LONG' if state['direction'] > 0 else 'SHORT'}")
            store.append("events", instrument, session_date, "signals.jsonl", [
                SignalEvent(
                    event_time=bar_ev, session_date=session_date, available_at=ev,
                    underlying=instrument, setup_id=setup_id,
                    direction=state["direction"],
                    previous_day_high=state["pdh"], previous_day_low=state["pdl"],
                    level=state["level"], distance_to_level=state["distance"],
                    atr=state["atr"], band_atr=BAND_ATR,
                    underlying_price=state["close"],
                    signal_state="ENTRY_ELIGIBLE", in_band=True)])
            result["signal"] = setup_id

    result["ok"] = True
    return result


# ---------------------------------------------------------------------
# Loop
# ---------------------------------------------------------------------

def market_open(now: Optional[dt.datetime] = None) -> bool:
    now = now or dt.datetime.now(IST)
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

    seen_sessions = set()
    try:
        while True:
            if args.ignore_market_hours or market_open():
                for inst in args.instruments:
                    r = snapshot(store, inst, dry_run=args.dry_run)
                    seen_sessions.add((inst, r["session_date"]))
                    logger.info("%s %s quotes=%d quality=%s signal=%s%s",
                                r["session_date"], inst, r["quotes"],
                                {k: v for k, v in r.get("quality", {}).items() if v},
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
