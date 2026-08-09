# Strategy audit — `institutional_momentum`

Window: 2026-02-01 09:15:00 → 2026-07-31 15:25:00 (123 trading days)  
Rally set: **381** sustained underlying moves (≥0.30% within 90 min).  
Production entry flags: `{'enable_volume_filter': False, 'enable_ema_filter': False, 'enable_vwap_filter': False, 'enable_rsi_filter': False, 'enable_squeeze_filter': True, 'enable_extension_filter': True, 'enable_cpr_filter': True, 'enable_aggression_filter': True}`, daily cap **3**.

## 1. Baseline — production path vs legacy path

| Metric | PRODUCTION (config/settings.json) | legacy (no settings) |
|---|---|---|
| trades (legs) | 120 | 234 |
| net profit | -20,088 | 80,048 |
| expectancy | -167.40 | 342.09 |
| profit factor | 0.91 | 1.21 |
| max drawdown % | 55.34 | 20.58 |
| recovery factor | -0.36 | 3.89 |
| win rate % | 50.8 | 59.0 |
| realised R:R | 0.88 | 0.84 |
| consecutive losses | 5 | 5 |
| avg holding min | 44.4 | 38.7 |
| Q2 ratio | 3.16 | 1.18 |
| false-signal rate % | 39.8 | 34.0 |
| first-touch edge pp | 5.3 | 19.1 |
| never-rose % | 5.3 | 8.6 |
| rally capture % | 21.3 | 40.2 |
| held % of covered run | 28.6 | 33.3 |
| positions | 113 | 209 |
| **verdict** | **REMOVE** | **KEEP** |

`PRODUCTION (config/settings.json)` — REMOVE: N1 no edge (PF=0.91, expectancy=-167.40); N4 survivability: 55.3% drawdown exceeds 30% (recovering it requires +124%); Q1 recovery factor -0.36 < 2.0 (did not earn twice its worst drawdown); Q2 drawdown unexplained by risk model: 55.3% is 3.16x the 17.5% that 5 consecutive losses at 3.5%/trade would produce; Q3 regime robustness: profitable in only 2/4 adequately-sampled regimes

`legacy (no settings)` — KEEP: Passes all necessary and quality gates: PF=1.21, expectancy=342.09, net=80048, drawdown=20.6%, recovery=3.89, profitable in 3/5 regimes.

## 2. Signal duty cycle and churn

Tests the re-entry mechanism found in `ema_rsi` and `advanced_ai` rather than assuming it. A level-triggered strategy re-enters the same setup bar after bar, which shows up as a short median gap between one exit and the next entry plus a high same-direction rate.

| Measure | PRODUCTION (config/settings.json) | legacy (no settings) |
|---|---|---|
| bars evaluated | 9,220 | 9,220 |
| signal bars | 179 | 488 |
| duty cycle % | 1.9 | 5.3 |
| signals repeating previous bar % | 13.4 | 28.3 |
| same-day re-entries | 32 | 100 |
| median exit→next entry (min) | 77.5 | 87.5 |
| p25 gap (min) | 45.0 | 30.0 |
| re-entries within one bar % | 6.2 | 3.0 |
| same-direction re-entries % | 53.1 | 81.0 |

## 3. Entry quality (production path, exit-independent)

First touch of ±1R, where R is the position's real `resolve_initial_stop` distance. `false entry` = loss-first.

| Outcome | n | share |
|---|---|---|
| win-first | 51 | 45.1% |
| **loss-first (false entry)** | 45 | **39.8%** |
| neither within the day | 17 | 15.0% |

| Excursion (R) | p10 | p25 | median | p75 | p90 |
|---|---|---|---|---|---|
| mfe_r | 0.12 | 0.47 | 1.37 | 2.97 | 5.24 |
| mae_r | -4.73 | -2.70 | -1.10 | -0.42 | 0.12 |

### 3b. Entry timing

| Session bucket | n | first-touch edge pp | net P&L | mean P&L |
|---|---|---|---|---|
| 09:15-10:00 | 14 | +57.1 | -5,980 | -427 |
| 10:00-11:00 | 9 | +33.3 | 15,794 | 1,755 |
| 11:00-12:30 | 25 | +16.0 | 31,821 | 1,273 |
| 12:30-14:00 | 33 | -27.3 | -48,926 | -1,483 |
| 14:00-15:30 | 32 | +0.0 | -12,798 | -400 |

## 4. Exit behaviour (production path)

Grouped by exit MECHANISM — `TieredExitManager`'s reason strings embed live numbers, so the raw text would give one bucket per trade.

| Exit mechanism | n | % | net P&L | mean | median hold (min) |
|---|---|---|---|---|---|
| `eod` | 21 | 18.6% | 33,256 | 1,584 | 35 |
| `hard_stop` | 41 | 36.3% | -195,956 | -4,779 | 20 |
| `tiered_exhaustion` | 51 | 45.1% | 142,612 | 2,796 | 65 |

### 4b. Premature exits and trend capture

Premature = the premium exceeded the exit price within the next 60 minutes of the same day, i.e. the position was closed into a move that was still running.

| Measure | value |
|---|---|
| positions measured | 113 |
| premature exits | 81.4% |
| median missed upside after exit | 6.01% |
| p90 missed upside after exit | 72.29% |
| median capture of the in-trade move | 30.0% |
| median trend capture (vs day's best) | 5.0% |
| median continuation +5min after exit | 1.29% |
| median continuation +15min after exit | 3.86% |
| median continuation +30min after exit | 5.35% |
| median continuation +60min after exit | 6.01% |

### 4c. Exit mechanism mix (legs) and trailing behaviour

| Mechanism | legs | % | median realised % | median giveback pp | armed % |
|---|---|---|---|---|---|
| `eod` | 21 | 17.5% | 2.15 | 2.42 | 90% |
| `hard_stop` | 41 | 34.2% | -16.44 | 18.08 | 34% |
| `tiered_exhaustion` | 51 | 42.5% | 7.17 | 8.26 | 100% |
| `tiered_partial` | 7 | 5.8% | 53.18 | 0.00 | 100% |

## 5. Missed opportunities (production path)

Every rally in the fixed set the strategy was NOT positioned for, classified by cause. Only `signalled but blocked` and `opposite position held` are addressable; `no setup` is the strategy's own philosophy.

| Cause | n | share of missed |
|---|---|---|
| no setup | 295 | 98.3% |
| signalled but blocked | 5 | 1.7% |
| **total missed** | **300** | of 381 runs |

## 6. Position sizing, stops and risk taken (production path)

| Measure | p10 | median | p90 |
|---|---|---|---|
| entry premium | 58.11 | 182.84 | 221.21 |
| risk per unit (₹) | 10.83 | 23.29 | 27.13 |
| stop distance % of premium | 12.26 | 12.73 | 17.32 |

| Stop band | positions | share | net P&L | false-signal % |
|---|---|---|---|---|
| `>₹250` | 1 | 0.9% | 932 | 0.0% |
| `₹100-150` | 14 | 12.4% | 20,565 | 42.9% |
| `₹150-250` | 73 | 64.6% | 16,169 | 37.0% |
| `₹20-50` | 9 | 8.0% | -22,414 | 55.6% |
| `₹50-100` | 16 | 14.2% | -35,339 | 43.8% |

## 7. Rejection and risk-control behaviour

| Counter | PRODUCTION (config/settings.json) | legacy (no settings) |
|---|---|---|
| days_run | 123 | 123 |
| candidate_signals | 129 | 264 |
| rejected_risk_gate | 9 | 29 |
| rejected_market_hours | 7 | 26 |
| rejected_untradeable_sl | 0 | 0 |

Risk-gate rejections by the gate's own reason string:

| Reason | PRODUCTION (config/settings.json) | legacy (no settings) |
|---|---|---|
| `Daily loss limit exceeded: -12049.87` | 0 | 1 |
| `Daily loss limit exceeded: -12384.11` | 0 | 1 |
| `Daily loss limit exceeded: -13493.73` | 1 | 0 |
| `Daily loss limit exceeded: -13824.29` | 1 | 1 |
| `Daily loss limit exceeded: -5092.06` | 0 | 1 |
| `Daily loss limit exceeded: -5411.82` | 0 | 1 |
| `Daily loss limit exceeded: -5510.50` | 0 | 1 |
| `Daily loss limit exceeded: -5642.64` | 0 | 1 |
| `Daily loss limit exceeded: -6824.49` | 0 | 1 |
| `Daily loss limit exceeded: -6969.71` | 1 | 0 |
| `Daily loss limit exceeded: -7011.05` | 0 | 1 |
| `Daily loss limit exceeded: -7510.80` | 0 | 1 |
| `Daily loss limit exceeded: -8011.96` | 0 | 1 |
| `Daily loss limit exceeded: -8024.88` | 1 | 0 |
| `Daily loss limit exceeded: -9166.79` | 0 | 1 |
| `Daily loss limit exceeded: -9842.89` | 1 | 0 |
| `Max trades per day reached (3)` | 1 | 0 |
| `RISK-OFF: Daily loss limit hit (-12049.87)` | 0 | 3 |
| `RISK-OFF: Daily loss limit hit (-12384.11)` | 0 | 1 |
| `RISK-OFF: Daily loss limit hit (-13493.73)` | 1 | 0 |
| `RISK-OFF: Daily loss limit hit (-13824.29)` | 1 | 0 |
| `RISK-OFF: Daily loss limit hit (-5092.06)` | 0 | 1 |
| `RISK-OFF: Daily loss limit hit (-5411.82)` | 0 | 2 |
| `RISK-OFF: Daily loss limit hit (-5510.50)` | 0 | 3 |
| `RISK-OFF: Daily loss limit hit (-5642.64)` | 0 | 4 |
| `RISK-OFF: Daily loss limit hit (-6969.71)` | 1 | 0 |
| `RISK-OFF: Daily loss limit hit (-7510.80)` | 0 | 2 |
| `RISK-OFF: Daily loss limit hit (-9166.79)` | 0 | 1 |

Trades/day (production): mean **0.92**, max **3**. Worst day **₹-13,824**, best day **₹17,584**, days below −₹5,000: **11** of 81.

## 8. Regime detail (production path)

| Regime | days | trades | net | PF | DD% | win% | expectancy |
|---|---|---|---|---|---|---|---|
| trending | 39 | 39 | -56,073 | 0.46 | 56.07 | 38.5 | -1,437.76 |
| sideways | 62 | 60 | 38,876 | 1.47 | 13.11 | 58.3 | 647.94 |
| high_volatility | 3 | 0 | — | — | — | — | — |
| low_volatility | 6 | 9 | -6,284 | 0.40 | 7.39 | 55.6 | -698.23 |
| gap_day | 13 | 12 | 3,392 | 1.17 | 9.81 | 50.0 | 282.70 |
