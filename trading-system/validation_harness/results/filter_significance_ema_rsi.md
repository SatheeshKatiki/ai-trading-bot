# Are any entry-filter changes statistically defensible? — `ema_rsi`

Window: 2026-02-01 09:15:00 → 2026-07-31 15:25:00 (123 trading days)  
Bootstrap: 20,000 resamples, seed 20260809. Baseline is the production configuration (all four filters, cap 3).

Tests are run symmetrically over all four filters, so no result is selected after seeing which filter looks good.

## Test 1 — paired day-level bootstrap of total P&L

Day-isolated runs give each day a fresh RiskManager, so days are independent draws and pairing over them is valid.

| Filter disabled | days changed | better | worse | total Δ P&L | 95% CI | P(Δ>0) |
|---|---|---|---|---|---|---|
| squeeze | 63 | 37 | 26 | -9,255 | [-75,952, 54,642] | 38.9% |
| extension | 13 | 7 | 6 | -7,574 | [-42,862, 26,165] | 32.7% |
| cpr | 26 | 17 | 9 | 27,759 | [-45,624, 101,164] | 77.9% |
| aggression | 65 | 43 | 22 | 39,807 | [-62,208, 136,351] | 78.8% |

## Test 2 — do the blocked trades lose money?

The trades a filter blocks, isolated by (symbol, entry_time), with their mean P&L bootstrapped against zero.

| Filter | blocked | mean P&L | total | 95% CI of mean | P(mean>0) | win-first | loss-first |
|---|---|---|---|---|---|---|---|
| squeeze | 79 | -17 | -1,379 | [-781, 738] | 48.2% | 40.5% | 44.3% |
| extension | 13 | 360 | 4,676 | [-1,640, 2,505] | 63.0% | 53.8% | 46.2% |
| cpr | 32 | 1,142 | 36,535 | [-857, 3,290] | 86.0% | 50.0% | 31.2% |
| aggression | 85 | 261 | 22,179 | [-666, 1,139] | 71.8% | 56.5% | 40.0% |

## Test 3 — signal-population quality (best powered)

Every signal the unfiltered strategy emits, scored on the underlying. A filter that works should reject signals whose edge is worse than the ones it lets through, at every threshold.

Signal population: **725** bars.

### Threshold ±0.15% of index

| Filter | rejected | edge of rejected | allowed | edge of allowed | difference | 95% CI | P(rejected worse) |
|---|---|---|---|---|---|---|---|
| squeeze | 250 | -5.2pp | 475 | +11.2pp | **-16.4pp** | [-29.9, -3.1] | 99.2% |
| extension | 25 | +12.0pp | 700 | +5.3pp | **+6.7pp** | [-32.7, +46.6] | 37.1% |
| cpr | 125 | +8.0pp | 600 | +5.0pp | **+3.0pp** | [-13.7, +20.0] | 35.7% |
| aggression | 285 | +4.9pp | 440 | +5.9pp | **-1.0pp** | [-14.9, +12.6] | 56.1% |

### Threshold ±0.21% of index

| Filter | rejected | edge of rejected | allowed | edge of allowed | difference | 95% CI | P(rejected worse) |
|---|---|---|---|---|---|---|---|
| squeeze | 250 | -4.8pp | 475 | +13.7pp | **-18.5pp** | [-31.3, -6.0] | 99.8% |
| extension | 25 | +12.0pp | 700 | +7.1pp | **+4.9pp** | [-33.9, +44.1] | 40.3% |
| cpr | 125 | +8.8pp | 600 | +7.0pp | **+1.8pp** | [-13.5, +17.1] | 40.6% |
| aggression | 285 | +8.1pp | 440 | +6.8pp | **+1.3pp** | [-11.6, +13.6] | 42.6% |

### Threshold ±0.30% of index

| Filter | rejected | edge of rejected | allowed | edge of allowed | difference | 95% CI | P(rejected worse) |
|---|---|---|---|---|---|---|---|
| squeeze | 250 | -5.2pp | 475 | +7.6pp | **-12.8pp** | [-23.2, -2.8] | 99.3% |
| extension | 25 | +12.0pp | 700 | +2.9pp | **+9.1pp** | [-28.6, +47.6] | 31.3% |
| cpr | 125 | -4.0pp | 600 | +4.7pp | **-8.7pp** | [-22.2, +4.5] | 90.1% |
| aggression | 285 | -0.4pp | 440 | +5.5pp | **-5.8pp** | [-16.8, +5.1] | 85.6% |
