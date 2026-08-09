# Strategy audit — `structure_break`

Window: 2026-02-01 09:15:00 → 2026-07-31 15:25:00 (123 trading days) — **OOS** split  
Risk tier: **base** (1% base, research)  
Rally set: **381** sustained underlying moves (≥0.30% within 90 min).  
Production entry flags: `{'enable_volume_filter': False, 'enable_ema_filter': False, 'enable_vwap_filter': False, 'enable_rsi_filter': False, 'enable_squeeze_filter': True, 'enable_extension_filter': True, 'enable_cpr_filter': True, 'enable_aggression_filter': True}`, daily cap **3**.

## 1. Baseline — production path vs legacy path

| Metric | PRODUCTION (config/settings.json) | legacy (no settings) |
|---|---|---|
| trades (legs) | 37 | 194 |
| net profit | 20,647 | 16,542 |
| expectancy | 558.04 | 85.27 |
| profit factor | 3.11 | 1.19 |
| max drawdown % | 5.19 | 9.24 |
| recovery factor | 3.98 | 1.79 |
| win rate % | 83.8 | 71.6 |
| realised R:R | 0.60 | 0.47 |
| consecutive losses | 3 | 4 |
| avg holding min | 29.1 | 30.3 |
| Q2 ratio | 0.49 | 0.66 |
| false-signal rate % | 36.7 | 42.7 |
| first-touch edge pp | 16.7 | 7.3 |
| never-rose % | 3.3 | 10.7 |
| rally capture % | 7.3 | 28.3 |
| held % of covered run | 32.3 | 23.5 |
| positions | 30 | 150 |
| **verdict** | **KEEP** | **IMPROVE** |

`PRODUCTION (config/settings.json)` — KEEP: Passes all necessary and quality gates: PF=3.11, expectancy=558.04, net=20647, drawdown=5.2%, recovery=3.98, profitable in 2/3 regimes.

`legacy (no settings)` — IMPROVE: Q1 recovery factor 1.79 < 2.0 (did not earn twice its worst drawdown)

## 2. Signal duty cycle and churn

Tests the re-entry mechanism found in `ema_rsi` and `advanced_ai` rather than assuming it. A level-triggered strategy re-enters the same setup bar after bar, which shows up as a short median gap between one exit and the next entry plus a high same-direction rate.

| Measure | PRODUCTION (config/settings.json) | legacy (no settings) |
|---|---|---|
| bars evaluated | 9,220 | 9,220 |
| signal bars | 30 | 153 |
| duty cycle % | 0.3 | 1.7 |
| signals repeating previous bar % | 0.0 | 0.0 |
| same-day re-entries | 3 | 31 |
| median exit→next entry (min) | 65.0 | 160.0 |
| p25 gap (min) | 65.0 | 77.5 |
| re-entries within one bar % | 0.0 | 0.0 |
| same-direction re-entries % | 0.0 | 0.0 |

## 3. Entry quality (production path, exit-independent)

First touch of ±1R, where R is the position's real `resolve_initial_stop` distance. `false entry` = loss-first.

| Outcome | n | share |
|---|---|---|
| win-first | 16 | 53.3% |
| **loss-first (false entry)** | 11 | **36.7%** |
| neither within the day | 3 | 10.0% |

| Excursion (R) | p10 | p25 | median | p75 | p90 |
|---|---|---|---|---|---|
| mfe_r | 0.47 | 0.85 | 2.30 | 7.70 | 17.94 |
| mae_r | -3.93 | -2.33 | -0.80 | -0.23 | 0.37 |

### 3b. Entry timing

| Session bucket | n | first-touch edge pp | net P&L | mean P&L |
|---|---|---|---|---|
| 09:15-10:00 | 10 | +30.0 | 5,014 | 501 |
| 10:00-11:00 | 9 | -11.1 | -352 | -39 |
| 11:00-12:30 | 3 | +100.0 | 13,980 | 4,660 |
| 12:30-14:00 | 4 | +0.0 | 1,496 | 374 |
| 14:00-15:30 | 4 | +0.0 | 509 | 127 |

## 4. Exit behaviour (production path)

Grouped by exit MECHANISM — `TieredExitManager`'s reason strings embed live numbers, so the raw text would give one bucket per trade.

| Exit mechanism | n | % | net P&L | mean | median hold (min) |
|---|---|---|---|---|---|
| `stop` | 6 | 20.0% | -9,793 | -1,632 | 10 |
| `trail_atr` | 1 | 3.3% | 136 | 136 | 160 |
| `trail_offset` | 23 | 76.7% | 30,304 | 1,318 | 25 |

### 4b. Premature exits and trend capture

Premature = the premium exceeded the exit price within the next 60 minutes of the same day, i.e. the position was closed into a move that was still running.

| Measure | value |
|---|---|
| positions measured | 30 |
| premature exits | 90.0% |
| median missed upside after exit | 10.69% |
| p90 missed upside after exit | 55.64% |
| median capture of the in-trade move | 59.4% |
| median trend capture (vs day's best) | 17.6% |
| median continuation +5min after exit | 1.60% |
| median continuation +15min after exit | 5.21% |
| median continuation +30min after exit | 8.68% |
| median continuation +60min after exit | 10.69% |

### 4c. Exit mechanism mix (legs) and trailing behaviour

| Mechanism | legs | % | median realised % | median giveback pp | armed % |
|---|---|---|---|---|---|
| `partial` | 7 | 18.9% | 16.22 | 0.00 | 100% |
| `stop` | 6 | 16.2% | -23.30 | 25.02 | 50% |
| `trail_atr` | 1 | 2.7% | 1.27 | 5.26 | 100% |
| `trail_offset` | 23 | 62.2% | 4.46 | 2.08 | 100% |

## 5. Missed opportunities (production path)

Every rally in the fixed set the strategy was NOT positioned for, classified by cause. Only `signalled but blocked` and `opposite position held` are addressable; `no setup` is the strategy's own philosophy.

| Cause | n | share of missed |
|---|---|---|
| no setup | 353 | 100.0% |
| **total missed** | **353** | of 381 runs |

## 6. Position sizing, stops and risk taken (production path)

| Measure | p10 | median | p90 |
|---|---|---|---|
| entry premium | 43.62 | 182.07 | 232.66 |
| risk per unit (₹) | 7.36 | 23.22 | 28.26 |
| stop distance % of premium | 12.15 | 12.75 | 17.55 |

| Stop band | positions | share | net P&L | false-signal % |
|---|---|---|---|---|
| `₹100-150` | 4 | 13.3% | -5 | 25.0% |
| `₹150-250` | 21 | 70.0% | 18,566 | 33.3% |
| `₹20-50` | 4 | 13.3% | 3,359 | 50.0% |
| `₹50-100` | 1 | 3.3% | -1,272 | 100.0% |

## 7. Rejection and risk-control behaviour

| Counter | PRODUCTION (config/settings.json) | legacy (no settings) |
|---|---|---|
| days_run | 123 | 123 |
| candidate_signals | 30 | 153 |
| rejected_risk_gate | 0 | 0 |
| rejected_market_hours | 0 | 3 |
| rejected_untradeable_sl | 0 | 0 |

Risk-gate rejections by the gate's own reason string:

| Reason | PRODUCTION (config/settings.json) | legacy (no settings) |
|---|---|---|

Trades/day (production): mean **0.24**, max **2**. Worst day **₹-2,109**, best day **₹7,638**, days below −₹5,000: **0** of 27.

## 8. Regime detail (production path)

| Regime | days | trades | net | PF | DD% | win% | expectancy |
|---|---|---|---|---|---|---|---|
| trending | 39 | 5 | 1,351 | 1.73 | 1.81 | 80.0 | 270.27 |
| sideways | 62 | 26 | 17,552 | 3.63 | 4.15 | 84.6 | 675.07 |
| high_volatility | 3 | 3 | -563 | 0.56 | 1.27 | 66.7 | -187.63 |
| low_volatility | 6 | 1 | 1,154 | Infinity | 0.00 | 100.0 | 1,153.52 |
| gap_day | 13 | 2 | 1,154 | Infinity | 0.00 | 100.0 | 576.76 |
