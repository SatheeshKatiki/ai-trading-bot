"""Phase 8 §24 -- VALIDATION run on the locked candidate set.

The candidate list below is FROZEN. It was chosen from DEV, where 14
comparisons were made, so every entry here is DATA-DEPENDENT and the
Bonferroni-style correction for 14 comparisons is applied to the reported
p-values. HOLDOUT is not touched by this file.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pickle

import p8lib as P
import split as S

W = 8
N_DEV_COMPARISONS = 14   # declared: 7 candidates + 7 entry-point variants


def blocks(cond, ex, side):
    b = side == "bull"
    return dict(
        htf=cond["htf_bull" if b else "htf_bear"], regime=cond["regime_ok"],
        level=cond["level_near_bull" if b else "level_near_bear"],
        sweep=cond["sweep_bull" if b else "sweep_bear"],
        struct=cond["struct_bull" if b else "struct_bear"],
        rsi=cond["rsi_bull" if b else "rsi_bear"],
        trig=cond["trigger_bull" if b else "trigger_bear"],
        rr=cond["rr_ok_bull" if b else "rr_ok_bear"], free=cond["not_blocked"],
        bos=ex["bos_up" if b else "bos_dn"], choch=ex["choch_up" if b else "choch_dn"],
        trending=ex["trending"], ranging=ex["ranging"])


def locked_candidates(cond, ex):
    out = {}
    for side in ("bull", "bear"):
        g = blocks(cond, ex, side)
        ctx = g["htf"] & g["regime"] & g["free"]
        so = P.onset(g["sweep"])
        se_ = (g["ranging"] & g["choch"]) | (g["trending"] & g["bos"])
        seq = P.ordered_after(so, se_, W)

        cands = {
            # CONTROL -- what Phase 7 shipped.
            "A_shipped": (g["htf"] & g["regime"] & g["level"] & g["sweep"] &
                          g["struct"] & g["rsi"] & g["trig"] & g["rr"] & g["free"]),
            # Setup core, no RSI/trigger/RR.
            "E_setup_core": (g["htf"] & g["regime"] & g["level"] & g["sweep"] &
                             g["struct"] & g["free"]),
            # Windowed sequential.
            "F_sequential": P.recent(seq, W) & ctx & g["rsi"],
            # Sequential, entering ON the structure event bar. DEV leader.
            "S4_sequence_event": seq & ctx,
            # Earliest actionable point in the sequence.
            "S1_sweep_onset": so & ctx,
        }
        for k, v in cands.items():
            out.setdefault(k, {})[side] = v
    return out


def to_dir(masks):
    d = np.zeros(masks["bull"].shape[0], dtype=int)
    d = np.where(masks["bear"], -1, d)
    d = np.where(masks["bull"], 1, d)
    return d


def evaluate(bars, up, dn, masks, window_mask, label, draws=4000):
    valid = np.isfinite(up) & np.isfinite(dn)
    rows = []
    for name, m in masks.items():
        d = to_dir(m)
        raw = np.where(d != 0, d, 0)
        sig = P.edge_trigger_np(raw)
        sel = (sig != 0) & window_mask & valid
        dd = np.where(sig > 0, 1, np.where(sig < 0, -1, 0))
        if sel.sum() == 0:
            rows.append((name, 0, np.nan, np.nan, np.nan, np.nan, np.nan, np.nan))
            continue
        st = P.excursion_stats(up, dn, dd, sel)
        pos = np.flatnonzero(sel)
        cl = P.clustering(bars.index, pos, 24)
        ce = int((dd[sel] > 0).sum()); pe = int((dd[sel] < 0).sum())
        base = (ce * S.baseline_ratio(up, dn, 1, window_mask) +
                pe * S.baseline_ratio(up, dn, -1, window_mask)) / max(1, ce + pe)
        null = S.fast_same_day_null(bars.index, up, dn, dd, sel, draws=draws)
        rows.append((name, st["n"], cl["days"], cl["effective"], st["ratio"],
                     st["ratio"] - base, null.get("null_mean", np.nan),
                     null.get("p_value", np.nan)))
    print(f"\n### {label}")
    print(f"{'candidate':<20}{'n':>6}{'days':>6}{'eff':>6}{'ratio':>8}"
          f"{'vs base':>9}{'sameday null':>14}{'p':>8}{'p x14':>8}")
    for name, n, days, eff, ratio, delta, nullm, p in rows:
        if n == 0:
            print(f"{name:<20}{0:>6}")
            continue
        padj = min(1.0, p * N_DEV_COMPARISONS) if np.isfinite(p) else np.nan
        print(f"{name:<20}{n:>6}{days:>6}{eff:>6}{ratio:>8.3f}{delta:>+9.3f}"
              f"{nullm:>14.3f}{p:>8.4f}{padj:>8.4f}")
    return rows


if __name__ == "__main__":
    bars = P.load_nifty()
    fwd = pickle.load(open("fwd.pkl", "rb"))
    cond = pickle.load(open("cond.pkl", "rb"))
    ex = pickle.load(open("extras.pkl", "rb"))
    up, dn = fwd[24]
    masks = locked_candidates(cond, ex)

    for split_name in ("DEV", "VAL"):
        m = S.split_mask(bars.index, split_name)
        evaluate(bars, up, dn, masks, m,
                 f"{split_name}  ({S.SPLITS[split_name][0]}..{S.SPLITS[split_name][1]})")
