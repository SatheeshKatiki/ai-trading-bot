"""Phase 10 sec10/sec17 -- realized economics vs independently recomputed friction."""
import os,sys; SP=os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0,SP)
import numpy as np, pandas as pd
import p8lib as P, split as S, entry as E, setup as U, selection as SEL, exits as X

SESSION_BARS=75.0
# Every constant below is MEASURED (repo calibration 2026-09-21) except where
# marked. Independently re-entered here rather than copied from Phase 9 code.
PROF={
 "NIFTY":    dict(delta=0.42,  spread=0.21, regimes={"DTE<=1":(0.32,13.4), "DTE 8-14":(1.03,4.0)}),
 "BANKNIFTY":dict(delta=0.376, spread=0.35, regimes={"DTE 8-14":(1.38,5.9)}),
 "SENSEX":   dict(delta=0.305, spread=0.21, regimes={"UNMEASURED":(0.76,None)}),
 "FINNIFTY": dict(delta=None,  spread=None, regimes={"UNMEASURED":(None,None)}),
}

def friction_points(instrument, spot, bars_held, regime):
    p=PROF[instrument]; prem_pct,theta=p["regimes"][regime]
    if p["delta"] is None or prem_pct is None or theta is None: return float("nan")
    prem=spot*prem_pct/100.0
    hold=bars_held/SESSION_BARS
    return (p["spread"]/100.0*prem + theta/100.0*prem*hold)/p["delta"]

def run(bars,label,instrument,policy=SEL.policy_A):
    eps=U.episodes(bars); sig=policy(bars,eps)
    close=bars["close"].to_numpy(float)
    print(f"\n### {label}  ({instrument})")
    print(f'  {"exit family":<28}{"n":>5}{"realized":>10}{"held(min)":>11}'
          + "".join(f'{r:>16}' for r in PROF[instrument]["regimes"]))
    for fam,mb in (("A_fixed_time",6),("A_fixed_time",12),("A_fixed_time",24),
                   ("B_return_to_level",48),("C_invalidation",48),
                   ("D_time_plus_invalidation",24)):
        tr=X.simulate(bars,sig,fam,max_bars=mb); st=X.stats(tr)
        if not st: continue
        spot=close[tr.entry_i.to_numpy()].mean()
        cells=[]
        for r in PROF[instrument]["regimes"]:
            fr=friction_points(instrument,spot,st["bars"],r)
            cells.append(f'{st["mean"]-fr:>+16.1f}' if fr==fr else f'{"n/a":>16}')
        nm=f'{fam}({mb})' if fam=="A_fixed_time" else fam
        print(f'  {nm:<28}{st["n"]:>5}{st["mean"]:>+10.1f}{st["mins"]:>11.0f}'+"".join(cells))

if __name__=="__main__":
    print("=== REALIZED underlying points MINUS option friction (net, per trade) ===")
    print("    Phase 9 used MFE-MAE (excursion asymmetry, an UPPER BOUND needing a")
    print("    perfect exit). This uses REALIZED returns from causal exit rules.")
    nf=P.load_nifty()
    for sp in ("DEV","VAL"):
        run(nf[S.split_mask(nf.index,sp)],f"NIFTY {sp}","NIFTY")
    run(P.load_csv("BSE_SENSEX-INDEX_5Min.csv").loc["2026-04-01":],"SENSEX FRESH","SENSEX")
    run(P.load_csv("NSE_NIFTYBANK-INDEX_5Min.csv"),"BANKNIFTY FRESH","BANKNIFTY")
