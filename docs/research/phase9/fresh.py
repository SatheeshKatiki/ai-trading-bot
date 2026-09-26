"""Phase 9 sec23 -- FRESH untouched holdout.

The Phase 8 NIFTY holdout (2026-04-01..2026-09-25) is CONTAMINATED: it was
inspected, and the pre-10:00 effect was found in it afterwards. It is used
here for description only.

GENUINELY UNTOUCHED partitions, neither inspected nor computed in Phase 8:
  * SENSEX    2026-04-01 .. 2026-09-25   (Phase 8 cut SENSEX at 2026-03-31)
  * BANKNIFTY 2026-06-29 .. 2026-09-25   (skipped entirely in Phase 8)

Frozen candidates: P1_rejection_only (primary), P4_proximity_state,
P5_reclaim_only. These need no SMC replay -- only previous-day levels and
ATR -- so the holdout run is exactly the declared rule and nothing else.
"""
import os, sys, pickle
SP=os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0,SP)
import numpy as np, pandas as pd
import p8lib as P, split as S, timing as T
from trading_bot.strategies.rsi_smc_options_buyer import levels as L
from shared.indicators import atr as _atr

ATR_NEAR=0.25

def candidate_masks(bars):
    daily=L.compute_daily_levels(bars)
    a=_atr(bars,14).to_numpy(float); close=bars['close'].to_numpy(float)
    out={}
    for side,b in (("low",True),("high",False)):
        lvl = daily.prev_day_low if b else daily.prev_day_high
        out.setdefault('P1_rejection_only',{})['bull' if b else 'bear']=T.rejection_events(bars,lvl,side)
        out.setdefault('P4_proximity_state',{})['bull' if b else 'bear']=np.isfinite(lvl)&(np.abs(close-lvl)<=ATR_NEAR*a)
        out.setdefault('P5_reclaim_only',{})['bull' if b else 'bear']=T.reclaim_events(bars,lvl,side,6)
    return out

def run(bars,label,delays=(0,1)):
    fwd=P.forward_excursions(bars,(24,)); up,dn=fwd[24]
    valid=np.isfinite(up)&np.isfinite(dn); n=len(bars); allm=np.ones(n,bool)
    fams=candidate_masks(bars)
    print(f"\n### {label}   {bars.index[0].date()}..{bars.index[-1].date()}  "
          f"{n:,} bars / {bars.index.normalize().nunique()} days")
    print(f'   baseline long {S.baseline_ratio(up,dn,1,allm):.3f}  short {S.baseline_ratio(up,dn,-1,allm):.3f}')
    print(f'   {"family":<24}{"delay":>6}{"n":>6}{"days":>6}{"eff":>6}{"ratio":>8}{"vs base":>9}{"null":>8}{"p":>8}')
    for nm,fam in fams.items():
        raw=np.select([fam['bear'],fam['bull']],[-1,1],default=0).astype(int)
        base_sig=P.edge_trigger_np(raw)
        for k in delays:
            sig=np.zeros(n,int); src=np.flatnonzero(base_sig!=0); tgt=src+k; ok=tgt<n
            sig[tgt[ok]]=base_sig[src[ok]]
            sel=(sig!=0)&valid; d=np.where(sig>0,1,np.where(sig<0,-1,0))
            if sel.sum()<20:
                print(f'   {nm:<24}{k:>6}{int(sel.sum()):>6}   (n<20)'); continue
            st=P.excursion_stats(up,dn,d,sel)
            ce=int((d[sel]>0).sum()); pe=int((d[sel]<0).sum())
            b=(ce*S.baseline_ratio(up,dn,1,allm)+pe*S.baseline_ratio(up,dn,-1,allm))/max(1,ce+pe)
            nl=S.fast_same_day_null(bars.index,up,dn,d,sel,draws=4000)
            cl=P.clustering(bars.index,np.flatnonzero(sel),24)
            print(f'   {nm:<24}{k:>6}{st["n"]:>6}{cl["days"]:>6}{cl["effective"]:>6}{st["ratio"]:>8.3f}'
                  f'{st["ratio"]-b:>+9.3f}{nl.get("null_mean",np.nan):>8.3f}{nl.get("p_value",np.nan):>8.4f}')

if __name__=="__main__":
    print("################  FRESH HOLDOUT -- OPENED ONCE  ################")
    sx=P.load_csv("BSE_SENSEX-INDEX_5Min.csv").loc["2026-04-01":]
    run(sx,"FRESH A -- SENSEX (never inspected)")
    bn=P.load_csv("NSE_NIFTYBANK-INDEX_5Min.csv")
    run(bn,"FRESH B -- BANKNIFTY (never inspected)")
    print("\n--- CONTAMINATED, descriptive only ---")
    nf=P.load_nifty(); m=S.split_mask(nf.index,'HOLDOUT')
    run(nf[m],"NIFTY 2026-04-01+ (Phase 8 holdout, contaminated)")
