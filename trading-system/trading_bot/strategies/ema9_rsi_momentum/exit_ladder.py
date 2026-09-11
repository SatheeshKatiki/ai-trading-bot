"""The owner's exit: a stop that only ratchets up, and no fixed target.

Stated by the owner on 2026-09-12: *"we use a trailing stop, so there is no
fixed target -- if the move has room, the target should move up by itself,
and the trailing stop should keep moving up too, until the market
reverses."*

So the premium climbs a ladder of rungs. The stop starts 15% under entry;
reaching a rung moves it up to the rung below; the "target" shown for a
position is only ever the next rung. The trade ends when the stop is hit,
when the EMA/RSI reversal fires, or at the EOD square-off -- never because a
target was reached.

  rungs (gain over entry):  15   33   50   75   100   150   200
  stop once reached:         0   15   33   50    75   100   150    (0 = breakeven)

Measured before adoption over 578 NIFTY sessions, the same harness as every
other result (owner's entries, reversal and EOD exits unchanged):

  15-min ITM   fixed 33% target  +1.99%/trade  best +31%
               this ladder       +2.25%/trade  best +106%
  5-min ATM    fixed 33% target  -3.20%/trade
               this ladder       -2.89%/trade

The first rung is the owner's original "stop to breakeven at +15%" and the
second the old 33% target -- now a rung to pass, not a place to stop.
"""

from __future__ import annotations

from typing import Optional, Sequence, Tuple

#: Rungs, as % gain in premium over the entry price.
DEFAULT_PROFIT_LADDER_PCT: Tuple[float, ...] = (15.0, 33.0, 50.0, 75.0, 100.0, 150.0, 200.0)
#: The initial stop, as % below the entry price.
DEFAULT_INITIAL_SL_PCT: float = 15.0


def ladder_levels(best_gain_pct: float,
                  rungs: Sequence[float] = DEFAULT_PROFIT_LADDER_PCT,
                  initial_sl_pct: float = DEFAULT_INITIAL_SL_PCT) -> Tuple[float, Optional[float]]:
    """(stop, next rung) implied by the best gain the premium has reached.

    Both are % relative to entry. Before the first rung the stop is
    ``-initial_sl_pct``; reaching rung *i* moves it to rung *i-1* (breakeven
    for the first). ``next rung`` is None once the top rung is passed.
    """
    ordered = sorted(float(r) for r in rungs)
    stop = -float(initial_sl_pct)
    previous = 0.0
    for rung in ordered:
        if best_gain_pct >= rung:
            stop = previous
            previous = rung
        else:
            return stop, rung
    return stop, None


def ratchet_stop(entry: float, current_stop: float, best_price: float,
                 rungs: Sequence[float] = DEFAULT_PROFIT_LADDER_PCT,
                 initial_sl_pct: float = DEFAULT_INITIAL_SL_PCT,
                 tick: float = 0.05) -> Tuple[float, Optional[float]]:
    """New stop PRICE and next-rung PRICE for a position.

    The stop only ever moves up: whatever the ladder implies, a stop already
    higher is kept. Prices are rounded to the exchange tick (the stop down,
    so rounding never tightens it past its rung).
    """
    if entry <= 0:
        raise ValueError(f"entry must be positive, got {entry}")
    best_gain_pct = (best_price - entry) / entry * 100.0
    stop_pct, next_pct = ladder_levels(best_gain_pct, rungs, initial_sl_pct)
    implied = entry * (1.0 + stop_pct / 100.0)
    if tick > 0:
        implied = int(implied / tick + 1e-9) * tick
    new_stop = round(max(current_stop, implied), 2)
    next_price = round(entry * (1.0 + next_pct / 100.0), 2) if next_pct is not None else None
    return new_stop, next_price


def initial_stop(entry: float, initial_sl_pct: float = DEFAULT_INITIAL_SL_PCT, tick: float = 0.05) -> float:
    """The opening stop price, ``initial_sl_pct`` under entry, on the tick grid."""
    price = entry * (1.0 - initial_sl_pct / 100.0)
    if tick > 0:
        price = int(price / tick + 1e-9) * tick
    return round(price, 2)


def stop_reason(entry: float, stop: float) -> str:
    """How to label a stop-out: the original stop, breakeven, or a locked gain."""
    if stop < entry - 1e-9:
        return "STOP LOSS"
    if abs(stop - entry) <= 0.05:
        return "BREAKEVEN STOP"
    return f"TRAILING STOP (+{(stop - entry) / entry * 100:.0f}% locked)"
