"""One place that knows what a timeframe string means.

The UI stores the user's chart selection in ``config/settings.json`` as
``"timeframe"`` -- "5 Min", "15 Min", "1 Hour", "1 Week" and so on. Before
this module each consumer re-parsed that itself or, worse, ignored it:
``trading_bot/main.py`` parsed it inline, ``paper_observer.py`` hardcoded
"5 Min" in two places, and ``Ema9RsiMomentumConfig.timeframe_minutes`` sat at
its default of 5 no matter what the user picked. A user on the 15-minute
chart was watching one timeframe and being traded on another.

Everything here is expressed in MINUTES, and bars are anchored the way
``pandas.DataFrame.resample`` anchors them -- from midnight -- because that
is how ``shared.closed_bars.resample_closed`` already builds them, and the
live series and the backtested one have to be the same construction.
"""

from __future__ import annotations

import datetime as _dt
import re
from typing import Optional

#: Minutes in a trading day and a trading week, for the non-intraday sizes.
MINUTES_PER_DAY = 1440
MINUTES_PER_WEEK = 7 * MINUTES_PER_DAY
MINUTES_PER_MONTH = 30 * MINUTES_PER_DAY

#: What the UI offers, in the exact spelling the broker wrappers expect.
CANONICAL_LABELS = {
    1: "1 Min",
    3: "3 Min",
    5: "5 Min",
    15: "15 Min",
    30: "30 Min",
    60: "1 Hour",
    MINUTES_PER_DAY: "1 Day",
    MINUTES_PER_WEEK: "1 Week",
    MINUTES_PER_MONTH: "1 Month",
}

DEFAULT_MINUTES = 5

_UNIT_MINUTES = {
    "m": 1, "min": 1, "mins": 1, "minute": 1, "minutes": 1,
    "h": 60, "hr": 60, "hour": 60, "hours": 60,
    "d": MINUTES_PER_DAY, "day": MINUTES_PER_DAY, "days": MINUTES_PER_DAY,
    "w": MINUTES_PER_WEEK, "wk": MINUTES_PER_WEEK, "week": MINUTES_PER_WEEK,
    "weeks": MINUTES_PER_WEEK,
    "mo": MINUTES_PER_MONTH, "month": MINUTES_PER_MONTH,
    "months": MINUTES_PER_MONTH,
}

_PATTERN = re.compile(r"^\s*(\d+)\s*([A-Za-z]*)\s*$")


def parse_timeframe(value, default: int = DEFAULT_MINUTES) -> int:
    """Minutes per bar for anything the UI or a settings file might hold.

    Accepts "5 Min", "5min", "5m", "5", 5, "1 Hour", "1H", "1 Day", "1W",
    "1 Month" -- case and spacing are ignored. An unreadable value falls back
    to `default` rather than raising: a malformed setting must not stop a book
    from trading, it must trade the timeframe it has always traded.

    Note "m" means minutes and "mo"/"month" means months, matching the UI's
    own labels. There is no ambiguity with "M" for month because the UI never
    writes a bare "M".
    """
    if value is None:
        return default
    if isinstance(value, bool):           # bool is an int subclass; not a timeframe
        return default
    if isinstance(value, (int, float)):
        minutes = int(value)
        return minutes if minutes > 0 else default

    match = _PATTERN.match(str(value))
    if not match:
        return default
    count = int(match.group(1))
    unit = (match.group(2) or "min").lower()
    per_unit = _UNIT_MINUTES.get(unit)
    if per_unit is None or count <= 0:
        return default
    return count * per_unit


def timeframe_label(minutes: int) -> str:
    """The broker-facing spelling for a bar size, e.g. 15 -> "15 Min"."""
    known = CANONICAL_LABELS.get(int(minutes))
    if known:
        return known
    minutes = int(minutes)
    if minutes % MINUTES_PER_WEEK == 0:
        return f"{minutes // MINUTES_PER_WEEK} Week"
    if minutes % MINUTES_PER_DAY == 0:
        return f"{minutes // MINUTES_PER_DAY} Day"
    if minutes % 60 == 0:
        return f"{minutes // 60} Hour"
    return f"{minutes} Min"


def settings_timeframe(settings: Optional[dict], default: int = DEFAULT_MINUTES) -> int:
    """The user's chart selection, in minutes, from a settings dict."""
    if not settings:
        return default
    return parse_timeframe(settings.get("timeframe"), default)


def is_intraday(minutes: int) -> bool:
    """Whether a bar of this size opens and closes inside one session."""
    return 0 < int(minutes) < MINUTES_PER_DAY


def seconds_to_bar_close(now: _dt.datetime, minutes: int) -> Optional[float]:
    """Seconds left in the bar `now` falls inside, or None if it has no
    intraday close.

    Bars are anchored from midnight, which is what `pandas.resample` does and
    therefore what `shared.closed_bars.resample_closed` produces: a 30-minute
    chart runs 09:00-09:30, 09:30-10:00 -- not 09:15-09:45 from the session
    open. Anchoring the timing gate any other way would have it counting down
    to a boundary the candle series does not have.

    Daily, weekly and monthly bars return None: their close is days away, so
    "wait for the bar to close" is not a thing a live entry can do. Callers
    treat None as "this rule does not apply here".
    """
    minutes = int(minutes)
    if minutes <= 0:
        raise ValueError(f"minutes must be positive, got {minutes}")
    if not is_intraday(minutes):
        return None
    span = minutes * 60
    into_day = (now.hour * 60 + now.minute) % minutes
    into_bar = into_day * 60 + now.second + now.microsecond / 1e6
    return span - into_bar
