"""Phase 8 sec19/20/24/29 -- decay, walk-forward, regime, cross-instrument."""
import numpy as np, pandas as pd, pickle
import p8lib as P, split as S, validate as V

bars=P.load_nifty(); fwd=pickle.load(open("fwd.pkl","rb"))
cond=pickle.load(open("cond.pkl","rb")); ex=pickle.load(open("extras.pkl","rb"))
masks=V.locked_candidates(cond,ex)
HORIZ=(3,6,12,24,48)
fwd_all=P.forward_excursions(bars,HORIZ)

def stat(up,dn,sig,m):
    valid=np.isfinite(up)&np.isfinite(dn)
    sel=(sig!=0)&m&valid
    if sel.sum()<5: return None
    d=np.where(sig>0,1,np.where(sig<0,-1,0))
    st=P.excursion_stats(up,dn,d,sel)
    ce=int((d[sel]>0).sum()); pe=int((d[sel]<0).sum())
    base=(ce*S.baseline_ratio(up,dn,1,m)+pe*S.baseline_ratio(up,dn,-1,m))/max(1,ce+pe)
    return st["n"], st["ratio"], st["ratio"]-base

print("=== SIGNAL DECAY (sec29): ratio minus baseline, by horizon ===")
print(f'{"candidate":<20}{"split":<6}'+''.join(f'{h:>9}' for h in HORIZ))
for nm in ("A_shipped","E_setup_core","F_sequential","S1_sweep_onset"):
    sig=P.edge_trigger_np(V.to_dir(masks[nm]))
    for sp in ("DEV","VAL"):
        m=S.split_mask(bars.index,sp); row=[]
        for h in HORIZ:
            up,dn=fwd_all[h]; r=stat(up,dn,sig,m)
            row.append(f'{r[2]:>+9.3f}' if r else f'{"--":>9}')
        print(f'{nm:<20}{sp:<6}'+''.join(row))

print()
print("=== WALK-FORWARD by quarter (sec24), horizon 24, vs baseline ===")
up,dn=fwd_all[24]
q=pd.PeriodIndex(bars.index,freq="Q")
qs=sorted(set(q.astype(str)))
print(f'{"candidate":<20}'+''.join(f'{x[-6:]:>9}' for x in qs))
for nm in ("A_shipped","E_setup_core","F_sequential","S1_sweep_onset"):
    sig=P.edge_trigger_np(V.to_dir(masks[nm])); row=[]
    for qq in qs:
        m=np.asarray(q.astype(str)==qq); r=stat(up,dn,sig,m)
        row.append(f'{r[2]:>+9.3f}' if r else f'{"--":>9}')
    print(f'{nm:<20}'+''.join(row))

print()
print("=== REGIME-STRATIFIED (sec19), horizon 24, vs baseline ===")
print(f'{"candidate":<20}{"trending":>12}{"ranging":>12}')
for nm in ("A_shipped","E_setup_core","F_sequential","S1_sweep_onset"):
    sig=P.edge_trigger_np(V.to_dir(masks[nm])); row=[]
    for key in ("trending","ranging"):
        m=np.asarray(ex[key],bool); r=stat(up,dn,sig,m)
        row.append(f'{r[2]:>+7.3f}(n{r[0]})' if r else f'{"--":>12}')
    print(f'{nm:<20}'+''.join(f'{x:>12}' for x in row))
