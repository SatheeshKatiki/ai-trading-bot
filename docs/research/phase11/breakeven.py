"""Phase 11 sec30 -- the break-even economic model.

Rather than model an option P&L from data that does not exist, invert the
question: how large must the UNDERLYING move be to cover measured option
friction? That requires only OBSERVED constants and the measured realized
return, and it cannot be inflated by a fabricated premium path.
"""
import os,sys; SP=os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0,SP)
import numpy as np, pandas as pd
import p8lib as P, split as S, entry as E, setup as U, selection as SEL, exits as X, tf as TF

SESSION_BARS_5M = 75.0
PROF = {
 "NIFTY":     dict(delta=0.42,  spread=0.21, prem=0.32,  theta=13.4, src="OBSERVED"),
 "NIFTY_far": dict(delta=0.42,  spread=0.21, prem=1.03,  theta=4.0,  src="OBSERVED"),
 "BANKNIFTY": dict(delta=0.376, spread=0.35, prem=1.38,  theta=5.9,  src="OBSERVED"),
 "SENSEX":    dict(delta=0.305, spread=0.21, prem=0.76,  theta=None, src="theta UNAVAILABLE"),
}

def breakeven_points(key, spot, hold_min):
    p = PROF[key]
    if p["theta"] is None: return float("nan")
    prem = spot * p["prem"] / 100.0
    hold = (hold_min / 5.0) / SESSION_BARS_5M     # fraction of a session
    return (p["spread"]/100.0*prem + p["theta"]/100.0*prem*hold) / p["delta"]

def realized(bars5, instrument, hold_min):
    eps = U.episodes(bars5)
    if eps.empty: return None
    sig = SEL.policy_A(bars5, eps)
    tr = X.simulate(bars5, sig, "A_fixed_time", max_bars=max(1, hold_min//5))
    st = X.stats(tr)
    if not st: return None
    spot = bars5["close"].to_numpy(float)[tr.entry_i.to_numpy()].mean()
    return st, spot

if __name__ == "__main__":
    nf = P.load_nifty()
    print("=== sec30 BREAK-EVEN: underlying points REQUIRED vs points DELIVERED ===")
    print("    friction uses only OBSERVED constants; no premium path is modelled\n")
    print(f'{"instrument":<12}{"window":<8}{"hold":>6}{"n":>5}{"delivered":>11}{"required":>10}{"margin":>9}')
    for sp in ("DEV","VAL"):
        b = nf[S.split_mask(nf.index, sp)]
        for hold in (30, 60, 120):
            out = realized(b, "NIFTY", hold)
            if not out: continue
            st, spot = out
            for key,lab in (("NIFTY","NIFTY DTE<=1"),("NIFTY_far","NIFTY DTE8-14")):
                req = breakeven_points(key, spot, hold)
                print(f'{lab:<12}{sp:<8}{hold:>6}{st["n"]:>5}{st["mean"]:>+11.1f}{req:>10.1f}{st["mean"]-req:>+9.1f}')
        print()
    for lab,f,sl,key in (("BANKNIFTY","NSE_NIFTYBANK-INDEX_5Min.csv",None,"BANKNIFTY"),
                         ("SENSEX","BSE_SENSEX-INDEX_5Min.csv","2026-04-01","SENSEX")):
        d = P.load_csv(f); d = d.loc[sl:] if sl else d
        for hold in (30, 60, 120):
            out = realized(d, lab, hold)
            if not out: continue
            st, spot = out
            req = breakeven_points(key, spot, hold)
            mar = st["mean"]-req
            print(f'{lab:<12}{"FRESH":<8}{hold:>6}{st["n"]:>5}{st["mean"]:>+11.1f}'
                  + (f'{req:>10.1f}{mar:>+9.1f}' if req==req else f'{"n/a":>10}{"n/a":>9}'))
        print()
    print("=== sec18 WHY BANKNIFTY COSTS MORE PER POINT ===")
    for key in ("NIFTY","BANKNIFTY"):
        p=PROF[key]
        ratio = (p["prem"]/100.0) / p["delta"]
        print(f'  {key:<10} premium {p["prem"]:>5.2f}% of spot / delta {p["delta"]:.3f}'
              f'  -> friction scales as {ratio*100:.2f} per 1% cost')
    r = (PROF["BANKNIFTY"]["prem"]/PROF["BANKNIFTY"]["delta"]) / (PROF["NIFTY"]["prem"]/PROF["NIFTY"]["delta"])
    print(f'  BANKNIFTY friction per underlying point is {r:.1f}x NIFTY (DTE<=1 basis)')
