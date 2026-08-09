"""Structure Break — opening-balance breakout, event-triggered.

Philosophy
----------
The first `OPENING_RANGE_MINUTES` of a session is where the overnight
information gap is priced in: participants who must trade the open do so,
and the range they leave behind is the session's initial balance area.
Price *leaving* that area is the session establishing direction. That is a
discrete **event** with an economic story, not a pattern fitted to a
sample.

This module deliberately contains no indicator stack — no RSI, MACD,
volume, ADX or trend overlay. It is the smallest expression of one
mechanism, so that a later evidence-driven change has an honest baseline
to be measured against, rather than being buried under conditions nobody
validated. Every one of those additions is a hypothesis to be *tested*,
not an assumption to ship.

Three design properties, each earned from a measured failure elsewhere in
this repository (see docs/STRATEGY_IMPROVEMENT_BACKLOG.md):

1. **Event-triggered, not level-triggered.** A level condition
   ("EMA > EMA and RSI > 55") holds for long stretches, so a
   level-triggered strategy re-enters the same setup bar after bar. That
   mechanism was measured to be the dominant drawdown driver in `ema_rsi`
   (47.9% -> 20.8% drawdown once edge-triggered) and `advanced_ai` (Q2
   2.95 -> 1.32). The only event-triggered strategy in the suite showed
   no churn at all. Here the break of a fixed daily level can only happen
   once per direction per session, so churn is impossible by
   construction rather than suppressed by a later patch.

2. **Confirmed on a COMPLETED bar.** The signal for bar *i* is decided by
   the close of bar *i-1*. Live, `main.py` evaluates `signals.iloc[-1]`
   on the bar still forming; a rule that reads the current bar's close
   therefore means "price touched the level at some instant" live but
   "the bar closed beyond the level" in a backtest — two different
   strategies wearing one name. `TieredExitManager` shipped exactly that
   divergence. Reading only closed bars makes live and backtest
   semantically identical, which is the whole point.

3. **One event per direction per session.** Not a cooldown timer or a
   de-duplication filter bolted on afterwards: the first confirmed break
   in a direction is the event, and there is no second one that day. A
   genuine reversal (a break of the opposite side) is still allowed,
   because that is a different event, not a repeat of the same one.

What this module does NOT do
----------------------------
No option selection, sizing, stop-loss, target, trailing or exit logic
lives here. Those belong to the shared production pipeline
(`select_option`, `resolve_initial_stop`, `RiskManager`,
`SmartExitEngine`) which already runs for every strategy, and which this
one deliberately does not replace or special-case. The single strategy in
this repository that took its own exit path is the one whose exits never
executed at all.

Configuration
-------------
`OPENING_RANGE_MINUTES` is structural, not tuned: 30 minutes is the
conventional definition of the opening balance. It was not swept over the
development set, and must not be.
"""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

STRATEGY_NAME = "structure_break"

#: Length of the opening balance area, in minutes. Structural choice (the
#: conventional opening-range definition), deliberately not optimised.
OPENING_RANGE_MINUTES = 30

__all__ = [
    "STRATEGY_NAME",
    "OPENING_RANGE_MINUTES",
    "generate_signals",
]


def _bar_minutes(index: pd.DatetimeIndex) -> float:
    """Infer the bar size in minutes from the index itself.

    The opening range is defined in MINUTES, not in bars, so the same
    strategy expresses the same idea whether it is handed 1-, 3-, 5- or
    15-minute data. Hard-coding "6 bars" would silently mean 6 minutes on
    a 1-minute feed and 90 on a 15-minute one.
    """
    if len(index) < 2:
        return 5.0
    deltas = np.diff(index.values).astype("timedelta64[s]").astype(float)
    deltas = deltas[deltas > 0]
    if deltas.size == 0:
        return 5.0
    return float(np.median(deltas)) / 60.0


def generate_signals(df: pd.DataFrame, **kwargs) -> pd.Series:
    """Return a {-1, 0, +1} signal Series aligned to `df`.

    +1 = break above the opening range (buy CALL),
    -1 = break below it (buy PUT),
     0 = no event.

    Parameters
    ----------
    df
        OHLCV frame with a DatetimeIndex. May span many days; each
        calendar day is evaluated independently, which matches both the
        day-isolated validation harness and the live engine's per-session
        reality.
    opening_range_minutes
        Override for `OPENING_RANGE_MINUTES`. Present so tests and
        research can vary it explicitly; production passes nothing and
        gets the module default.
    """
    signals = np.zeros(len(df), dtype=int)
    if df.empty or not isinstance(df.index, pd.DatetimeIndex):
        return pd.Series(signals, index=df.index, dtype=int)

    range_minutes = float(kwargs.get("opening_range_minutes", OPENING_RANGE_MINUTES))
    bar_minutes = _bar_minutes(df.index)
    if bar_minutes <= 0:
        return pd.Series(signals, index=df.index, dtype=int)

    n_range_bars = max(1, int(round(range_minutes / bar_minutes)))

    high = df["high"].to_numpy(dtype=float)
    low = df["low"].to_numpy(dtype=float)
    close = df["close"].to_numpy(dtype=float)
    positions = np.arange(len(df))

    # Day boundaries. Built once from the index rather than by grouping
    # the frame, so no intermediate DataFrames are materialised per day —
    # this runs on every tick in production.
    dates = df.index.normalize().to_numpy()
    day_starts = np.flatnonzero(np.r_[True, dates[1:] != dates[:-1]])
    day_ends = np.r_[day_starts[1:], len(df)]  # exclusive

    for start, end in zip(day_starts, day_ends):
        n_bars = end - start
        # Need the full range plus a confirming bar plus a bar to act on.
        if n_bars < n_range_bars + 2:
            continue

        range_slice = slice(start, start + n_range_bars)
        or_high = float(np.max(high[range_slice]))
        or_low = float(np.min(low[range_slice]))
        if not np.isfinite(or_high) or not np.isfinite(or_low):
            continue

        # Confirming bars: those that have CLOSED outside the range,
        # starting with the first bar after the range itself. The signal
        # is emitted on the NEXT bar, which is the first bar on which the
        # engine could actually act on that information.
        confirm = positions[start + n_range_bars: end - 1]
        if confirm.size == 0:
            continue

        broke_up = close[confirm] > or_high
        broke_dn = close[confirm] < or_low

        # `argmax` on a boolean array gives the first True; guard with
        # `.any()` because argmax returns 0 for an all-False array.
        if broke_up.any():
            signals[confirm[int(np.argmax(broke_up))] + 1] = 1
        if broke_dn.any():
            idx = confirm[int(np.argmax(broke_dn))] + 1
            # A day can legitimately break both ways (a failed break that
            # reverses). Each is its own event. If both resolve onto the
            # same bar the later-confirmed one would overwrite the other,
            # which would silently drop an event — emit nothing there
            # instead of picking arbitrarily, and say so.
            if signals[idx] == 0:
                signals[idx] = -1
            else:
                logger.debug(
                    "structure_break: up and down breaks confirmed onto the same "
                    "bar at %s — emitting neither.", df.index[idx],
                )
                signals[idx] = 0

    return pd.Series(signals, index=df.index, dtype=int)
