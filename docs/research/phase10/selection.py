"""Phase 10 sec5 -- selection policies. All causal: each picks using only
information available at the bar it picks.

A  first valid signal overall (one trade per day, whichever comes first)
B  one signal per (day, direction) -- first episode of each day-side
C  one trade per day, first signal of the day        [= A; kept distinct
   only because sec5 lists them separately -- measured and reported as equal]
D  first signal of the day-side that is within TIGHT_BAND of the level
   (causal: the tighter distance is known at the bar)
E  first signal of the day-side whose bar closes in the reverting direction
   (causal: close vs open of that same bar)
"""
import os,sys; SP=os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0,SP)
import numpy as np, pandas as pd
import entry as E, setup as U

TIGHT_BAND = 0.10   # pre-declared

def _entries_from_rows(n, rows):
    sig=np.zeros(n,dtype=int)
    for pos,d in rows: sig[pos]=d
    return sig

def policy_A(bars, eps):
    """First valid signal of each DAY, any direction."""
    n=len(bars); rows=[]
    for day,g in eps.groupby("day"):
        r=g.sort_values("start").iloc[0]
        rows.append((int(r.start), int(r.direction)))
    return _entries_from_rows(n,rows)

def policy_B(bars, eps):
    """First episode of each (day, direction)."""
    n=len(bars); rows=[]
    for (day,d),g in eps.groupby(["day","direction"]):
        r=g.sort_values("start").iloc[0]
        rows.append((int(r.start), int(d)))
    return _entries_from_rows(n,rows)

policy_C = policy_A   # identical by construction; reported as such

def policy_D(bars, eps, tight=TIGHT_BAND):
    """First bar of the day-side within `tight` ATR of the level."""
    n=len(bars); close=bars["close"].to_numpy(float)
    _,_,_,pdh,pdl,atr = E.raw_signal(bars)
    rows=[]
    for (day,d),g in eps.groupby(["day","direction"]):
        picked=None
        for _,r in g.sort_values("start").iterrows():
            for i in range(int(r.start), int(r.end)+1):
                lvl = pdl[i] if d>0 else pdh[i]
                if np.isfinite(lvl) and abs(close[i]-lvl) <= tight*atr[i]:
                    picked=i; break
            if picked is not None: break
        if picked is not None: rows.append((picked,int(d)))
    return _entries_from_rows(n,rows)

def policy_E(bars, eps):
    """First bar of the day-side that closes in the reverting direction."""
    n=len(bars); close=bars["close"].to_numpy(float); open_=bars["open"].to_numpy(float)
    rows=[]
    for (day,d),g in eps.groupby(["day","direction"]):
        picked=None
        for _,r in g.sort_values("start").iterrows():
            for i in range(int(r.start), int(r.end)+1):
                if (d>0 and close[i]>open_[i]) or (d<0 and close[i]<open_[i]):
                    picked=i; break
            if picked is not None: break
        if picked is not None: rows.append((picked,int(d)))
    return _entries_from_rows(n,rows)

POLICIES = {"A_first_of_day":policy_A, "B_first_per_day_side":policy_B,
            "D_tight_band_first":policy_D, "E_reverting_close_first":policy_E}
