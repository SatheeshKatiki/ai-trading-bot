"""Phase 10 sec1 -- reproduce Phase 9 exactly."""
import os,sys; SP=os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0,SP)
import numpy as np, pandas as pd
import p8lib as P, split as S, entry as E

def evaluate(bars, sig, mask=None, h=24, draws=4000, label=""):
    fwd=P.forward_excursions(bars,(h,)); up,dn=fwd[h]
    valid=np.isfinite(up)&np.isfinite(dn); n=len(bars)
    m = np.ones(n,bool) if mask is None else mask
    sel=(sig!=0)&m&valid; d=np.where(sig>0,1,np.where(sig<0,-1,0))
    if sel.sum()<20: return None
    st=P.excursion_stats(up,dn,d,sel)
    ce=int((d[sel]>0).sum()); pe=int((d[sel]<0).sum())
    base=(ce*S.baseline_ratio(up,dn,1,m)+pe*S.baseline_ratio(up,dn,-1,m))/max(1,ce+pe)
    nl=S.fast_same_day_null(bars.index,up,dn,d,sel,draws=draws)
    cl=P.clustering(bars.index,np.flatnonzero(sel),h)
    return dict(n=st['n'],days=cl['days'],eff=cl['effective'],ratio=st['ratio'],
                delta=st['ratio']-base,p=nl.get('p_value',np.nan),null=nl.get('null_mean',np.nan))

def row(lab,r,ref=None):
    if r is None: print(f'  {lab:<44}  (n<20)'); return
    tag='' if ref is None else f'   [P9: {ref}]'
    print(f'  {lab:<44}{r["n"]:>6}{r["days"]:>6}{r["eff"]:>6}{r["delta"]:>+9.3f}{r["p"]:>9.4f}{tag}')

if __name__=="__main__":
    print("=== sec1 PHASE 9 REPRODUCTION (band 0.25, horizon 24) ===")
    print(f'  {"window":<44}{"n":>6}{"days":>6}{"eff":>6}{"vs base":>9}{"p":>9}')
    nf=P.load_nifty()
    sig=E.edge_triggered(nf, strict_both=False)   # Phase 9 semantics
    for sp,ref in (("DEV","+0.250 p<0.0001"),("VAL","+0.143 p=0.0023")):
        row(f'NIFTY {sp}', evaluate(nf,sig,S.split_mask(nf.index,sp)), ref)
    row('NIFTY 2026-04+ (contaminated)', evaluate(nf,sig,S.split_mask(nf.index,'HOLDOUT')), "+0.302 p=0.087")
    sx=P.load_csv("BSE_SENSEX-INDEX_5Min.csv").loc["2026-04-01":]
    row('SENSEX FRESH', evaluate(sx,E.edge_triggered(sx,strict_both=False)), "+0.501 p=0.0003")
    bn=P.load_csv("NSE_NIFTYBANK-INDEX_5Min.csv")
    row('BANKNIFTY FRESH', evaluate(bn,E.edge_triggered(bn,strict_both=False)), "+0.382 p<0.0001")
    print()
    print("  --- strict_both=True (Phase 10 explicit no-trade on overlap) ---")
    sig2=E.edge_triggered(nf, strict_both=True)
    changed=int((sig!=sig2).sum())
    print(f'  bars where the overlap rule changes the signal: {changed}')
    for sp in ("DEV","VAL"):
        row(f'NIFTY {sp} strict', evaluate(nf,sig2,S.split_mask(nf.index,sp)))
