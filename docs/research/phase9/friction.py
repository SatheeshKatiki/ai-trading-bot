"""Phase 9 sec16/17 -- option-friction audit, with every input classified.

Phase 8 used theta = 9.7 %/session. That is backtesting_engine's MODEL
constant, not a measurement. The repository's own calibration (2026-09-21,
191 live contracts, 396 ATM contract-days) measured 13.4 %/session at DTE<=1
and 4.0 % at DTE 8-14, with premium moving the other way (0.32 % of spot at
DTE1 vs 1.03 % at DTE15+). Using one model constant for both is wrong in both
directions, so this reports a RANGE across the measured DTE regimes.

INPUT CLASSIFICATION
  premium % of spot     OBSERVED per DTE regime (NIFTY); OBSERVED (BANKNIFTY,
                        SENSEX) but SENSEX is a single chain snapshot
  delta                 OBSERVED per instrument
  round-trip spread     OBSERVED (NIFTY, BANKNIFTY); ASSUMED for SENSEX
                        (copies NIFTY -- BSE chain not measured)
  theta %/session       OBSERVED per DTE regime (NIFTY, BANKNIFTY);
                        UNAVAILABLE for SENSEX
  IV / vega             UNAVAILABLE -- not modelled, not fabricated
  historical option quotes  UNAVAILABLE -- Fyers serves none for expired
                        symbols, so none of this is a backtest of real fills
"""
import os, sys, pickle
SP=os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0,SP)
import numpy as np
import p8lib as P, split as S, timing as T
from trading_bot.strategies.rsi_smc_options_buyer import levels as L
from shared.indicators import atr as _atr

SESSION_BARS = 75.0
PROFILE = {
  # instrument: {dte_regime: (premium_pct_of_spot, theta_pct_per_session)}, delta, spread_pct
  "NIFTY":     {"regimes": {"DTE<=1": (0.32, 13.4), "DTE 8-14": (1.03, 4.0)},
                "delta": 0.42, "spread_pct": 0.21, "spread_src": "OBSERVED"},
  "BANKNIFTY": {"regimes": {"DTE 8-14": (1.38, 5.9)},
                "delta": 0.376, "spread_pct": 0.35, "spread_src": "OBSERVED"},
  "SENSEX":    {"regimes": {"theta UNAVAILABLE": (0.76, None)},
                "delta": 0.305, "spread_pct": 0.21, "spread_src": "ASSUMED (NIFTY)"},
}

def masks(bars, atr_near=0.25):
    daily=L.compute_daily_levels(bars); a=_atr(bars,14).to_numpy(float)
    close=bars['close'].to_numpy(float); out={}
    for side,b in (("low",True),("high",False)):
        lvl = daily.prev_day_low if b else daily.prev_day_high
        out.setdefault('P1',{})['bull' if b else 'bear']=T.rejection_events(bars,lvl,side)
        out.setdefault('P4',{})['bull' if b else 'bear']=np.isfinite(lvl)&(np.abs(close-lvl)<=atr_near*a)
        out.setdefault('P5',{})['bull' if b else 'bear']=T.reclaim_events(bars,lvl,side,6)
    return out

def analyse(bars, instrument, fam_key, horizons=(6,12,24,48)):
    fams=masks(bars); fam=fams[fam_key]
    raw=np.select([fam['bear'],fam['bull']],[-1,1],default=0).astype(int)
    sig=P.edge_trigger_np(raw)
    fwd=P.forward_excursions(bars,horizons)
    close=bars['close'].to_numpy(float)
    prof=PROFILE[instrument]; delta=prof['delta']
    print(f"\n### {instrument} / {fam_key}   ({bars.index[0].date()}..{bars.index[-1].date()})")
    print(f"    delta {delta} OBSERVED | spread {prof['spread_pct']}% {prof['spread_src']}")
    for rname,(prem_pct,theta_pct) in prof['regimes'].items():
        print(f"    -- {rname}: premium {prem_pct}% of spot OBSERVED, "
              f"theta {theta_pct if theta_pct is not None else 'UNAVAILABLE'}"
              f"{'%/session OBSERVED' if theta_pct is not None else ''}")
        print(f'      {"bars":>5}{"min":>6}{"n":>6}{"MFE":>8}{"MAE":>8}{"MFE-MAE":>9}{"friction":>10}{"net":>8}')
        for h in horizons:
            up,dn=fwd[h]; valid=np.isfinite(up)&np.isfinite(dn)
            sel=(sig!=0)&valid; d=np.where(sig>0,1,np.where(sig<0,-1,0))
            if sel.sum()<20: continue
            st=P.excursion_stats(up,dn,d,sel)
            spot=close[sel].mean(); prem=spot*prem_pct/100.0
            hold=h/SESSION_BARS
            if theta_pct is None:
                fr=float('nan')
            else:
                fr=(prof['spread_pct']/100.0*prem + theta_pct/100.0*prem*hold)/delta
            asym=st['mean_mfe']-st['mean_mae']
            net = asym-fr if fr==fr else float('nan')
            frs = f'{fr:>10.1f}' if fr==fr else f'{"n/a":>10}'
            nets= f'{net:>+8.1f}' if net==net else f'{"n/a":>8}'
            print(f'      {h:>5}{h*5:>6}{st["n"]:>6}{st["mean_mfe"]:>8.1f}{st["mean_mae"]:>8.1f}{asym:>+9.1f}{frs}{nets}')

if __name__=="__main__":
    nf=P.load_nifty()
    analyse(nf,"NIFTY","P4")
    sx=P.load_csv("BSE_SENSEX-INDEX_5Min.csv").loc["2026-04-01":]
    analyse(sx,"SENSEX","P4")
    bn=P.load_csv("NSE_NIFTYBANK-INDEX_5Min.csv")
    analyse(bn,"BANKNIFTY","P4")
