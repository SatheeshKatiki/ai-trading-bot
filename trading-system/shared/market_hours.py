"""NSE market-hours gate for real-money-adjacent trading decisions.

Mirrors `frontend/lib/ist-time.ts`'s `isMarketOpenIST()` definition
(weekday + 09:15–15:30 IST window, no holiday calendar) so "is the market
open" means the same thing on both sides of this system. The frontend's
version is presentation-only (dims a UI badge); this is the backend's
authoritative version — it gates real paper-trading entries.

Root cause / why this exists
-----------------------------
Nothing previously stopped a new entry from executing outside real NSE
trading hours. Found live 2026-08-06: a NIFTY position opened at 02:50 IST
off a single stale post-restart snapshot tick, then received zero risk
management for 7h49m because nothing else in the system detects or reports
a silent tick feed either (see `shared/risk/tick_staleness.py`, fixed
alongside this). A real broker structurally rejects any order placed
outside the exchange session; paper mode had no equivalent enforcement.
Full incident write-up in
`docs/paper_trading_validation/anomaly_log.md`'s 2026-08-06 entry.

Scope
-----
This only ever gates NEW entries (see `trading_bot/main.py`'s call site,
placed immediately after a signal is confirmed non-zero, before any SL/
sizing/order-placement work happens). An already-open position must keep
receiving full exit management — trailing stop, hard SL, EOD square-off,
partial booking, pyramiding — regardless of the time of day. Refusing to
manage risk on an open position just because the clock says
market-closed would be actively dangerous, not conservative, so this
module is never consulted anywhere on the exit path.
"""
from __future__ import annotations

from datetime import datetime, time as dt_time
from typing import Any, Mapping, Optional

import pytz

__all__ = ["IST", "MARKET_OPEN_TIME", "MARKET_CLOSE_TIME", "is_market_open"]

IST = pytz.timezone("Asia/Kolkata")

#: Same window as frontend/lib/ist-time.ts's isMarketOpenIST() — keep both
#: in sync if this ever changes.
MARKET_OPEN_TIME = dt_time(9, 15)
MARKET_CLOSE_TIME = dt_time(15, 30)

_WEEKEND_ISO_WEEKDAYS = (5, 6)  # datetime.weekday(): Monday=0 ... Sunday=6


def is_market_open(
    now: Optional[datetime] = None,
    settings: Optional[Mapping[str, Any]] = None,
) -> bool:
    """True during real NSE weekday trading hours (09:15–15:30 IST).

    No holiday calendar — matches the frontend's definition exactly rather
    than introducing a second, stricter standard only one side of the
    system knows about. A holiday will read as "open" here; that's a known,
    accepted gap shared with the existing frontend indicator, not a new one
    introduced by this gate.

    Parameters
    ----------
    now
        Reference instant. Defaults to the real current time
        (`datetime.now(IST)`) — overridable for tests. A naive `datetime`
        is assumed to already be IST wall-clock time, matching the rest of
        this codebase's convention (e.g. `record_trade`'s timestamps).
    settings
        Recognised key: `market_hours_override` — if explicitly `True` or
        `False` (not merely absent), short-circuits the real check
        entirely. Exists for deliberately exercising the paper engine
        outside real hours on purpose (e.g. testing) without editing code
        — distinct from silently disabling the gate, since it requires an
        explicit, visible settings-file entry to activate.
    """
    settings = settings or {}
    override = settings.get("market_hours_override")
    if override is not None:
        return bool(override)

    if now is None:
        now = datetime.now(IST)
    elif now.tzinfo is None:
        now = IST.localize(now)
    else:
        now = now.astimezone(IST)

    if now.weekday() in _WEEKEND_ISO_WEEKDAYS:
        return False

    current_time = now.time()
    return MARKET_OPEN_TIME <= current_time < MARKET_CLOSE_TIME
