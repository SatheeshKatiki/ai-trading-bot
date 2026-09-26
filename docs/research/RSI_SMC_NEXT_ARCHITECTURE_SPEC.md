# Next Architecture — Specification (research)

**Status:** research specification. **Not approved for implementation, not
enabled, not paper traded.** Written because Phase 9 produced a signal that
cleared a fresh, never-inspected holdout on two instruments with all
adversarial controls behaving correctly — the bar §29 sets for this document
to exist at all.

**Scope:** this specifies an **ENTRY SIGNAL**, not a trading system. Exits,
sizing and contract selection are explicitly out of scope and unresolved.

---

## 1. What this replaces, and why

The shipped `rsi_smc_options_buyer` entry is a nine-condition conjunction. It
scores **−0.132** against its direction-matched baseline on the Phase 8
holdout. Measured stage by stage, it accumulates information through six
stages and destroys it in the last three, then the Phase 9 context block
destroys most of the remaining sample.

| Architecture | Conditions | Best out-of-sample result |
|---|---|---|
| Shipped (Phase 7) | 9 | −0.132 (holdout) |
| `E_setup_core` (Phase 8) | 6 | +0.178 (holdout), fails same-day null |
| **This spec (Phase 9)** | **1** | **+0.501 / +0.382 (two fresh instruments), beats same-day null p<0.001** |

The direction of the evidence is consistent and unambiguous: **every layer
removed improved out-of-sample behaviour.**

---

## 2. The signal

> **Enter toward reversion when price is within 0.25 ATR of the previous
> trading day's high or low.**

```
    price within 0.25 x ATR(14) of PREVIOUS DAY LOW    ->  long   (buy CE)
    price within 0.25 x ATR(14) of PREVIOUS DAY HIGH   ->  short  (buy PE)
```

That is the whole entry rule. No HTF bias, no regime gate, no RSI, no
BOS/CHoCH, no FVG, no Order Block, no sweep-window, no price-action trigger,
no R:R gate.

### Causal availability

| Input | Available at bar *i*? | How |
|---|---|---|
| Previous day high / low | **Yes** | Completed prior session; constant through the day |
| ATR(14) | **Yes** | Closed bars up to *i* |
| Close | **Yes** | Bar *i*'s close |

No SMC object, no confirmation delay, no lifecycle gating is required —
which is precisely why it is early. The entire `smc_lifecycle` /
`SmcView` apparatus built in Phase 7 is **not needed by this signal**. It
remains valuable for the chart and research surfaces and should stay.

### Parameters

| Parameter | Value | Status |
|---|---|---|
| Proximity band | 0.25 × ATR(14) | **Pre-declared.** Robustness profile measured at 0.10 / 0.25 / 0.50 / 1.00 ATR: +0.250 / +0.229 / +0.105 / +0.015 — monotone decay, no tuned cliff |
| ATR length | 14 | Inherited house default, not swept |
| Level source | previous completed session H/L | Adversarially confirmed as specific (§4) |

**Exactly one parameter.** That is deliberate: Phase 8 and Phase 9 both showed
that additional conditions in this codebase cost more out of sample than they
contribute.

---

## 3. Evidence

| Window | Instrument | n | eff | Δ vs baseline | same-day null *p* |
|---|---|---|---|---|---|
| DEV 2024-01→2025-06 | NIFTY | 598 | 245 | +0.250 | <0.0001 |
| VAL 2025-07→2026-03 | NIFTY | 365 | 168 | +0.143 | 0.0023 |
| **FRESH** 2026-04→2026-09 | **SENSEX** | 310 | 110 | **+0.501** | **0.0003** |
| **FRESH** 2026-06→2026-09 | **BANKNIFTY** | 152 | 62 | **+0.382** | **<0.0001** |
| contaminated 2026-04→2026-09 | NIFTY | 270 | 107 | +0.302 | 0.087 |

Bonferroni ×38 (all Phase 8 + Phase 9 comparisons): SENSEX p = 0.011,
BANKNIFTY p < 0.004. **Both survive.**

This is the only rule found in this repository that beats the
same-day-same-direction permutation null. Every movement-triggered
architecture — including all five existing strategies measured for
calibration — fails it.

---

## 4. Why it is believed (adversarial profile)

| Control | Result | Reading |
|---|---|---|
| Direction inverted | +0.229 → **−0.192** | clean sign flip |
| PDH/PDL shuffled to other days | −0.080 / −0.084 | the specific day's levels matter |
| Random level from same-day range | −0.047 / −0.008 | not "near any level" |
| Session H/L substituted | −0.006 | not any structural level |
| EQH/EQL pools substituted | −0.014 | specifically previous-day |
| Band 0.10 → 1.00 ATR | +0.250 → +0.015 | graceful, not a cliff |
| Trending / ranging | +0.228 / +0.228 | regime-independent |
| Entry delay +1/+2/+3 bars | +0.191 / +0.196 / +0.178 (VAL) | survives execution delay |

---

## 5. Option translation — NIFTY only

Using measured constants (premium % of spot, delta, spread, theta per DTE
regime). IV and vega are **not modelled**; no historical option quotes exist.

| Hold | Excursion asymmetry | Friction | **Net** |
|---|---|---|---|
| 30 min | +3.4 pts | 2.4 | **+1.0** |
| 60 min | +6.7 | 4.3 | **+2.3** |
| **120 min** | **+10.9** | **8.3** | **+2.6** |
| 240 min | +12.9 | 16.2 | **−3.3** |

**Indicated hold window: 30–120 minutes.** Beyond ~2 hours theta overtakes the
edge.

- **BANKNIFTY: net negative at every horizon** (−8 to −49). Strong underlying
  signal, wrong option vehicle — premium 1.38 % of spot against delta 0.376.
- **SENSEX: unassessable.** BSE chain theta has never been measured. Do not
  substitute NIFTY's.

**Recommended instrument scope for any future work: NIFTY only.**

---

## 6. What is NOT specified, and must be before this is a strategy

1. **Exit rule.** None exists. The +2.6 points is an excursion asymmetry, not
   realised P&L. Phase 9 was correctly forbidden from tuning exits.
2. **Signal selection.** The rule fires ~2.1×/day. A book taking one or two
   positions must choose which; that choice is untested and could consume the
   entire edge.
3. **Volatility.** No IV or vega term. A vol crush erases the margin.
4. **Contract selection.** Strike, expiry and DTE regime materially change
   friction (the 30-min net is +1.0 at DTE≤1 versus +0.3 at DTE 8–14).
5. **Interaction with the existing risk and exit infrastructure.**

---

## 7. If implementation is ever approved

Isolated inside `trading_bot/strategies/rsi_smc_options_buyer/` as an
additional, **off-by-default** signal module. Specifically:

- Reuse `levels.compute_daily_levels()` (already causal and tested) and
  `shared.indicators.atr`.
- Do **not** call `structure.build()` — this signal needs no SMC object, and
  avoiding it removes the 88 ms cache-miss cost entirely.
- Keep the causal/analytical split, the lifecycle model and all 191 existing
  tests. They remain correct and are what makes the chart and research
  surfaces trustworthy.
- Add a config flag defaulting to OFF, exactly as `use_ob_trigger` does.
- No change to `active_strategy`, `main.py`, or any shared module.

**None of that should happen until §6 is answered.**

---

## 8. Honest summary

A one-parameter mean-reversion signal at the previous day's extremes
outperformed a nine-condition SMC architecture on every out-of-sample measure
tried, and is the only rule in this repository to beat the correct
permutation null.

It is also a well-known effect, it is not RSI + SMC, and it has no exit. It
should be treated as a promising **entry primitive** requiring full validation
— not as a strategy, and not as vindication of the Phase 7 design.
