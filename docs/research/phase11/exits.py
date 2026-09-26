"""Phase 10 sec7-sec10 -- exit families. All causal, all EOD-capped.

Entry fill is bar (i+1) OPEN -- the first price a live engine could transact
at. Exit fill is the OPEN of the bar after the exit condition is met, except
for the EOD cap which fills at the last bar's close. No exit uses a future
high, low or extremum.
"""
import os,sys; SP=os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0,SP)
import numpy as np, pandas as pd
import entry as E

def _day_bounds(bars):
    days=bars.index.normalize().to_numpy()
    ch=np.r_[True, days[1:]!=days[:-1]]
    starts=np.flatnonzero(ch); ends=np.r_[starts[1:], len(days)]
    day_end=np.empty(len(days),dtype=int)
    for a,b in zip(starts,ends): day_end[a:b]=b-1
    return day_end

def simulate(bars, sig, family, *, max_bars=24, invalidation_atr=0.5,
             entry_delay=1):
    """Returns a DataFrame of completed trades in UNDERLYING points."""
    n=len(bars)
    o=bars["open"].to_numpy(float); h=bars["high"].to_numpy(float)
    l=bars["low"].to_numpy(float);  c=bars["close"].to_numpy(float)
    _,_,_,pdh,pdl,atr = E.raw_signal(bars)
    day_end=_day_bounds(bars)
    rows=[]
    for i in np.flatnonzero(sig!=0):
        d=int(sig[i]); ent=i+entry_delay
        if ent>=n or ent>day_end[i]: continue
        entry_px=o[ent]
        lvl = pdl[i] if d>0 else pdh[i]
        if not np.isfinite(lvl): continue
        # the reversion objective: the midpoint of the prior-day range
        other = pdh[i] if d>0 else pdl[i]
        if not np.isfinite(other): continue
        target = (lvl+other)/2.0
        stop = lvl - invalidation_atr*atr[i] if d>0 else lvl + invalidation_atr*atr[i]
        last = min(day_end[ent], ent+max_bars)
        exit_px=None; exit_i=None; why=None
        for j in range(ent, last+1):
            if family in ("C_invalidation","D_time_plus_invalidation"):
                if (d>0 and c[j]<=stop) or (d<0 and c[j]>=stop):
                    k=min(j+1,last); exit_px=o[k] if k>j else c[j]; exit_i=k; why="INVALIDATED"; break
            if family in ("B_return_to_level","D_time_plus_invalidation"):
                if (d>0 and h[j]>=target) or (d<0 and l[j]<=target):
                    exit_px=target; exit_i=j; why="TARGET"; break
        if exit_px is None:
            exit_i=last; exit_px=c[last]; why="TIME" if last<day_end[ent] else "EOD"
        pts = (exit_px-entry_px) if d>0 else (entry_px-exit_px)
        rows.append(dict(i=i, entry_i=ent, exit_i=exit_i, direction=d,
                         entry=entry_px, exit=exit_px, points=pts, why=why,
                         bars_held=exit_i-ent, day=bars.index[i].normalize()))
    return pd.DataFrame(rows)

def stats(tr):
    if tr is None or tr.empty: return None
    p=tr.points.to_numpy(float)
    wins=p>0
    return dict(n=len(p), mean=p.mean(), median=float(np.median(p)),
                win=float(wins.mean()*100), total=p.sum(),
                p10=float(np.percentile(p,10)), p90=float(np.percentile(p,90)),
                worst=p.min(), best=p.max(),
                bars=float(tr.bars_held.mean()),
                mins=float(tr.bars_held.mean()*5))
