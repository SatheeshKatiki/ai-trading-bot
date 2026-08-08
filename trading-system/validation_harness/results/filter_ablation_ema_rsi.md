# Entry-filter and trade-cap ablation — `ema_rsi`

Window: 2026-02-01 09:15:00 → 2026-07-31 15:25:00 (123 trading days)  
Capital: Rs 100,000  
Rally set: **381** sustained underlying moves (≥0.30% within 90 min), identical for every configuration — only coverage changes.

Every row is a full day-isolated run through the production pipeline. One variable at a time: LOO removes a single filter from production, SOLO runs a single filter against the unfiltered path, CAP sweeps the daily cap with filters held at production.

## All configurations

| Config | pos | net | exp | PF | DD% | recov | win% | R:R | Q2 | false% | edge pp | rally% | verdict |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| PRODUCTION (all 4 filters, cap 3) | 145 | 81,922 | 422 | 1.42 | 15.24 | 5.38 | 75.3 | 0.47 | 1.45 | 35.9 | 14.5 | 23.4 | KEEP |
| legacy (no filters, no cap) | 392 | 211,316 | 405 | 1.39 | 19.01 | 11.12 | 72.6 | 0.53 | 1.36 | 37.5 | 13.8 | 40.9 | KEEP |
| LOO: production minus squeeze | 202 | 72,667 | 276 | 1.26 | 18.33 | 3.96 | 73.4 | 0.46 | 1.05 | 39.6 | 8.4 | 27.3 | KEEP |
| LOO: production minus extension | 151 | 74,348 | 368 | 1.35 | 16.96 | 4.38 | 74.3 | 0.47 | 1.21 | 37.1 | 12.6 | 24.9 | KEEP |
| LOO: production minus cpr | 171 | 109,681 | 481 | 1.47 | 14.45 | 7.59 | 74.6 | 0.50 | 0.69 | 33.9 | 17.0 | 26.8 | KEEP |
| LOO: production minus aggression | 186 | 121,729 | 470 | 1.48 | 16.79 | 7.25 | 76.8 | 0.45 | 1.60 | 36.0 | 19.4 | 26.2 | KEEP |
| SOLO: squeeze only, no cap | 277 | 193,988 | 510 | 1.50 | 14.91 | 13.01 | 73.9 | 0.53 | 1.06 | 35.7 | 17.0 | 35.2 | KEEP |
| SOLO: extension only, no cap | 376 | 218,017 | 435 | 1.43 | 18.42 | 11.83 | 73.1 | 0.53 | 1.32 | 36.4 | 15.4 | 39.1 | KEEP |
| SOLO: cpr only, no cap | 347 | 150,476 | 326 | 1.31 | 22.91 | 6.57 | 72.1 | 0.51 | 1.31 | 38.6 | 11.2 | 36.7 | KEEP |
| SOLO: aggression only, no cap | 291 | 147,722 | 388 | 1.38 | 13.46 | 10.98 | 73.5 | 0.50 | 0.77 | 36.8 | 12.4 | 35.4 | KEEP |
| CAP: all filters, cap unlimited | 158 | 92,023 | 432 | 1.43 | 15.00 | 6.13 | 75.1 | 0.47 | 1.43 | 34.8 | 15.8 | 24.9 | KEEP |
| CAP: all filters, cap 4 | 151 | 77,342 | 383 | 1.38 | 15.15 | 5.11 | 74.8 | 0.47 | 1.44 | 35.1 | 14.6 | 24.1 | KEEP |
| CAP: all filters, cap 5 | 156 | 93,151 | 444 | 1.45 | 14.90 | 6.25 | 75.2 | 0.48 | 1.42 | 34.6 | 16.0 | 24.7 | KEEP |
| CAP: all filters, cap 6 | 157 | 98,239 | 463 | 1.47 | 14.46 | 6.80 | 75.5 | 0.48 | 1.38 | 34.4 | 16.6 | 24.9 | KEEP |
| CAP: all filters, cap 8 | 158 | 92,023 | 432 | 1.43 | 15.00 | 6.13 | 75.1 | 0.47 | 1.43 | 34.8 | 15.8 | 24.9 | KEEP |

## 1. What each filter blocks (leave-one-out)

The cohort is the set of positions that appear when the filter is removed from the production configuration — precisely the trades that filter was blocking. `edge` is win-first minus loss-first on those trades alone.

| Filter removed | trades it blocks | their net P&L | mean | win-first | loss-first | edge | verdict on the filter |
|---|---|---|---|---|---|---|---|
| squeeze | 79 | -1,379 | -17 | 40.5% | 44.3% | **-3.8pp** | removes losing/neutral trades |
| extension | 13 | 4,676 | 360 | 53.8% | 46.2% | **+7.7pp** | removes PROFITABLE trades |
| cpr | 32 | 36,535 | 1,142 | 50.0% | 31.2% | **+18.8pp** | removes PROFITABLE trades |
| aggression | 85 | 22,179 | 261 | 56.5% | 40.0% | **+16.5pp** | removes PROFITABLE trades |

### Full metric impact of removing each filter

| Config | Δ positions | Δ net | Δ PF | Δ DD% | Δ recov | Δ false% | Δ edge pp | Δ rally% |
|---|---|---|---|---|---|---|---|---|
| minus squeeze | +57 | -9,255 | -0.16 | +3.09 | -1.42 | +3.7 | -6.1 | +3.9 |
| minus extension | +6 | -7,574 | -0.07 | +1.72 | -1.00 | +1.2 | -1.9 | +1.6 |
| minus cpr | +26 | +27,759 | +0.05 | -0.79 | +2.21 | -1.9 | +2.5 | +3.4 |
| minus aggression | +41 | +39,807 | +0.06 | +1.55 | +1.87 | +0.2 | +4.9 | +2.9 |

## 2. Each filter on its own (SOLO, against the unfiltered path)

| Config | positions | net | PF | DD% | false% | edge pp | rally% |
|---|---|---|---|---|---|---|---|
| legacy: no filters | 392 | 211,316 | 1.39 | 19.01 | 37.5 | 13.8 | 40.9 |
| squeeze only | 277 | 193,988 | 1.50 | 14.91 | 35.7 | 17.0 | 35.2 |
| extension only | 376 | 218,017 | 1.43 | 18.42 | 36.4 | 15.4 | 39.1 |
| cpr only | 347 | 150,476 | 1.31 | 22.91 | 38.6 | 11.2 | 36.7 |
| aggression only | 291 | 147,722 | 1.38 | 13.46 | 36.8 | 12.4 | 35.4 |

## 3. The daily trade cap

| Config | positions | trades/day | days at/over cap | net | PF | DD% | recov | rally% |
|---|---|---|---|---|---|---|---|---|
| PRODUCTION (all 4 filters, cap 3) | 145 | 1.59 | 7 | 81,922 | 1.42 | 15.24 | 5.38 | 23.4 |
| CAP: all filters, cap unlimited | 158 | 1.74 | 0 | 92,023 | 1.43 | 15.00 | 6.13 | 24.9 |
| CAP: all filters, cap 4 | 151 | 1.66 | 2 | 77,342 | 1.38 | 15.15 | 5.11 | 24.1 |
| CAP: all filters, cap 5 | 156 | 1.71 | 0 | 93,151 | 1.45 | 14.90 | 6.25 | 24.7 |
| CAP: all filters, cap 6 | 157 | 1.73 | 0 | 98,239 | 1.47 | 14.46 | 6.80 | 24.9 |
| CAP: all filters, cap 8 | 158 | 1.74 | 0 | 92,023 | 1.43 | 15.00 | 6.13 | 24.9 |

## 4. Regime detail for every configuration

| Config | trending | sideways | high_volatility | low_volatility | gap_day |
|---|---|---|---|---|---|
| PRODUCTION (all 4 filters, cap 3) | 68t / 33,714 | 95t / 26,709 | 7t / 16,231 | 4t / -10,883 | 20t / 16,151 |
| legacy (no filters, no cap) | 172t / 31,506 | 277t / 182,131 | 12t / -4,586 | 13t / -20,024 | 48t / 22,290 |
| LOO: production minus squeeze | 92t / 15,504 | 131t / 47,249 | 8t / 17,510 | 9t / -10,943 | 23t / 3,347 |
| LOO: production minus extension | 70t / 41,188 | 99t / 27,576 | 7t / 16,231 | 4t / -10,883 | 22t / 236 |
| LOO: production minus cpr | 75t / 42,623 | 120t / 68,300 | 6t / -6,829 | 7t / -10,564 | 20t / 16,151 |
| LOO: production minus aggression | 88t / 17,974 | 135t / 87,068 | 6t / -5,073 | 4t / -9,254 | 26t / 31,013 |
| SOLO: squeeze only, no cap | 121t / 32,757 | 203t / 151,799 | 11t / -5,865 | 8t / -14,094 | 37t / 29,390 |
| SOLO: extension only, no cap | 168t / 23,452 | 269t / 182,126 | 11t / -620 | 13t / -20,024 | 40t / 33,083 |
| SOLO: cpr only, no cap | 160t / 24,891 | 231t / 125,768 | 12t / -4,586 | 11t / -17,887 | 48t / 22,290 |
| SOLO: aggression only, no cap | 137t / 58,670 | 190t / 88,716 | 7t / -5,551 | 11t / -13,080 | 36t / 18,967 |
| CAP: all filters, cap unlimited | 79t / 36,278 | 101t / 31,013 | 7t / 16,231 | 4t / -10,883 | 22t / 19,385 |
| CAP: all filters, cap 4 | 73t / 34,672 | 98t / 21,172 | 7t / 16,231 | 4t / -10,883 | 20t / 16,151 |
| CAP: all filters, cap 5 | 76t / 37,406 | 101t / 31,013 | 7t / 16,231 | 4t / -10,883 | 22t / 19,385 |
| CAP: all filters, cap 6 | 78t / 42,494 | 101t / 31,013 | 7t / 16,231 | 4t / -10,883 | 22t / 19,385 |
| CAP: all filters, cap 8 | 79t / 36,278 | 101t / 31,013 | 7t / 16,231 | 4t / -10,883 | 22t / 19,385 |
