# Strategy audit — `structure_break`

Window: 2025-05-16 09:15:00 → 2026-01-30 15:25:00 (178 trading days) — **DEV** split  
Risk tier: **base** (1% base, research)  
Rally set: **313** sustained underlying moves (≥0.30% within 90 min).  
Production entry flags: `{'enable_volume_filter': False, 'enable_ema_filter': False, 'enable_vwap_filter': False, 'enable_rsi_filter': False, 'enable_squeeze_filter': True, 'enable_extension_filter': True, 'enable_cpr_filter': True, 'enable_aggression_filter': True}`, daily cap **3**.

## 1. Baseline — production path vs legacy path

| Metric | PRODUCTION (config/settings.json) | legacy (no settings) |
|---|---|---|
| trades (legs) | 61 | 273 |
| net profit | 13,116 | 43,749 |
| expectancy | 215.02 | 160.25 |
| profit factor | 1.90 | 1.51 |
| max drawdown % | 3.70 | 8.99 |
| recovery factor | 3.55 | 4.87 |
| win rate % | 83.6 | 75.8 |
| realised R:R | 0.37 | 0.48 |
| consecutive losses | 2 | 4 |
| avg holding min | 42.0 | 36.6 |
| Q2 ratio | 0.53 | 0.64 |
| false-signal rate % | 39.5 | 34.8 |
| first-touch edge pp | 9.3 | 17.1 |
| never-rose % | 9.3 | 9.0 |
| rally capture % | 11.8 | 42.5 |
| held % of covered run | 22.2 | 22.2 |
| positions | 43 | 210 |
| **verdict** | **KEEP** | **KEEP** |

`PRODUCTION (config/settings.json)` — KEEP: Passes all necessary and quality gates: PF=1.90, expectancy=215.02, net=13116, drawdown=3.7%, recovery=3.55, profitable in 3/4 regimes.

`legacy (no settings)` — KEEP: Passes all necessary and quality gates: PF=1.51, expectancy=160.25, net=43749, drawdown=9.0%, recovery=4.87, profitable in 3/5 regimes.

## 2. Signal duty cycle and churn

Tests the re-entry mechanism found in `ema_rsi` and `advanced_ai` rather than assuming it. A level-triggered strategy re-enters the same setup bar after bar, which shows up as a short median gap between one exit and the next entry plus a high same-direction rate.

| Measure | PRODUCTION (config/settings.json) | legacy (no settings) |
|---|---|---|
| bars evaluated | 13,288 | 13,288 |
| signal bars | 43 | 210 |
| duty cycle % | 0.3 | 1.6 |
| signals repeating previous bar % | 0.0 | 0.0 |
| same-day re-entries | 2 | 38 |
| median exit→next entry (min) | 177.5 | 135.0 |
| p25 gap (min) | 153.8 | 75.0 |
| re-entries within one bar % | 0.0 | 2.6 |
| same-direction re-entries % | 0.0 | 0.0 |

## 3. Entry quality (production path, exit-independent)

First touch of ±1R, where R is the position's real `resolve_initial_stop` distance. `false entry` = loss-first.

| Outcome | n | share |
|---|---|---|
| win-first | 21 | 48.8% |
| **loss-first (false entry)** | 17 | **39.5%** |
| neither within the day | 5 | 11.6% |

| Excursion (R) | p10 | p25 | median | p75 | p90 |
|---|---|---|---|---|---|
| mfe_r | 0.09 | 0.64 | 1.51 | 3.32 | 4.43 |
| mae_r | -5.10 | -2.72 | -1.50 | -0.47 | -0.18 |

### 3b. Entry timing

| Session bucket | n | first-touch edge pp | net P&L | mean P&L |
|---|---|---|---|---|
| 09:15-10:00 | 12 | +50.0 | 5,742 | 479 |
| 10:00-11:00 | 13 | +7.7 | 3,590 | 276 |
| 11:00-12:30 | 7 | -14.3 | 2,528 | 361 |
| 12:30-14:00 | 5 | -60.0 | -3,446 | -689 |
| 14:00-15:30 | 6 | +16.7 | 4,702 | 784 |

## 4. Exit behaviour (production path)

Grouped by exit MECHANISM — `TieredExitManager`'s reason strings embed live numbers, so the raw text would give one bucket per trade.

| Exit mechanism | n | % | net P&L | mean | median hold (min) |
|---|---|---|---|---|---|
| `end_of_data` | 1 | 2.3% | 498 | 498 | 10 |
| `eod` | 3 | 7.0% | 3,161 | 1,054 | 15 |
| `stop` | 14 | 32.6% | -10,161 | -726 | 28 |
| `trail_atr` | 4 | 9.3% | 3,772 | 943 | 40 |
| `trail_offset` | 21 | 48.8% | 15,847 | 755 | 25 |

### 4b. Premature exits and trend capture

Premature = the premium exceeded the exit price within the next 60 minutes of the same day, i.e. the position was closed into a move that was still running.

| Measure | value |
|---|---|
| positions measured | 43 |
| premature exits | 76.2% |
| median missed upside after exit | 4.02% |
| p90 missed upside after exit | 32.95% |
| median capture of the in-trade move | 67.1% |
| median trend capture (vs day's best) | 28.2% |
| median continuation +5min after exit | -0.33% |
| median continuation +15min after exit | 1.24% |
| median continuation +30min after exit | 2.66% |
| median continuation +60min after exit | 4.02% |

### 4c. Exit mechanism mix (legs) and trailing behaviour

| Mechanism | legs | % | median realised % | median giveback pp | armed % |
|---|---|---|---|---|---|
| `end_of_data` | 1 | 1.6% | 12.87 | 0.00 | 100% |
| `eod` | 3 | 4.9% | 36.97 | 0.00 | 67% |
| `partial` | 18 | 29.5% | 19.72 | 0.00 | 100% |
| `stop` | 14 | 23.0% | -14.84 | 16.54 | 50% |
| `trail_atr` | 4 | 6.6% | 11.06 | 17.71 | 100% |
| `trail_offset` | 21 | 34.4% | 4.25 | 2.12 | 100% |

## 5. Missed opportunities (production path)

Every rally in the fixed set the strategy was NOT positioned for, classified by cause. Only `signalled but blocked` and `opposite position held` are addressable; `no setup` is the strategy's own philosophy.

| Cause | n | share of missed |
|---|---|---|
| no setup | 276 | 100.0% |
| **total missed** | **276** | of 313 runs |

## 6. Position sizing, stops and risk taken (production path)

| Measure | p10 | median | p90 |
|---|---|---|---|
| entry premium | 46.62 | 161.38 | 227.73 |
| risk per unit (₹) | 8.05 | 21.13 | 27.79 |
| stop distance % of premium | 12.19 | 13.10 | 18.37 |

| Stop band | positions | share | net P&L | false-signal % |
|---|---|---|---|---|
| `>₹250` | 1 | 2.3% | 286 | 100.0% |
| `₹100-150` | 6 | 14.0% | 847 | 50.0% |
| `₹150-250` | 21 | 48.8% | 5,188 | 38.1% |
| `₹20-50` | 5 | 11.6% | 5,235 | 20.0% |
| `₹50-100` | 10 | 23.3% | 1,561 | 40.0% |

## 7. Rejection and risk-control behaviour

| Counter | PRODUCTION (config/settings.json) | legacy (no settings) |
|---|---|---|
| days_run | 178 | 178 |
| candidate_signals | 43 | 210 |
| rejected_risk_gate | 0 | 0 |
| rejected_market_hours | 0 | 0 |
| rejected_untradeable_sl | 0 | 0 |

Risk-gate rejections by the gate's own reason string:

| Reason | PRODUCTION (config/settings.json) | legacy (no settings) |
|---|---|---|

Trades/day (production): mean **0.24**, max **2**. Worst day **₹-2,344**, best day **₹2,917**, days below −₹5,000: **0** of 41.

## 8. Regime detail (production path)

| Regime | days | trades | net | PF | DD% | win% | expectancy |
|---|---|---|---|---|---|---|---|
| trending | 70 | 24 | 5,287 | 1.97 | 3.66 | 87.5 | 220.29 |
| sideways | 72 | 28 | 8,992 | 3.40 | 2.14 | 85.7 | 321.14 |
| high_volatility | 13 | 5 | -1,400 | 0.68 | 3.98 | 60.0 | -279.91 |
| low_volatility | 17 | 3 | 50 | 1.05 | 1.05 | 66.7 | 16.71 |
| gap_day | 6 | 1 | 187 | Infinity | 0.00 | 100.0 | 186.76 |
