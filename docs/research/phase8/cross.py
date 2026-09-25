"""Phase 8 sec20 -- cross-instrument, restricted to <= VAL end so the
NIFTY holdout window is not burned on another instrument."""
import numpy as np, pandas as pd, pickle
import p8lib as P, split as S, validate as V
from trading_bot.strategies.rsi_smc_options_buyer.config import RsiSmcConfig

CUT = pd.Timestamp("2026-03-31 23:59")
cfg = RsiSmcConfig()

for label, fname in (("SENSEX","BSE_SENSEX-INDEX_5Min.csv"),
                     ("BANKNIFTY","NSE_NIFTYBANK-INDEX_5Min.csv")):
    df = P.load_csv(fname)
    df = df.loc[:CUT]
    if len(df) < 1000:
        print(f"{label}: only {len(df)} bars before {CUT.date()} -- insufficient "
              f"pre-holdout history, skipped rather than burning the holdout")
        continue
    sig_r, cond, diag = P.replay_conditions(df, cfg, chunk=200, symbol=label)
    ex = P.replay_extras(df, cfg, chunk=200, symbol=label)
    fwd = P.forward_excursions(df, (24,))
    up, dn = fwd[24]
    masks = V.locked_candidates(cond, ex)
    valid = np.isfinite(up)&np.isfinite(dn)
    allm = np.ones(len(df), bool)
    print(f"\n=== {label}  {df.index[0].date()}..{df.index[-1].date()}  "
          f"{len(df):,} bars, {df.index.normalize().nunique()} days ===")
    print(f'  baseline long {S.baseline_ratio(up,dn,1,allm):.3f}  short {S.baseline_ratio(up,dn,-1,allm):.3f}')
    print(f'  {"candidate":<20}{"n":>6}{"days":>6}{"ratio":>8}{"vs base":>9}{"null":>8}{"p":>8}')
    for nm, m in masks.items():
        sig = P.edge_trigger_np(V.to_dir(m))
        sel = (sig!=0)&valid
        d = np.where(sig>0,1,np.where(sig<0,-1,0))
        if sel.sum()<5:
            print(f'  {nm:<20}{int(sel.sum()):>6}'); continue
        st = P.excursion_stats(up,dn,d,sel)
        ce=int((d[sel]>0).sum()); pe=int((d[sel]<0).sum())
        base=(ce*S.baseline_ratio(up,dn,1,allm)+pe*S.baseline_ratio(up,dn,-1,allm))/max(1,ce+pe)
        nl=S.fast_same_day_null(df.index,up,dn,d,sel,draws=3000)
        cl=P.clustering(df.index,np.flatnonzero(sel),24)
        print(f'  {nm:<20}{st["n"]:>6}{cl["days"]:>6}{st["ratio"]:>8.3f}{st["ratio"]-base:>+9.3f}'
              f'{nl.get("null_mean",float("nan")):>8.3f}{nl.get("p_value",float("nan")):>8.4f}')
