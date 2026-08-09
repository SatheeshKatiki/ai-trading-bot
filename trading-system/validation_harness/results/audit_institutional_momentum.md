# Strategy audit — `institutional_momentum`

Window: 2026-02-01 09:15:00 → 2026-07-31 15:25:00 (123 trading days)  
Rally set: **381** sustained underlying moves (≥0.30% within 90 min).  
Production entry flags: `{'enable_volume_filter': False, 'enable_ema_filter': False, 'enable_vwap_filter': False, 'enable_rsi_filter': False, 'enable_squeeze_filter': True, 'enable_extension_filter': True, 'enable_cpr_filter': True, 'enable_aggression_filter': True}`, daily cap **3**.

## 1. Baseline — production path vs legacy path

| Metric | PRODUCTION (config/settings.json) | legacy (no settings) |
|---|---|---|
| trades (legs) | 149 | 317 |
| net profit | -8,867 | 88,511 |
| expectancy | -59.51 | 279.21 |
| profit factor | 0.95 | 1.25 |
| max drawdown % | 42.34 | 15.12 |
| recovery factor | -0.21 | 5.85 |
| win rate % | 67.8 | 72.2 |
| realised R:R | 0.45 | 0.48 |
| consecutive losses | 5 | 4 |
| avg holding min | 30.6 | 25.4 |
| Q2 ratio | 2.42 | 1.08 |
| false-signal rate % | 40.5 | 34.0 |
| first-touch edge pp | 5.2 | 17.8 |
| never-rose % | 5.2 | 10.0 |
| rally capture % | 20.7 | 39.6 |
| held % of covered run | 26.7 | 27.3 |
| positions | 116 | 241 |
| **verdict** | **REMOVE** | **KEEP** |

`PRODUCTION (config/settings.json)` — REMOVE: N1 no edge (PF=0.95, expectancy=-59.51); N4 survivability: 42.3% drawdown exceeds 30% (recovering it requires +73%); Q1 recovery factor -0.21 < 2.0 (did not earn twice its worst drawdown); Q2 drawdown unexplained by risk model: 42.3% is 2.42x the 17.5% that 5 consecutive losses at 3.5%/trade would produce; Q3 regime robustness: profitable in only 2/4 adequately-sampled regimes

`legacy (no settings)` — KEEP: Passes all necessary and quality gates: PF=1.25, expectancy=279.21, net=88511, drawdown=15.1%, recovery=5.85, profitable in 4/5 regimes.

## 2. Signal duty cycle and churn

Tests the re-entry mechanism found in `ema_rsi` and `advanced_ai` rather than assuming it. A level-triggered strategy re-enters the same setup bar after bar, which shows up as a short median gap between one exit and the next entry plus a high same-direction rate.

| Measure | PRODUCTION (config/settings.json) | legacy (no settings) |
|---|---|---|
| bars evaluated | 9,220 | 9,220 |
| signal bars | 179 | 488 |
| duty cycle % | 1.9 | 5.3 |
| signals repeating previous bar % | 13.4 | 28.3 |
| same-day re-entries | 35 | 132 |
| median exit→next entry (min) | 100.0 | 50.0 |
| p25 gap (min) | 47.5 | 20.0 |
| re-entries within one bar % | 20.0 | 8.3 |
| same-direction re-entries % | 57.1 | 84.8 |

## 3. Entry quality (production path, exit-independent)

First touch of ±1R, where R is the position's real `resolve_initial_stop` distance. `false entry` = loss-first.

| Outcome | n | share |
|---|---|---|
| win-first | 53 | 45.7% |
| **loss-first (false entry)** | 47 | **40.5%** |
| neither within the day | 16 | 13.8% |

| Excursion (R) | p10 | p25 | median | p75 | p90 |
|---|---|---|---|---|---|
| mfe_r | 0.12 | 0.51 | 1.38 | 3.02 | 5.42 |
| mae_r | -4.84 | -2.80 | -1.11 | -0.46 | 0.05 |

### 3b. Entry timing

| Session bucket | n | first-touch edge pp | net P&L | mean P&L |
|---|---|---|---|---|
| 09:15-10:00 | 14 | +57.1 | 2,303 | 164 |
| 10:00-11:00 | 9 | +33.3 | 13,665 | 1,518 |
| 11:00-12:30 | 30 | +23.3 | 30,830 | 1,028 |
| 12:30-14:00 | 31 | -35.5 | -43,600 | -1,406 |
| 14:00-15:30 | 32 | -3.1 | -12,065 | -377 |

## 4. Exit behaviour (production path)

| Exit reason | n | % | net P&L | mean | median hold (min) |
|---|---|---|---|---|---|
| `Stop-Loss Hit` | 48 | 41.4% | -136,163 | -2,837 | 20 |
| `Time-based EOD Exit` | 12 | 10.3% | 6,489 | 541 | 15 |
| `Trailing Stop-Loss Hit` | 1 | 0.9% | 3,139 | 3,139 | 25 |
| `Trailing Stop-Loss Hit (Offset)` | 55 | 47.4% | 117,669 | 2,139 | 25 |

### 4b. Premature exits and trend capture

Premature = the premium exceeded the exit price within the next 60 minutes of the same day, i.e. the position was closed into a move that was still running.

| Measure | value |
|---|---|
| positions measured | 116 |
| premature exits | 81.9% |
| median missed upside after exit | 8.97% |
| p90 missed upside after exit | 56.55% |
| median capture of the in-trade move | 55.1% |
| median trend capture (vs day's best) | 13.4% |
| median continuation +5min after exit | 0.69% |
| median continuation +15min after exit | 4.19% |
| median continuation +30min after exit | 6.09% |
| median continuation +60min after exit | 8.97% |

### 4c. Exit mechanism mix (legs) and trailing behaviour

| Mechanism | legs | % | median realised % | median giveback pp | armed % |
|---|---|---|---|---|---|
| `eod` | 12 | 8.1% | 1.91 | 0.61 | 83% |
| `partial` | 33 | 22.1% | 17.62 | 0.00 | 100% |
| `stop` | 48 | 32.2% | -15.25 | 17.79 | 44% |
| `trail_atr` | 1 | 0.7% | 15.30 | 24.78 | 100% |
| `trail_offset` | 55 | 36.9% | 5.68 | 2.43 | 100% |

## 5. Missed opportunities (production path)

Every rally in the fixed set the strategy was NOT positioned for, classified by cause. Only `signalled but blocked` and `opposite position held` are addressable; `no setup` is the strategy's own philosophy.

| Cause | n | share of missed |
|---|---|---|
| no setup | 298 | 98.7% |
| signalled but blocked | 3 | 1.0% |
| opposite position held | 1 | 0.3% |
| **total missed** | **302** | of 381 runs |

## 6. Position sizing, stops and risk taken (production path)

| Measure | p10 | median | p90 |
|---|---|---|---|
| entry premium | 55.86 | 179.29 | 218.74 |
| risk per unit (₹) | 10.58 | 22.91 | 26.88 |
| stop distance % of premium | 12.29 | 12.78 | 17.59 |

| Stop band | positions | share | net P&L | false-signal % |
|---|---|---|---|---|
| `>₹250` | 1 | 0.9% | 1,166 | 0.0% |
| `₹100-150` | 15 | 12.9% | 12,533 | 46.7% |
| `₹150-250` | 72 | 62.1% | 7,122 | 37.5% |
| `₹20-50` | 10 | 8.6% | -2,160 | 50.0% |
| `₹50-100` | 18 | 15.5% | -27,529 | 44.4% |

## 7. Rejection and risk-control behaviour

| Counter | PRODUCTION (config/settings.json) | legacy (no settings) |
|---|---|---|
| days_run | 123 | 123 |
| candidate_signals | 133 | 294 |
| rejected_risk_gate | 10 | 26 |
| rejected_market_hours | 7 | 27 |
| rejected_untradeable_sl | 0 | 0 |

Risk-gate rejections by the gate's own reason string:

| Reason | PRODUCTION (config/settings.json) | legacy (no settings) |
|---|---|---|
| `Daily loss limit exceeded: -12049.87` | 0 | 1 |
| `Daily loss limit exceeded: -12384.11` | 0 | 1 |
| `Daily loss limit exceeded: -13493.73` | 1 | 0 |
| `Daily loss limit exceeded: -5092.06` | 0 | 1 |
| `Daily loss limit exceeded: -5411.82` | 0 | 1 |
| `Daily loss limit exceeded: -5456.59` | 1 | 0 |
| `Daily loss limit exceeded: -5510.50` | 0 | 1 |
| `Daily loss limit exceeded: -5553.83` | 0 | 1 |
| `Daily loss limit exceeded: -5642.64` | 0 | 1 |
| `Daily loss limit exceeded: -7510.80` | 0 | 1 |
| `Daily loss limit exceeded: -8024.88` | 1 | 0 |
| `Daily loss limit exceeded: -9166.79` | 0 | 1 |
| `Daily loss limit exceeded: -9842.89` | 1 | 0 |
| `Max trades per day reached (3)` | 5 | 0 |
| `RISK-OFF: Daily loss limit hit (-12049.87)` | 0 | 3 |
| `RISK-OFF: Daily loss limit hit (-12384.11)` | 0 | 1 |
| `RISK-OFF: Daily loss limit hit (-13493.73)` | 1 | 0 |
| `RISK-OFF: Daily loss limit hit (-5092.06)` | 0 | 1 |
| `RISK-OFF: Daily loss limit hit (-5411.82)` | 0 | 2 |
| `RISK-OFF: Daily loss limit hit (-5510.50)` | 0 | 3 |
| `RISK-OFF: Daily loss limit hit (-5642.64)` | 0 | 4 |
| `RISK-OFF: Daily loss limit hit (-7510.80)` | 0 | 2 |
| `RISK-OFF: Daily loss limit hit (-9166.79)` | 0 | 1 |

Trades/day (production): mean **0.94**, max **3**. Worst day **₹-13,494**, best day **₹19,877**, days below −₹5,000: **9** of 81.

## 8. Regime detail (production path)

| Regime | days | trades | net | PF | DD% | win% | expectancy |
|---|---|---|---|---|---|---|---|
| trending | 39 | 43 | -50,343 | 0.43 | 50.34 | 53.5 | -1,170.77 |
| sideways | 62 | 80 | 35,639 | 1.50 | 14.52 | 73.8 | 445.49 |
| high_volatility | 3 | 0 | — | — | — | — | — |
| low_volatility | 6 | 9 | -6,574 | 0.34 | 7.98 | 66.7 | -730.44 |
| gap_day | 13 | 17 | 12,411 | 2.14 | 3.58 | 76.5 | 730.05 |
