"""Market holidays from the exchange, not from a list someone remembered to edit.

The orchestrator carried a hardcoded `NSE_HOLIDAYS` table. On 2026-09-14 it was
missing Ganesh Chaturthi and a full session ran into a closed exchange. Checked
against NSE's own calendar on 2026-09-18 that table was wrong **seven** ways:

* missing three WEEKDAY holidays (2026-01-15 Maharashtra municipal election,
  2026-03-26 Ram Navami, 2026-03-31 Mahavir Jayanti) -- days the system would
  have tried to trade into a closed market;
* claiming four holidays the exchange does not have (2026-03-20, 2026-03-27,
  2026-09-04, 2026-11-09) -- real trading days the system would have sat out.

So the calendar is fetched from the exchange and cached. The hardcoded table
survives only as the fallback for a year that has never been fetched.

Two different questions, two different sources:

* *Will the market be open on date D?* -> the exchange's published calendar,
  which is what brokers republish. Fyers has no holiday endpoint.
* *Is the market open right now?* -> the broker's own `market_status()`. That
  is authoritative for today and catches an unscheduled closure a calendar
  cannot know about.
"""

from __future__ import annotations

import datetime
import json
import logging
import urllib.request
from pathlib import Path
from typing import Dict, Optional, Tuple

logger = logging.getLogger(__name__)

_ROOT = Path(__file__).resolve().parents[1]
#: Where the fetched calendar lives between runs.
CACHE_PATH = _ROOT / "config" / "market_holidays.json"
#: The exchange's own trading-holiday list.
NSE_HOLIDAY_URL = "https://www.nseindia.com/api/holiday-master?type=trading"
#: Segment preference: derivatives first (what this system trades), then cash.
_SEGMENT_ORDER = ("FO", "CM", "CD")
#: Refetch when the cache is older than this.
MAX_CACHE_AGE_DAYS = 7

#: Last-resort table, used only for a year the exchange was never fetched for.
#: Known to be imperfect -- that is the whole reason for the fetch above.
FALLBACK_HOLIDAYS: Dict[int, set] = {
    2026: {
        "2026-01-26", "2026-03-03", "2026-03-20", "2026-03-27", "2026-04-03",
        "2026-04-14", "2026-05-01", "2026-05-28", "2026-06-26", "2026-08-15",
        "2026-09-04", "2026-09-14", "2026-10-02", "2026-10-20", "2026-11-09",
        "2026-11-10", "2026-11-24", "2026-12-25",
    },
}


def fetch_exchange_holidays(timeout: float = 20.0) -> Dict[str, str]:
    """Trading holidays straight from the exchange: {ISO date: description}.

    Raises on any failure -- the caller decides whether to fall back, because
    "could not fetch" must never quietly become "no holidays".
    """
    req = urllib.request.Request(
        NSE_HOLIDAY_URL,
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
            "Accept": "application/json",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": "https://www.nseindia.com/",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        payload = json.load(resp)

    segment = next((s for s in _SEGMENT_ORDER if payload.get(s)), None)
    if segment is None:
        raise ValueError(f"no known segment in exchange response (got {sorted(payload)[:6]})")

    out: Dict[str, str] = {}
    for row in payload[segment]:
        raw = (row or {}).get("tradingDate", "")
        try:
            day = datetime.datetime.strptime(raw, "%d-%b-%Y").date()
        except ValueError:
            continue
        out[day.isoformat()] = str(row.get("description", "")).strip()
    if not out:
        raise ValueError("exchange returned no usable holiday dates")
    return out


def load_cache() -> dict:
    try:
        if CACHE_PATH.is_file():
            with open(CACHE_PATH, "r", encoding="utf-8") as fh:
                return json.load(fh) or {}
    except (OSError, ValueError) as exc:
        logger.warning("Holiday cache unreadable (%s) -- falling back.", exc)
    return {}


def save_cache(holidays: Dict[str, str], source: str) -> None:
    payload = {
        "fetched_at": datetime.datetime.now().isoformat(),
        "source": source,
        "holidays": holidays,
    }
    try:
        CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp = CACHE_PATH.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2, sort_keys=True)
        tmp.replace(CACHE_PATH)
    except OSError as exc:
        logger.error("Could not write holiday cache: %s", exc)


def cache_age_days() -> Optional[float]:
    data = load_cache()
    stamp = data.get("fetched_at")
    if not stamp:
        return None
    try:
        age = datetime.datetime.now() - datetime.datetime.fromisoformat(stamp)
    except ValueError:
        return None
    return age.total_seconds() / 86400.0


def refresh(force: bool = False) -> Tuple[bool, str]:
    """Update the cached calendar. Returns (refreshed, message).

    Never raises: a failed refresh leaves the previous cache in place, which is
    still better than the hardcoded table.
    """
    age = cache_age_days()
    if not force and age is not None and age <= MAX_CACHE_AGE_DAYS:
        return False, f"holiday calendar is {age:.1f} days old -- no refresh needed"
    try:
        holidays = fetch_exchange_holidays()
    except Exception as exc:
        have = len(load_cache().get("holidays") or {})
        return False, (f"exchange holiday fetch failed ({type(exc).__name__}: {exc}); "
                       f"keeping {have} cached date(s)")
    save_cache(holidays, source=NSE_HOLIDAY_URL)
    return True, f"holiday calendar refreshed from the exchange: {len(holidays)} date(s)"


def holidays_for(year: int) -> Dict[str, str]:
    """The holidays known for ``year``: exchange data if we have it, else the
    fallback table. Exchange data REPLACES the fallback rather than merging --
    the fallback is known to contain dates the exchange does not."""
    cached = {d: desc for d, desc in (load_cache().get("holidays") or {}).items()
              if d.startswith(f"{year}-")}
    if cached:
        return cached
    return {d: "" for d in FALLBACK_HOLIDAYS.get(year, set())}


def closed_reason(day: Optional[datetime.date] = None) -> Optional[str]:
    """Why the market is shut on ``day``, or None if it is a trading day."""
    day = day or datetime.date.today()
    if day.weekday() >= 5:
        return "weekend"
    known = holidays_for(day.year)
    iso = day.isoformat()
    if iso in known:
        desc = known[iso]
        return f"holiday: {desc}" if desc else "holiday"
    return None


def is_trading_day(day: Optional[datetime.date] = None) -> bool:
    return closed_reason(day) is None


def market_closed_now() -> Optional[str]:
    """Why an order must not be sent RIGHT NOW, or None when the market is open.

    Three questions, narrowest last:

    1. Is today a trading day at all?  -> the exchange calendar.
    2. Is it within session hours?     -> 09:15-15:30 IST.
    3. Does the broker agree it is open right now? -> market_status, which can
       catch an unscheduled halt no calendar knows about. Unreachable or paper
       mode is "unknown", and unknown is never read as open.

    Both workflows call this: the autonomous engine before an entry, and every
    manual order from the dashboard.
    """
    reason = closed_reason()
    if reason:
        return reason
    try:
        from shared.market_hours import is_market_open
        if not is_market_open():
            return "outside market hours (09:15-15:30 IST)"
    except Exception as exc:                      # pragma: no cover - import guard
        logger.debug("Market-hours check unavailable: %s", exc)
    if broker_market_open() is False:
        return "the broker reports the market is closed right now"
    return None


def next_holidays(after: Optional[datetime.date] = None, limit: int = 5) -> list:
    """The next few closures, so they can be announced in advance."""
    after = after or datetime.date.today()
    out = []
    for year in (after.year, after.year + 1):
        for iso, desc in sorted(holidays_for(year).items()):
            try:
                day = datetime.date.fromisoformat(iso)
            except ValueError:
                continue
            if day >= after:
                out.append((day, desc))
    return out[:limit]


def broker_market_open(broker=None) -> Optional[bool]:
    """Is the market open RIGHT NOW according to the broker?

    True/False, or None when it cannot be determined (no session, no network,
    unexpected payload). None means "unknown" and must never be read as "open".
    """
    try:
        if broker is None:
            from brokers import BrokerFactory
            broker = BrokerFactory.get_active_broker()
        if getattr(broker, "paper_mode", False):
            return None                      # nothing real to ask
        model = getattr(broker, "_fyers_model", None) or getattr(broker, "fyers", None)
        if model is None or not hasattr(model, "market_status"):
            return None
        resp = model.market_status() or {}
        rows = resp.get("marketStatus") or []
        for row in rows:
            if str(row.get("market_type", "")).upper() == "NORMAL":
                status = str(row.get("status", "")).upper()
                if "OPEN" in status:
                    return True
        return False if rows else None
    except Exception as exc:
        logger.debug("Broker market status unavailable: %s", exc)
        return None
