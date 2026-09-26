"""Phase 10 sec4/sec6 -- setup identity and the deterministic lifecycle.

THE PROBLEM
-----------
The Phase 9 rule is a STATE ("price is near the level"), so it is true for
runs of bars. `edge_trigger` collapses a contiguous run to its first bar, but
price can leave the band and return on the same day at the same level, and
each return produced a fresh "signal". Those are not independent experiments:
they are one setup observed repeatedly. Treating them as independent inflates
both the sample size and the apparent significance.

THE LIFECYCLE
-------------
    NO_SETUP
       |  price enters the band around a prior-day extreme
       v
    NEAR_PRIOR_DAY_EXTREME
       |  which level decides the side (low -> long, high -> short)
       v
    DIRECTION_ESTABLISHED
       |  bar closes; the rule is evaluable
       v
    ENTRY_ELIGIBLE
       |  selection policy picks it (see selection.py)
       v
    ENTRY            <- executable at the NEXT bar's open
       v
    POSITION_OPEN
       v
    EXIT

Every transition uses only bars at or before the transition bar.

SETUP IDENTITY -- two pre-declared groupings, both reported
-----------------------------------------------------------
EPISODE   a maximal run of consecutive bars in the band, same direction, same
          day. Leaving the band ends it. Returning starts a new episode.
DAY_SIDE  one setup per (calendar day, direction). The most conservative
          reading: everything that happens at yesterday's low today is one
          idea, however many times price revisits it.

Neither is "correct" a priori, so both are measured and the difference is
reported rather than a choice being buried.
"""
from __future__ import annotations

import os
import sys

SP = os.path.dirname(os.path.abspath(__file__))
if SP not in sys.path:
    sys.path.insert(0, SP)

import numpy as np
import pandas as pd

import entry as E

STATES = ("NO_SETUP", "NEAR_PRIOR_DAY_EXTREME", "DIRECTION_ESTABLISHED",
          "ENTRY_ELIGIBLE", "ENTRY", "POSITION_OPEN", "EXIT")


def episodes(bars: pd.DataFrame, band: float = E.BAND):
    """Contiguous in-band runs. Returns a DataFrame, one row per episode.

    Columns: start, end (inclusive positions), direction, day, level, n_bars.
    """
    raw, near_low, near_high, pdh, pdl, atr = E.raw_signal(bars, band)
    days = bars.index.normalize().to_numpy()
    n = len(bars)

    rows = []
    i = 0
    while i < n:
        d = raw[i]
        if d == 0:
            i += 1
            continue
        j = i
        while j + 1 < n and raw[j + 1] == d and days[j + 1] == days[i]:
            j += 1
        rows.append(dict(start=i, end=j, direction=int(d), day=days[i],
                         level=float(pdl[i] if d > 0 else pdh[i]),
                         atr=float(atr[i]), n_bars=j - i + 1))
        i = j + 1
    return pd.DataFrame(rows)


def group_day_side(eps: pd.DataFrame) -> pd.DataFrame:
    """Collapse episodes to one row per (day, direction)."""
    if eps.empty:
        return eps
    g = eps.sort_values("start").groupby(["day", "direction"], as_index=False)
    out = g.agg(start=("start", "first"), end=("end", "last"),
                level=("level", "first"), atr=("atr", "first"),
                n_bars=("n_bars", "sum"), n_episodes=("start", "size"))
    return out.sort_values("start").reset_index(drop=True)


def summarise(bars, band: float = E.BAND, label: str = ""):
    eps = episodes(bars, band)
    ds = group_day_side(eps)
    days = bars.index.normalize().nunique()
    raw, *_ = E.raw_signal(bars, band)
    import p8lib as P
    et = int((P.edge_trigger_np(raw) != 0).sum())
    return dict(label=label, bars=len(bars), days=days,
                in_band_bars=int((raw != 0).sum()),
                edge_triggered=et, episodes=len(eps),
                day_side=len(ds),
                eps_per_day=len(eps) / max(1, days),
                dayside_per_day=len(ds) / max(1, days),
                median_episode_bars=float(eps.n_bars.median()) if len(eps) else np.nan,
                episodes_per_dayside=len(eps) / max(1, len(ds)))
