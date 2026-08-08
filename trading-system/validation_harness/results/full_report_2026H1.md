# Production Strategy Validation Report

**Instrument:** NIFTY | **Period:** 2026-02-01 09:15:00 → 2026-07-31 15:25:00 | **Trading days:** 123 | **Initial capital per day-isolated run:** ₹100,000

**Regime day counts:** {'sideways': 62, 'trending': 39, 'gap_day': 13, 'low_volatility': 6, 'high_volatility': 3}

---

## Ranking (best → worst)

| Rank | Strategy | Verdict | Trades | Net Profit | Profit Factor | Win Rate | Max DD |
|---|---|---|---|---|---|---|---|
| 1 | institutional_momentum | **KEEP** | 319 | ₹78397.06 | 1.22 | 72.7% | 16.74% |
| 2 | buy_the_dip | **KEEP** | 306 | ₹74101.73 | 1.25 | 73.2% | 22.05% |
| 3 | ultra_meta_dip_swarm | **KEEP** | 246 | ₹58035.97 | 1.24 | 74.4% | 24.99% |
| 4 | advanced_ai | **IMPROVE** | 912 | ₹331195.07 | 1.32 | 72.0% | 46.03% |
| 5 | ema_rsi | **IMPROVE** | 609 | ₹247201.47 | 1.38 | 72.1% | 47.89% |
| 6 | MARL_Ultra | **IMPROVE** | 976 | ₹130399.24 | 1.1 | 70.4% | 41.26% |
| 7 | marl_strategy | **IMPROVE** | 976 | ₹130399.24 | 1.1 | 70.4% | 41.26% |
| 8 | meta_agent_swarm | **IMPROVE** | 242 | ₹36290.38 | 1.13 | 70.2% | 42.72% |
| 9 | premium | **IMPROVE** | 135 | ₹13915.01 | 1.17 | 74.1% | 11.47% |
| 10 | ema_crossover | **IMPROVE** | 25 | ₹13239.06 | 1.71 | 80.0% | 10.1% |
| 11 | drl_strategy | **REMOVE** | 1189 | ₹109161.23 | 1.07 | 69.5% | 39.19% |
| 12 | enhanced_ai | **REMOVE** | 585 | ₹-16159.66 | 0.98 | 68.4% | 55.31% |

## Summary

- Total strategies evaluated: 12
- KEEP (production-ready): 3
- IMPROVE (potential, needs work): 7
- REMOVE (no sustainable edge): 2

---

## Per-strategy detail

### institutional_momentum — KEEP

**Reasons:** Passes all necessary and quality gates: PF=1.22, expectancy=245.76, net=78397, drawdown=16.7%, recovery=4.68, profitable in 4/5 regimes.

**Overall:** trades=319, net_profit=₹78397.06 (78.4%), profit_factor=1.22, win_rate=72.7%, expectancy=₹245.76, max_drawdown=16.74%, recovery_factor=4.68, max_consecutive_losses=4, avg_trade=₹245.76, avg_holding=25.1min, realized_R:R=0.46

**Diagnostics:** candidate_signals=295, rejected_untradeable_sl=0, rejected_risk_gate=26, rejected_market_hours=27, elapsed=82.8s

| Regime | Trades | Net Profit | Profit Factor | Win Rate | Expectancy |
|---|---|---|---|---|---|
| trending | 120 | ₹37871.52 | 1.32 | 75.0% | ₹315.6 |
| sideways | 158 | ₹26166.01 | 1.13 | 70.3% | ₹165.61 |
| high_volatility | 9 | ₹14716.43 | 5.65 | 88.9% | ₹1635.16 |
| low_volatility | 12 | ₹884.15 | 1.08 | 75.0% | ₹73.68 |
| gap_day | 20 | ₹-1241.05 | 0.96 | 70.0% | ₹-62.05 |

### buy_the_dip — KEEP

**Reasons:** Passes all necessary and quality gates: PF=1.25, expectancy=242.16, net=74102, drawdown=22.1%, recovery=3.36, profitable in 4/5 regimes.

**Overall:** trades=306, net_profit=₹74101.73 (74.1%), profit_factor=1.25, win_rate=73.2%, expectancy=₹242.16, max_drawdown=22.05%, recovery_factor=3.36, max_consecutive_losses=5, avg_trade=₹242.16, avg_holding=27.8min, realized_R:R=0.46

**Diagnostics:** candidate_signals=273, rejected_untradeable_sl=0, rejected_risk_gate=30, rejected_market_hours=13, elapsed=169.5s

| Regime | Trades | Net Profit | Profit Factor | Win Rate | Expectancy |
|---|---|---|---|---|---|
| trending | 95 | ₹43815.81 | 1.55 | 77.9% | ₹461.22 |
| sideways | 138 | ₹1424.53 | 1.01 | 70.3% | ₹10.32 |
| high_volatility | 12 | ₹20989.22 | 2.79 | 75.0% | ₹1749.1 |
| low_volatility | 16 | ₹11125.98 | 3.29 | 81.2% | ₹695.37 |
| gap_day | 45 | ₹-3253.8 | 0.94 | 68.9% | ₹-72.31 |

### ultra_meta_dip_swarm — KEEP

**Reasons:** Passes all necessary and quality gates: PF=1.24, expectancy=235.92, net=58036, drawdown=25.0%, recovery=2.32, profitable in 5/5 regimes.

**Overall:** trades=246, net_profit=₹58035.97 (58.04%), profit_factor=1.24, win_rate=74.4%, expectancy=₹235.92, max_drawdown=24.99%, recovery_factor=2.32, max_consecutive_losses=5, avg_trade=₹235.92, avg_holding=27.0min, realized_R:R=0.43

**Diagnostics:** candidate_signals=209, rejected_untradeable_sl=0, rejected_risk_gate=10, rejected_market_hours=12, elapsed=372.2s

| Regime | Trades | Net Profit | Profit Factor | Win Rate | Expectancy |
|---|---|---|---|---|---|
| trending | 82 | ₹44219.61 | 1.61 | 80.5% | ₹539.26 |
| sideways | 112 | ₹3561.13 | 1.03 | 69.6% | ₹31.8 |
| high_volatility | 8 | ₹2214.77 | 1.19 | 62.5% | ₹276.85 |
| low_volatility | 11 | ₹4363.31 | 1.95 | 81.8% | ₹396.66 |
| gap_day | 33 | ₹3677.15 | 1.1 | 75.8% | ₹111.43 |

### advanced_ai — IMPROVE

**Reasons:** N4 survivability: 46.0% drawdown exceeds 30% (recovering it requires +85%)

**Overall:** trades=912, net_profit=₹331195.07 (331.2%), profit_factor=1.32, win_rate=72.0%, expectancy=₹363.15, max_drawdown=46.03%, recovery_factor=7.19, max_consecutive_losses=10, avg_trade=₹363.15, avg_holding=27.6min, realized_R:R=0.51

**Diagnostics:** candidate_signals=1397, rejected_untradeable_sl=0, rejected_risk_gate=594, rejected_market_hours=92, elapsed=403.8s

| Regime | Trades | Net Profit | Profit Factor | Win Rate | Expectancy |
|---|---|---|---|---|---|
| trending | 318 | ₹154310.64 | 1.43 | 71.1% | ₹485.25 |
| sideways | 466 | ₹186006.13 | 1.37 | 73.6% | ₹399.15 |
| high_volatility | 5 | ₹-30154.16 | 0.0 | 0.0% | ₹-6030.83 |
| low_volatility | 28 | ₹-8153.28 | 0.7 | 71.4% | ₹-291.19 |
| gap_day | 95 | ₹29185.76 | 1.23 | 71.6% | ₹307.22 |

### ema_rsi — IMPROVE

**Reasons:** N4 survivability: 47.9% drawdown exceeds 30% (recovering it requires +92%) Q2 drawdown unexplained by risk model: 47.9% is 2.74x the 17.5% that 5 consecutive losses at 3.5%/trade would produce

**Overall:** trades=609, net_profit=₹247201.47 (247.2%), profit_factor=1.38, win_rate=72.1%, expectancy=₹405.91, max_drawdown=47.89%, recovery_factor=5.16, max_consecutive_losses=5, avg_trade=₹405.91, avg_holding=28.3min, realized_R:R=0.53

**Diagnostics:** candidate_signals=936, rejected_untradeable_sl=0, rejected_risk_gate=297, rejected_market_hours=177, elapsed=24.1s

| Regime | Trades | Net Profit | Profit Factor | Win Rate | Expectancy |
|---|---|---|---|---|---|
| trending | 191 | ₹30264.12 | 1.14 | 72.3% | ₹158.45 |
| sideways | 329 | ₹230107.84 | 1.71 | 72.3% | ₹699.42 |
| high_volatility | 20 | ₹10907.49 | 1.55 | 90.0% | ₹545.37 |
| low_volatility | 15 | ₹-18292.5 | 0.31 | 60.0% | ₹-1219.5 |
| gap_day | 54 | ₹-5785.48 | 0.92 | 66.7% | ₹-107.14 |

### MARL_Ultra — IMPROVE

**Reasons:** N4 survivability: 41.3% drawdown exceeds 30% (recovering it requires +70%)

**Overall:** trades=976, net_profit=₹130399.24 (130.4%), profit_factor=1.1, win_rate=70.4%, expectancy=₹133.61, max_drawdown=41.26%, recovery_factor=3.16, max_consecutive_losses=6, avg_trade=₹133.61, avg_holding=28.7min, realized_R:R=0.46

**Diagnostics:** candidate_signals=2590, rejected_untradeable_sl=0, rejected_risk_gate=1801, rejected_market_hours=37, elapsed=394.4s

| Regime | Trades | Net Profit | Profit Factor | Win Rate | Expectancy |
|---|---|---|---|---|---|
| trending | 283 | ₹-60171.51 | 0.83 | 67.5% | ₹-212.62 |
| sideways | 486 | ₹26128.73 | 1.04 | 71.4% | ₹53.76 |
| high_volatility | 29 | ₹22825.51 | 1.33 | 65.5% | ₹787.09 |
| low_volatility | 35 | ₹2495.16 | 1.08 | 74.3% | ₹71.29 |
| gap_day | 143 | ₹139121.34 | 1.68 | 72.7% | ₹972.88 |

### marl_strategy — IMPROVE

**Reasons:** N4 survivability: 41.3% drawdown exceeds 30% (recovering it requires +70%)

**Overall:** trades=976, net_profit=₹130399.24 (130.4%), profit_factor=1.1, win_rate=70.4%, expectancy=₹133.61, max_drawdown=41.26%, recovery_factor=3.16, max_consecutive_losses=6, avg_trade=₹133.61, avg_holding=28.7min, realized_R:R=0.46

**Diagnostics:** candidate_signals=2590, rejected_untradeable_sl=0, rejected_risk_gate=1801, rejected_market_hours=37, elapsed=92.0s

| Regime | Trades | Net Profit | Profit Factor | Win Rate | Expectancy |
|---|---|---|---|---|---|
| trending | 283 | ₹-60171.51 | 0.83 | 67.5% | ₹-212.62 |
| sideways | 486 | ₹26128.73 | 1.04 | 71.4% | ₹53.76 |
| high_volatility | 29 | ₹22825.51 | 1.33 | 65.5% | ₹787.09 |
| low_volatility | 35 | ₹2495.16 | 1.08 | 74.3% | ₹71.29 |
| gap_day | 143 | ₹139121.34 | 1.68 | 72.7% | ₹972.88 |

### meta_agent_swarm — IMPROVE

**Reasons:** N4 survivability: 42.7% drawdown exceeds 30% (recovering it requires +75%) Q1 recovery factor 0.85 < 2.0 (did not earn twice its worst drawdown) Q2 drawdown unexplained by risk model: 42.7% is 3.05x the 14.0% that 4 consecutive losses at 3.5%/trade would produce Q3 regime robustness: profitable in only 2/5 adequately-sampled regimes

**Overall:** trades=242, net_profit=₹36290.38 (36.29%), profit_factor=1.13, win_rate=70.2%, expectancy=₹149.96, max_drawdown=42.72%, recovery_factor=0.85, max_consecutive_losses=4, avg_trade=₹149.96, avg_holding=23.5min, realized_R:R=0.48

**Diagnostics:** candidate_signals=240, rejected_untradeable_sl=0, rejected_risk_gate=29, rejected_market_hours=24, elapsed=423.9s

| Regime | Trades | Net Profit | Profit Factor | Win Rate | Expectancy |
|---|---|---|---|---|---|
| trending | 87 | ₹31135.19 | 1.34 | 72.4% | ₹357.88 |
| sideways | 120 | ₹31502.86 | 1.24 | 70.0% | ₹262.52 |
| high_volatility | 8 | ₹-11524.49 | 0.48 | 50.0% | ₹-1440.56 |
| low_volatility | 6 | ₹-184.37 | 0.97 | 83.3% | ₹-30.73 |
| gap_day | 21 | ₹-14638.8 | 0.62 | 66.7% | ₹-697.09 |

### premium — IMPROVE

**Reasons:** Q1 recovery factor 1.21 < 2.0 (did not earn twice its worst drawdown)

**Overall:** trades=135, net_profit=₹13915.01 (13.92%), profit_factor=1.17, win_rate=74.1%, expectancy=₹103.07, max_drawdown=11.47%, recovery_factor=1.21, max_consecutive_losses=4, avg_trade=₹103.07, avg_holding=89.5min, realized_R:R=0.41

**Diagnostics:** candidate_signals=0, rejected_untradeable_sl=0, rejected_risk_gate=0, rejected_market_hours=0, elapsed=627.5s

| Regime | Trades | Net Profit | Profit Factor | Win Rate | Expectancy |
|---|---|---|---|---|---|
| trending | 55 | ₹16677.37 | 1.75 | 76.4% | ₹303.22 |
| sideways | 63 | ₹-7886.09 | 0.84 | 71.4% | ₹-125.18 |
| high_volatility | 5 | ₹5283.6 | 3.42 | 80.0% | ₹1056.72 |
| low_volatility | 6 | ₹-1851.11 | 0.64 | 66.7% | ₹-308.52 |
| gap_day | 6 | ₹1691.24 | 1.45 | 83.3% | ₹281.87 |

### ema_crossover — IMPROVE

**Reasons:** N2 sample too small (25 trades < 30) — neither KEEP nor REMOVE is supportable Q1 recovery factor 1.31 < 2.0 (did not earn twice its worst drawdown)

**Overall:** trades=25, net_profit=₹13239.06 (13.24%), profit_factor=1.71, win_rate=80.0%, expectancy=₹529.56, max_drawdown=10.1%, recovery_factor=1.31, max_consecutive_losses=3, avg_trade=₹529.56, avg_holding=19.0min, realized_R:R=0.43

**Diagnostics:** candidate_signals=19, rejected_untradeable_sl=0, rejected_risk_gate=0, rejected_market_hours=0, elapsed=24.4s

| Regime | Trades | Net Profit | Profit Factor | Win Rate | Expectancy |
|---|---|---|---|---|---|
| trending | 7 | ₹15460.18 | Infinity | 100.0% | ₹2208.6 |
| sideways | 12 | ₹4153.01 | 1.6 | 83.3% | ₹346.08 |
| high_volatility | 1 | ₹-3091.74 | 0.0 | 0.0% | ₹-3091.74 |
| low_volatility | 1 | ₹2455.56 | Infinity | 100.0% | ₹2455.56 |
| gap_day | 4 | ₹-5737.94 | 0.33 | 50.0% | ₹-1434.49 |

### drl_strategy — REMOVE

**Reasons:** N3 unresolved critical defect: market-blind — a +7,500pt uptrend and a -7,500pt downtrend produce byte-identical signals (286 BUY / 0 SELL in both); constant observation vector plus a collapsed model artifact, and attaching real features changed nothing N4 survivability: 39.2% drawdown exceeds 30% (recovering it requires +64%)

**Overall:** trades=1189, net_profit=₹109161.23 (109.16%), profit_factor=1.07, win_rate=69.5%, expectancy=₹91.81, max_drawdown=39.19%, recovery_factor=2.79, max_consecutive_losses=6, avg_trade=₹91.81, avg_holding=27.7min, realized_R:R=0.47

**Diagnostics:** candidate_signals=3826, rejected_untradeable_sl=0, rejected_risk_gate=2531, rejected_market_hours=372, elapsed=290.6s

| Regime | Trades | Net Profit | Profit Factor | Win Rate | Expectancy |
|---|---|---|---|---|---|
| trending | 397 | ₹29730.46 | 1.06 | 68.0% | ₹74.89 |
| sideways | 564 | ₹-9023.86 | 0.99 | 70.2% | ₹-16.0 |
| high_volatility | 13 | ₹-21795.52 | 0.54 | 30.8% | ₹-1676.58 |
| low_volatility | 45 | ₹4919.24 | 1.12 | 73.3% | ₹109.32 |
| gap_day | 170 | ₹105330.92 | 1.42 | 72.4% | ₹619.59 |

### enhanced_ai — REMOVE

**Reasons:** N1 no edge (PF=0.98, expectancy=-27.62) N4 survivability: 55.3% drawdown exceeds 30% (recovering it requires +124%) Q1 recovery factor -0.29 < 2.0 (did not earn twice its worst drawdown) Q2 drawdown unexplained by risk model: 55.3% is 3.95x the 14.0% that 4 consecutive losses at 3.5%/trade would produce Q3 regime robustness: profitable in only 2/5 adequately-sampled regimes

**Overall:** trades=585, net_profit=₹-16159.66 (-16.16%), profit_factor=0.98, win_rate=68.4%, expectancy=₹-27.62, max_drawdown=55.31%, recovery_factor=-0.29, max_consecutive_losses=4, avg_trade=₹-27.62, avg_holding=26.8min, realized_R:R=0.45

**Diagnostics:** candidate_signals=1060, rejected_untradeable_sl=0, rejected_risk_gate=487, rejected_market_hours=119, elapsed=10.5s

| Regime | Trades | Net Profit | Profit Factor | Win Rate | Expectancy |
|---|---|---|---|---|---|
| trending | 195 | ₹-1022.47 | 1.0 | 69.2% | ₹-5.24 |
| sideways | 283 | ₹12850.69 | 1.04 | 68.6% | ₹45.41 |
| high_volatility | 13 | ₹2049.61 | 1.09 | 76.9% | ₹157.66 |
| low_volatility | 20 | ₹-23353.6 | 0.3 | 55.0% | ₹-1167.68 |
| gap_day | 74 | ₹-6683.89 | 0.95 | 67.6% | ₹-90.32 |
