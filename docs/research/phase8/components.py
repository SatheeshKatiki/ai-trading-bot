"""Phase 8 sec14/16/17/30 -- liquidity types, FVG, RSI, failure modes.
DEV+VAL only: the holdout has been spent."""
import numpy as np, pandas as pd, pickle
import p8lib as P, split as S
from trading_bot.strategies.rsi_smc_options_buyer.config import RsiSmcConfig
from trading_bot.strategies.rsi_smc_options_buyer import levels as L, liquidity as LQ, structure as ST

bars=P.load_nifty(); fwd=pickle.load(open("fwd.pkl","rb")); up,dn=fwd[24]
cond=pickle.load(open("cond.pkl","rb")); ex=pickle.load(open("extras.pkl","rb"))
cfg=RsiSmcConfig()
devval = S.split_mask(bars.index,"DEV") | S.split_mask(bars.index,"VAL")
valid=np.isfinite(up)&np.isfinite(dn)

def score(mask, direction_value):
    d=np.full(len(bars),direction_value,int)
    sel=np.asarray(mask,bool)&devval&valid
    if sel.sum()<20: return None
    st=P.excursion_stats(up,dn,d,sel)
    base=S.baseline_ratio(up,dn,direction_value,devval)
    return st["n"], st["ratio"], st["ratio"]-base

# --- sec14: liquidity level families, measured separately -------------
print("=== sec14  LIQUIDITY TYPE, sweep of each family alone (DEV+VAL) ===")
daily=L.compute_daily_levels(bars)
view_pool_low=np.full(len(bars),np.nan); view_pool_high=np.full(len(bars),np.nan)
start=0
while start<len(bars):
    stop=min(start+200,len(bars)); lo=max(0,start-P.LIVE_CONTEXT_BARS)
    w=bars.iloc[lo:stop]
    if len(w)>=cfg.min_bars:
        ST.clear_cache(); v=ST.build(w,cfg,symbol="NIFTY"); off=start-lo
        view_pool_low[start:stop]=v.pool_low[off:]; view_pool_high[start:stop]=v.pool_high[off:]
    start=stop
close=bars["close"].to_numpy(float)
families={
 "EQL/EQH pools": (view_pool_low, view_pool_high),
 "prev-day H/L":  (daily.prev_day_low, daily.prev_day_high),
 "session H/L":   (daily.session_low, daily.session_high),
 "rolling extreme": LQ.rolling_extreme_levels(bars,20,5),
}
print(f'{"family":<18}{"dir":<7}{"n":>7}{"ratio":>8}{"vs base":>9}')
for name,(lowlvl,highlvl) in families.items():
    r=LQ.key_level_sweeps(bars,np.asarray(lowlvl,float),np.asarray(highlvl,float),5,40)
    for lab,mask,dv in (("long",r.bullish,1),("short",r.bearish,-1)):
        s=score(mask,dv)
        print(f'{name:<18}{lab:<7}'+(f'{s[0]:>7}{s[1]:>8.3f}{s[2]:>+9.3f}' if s else f'{"--":>7}'))

# --- sec16/17: FVG and RSI as standalone conditions --------------------
print()
print("=== sec16/17  FVG and RSI alone (DEV+VAL) ===")
print(f'{"feature":<26}{"dir":<7}{"n":>7}{"ratio":>8}{"vs base":>9}')
for name,mask,dv in (("in bullish FVG",ex["in_bull_fvg"],1),("in bearish FVG",ex["in_bear_fvg"],-1),
                     ("RSI bullish state",cond["rsi_bull"],1),("RSI bearish state",cond["rsi_bear"],-1),
                     ("trigger bull",cond["trigger_bull"],1),("trigger bear",cond["trigger_bear"],-1),
                     ("RR ok bull",cond["rr_ok_bull"],1),("RR ok bear",cond["rr_ok_bear"],-1),
                     ("in bullish OB",ex["in_bull_ob"],1),("in bearish OB",ex["in_bear_ob"],-1)):
    s=score(mask,dv)
    print(f'{name:<26}{dv>0 and "long" or "short":<7}'+(f'{s[0]:>7}{s[1]:>8.3f}{s[2]:>+9.3f}' if s else f'{"--":>7} (n too small)'))

# --- sec7: redundancy -------------------------------------------------
print()
print("=== sec7  PAIRWISE CORRELATION of the bull conditions (DEV+VAL) ===")
names=["htf_bull","regime_ok","level_near_bull","sweep_bull","struct_bull","rsi_bull","trigger_bull","rr_ok_bull"]
M=np.vstack([np.asarray(cond[n],bool)[devval] for n in names]).astype(float)
C=np.corrcoef(M)
print("      "+"".join(f'{n[:9]:>10}' for n in names))
for i,n in enumerate(names):
    print(f'{n[:9]:<10}'+"".join(f'{C[i,j]:>10.2f}' for j in range(len(names))))
