"""Phase 9 sec6/sec14 -- the timing curve. How much of the move is already
gone by the time the current architecture enters?"""
import os, sys, pickle
SP=os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0,SP)
import numpy as np, pandas as pd
import p8lib as P, split as S, timing as T

bars=P.load_nifty(); n=len(bars)
fwd=pickle.load(open(os.path.join(SP,'fwd.pkl'),'rb'))
cond=pickle.load(open(os.path.join(SP,'cond.pkl'),'rb'))
ex=pickle.load(open(os.path.join(SP,'extras.pkl'),'rb'))
pdl=np.load(os.path.join(SP,'pdl.npy')); pdh=np.load(os.path.join(SP,'pdh.npy'))
up,dn=fwd[24]
W=8

def chain(side):
    """side 'low' -> long/PDL ; 'high' -> short/PDH"""
    b = side=="low"; dv = 1 if b else -1
    ctx = cond['htf_bull' if b else 'htf_bear'] & cond['regime_ok'] & cond['not_blocked']
    lvl = pdl if b else pdh
    T1 = T.rejection_events(bars, lvl, side) & ctx                 # earliest causal
    struct = (ex['ranging']&ex['choch_up' if b else 'choch_dn']) | (ex['trending']&ex['bos_up' if b else 'bos_dn'])
    trig = cond['trigger_bull' if b else 'trigger_bear']
    rr   = cond['rr_ok_bull' if b else 'rr_ok_bear']
    rsi  = cond['rsi_bull' if b else 'rsi_bear']
    p1 = np.flatnonzero(T1)
    p2 = T.first_after(struct, p1, W)
    p3 = T.first_after(rsi & trig, np.where(p2>=0,p2,10**9), W)
    p3 = np.where(p2>=0, p3, -1)
    p4 = T.first_after(rsi & trig & rr, np.where(p2>=0,p2,10**9), W)
    p4 = np.where(p2>=0, p4, -1)
    return dv, p1, p2, p3, p4

print("=== sec6 TIMING CURVE  (NIFTY full sample, horizon 24, PDH/PDL setups) ===")
print(f'{"stamp":<34}{"dir":<7}{"n":>6}{"meanMFE":>9}{"meanMAE":>9}{"ratio":>8}{"MFE>MAE":>9}{"lag":>6}{"travelled":>11}')
store={}
for side,lab in (("low","LONG / PDL"),("high","SHORT / PDH")):
    dv,p1,p2,p3,p4 = chain(side)
    store[side]=(dv,p1,p2,p3,p4)
    base=S.baseline_ratio(up,dn,dv,np.ones(n,bool))
    for nm,pp in (("T1 rejection (earliest causal)",p1),
                  ("T2 + structure confirmation",p2),
                  ("T3 + RSI & price-action trigger",p3),
                  ("T4 + R:R gate",p4)):
        st=T.excursion_at(up,dn,np.asarray(pp),dv)
        if st['n']==0: print(f'{nm:<34}{lab:<7}{0:>6}'); continue
        tr,lag = T.travelled(bars,p1,np.asarray(pp),dv) if nm!="T1 rejection (earliest causal)" else (0.0,0.0)
        print(f'{nm:<34}{lab:<7}{st["n"]:>6}{st["mfe"]:>9.1f}{st["mae"]:>9.1f}{st["ratio"]:>8.3f}{st["win"]:>8.1f}%{lag:>6.1f}{tr:>+11.1f}')
    print(f'{"   (unconditional baseline)":<34}{lab:<7}{"":>6}{"":>9}{"":>9}{base:>8.3f}')
    print()
pickle.dump(store, open(os.path.join(SP,'chain.pkl'),'wb'))

print("=== sec14 TIME-TO-MOVE: bars to MFE / MAE from each stamp (long+short pooled) ===")
highs=bars['high'].to_numpy(float); lows=bars['low'].to_numpy(float); close=bars['close'].to_numpy(float)
days=bars.index.normalize().to_numpy()
def time_to(pos,dv,H=24):
    tm=[];ta=[]
    for p in pos:
        if p<0 or p+1>=n: continue
        end=min(p+1+H,n); same=days[p+1:end]==days[p]
        if not same.any(): continue
        hi=highs[p+1:end][same]; lo=lows[p+1:end][same]
        fav = hi-close[p] if dv>0 else close[p]-lo
        adv = close[p]-lo if dv>0 else hi-close[p]
        tm.append(int(np.argmax(np.maximum.accumulate(fav)==fav.max())+1))
        ta.append(int(np.argmax(np.maximum.accumulate(adv)==adv.max())+1))
    return (np.median(tm) if tm else np.nan, np.median(ta) if ta else np.nan, len(tm))
print(f'{"stamp":<34}{"med bars to MFE":>17}{"med bars to MAE":>17}{"n":>7}')
for nm,i in (("T1 rejection",1),("T2 + structure",2),("T3 + trigger",3),("T4 + R:R",4)):
    allm=[];alla=[];tot=0
    for side in ("low","high"):
        dv,*ps = store[side]; pp=np.asarray(ps[i-1])
        a,b,c = time_to(pp[pp>=0],dv)
        if c: allm.append(a); alla.append(b); tot+=c
    print(f'{nm:<34}{np.nanmean(allm):>17.1f}{np.nanmean(alla):>17.1f}{tot:>7}')
