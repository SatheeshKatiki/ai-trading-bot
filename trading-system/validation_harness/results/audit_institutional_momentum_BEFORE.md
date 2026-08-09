# Strategy audit — `institutional_momentum`

Window: 2026-02-01 09:15:00 → 2026-07-31 15:25:00 (123 trading days)  
Rally set: **381** sustained underlying moves (≥0.30% within 90 min).  
Production entry flags: `{'enable_volume_filter': False, 'enable_ema_filter': False, 'enable_vwap_filter': False, 'enable_rsi_filter': False, 'enable_squeeze_filter': True, 'enable_extension_filter': True, 'enable_cpr_filter': True, 'enable_aggression_filter': True}`, daily cap **3**.

## 1. Baseline — production path vs legacy path

| Metric | PRODUCTION (config/settings.json) | legacy (no settings) |
|---|---|---|
| trades (legs) | 0 | 317 |
| net profit | 0 | 88,511 |
| expectancy | — | 279.21 |
| profit factor | — | 1.25 |
| max drawdown % | 0.00 | 15.12 |
| recovery factor | — | 5.85 |
| win rate % | — | 72.2 |
| realised R:R | — | 0.48 |
| consecutive losses | 0 | 4 |
| avg holding min | — | 25.4 |
| Q2 ratio | — | 1.08 |
| false-signal rate % | — | 34.0 |
| first-touch edge pp | — | 17.8 |
| never-rose % | — | 10.0 |
| rally capture % | — | 39.6 |
| held % of covered run | — | 27.3 |
| positions | 0 | 241 |
| **verdict** | **IMPROVE** | **KEEP** |

`PRODUCTION (config/settings.json)` — IMPROVE: N2 sample too small (0 trades < 30) — neither KEEP nor REMOVE is supportable; N1 no edge (PF=0.00, expectancy=0.00); Q1 recovery factor 0.00 < 2.0 (did not earn twice its worst drawdown)

`legacy (no settings)` — KEEP: Passes all necessary and quality gates: PF=1.25, expectancy=279.21, net=88511, drawdown=15.1%, recovery=5.85, profitable in 4/5 regimes.

## 2. Signal duty cycle and churn

Tests the re-entry mechanism found in `ema_rsi` and `advanced_ai` rather than assuming it. A level-triggered strategy re-enters the same setup bar after bar, which shows up as a short median gap between one exit and the next entry plus a high same-direction rate.

| Measure | PRODUCTION (config/settings.json) | legacy (no settings) |
|---|---|---|
| bars evaluated | 9,220 | 9,220 |
| signal bars | 0 | 488 |
| duty cycle % | 0.0 | 5.3 |
| signals repeating previous bar % | — | 28.3 |
| same-day re-entries | — | 132 |
| median exit→next entry (min) | — | 50.0 |
| p25 gap (min) | — | 20.0 |
| re-entries within one bar % | — | 8.3 |
| same-direction re-entries % | — | 84.8 |

## 3-8. Production path takes ZERO trades

`institutional_momentum` opened **no positions at all** on the production path across 123 trading days (`candidate_signals` = 0), so every position-level section below is undefined. That is the audit's headline finding, not a harness failure — the legacy column above is the only configuration of this strategy that trades.
