"""Phase 9 sec10 -- REVISED family set.

The first five families (families.py) are ABANDONED for insufficient sample,
not for poor performance: requiring the full context block (HTF bias AND
regime AND no-trade-clear) cut PDL rejections from 955 to 42 events over 588
days -- 0.07/day, far below anything measurable. That is a frequency
rejection, decided before looking at their out-of-sample numbers.

This set keeps the high-information component Phase 8 identified (previous-day
H/L) and varies ONLY what is stacked on top. Declared before DEV/VAL/FRESH
comparison.
"""
import os, sys
SP=os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0,SP)
import numpy as np
import p8lib as P, timing as T

ATR_NEAR = 0.25   # pre-declared, not swept

def build(bars, cond, ex, pdl, pdh, atr):
    close = bars["close"].to_numpy(float)
    out = {}
    for side, b in (("low", True), ("high", False)):
        lvl = pdl if b else pdh
        rej = T.rejection_events(bars, lvl, side)
        rec = T.reclaim_events(bars, lvl, side, 6)
        near = np.isfinite(lvl) & (np.abs(close - lvl) <= ATR_NEAR * atr)
        htf = cond['htf_bull' if b else 'htf_bear']
        rsi = cond['rsi_bull' if b else 'rsi_bear']
        regime = cond['regime_ok']
        free = cond['not_blocked']
        struct = ((ex['ranging'] & ex['choch_up' if b else 'choch_dn']) |
                  (ex['trending'] & ex['bos_up' if b else 'bos_dn']))
        fams = {
            "P1_rejection_only":      rej,
            "P2_rejection_plus_rsi":  rej & rsi,
            "P3_rejection_plus_htf":  rej & htf,
            "P4_proximity_state":     near,
            "P5_reclaim_only":        rec,
            # kept as controls
            "P6_rejection_full_ctx":  rej & htf & regime & free,
            "P7_rejection_then_struct": P.recent(rej, 8) & struct,
        }
        for k, v in fams.items():
            out.setdefault(k, {})["bull" if b else "bear"] = np.asarray(v, bool)
    return out

def to_signals(fam):
    raw = np.select([fam["bear"], fam["bull"]], [-1, 1], default=0).astype(int)
    return P.edge_trigger_np(raw)
