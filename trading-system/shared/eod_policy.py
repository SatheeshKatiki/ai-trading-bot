"""When an open position must be closed at the end of the day.

The owner's rule, 2026-09-22, replacing a flat 15:15 guillotine:

  * at 15:15 every open position is REVIEWED, not automatically closed;
  * one that is still running -- in profit and still near its own best
    premium -- may keep going;
  * at 15:25 everything closes, without exception;
  * an overnight carry is possible only on very strong evidence, is off by
    default, and never happens on an expiry day.

Measured over 675 sessions with costs calibrated from real option premiums:

                                     NIFTY      SENSEX
  close everything at 15:15        +11,150     -37,841
  close everything at 15:25         +7,415     -37,507
  extend only runners (within 3%)  +12,428     -37,463
  extend only runners (within 5%)  +12,005     -37,297

Extending everything loses money. Extending only what is still at its high
makes money. That is the whole rule: it is not "trade later", it is "do not
interrupt a move that is still going".

On expiry day the carry branch does not exist. The contract expires; there is
nothing to carry, and anything still open at the close is settled by the
exchange at intrinsic value, which for an OTM option is zero.
"""

from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass
from typing import Optional

CLOSE_NOW = "close"
EXTEND = "extend"
HOLD_OPEN = "hold"       # still before the review time
CARRY = "carry"          # overnight, off by default


@dataclass(frozen=True)
class EodVerdict:
    action: str
    reason: str

    @property
    def must_close(self) -> bool:
        return self.action == CLOSE_NOW


def _as_time(value, fallback: _dt.time) -> _dt.time:
    try:
        hh, mm = str(value).split(":")[:2]
        return _dt.time(int(hh), int(mm))
    except Exception:
        return fallback


def decide_eod(now: _dt.time,
               gain_pct: float,
               giveback_pct: float,
               strength: str,
               cfg,
               is_expiry_day: bool = False,
               reversed_signal: bool = False) -> EodVerdict:
    """What to do with one open position, right now.

    `gain_pct` is the position's profit on its entry premium and
    `giveback_pct` how far it has come off its own best premium, both in
    percent. `reversed_signal` is True when the strategy has flipped against
    the position -- a runner that has lost its trend is not a runner.
    """
    review = _as_time(getattr(cfg, "eod_review_time", "15:15"), _dt.time(15, 15))
    hard = _as_time(getattr(cfg, "eod_hard_time", "15:25"), _dt.time(15, 25))

    if now < review:
        return EodVerdict(HOLD_OPEN, "before the end-of-day review")

    if now < hard:
        if reversed_signal:
            return EodVerdict(CLOSE_NOW, f"end-of-day review at {review:%H:%M}: signal has reversed")
        if gain_pct <= 0:
            return EodVerdict(CLOSE_NOW,
                              f"end-of-day review at {review:%H:%M}: not in profit ({gain_pct:+.1f}%)")
        allowed = float(getattr(cfg, "eod_runner_giveback_pct", 5.0))
        if giveback_pct > allowed:
            return EodVerdict(CLOSE_NOW,
                              f"end-of-day review at {review:%H:%M}: {giveback_pct:.1f}% off its high, "
                              f"more than the {allowed:.0f}% a runner may give back")
        return EodVerdict(EXTEND,
                          f"still running (+{gain_pct:.1f}%, {giveback_pct:.1f}% off its high) -- "
                          f"held to {hard:%H:%M}")

    # Past the hard cutoff. Everything closes, unless an overnight carry has
    # been explicitly enabled AND earns itself -- and never on expiry day.
    if is_expiry_day:
        return EodVerdict(CLOSE_NOW, f"expiry day: nothing survives {hard:%H:%M}")
    if not bool(getattr(cfg, "allow_overnight_carry", False)):
        return EodVerdict(CLOSE_NOW, f"hard square-off at {hard:%H:%M}")

    floor = float(getattr(cfg, "overnight_min_gain_pct", 40.0))
    want = str(getattr(cfg, "overnight_min_strength", "VERY_STRONG")).upper()
    if reversed_signal:
        return EodVerdict(CLOSE_NOW, f"hard square-off at {hard:%H:%M}: signal reversed")
    if gain_pct < floor:
        return EodVerdict(CLOSE_NOW,
                          f"hard square-off at {hard:%H:%M}: +{gain_pct:.1f}% is below the "
                          f"+{floor:.0f}% an overnight carry needs")
    if str(strength).upper() != want:
        return EodVerdict(CLOSE_NOW,
                          f"hard square-off at {hard:%H:%M}: momentum {strength or 'NONE'} "
                          f"is not {want}")
    return EodVerdict(CARRY,
                      f"carried overnight: +{gain_pct:.1f}%, momentum {strength}, "
                      f"signal intact -- gap risk is now unhedged")


def late_entry_allowed(now: _dt.time, strength: str, cfg,
                       is_expiry_day: bool = True) -> tuple[bool, str]:
    """Whether a NEW entry may be taken after the normal cutoff (15:15).

    Applies on ALL days (not just expiry days): allowed until `late_entry_end`
    (15:25) ONLY on the strongest momentum band (VERY_STRONG).
    """
    late_enabled = bool(getattr(cfg, "late_entry_enabled", getattr(cfg, "expiry_late_entry", True)))
    if not late_enabled:
        return False, "late entry is switched off"
    end_str = getattr(cfg, "late_entry_end", getattr(cfg, "expiry_late_entry_end", "15:25"))
    end = _as_time(end_str, _dt.time(15, 25))
    if now >= end:
        return False, f"past the late entry cutoff of {end:%H:%M}"
    want = str(getattr(cfg, "late_entry_min_strength", getattr(cfg, "expiry_late_entry_min_strength", "VERY_STRONG"))).upper()
    if str(strength).upper() != want:
        return False, (f"late entry needs {want} momentum, "
                       f"this is {strength or 'NONE'}")
    return True, f"late entry permitted on {strength} momentum until {end:%H:%M}"


# Backward compatibility alias
expiry_late_entry_allowed = late_entry_allowed



def is_expiry_day(symbol: str, day: Optional[_dt.date] = None) -> Optional[bool]:
    """Whether `day` is an expiry for `symbol`'s nearest contract.

    Returns None when it cannot be determined -- callers treat None as "not
    an expiry day", because the late-entry and carry branches both widen what
    the bot may do, and a guess must never be what opens them.
    """
    day = day or _dt.date.today()
    try:
        from trading_bot.strategies.momentum_strategy.itm_selector import ItmSelector
        return bool(ItmSelector.is_expiry_day(day))
    except Exception:
        return None
