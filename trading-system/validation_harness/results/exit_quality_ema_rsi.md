# Exit-quality & trend-capture audit — `ema_rsi`

Window: 2026-02-01 09:15:00 → 2026-07-31 15:25:00  
Trading days: 123  
Legs: 528   Positions: 397

## 0. Reconstruction fidelity

Every number below is computed from a re-priced premium path. That path is only trustworthy if it reproduces the premiums the harness itself recorded, so that is checked first, on every leg:

- legs checked: **528**
- unreconstructable: **0**
- worst entry-premium error: **Rs 0.000000**

## 1. Exit reason distribution

### Legs (every close, including the 50% partial)

| Exit reason | n | % | net P&L | mean P&L | win rate |
|---|---|---|---|---|---|
| `END_OF_DATA` | 1 | 0.2% | 1,343 | 1,343 | 100.0% |
| `Partial Profit Booking (1:1.0)` | 131 | 24.8% | 295,943 | 2,259 | 100.0% |
| `Stop-Loss Hit` | 137 | 25.9% | -508,318 | -3,710 | 6.6% |
| `Time-based EOD Exit` | 41 | 7.8% | 48,862 | 1,192 | 61.0% |
| `Trailing Stop-Loss Hit` | 2 | 0.4% | 731 | 365 | 100.0% |
| `Trailing Stop-Loss Hit (Offset)` | 216 | 40.9% | 363,480 | 1,683 | 100.0% |
| **TOTAL** | 528 | 100% | 202,040 | 383 | 72.7% |

### Positions (what finally closed the position)

| Final exit | n | % | net P&L | mean P&L | win rate | median hold (min) |
|---|---|---|---|---|---|---|
| `end_of_data` | 1 | 0.3% | 3,087 | 3,087 | 100.0% | 30 |
| `eod` | 41 | 10.3% | 73,205 | 1,785 | 61.0% | 20 |
| `stop` | 137 | 34.5% | -455,186 | -3,323 | 12.4% | 20 |
| `trail_atr` | 2 | 0.5% | 731 | 365 | 100.0% | 65 |
| `trail_offset` | 216 | 54.4% | 580,204 | 2,686 | 100.0% | 25 |
| **TOTAL** | 397 | 100% | 202,040 | 509 | 65.7% | 25 |

## 2. MFE and capture (position level)

`mfe_pct` = best premium reached while the position was open, % of entry. `capture_pct` = quantity-weighted realised % / mfe_pct.

### MFE % by final exit

| final_exit_reason_class | n | mean | p25 | median | p75 | p90 |
|---|---|---|---|---|---|---|
| end_of_data | 1 | 14.69 | 14.69 | 14.69 | 14.69 | 14.69 |
| eod | 41 | 13.08 | 0.11 | 5.04 | 16.84 | 37.28 |
| stop | 137 | 7.28 | 0.00 | 0.00 | 4.19 | 16.52 |
| trail_atr | 2 | 6.63 | 6.55 | 6.63 | 6.72 | 6.77 |
| trail_offset | 216 | 18.94 | 5.86 | 10.84 | 20.89 | 43.48 |
| **ALL** | 397 | 14.24 | 1.26 | 6.51 | 15.34 | 36.74 |

### Capture % of the in-trade move, by final exit

| final_exit_reason_class | n | mean | p25 | median | p75 | p90 |
|---|---|---|---|---|---|---|
| end_of_data | 1 | 88.5 | 88.5 | 88.5 | 88.5 | 88.5 |
| eod | 31 | -167.4 | 43.6 | 83.2 | 100.0 | 100.0 |
| stop | 62 | -1,041.9 | -931.0 | -319.1 | 15.2 | 51.5 |
| trail_atr | 2 | 36.2 | 35.7 | 36.2 | 36.8 | 37.1 |
| trail_offset | 216 | 65.4 | 55.8 | 68.1 | 80.1 | 86.1 |
| **ALL** | 312 | -177.9 | 37.0 | 63.1 | 78.5 | 87.6 |

### Give-back (MFE % − realised %) by final exit

| final_exit_reason_class | n | mean | p25 | median | p75 | p90 |
|---|---|---|---|---|---|---|
| end_of_data | 1 | 1.69 | 1.69 | 1.69 | 1.69 | 1.69 |
| eod | 41 | 4.86 | 0.72 | 3.92 | 5.98 | 10.43 |
| stop | 137 | 23.86 | 15.37 | 18.08 | 28.07 | 37.83 |
| trail_atr | 2 | 4.23 | 4.21 | 4.23 | 4.25 | 4.26 |
| trail_offset | 216 | 5.98 | 1.88 | 3.21 | 6.19 | 13.29 |
| **ALL** | 397 | 12.02 | 2.27 | 6.08 | 16.82 | 28.97 |

Positions that were ever in profit: **312/397** (78.6%)  
…of which ended NEGATIVE: **51** (16.3%)

## 3. Trend / rally capture

`day_best_pct` = best premium available from entry to the END OF THE ENTRY DAY, whether or not we still held it — the whole intraday move the strategy could have had without carrying overnight. `trend_capture_pct` = realised % / day_best_pct.

### Full available move (day_best_pct) by final exit

| final_exit_reason_class | n | mean | p25 | median | p75 | p90 |
|---|---|---|---|---|---|---|
| end_of_data | 1 | 14.69 | 14.69 | 14.69 | 14.69 | 14.69 |
| eod | 41 | 14.35 | 0.11 | 7.27 | 17.62 | 42.46 |
| stop | 137 | 52.99 | 0.60 | 11.94 | 64.78 | 135.74 |
| trail_atr | 2 | 6.63 | 6.55 | 6.63 | 6.72 | 6.77 |
| trail_offset | 216 | 54.54 | 14.31 | 28.66 | 60.90 | 123.06 |
| **ALL** | 397 | 49.51 | 7.70 | 21.13 | 54.62 | 118.85 |

### Trend capture % by final exit

| final_exit_reason_class | n | mean | p25 | median | p75 | p90 |
|---|---|---|---|---|---|---|
| end_of_data | 1 | 88.5 | 88.5 | 88.5 | 88.5 | 88.5 |
| eod | 31 | -176.0 | 37.5 | 66.0 | 84.7 | 95.5 |
| stop | 105 | -314.0 | -221.1 | -46.6 | -14.7 | 16.9 |
| trail_atr | 2 | 36.2 | 35.7 | 36.2 | 36.8 | 37.1 |
| trail_offset | 216 | 34.1 | 14.6 | 26.6 | 53.6 | 68.4 |
| **ALL** | 355 | -87.1 | -10.9 | 17.7 | 48.8 | 70.3 |

**Rallies with ≥10% of premium available on the day** — n=279, median available 35.3%, median captured 6.3%, median trend capture **17.5%**  
**Rallies with ≥20% of premium available on the day** — n=204, median available 52.4%, median captured 7.3%, median trend capture **15.5%**  
**Rallies with ≥30% of premium available on the day** — n=161, median available 71.6%, median captured 9.0%, median trend capture **14.3%**  

## 4. Post-exit continuation

Best premium in the N minutes AFTER the position was fully closed, as % of the exit premium. Same trading day only.

| Final exit | n | +5m | +15m | +30m | +60m | median mins to post-exit peak |
|---|---|---|---|---|---|---|
| `end_of_data` | 1 | — | — | — | — | — |
| `eod` | 41 | 0.67 | 1.19 | 1.19 | 1.19 | 5 |
| `stop` | 137 | 1.54 | 5.16 | 10.66 | 19.93 | 50 |
| `trail_atr` | 2 | 0.92 | 2.61 | 3.05 | 3.05 | 45 |
| `trail_offset` | 216 | -0.22 | 3.58 | 6.04 | 9.04 | 65 |
| **ALL** | 397 | 0.42 | 3.56 | 5.79 | 8.85 | 45 |

### Premature exits

Mechanical definition: the premium exceeded the exit price by more than one tick within 60 minutes of the exit — the position was closed into a move that was still running.

| Final exit | n | premature | median missed upside % | p90 missed upside % |
|---|---|---|---|---|
| `end_of_data` | 0 | nan% | — | — |
| `eod` | 41 | 68.3% | 1.19 | 4.66 |
| `stop` | 137 | 88.3% | 19.93 | 143.50 |
| `trail_atr` | 2 | 100.0% | 3.05 | 3.64 |
| `trail_offset` | 216 | 84.7% | 9.04 | 39.50 |
| **ALL** | 396 | 84.3% | 8.85 | 69.47 |

## 5. Trailing-stop behaviour

Engine config in the harness: `trailing_activation_pct=1.0`, `trailing_offset_pct=0.35`, `atr_multiplier=1.5`, `partial_target_reward=1.0`, `partial_booking_pct=50`.

Two independent trailing mechanisms run side by side and whichever fires first wins: an ATR trailing stop (`highest − 1.5×ATR`) and a percentage trailing stop that exits when profit gives back `0.35` PERCENTAGE POINTS from its peak. Their exit reasons are kept distinct here.

| Mechanism | legs | % of all legs | net P&L | median MFE % | median capture % | median give-back % |
|---|---|---|---|---|---|---|
| `trail_atr` | 2 | 0.4% | 731 | 6.63 | 36.2 | 4.23 |
| `trail_offset` | 216 | 40.9% | 363,480 | 10.84 | 68.1 | 3.00 |

Legs whose profit ever reached the 1.0% activation threshold: **431/528** (81.6%)  
Median bars from entry to arming: **1** (one bar = 5 min)  
Median bars held AFTER arming before the exit: **2**

### Where the percentage trailing stop fires

Peak profit % reached before the offset stop closed the leg:

| n | p10 | p25 | median | p75 | p90 | max |
|---|---|---|---|---|---|---|
| 216 | 3.69 | 5.86 | 10.84 | 20.89 | 43.48 | 161.36 |

Offset-stop legs whose peak profit never exceeded **2%**: **1/216** (0.5%)  
Offset-stop legs that were premature: **84.7%**, median missed upside **9.04%**

## 6. Partial profit booking and the 'runner'

Partial booking closes 50% at 1:1 reward:risk and moves the stop to breakeven. The remaining half is the position's runner — the piece that is supposed to capture the trend.

Positions that reached partial booking: **131/397** (33.0%)

Time the runner survived after the partial booking:  
median **10 min** (2 bars), p75 15 min, p90 20 min  
Runners closed within ONE 5-minute bar of the partial booking: **24/131** (18.3%)

| What closed the runner | n | % |
|---|---|---|
| `end_of_data` | 1 | 0.8% |
| `eod` | 11 | 8.4% |
| `stop` | 20 | 15.3% |
| `trail_offset` | 99 | 75.6% |

## 7. Target and stop-loss behaviour

`Profit Target Hit` exits: **0**. Option entries are opened with `target=0.0` ("no fixed profit target — unlimited upside, managed by the trailing stop"), so this mechanism is inert by design; the number above confirms it never fires.

### Initial stop-loss band mix

| Band | positions | net P&L | win rate | median MFE % | median realised % |
|---|---|---|---|---|---|
| ₹100-150 | 53 | 44,475 | 67.9% | 7.86 | 4.12 |
| ₹150-250 | 238 | 101,258 | 69.7% | 5.51 | 2.91 |
| ₹20-50 | 33 | 33,773 | 57.6% | 23.18 | 6.50 |
| ₹50-100 | 73 | 22,535 | 54.8% | 7.96 | 1.54 |

`Stop-Loss Hit` positions: **137**, of which **2** (1.5%) closed within ±1% of entry — i.e. they are breakeven-stop exits on a position that had already partially booked, not initial-stop losses.  
Median MFE before the stop: **0.00%**  
Premature (recovered above the exit within 60 min): **88.3%**

## 8. Unit-space check: what is `trailing_offset_pct` actually worth?

`trailing_offset_pct` came from `backtesting_engine/run.py`, which applies it to the P&L % of the UNDERLYING instrument (its own comment: "Give 0.35% room so we don't exit too early on volatility"). `SmartExitEngine` applies the same number to the P&L % of an OPTION PREMIUM. Those are different units. This section measures the conversion factor from the data itself.

Premium elasticity (|premium % move| / |underlying % move|), measured over 2,161 held 5-minute bars:  
median **70.8x**, p25 64.7x, p75 79.4x

So a give-back of **0.35 percentage points of premium** is a give-back of **0.0049% of the underlying** — about **1.2 NIFTY points** at this window's median index level of 24,040.  
The rule was designed to allow 0.35% of the underlying, i.e. ~84 points. As ported, it allows about **71x less room than its own stated design intent**.

Against the noise floor of a single bar:

| |premium move| in one 5-min bar | p10 | p25 | median | p75 | p90 |
|---|---|---|---|---|---|
| percentage points | 0.46 | 1.28 | 2.76 | 5.52 | 10.11 |

**92.4%** of individual 5-minute bars move the premium by more than the entire 0.35pp allowance on their own. The threshold sits below the noise floor of one bar, so it does not act as a trailing stop at all — it acts as "exit on the first close below the peak".

Measured directly: **70.1%** of offset-stop exits fired on the FIRST 5-minute close below the running peak. The give-back actually realised at those exits has a median of **3.00pp** — 9x the nominal threshold, because a 5-minute bar cannot resolve 0.35pp. Live polling is ~1s, so live fires even closer to the peak: the harness UNDERSTATES this effect.
