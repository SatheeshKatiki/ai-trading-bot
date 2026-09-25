"""Phase 8 §11 -- the PRE-DECLARED candidate matrix.

Seven structurally different architectures. Not a parameter sweep: every
entry here is a different *shape* of decision, and each exists because a
specific Phase 8 finding motivates it. No thresholds are tuned; the only
window used (confirm_window = 8) is the one the Phase 7 strategy already
shipped with.

Declared before any DEV/VAL/HOLDOUT comparison was run.
"""
from __future__ import annotations

import numpy as np

import p8lib as P

W = 8  # confirm window, inherited from the shipped config -- NOT swept


def _build(cond, ex, side):
    """Common building blocks for one direction."""
    b = side == "bull"
    return {
        "htf":     cond["htf_bull" if b else "htf_bear"],
        "regime":  cond["regime_ok"],
        "level":   cond["level_near_bull" if b else "level_near_bear"],
        "sweep":   cond["sweep_bull" if b else "sweep_bear"],
        "struct":  cond["struct_bull" if b else "struct_bear"],
        "rsi":     cond["rsi_bull" if b else "rsi_bear"],
        "trigger": cond["trigger_bull" if b else "trigger_bear"],
        "rr":      cond["rr_ok_bull" if b else "rr_ok_bear"],
        "free":    cond["not_blocked"],
        "bos":     ex["bos_up" if b else "bos_dn"],
        "choch":   ex["choch_up" if b else "choch_dn"],
        "trending": ex["trending"],
        "ranging":  ex["ranging"],
    }


def candidate_masks(cond, ex):
    """{name: {'bull': mask, 'bear': mask}} for every declared candidate."""
    out = {}
    for side in ("bull", "bear"):
        g = _build(cond, ex, side)

        # A -- the Phase 7 architecture, unchanged.
        A = (g["htf"] & g["regime"] & g["level"] & g["sweep"] &
             g["struct"] & g["rsi"] & g["trigger"] & g["rr"] & g["free"])

        # B -- drop the price-action trigger. Tests whether requiring a
        #      decisive candle is buying in after the move.
        B = (g["htf"] & g["regime"] & g["level"] & g["sweep"] &
             g["struct"] & g["rsi"] & g["rr"] & g["free"])

        # C -- drop the R:R gate. Tests whether selecting for a distant
        #      opposing level selects for bad location.
        C = (g["htf"] & g["regime"] & g["level"] & g["sweep"] &
             g["struct"] & g["rsi"] & g["trigger"] & g["free"])

        # D -- drop both. Context + setup + confirmation only.
        D = (g["htf"] & g["regime"] & g["level"] & g["sweep"] &
             g["struct"] & g["rsi"] & g["free"])

        # E -- setup core: no RSI, no trigger, no R:R.
        E = (g["htf"] & g["regime"] & g["level"] & g["sweep"] &
             g["struct"] & g["free"])

        # F -- SEQUENTIAL. sweep, THEN structure, THEN state now.
        #      Tests §9: are these stages a sequence rather than a
        #      simultaneous conjunction?
        sweep_onset = P.onset(g["sweep"])
        struct_event = (g["ranging"] & g["choch"]) | (g["trending"] & g["bos"])
        seq = P.ordered_after(sweep_onset, struct_event, W)
        F = (P.recent(seq, W) & g["htf"] & g["regime"] & g["rsi"] & g["free"])

        # G -- EVIDENCE SCORE. Six independent causal blocks, threshold
        #      pre-declared at 5 of 6. No weights, no optimisation.
        score = (g["htf"].astype(int) + g["regime"].astype(int) +
                 g["level"].astype(int) + g["sweep"].astype(int) +
                 g["struct"].astype(int) + g["rsi"].astype(int))
        G = (score >= 5) & g["free"]

        for name, mask in (("A_full_conjunction", A), ("B_no_trigger", B),
                           ("C_no_rr", C), ("D_no_trigger_no_rr", D),
                           ("E_setup_core", E), ("F_sequential", F),
                           ("G_evidence_5of6", G)):
            out.setdefault(name, {})[side] = mask
    return out


def to_signals(masks_for_candidate):
    """Combine bull/bear masks into an edge-triggered {-1,0,+1} series.

    Bear resolved first on the (structurally impossible) overlap, matching
    signal_engine.compose.
    """
    bull = masks_for_candidate["bull"]
    bear = masks_for_candidate["bear"]
    raw = np.select([bear, bull], [-1, 1], default=0).astype(int)
    return P.edge_trigger_np(raw)
