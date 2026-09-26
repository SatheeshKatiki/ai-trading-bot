"""Phase 11 sec7/sec8 -- underlying economics by timeframe."""
import os,sys; SP=os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0,SP)
import numpy as np, pandas as pd
import p8lib as P, split as S, entry as E, setup as U, selection as SEL, exits as X, tf as TF, repro as R

def run_tf(bars5, tf, split_name, instrument="NIFTY"):
    b = TF.resample_session(bars5, tf)
    eps = U.episodes(b)
    if eps.empty: return None
    sig = SEL.policy_A(b, eps)
    out = dict(tf=tf, split=split_name, bars=len(b), days=b.index.normalize().nunique(),
               episodes=len(eps), setups=int((sig!=0).sum()))
    # excursion at the 120-min-equivalent horizon, for comparability with P8/P9
    h = TF.bars_for_minutes(120, tf)
    r = R.evaluate(b, sig, h=h, draws=2500)
    out.update(delta=r["delta"] if r else np.nan, p=r["p"] if r else np.nan,
               eff=r["eff"] if r else 0)
    for mins in TF.HOLD_MINUTES:
        mb = TF.bars_for_minutes(mins, tf)
        tr = X.simulate(b, sig, "A_fixed_time", max_bars=mb)
        st = X.stats(tr)
        out[f"ret{mins}"] = st["mean"] if st else np.nan
        out[f"n{mins}"] = st["n"] if st else 0
        out[f"held{mins}"] = st["mins"] if st else np.nan
    tr = X.simulate(b, sig, "C_invalidation", max_bars=TF.bars_for_minutes(240, tf))
    st = X.stats(tr)
    out["retC"] = st["mean"] if st else np.nan
    out["heldC"] = st["mins"] if st else np.nan
    return out

if __name__ == "__main__":
    nf = P.load_nifty()
    print("=== sec5/sec7/sec8  TIMEFRAME SCALING -- NIFTY, frozen rule, Policy A ===")
    print("    realized = mean underlying POINTS per trade under a causal exit")
    print()
    hdr = (f'{"tf":>4}{"split":<6}{"bars":>7}{"setups":>8}{"eff":>5}{"exc dlt":>9}{"p":>8}'
           + "".join(f'{"ret"+str(m)+"m":>9}' for m in TF.HOLD_MINUTES) + f'{"retC":>8}{"heldC":>8}')
    print(hdr)
    rows=[]
    for sp in ("DEV","VAL"):
        m = S.split_mask(nf.index, sp)
        for tf in TF.TIMEFRAMES:
            r = run_tf(nf[m], tf, sp)
            if not r: continue
            rows.append(r)
            print(f'{tf:>4}{sp:<6}{r["bars"]:>7}{r["setups"]:>8}{r["eff"]:>5}{r["delta"]:>+9.3f}{r["p"]:>8.4f}'
                  + "".join(f'{r["ret"+str(m2)]:>+9.1f}' for m2 in TF.HOLD_MINUTES)
                  + f'{r["retC"]:>+8.1f}{r["heldC"]:>8.0f}')
        print()
    pd.DataFrame(rows).to_csv(os.path.join(SP,"tf_nifty.csv"), index=False)
