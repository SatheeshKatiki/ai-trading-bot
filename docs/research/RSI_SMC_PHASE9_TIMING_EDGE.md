# Phase 9 — Entry-Timing Architecture

**Status:** research only. Production plane untouched. `active_strategy`
remains `ema9_rsi_momentum`. No live configuration key added. No paper-trading
code. **The strategy is not enabled and must not be.**

**Decision: VALIDATION CANDIDATE** — scoped to the *entry signal* only, with
conditions listed in §14. Not production-ready. Not to be paper traded on the
strength of this document alone.

---

## 1. Executive summary

Phase 9 set out to recover the directional information Phase 8 found while
entering earlier. It did, but not where it was expected.

**The context block is a third over-filter.** Requiring HTF bias AND regime
AND no-trade-clear cut previous-day-low rejections from **955 events to 42**
over 588 days — a 96% cut — without reliably improving the effect (PDL
+0.211 → +0.378, but PDH +0.246 → **+0.199**). Every Phase 9 family that
stacked anything on top of the raw previous-day interaction collapsed out of
sample.

**What survived is radically simpler than anything previously tested.**
`P4_proximity_state` — price within 0.25 ATR of the previous day's high or
low, traded toward reversion — is positive in every window tested, beats the
same-day-same-direction permutation null in four of five, and survives a
fresh holdout on two instruments that were never inspected during selection.

| Window | n | Δ vs baseline | null *p* |
|---|---|---|---|
| NIFTY DEV (2024-01→2025-06) | 598 | +0.250 | <0.0001 |
| NIFTY VAL (2025-07→2026-03) | 365 | +0.143 | 0.0023 |
| **SENSEX FRESH (2026-04→2026-09)** | **310** | **+0.501** | **0.0003** |
| **BANKNIFTY FRESH (2026-06→2026-09)** | **152** | **+0.382** | **<0.0001** |
| NIFTY 2026-04+ *(contaminated)* | 270 | +0.302 | 0.087 |

**This is the first thing in the entire investigation to beat the same-day
null.** Phase 8 found nothing did — every architecture entered at
worse-than-random moments on the days it selected. A level-*location* signal
does not, because it is not triggered by movement.

**Phase 8's option-friction verdict was computed from the wrong constants.**
It used theta = 9.7 %/session, which is `backtesting_engine`'s MODEL value.
The repository's own calibration measured 13.4 %/session at DTE≤1 and 4.0 %
at DTE 8–14, with premium moving the other way. Recomputed with the measured
values, **NIFTY is net positive at 30–120 minute holds** (+1.0 to +2.6 points
after spread and theta). BANKNIFTY is strongly negative. SENSEX cannot be
assessed — BSE chain theta has never been measured.

---

## 2. Phase 8 reproduction (§2)

All nine checks reproduce **exactly**. No discrepancy to resolve.

| # | Check | Phase 8 | Phase 9 | ✓ |
|---|---|---|---|---|
| R1 | live-equivalent entry count | 51 | 51 | ✓ |
| R2 | baselines DEV/VAL/HOLDOUT | .920/1.088, .875/1.143, .965/1.037 | identical | ✓ |
| R3 | `E_setup_core` DEV/VAL/HOLDOUT | +.082 / +.144 / +.178 | identical | ✓ |
| R4 | filter removal on holdout | A −.132, E +.178 | identical | ✓ |
| R5 | bull funnel | .914 → 1.036 → .860 → .632 | identical | ✓ |
| R6 | corr(sweep, rr_ok) | 0.78 | 0.78 | ✓ |
| R7 | timing degradation (E, DEV) | −0.494 | −0.494 | ✓ |
| R8 | 83 → 11 chain | 83 / 10 / 12 / 11 | identical | ✓ |
| R9 | PDH/PDL vs EQH/EQL | +.176/+.281 vs +.010/+.006 | identical | ✓ |

---

## 3. Research-data manifest (§3)

| File | Start | End | Bars | Days | Dup | Med/day | Vol uniq | SHA-256 (16) |
|---|---|---|---|---|---|---|---|---|
| `NSE_NIFTY50-INDEX_5.csv` | 2024-01-01 09:15 | 2024-12-31 15:25 | 18,504 | 249 | 0 | 75 | **1** | `be037fe66b5eab0c` |
| `NIFTY_cache.csv` | 2025-05-19 09:15 | 2026-05-15 15:25 | 18,463 | 247 | 0 | 75 | 16,107 | `2a04a68e8f5344db` |
| `NSE_NIFTY50-INDEX_5Min.csv` | 2025-09-22 09:15 | 2026-09-25 15:20 | 18,766 | 251 | 0 | 75 | 18,681 | `e6d812031bbcfa3e` |
| `BSE_SENSEX-INDEX_5Min.csv` | 2025-09-01 09:15 | 2026-09-25 15:25 | 19,891 | 266 | 0 | 75 | 19,173 | `c93075d6e4c62f0e` |
| `NSE_NIFTYBANK-INDEX_5Min.csv` | 2026-06-29 09:15 | 2026-09-25 15:20 | 4,779 | 64 | 0 | 75 | 4,669 | `526630a4767b6a75` |
| `NSE_FINNIFTY-INDEX_5Min.csv` | 2026-07-07 09:15 | 2026-08-31 15:25 | 2,976 | 40 | 0 | 75 | 2,949 | `bc4b9dcb5dcb8522` |
| `NSE_TCS-EQ_5Min.csv` | 2026-06-25 09:15 | 2026-09-21 15:25 | 4,652 | 61 | **75** | 75 | 4,383 | `d4be0945db053a78` |
| `RELIANCE.NS_1min.csv` | **2026-05-04 03:45** | 2026-05-08 09:59 | 1,873 | 5 | 0 | 375 | 1,849 | `e76b314d1c6a7552` |

**Timezone:** all files tz-naive. Every NSE/BSE file starts at 09:15 (IST
session open) except `RELIANCE.NS_1min.csv`, which starts at **03:45** — a
different timezone, almost certainly UTC from yfinance. Not used by this
research; recorded as a provenance defect.

**Defects found and recorded (not repaired — production is frozen):**

1. **`NSE_TCS-EQ_5Min.csv` carries 75 duplicate timestamps.** No other file does.
2. **`RELIANCE.NS_1min.csv` is in a foreign timezone.**
3. **The 2024 NIFTY block has no real volume** (`nunique == 1`). Harmless for
   this research — verified no component reads volume — but it would silently
   break any volume-dependent study.
4. **`research_config.load_window` reads a CWD-relative path** and so returns
   different data depending on where the runner was launched from.
5. **The declared DEV window no longer matches the data.** `DEV_START =
   2025-05-16` against a file beginning 2025-09-22: the documented 178-day
   set is **89 days**. This is the root cause of Phase 8's "83 → 11".

**Rule adopted for Phase 9 and after:** every research run states its dataset
boundaries explicitly and never relies on a declared period matching what is
on disk.

---

## 4. The contaminated result is discarded (§4, §19)

Phase 8 found pre-10:00 entries scoring +20.1 points against −4.9 after
14:00 — **after** the NIFTY holdout had been opened. Phase 9 retested it on
the two untouched partitions, with broad pre-declared buckets:

| Bucket | SENSEX fresh | BANKNIFTY fresh |
|---|---|---|
| 09:15–10:00 | +0.275 | +0.522 |
| 10:00–12:00 | **+0.753** | −0.105 |
| 12:00–14:00 | +0.384 | +0.597 |
| 14:00–15:30 | +0.670 | **+0.648** |

**It does not replicate.** The two instruments disagree on which bucket is
best, and neither favours the pre-10:00 window Phase 8 flagged. The effect is
broadly positive across the session with no stable concentration. The
contaminated lead is **dead** and no session rule is proposed.

---

## 5. Three separate questions (§5)

| Question | Answer | Evidence |
|---|---|---|
| **A. Day-level edge** — can it pick days? | **Yes** | Phase 8: the day+direction pairs the architecture chooses score 1.26–1.66 against an unconditional ~1.00. |
| **B. Directional edge** — given a setup, the right way? | **Yes** | P4 inverted scores −0.192 against +0.229 as declared — a clean sign flip (§10). |
| **C. Timing edge** — a sufficiently early executable entry? | **Was no, now yes** | Every movement-triggered architecture failed the same-day null (p≈1.0). The location-triggered P4 beats it (p<0.001). |

The Phase 8 hypothesis `A useful, B useful, C weak` is confirmed for the
shipped architecture and **overturned** by changing what triggers the entry.

---

## 6. The timing curve (§6, §14)

PDH/PDL setups, full NIFTY sample, horizon 24. `travelled` is the distance
already covered in the trade's favour since the rejection bar.

| Stamp | dir | n | mean MFE | mean MAE | ratio | lag (bars) | travelled |
|---|---|---|---|---|---|---|---|
| T1 rejection (earliest causal) | LONG/PDL | 42 | 65.7 | 50.9 | **1.292** | 0.0 | +0.0 |
| T2 + structure confirmation | LONG/PDL | 6 | 104.7 | 64.6 | 1.620 | 3.7 | **+82.0** |
| T3 + RSI & price-action trigger | LONG/PDL | 6 | 79.3 | 90.1 | 0.880 | 4.7 | **+107.4** |
| T4 + R:R gate | LONG/PDL | 2 | 17.6 | 84.1 | 0.209 | 5.0 | +73.7 |
| T1 rejection | SHORT/PDH | 42 | 57.2 | 44.3 | **1.292** | 0.0 | +0.0 |
| T2 + structure | SHORT/PDH | 5 | 18.3 | 13.3 | 1.374 | 3.8 | +41.4 |
| T3 + trigger | SHORT/PDH | 2 | 39.7 | 4.6 | — | 3.0 | +37.7 |
| T4 + R:R | SHORT/PDH | 1 | — | — | — | 4.0 | +46.4 |

**Answer to "how much of the move is gone by the time we enter": on the long
side, about 107 of roughly 180 points — a little under 60% — and roughly 5
bars (25 minutes).** The T2/T3/T4 rows carry n ≤ 6 and are reported for the
lag and travelled columns only; their ratios are not evidence.

**Time to move** (median bars from stamp, pooled):

| Stamp | to MFE | to MAE | n |
|---|---|---|---|
| T1 rejection | 7.0 | 8.0 | 84 |
| T2 + structure | 10.0 | 3.5 | 11 |
| T3 + trigger | 10.8 | 2.5 | 8 |

Adverse excursion arrives **earlier** after each added confirmation (8.0 →
3.5 → 2.5 bars) while the favourable move arrives later. That is the
mechanical signature of a late entry.

---

## 7. Family results (§10)

### First declared set — abandoned on frequency, not performance

| Family | events/day | Reason |
|---|---|---|
| Context + PDL rejection | 0.07 | 42 events in 588 days |
| Context + PDL reclaim | 0.02 | 9 events |

All five original families required the full context block. That cut PDL
rejections from 955 to 42 (**96%**) and PDH from 1,006 to 42. The set was
abandoned **before** its out-of-sample numbers were examined, for insufficient
sample — a frequency rejection, not a performance one.

### Revised set — DEV and VAL

| Family | DEV n | DEV Δ | DEV *p* | VAL n | VAL Δ | VAL *p* |
|---|---|---|---|---|---|---|
| **P1 rejection only** | 670 | **+0.243** | **0.0023** | 426 | **+0.294** | **0.0017** |
| P2 rejection + RSI | 240 | +0.277 | 0.645 | 131 | −0.040 | 0.937 |
| P3 rejection + HTF | 38 | +0.403 | 0.630 | 17 | −0.135 | 0.964 |
| **P4 proximity state** | 598 | **+0.250** | **<0.0001** | 365 | **+0.143** | **0.0023** |
| **P5 reclaim only** | 319 | +0.193 | 0.064 | 196 | **+0.555** | **<0.0001** |
| P6 rejection + full context | 25 | +0.443 | 0.797 | 11 | −0.367 | 0.998 |
| P7 rejection + structure | 61 | −0.044 | 0.919 | 33 | −0.000 | 0.885 |

**Every family that adds a filter to the raw previous-day interaction fails
out of sample.** P2, P3, P6 all look best on DEV and all flip negative on
VAL. P7 is negative on both. The Phase 8 pattern repeats one level deeper,
now on adequate samples.

---

## 8. Execution-delay robustness (§15, §18)

Δ vs baseline, horizon 24:

| Family | Split | +0 bars | +1 | +2 | +3 |
|---|---|---|---|---|---|
| P1 | DEV | +0.243 | +0.286 | +0.331 | +0.275 |
| P1 | VAL | +0.294 | +0.287 | +0.255 | +0.159 |
| P4 | DEV | +0.250 | +0.221 | +0.207 | +0.143 |
| P4 | VAL | +0.143 | +0.191 | +0.196 | +0.178 |
| P5 | DEV | +0.193 | +0.224 | +0.284 | +0.268 |
| P5 | VAL | +0.555 | +0.607 | +0.622 | +0.523 |
| P2 *(fails OOS)* | VAL | −0.040 | −0.033 | −0.124 | −0.208 |

The survivors **degrade gracefully or improve** at +1 to +3 bars. That is the
signature of a location signal rather than a knife-edge close-price artifact,
and it is the property §18 requires. A 5-minute execution delay does not
destroy the edge.

---

## 9. Fresh holdout (§23)

The Phase 8 NIFTY holdout is contaminated. Two partitions were **never
inspected or computed** in Phase 8 — SENSEX was explicitly cut at 2026-03-31
and BANKNIFTY was skipped entirely.

```
################  FRESH HOLDOUT -- OPENED ONCE  ################
```

**FRESH A — SENSEX 2026-04-01…2026-09-25** (10,051 bars / 124 days)
baseline long 0.931, short 1.074

| Family | delay | n | days | eff | ratio | Δ vs base | null *p* |
|---|---|---|---|---|---|---|---|
| P1 | 0 | 309 | 75 | 115 | 1.282 | +0.279 | 0.116 |
| **P4** | 0 | 310 | 74 | 110 | **1.506** | **+0.501** | **0.0003** |
| **P4** | 1 | 314 | 77 | 111 | 1.462 | +0.456 | 0.0027 |
| **P5** | 0 | 147 | 62 | 75 | 1.468 | **+0.462** | **0.0088** |

**FRESH B — BANKNIFTY 2026-06-29…2026-09-25** (4,779 bars / 64 days)
baseline long 0.963, short 1.039

| Family | delay | n | days | eff | ratio | Δ vs base | null *p* |
|---|---|---|---|---|---|---|---|
| **P1** | 0 | 149 | 40 | 64 | 1.485 | **+0.489** | **<0.0001** |
| **P4** | 0 | 152 | 40 | 62 | 1.378 | **+0.382** | **<0.0001** |
| **P5** | 0 | 78 | 37 | 44 | 1.445 | **+0.449** | **0.0003** |

**Multiple testing:** approximately 38 comparisons across Phases 8 and 9.
Bonferroni ×38: SENSEX P4 `p = 0.0003 × 38 = 0.011`; BANKNIFTY P4
`p < 0.0001 × 38 < 0.004`. **Both survive correction.**

---

## 10. Adversarial controls (§27)

NIFTY full sample, horizon 24. Every control behaves as it must if the effect
is real.

| Control | n | Δ vs base | null *p* | Expected |
|---|---|---|---|---|
| **P4 as declared** (PDL→long, PDH→short) | 1,236 | **+0.229** | <0.0001 | — |
| Direction **inverted** | 1,236 | **−0.192** | 1.000 | sign flip ✓ |
| PDH/PDL **shuffled** across days (trial 1) | 149 | −0.080 | 0.892 | destroyed ✓ |
| PDH/PDL **shuffled** (trial 2) | 146 | −0.084 | 0.923 | destroyed ✓ |
| **Random level** from same-day range (1) | 3,139 | −0.047 | 0.963 | destroyed ✓ |
| **Random level** (2) | 3,203 | −0.008 | 0.562 | destroyed ✓ |
| **Session H/L** instead | 2,720 | −0.006 | — | destroyed ✓ |
| **EQL/EQH pools** instead | 6,731 | −0.014 | — | destroyed ✓ |
| Proximity band 0.10 ATR | 610 | +0.250 | 0.0007 | graceful ✓ |
| Proximity band 0.25 ATR | 1,236 | +0.229 | <0.0001 | graceful ✓ |
| Proximity band 0.50 ATR | 1,760 | +0.105 | 0.0003 | graceful ✓ |
| Proximity band 1.00 ATR | 1,964 | +0.015 | 0.035 | graceful ✓ |
| Trending regime only | 821 | +0.228 | <0.0001 | regime-free ✓ |
| Ranging regime only | 415 | +0.228 | 0.0053 | regime-free ✓ |

The effect **inverts** on direction flip, **vanishes** when the levels are
shuffled to other days, **vanishes** for random levels, **vanishes** for
session extremes and for the SMC engine's own EQH/EQL pools, and **decays
monotonically** with band width rather than sitting on a tuned cliff. It is
specifically the *previous day's* high and low, and the direction convention
matters.

---

## 11. Option-friction audit (§16, §17)

### Phase 8's calculation was wrong

Phase 8 used `theta = 9.7 %/session`. That is
`backtesting_engine/run.py::OPTION_COST_PROFILES`'s **model constant**, not a
measurement. The repository's own calibration (2026-09-21, 191 live contracts,
396 ATM contract-days, 15 sessions) measured **13.4 %/session at DTE≤1 and
4.0 % at DTE 8–14**, with premium moving the opposite way (0.32 % of spot at
DTE 1 versus 1.03 % at DTE 15+). One flat constant is wrong in both
directions.

### Input classification

| Input | NIFTY | BANKNIFTY | SENSEX |
|---|---|---|---|
| Premium % of spot | **OBSERVED** per DTE (0.32 / 1.03) | **OBSERVED** (1.38) | **OBSERVED** (0.76, single chain snapshot) |
| Delta | **OBSERVED** 0.42 | **OBSERVED** 0.376 | **OBSERVED** 0.305 |
| Round-trip spread | **OBSERVED** 0.21 % | **OBSERVED** 0.35 % | **ASSUMED** (copies NIFTY) |
| Theta %/session | **OBSERVED** 13.4 / 4.0 | **OBSERVED** 5.9 | **UNAVAILABLE** |
| IV / vega | **UNAVAILABLE** — not modelled, not fabricated | | |
| Historical option quotes | **UNAVAILABLE** — Fyers serves none for expired symbols | | |

### Recomputed result — P4, points of underlying

**NIFTY** (n = 1,236)

| Hold | DTE≤1 asym | friction | **net** | DTE 8–14 friction | **net** |
|---|---|---|---|---|---|
| 30 min | +3.4 | 2.4 | **+1.0** | 3.1 | **+0.3** |
| 60 min | +6.7 | 4.3 | **+2.3** | 5.0 | **+1.6** |
| **120 min** | **+10.9** | **8.3** | **+2.6** | 8.8 | **+2.1** |
| 240 min | +12.9 | 16.2 | −3.3 | 16.4 | −3.5 |

**BANKNIFTY** (n = 152) — net **−8.0 / −9.7 / −10.9 / −48.7** at 30/60/120/240
minutes. Premium is 1.38 % of spot against a delta of only 0.376, so friction
per point of underlying is roughly triple NIFTY's. **The signal is strong on
the BANKNIFTY underlying and the option is the wrong vehicle for it.**

**SENSEX** — `n/a`. BSE chain theta has never been measured. Reported as
unavailable rather than filled with NIFTY's number.

**This reverses Phase 8's blanket conclusion.** Friction does not beat the
edge everywhere; on NIFTY at 30–120 minute holds it does not.

---

## 12. Redundancy and the R:R question (§12, §13)

**R:R is not independent information.** `corr(sweep_bull, rr_ok_bull) = 0.78`
reproduces exactly. Risk in the R:R calculation is defined as the distance to
the swept extreme, so the gate is largely a restatement of the sweep
condition with a threshold attached. Phase 8 measured its standalone
contribution at **+0.010 / +0.003** — nothing. Adding it to the funnel cost
−0.228 (bull).

**Verdict: R:R carries no predictive information and must not filter
setups.** It may return later as an *execution* constraint (position sizing,
or refusing a contract whose stop is inside the spread), which is a different
job entirely.

Same verdict, same evidence class, for the price-action trigger (sign-
inconsistent alone: +0.038 / −0.051), FVG (+0.036 / −0.057), Order Blocks (9
events in 43,870 bars), and EQH/EQL pools (+0.010 / +0.006, and destroyed as
a level source in §10).

**RSI as a state** is weakly positive and sign-consistent (+0.032 / +0.039),
but as a gate on top of the previous-day interaction it destroyed the effect
out of sample (P2: DEV +0.277 → VAL −0.040). It is redundant, not harmful in
isolation.

---

## 13. Answers to the required questions (§30)

1. **Is the problem truly entry timing?** Partly. It is over-filtering
   *first* — three filter layers in Phase 8, the context block in Phase 9 —
   and timing second. Both are the same underlying mistake: each added
   confirmation moves the entry later and costs more than it contributes.
2. **How much movement is lost before current entry?** About **107 of ~180
   points** on the long side, roughly 5 bars / 25 minutes after the earliest
   causal stamp.
3. **Is PDH/PDL genuinely informative?** **Yes.** It survives shuffling,
   random-level substitution, session-extreme substitution, EQH/EQL
   substitution and direction inversion. No other level family does.
4. **Does reclaim/rejection provide earlier causal information?** **Yes.**
   Both are detectable at the close of the piercing bar, roughly 5 bars ahead
   of the current trigger, and both carry measurable edge (P1, P5).
5. **Does an event-driven lifecycle beat the flat boolean evaluation?** **Not
   demonstrated.** P7 (rejection → structure sequence) was negative on both
   splits; Phase 8's sequential families collapsed out of sample. The winning
   change was *removing* stages, not re-ordering them.
6. **Which confirmation layers are redundant?** R:R, price-action trigger,
   FVG, Order Blocks, EQH/EQL, and — new in Phase 9 — the whole context block.
7. **Does RSI add information as a state?** Marginally (+0.03/+0.04) and
   sign-consistently, but it is redundant on top of the level interaction.
8. **Does structure justify its delay?** **No.** It arrives ~4 bars and ~80
   points late, and P7 shows it is negative once the level interaction is
   already in hand.
9. **Is R:R predictive or a location transformation?** A location
   transformation — 0.78 correlated with `sweep`, standalone contribution
   ≈ 0.01.
10. **Does the candidate survive execution delay?** **Yes** — P4 holds
    +0.14 to +0.22 at +1 to +3 bars on both NIFTY splits and +0.456 at +1 bar
    on the fresh SENSEX partition.
11. **Does the improvement survive a fresh holdout?** **Yes** — two
    never-inspected instruments, p = 0.0003 and p < 0.0001, both surviving
    Bonferroni ×38.
12. **Does it survive realistic option friction?** **On NIFTY at 30–120
    minute holds, yes** (+1.0 to +2.6 points). On BANKNIFTY, no. On SENSEX,
    unanswerable.

---

## 14. Decision and conditions (§31)

### **VALIDATION CANDIDATE**

Scoped to the **entry signal** (`P4_proximity_state`, with `P1` and `P5` as
close relatives), **not** to the `rsi_smc_options_buyer` architecture as
shipped and **not** to any complete trading system.

This is the honest label because the signal cleared every gate §25 sets:
adequate effective sample (110–277 independent observations per window),
causal correctness, directional usefulness, earlier timing, robustness to
execution delay, a significant margin over the correct null, stability across
four windows and three instruments, and no dependence on the contaminated
result.

**It is not a strategy yet, and the following must be settled before it
becomes one:**

1. **No exit rule exists.** MFE−MAE is an excursion asymmetry, not realised
   P&L. Capturing +2.6 points of a +10.9 asymmetry requires an exit, and
   Phase 9 was forbidden — correctly — from tuning one.
2. **The selection problem is unsolved.** P4 fires ~2.1 times a day. A book
   taking one or two positions must choose which, and *that choice* is
   untested. The measured edge is an average over all firings.
3. **The option margin is thin and has no volatility term.** +2.6 points on a
   ~57-point MFE, with IV and vega absent from the model. A vol crush erases
   it. No historical option quotes exist to check against.
4. **BANKNIFTY options are the wrong vehicle**, despite the strongest
   underlying result. SENSEX is unassessable.
5. **The NIFTY 2026-04+ window is the weakest** (+0.302, p = 0.087, versus
   +0.25/+0.14 earlier and +0.50/+0.38 on the fresh instruments). Possible
   decay; it is also the contaminated window, so it is evidence of limited
   weight in both directions.
6. **This signal is not RSI + SMC.** Adopting it means largely setting aside
   the Phase 7 design. The evidence supports that, but it is a decision about
   what to build, not a tuning step.

**Unchanged: the strategy is not enabled, not paper traded, and not
production-ready.**

---

## 15. Reproducibility

`docs/research/phase9/` — `p8lib.py`, `split.py` (Phase 8, reused verbatim for
reproduction), plus `timing.py`, `curve.py`, `families.py`, `fam2.py`,
`p9eval.py`, `fresh.py`, `friction.py`, `adversarial.py`.

Research-only. Nothing under `trading_bot/` imports any of it.

## 16. What was NOT done

- No production file modified; no live config key added; `active_strategy`
  unchanged; no paper-trading code; no exit tuning.
- The fresh holdout was opened **once**, after DEV and VAL were complete, and
  nothing was changed afterwards.
- No parameter was swept. The proximity band was pre-declared at 0.25 ATR;
  the other bands in §10 are a reported robustness profile, not a search.
- No IV, OI, Delta or Greek was fabricated. SENSEX friction is left blank.
- The contaminated pre-10:00 result was tested and discarded, not used.
