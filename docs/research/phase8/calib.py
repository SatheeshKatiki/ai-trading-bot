"""Phase 8 sec21 -- calibration. Same measurement, existing strategies."""
import numpy as np, pandas as pd, pickle
import p8lib as P, split as S

def replay_registry(bars, name, chunk=500, context=P.LIVE_CONTEXT_BARS):
    from trading_bot.strategies.registry import registry
    n=len(bars); out=np.zeros(n,dtype=int); start=0
    while start<n:
        stop=min(start+chunk,n); lo=max(0,start-context)
        w=bars.iloc[lo:stop]
        try:
            r=registry._strategies[name](w)
            r=r[0] if isinstance(r,tuple) else r
            out[start:stop]=np.asarray(pd.Series(r).fillna(0),dtype=int)[start-lo:]
        except Exception:
            pass
        start=stop
    return P.edge_trigger_np(out)

if __name__=="__main__":
    bars=P.load_nifty(); fwd=pickle.load(open("fwd.pkl","rb")); up,dn=fwd[24]
    valid=np.isfinite(up)&np.isfinite(dn)
    names=["ema9_rsi_momentum","momentum_15_5","structure_break","ema_rsi","buy_the_dip"]
    print(f'{"strategy":<22}{"split":<6}{"n":>6}{"days":>6}{"ratio":>8}{"vs base":>9}{"null":>8}{"p":>8}')
    for nm in names:
        sig=replay_registry(bars,nm)
        for sp in ("DEV","VAL"):
            m=S.split_mask(bars.index,sp)
            sel=(sig!=0)&m&valid
            d=np.where(sig>0,1,np.where(sig<0,-1,0))
            if sel.sum()<5:
                print(f'{nm:<22}{sp:<6}{int(sel.sum()):>6}'); continue
            st=P.excursion_stats(up,dn,d,sel)
            ce=int((d[sel]>0).sum()); pe=int((d[sel]<0).sum())
            base=(ce*S.baseline_ratio(up,dn,1,m)+pe*S.baseline_ratio(up,dn,-1,m))/max(1,ce+pe)
            nl=S.fast_same_day_null(bars.index,up,dn,d,sel,draws=3000)
            cl=P.clustering(bars.index,np.flatnonzero(sel),24)
            print(f'{nm:<22}{sp:<6}{st["n"]:>6}{cl["days"]:>6}{st["ratio"]:>8.3f}{st["ratio"]-base:>+9.3f}{nl.get("null_mean",float("nan")):>8.3f}{nl.get("p_value",float("nan")):>8.4f}')
