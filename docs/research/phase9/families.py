"""Phase 9 sec10 -- the five PRE-DECLARED entry families.

Declared before any DEV/VAL/FRESH comparison. No parameter sweep: the only
window is W=8, inherited from the shipped config. Every family has a stated
structural hypothesis.
"""
import os, sys
SP=os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0,SP)
import numpy as np
import p8lib as P, timing as T

W = 8

def build(bars, cond, ex, pdl, pdh, *, reclaim_max_outside=6):
    """{family: {'bull':mask,'bear':mask}} -- all causal, all same-bar stamped."""
    out = {}
    for side, b in (("low", True), ("high", False)):
        lvl = pdl if b else pdh
        ctx = (cond['htf_bull' if b else 'htf_bear'] & cond['regime_ok']
               & cond['not_blocked'])
        rej = T.rejection_events(bars, lvl, side)
        rec = T.reclaim_events(bars, lvl, side, reclaim_max_outside)
        struct = ((ex['ranging'] & ex['choch_up' if b else 'choch_dn']) |
                  (ex['trending'] & ex['bos_up' if b else 'bos_dn']))
        rsi = cond['rsi_bull' if b else 'rsi_bear']
        trig = cond['trigger_bull' if b else 'trigger_bear']
        rr = cond['rr_ok_bull' if b else 'rr_ok_bear']
        lvl_near = cond['level_near_bull' if b else 'level_near_bear']
        sweep = cond['sweep_bull' if b else 'sweep_bear']
        smc_struct = cond['struct_bull' if b else 'struct_bear']

        fams = {
            # A -- control: exactly what Phase 7 shipped.
            "A_shipped": (cond['htf_bull' if b else 'htf_bear'] & cond['regime_ok']
                          & lvl_near & sweep & smc_struct & rsi & trig & rr
                          & cond['not_blocked']),
            # B -- context + PDH/PDL sweep + earliest causal RECLAIM.
            #      Hypothesis: an accepted-then-failed break is the signal.
            "B_reclaim": ctx & rec,
            # C -- context + PDH/PDL rejection + causal STRUCTURE confirmation.
            #      Hypothesis: structure is worth its delay.
            "C_rejection_then_structure": ctx & P.recent(rej, W) & struct,
            # D -- context + PDH/PDL rejection + MOMENTUM STATE at that bar.
            #      Hypothesis: RSI as a state is a cheaper confirmation.
            "D_rejection_plus_momentum": ctx & rej & rsi,
            # E -- context + PDH/PDL rejection alone. EARLIEST DEFENSIBLE.
            #      Hypothesis: the rejection itself is the information.
            "E_rejection_only": ctx & rej,
        }
        for k, v in fams.items():
            out.setdefault(k, {})[side_key(b)] = np.asarray(v, bool)
    return out


def side_key(is_bull):
    return "bull" if is_bull else "bear"


def to_signals(fam):
    raw = np.select([fam["bear"], fam["bull"]], [-1, 1], default=0).astype(int)
    return P.edge_trigger_np(raw)
