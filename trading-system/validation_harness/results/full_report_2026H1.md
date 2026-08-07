# Production Strategy Validation Report

**Instrument:** NIFTY | **Period:** 2026-02-01 09:15:00 → 2026-07-31 15:25:00 | **Trading days:** 123 | **Initial capital per day-isolated run:** ₹100,000

**Regime day counts:** {'sideways': 45, 'gap_day': 44, 'trending': 28, 'low_volatility': 5, 'high_volatility': 1}

---

## Ranking (best → worst)

| Rank | Strategy | Verdict | Trades | Net Profit | Profit Factor | Win Rate | Max DD |
|---|---|---|---|---|---|---|---|
| 1 | advanced_ai | **IMPROVE** | 993 | ₹277101.03 | 1.24 | 71.0% | 61.86% |
| 2 | ema_rsi | **IMPROVE** | 609 | ₹247201.47 | 1.38 | 72.1% | 47.89% |
| 3 | marl_strategy | **IMPROVE** | 976 | ₹130399.24 | 1.1 | 70.4% | 41.26% |
| 4 | drl_strategy | **IMPROVE** | 1189 | ₹109161.23 | 1.07 | 69.5% | 39.19% |
| 5 | institutional_momentum | **IMPROVE** | 319 | ₹78397.06 | 1.22 | 72.7% | 16.74% |
| 6 | buy_the_dip | **IMPROVE** | 306 | ₹74101.73 | 1.25 | 73.2% | 22.05% |
| 7 | ultra_meta_dip_swarm | **IMPROVE** | 246 | ₹58035.97 | 1.24 | 74.4% | 24.99% |
| 8 | MARL_Ultra | **IMPROVE** | 127 | ₹53456.26 | 1.41 | 70.9% | 16.52% |
| 9 | premium | **IMPROVE** | 135 | ₹13915.01 | 1.17 | 74.1% | 11.47% |
| 10 | ema_crossover | **IMPROVE** | 25 | ₹13239.06 | 1.71 | 80.0% | 10.1% |
| 11 | meta_agent_swarm | **IMPROVE** | 132 | ₹11570.08 | 1.07 | 67.4% | 40.2% |
| 12 | enhanced_ai | **IMPROVE** | 587 | ₹-22777.78 | 0.97 | 68.1% | 61.64% |

## Summary

- Total strategies evaluated: 12
- KEEP (production-ready): 0
- IMPROVE (potential, needs work): 12
- REMOVE (no sustainable edge): 0

---

## Per-strategy detail

### advanced_ai — IMPROVE

**Reasons:** Overall PF=1.24, expectancy=279.05, net=277101.03. Profitable in 2/4 regimes traded — mixed, not consistent enough for KEEP or REMOVE. Max drawdown 61.86% is a real concern even where profitable.

**Overall:** trades=993, net_profit=₹277101.03 (277.1%), profit_factor=1.24, win_rate=71.0%, expectancy=₹279.05, max_drawdown=61.86%, recovery_factor=4.48, max_consecutive_losses=6, avg_trade=₹279.05, avg_holding=28.8min, realized_R:R=0.51

**Diagnostics:** candidate_signals=2537, rejected_untradeable_sl=0, rejected_risk_gate=1563, rejected_market_hours=198, elapsed=134.4s

| Regime | Trades | Net Profit | Profit Factor | Win Rate | Expectancy |
|---|---|---|---|---|---|
| trending | 211 | ₹-39202.62 | 0.85 | 67.3% | ₹-185.79 |
| sideways | 352 | ₹182573.95 | 1.52 | 75.6% | ₹518.68 |
| high_volatility | 1 | ₹-5033.68 | 0.0 | 0.0% | ₹-5033.68 |
| low_volatility | 36 | ₹-1982.31 | 0.94 | 69.4% | ₹-55.06 |
| gap_day | 393 | ₹140745.68 | 1.28 | 69.2% | ₹358.13 |

### ema_rsi — IMPROVE

**Reasons:** Overall PF=1.38, expectancy=405.91, net=247201.47. Profitable in 3/5 regimes traded — mixed, not consistent enough for KEEP or REMOVE. Max drawdown 47.89% is a real concern even where profitable.

**Overall:** trades=609, net_profit=₹247201.47 (247.2%), profit_factor=1.38, win_rate=72.1%, expectancy=₹405.91, max_drawdown=47.89%, recovery_factor=5.16, max_consecutive_losses=5, avg_trade=₹405.91, avg_holding=28.3min, realized_R:R=0.53

**Diagnostics:** candidate_signals=936, rejected_untradeable_sl=0, rejected_risk_gate=297, rejected_market_hours=177, elapsed=14.4s

| Regime | Trades | Net Profit | Profit Factor | Win Rate | Expectancy |
|---|---|---|---|---|---|
| trending | 152 | ₹72806.25 | 1.53 | 74.3% | ₹478.99 |
| sideways | 245 | ₹230526.25 | 2.0 | 75.1% | ₹940.92 |
| high_volatility | 10 | ₹14515.88 | Infinity | 100.0% | ₹1451.59 |
| low_volatility | 11 | ₹-11089.37 | 0.38 | 63.6% | ₹-1008.12 |
| gap_day | 191 | ₹-59557.53 | 0.77 | 65.4% | ₹-311.82 |

### marl_strategy — IMPROVE

**Reasons:** Overall PF=1.1, expectancy=133.61, net=130399.24. Profitable in 1/4 regimes traded — mixed, not consistent enough for KEEP or REMOVE. Max drawdown 41.26% is a real concern even where profitable.

**Overall:** trades=976, net_profit=₹130399.24 (130.4%), profit_factor=1.1, win_rate=70.4%, expectancy=₹133.61, max_drawdown=41.26%, recovery_factor=3.16, max_consecutive_losses=6, avg_trade=₹133.61, avg_holding=28.7min, realized_R:R=0.46

**Diagnostics:** candidate_signals=2590, rejected_untradeable_sl=0, rejected_risk_gate=1801, rejected_market_hours=37, elapsed=137.6s

| Regime | Trades | Net Profit | Profit Factor | Win Rate | Expectancy |
|---|---|---|---|---|---|
| trending | 233 | ₹-1686.39 | 0.99 | 69.5% | ₹-7.24 |
| sideways | 348 | ₹-8397.86 | 0.98 | 69.8% | ₹-24.13 |
| high_volatility | 2 | ₹-8349.68 | 0.0 | 0.0% | ₹-4174.84 |
| low_volatility | 26 | ₹-6804.73 | 0.74 | 73.1% | ₹-261.72 |
| gap_day | 367 | ₹155637.89 | 1.32 | 71.7% | ₹424.08 |

### drl_strategy — IMPROVE

**Reasons:** Overall PF=1.07, expectancy=91.81, net=109161.23. Profitable in 2/4 regimes traded — mixed, not consistent enough for KEEP or REMOVE. Max drawdown 39.19% is a real concern even where profitable.

**Overall:** trades=1189, net_profit=₹109161.23 (109.16%), profit_factor=1.07, win_rate=69.5%, expectancy=₹91.81, max_drawdown=39.19%, recovery_factor=2.79, max_consecutive_losses=6, avg_trade=₹91.81, avg_holding=27.7min, realized_R:R=0.47

**Diagnostics:** candidate_signals=3826, rejected_untradeable_sl=0, rejected_risk_gate=2531, rejected_market_hours=372, elapsed=305.8s

| Regime | Trades | Net Profit | Profit Factor | Win Rate | Expectancy |
|---|---|---|---|---|---|
| trending | 281 | ₹28638.36 | 1.1 | 70.8% | ₹101.92 |
| sideways | 408 | ₹-28025.85 | 0.95 | 69.6% | ₹-68.69 |
| high_volatility | 2 | ₹-9145.74 | 0.0 | 0.0% | ₹-4572.87 |
| low_volatility | 37 | ₹-1450.84 | 0.95 | 73.0% | ₹-39.21 |
| gap_day | 461 | ₹119145.3 | 1.17 | 68.5% | ₹258.45 |

### institutional_momentum — IMPROVE

**Reasons:** Overall PF=1.22, expectancy=245.76, net=78397.06. Profitable in 4/5 regimes traded — mixed, not consistent enough for KEEP or REMOVE.

**Overall:** trades=319, net_profit=₹78397.06 (78.4%), profit_factor=1.22, win_rate=72.7%, expectancy=₹245.76, max_drawdown=16.74%, recovery_factor=4.68, max_consecutive_losses=4, avg_trade=₹245.76, avg_holding=25.1min, realized_R:R=0.46

**Diagnostics:** candidate_signals=295, rejected_untradeable_sl=0, rejected_risk_gate=26, rejected_market_hours=27, elapsed=47.0s

| Regime | Trades | Net Profit | Profit Factor | Win Rate | Expectancy |
|---|---|---|---|---|---|
| trending | 81 | ₹41925.49 | 1.68 | 77.8% | ₹517.6 |
| sideways | 126 | ₹33077.55 | 1.21 | 71.4% | ₹262.52 |
| high_volatility | 5 | ₹4661.76 | 2.47 | 80.0% | ₹932.35 |
| low_volatility | 10 | ₹8802.08 | 3.39 | 90.0% | ₹880.21 |
| gap_day | 97 | ₹-10069.82 | 0.92 | 68.0% | ₹-103.81 |

### buy_the_dip — IMPROVE

**Reasons:** Overall PF=1.25, expectancy=242.16, net=74101.73. Profitable in 3/4 regimes traded — mixed, not consistent enough for KEEP or REMOVE.

**Overall:** trades=306, net_profit=₹74101.73 (74.1%), profit_factor=1.25, win_rate=73.2%, expectancy=₹242.16, max_drawdown=22.05%, recovery_factor=3.36, max_consecutive_losses=5, avg_trade=₹242.16, avg_holding=27.8min, realized_R:R=0.46

**Diagnostics:** candidate_signals=273, rejected_untradeable_sl=0, rejected_risk_gate=30, rejected_market_hours=13, elapsed=81.0s

| Regime | Trades | Net Profit | Profit Factor | Win Rate | Expectancy |
|---|---|---|---|---|---|
| trending | 67 | ₹31767.39 | 1.55 | 76.1% | ₹474.14 |
| sideways | 103 | ₹44863.74 | 1.51 | 75.7% | ₹435.57 |
| high_volatility | 1 | ₹-2858.86 | 0.0 | 0.0% | ₹-2858.86 |
| low_volatility | 10 | ₹10777.19 | 45.66 | 90.0% | ₹1077.72 |
| gap_day | 125 | ₹-10447.73 | 0.93 | 68.8% | ₹-83.58 |

### ultra_meta_dip_swarm — IMPROVE

**Reasons:** Overall PF=1.24, expectancy=235.92, net=58035.97. Profitable in 3/4 regimes traded — mixed, not consistent enough for KEEP or REMOVE.

**Overall:** trades=246, net_profit=₹58035.97 (58.04%), profit_factor=1.24, win_rate=74.4%, expectancy=₹235.92, max_drawdown=24.99%, recovery_factor=2.32, max_consecutive_losses=5, avg_trade=₹235.92, avg_holding=27.0min, realized_R:R=0.43

**Diagnostics:** candidate_signals=209, rejected_untradeable_sl=0, rejected_risk_gate=10, rejected_market_hours=12, elapsed=99.4s

| Regime | Trades | Net Profit | Profit Factor | Win Rate | Expectancy |
|---|---|---|---|---|---|
| trending | 59 | ₹30949.82 | 1.61 | 78.0% | ₹524.57 |
| sideways | 85 | ₹42898.04 | 1.62 | 77.6% | ₹504.68 |
| high_volatility | 1 | ₹-2858.86 | 0.0 | 0.0% | ₹-2858.86 |
| low_volatility | 6 | ₹4757.76 | Infinity | 100.0% | ₹792.96 |
| gap_day | 95 | ₹-17710.8 | 0.86 | 68.4% | ₹-186.43 |

### MARL_Ultra — IMPROVE

**Reasons:** Overall PF=1.41, expectancy=420.92, net=53456.26. Profitable in 2/3 regimes traded — mixed, not consistent enough for KEEP or REMOVE.

**Overall:** trades=127, net_profit=₹53456.26 (53.46%), profit_factor=1.41, win_rate=70.9%, expectancy=₹420.92, max_drawdown=16.52%, recovery_factor=3.24, max_consecutive_losses=3, avg_trade=₹420.92, avg_holding=32.5min, realized_R:R=0.58

**Diagnostics:** candidate_signals=235, rejected_untradeable_sl=0, rejected_risk_gate=103, rejected_market_hours=37, elapsed=90.5s

| Regime | Trades | Net Profit | Profit Factor | Win Rate | Expectancy |
|---|---|---|---|---|---|
| trending | 69 | ₹-9537.33 | 0.84 | 71.0% | ₹-138.22 |
| sideways | 19 | ₹51922.41 | 4.53 | 78.9% | ₹2732.76 |
| high_volatility | 0 | — | — | — | — |
| low_volatility | 0 | — | — | — | — |
| gap_day | 39 | ₹11071.18 | 1.2 | 66.7% | ₹283.88 |

### premium — IMPROVE

**Reasons:** Overall PF=1.17, expectancy=103.07, net=13915.01. Profitable in 3/5 regimes traded — mixed, not consistent enough for KEEP or REMOVE.

**Overall:** trades=135, net_profit=₹13915.01 (13.92%), profit_factor=1.17, win_rate=74.1%, expectancy=₹103.07, max_drawdown=11.47%, recovery_factor=1.21, max_consecutive_losses=4, avg_trade=₹103.07, avg_holding=89.5min, realized_R:R=0.41

**Diagnostics:** candidate_signals=0, rejected_untradeable_sl=0, rejected_risk_gate=0, rejected_market_hours=0, elapsed=260.6s

| Regime | Trades | Net Profit | Profit Factor | Win Rate | Expectancy |
|---|---|---|---|---|---|
| trending | 39 | ₹13267.39 | 1.94 | 76.9% | ₹340.19 |
| sideways | 46 | ₹-8784.32 | 0.79 | 73.9% | ₹-190.96 |
| high_volatility | 3 | ₹-1305.72 | 0.4 | 66.7% | ₹-435.24 |
| low_volatility | 5 | ₹997.55 | 1.43 | 80.0% | ₹199.51 |
| gap_day | 42 | ₹9740.11 | 1.46 | 71.4% | ₹231.91 |

### ema_crossover — IMPROVE

**Reasons:** Only 25 trades in the validated window (need >= 30 for a confident verdict) — insufficient evidence for KEEP or REMOVE either way.

**Overall:** trades=25, net_profit=₹13239.06 (13.24%), profit_factor=1.71, win_rate=80.0%, expectancy=₹529.56, max_drawdown=10.1%, recovery_factor=1.31, max_consecutive_losses=3, avg_trade=₹529.56, avg_holding=19.0min, realized_R:R=0.43

**Diagnostics:** candidate_signals=19, rejected_untradeable_sl=0, rejected_risk_gate=0, rejected_market_hours=0, elapsed=15.4s

| Regime | Trades | Net Profit | Profit Factor | Win Rate | Expectancy |
|---|---|---|---|---|---|
| trending | 5 | ₹8360.25 | Infinity | 100.0% | ₹1672.05 |
| sideways | 10 | ₹6850.48 | 2.94 | 90.0% | ₹685.05 |
| high_volatility | 0 | — | — | — | — |
| low_volatility | 1 | ₹2455.56 | Infinity | 100.0% | ₹2455.56 |
| gap_day | 9 | ₹-4427.23 | 0.71 | 55.6% | ₹-491.91 |

### meta_agent_swarm — IMPROVE

**Reasons:** Overall PF=1.07, expectancy=87.65, net=11570.08. Profitable in 2/4 regimes traded — mixed, not consistent enough for KEEP or REMOVE. Max drawdown 40.2% is a real concern even where profitable.

**Overall:** trades=132, net_profit=₹11570.08 (11.57%), profit_factor=1.07, win_rate=67.4%, expectancy=₹87.65, max_drawdown=40.2%, recovery_factor=0.29, max_consecutive_losses=6, avg_trade=₹87.65, avg_holding=21.0min, realized_R:R=0.52

**Diagnostics:** candidate_signals=122, rejected_untradeable_sl=0, rejected_risk_gate=5, rejected_market_hours=13, elapsed=183.0s

| Regime | Trades | Net Profit | Profit Factor | Win Rate | Expectancy |
|---|---|---|---|---|---|
| trending | 30 | ₹30385.88 | 2.23 | 63.3% | ₹1012.86 |
| sideways | 45 | ₹22987.59 | 1.65 | 82.2% | ₹510.84 |
| high_volatility | 2 | ₹3878.79 | Infinity | 100.0% | ₹1939.4 |
| low_volatility | 3 | ₹-3575.78 | 0.5 | 66.7% | ₹-1191.93 |
| gap_day | 52 | ₹-42106.41 | 0.6 | 55.8% | ₹-809.74 |

### enhanced_ai — IMPROVE

**Reasons:** Overall PF=0.97, expectancy=-38.8, net=-22777.78. Profitable in 3/5 regimes traded — mixed, not consistent enough for KEEP or REMOVE. Max drawdown 61.64% is a real concern even where profitable.

**Overall:** trades=587, net_profit=₹-22777.78 (-22.78%), profit_factor=0.97, win_rate=68.1%, expectancy=₹-38.8, max_drawdown=61.64%, recovery_factor=-0.37, max_consecutive_losses=4, avg_trade=₹-38.8, avg_holding=27.0min, realized_R:R=0.45

**Diagnostics:** candidate_signals=1080, rejected_untradeable_sl=0, rejected_risk_gate=501, rejected_market_hours=124, elapsed=14.8s

| Regime | Trades | Net Profit | Profit Factor | Win Rate | Expectancy |
|---|---|---|---|---|---|
| trending | 144 | ₹8544.8 | 1.05 | 70.8% | ₹59.34 |
| sideways | 205 | ₹35527.77 | 1.14 | 69.3% | ₹173.31 |
| high_volatility | 4 | ₹5227.39 | 2.65 | 75.0% | ₹1306.85 |
| low_volatility | 16 | ₹-17386.51 | 0.34 | 56.2% | ₹-1086.66 |
| gap_day | 218 | ₹-54691.22 | 0.84 | 66.1% | ₹-250.88 |
