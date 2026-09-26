# Phase 10 — Complete Trade Validation

**Status:** research only. Production plane untouched. `active_strategy`
remains `ema9_rsi_momentum`. No live config key. No paper-trading code.

**Decision: NO-GO — OPTIONS IMPLEMENTATION**

The entry signal is causally clean, structurally robust and reproducible. It
does **not** survive conversion into an options-buying trade once repeated
observations of the same setup are deduplicated and realistic causal exits
replace the excursion-asymmetry proxy.

The final holdout (FINNIFTY) was **deliberately not opened** — nothing passed
validation, so there was nothing to confirm, and it is the last untouched data
in the repository.

---

## 1. Executive summary

Phase 9 reported the entry at **+0.501 / +0.382** against baseline on two
fresh instruments with p ≤ 0.0003, and an options net of **+2.6 points** at a
2-hour hold. Phase 10 reproduces every one of those numbers exactly, and then
finds two measurement problems that together account for the entire result.

**Problem 1 — the sample was not independent.** The Phase 9 rule is a *state*
("price is near the level"), so price leaves the band and returns repeatedly
at the same level on the same day. Grouping by `(day, direction)` shows
**3.2 episodes per setup**. Phase 9's n = 1,236 is really ~390 setups.
Deduplicated, significance collapses:

| Window | Phase 9 (every episode) | Deduplicated (one entry per setup) |
|---|---|---|
| NIFTY DEV | +0.250, p < 0.0001 | +0.125, p = 0.099 |
| NIFTY VAL | +0.143, p = 0.0022 | +0.155, p = 0.043 |
| SENSEX FRESH | +0.501, p = 0.0003 | +0.246, p = 0.309 |
| BANKNIFTY FRESH | +0.382, p < 0.0001 | +0.476, p = 0.063 |

Still positive in all four windows — but no policy reaches p < 0.05 on both
NIFTY splits, and nothing survives multiple-testing correction.

**Problem 2 — MFE−MAE is not a realizable return.** Phase 9's +2.6-point net
came from excursion asymmetry, which requires exiting at the exact favourable
extreme. With causal exit rules the realized return is **+2.3 points**, not
+10.9 — a **4.7× overstatement**. Against measured friction of 3.4–6.0 points
at the matching hold times, **NIFTY is net negative in 11 of 12 exit ×
split cells.**

**What is genuinely established:** a small, causally clean, structurally
robust location effect at prior-day extremes, worth roughly **+2 underlying
points per trade** on NIFTY. That is below the cost of buying an option to
express it.

---

## 2. The frozen entry rule (§1)

For each 5-minute bar *i*, using only bars with index ≤ *i*:

```
PDH[i] = HIGH of the most recent COMPLETED prior session
PDL[i] = LOW  of the most recent COMPLETED prior session
ATR[i] = shared.indicators.atr(df, 14) at bar i
C[i]   = CLOSE of bar i

near_low [i] = isfinite(PDL[i]) and |C[i] - PDL[i]| <= 0.25 * ATR[i]
near_high[i] = isfinite(PDH[i]) and |C[i] - PDH[i]| <= 0.25 * ATR[i]

raw[i] = +1  if near_low and not near_high      -> buy CE
         -1  if near_high and not near_low      -> buy PE
          0  otherwise
```

Every ambiguity §1 lists, resolved:

| Question | Answer |
|---|---|
| "within 0.25 ATR" | **Absolute** distance from the bar's **close** to the level, both sides. A proximity band, not a touch or a cross. |
| Which ATR | `shared.indicators.atr(df, 14)` — `ewm(span=14, adjust=False)` of true range. **Not** the SMC engine's internal ATR. |
| ATR timestamp | Bars 0…*i*. Prefix-stability verified (§3). |
| Previous-day H/L | `levels.compute_daily_levels()`. Max high / min low of the previous **trading day present in the frame**. First day of any frame = NaN, can never signal. |
| Session boundary | Where the normalised date changes. No exchange calendar consulted. |
| Must price approach? | **No.** Pure location. Pierce-and-revert variants (P1 rejection, P5 reclaim) are different rules, tested separately in Phase 9. |
| "Traded toward reversion" | near **PDL → long (CE)**; near **PDH → short (PE)**. The bet is that price moves back into the prior range. |
| Both levels near | Explicit **no-trade**. Phase 9 silently preferred bear; measured here — **it changes 0 bars** in the whole sample. |
| Signal timestamp | Bar *i*'s **close**. |
| Executable timestamp | Bar ***i+1*'s open** — the base case for all Phase 10 economics. |
| CE/PE mapping | +1 → CE, −1 → PE. Premium is only ever bought. |

---

## 3. Reproduction and causality audit (§1, §2)

**Phase 9 reproduces exactly.**

| Window | Phase 10 | Phase 9 |
|---|---|---|
| NIFTY DEV | +0.250, p < 0.0001, n=598 | +0.250, p < 0.0001 |
| NIFTY VAL | +0.143, p = 0.0022, n=365 | +0.143, p = 0.0023 |
| SENSEX FRESH | +0.501, p = 0.0003, n=310 | +0.501, p = 0.0003 |
| BANKNIFTY FRESH | +0.382, p < 0.0001, n=152 | +0.382, p < 0.0001 |
| NIFTY 2026-04+ (contaminated) | +0.315, n=273 | +0.302, n=270 |

The contaminated window differs trivially (273 vs 270 entries) because Phase 9
computed levels on the sliced frame while Phase 10 computes on the full frame
and masks — the slice loses its first day's prior-day levels. Immaterial, and
in the contaminated window only.

**Causality audit — all PASS:**

| Check | Result |
|---|---|
| Future-truncation invariance (k = 3000/4000/5000/5900) | **0 mismatches** |
| ATR prefix-stable | **PASS** |
| PDH never equals today's high | **PASS** |
| Entry executable at bar *i+1* open | enforced in `exits.simulate(entry_delay=1)` |

---

## 4. Lifecycle and deduplication (§4, §6)

```
NO_SETUP -> NEAR_PRIOR_DAY_EXTREME -> DIRECTION_ESTABLISHED
         -> ENTRY_ELIGIBLE -> ENTRY -> POSITION_OPEN -> EXIT
```

Two pre-declared groupings, both measured:

* **EPISODE** — a maximal run of consecutive in-band bars, same day, same direction.
* **DAY_SIDE** — one setup per `(day, direction)`; the conservative reading.

| Window | bars | days | in-band bars | Phase 9 signals | episodes | **day-side** | eps/day-side |
|---|---|---|---|---|---|---|---|
| NIFTY DEV | 20,829 | 280 | 882 | 601 | 602 | **191** | 3.15 |
| NIFTY VAL | 13,888 | 186 | 554 | 370 | 370 | **122** | 3.03 |
| NIFTY HOLDOUT | 9,153 | 122 | 387 | 273 | 273 | **80** | 3.41 |
| SENSEX FRESH | 9,153 | 122 | 471 | 316 | 316 | **80** | 3.95 |
| BANKNIFTY FRESH | 4,779 | 64 | 232 | 153 | 153 | **42** | 3.64 |

`edge_trigger` already collapses contiguous runs (601 ≈ 602 episodes), but it
does **not** group repeat visits to the same level on the same day. Each setup
generates ~3.2 of them.

**Why this inflates significance.** The same-day permutation null draws
*independent* bars from each day; the strategy's repeats are *correlated*. The
null distribution is therefore narrower than the observed statistic's, making
the p-value anti-conservative. The test is valid in form; its power was
overstated. The deduplicated figures in §5 are the honest ones.

---

## 5. Selection policies (§5, §13)

All causal — each picks using only information available at the bar it picks.
Policy C is identical to A by construction and is reported as such.

**NIFTY DEV**

| Policy | n | days | Δ vs base | p |
|---|---|---|---|---|
| *(Phase 9: every episode)* | 598 | 171 | +0.250 | <0.0001 |
| A — first signal of the day | 171 | 171 | +0.125 | 0.099 |
| B — first per (day, direction) | 190 | 171 | +0.097 | 0.048 |
| D — first within 0.10 ATR | 130 | 125 | +0.203 | 0.081 |
| E — first bar closing toward reversion | 152 | 144 | +0.110 | 0.074 |

**NIFTY VAL**

| Policy | n | days | Δ vs base | p |
|---|---|---|---|---|
| *(Phase 9: every episode)* | 365 | 115 | +0.143 | 0.0022 |
| A | 115 | 115 | +0.155 | 0.043 |
| B | 122 | 115 | +0.021 | 0.091 |
| D | 90 | 87 | −0.021 | 0.328 |
| E | 98 | 95 | +0.074 | 0.149 |

**Fresh instruments, deduplicated**

| Policy | SENSEX Δ (p) | BANKNIFTY Δ (p) |
|---|---|---|
| A | +0.246 (0.309) | +0.476 (0.063) |
| B | +0.245 (0.176) | +0.509 (0.025) |
| D | +0.424 (0.040) | +0.926 (0.0003) |
| E | +0.510 (0.120) | +0.462 (0.043) |

**Frozen choice: Policy A.** Positive in all four windows, the simplest, the
most trivially causal, and it yields exactly one trade per day — which also
resolves the trade-cap interaction for free. It is **not** chosen for being the
largest; D is larger where it works and negative on VAL.

---

## 6. Exit families (§7–§10)

Entry at bar *i+1* open; exit at the open of the bar after the condition
fires; everything EOD-capped. No exit reads a future high, low or extremum.

**Realized underlying points per trade, Policy A:**

| Family | DEV n=171 | VAL n=115 | held (min) |
|---|---|---|---|
| A — fixed 30 min | −1.1 | +3.6 | 30 |
| A — fixed 60 min | +0.2 | +0.9 | 58 |
| A — fixed 120 min | +2.3 | +2.1 | 113 |
| A — fixed 240 min | +0.7 | +0.4 | 42 bars |
| B — return to prior-day midpoint | −1.4 | −1.6 | 170 |
| C — structural invalidation (0.5 ATR beyond level) | +2.0 | +2.0 | 76 |
| D — invalidation + 120 min cap | −0.7 | +0.4 | 40 |

Win rates 44–56%, medians frequently **negative** with positive means — a
heavy-tailed distribution whose expectancy sits within noise of zero. Family C
is the most consistent (+2.0 on both splits) and is the only family whose sign
agrees across splits at the same parameters.

**No exit family produces a mean realized return above ~+2.3 points.**

---

## 7. Options data audit (§14, §16)

| Field | Status |
|---|---|
| Option OHLC history | **UNAVAILABLE** — no CE/PE files in `data/` |
| Historical bid / ask | **UNAVAILABLE** — live-only |
| Historical IV | **UNAVAILABLE** |
| Historical OI | **UNAVAILABLE** |
| Greeks | **UNAVAILABLE** historically; `opt_delta` recorded per trade in `paper_obs_logs/` |
| Real entry/exit premiums | **PARTIAL** — 13 recorded sessions (2026-08-25 → 2026-09-25), `ema9_rsi_momentum` trades only, not this signal's timestamps |
| Strike / expiry / underlying mapping | **DERIVABLE** via `select_option()` |

`paper_obs_logs/` holds 152 report files covering **13 sessions with real
trades**, each carrying `entry_premium`, `exit_premium`, `opt_delta`,
`strike`, `entry_spot` and `duration_min` — genuine recorded quotes. But they
are another strategy's entries, and 13 sessions cannot validate anything.

**Consequence: the options layer is `UNVALIDATED` and cannot be validated
from this repository.** Any option P&L below is *modelled*, not backtested.
No IV or vega term exists, and none was invented.

---

## 8. Friction revalidation (§17) — independently recomputed

Constants re-entered from the repository's own 2026-09-21 calibration rather
than copied from Phase 9 code.

| Input | NIFTY | BANKNIFTY | SENSEX | FINNIFTY |
|---|---|---|---|---|
| Premium % of spot | 0.32 (DTE≤1) / 1.03 (DTE 8-14) **OBSERVED** | 1.38 **OBSERVED** | 0.76 **OBSERVED** (one snapshot) | **UNMEASURED** |
| Delta | 0.42 **OBSERVED** | 0.376 **OBSERVED** | 0.305 **OBSERVED** | **UNMEASURED** |
| Round-trip spread | 0.21% **OBSERVED** | 0.35% **OBSERVED** | 0.21% **ASSUMED** (copies NIFTY) | **UNMEASURED** |
| Theta %/session | 13.4 / 4.0 **OBSERVED** | 5.9 **OBSERVED** | **UNAVAILABLE** | **UNMEASURED** |
| IV / vega | **UNAVAILABLE — not modelled** | | | |

Phase 9's arithmetic checks out. **Its input did not.** Phase 9 fed friction
with MFE−MAE (+10.9 points at 2 hours) rather than a realized return. That is
the error this phase corrects.

---

## 9. Realized economics: net of friction (§10, §11, §18)

**Realized underlying points minus modelled option friction, per trade.**

### NIFTY — the only instrument with a complete measured friction model

| Exit family | DEV realized | DEV net (DTE≤1 / 8-14) | VAL realized | VAL net (DTE≤1 / 8-14) |
|---|---|---|---|---|
| fixed 30 min | −1.1 | **−3.4 / −4.2** | +3.6 | **+1.1 / +0.3** |
| fixed 60 min | +0.2 | −3.9 / −4.6 | +0.9 | −3.4 / −4.2 |
| fixed 120 min | +2.3 | −5.5 / −6.0 | +2.1 | −5.9 / −6.5 |
| return to level | −1.4 | −12.4 / −12.8 | −1.6 | −14.2 / −14.6 |
| invalidation | +2.0 | −3.4 / −4.0 | +2.0 | −3.6 / −4.3 |
| invalidation + time | −0.7 | −3.4 / −4.1 | +0.4 | −3.0 / −3.8 |

**11 of 12 cells are net negative.** The single positive cell (VAL, 30 min,
DTE≤1: +1.1) has the **opposite sign on DEV** (−3.4) for the identical rule.

### BANKNIFTY FRESH (n = 40, 64 days)

Realized returns are large (+11 to +63 points) but so is friction. Only
`fixed 120 min` is net positive (**+17.0**); every other family is −0.1 to
−21.8. A +63-point realized mean on 40 trades in one 64-day window, against
NIFTY's +2.3 on 171, is far more consistent with small-sample noise than with
a real BANKNIFTY-specific edge.

### SENSEX FRESH

Realized returns positive for three of six families (+7.7 to +57.8), but
**BSE chain theta has never been measured**, so net is `n/a` throughout. No
readiness claim is possible.

### FINNIFTY

No friction constants measured at all. Not assessable.

---

## 10. Robustness (§20, §22, §23)

**Band sensitivity — a smooth band, not a single number** (deduplicated,
Policy A, DEV+VAL):

| Band (ATR) | setups | n | Δ vs base | p | realized (120 min) |
|---|---|---|---|---|---|
| 0.10 | 490 | 212 | +0.142 | 0.097 | +3.9 |
| 0.15 | 679 | 251 | +0.148 | 0.038 | +3.6 |
| 0.20 | 848 | 272 | +0.153 | 0.012 | +4.1 |
| **0.25** | 972 | 286 | +0.135 | 0.022 | +2.3 |
| 0.30 | 1114 | 301 | +0.104 | 0.032 | +1.5 |
| 0.40 | 1277 | 317 | +0.089 | 0.063 | +0.8 |
| 0.50 | 1400 | 332 | −0.007 | 0.293 | −2.0 |
| 0.75 | 1550 | 352 | +0.003 | 0.383 | −1.2 |
| 1.00 | 1603 | 372 | −0.055 | 0.699 | −3.0 |

Smooth decay from 0.10 through 0.40, gone by 0.50. **Structural, not a tuned
cliff.** Both the excursion measure and the realized return agree on the shape.

**Execution delay** (deduplicated, DEV+VAL): +0.135 / +0.091 / +0.112 / +0.044
at +0/+1/+2/+3 bars. Graceful decay; survives a 5-minute delay.

**Adversarial** (deduplicated):

| Control | n | Δ vs base | p |
|---|---|---|---|
| As declared | 286 | +0.135 | 0.022 |
| Inverted direction | 286 | **−0.128** | 0.978 |
| Random time, same day + direction (1) | 280 | +0.002 | 0.323 |
| Random time, same day + direction (2) | 279 | −0.107 | 0.788 |

The sign inverts correctly and randomised timing destroys it. **The entry
mechanism is real.** It is the magnitude, not the existence, that fails.

---

## 11. The final holdout was NOT opened (§12)

FINNIFTY (2026-07-07 → 2026-08-31, 2,976 bars, 40 days) is the **only
partition in this repository never inspected in any phase.**

It was deliberately left closed. Nothing passed validation — every NIFTY
exit × split cell but one is net negative, and that one flips sign across
splits — so there is no candidate for the holdout to confirm. Spending the
last untouched data to confirm a failure would leave nothing for a future
phase. It remains sealed.

**After FINNIFTY there is no more untouched data in this repository.** Any
further iteration on this signal requires forward accumulation, or fetching
genuinely new history from the broker.

---

## 12. Answers to the required questions (§32)

1. **Exact causal entry rule?** §2 above. One condition, one parameter.
2. **How are repeated signals grouped?** EPISODE (contiguous in-band run) and
   DAY_SIDE (one per day+direction). 3.2 episodes per setup.
3. **Selection policy?** Policy A — first signal of the day, either direction.
4. **Why causally justified?** It uses only the bar's own close and the
   completed prior session; no comparison across future signals is required.
5. **Exit rule?** No family qualified. C (structural invalidation, 0.5 ATR
   beyond the level) is the most consistent at +2.0 on both splits.
6. **Why causally justified?** It fires when price closes beyond the level the
   trade was predicated on reverting from — the premise is dead, observable at
   that bar's close.
7. **Survives execution delay?** **Yes** — +0.091 at +1 bar, +0.112 at +2.
8. **Survives fresh holdout?** Phase 9's two fresh instruments stay positive
   deduplicated (+0.246, +0.476) but only BANKNIFTY approaches significance.
   The final holdout was not opened (§11).
9. **Survives across instruments?** Directionally yes on all four; significance
   only on BANKNIFTY, the smallest sample.
10. **Does the option contract preserve the edge?** **No.** A ~+2-point
    underlying edge against 3.4–6.0 points of friction.
11. **After spread / slippage / theta / IV?** Net negative in 11 of 12 NIFTY
    cells. IV and vega are **not modelled** — they can only make it worse.
12. **Which instruments viable?** **None demonstrated.** BANKNIFTY at a
    120-minute hold is the only positive cell and rests on 40 trades.
13. **Which fail and why?** NIFTY — edge below friction. BANKNIFTY — rich
    premium (1.38% of spot) and low delta (0.376) triple the per-point cost.
    SENSEX — theta unmeasured. FINNIFTY — nothing measured.
14. **Does the strategy need RSI/SMC?** **No.** Every such component was
    measured redundant or harmful in Phases 8–9 and none was reintroduced.
15. **Is the simple prior-day-extreme architecture sufficient?** Sufficient as
    an *entry*; **not sufficient as an options trade**.
16. **Remaining uncertainties?** No historical option data; no IV/vega term;
    SENSEX and FINNIFTY friction unmeasured; BANKNIFTY's positive cell rests
    on 40 trades; the final holdout is unopened.

---

## 13. Decision (§33)

### **NO-GO — OPTIONS IMPLEMENTATION**

The entry is real: causally clean, prefix-stable, direction-inverting under
control, smooth across a parameter band, robust to execution delay, and
positive in every window tested. It is simply **too small to pay for an
option**.

This is not a measurement failure to be re-litigated. Two Phase 9 figures were
inflated — the sample by 3.2× through un-deduplicated repeats, the return by
4.7× through using excursion asymmetry instead of realized P&L — and once both
are corrected the remaining edge (~+2 underlying points) sits below the
cheapest friction available (3.4 points at a 30-minute NIFTY hold).

**Not `CONTINUE RESEARCH`**, because the specific hypothesis "this entry can
become an options-buying trade" has been tested and answered. **Not `NO-GO —
ENTRY ONLY`**, because the entry is not the thing that failed.

**Paper trading remains blocked. No orders. Nothing enabled.**

### If this line is picked up again

The blocker is arithmetic: the move must be larger, or the friction smaller.
Three directions the evidence actually supports —

1. **A larger timeframe.** The effect is a location effect; on 15- or 30-minute
   bars the same rule would target proportionally larger excursions against the
   same per-trade friction.
2. **A cheaper expression.** Futures or spreads rather than long premium.
   Outside the current options-buying mandate, but the friction table is the
   reason.
3. **Measure the missing constants first.** SENSEX theta and FINNIFTY's whole
   profile are unmeasured; BANKNIFTY's single positive cell deserves a real
   sample before it is believed or dismissed.

No `RSI_SMC_FINAL_ARCHITECTURE_SPEC.md` was written — §31 gates it on a
genuinely supported complete architecture, and there is not one.

---

## 14. Reproducibility

`docs/research/phase10/` — `entry.py` (the frozen rule), `setup.py`
(lifecycle + deduplication), `selection.py`, `exits.py`, `economics.py`,
`repro.py`, plus `p8lib.py` / `split.py` reused verbatim from Phase 8.

Research only. Nothing under `trading_bot/` imports any of it.

## 15. What was NOT done

- No production file modified; no live config key; `active_strategy`
  unchanged; no paper-trading code; no orders.
- **The FINNIFTY holdout was not opened.**
- No parameter was optimised. The band grid in §10 was pre-declared as a
  sensitivity analysis and the 0.25 default was left unchanged despite 0.20
  scoring higher.
- No IV, OI, Delta or Greek was fabricated. SENSEX and FINNIFTY friction cells
  are blank.
- No RSI/SMC component was reintroduced.
