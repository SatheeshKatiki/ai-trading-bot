"""Phase 8 §6/§7 -- the complete information funnel, live-equivalent context."""
from __future__ import annotations

import numpy as np
import pandas as pd

import p8lib as P
from trading_bot.strategies.rsi_smc_options_buyer.config import RsiSmcConfig

HORIZONS = (6, 12, 24, 48)
PRIMARY = 24   # 2 hours on 5-minute bars; declared before looking at results


def run(bars, cfg, label=""):
    sig, cond, diag = P.replay_conditions(bars, cfg, chunk=200)
    sig_et = P.edge_trigger_np(sig)
    fwd = P.forward_excursions(bars, HORIZONS)
    return sig, sig_et, cond, diag, fwd


def funnel_table(bars, cond, fwd, horizon, side):
    """Cumulative AND of the chain, one stage at a time."""
    n = len(bars)
    up, dn = fwd[horizon]
    if side == "bull":
        chain = ["htf_bull", "regime_ok", "level_near_bull", "sweep_bull",
                 "struct_bull", "rsi_bull", "trigger_bull", "rr_ok_bull",
                 "not_blocked"]
        direction = np.ones(n, dtype=int)
    else:
        chain = ["htf_bear", "regime_ok", "level_near_bear", "sweep_bear",
                 "struct_bear", "rsi_bear", "trigger_bear", "rr_ok_bear",
                 "not_blocked"]
        direction = -np.ones(n, dtype=int)

    rows = []
    acc = np.ones(n, dtype=bool)
    base = P.excursion_stats(up, dn, direction, acc)
    rows.append(("(all bars)", n, base))
    prev_n = n
    for name in chain:
        acc = acc & cond[name]
        st = P.excursion_stats(up, dn, direction, acc)
        rows.append((name, int(acc.sum()), st))
        prev_n = int(acc.sum())
    return rows


def marginal_table(bars, cond, fwd, horizon, side):
    """Each condition ALONE, against the same labels. Isolates whether a
    filter carries information or merely reduces count."""
    n = len(bars)
    up, dn = fwd[horizon]
    if side == "bull":
        names = ["htf_bull", "regime_ok", "level_near_bull", "sweep_bull",
                 "struct_bull", "rsi_bull", "trigger_bull", "rr_ok_bull"]
        direction = np.ones(n, dtype=int)
    else:
        names = ["htf_bear", "regime_ok", "level_near_bear", "sweep_bear",
                 "struct_bear", "rsi_bear", "trigger_bear", "rr_ok_bear"]
        direction = -np.ones(n, dtype=int)
    out = []
    for name in names:
        st = P.excursion_stats(up, dn, direction, cond[name])
        out.append((name, st))
    return out


def fmt(rows, title):
    print(f"\n### {title}")
    print(f"{'stage':<18}{'retained':>9}{'ret %':>8}{'n lbl':>8}{'MFE>MAE':>9}{'MFE/MAE':>9}{'mMFE':>8}{'mMAE':>8}")
    total = rows[0][1]
    for name, count, st in rows:
        if st.get("n", 0) == 0:
            print(f"{name:<18}{count:>9}{count/total*100:>7.1f}%{0:>8}{'--':>9}{'--':>9}{'--':>8}{'--':>8}")
            continue
        print(f"{name:<18}{count:>9}{count/total*100:>7.1f}%{st['n']:>8}"
              f"{st['mfe_gt_mae']:>8.1f}%{st['ratio']:>9.3f}"
              f"{st['mean_mfe']:>8.1f}{st['mean_mae']:>8.1f}")


if __name__ == "__main__":
    cfg = RsiSmcConfig()
    bars = P.load_nifty()
    print(f"NIFTY 5-min: {bars.index[0]} .. {bars.index[-1]}  {len(bars):,} bars, "
          f"{bars.index.normalize().nunique()} days")
    sig, sig_et, cond, diag, fwd = run(bars, cfg)

    pos = np.flatnonzero(sig_et != 0)
    print(f"\nLIVE-EQUIVALENT entries: {len(pos)}  "
          f"(CE {int((sig_et==1).sum())}, PE {int((sig_et==-1).sum())})")

    print("\n== EFFECTIVE SAMPLE SIZE ==")
    for h in HORIZONS:
        c = P.clustering(bars.index, pos, h)
        print(f"  horizon {h:>2}: raw {c['raw']}, days {c['days']}, "
              f"per-day {c['per_day']:.2f}, overlapping {c['overlapping']}, "
              f"effective (non-overlapping) {c['effective']}")

    for side in ("bull", "bear"):
        fmt(funnel_table(bars, cond, fwd, PRIMARY, side),
            f"FUNNEL -- {side.upper()} chain, horizon {PRIMARY} bars")

    for side in ("bull", "bear"):
        print(f"\n### MARGINAL -- {side.upper()}, each condition alone, horizon {PRIMARY}")
        print(f"{'condition':<18}{'n':>8}{'MFE>MAE':>9}{'MFE/MAE':>9}")
        for name, st in marginal_table(bars, cond, fwd, PRIMARY, side):
            if st.get("n", 0) == 0:
                print(f"{name:<18}{0:>8}{'--':>9}{'--':>9}")
            else:
                print(f"{name:<18}{st['n']:>8}{st['mfe_gt_mae']:>8.1f}%{st['ratio']:>9.3f}")

    np.save("sig_et.npy", sig_et)
    np.save("pos.npy", pos)
    import pickle
    with open("cond.pkl", "wb") as f:
        pickle.dump({k: v for k, v in cond.items()}, f)
    with open("diag.pkl", "wb") as f:
        pickle.dump({k: v for k, v in diag.items()}, f)
    print("\n[saved sig_et.npy, pos.npy, cond.pkl, diag.pkl]")
