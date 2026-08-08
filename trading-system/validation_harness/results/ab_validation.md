# Validation before/after — partial-booking runner re-baseline

Window: 2026-02-01 09:15:00 → 2026-07-31 15:25:00 (123 trading days)  
Capital: Rs 100,000  
Day-isolated, fresh RiskManager per day, full production pipeline. BEFORE is each strategy's cached pre-change trade set; AFTER is a fresh run through the changed engine over the same data.

## Summary across strategies

| Strategy | Trades B→A | Net B | Net A | Net Δ | PF B→A | DD% B→A | Recovery B→A |
|---|---|---|---|---|---|---|---|
| ema_rsi | 528→522 | 202,040.50 | 211,316.31 | +9,276 | 1.37→1.39 | 20.84→19.01 | 9.7→11.12 |
| institutional_momentum | 319→317 | 78,397.06 | 88,510.52 | +10,113 | 1.22→1.25 | 16.74→15.12 | 4.68→5.85 |
| buy_the_dip | 306→306 | 74,101.73 | 68,485.47 | -5,616 | 1.25→1.23 | 22.05→22.05 | 3.36→3.11 |
| ultra_meta_dip_swarm | 246→246 | 58,035.97 | 53,892.34 | -4,144 | 1.24→1.22 | 24.99→25.5 | 2.32→2.11 |
| enhanced_ai | 585→587 | -16,159.66 | 14,710.87 | +30,871 | 0.98→1.02 | 55.31→46.97 | -0.29→0.31 |
| MARL_Ultra | 976→961 | 130,399.24 | 149,119.72 | +18,720 | 1.1→1.12 | 41.26→40.34 | 3.16→3.7 |

## `ema_rsi` — full metric detail

| Metric | Before | After | Change |
|---|---|---|---|
| trade_count | 528 | 522 | -6.00 |
| net_profit | 202,040.50 | 211,316.31 | +9,275.81 BETTER |
| net_profit_pct | 202.04 | 211.32 | +9.28 BETTER |
| profit_factor | 1.37 | 1.39 | +0.02 BETTER |
| win_rate_pct | 72.70 | 72.60 | -0.10 |
| expectancy | 382.65 | 404.82 | +22.17 BETTER |
| max_drawdown_pct | 20.84 | 19.01 | -1.83 BETTER |
| recovery_factor | 9.70 | 11.12 | +1.42 BETTER |
| max_consecutive_losses | 4 | 4 | unchanged |
| avg_trade | 382.65 | 404.82 | +22.17 BETTER |
| avg_holding_minutes | 29.40 | 29.70 | +0.30 |
| avg_risk_reward | 0.51 | 0.53 | +0.02 BETTER |
| gross_profit | 751,116.87 | 748,852.82 | -2,264.05 WORSE |
| gross_loss | 549,076.38 | 537,536.51 | -11,539.87 BETTER |

### `ema_rsi` — exit-reason mix

| Exit reason | Before | After |
|---|---|---|
| `END_OF_DATA` | 1 | 1 |
| `Partial Profit Booking` | 131 | 130 |
| `Stop-Loss Hit` | 137 | 138 |
| `Time-based EOD Exit` | 41 | 42 |
| `Trailing Stop-Loss Hit` | 2 | 2 |
| `Trailing Stop-Loss Hit (Offset)` | 216 | 209 |

### `ema_rsi` — by regime

| Regime | Trades B→A | Net B | Net A | PF B | PF A | DD% B | DD% A |
|---|---|---|---|---|---|---|---|
| trending | 174→172 | 23,482.15 | 31,505.77 | 1.13 | 1.18 | 35.40 | 30.82 |
| sideways | 278→277 | 178,555.68 | 182,130.59 | 1.65 | 1.67 | 10.80 | 10.80 |
| high_volatility | 13→12 | -4,615.80 | -4,586.20 | 0.77 | 0.77 | 18.62 | 18.62 |
| low_volatility | 13→13 | -20,023.69 | -20,023.69 | 0.25 | 0.25 | 20.39 | 20.39 |
| gap_day | 50→48 | 24,642.15 | 22,289.84 | 1.58 | 1.53 | 7.02 | 7.02 |
