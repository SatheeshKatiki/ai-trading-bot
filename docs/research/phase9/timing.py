"""Phase 9 -- entry-timing architecture. Research only.

Phase 8 established that every architecture tested picks the right day and
direction and the wrong moment, giving back 0.43-0.73 of MFE/MAE. Phase 9
asks whether that can be recovered by entering EARLIER at a point that is
still causally defensible.

Everything here is causal by construction: each event is detected from bars
at or before the bar it is stamped on, and forward labels start at the NEXT
bar.
"""
from __future__ import annotations

import os
import sys

SP = os.path.dirname(os.path.abspath(__file__))
if SP not in sys.path:
    sys.path.insert(0, SP)

import numpy as np
import pandas as pd

import p8lib as P
import split as S


# ---------------------------------------------------------------------
# Causal level-interaction events
# ---------------------------------------------------------------------

def rejection_events(bars, level, side):
    """IMMEDIATE rejection: one bar pierces the level and closes back inside.

    `side="low"` -> a sell-side level (PDL): wick below, close above. This is
    the long setup. `side="high"` -> PDH: wick above, close below, short.

    Detectable at the CLOSE of the piercing bar, so this is the earliest
    causally defensible signal of a failed break. Stamped on that bar; a
    forward window starting at the next bar uses no information from it.
    """
    low = bars["low"].to_numpy(float)
    high = bars["high"].to_numpy(float)
    close = bars["close"].to_numpy(float)
    lv = np.asarray(level, float)
    if side == "low":
        return np.isfinite(lv) & (low < lv) & (close > lv)
    return np.isfinite(lv) & (high > lv) & (close < lv)


def reclaim_events(bars, level, side, max_bars_outside=6):
    """DELAYED reclaim: price CLOSED beyond the level, then closes back inside.

    Distinct from a rejection -- here the break was accepted for at least one
    bar before failing. `max_bars_outside` bounds how long it may have stayed
    out and still count as a reclaim rather than a trend.

    Causal: bar i is flagged using only closes at i and earlier.
    """
    close = bars["close"].to_numpy(float)
    lv = np.asarray(level, float)
    n = len(close)
    outside = (close < lv) if side == "low" else (close > lv)
    outside = np.nan_to_num(outside, nan=False).astype(bool)
    inside = np.isfinite(lv) & (~outside)

    out = np.zeros(n, dtype=bool)
    run = 0
    for i in range(n):
        if outside[i]:
            run += 1
            continue
        if inside[i] and 1 <= run <= max_bars_outside:
            out[i] = True
        run = 0
    return out


def sweep_onset(bars, level, side, recent=5, warmup=40):
    """The shipped sweep definition's first visible bar (Phase 8 semantics)."""
    from trading_bot.strategies.rsi_smc_options_buyer import liquidity as LQ
    nan = np.full(len(bars), np.nan)
    lo = np.asarray(level, float) if side == "low" else nan
    hi = nan if side == "low" else np.asarray(level, float)
    r = LQ.key_level_sweeps(bars, lo, hi, recent, warmup)
    return P.onset(r.bullish if side == "low" else r.bearish)


# ---------------------------------------------------------------------
# Timing curve
# ---------------------------------------------------------------------

def first_after(event_mask, anchor_positions, window):
    """For each anchor, the first bar in (anchor, anchor+window] where
    `event_mask` is True, or -1."""
    ev = np.flatnonzero(np.asarray(event_mask, bool))
    out = np.full(anchor_positions.shape[0], -1, dtype=int)
    if ev.size == 0:
        return out
    idx = np.searchsorted(ev, anchor_positions, side="right")
    for k, (a, j) in enumerate(zip(anchor_positions, idx)):
        if j < ev.size and ev[j] <= a + window:
            out[k] = ev[j]
    return out


def excursion_at(up, dn, positions, direction):
    """MFE/MAE at given positions for a fixed direction."""
    valid = positions >= 0
    pos = positions[valid]
    if pos.size == 0:
        return dict(n=0)
    ok = np.isfinite(up[pos]) & np.isfinite(dn[pos])
    pos = pos[ok]
    if pos.size == 0:
        return dict(n=0)
    mfe = up[pos] if direction > 0 else dn[pos]
    mae = dn[pos] if direction > 0 else up[pos]
    return dict(n=int(pos.size), mfe=float(mfe.mean()), mae=float(mae.mean()),
                ratio=float(mfe.sum() / mae.sum()) if mae.sum() > 0 else np.nan,
                win=float((mfe > mae).mean() * 100))


def travelled(bars, from_pos, to_pos, direction):
    """Price already travelled in the trade's favour between two stamps."""
    close = bars["close"].to_numpy(float)
    ok = (from_pos >= 0) & (to_pos >= 0)
    if not ok.any():
        return np.nan, np.nan
    d = close[to_pos[ok]] - close[from_pos[ok]]
    if direction < 0:
        d = -d
    lag = (to_pos[ok] - from_pos[ok]).astype(float)
    return float(d.mean()), float(lag.mean())


# ---------------------------------------------------------------------
# Execution-delay robustness
# ---------------------------------------------------------------------

def delayed(positions, k, n):
    """Shift entry stamps forward by k bars, dropping those that fall off."""
    out = positions + k
    out[positions < 0] = -1
    out[out >= n] = -1
    return out
