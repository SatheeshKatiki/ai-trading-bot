# Phase 8 — Deep Edge Research: RSI_SMC_OPTIONS_BUYER

**Status:** research only. Production plane untouched and unchanged throughout.
`active_strategy` remains `ema9_rsi_momentum`. No live configuration key was
added. No paper-trading code was written. **The strategy remains NO-GO.**

**Decision: CONTINUE RESEARCH.**

---

## 1. Executive summary

Phase 7 concluded "no entry edge" from MFE/MAE ratios of 0.74–0.97 measured
against a reference of 1.0. Phase 8 finds that conclusion was **measured
wrongly in three independent ways**, and that the underlying architecture is
failing for a reason Phase 7 did not identify.

**Three measurement defects, each corrected here:**

1. **The reference was wrong.** In this sample a *long* entry's MFE/MAE is
   **0.92** by construction and a *short* entry's is **1.09**, at every
   horizon and in every split. Comparing both to 1.0 penalised longs and
   flattered shorts. Phase 7's CE ratio of 0.949 was in fact *above* its
   baseline; the PE ratio of 1.012 was *below* its own.
2. **The context was wrong.** `measure_signal_edge.py` runs the strategy on
   all 43,870 bars at once. The live engine sees `tail(2000)`. Because the
   strategy's liquidity-pool set grows with history, the same date range
   produces different signals — 24 entries at ≤2000 bars of context, 26 at
   ≥6000, with different timestamps. Phase 7's "83 entries" is a
   configuration the live engine would never run; the live-equivalent number
   is **51**.
3. **The window was wrong.** `research_config.load_window` declares DEV as
   2025-05-16…2026-01-31 but reads a CSV that now begins 2025-09-22. The
   documented 178-day development set is silently **89 days**. That is why
   the entry-information test saw 11 entries.

**The architectural finding.** Measured stage by stage, the shipped
nine-condition chain *accumulates* information through its first six stages
and then *destroys* it in the last three:

| | bull chain | bear chain |
|---|---|---|
| baseline | 0.914 | 1.094 |
| after structure + RSI | **1.036** (n=483) | **1.205** (n=395) |
| after price-action trigger | 0.860 (n=186) | 1.040 (n=133) |
| after R:R gate | **0.632** (n=42) | **1.003** (n=25) |

Removing RSI, the trigger and the R:R gate turns an architecture that scores
**−0.13 below baseline** on the final holdout into one that scores **+0.18
above it**, and that survives every window tested.

**But it is still not tradeable as an options-buying system**, for a reason
that is now precisely quantified: the surviving architecture's directional
asymmetry is **smaller than option friction at every hold time**.

---

## 2. Measurement-integrity audit (§2)

| Check | Finding |
|---|---|
| OHLCV source integrity | `NIFTY_cache.csv` and `NSE_NIFTY50-INDEX_5Min.csv` overlap on 11,863 bars and agree **exactly** — 0 differences in O/H/L/C/volume. No hybrid-series risk. |
| 2024 block | `NSE_NIFTY50-INDEX_5.csv` has `volume.nunique() == 1` — **no real volume**. Not a defect for this strategy: no component reads volume (verified — regime uses ADX/BB/ATR, choppiness uses range, SMC uses volume only for a diagnostic `OrderBlock.volume` field). |
| Timezone | All sources tz-naive IST. Consistent. No conversion applied anywhere. |
| Candle ordering / duplicates | `drop_duplicates(subset=["_ts"])` then `sort_values`. Clean. |
| Session boundaries | Forward windows are truncated at the day boundary. Verified this does **not** bias the ratio: MFE/MAE by time-of-day is flat (long 0.89–0.93 across 09:15–15:00). |
| 5m→15m aggregation | Positional bucketing, previous **completed** bucket only. A bug was found and fixed during Phase 7 (`index.view("int64")` is unit-dependent; this data parses as `datetime64[us]`, collapsing 4,000 bars into 8 buckets). |
| Indicator alignment | Verified by the Phase 7 causality suite (31 tests). |
| Feature availability | Every SMC object carries an explicit confirmation bar; see `docs/SMC_FEATURE_CAUSALITY.md`. |
| Forward-window construction | Entry price = bar *i*'s close; window = bars [*i*+1, *i*+h]. Consistent and applied identically to every strategy compared. |
| Sample exclusions | Only bars with no same-day forward window. Zero entries lost at any horizon. |

**Two axes of invariance, tested separately:**

- **Future-truncation invariance — PASSES.** Truncating future bars never
  changes an earlier signal (pinned by `test_signals_do_not_change_when_future_bars_arrive`). No look-ahead.
- **Past-context invariance — FAILS.** Varying the amount of *preceding*
  history changes signals:

```
same target range (2026-02-01..2026-07-31), varying preceding context
  context bars    entries    timestamp hash
             0         24    c43ffabee862
           500         24    c43ffabee862
          2000         24    c43ffabee862
          6000         26    b8c97235dfb6   <- CHANGED
         12000         26    c1bdc2779f4c   <- CHANGED
         31717         26    ac071369794d   <- CHANGED
```

This is **not** look-ahead — every pool involved is in the past. It is an
unbounded-history dependence: `nearest_price_mask` scans every liquidity pool
in the frame, so a longer frame offers a nearer pool. **Live it would behave
as the ≤2000 row; every Phase 7 research number came from the last row.**
All Phase 8 measurements use a live-equivalent replay (blocks of 200 bars,
each seeing at most 2000 prior bars), verified stable: chunk=100 and
chunk=200 give identical entry fingerprints.

---

## 3. The 83 → 11 reconciliation (§3)

Fully reconciled. There is no hidden filter cascade — the two numbers come
from **different date ranges**.

```
 83   raw entries, measure_signal_edge frame
      (2024-01-01..2026-09-25, 588 days, 43,870 bars, unbounded context)
  ↓  −73   outside the DEV date range: DEV is 89 of those 588 days
 10   entries inside the DEV range, computed on the full frame
  ↓   +2   strategy re-run on the DEV slice alone — different preceding
           context (§2) and a different warm-up prefix
 12   entries the entry-information test starts from
  ↓   −1   inside the opening 6 bars, so not in the eligible pool
 11   entries measured
```

Checked and **not** contributing: direction matching (0 lost), timestamp
alignment (0), missing forward bars (0), instrument mapping (0), duplicate
removal (0), invalid labels (0), option/underlying mapping (0), late-session
exclusion (0 — no entry fell at/after 15:15).

**Conclusion:** the 11-entry market-blindness result was never a statistical
finding. It was a window-size artifact, arising from a research-config defect.
No conclusion should have been drawn from it, and none is drawn here.

---

## 4. Label / MFE / MAE audit (§4)

| Element | Verdict |
|---|---|
| MFE / MAE definition | Max favourable / adverse excursion from bar *i*'s close over [*i*+1, *i*+h]. Sound and exit-independent. |
| Entry reference | Bar *i*'s close, forward window from *i*+1. Excludes the signal bar's own excursion — conservative, and identical for every strategy compared. |
| Direction normalisation | Verified: CE favourable = up, PE favourable = down. |
| Gap handling | Windows never cross a day boundary, so overnight gaps never enter a label. |
| Horizon construction | Fixed bar counts; no adaptive horizon. |

### Special check — target selection (§4)

Phase 7 changed the target from *nearest* opposing level to *most rewarding
qualifying* level. **Audited: this is causal.** All three candidate families
are known at decision time — liquidity pools are gated on the measured
confirmation bar, previous-day levels come from a completed prior day, and
session extremes are a running aggregate that **excludes the current bar**.
The selection maximises reward/risk *among levels available at bar i*; it
cannot see a future extremum or a later structure. The future-truncation test
(§2) confirms this empirically.

`Known at T` and `Discovered after T` are structurally separated by
`structure.SmcView` (`IS_CAUSAL`) versus `structure.SmcAnalyticalView`
(`IS_ANALYTICAL`), with `assert_causal()` enforcing the boundary.

---

## 5. Effective sample size (§5)

Live-equivalent, full 588-day sample, shipped architecture:

| horizon | raw | days | per day | overlapping | effective (non-overlapping) |
|---|---|---|---|---|---|
| 6 | 51 | 43 | 1.19 | 6 | 45 |
| 12 | 51 | 43 | 1.19 | 7 | 44 |
| 24 | 51 | 43 | 1.19 | 7 | 44 |
| 48 | 51 | 43 | 1.19 | 8 | 43 |

Clustering is mild — 51 raw entries are ~44 independent observations. The
binding constraint is **raw count, not correlation**: 51 entries over 588
days is 0.09/session, well below the 200-entry pre-registration bar. The
surviving candidate (§11) produces 711 entries / ~470 effective, which does
clear it.

---

## 6. The complete information funnel (§6)

NIFTY, full sample, live-equivalent, horizon 24.

### Bull chain (baseline 0.914)

| Stage | Retained | Ret % | MFE>MAE | MFE/MAE | Δ vs previous |
|---|---|---|---|---|---|
| (all bars) | 43,870 | 100% | 48.5% | 0.914 | — |
| htf_bull | 18,716 | 42.7% | 49.4% | 0.895 | −0.019 |
| regime_ok | 14,741 | 33.6% | 49.5% | 0.910 | +0.015 |
| level_near | 7,867 | 17.9% | 50.2% | 0.952 | +0.042 |
| sweep | 4,321 | 9.8% | 50.8% | 0.978 | +0.026 |
| struct | 660 | 1.5% | 54.0% | 0.980 | +0.002 |
| **rsi** | **483** | **1.1%** | **55.7%** | **1.036** | **+0.056 ← peak** |
| trigger | 186 | 0.4% | 48.4% | 0.860 | **−0.176** |
| rr_ok | 42 | 0.1% | 42.5% | 0.632 | **−0.228** |
| not_blocked | 36 | 0.1% | 47.2% | 0.663 | +0.031 |

### Bear chain (baseline 1.094)

| Stage | Retained | Ret % | MFE>MAE | MFE/MAE | Δ vs previous |
|---|---|---|---|---|---|
| (all bars) | 43,870 | 100% | 51.5% | 1.094 | — |
| htf_bear | 16,764 | 38.2% | 51.8% | 1.061 | −0.033 |
| regime_ok | 13,485 | 30.7% | 51.7% | 1.040 | −0.021 |
| level_near | 7,078 | 16.1% | 50.8% | 1.048 | +0.008 |
| sweep | 4,002 | 9.1% | 52.5% | 1.081 | +0.033 |
| **struct** | **587** | **1.3%** | **55.7%** | **1.205** | **+0.124 ← peak** |
| rsi | 395 | 0.9% | 55.6% | 1.205 | 0.000 |
| trigger | 133 | 0.3% | 48.9% | 1.040 | **−0.165** |
| rr_ok | 25 | 0.1% | 44.0% | 1.003 | **−0.037** |
| not_blocked | 24 | 0.1% | 41.7% | 0.999 | −0.004 |

**The last three stages destroy what the first six accumulate, in both
directions.** This is the single clearest structural result in Phase 8.

---

## 7. Incremental information and redundancy (§7)

Every condition measured **alone** against the same labels is within ±0.06 of
baseline — no single filter carries meaningful standalone information. The
pairwise correlation matrix explains why nine conditions are not nine sources
of evidence:

| pair | correlation |
|---|---|
| `sweep_bull` ↔ `rr_ok_bull` | **0.78** |
| `level_near_bull` ↔ `sweep_bull` | 0.39 |
| `level_near_bull` ↔ `rr_ok_bull` | 0.36 |
| `struct_bull` ↔ `rsi_bull` | 0.27 |
| `htf_bull` ↔ `rr_ok_bull` | −0.26 |

`rr_ok` is largely a **restatement of `sweep`** — unsurprising, since risk is
defined as the distance to the swept extreme. Level / sweep / R:R form one
correlated cluster. The architecture has roughly **four to five** independent
blocks presented as nine.

---

## 8. Event / state / lifecycle semantics (§8)

| Feature | Implemented as | Should be | Correct? |
|---|---|---|---|
| HTF bias | STATE (previous completed 15m bucket) | STATE | ✅ |
| Regime | STATE | STATE | ✅ |
| Key level | LEVEL, with lifecycle gating | LEVEL | ✅ |
| Liquidity sweep | EVENT with a 5-bar lifetime | EVENT with lifetime | ✅ |
| BOS / CHoCH | EVENT, widened by `_recent(window)` | EVENT | ✅ |
| Order Block | LIFECYCLE OBJECT (candidate→confirmed→mitigated/invalidated) | same | ✅ |
| FVG | LIFECYCLE OBJECT | same | ✅ |
| Swing | LIFECYCLE OBJECT, confirmed at pivot+L | same | ✅ |
| **RSI** | Phase 7 draft: EVENT (midline cross). Shipped: STATE | STATE | ✅ corrected in Phase 7 |
| **Price-action trigger** | EVENT (decisive candle) | — | ⚠️ semantically fine, **empirically harmful** |

No remaining semantic error was found: after the Phase 7 RSI correction, every
feature is handled at the right level. **The problem is not semantics.**

---

## 9. Sequential structure (§9)

Tested `sweep → structure → state` as an ordered sequence against the flat
conjunction. On DEV the sequential forms looked much better; **they did not
replicate.**

| Candidate | DEV | VAL | SENSEX | HOLDOUT |
|---|---|---|---|---|
| F_sequential (windowed) | **+0.203** | +0.009 | −0.172 | −0.008 |
| S4_sequence_event (on the event bar) | **+0.294** | +0.002 | −0.047 | −0.079 |

The two best DEV performers failed hardest everywhere else — the textbook
signature of selection on noise, and precisely what the pre-declared split was
built to catch. **Sequencing is not the answer.**

---

## 10. Structure bottleneck (§12)

`2,915 level candidates → 1,632 sweep → 17 structure` was the Phase 7 funnel.
The five hypotheses, measured:

| Case | Verdict |
|---|---|
| **A** — structure is informative but rare | **Partly true.** Structure is the largest single jump in MFE>MAE (50.8→54.0% bull, 52.5→55.7% bear), but its ratio gain is small on the bull side. |
| **B** — definition unnecessarily restrictive | **False as the primary cause.** Lowering the swing length raises count but not quality; the architecture already runs at LuxAlgo's internal-structure length of 5. |
| **C** — confirmation delayed past useful entry timing | **TRUE, and it is the dominant effect.** See §11. |
| **D** — duplicates liquidity/regime information | **Partly true**, correlation 0.27 with RSI, −0.08 with sweep. Not the main issue. |
| **E** — sparse because of swing/confirmation semantics | **True but benign** — sparsity is real, and the confirmation delays are causally required. |

---

## 11. Structure timing — the central finding (§13)

Decomposing each architecture into **which days and directions it picks**
versus **when within those days it enters** (horizon 24, DEV):

| Candidate | strategy entries | all bars, same day + same direction | timing delta |
|---|---|---|---|
| A (shipped) | 0.640 | 1.256 | **−0.616** |
| B (no trigger) | 0.753 | 1.481 | **−0.729** |
| C (no R:R) | 1.019 | 1.445 | **−0.426** |
| D (neither) | 1.049 | 1.562 | **−0.513** |
| E (setup core) | 1.077 | 1.571 | **−0.494** |
| F (sequential) | 1.202 | 1.660 | **−0.458** |
| G (evidence 5/6) | 1.022 | 1.466 | **−0.444** |

**Every architecture picks the right day and direction and the wrong moment.**
The day/direction choice is genuinely informative (1.26–1.66 against an
unconditional ~1.0). The intraday entry timing gives back 0.43–0.73 of it.

The mechanism is not mysterious: these are **movement-triggered** entries. A
crossover, a break, a sweep confirmation all fire *after* price has moved, so
part of the favourable excursion is already spent while the retracement is
still ahead. A randomly chosen earlier bar on the same day captures more of
the move.

**This is a repository-level property, not a defect unique to this strategy** —
see §19.

---

## 12. Liquidity analysis (§14)

Each level family measured independently, same rule, DEV+VAL:

| Family | long n | long Δ | short n | short Δ |
|---|---|---|---|---|
| **Previous-day H/L** | 2,400 | **+0.176** | 2,463 | **+0.281** |
| Session H/L | 163 | +0.142 | 148 | +0.162 |
| EQH/EQL pools (SMC engine) | 17,297 | +0.010 | 17,663 | +0.006 |
| Rolling extreme (reference detector) | 6,874 | −0.048 | 7,376 | −0.016 |

**Liquidity types are emphatically not equal.** Previous-day high/low sweeps
carry several times the information of anything else, in both directions, on
a large sample. The SMC engine's own EQH/EQL pools — which required the entire
lifecycle and availability-delay apparatus — contribute **essentially nothing**.
The rolling extreme, which is the dead `LiquiditySweepDetector`'s definition,
is mildly **negative**.

The shipped architecture blends all of these into one `nearest_level` call,
diluting the only family that works.

---

## 13. Order Block analysis (§15)

Under live-equivalent context, over 43,870 bars: `in_bull_ob` fires **6**
times, `in_bear_ob` **3** times. Sample too small to measure at all.

Confirmation lag distribution (813 blocks, full sample): median ≈ 4 bars,
range 1–16. The lifecycle model works correctly; the feature is simply
near-empty because OB zones are narrow and are mitigated quickly.

**Verdict: keep Order Blocks as a causal research / chart / analytics feature.
Do not add them as a trade filter.** The `use_ob_trigger` flag remains OFF and
should stay OFF. This matches the Phase 7 decision, now supported by a count.

---

## 14. FVG analysis (§16)

| | n | Δ vs baseline |
|---|---|---|
| In a confirmed, unmitigated bullish FVG | 12,849 | +0.036 |
| In a confirmed, unmitigated bearish FVG | 10,678 | **−0.057** |

**Sign-inconsistent between directions on a large sample** — the hallmark of
noise rather than information. FVG works as a *location* descriptor and is
correctly modelled as a lifecycle object, but there is no evidence it belongs
in the entry decision.

---

## 15. RSI analysis (§17)

| | n | Δ vs baseline |
|---|---|---|
| RSI bullish state | 12,328 | +0.032 |
| RSI bearish state | 11,506 | +0.039 |

As a **state**, RSI is weakly positive and *sign-consistent* — the only
confirmation-class feature that is. But in the funnel it adds +0.056 (bull)
and 0.000 (bear), and removing it entirely (E vs D) *improves* out-of-sample
consistency. Its marginal information is already contained in the HTF-bias and
structure blocks (correlation 0.27 with `struct`, 0.18 with `htf`).

**Verdict: RSI is correctly modelled as a state and is not harmful, but it is
redundant.** It should not be a mandatory gate.

---

## 16. Session / time-of-day (§18)

Unconditional ratio by slot (full sample) is **flat**, which is what rules out
day-boundary truncation as an explanation for anything above:

| Slot | long | short | avg forward bars |
|---|---|---|---|
| 09:15–10:00 | 0.907 | 1.103 | 24.0 |
| 10:00–11:00 | 0.931 | 1.074 | 24.0 |
| 11:00–12:00 | 0.915 | 1.092 | 24.0 |
| 12:00–13:00 | 0.913 | 1.095 | 24.0 |
| 13:00–14:00 | 0.905 | 1.105 | 22.2 |
| 14:00–15:00 | 0.890 | 1.123 | 11.5 |
| 15:00–15:30 | 1.077 | 0.928 | 3.0 |

A strong session effect *does* appear in the failure-mode analysis (§21), but
it was found **after** the holdout was spent and is therefore flagged
DATA-DEPENDENT and unvalidated.

---

## 17. Regime-stratified edge (§19)

| Candidate | trending | ranging |
|---|---|---|
| A (shipped) | −0.178 (n=44) | −0.140 (n=7) |
| **E (setup core)** | **+0.101 (n=610)** | **+0.256 (n=101)** |
| F (sequential) | +0.111 (n=569) | +0.020 (n=128) |
| S1 (sweep onset) | +0.021 (n=3,180) | +0.213 (n=458) |

E is positive in **both** regimes and materially stronger in ranging markets —
consistent with a sweep-and-reversal mechanism. No candidate depends on a
single regime.

---

## 18. Cross-instrument (§20)

SENSEX, restricted to ≤2026-03-31 so the NIFTY holdout was not burned on
another instrument. Same definitions, no per-instrument tuning.

| Candidate | NIFTY DEV | NIFTY VAL | SENSEX |
|---|---|---|---|
| A (shipped) | −0.367 | +0.171 (n=15) | −0.119 |
| **E (setup core)** | **+0.082** | **+0.144** | **+0.085** |
| F (sequential) | +0.203 | +0.009 | **−0.172** |
| S4 (sequence event) | +0.294 | +0.002 | −0.047 |
| S1 (sweep onset) | +0.050 | +0.073 | +0.101 |

BANKNIFTY has **zero** bars before the holdout cut — skipped rather than burn
the holdout. Its data begins 2026-06-29.

---

## 19. Existing-strategy calibration (§21)

Identical methodology, live-equivalent replay, same labels.

| Strategy | DEV Δ | VAL Δ | same-day null *p* (DEV / VAL) |
|---|---|---|---|
| ema9_rsi_momentum | +0.125 | −0.100 | 0.61 / 0.68 |
| momentum_15_5 | −0.094 | +0.185 | 0.94 / 0.34 |
| structure_break | +0.072 | +0.007 | 0.999 / 0.998 |
| ema_rsi | −0.045 | −0.031 | 1.000 / 1.000 |
| buy_the_dip | −0.074 | +0.063 | 0.999 / 0.930 |

**Three calibration conclusions:**

1. **MFE/MAE below baseline is normal here.** Every strategy tested flips sign
   between DEV and VAL. Phase 7's gate ("materially > 1.0") is one that
   essentially nothing in this repository passes — and, being direction-blind,
   it was biased against long-heavy strategies.
2. **Failing the same-day null is universal.** Every strategy with enough
   entries fails it. The late-entry property in §11 is a property of
   movement-triggered entries in general, not of `rsi_smc_options_buyer`.
3. **The sample-size gate was reasonable.** 200 entries is not demanding:
   `ema_rsi` produces 1,306 on DEV alone. A strategy generating 51 in 588
   sessions has a frequency problem regardless of quality.

---

## 20. Market-blindness / permutation results (§22)

Null A (same day, same direction, random time), 4,000 draws, validated on
random masks first (observed ≈ null mean, p ≈ 0.16–0.75, as required).

| Candidate | split | n | observed | null mean | null p05–p95 | p |
|---|---|---|---|---|---|---|
| A | DEV | 21 | 0.640 | 1.336 | 0.736–2.144 | 0.983 |
| E | DEV | 309 | 1.077 | 1.579 | 1.366–1.814 | 1.000 |
| E | HOLDOUT | 171 | 1.179 | 1.602 | — | 0.998 |
| F | DEV | 305 | 1.202 | 1.669 | 1.427–1.937 | 1.000 |

**No architecture beats the same-day null, in any window.** The observed value
sits below the null's 5th percentile in most cases — significantly *worse*
than random timing on the same days.

Against the **unconditional** baseline (Null B family) the picture is
different and positive for E — see §22. Both statements are true; they answer
different questions, and reporting only one would be misleading.

---

## 21. Failure modes (§30)

E_setup_core, 711 entries, 312 losers (44%):

| Attribute | n | loss rate | vs overall | mean MFE−MAE |
|---|---|---|---|---|
| **Entered before 10:00** | 107 | 38.3% | **−5.6pp** | **+20.1 pts** |
| **Entered after 14:00** | 134 | 52.2% | **+8.4pp** | **−4.9 pts** |
| Ranging regime | 101 | 42.6% | −1.3pp | +11.1 pts |
| Trending regime | 610 | 44.1% | +0.2pp | +4.8 pts |
| RR gate passed | 251 | 46.6% | +2.7pp | −0.1 pts |
| Trigger candle fired | 264 | 45.8% | +2.0pp | +5.5 pts |
| RSI agreed | 510 | 43.7% | −0.2pp | +6.1 pts |
| Long side | 375 | 45.9% | +2.0pp | −0.4 pts |

The R:P gate and the trigger candle both raise the loss rate — independent
confirmation of §6.

> **The early-session effect (+20.1 pts before 10:00) was found AFTER the
> holdout was spent. It is DATA-DEPENDENT and UNVALIDATED. It must not become
> a rule without a fresh split.** It is recorded as a research lead only.

---

## 22. Data-mining controls and the walk-forward (§23, §24)

**Pre-declared split**, fixed before any candidate comparison:

| Split | Range | Bars | Days | Role |
|---|---|---|---|---|
| DEV | 2024-01-01 … 2025-06-30 | 20,829 | 280 | selection |
| VAL | 2025-07-01 … 2026-03-31 | 13,888 | 186 | validation |
| HOLDOUT | 2026-04-01 … 2026-09-25 | 9,153 | 122 | touched **once** |

Embargo of 48 bars (the longest horizon) between blocks. 14 DEV comparisons
were made (7 candidates + 7 entry-point variants); a Bonferroni factor of 14
is applied to all reported p-values. **No p-value survives it** — reported
honestly rather than omitted.

### Walk-forward by quarter (Δ vs baseline, horizon 24)

| Candidate | 24Q1 | 24Q2 | 24Q3 | 24Q4 | 25Q2 | 25Q3 | 25Q4 | 26Q1 | 26Q2 | 26Q3 | positive |
|---|---|---|---|---|---|---|---|---|---|---|---|
| A | −0.22 | — | −0.34 | −0.61 | — | — | −0.11 | — | −0.21 | — | **0/6** |
| **E** | −0.11 | +0.12 | +0.54 | +0.02 | −0.01 | +0.05 | +0.15 | +0.25 | +0.17 | +0.18 | **8/10** |
| F | +0.12 | +0.47 | +0.22 | +0.13 | −0.17 | +0.20 | −0.17 | −0.01 | +0.01 | −0.04 | 6/10 |
| S1 | −0.02 | +0.10 | +0.31 | −0.13 | +0.03 | −0.02 | +0.05 | +0.16 | +0.03 | −0.08 | 6/10 |

### Final holdout — touched once

| Candidate | n | days | effective | ratio | Δ vs baseline |
|---|---|---|---|---|---|
| A (shipped) | 15 | 12 | 12 | 0.852 | **−0.132** |
| **E (setup core)** | **171** | **76** | **92** | **1.179** | **+0.178** |
| F (sequential) | 160 | 87 | 107 | 0.998 | −0.008 |
| S4 (sequence event) | 94 | 67 | 76 | 0.928 | −0.079 |
| S1 (sweep onset) | 796 | 119 | 252 | 0.986 | −0.013 |

**Exactly one candidate is positive in all four windows: E_setup_core**
(DEV +0.082, VAL +0.144, SENSEX +0.085, HOLDOUT +0.178).

---

## 23. Candidate architectures and their failure modes (§32, §33)

**A — full conjunction (shipped).** Nine ANDed conditions.
*Evidence against:* negative on DEV (−0.367) and HOLDOUT (−0.132); 0 of 6
quarters positive; n=15–21 per window; fails cross-instrument.
*Evidence for:* none. **Rejected.**

**E — setup core.** `HTF bias AND regime AND level proximity AND liquidity
sweep AND structure confirmation AND no-trade-clear`. RSI, price-action
trigger and R:R gate all removed.
*Evidence for:* positive in all four windows; 8/10 quarters; both regimes;
horizon-monotone on DEV, VAL and HOLDOUT; 711 entries / ~470 effective.
*Evidence against:* fails the same-day null (p=0.998); effect size below
option friction (§24); +0.178 on holdout rests on 171 entries over 76 days.
**The only candidate worth further research.**

**F — windowed sequential / S4 — sequence event.** DEV leaders.
*Evidence against:* collapse on VAL (+0.009, +0.002), negative on SENSEX and
HOLDOUT. **Rejected — selection on noise.**

**S1 — sweep onset.** Earliest actionable point.
*Evidence for:* positive DEV/VAL/SENSEX, very high frequency (796 holdout
entries). *Evidence against:* −0.013 on holdout. **Rejected.**

**G — evidence score (5 of 6).**
*Evidence against:* +0.023 on DEV, smallest margin of any variant; the
correlation structure (§7) means the score double-counts. **Rejected.**

---

## 24. Underlying edge and options-implementation readiness (§25, §26, §27)

### Layer A — underlying directional edge

E_setup_core shows a **small but repeatable** directional asymmetry:
+0.08 to +0.18 MFE/MAE above the direction-matched baseline, across four
independent windows and two instruments.

### Layer B — contract implementation

Using only **measured** NIFTY values (2026-09-21: premium 0.40% of spot,
delta 0.42, round-trip spread 0.21% of premium, theta 9.7%/session). No
fabricated IV, OI or Greeks.

| Hold | Minutes | n | mean MFE | mean MAE | MFE−MAE | Friction | **Net** |
|---|---|---|---|---|---|---|---|
| 3 bars | 15 | 711 | 18.9 | 18.2 | +0.6 | 1.4 | **−0.7** |
| 6 bars | 30 | 711 | 26.3 | 25.9 | +0.5 | 2.3 | **−1.8** |
| 12 bars | 60 | 711 | 37.4 | 35.7 | +1.7 | 4.1 | **−2.4** |
| 24 bars | 120 | 711 | 53.3 | 47.5 | +5.7 | 7.7 | **−1.9** |
| 48 bars | 240 | 711 | 68.5 | 57.6 | +10.9 | 14.8 | **−3.9** |

*(all figures in NIFTY points; friction converted at delta 0.42)*

**This is the decisive options-specific result. The directional asymmetry is
smaller than option-buying friction at every hold time tested.** The edge
grows with hold time (+0.6 → +10.9) but friction grows faster (1.4 → 14.8),
because theta dominates and scales with time held.

The squeeze is structural: E's edge does not appear until 12–24 bars
(holdout: −0.029 at 3 bars, −0.045 at 6, +0.112 at 12, +0.178 at 24), but by
then decay has consumed more than the edge is worth.

**Option layer verdict: UNVALIDATED and, on present evidence, NEGATIVE.**
Historical option-chain data does not exist in this repository, so these are
modelled costs applied to measured underlying excursions — directionally
reliable, not exact.

---

## 25. Recommended next research architecture (§31)

No `RSI_SMC_NEXT_ARCHITECTURE_SPEC.md` has been written. Per §35 that document
is created *only if a genuinely defensible architecture emerges*, and
E_setup_core does not clear that bar: it fails the same-day null and its
measured edge is smaller than option friction. Writing a spec would overstate
what the evidence supports.

**What the evidence does support, for a future phase:**

1. **Delete three stages.** RSI gate, price-action trigger, R:R gate. Each is
   measurably harmful or redundant; together they invert the architecture's sign.
2. **Stop blending liquidity families.** Previous-day H/L is worth several
   times the others (+0.176 / +0.281). EQH/EQL pools contribute ~0.01. A
   PDH/PDL-only sweep rule is simpler *and* better-supported.
3. **Attack the timing deficit directly.** Every architecture gives back
   0.43–0.73 by entering after movement. Candidate approaches worth testing on
   a *fresh* split: entering on the approach to a level rather than after the
   sweep confirms; limit-style entries at the level; or accepting the
   day/direction call and timing entry by something other than the setup event.
4. **Treat the frequency problem as primary.** 0.09–1.2 entries/session is too
   few to validate anything quickly. Any redesign should target frequency
   *before* selectivity.
5. **Fix the research pipeline first** (§2): the DEV window is half its
   documented size, and `measure_signal_edge` uses unbounded context.

---

## 26. Explicit decision (§28, §37)

**A. Is there evidence of directional information anywhere in the feature
hierarchy?** **Yes.** The CONTEXT+SETUP block (HTF bias + regime + level
proximity + liquidity sweep + structure confirmation) is positive in all four
windows and on two instruments. Previous-day-liquidity sweeps are the single
most informative component found (+0.18 / +0.28).

**B. Which blocks appear useful?** HTF EMA bias with slope agreement; regime
classification; previous-day high/low sweeps; structure confirmation
(BOS/CHoCH); and, weakly and redundantly, RSI as a state.

**C. Which appear redundant or harmful?** The **R:R gate** (harmful; 0.78
correlated with `sweep`), the **price-action trigger** (harmful; sign-
inconsistent alone), **FVG** (sign-inconsistent), **Order Blocks** (9 events in
43,870 bars), **EQH/EQL pools** (≈0.01), and the **rolling-extreme sweep**
definition (negative).

**D. Is the nine-way AND structurally wrong?** **Yes, in its last three
stages.** Removing them moves the holdout from −0.132 to +0.178. The
conjunction *form* is not the problem — the sequential and score variants did
worse. The problem is *which* conditions are conjoined.

**E. Rarity, timing, semantics, or genuine lack of edge?** **Over-filtering
first, timing second.** Semantics are correct. There is real information, and
it is not rare in the setup block (711 entries). The two destroyers are three
value-negative filters and a systematic late-entry bias worth −0.43 to −0.73.

**F. Does a redesigned causal architecture have evidence sufficient for
further validation?** **Yes for continued research; no for promotion.**
E_setup_core is the only structure in this repository to survive a
pre-declared four-window protocol — but it fails the same-day null and its
edge is below option friction.

**G. Is the strategy still NO-GO for trading?** **Yes. Unchanged.**

### FINAL DECISION: **CONTINUE RESEARCH**

Not "promotion candidate": the options-translation test is negative and the
timing deficit is unresolved. Not "shelve": a causally clean architecture that
is positive in four independent windows and two instruments, with three
specifically identified value-destroying components, is a live research lead.

---

## 27. Reproducibility

Every figure comes from `docs/research/phase8/`:

| Script | Produces |
|---|---|
| `p8lib.py` | live-equivalent replay, forward labels, clustering |
| `split.py` | the pre-declared split, permutation nulls, baselines |
| `funnel.py` | §6 funnel, §7 marginals, §5 effective sample |
| `candidates.py` | the seven pre-declared architectures |
| `validate.py` | DEV/VAL/HOLDOUT evaluation of the locked set |
| `calib.py` | §21 existing-strategy calibration |
| `cross.py` | §20 cross-instrument |
| `components.py` | §14/16/17 component analysis, §7 correlations |
| `more.py` | §19 regime, §24 walk-forward, §29 decay |

Research-only. Nothing under `trading_bot/` imports any of it.

## 28. What was NOT done

- No production file was modified. No live config key added. `active_strategy`
  unchanged. No paper-trading code written.
- The holdout was inspected **once**, after DEV and VAL were complete, and no
  rule was changed afterwards.
- No parameter was swept. The only window used (`confirm_window = 8`) is the
  one already shipped.
- No IV, OI, Delta or Greek was fabricated. Option costs are measured values.
- The early-session effect was **not** turned into a rule.
