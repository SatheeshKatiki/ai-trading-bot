"""Phase 10 -- THE FROZEN ENTRY RULE. Research only.

This is the single authoritative definition. Everything downstream imports
from here, so there is exactly one place the rule can be read or changed.

=====================================================================
THE RULE
=====================================================================

For each 5-minute bar i, using ONLY bars with index <= i:

  PDH[i] = the HIGH of the most recent COMPLETED prior session
  PDL[i] = the LOW  of the most recent COMPLETED prior session
  ATR[i] = shared.indicators.atr(df, 14) evaluated at bar i
  C[i]   = the CLOSE of bar i

  near_low [i] = isfinite(PDL[i]) and |C[i] - PDL[i]| <= BAND * ATR[i]
  near_high[i] = isfinite(PDH[i]) and |C[i] - PDH[i]| <= BAND * ATR[i]

  raw[i] = +1  if near_low[i]  and not near_high[i]      (buy CE)
           -1  if near_high[i] and not near_low[i]       (buy PE)
            0  otherwise

  BAND = 0.25   (pre-declared in Phase 9)

`raw` is then EDGE-TRIGGERED: a run of identical consecutive non-zero values
collapses to its first bar (trading_bot.strategies._signal_utils.edge_trigger
semantics). See setup.py for the stronger setup-identity grouping Phase 10
adds on top.

=====================================================================
EVERY AMBIGUITY, RESOLVED
=====================================================================

"within 0.25 ATR"
    ABSOLUTE distance from the bar's CLOSE to the level, in price points,
    compared against 0.25 x ATR. Symmetric: price may be on either side of
    the level. It is a proximity BAND, not a touch and not a cross.

which ATR
    `shared.indicators.atr(df, window=14)` -- Wilder-style true range smoothed
    with `ewm(span=14, adjust=False)`. NOT the SMC engine's internal ATR.

ATR timestamp
    ATR[i] uses bars 0..i inclusive. `ewm` is causal by construction: the
    value at i never depends on i+1. Pinned by a test.

previous-day high/low
    Computed by `levels.compute_daily_levels()`. Sessions are separated by
    calendar date on the bar's own timestamp. PDH/PDL for every bar of day D
    is the max high / min low of day D-1 AS PRESENT IN THE FRAME (the previous
    trading day, so weekends and holidays are skipped naturally). The FIRST
    day of any frame has PDH/PDL = NaN and can never signal.

session boundary
    A new session starts where the normalised date changes. No exchange
    calendar is consulted; the data's own day structure defines it.

must price APPROACH the level?
    NO. The rule is pure location. There is no requirement that price came
    from a particular side, pierced the level, or reverted. Phase 9 tested
    the pierce-and-close-back variants (P1 rejection, P5 reclaim) separately;
    they are NOT this rule.

"traded toward reversion"
    Direction is assigned by WHICH level is near:
        near the previous day's LOW  -> LONG  -> buy a CALL  (CE)
        near the previous day's HIGH -> SHORT -> buy a PUT   (PE)
    i.e. the trade bets price moves AWAY from the prior-day extreme, back
    toward the interior of the prior range. Phase 9's inverted-direction
    control flipped exactly this mapping and the edge inverted (+0.229 ->
    -0.192), which is the evidence the mapping is the right way round.

both levels near at once
    Possible on a very narrow prior-day range relative to ATR. Resolved to 0
    (no trade) -- the direction would be undefined. Phase 9 used
    `np.select([bear, bull], [-1, 1])`, which silently preferred bear. This
    module makes it an explicit no-trade and the difference is MEASURED in
    the reproduction below rather than assumed immaterial.

exact signal timestamp
    Bar i's CLOSE. The rule needs C[i], so it cannot be known earlier.

exact executable timestamp
    Bar i+1 or later. All Phase 10 economics use entry at bar i+1's OPEN as
    the base case (delay = 1), which is the first price a live engine could
    actually transact at. Delay 0 (fill at bar i's close) is reported only for
    continuity with Phase 9.

CE/PE mapping
    +1 -> CE, -1 -> PE. This system only ever BUYS premium.
"""
from __future__ import annotations

import os
import sys

SP = os.path.dirname(os.path.abspath(__file__))
if SP not in sys.path:
    sys.path.insert(0, SP)

import numpy as np
import pandas as pd

import p8lib as P  # noqa: E402  (sets up sys.path to trading-system)

BAND = 0.25
ATR_WINDOW = 14


def prior_day_levels(bars: pd.DataFrame):
    """(PDH, PDL) per bar, from the completed previous session only."""
    from trading_bot.strategies.rsi_smc_options_buyer import levels as L
    d = L.compute_daily_levels(bars)
    return np.asarray(d.prev_day_high, float), np.asarray(d.prev_day_low, float)


def causal_atr(bars: pd.DataFrame, window: int = ATR_WINDOW) -> np.ndarray:
    from shared.indicators import atr as _atr
    return _atr(bars, window).to_numpy(dtype=float)


def raw_signal(bars: pd.DataFrame, band: float = BAND,
               atr_window: int = ATR_WINDOW, strict_both: bool = True):
    """The frozen rule. Returns (raw, near_low, near_high, pdh, pdl, atr)."""
    pdh, pdl = prior_day_levels(bars)
    atr = causal_atr(bars, atr_window)
    close = bars["close"].to_numpy(dtype=float)
    tol = band * atr

    near_low = np.isfinite(pdl) & np.isfinite(tol) & (np.abs(close - pdl) <= tol)
    near_high = np.isfinite(pdh) & np.isfinite(tol) & (np.abs(close - pdh) <= tol)

    if strict_both:
        both = near_low & near_high
        raw = np.where(near_low & ~both, 1, np.where(near_high & ~both, -1, 0))
    else:
        # Phase 9 behaviour: bear wins an overlap.
        raw = np.select([near_high, near_low], [-1, 1], default=0)
    return raw.astype(int), near_low, near_high, pdh, pdl, atr


def edge_triggered(bars, band: float = BAND, strict_both: bool = True) -> np.ndarray:
    raw, *_ = raw_signal(bars, band, strict_both=strict_both)
    return P.edge_trigger_np(raw)
