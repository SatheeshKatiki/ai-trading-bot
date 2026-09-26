"""Phase 9 sec27 -- try to destroy P4."""
import os, sys, pickle
SP=os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0,SP)
import numpy as np, pandas as pd
import p8lib as P, split as S, timing as T
from trading_bot.strategies.rsi_smc_options_buyer import levels as L
from shared.indicators import atr as _atr

ATR_NEAR=0.25

def score(bars,up,dn,bull,bear,mask=None):
    n=len(bars); raw=np.select([bear,bull],[-1,1],default=0).astype(int)
    sig=P.edge_trigger_np(raw); valid=np.isfinite(up)&np.isfinite(dn)
    sel=(sig!=0)&valid
    if mask is not None: sel=sel&mask
    if sel.sum()<20: return None
    d=np.where(sig>0,1,np.where(sig<0,-1,0)); st=P.excursion_stats(up,dn,d,sel)
    m = mask if mask is not None else np.ones(n,bool)
    ce=int((d[sel]>0).sum()); pe=int((d[sel]<0).sum())
    b=(ce*S.baseline_ratio(up,dn,1,m)+pe*S.baseline_ratio(up,dn,-1,m))/max(1,ce+pe)
    nl=S.fast_same_day_null(bars.index,up,dn,d,sel,draws=3000)
    return st['n'], st['ratio']-b, nl.get('p_value',np.nan)

def near(level, close, a, k=ATR_NEAR):
    lv=np.asarray(level,float)
    return np.isfinite(lv)&(np.abs(close-lv)<=k*a)

if __name__=="__main__":
    bars=P.load_nifty(); n=len(bars)
    fwd=pickle.load(open(os.path.join(SP,'fwd.pkl'),'rb')); up,dn=fwd[24]
    close=bars['close'].to_numpy(float); a=_atr(bars,14).to_numpy(float)
    daily=L.compute_daily_levels(bars)
    days=bars.index.normalize().to_numpy()
    rng=np.random.default_rng(20260926)

    print("=== sec27 ADVERSARIAL CONTROLS (NIFTY full sample, horizon 24) ===")
    print(f'{"control":<46}{"n":>7}{"vs base":>9}{"p(null)":>9}')
    r=score(bars,up,dn,near(daily.prev_day_low,close,a),near(daily.prev_day_high,close,a))
    print(f'{"P4 as declared (PDL long / PDH short)":<46}{r[0]:>7}{r[1]:>+9.3f}{r[2]:>9.4f}')

    # 1. Direction inverted -- if the effect is real, this should flip sign.
    r=score(bars,up,dn,near(daily.prev_day_high,close,a),near(daily.prev_day_low,close,a))
    print(f'{"  inverted direction (PDH long / PDL short)":<46}{r[0]:>7}{r[1]:>+9.3f}{r[2]:>9.4f}')

    # 2. Shuffled levels -- keep the level VALUES, attach them to other days.
    uniq=pd.unique(days)
    for trial in range(2):
        perm=rng.permutation(uniq); remap=dict(zip(uniq,perm))
        idx_by_day={d_:np.flatnonzero(days==d_) for d_ in uniq}
        shl=np.full(n,np.nan); shh=np.full(n,np.nan)
        for d_ in uniq:
            src=idx_by_day[remap[d_]]; tgt=idx_by_day[d_]
            if src.size==0: continue
            shl[tgt]=daily.prev_day_low[src[0]]; shh[tgt]=daily.prev_day_high[src[0]]
        r=score(bars,up,dn,near(shl,close,a),near(shh,close,a))
        lab=f'  shuffled PDH/PDL (trial {trial+1})'
        print(f'{lab:<46}'+(f'{r[0]:>7}{r[1]:>+9.3f}{r[2]:>9.4f}' if r else f'{"--":>7}'))

    # 3. Random intraday level drawn from the SAME day's range.
    for trial in range(2):
        rl=np.full(n,np.nan); rh=np.full(n,np.nan)
        for d_ in uniq:
            ix=np.flatnonzero(days==d_)
            lo=bars['low'].to_numpy(float)[ix].min(); hi=bars['high'].to_numpy(float)[ix].max()
            rl[ix]=rng.uniform(lo,hi); rh[ix]=rng.uniform(lo,hi)
        r=score(bars,up,dn,near(rl,close,a),near(rh,close,a))
        lab=f'  random level from same-day range (trial {trial+1})'
        print(f'{lab:<46}'+(f'{r[0]:>7}{r[1]:>+9.3f}{r[2]:>9.4f}' if r else f'{"--":>7}'))

    # 4. Other structural levels, same rule.
    for lab,lo_,hi_ in (("  session H/L instead of PDH/PDL",daily.session_low,daily.session_high),
                        ("  EQL/EQH pools instead",np.load(os.path.join(SP,'pool_low.npy')),
                         np.load(os.path.join(SP,'pool_high.npy')))):
        r=score(bars,up,dn,near(lo_,close,a),near(hi_,close,a))
        print(f'{lab:<46}'+(f'{r[0]:>7}{r[1]:>+9.3f}{r[2]:>9.4f}' if r else f'{"--":>7}'))

    # 5. Proximity band sensitivity (robustness, not optimisation).
    for k in (0.10,0.25,0.50,1.00):
        r=score(bars,up,dn,near(daily.prev_day_low,close,a,k),near(daily.prev_day_high,close,a,k))
        lab=f'  proximity band {k} ATR'
        print(f'{lab:<46}'+(f'{r[0]:>7}{r[1]:>+9.3f}{r[2]:>9.4f}' if r else f'{"--":>7}'))

    # 6. Regime conditioning.
    ex=pickle.load(open(os.path.join(SP,'extras.pkl'),'rb'))
    for lab,m in (("  trending only",np.asarray(ex['trending'],bool)),
                  ("  ranging only",np.asarray(ex['ranging'],bool))):
        r=score(bars,up,dn,near(daily.prev_day_low,close,a),near(daily.prev_day_high,close,a),mask=m)
        print(f'{lab:<46}'+(f'{r[0]:>7}{r[1]:>+9.3f}{r[2]:>9.4f}' if r else f'{"--":>7}'))
