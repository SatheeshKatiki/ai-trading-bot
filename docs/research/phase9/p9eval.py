import os, sys, pickle
SP=os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0,SP)
import numpy as np, pandas as pd
import p8lib as P, split as S, families as F

def report(bars, fwd, fams, window_mask, label, horizon=24, draws=3000, delay=0):
    up,dn=fwd[horizon]; valid=np.isfinite(up)&np.isfinite(dn); n=len(bars)
    print(f"\n### {label}   (horizon {horizon}, entry delay +{delay} bars)")
    print(f'{"family":<28}{"n":>6}{"days":>6}{"eff":>6}{"ratio":>8}{"vs base":>9}{"null":>8}{"p":>8}')
    rows={}
    for nm, fam in fams.items():
        sig=F.to_signals(fam)
        if delay:
            shifted=np.zeros(n,dtype=int)
            src=np.flatnonzero(sig!=0)
            tgt=src+delay; ok=tgt<n
            shifted[tgt[ok]]=sig[src[ok]]
            sig=shifted
        sel=(sig!=0)&window_mask&valid
        d=np.where(sig>0,1,np.where(sig<0,-1,0))
        if sel.sum()<5:
            print(f'{nm:<28}{int(sel.sum()):>6}'); rows[nm]=None; continue
        st=P.excursion_stats(up,dn,d,sel)
        ce=int((d[sel]>0).sum()); pe=int((d[sel]<0).sum())
        base=(ce*S.baseline_ratio(up,dn,1,window_mask)+pe*S.baseline_ratio(up,dn,-1,window_mask))/max(1,ce+pe)
        nl=S.fast_same_day_null(bars.index,up,dn,d,sel,draws=draws)
        cl=P.clustering(bars.index,np.flatnonzero(sel),horizon)
        print(f'{nm:<28}{st["n"]:>6}{cl["days"]:>6}{cl["effective"]:>6}{st["ratio"]:>8.3f}'
              f'{st["ratio"]-base:>+9.3f}{nl.get("null_mean",np.nan):>8.3f}{nl.get("p_value",np.nan):>8.4f}')
        rows[nm]=(st["n"],st["ratio"]-base)
    return rows
