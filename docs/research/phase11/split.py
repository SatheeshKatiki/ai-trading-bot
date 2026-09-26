"""Phase 8 §23/§24 -- pre-declared temporal split and the permutation machinery.

DECLARED BEFORE any candidate architecture was compared. The full-sample
funnel in funnel.py was exploratory and is treated as such: anything chosen
because of it is DATA-DEPENDENT and has to survive VALIDATION, and the
HOLDOUT is touched exactly once, at the end.

The existing validation_harness split could not be reused: research_config
declares DEV as 2025-05-16..2026-01-31 but the CSV it reads now begins
2025-09-22, so the documented 178-day development set is silently 89 days.
That defect is reported, not repaired (production plane is frozen).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

#: Embargo between blocks, in bars. The longest forward horizon is 48 bars,
#: so a 48-bar gap stops a training observation's forward window from
#: overlapping the first validation observation.
EMBARGO_BARS = 48

SPLITS = {
    "DEV":      ("2024-01-01", "2025-06-30"),
    "VAL":      ("2025-07-01", "2026-03-31"),
    "HOLDOUT":  ("2026-04-01", "2026-09-25"),
}


def split_mask(index: pd.DatetimeIndex, name: str) -> np.ndarray:
    start, end = SPLITS[name]
    return np.asarray((index >= pd.Timestamp(start)) &
                      (index <= pd.Timestamp(end) + pd.Timedelta(days=1)))


def describe(index: pd.DatetimeIndex) -> None:
    print(f"{'split':<9}{'start':<12}{'end':<12}{'bars':>8}{'days':>7}")
    for name in SPLITS:
        m = split_mask(index, name)
        idx = index[m]
        if len(idx) == 0:
            print(f"{name:<9}{'--':<12}{'--':<12}{0:>8}{0:>7}")
            continue
        print(f"{name:<9}{str(idx[0].date()):<12}{str(idx[-1].date()):<12}"
              f"{len(idx):>8}{idx.normalize().nunique():>7}")


# ---------------------------------------------------------------------
# Permutation tests with the RIGHT null
# ---------------------------------------------------------------------

def ratio_of(up, dn, direction, sel) -> float:
    d = direction[sel]
    mfe = np.where(d > 0, up[sel], dn[sel])
    mae = np.where(d > 0, dn[sel], up[sel])
    tot = mae.sum()
    return float(mfe.sum() / tot) if tot > 0 else float("nan")


def permutation_same_day(index, up, dn, direction, mask, *, draws=4000,
                         seed=20260926):
    """NULL A -- keep the days and the directions, randomise the TIME.

    Answers: does the entry rule carry timing information beyond "be long
    NIFTY on this day"? This is the null that matters, because the baseline
    drift of the sample is held constant by construction.
    """
    rng = np.random.default_rng(seed)
    valid = np.isfinite(up) & np.isfinite(dn)
    sel = mask & valid & (direction != 0)
    if sel.sum() == 0:
        return {}

    observed = ratio_of(up, dn, direction, sel)
    days = pd.Index(index).normalize()
    day_values = days.to_numpy()

    # Per-day pools of eligible bars
    pools = {}
    for day in np.unique(day_values[valid]):
        pools[day] = np.flatnonzero((day_values == day) & valid)

    entries = np.flatnonzero(sel)
    entry_days = day_values[entries]
    entry_dirs = direction[entries]

    null = np.empty(draws)
    for k in range(draws):
        picks = np.empty(entries.size, dtype=int)
        for j, day in enumerate(entry_days):
            pool = pools[day]
            picks[j] = pool[rng.integers(pool.size)]
        d = entry_dirs
        mfe = np.where(d > 0, up[picks], dn[picks])
        mae = np.where(d > 0, dn[picks], up[picks])
        tot = mae.sum()
        null[k] = mfe.sum() / tot if tot > 0 else np.nan

    null = null[np.isfinite(null)]
    return {
        "n": int(entries.size),
        "observed": observed,
        "null_mean": float(null.mean()),
        "null_p05": float(np.percentile(null, 5)),
        "null_p95": float(np.percentile(null, 95)),
        "p_value": float((null >= observed).mean()),
        "percentile": float((null < observed).mean() * 100),
    }


def permutation_population(up, dn, direction, mask, *, draws=4000,
                           seed=20260926):
    """NULL B -- same direction mix, bars drawn from anywhere in the sample.

    Answers the broader question: do these entries carry ANY information?
    Note this null inherits the sample's directional drift, which is why
    Null A above is the primary test.
    """
    rng = np.random.default_rng(seed)
    valid = np.isfinite(up) & np.isfinite(dn)
    sel = mask & valid & (direction != 0)
    if sel.sum() == 0:
        return {}
    observed = ratio_of(up, dn, direction, sel)
    entries = np.flatnonzero(sel)
    entry_dirs = direction[entries]
    pool = np.flatnonzero(valid)

    null = np.empty(draws)
    for k in range(draws):
        picks = pool[rng.integers(pool.size, size=entries.size)]
        d = entry_dirs
        mfe = np.where(d > 0, up[picks], dn[picks])
        mae = np.where(d > 0, dn[picks], up[picks])
        tot = mae.sum()
        null[k] = mfe.sum() / tot if tot > 0 else np.nan
    null = null[np.isfinite(null)]
    return {
        "n": int(entries.size),
        "observed": observed,
        "null_mean": float(null.mean()),
        "null_p05": float(np.percentile(null, 5)),
        "null_p95": float(np.percentile(null, 95)),
        "p_value": float((null >= observed).mean()),
        "percentile": float((null < observed).mean() * 100),
    }


def baseline_ratio(up, dn, direction_value: int, valid_mask=None) -> float:
    """The unconditional MFE/MAE for a direction over the whole sample.

    THE correct reference. Comparing a long-only rule's ratio to 1.0 is
    wrong when the sample itself drifts; the reference is what an
    uninformed entry in that direction would have produced here.
    """
    valid = np.isfinite(up) & np.isfinite(dn)
    if valid_mask is not None:
        valid = valid & valid_mask
    d = np.full(up.shape, direction_value, dtype=int)
    return ratio_of(up, dn, d, valid)


def fast_same_day_null(index, up, dn, direction, mask, *, draws=4000,
                       seed=20260926):
    """Vectorised NULL A. Bars are time-sorted, so each day is a contiguous
    block; an entry's null pool is the valid bars of its own day."""
    rng = np.random.default_rng(seed)
    valid = np.isfinite(up) & np.isfinite(dn)
    sel = np.asarray(mask) & valid & (direction != 0)
    if sel.sum() == 0:
        return {}
    observed = ratio_of(up, dn, direction, sel)

    days = pd.Index(index).normalize().to_numpy()
    changes = np.r_[True, days[1:] != days[:-1]]
    day_id = np.cumsum(changes) - 1
    starts = np.flatnonzero(changes)
    ends = np.r_[starts[1:], len(days)]

    # last VALID bar of each day (forward window exists)
    valid_end = np.empty_like(ends)
    for k, (a, b) in enumerate(zip(starts, ends)):
        v = np.flatnonzero(valid[a:b])
        valid_end[k] = a + (v[-1] + 1 if v.size else 0)
    lo = starts[day_id]
    hi = np.maximum(valid_end[day_id], lo + 1)

    entries = np.flatnonzero(sel)
    e_lo, e_hi = lo[entries], hi[entries]
    e_dir = direction[entries]
    width = (e_hi - e_lo).astype(float)

    u = rng.random((draws, entries.size))
    picks = e_lo + (u * width).astype(int)
    picks = np.clip(picks, 0, len(days) - 1)

    mfe = np.where(e_dir > 0, up[picks], dn[picks])
    mae = np.where(e_dir > 0, dn[picks], up[picks])
    bad = ~(np.isfinite(mfe) & np.isfinite(mae))
    mfe = np.where(bad, 0.0, mfe); mae = np.where(bad, 0.0, mae)
    tot = mae.sum(axis=1)
    null = np.where(tot > 0, mfe.sum(axis=1) / np.where(tot > 0, tot, 1), np.nan)
    null = null[np.isfinite(null)]
    return {
        "n": int(entries.size), "observed": observed,
        "null_mean": float(null.mean()),
        "null_p05": float(np.percentile(null, 5)),
        "null_p95": float(np.percentile(null, 95)),
        "p_value": float((null >= observed).mean()),
    }
