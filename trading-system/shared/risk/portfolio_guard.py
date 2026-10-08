"""One portfolio rule for new option entries, shared by every engine.

The live engine, the main paper book and the variant books all call
:func:`entry_block_reason` with the same inputs, so a paper result stays a
faithful preview of live behaviour.

Three checks, measured on the 49 sessions where NIFTY, BANKNIFTY and SENSEX
all have data (5-minute / ATM entries, the owner's exit ladder, one lot,
Rs 1,00,000):

  rule                                     worst day   max drawdown   days < -3%
  no cap (per-index rule only)               -10,282        -53,899           12
  max 1 same-direction position               -6,861        -41,446            6
  max 1 same-direction + 3% daily stop        -4,736        -35,538            8

1. **Daily loss stop.** Once the day's P&L (realised + open) is at or below
   ``max_daily_loss_pct`` of capital, no new entries. Open positions keep
   their own stops.
2. **One position per direction.** The three indices move together -- 5-min
   return correlation 0.75-0.91, and 61% of signals have a same-direction
   signal on another index within 15 minutes -- so three open CEs are one
   bet taken three times. ``max_same_direction_positions`` (default 1).
3. **No single trade may risk more than the day's whole loss limit.** One
   BANKNIFTY lot at a 15% stop risks ~Rs 2,400 against a Rs 1,000 per-trade
   policy, and the live risk manager let it through as "minimum size". The
   ceiling here is the owner's own daily limit: one stop-out can never end
   the day on its own.
"""

from __future__ import annotations

from typing import Iterable, Optional

DEFAULT_MAX_SAME_DIRECTION = 1
DEFAULT_MAX_DAILY_LOSS_PCT = 3.0


def option_direction(symbol: str) -> int:
    """+1 for a call, -1 for a put, 0 for anything else.

    Reads the SUFFIX. ``"CE" in symbol`` -- the test used elsewhere -- also
    matches RELIAN-CE.
    """
    text = str(symbol or "").strip().upper()
    if text.endswith("CE"):
        return 1
    if text.endswith("PE"):
        return -1
    return 0


def daily_loss_limit(capital: float, settings: Optional[dict] = None) -> float:
    """The day's loss limit in rupees."""
    pct = float((settings or {}).get("max_daily_loss_pct", DEFAULT_MAX_DAILY_LOSS_PCT))
    return capital * pct / 100.0


def entry_block_reason(*, direction: int, open_directions: Iterable[int], day_pnl: float,
                       capital: float, trade_risk: float, settings: Optional[dict] = None,
                       vix: Optional[float] = None,
                       stopped_out_dir: Optional[int] = None,
                       stopped_out_time: Optional[float] = None,
                       now_time: Optional[float] = None) -> Optional[str]:
    """Why a new option entry must not be taken, or None if it may.

    ``direction`` +1 (CE) / -1 (PE); ``open_directions`` the same for every
    open position; ``day_pnl`` realised + unrealised rupees today;
    ``trade_risk`` the rupees lost if this trade hits its opening stop;
    ``vix`` India VIX now, if known;
    ``stopped_out_dir`` / ``stopped_out_time`` last SL hit direction and time.
    """
    settings = settings or {}

    # 5. Post-StopLoss Cooldown Guard (User Rule 2026-10-05)
    # If the last trade in this symbol stopped out, allow opposite reversal immediately,
    # but require a cooldown (default 300s / 5m) before same-direction re-entry to stop revenge trades.
    if stopped_out_dir is not None and stopped_out_time is not None and stopped_out_dir == direction:
        cooldown = float(settings.get("post_sl_cooldown_seconds", 300.0))
        import time as _time
        current_t = now_time if now_time is not None else _time.time()
        elapsed = current_t - stopped_out_time
        if elapsed < cooldown:
            rem = int(cooldown - elapsed)
            side = "CE" if direction == 1 else "PE"
            return f"Post-SL cool-off active for {side} ({rem}s remaining -- awaiting cool-off or opposite signal)"

    limit = daily_loss_limit(capital, settings)
    if day_pnl <= -limit:
        return f"daily loss limit reached (Rs {day_pnl:,.0f} <= -Rs {limit:,.0f})"

    cap = int(settings.get("max_same_direction_positions", DEFAULT_MAX_SAME_DIRECTION))
    same = sum(1 for d in open_directions if d == direction)
    if cap > 0 and same >= cap:
        side = "CE" if direction == 1 else "PE"
        return f"{same} {side} position(s) already open -- the indices move together (cap {cap})"

    if trade_risk > limit:
        return f"one-lot risk Rs {trade_risk:,.0f} exceeds the day's whole loss limit Rs {limit:,.0f}"

    max_vix = settings.get("max_entry_vix")
    if max_vix is not None:
        if vix is None:
            return f"India VIX unknown and the VIX gate is on (max {float(max_vix):g})"
        if float(vix) > float(max_vix):
            return f"India VIX {float(vix):.2f} above the entry gate {float(max_vix):g}"
    return None
