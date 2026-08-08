# Entry-quality audit — `ema_rsi`

Window: 2026-02-01 09:15:00 → 2026-07-31 15:25:00 (123 trading days)  
Positions: 397

## 0. Signal reconstruction fidelity

Every conclusion below reads indicator state off a reconstructed signal frame, so the reconstruction is checked against the actual trades first: each entry must land on a bar this module independently reconstructs as a signal of the same direction.

- positions checked: **397**
- entry bar carries the matching signal: **397**
- entry bar missing from the frame: **0**
- signal direction mismatch: **0**

## 1. Is the entry right? (first touch of ±1R)

For each position, walk the premium path forward and record which comes first: **+1R** (premium reaches entry + its own initial stop distance) or **−1R**. R is the real `resolve_initial_stop` distance — the amount the live system actually risks on that trade.

This is exit-independent on purpose. It asks only whether the market went the signalled way before it went against it, by the size we were risking. **`false entry` = loss-first**: a full risk unit against the signal before a single one in its favour.

| Outcome | n | share |
|---|---|---|
| win-first | 203 | 51.1% |
| **loss-first (false entry)** | 150 | **37.8%** |
| neither within the day | 44 | 11.1% |

Of the 353 positions that resolved one way or the other, the signal was right first **57.5%** of the time — an edge of **+15.0pp** over a coin flip on its own risk unit.

Median bars to first touch: win-first **5**, loss-first **6** (one bar = 5 min)

### Post-entry excursion, in units of the position's own risk

| Metric | p10 | p25 | median | p75 | p90 |
|---|---|---|---|---|---|
| MFE (R) | -0.01 | 0.56 | 1.58 | 3.86 | 7.71 |
| MAE (R) | -4.26 | -2.40 | -1.13 | -0.38 | 0.07 |

Positions whose premium **never rose at all** after entry: **10.6%** — the purest false-signal count, independent of any threshold choice.

## 2. Confirmation quality — which component carries the signal?

All three conditions must hold for a signal to fire, so none of them can be tested by presence/absence. What CAN be tested is degree: for each component, does a stronger reading produce a better entry? A component whose buckets show no monotone edge is contributing confirmation in name only.

### RSI margin past its threshold

| RSI margin | n | win-first | loss-first | neither | edge (w−l) | net P&L | mean R:R proxy |
|---|---|---|---|---|---|---|---|
| 0-2 (at threshold) | 47 | 57.4% | 25.5% | 17.0% | **+31.9pp** | 36,067 | 3.11 |
| 2-5 | 74 | 54.1% | 36.5% | 9.5% | **+17.6pp** | 53,767 | 2.41 |
| 5-10 | 115 | 45.2% | 41.7% | 13.0% | **+3.5pp** | 739 | 3.27 |
| 10-15 | 74 | 56.8% | 31.1% | 12.2% | **+25.7pp** | 86,297 | 3.19 |
| 15+ | 87 | 48.3% | 46.0% | 5.7% | **+2.3pp** | 25,170 | 3.70 |
| **ALL** | 397 | 51.1% | 37.8% | 11.1% | **+13.4pp** | 202,040 | 3.17 |

### EMA separation (fast vs slow), signed toward the trade

| EMA gap | n | win-first | loss-first | neither | edge (w−l) | net P&L | mean R:R proxy |
|---|---|---|---|---|---|---|---|
| <0.05% (flat) | 111 | 52.3% | 34.2% | 13.5% | **+18.0pp** | 116,424 | 2.79 |
| 0.05-0.1% | 71 | 57.7% | 22.5% | 19.7% | **+35.2pp** | 64,761 | 2.29 |
| 0.1-0.2% | 114 | 45.6% | 43.9% | 10.5% | **+1.8pp** | -178 | 2.99 |
| 0.2-0.4% | 77 | 51.9% | 44.2% | 3.9% | **+7.8pp** | 7,050 | 4.64 |
| 0.4%+ | 24 | 50.0% | 50.0% | 0.0% | **+0.0pp** | 13,983 | 3.64 |
| **ALL** | 397 | 51.1% | 37.8% | 11.1% | **+13.4pp** | 202,040 | 3.17 |

### Supertrend leg age at entry

| Supertrend age | n | win-first | loss-first | neither | edge (w−l) | net P&L | mean R:R proxy |
|---|---|---|---|---|---|---|---|
| 0-1 (fresh flip) | 63 | 42.9% | 34.9% | 22.2% | **+7.9pp** | 18,504 | 3.41 |
| 2-3 | 9 | 66.7% | 33.3% | 0.0% | **+33.3pp** | 14,556 | 5.07 |
| 4-6 | 13 | 61.5% | 30.8% | 7.7% | **+30.8pp** | 14,218 | 3.31 |
| 7-12 | 28 | 46.4% | 32.1% | 21.4% | **+14.3pp** | 33,507 | 2.42 |
| 13+ (stale) | 284 | 52.5% | 39.4% | 8.1% | **+13.0pp** | 121,256 | 3.12 |
| **ALL** | 397 | 51.1% | 37.8% | 11.1% | **+13.4pp** | 202,040 | 3.17 |

### Price stretch beyond the fast EMA at entry (entry timing)

| Stretch | n | win-first | loss-first | neither | edge (w−l) | net P&L | mean R:R proxy |
|---|---|---|---|---|---|---|---|
| 0-0.05% | 44 | 59.1% | 27.3% | 13.6% | **+31.8pp** | 36,765 | 2.84 |
| 0.05-0.1% | 93 | 52.7% | 34.4% | 12.9% | **+18.3pp** | 68,386 | 2.33 |
| 0.1-0.2% | 133 | 42.9% | 44.4% | 12.8% | **-1.5pp** | 28,898 | 2.95 |
| 0.2%+ | 127 | 55.9% | 37.0% | 7.1% | **+18.9pp** | 67,990 | 4.13 |
| **ALL** | 397 | 51.1% | 37.8% | 11.1% | **+13.4pp** | 202,040 | 3.17 |

### Volume vs its 20-bar average

| Volume ratio | n | win-first | loss-first | neither | edge (w−l) | net P&L | mean R:R proxy |
|---|---|---|---|---|---|---|---|
| 1.0-1.5x | 319 | 53.0% | 38.2% | 8.8% | **+14.7pp** | 153,092 | 3.22 |
| 1.5-2.5x | 50 | 40.0% | 36.0% | 24.0% | **+4.0pp** | 43,527 | 3.41 |
| 2.5x+ | 28 | 50.0% | 35.7% | 14.3% | **+14.3pp** | 5,422 | 2.21 |
| **ALL** | 397 | 51.1% | 37.8% | 11.1% | **+13.4pp** | 202,040 | 3.17 |

## 3. Entry timing

### Time of day

| Session | n | win-first | loss-first | neither | edge (w−l) | net P&L | mean R:R proxy |
|---|---|---|---|---|---|---|---|
| open–09:30 | 51 | 51.0% | 49.0% | 0.0% | **+2.0pp** | -16,154 | 4.40 |
| 09:30–10:30 | 18 | 61.1% | 38.9% | 0.0% | **+22.2pp** | 15,190 | 4.22 |
| 10:30–12:00 | 88 | 55.7% | 42.0% | 2.3% | **+13.6pp** | 26,740 | 4.03 |
| 12:00–13:30 | 113 | 53.1% | 39.8% | 7.1% | **+13.3pp** | 52,519 | 2.92 |
| 13:30–close | 127 | 44.9% | 28.3% | 26.8% | **+16.5pp** | 123,745 | 2.15 |
| **ALL** | 397 | 51.1% | 37.8% | 11.1% | **+13.4pp** | 202,040 | 3.17 |

### How long the EMA regime had already been running

| EMA regime age | n | win-first | loss-first | neither | edge (w−l) | net P&L | mean R:R proxy |
|---|---|---|---|---|---|---|---|
| 0-3 bars | 77 | 51.9% | 36.4% | 11.7% | **+15.6pp** | 60,601 | 2.72 |
| 4-8 | 24 | 70.8% | 16.7% | 12.5% | **+54.2pp** | 45,444 | 2.72 |
| 9-20 | 39 | 48.7% | 30.8% | 20.5% | **+17.9pp** | 28,068 | 3.95 |
| 21-50 | 106 | 51.9% | 44.3% | 3.8% | **+7.5pp** | 35,605 | 3.19 |
| 51+ | 151 | 47.7% | 39.1% | 13.2% | **+8.6pp** | 32,323 | 3.25 |
| **ALL** | 397 | 51.1% | 37.8% | 11.1% | **+13.4pp** | 202,040 | 3.17 |

## 4. Regime

| Regime | n | win-first | loss-first | neither | edge (w−l) | net P&L | mean R:R proxy |
|---|---|---|---|---|---|---|---|
| gap_day | 35 | 54.3% | 37.1% | 8.6% | **+17.1pp** | 24,642 | 3.36 |
| high_volatility | 10 | 50.0% | 50.0% | 0.0% | **+0.0pp** | -4,616 | 3.46 |
| low_volatility | 11 | 18.2% | 63.6% | 18.2% | **-45.5pp** | -20,024 | 1.38 |
| sideways | 209 | 51.2% | 35.9% | 12.9% | **+15.3pp** | 178,556 | 3.15 |
| trending | 132 | 53.0% | 37.9% | 9.1% | **+15.2pp** | 23,482 | 3.28 |
| **ALL** | 397 | 51.1% | 37.8% | 11.1% | **+13.4pp** | 202,040 | 3.17 |

### Direction — and why the apparent asymmetry is NOT actionable

| Direction | n | win-first | loss-first | neither | edge (w−l) | net P&L | mean R:R proxy |
|---|---|---|---|---|---|---|---|
| CE | 203 | 46.3% | 41.9% | 11.8% | **+4.4pp** | -1,926 | 2.31 |
| PE | 194 | 56.2% | 33.5% | 10.3% | **+22.7pp** | 203,966 | 4.07 |
| **ALL** | 397 | 51.1% | 37.8% | 11.1% | **+13.4pp** | 202,040 | 3.17 |

Taken alone this looks like a large, exploitable skew. It is not. Controlling for the direction the index actually moved that day collapses it: the strategy is right when it is aligned with the day and wrong when it is not, symmetrically for CE and PE. The headline skew is a composition effect — the window drifted down (-3.62%), so far more PE positions were opened on days that went the PE way.

| Day | Direction | n | win-first | edge | net P&L |
|---|---|---|---|---|---|
| up day | CE | 134 | 52.2% | **+17.2pp** | 38,324 |
| up day | PE | 29 | 31.0% | **-27.6pp** | -46,153 |
| flat day | CE | 40 | 37.5% | **-10.0pp** | -9,289 |
| flat day | PE | 20 | 30.0% | **-15.0pp** | 3,632 |
| down day | CE | 29 | 31.0% | **-34.5pp** | -30,960 |
| down day | PE | 145 | 64.8% | **+37.9pp** | 246,487 |

**Conclusion: no direction-based change is justified.** Acting on the headline split would be fitting the window's drift.

## 5. Weak vs strong setups

A composite built ONLY from the strategy's own three conditions — no new indicator — scoring one point each for an RSI margin above 5, an EMA gap above 0.1%, and a Supertrend leg no older than 6 bars.

| Confirmation score (0-3) | n | win-first | loss-first | neither | edge (w−l) | net P&L | mean R:R proxy |
|---|---|---|---|---|---|---|---|
| 0 | 53 | 64.2% | 20.8% | 15.1% | **+43.4pp** | 88,847 | 2.06 |
| 1 | 131 | 51.9% | 36.6% | 11.5% | **+15.3pp** | 43,512 | 2.74 |
| 2 | 194 | 46.4% | 43.8% | 9.8% | **+2.6pp** | 72,219 | 3.65 |
| 3 | 19 | 57.9% | 31.6% | 10.5% | **+26.3pp** | -2,537 | 4.38 |
| **ALL** | 397 | 51.1% | 37.8% | 11.1% | **+13.4pp** | 202,040 | 3.17 |

## 6. Missed trend / rally opportunities

Sustained moves in the UNDERLYING (≥0.30% completed within 90 minutes, de-overlapped largest-first), and whether a position in the matching direction was OPEN at any point during each one.

Runs found: **381** over 123 days (3.1/day), median size **0.43%**

| Direction | runs | covered | median size | median held % of run |
|---|---|---|---|---|
| CE | 182 | 39.0% | 0.43% | 0.0% |
| PE | 199 | 42.7% | 0.44% | 0.0% |
| **ALL** | 381 | **40.9%** | 0.43% | 0.0% |

Among the runs that WERE covered, median time held is **32.3%** of the run (the all-runs median is 0% only because most runs are uncovered — quoting that would double-count the same miss).

Large runs (≥0.60% of index, n=94): covered **52.1%**; among those, median held **29.4%** of the run.

### Why the uncovered runs were missed

Categories are exclusive and are evaluated in this order: was any position open during the run; else did a signal fire; else did the raw level condition hold (i.e. would a level-triggered strategy have entered); else there was simply no setup.

| Reason | runs | share | median size | total index movement |
|---|---|---|---|---|
| holding an opposite-direction position | 63 | 28.0% | 0.43% | 30.7% |
| no setup at all | 139 | 61.8% | 0.41% | 64.7% |
| setup present, edge-trigger suppressed it | 4 | 1.8% | 0.44% | 2.1% |
| signal fired but no entry (risk gate / EOD cutoff) | 19 | 8.4% | 0.54% | 14.6% |

**The anti-churn edge-trigger accounts for 4 of 225 misses (1.8%).** It is not the reason rallies are being missed, and the measurement gives no reason to weaken it.

## 7. The entry path that was validated is not the one production runs

`config/settings.json` has all four institutional filters ENABLED. `registry.run_strategy` applies them to every strategy's signals. The validation harness calls it with `settings={}`, so all four are OFF in every number the validation report contains — including this audit's sections 1-6.

| Path | signal bars | vs harness |
|---|---|---|
| harness (`settings={}`, filters OFF) | 725 | — |
| production (`config/settings.json`, filters ON) | 212 | **-70.8%** |

Signals surviving the production filters: **212/725** (**29.2%**) — the production strategy takes roughly **71% fewer entries** than the one that was measured and given its KEEP verdict.

Also unmodelled: `config/settings.json` sets `max_daily_trades: 3`, which `main.py` writes into `risk_manager.config.max_trades_per_day` on the live entry path. The harness constructs `RiskManager` without a config, leaving the cap at its default of 0 (unlimited), and averages **3.2 positions/day**.

### Were the filtered-out entries the bad ones?

| Cohort | n | win-first | loss-first | edge | net P&L | mean P&L |
|---|---|---|---|---|---|---|
| kept by production filters | 120 | 50.8% | 34.2% | **+16.7pp** | 74,879 | 624 |
| removed by production filters | 277 | 51.3% | 39.4% | **+11.9pp** | 127,161 | 459 |
