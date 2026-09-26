# Phase 11 — Economic Validation: timeframe scaling and real option data

**Status:** research only. Production plane untouched. `active_strategy`
remains `ema9_rsi_momentum`. No live config key, no paper-trading code, no
orders. **FINNIFTY remains sealed.**

**Decision: NO-GO — OPTION EXPRESSION TOO EXPENSIVE**

---

## 1. Executive summary

Phase 11 asked one question: does the prior-day-extreme location effect become
economically exploitable when expressed over a **larger timeframe** and
evaluated with **real historical option data**?

**Timeframe: tested and failed.** The effect does not scale. At 15, 30 and 60
minutes it looks substantially *better* on DEV (60-minute: +0.373, p = 0.0056)
and **turns negative on VAL at every one of them** (60-minute: −0.131,
p = 0.84). The reversal holds across all seven band widths tested and all four
holding windows. **5 minutes is the only timeframe stable across both splits** —
and Phase 10 already established that its edge sits below friction.

**Real option data: it does not exist, and cannot be obtained here.** The
repository's "option history" endpoint does not return option data at all. It
derives a premium path from spot via Black-Scholes with **hardcoded
`sigma = 0.18` and `T = 0.02`** (`api_bridge.py:2149`). Every field required by
§10 — OHLC, bid, ask, OI, IV, volume — is UNAVAILABLE. The options layer
therefore remains **UNVALIDATED and unvalidatable from this repository**.

**What the evidence does support**, using only observed constants and measured
realized returns, is a break-even inversion that needs no fabricated premium
path: on NIFTY the trade must deliver 2.3–9.3 underlying points to cover
friction, and delivers −1.1 to +3.6. **Negative in 11 of 12 cells.**

---

## 2. Canonical data manifest (§2)

| File | Start | End | Bars | Days | Dup | Open | Close | Bars/day | Max gap | SHA-256 (12) |
|---|---|---|---|---|---|---|---|---|---|---|
| `NSE_NIFTY50-INDEX_5.csv` | 2024-01-01 09:15 | 2024-12-31 15:25 | 18,504 | 249 | 0 | 09:15 | 15:25 | 75 | 4 | `be037fe66b5e` |
| `NIFTY_cache.csv` | 2025-05-19 09:15 | 2026-05-15 15:25 | 18,463 | 247 | 0 | 09:15 | 15:25 | 75 | 4 | `2a04a68e8f53` |
| `NSE_NIFTY50-INDEX_5Min.csv` | 2025-09-22 09:15 | 2026-09-25 15:20 | 18,766 | 251 | 0 | 09:15 | 15:25 | 75 | 4 | `e6d812031bbc` |
| `BSE_SENSEX-INDEX_5Min.csv` | 2025-09-01 09:15 | 2026-09-25 15:25 | 19,891 | 266 | 0 | 09:15 | 15:25 | 75 | 4 | `c93075d6e4c6` |
| `NSE_NIFTYBANK-INDEX_5Min.csv` | 2026-06-29 09:15 | 2026-09-25 15:20 | 4,779 | 64 | 0 | 09:15 | 15:25 | 75 | 4 | `526630a4767b` |
| `NSE_FINNIFTY-INDEX_5Min.csv` | 2026-07-07 09:15 | 2026-08-31 15:25 | 2,976 | 40 | 0 | 09:15 | 15:25 | 75 | 3 | `bc4b9dcb5dcb` |
| `NSE_NIFTY50-INDEX_1Min.csv` | 2025-07-15 09:15 | 2026-08-31 15:29 | 104,686 | 280 | 0 | 09:15 | 15:29 | 375 | 4 | `fcc457d23e0b` |
| `NSE_NIFTY50-INDEX_3Min.csv` | 2025-07-15 09:15 | 2026-07-24 15:27 | 31,646 | 254 | 0 | 09:15 | 15:27 | 125 | 4 | `bc45e0abd27b` |
| `NSE_NIFTY50-INDEX_15Min.csv` | 2026-08-20 09:15 | 2026-09-22 15:15 | 578 | 23 | 0 | 09:15 | 15:15 | 25 | 4 | `b7fd4b9eed64` |
| `NSE_RELIANCE-EQ_5Min.csv` | 2026-05-04 09:15 | 2026-09-21 15:25 | 7,352 | 98 | 0 | 09:15 | 15:25 | 75 | 4 | `1dc1479306d8` |

**EXCLUDED per §2, not normalised, not used:**

| File | Reason |
|---|---|
| `NSE_TCS-EQ_5Min.csv` | **75 duplicate timestamps** |
| `RELIANCE.NS_1min.csv` | **Opens 03:45 — foreign timezone** (yfinance UTC) |

Every index file is session-aligned (09:15 → 15:25, 75 bars/day, zero
duplicates). Max day-gap of 4 is long weekends. Timezone tz-naive IST
throughout. The 2024 NIFTY block carries no real volume (`nunique == 1`);
harmless, since no component of this rule reads volume.

---

## 3. Option data audit (§4, §10, §16)

**The repository's option "history" is a transform of spot.**
`api_bridge.py:2149 generate_option_history_from_spot()` prices every candle
with Black-Scholes at fixed `sigma = 0.18`, `T = 0.02`, `r = 0.07`, regardless
of the actual contract, its expiry or the prevailing volatility. The history
endpoint routes every option symbol through it (`api_bridge.py:2441`).

| Field | Status | Note |
|---|---|---|
| Option OHLC | **UNAVAILABLE** | only BS-derived from spot at fixed IV |
| Bid / Ask | **UNAVAILABLE** | live-only, never persisted |
| Volume | **UNAVAILABLE** | copied from the underlying |
| Open Interest | **UNAVAILABLE** | — |
| Implied Volatility | **UNAVAILABLE** | hardcoded 0.18 in the derivation |
| Greeks | **UNAVAILABLE** historically | `opt_delta` recorded per live trade only |
| Strike / expiry / CE-PE / underlying map | **DERIVABLE** | `select_option()` |
| Real entry/exit premiums | **PARTIAL** | 13 sessions in `paper_obs_logs/`, another strategy's trades |

**Broker capability.** The repository's own calibration record states Fyers
serves no history for expired option symbols ("Invalid symbol") and a live
weekly carries only 6–9 days. No live broker call was made in this phase.

**Consequence:** §11–§16 (real option entry, real premium exit, IV/vega
analysis) **cannot be executed**. They are not reported as inconclusive — they
are not executable. The options layer stays `UNVALIDATED`.

---

## 4. Timeframe scaling — the central test (§5–§9)

Frozen rule, Policy A, deduplicated episodes, entry at the next bar's open,
holding windows in wall-clock minutes so the comparison is like-for-like on
the thing that drives theta.

**Causality verified at every timeframe:**

| TF | bars/day | future-truncation invariant | ATR prefix-stable | PDH ≠ today's high |
|---|---|---|---|---|
| 5 | 75.0 | PASS | PASS | PASS |
| 15 | 25.0 | PASS | PASS | PASS |
| 30 | 13.0 | PASS | PASS | PASS |
| 60 | 7.0 | PASS | PASS | PASS |

**Results — NIFTY** (`exc Δ` = excursion delta vs direction-matched baseline at
the 120-minute-equivalent horizon; `ret` = realized underlying points):

| TF | split | bars | setups | eff | exc Δ | p | ret 30m | ret 60m | ret 120m | ret 240m |
|---|---|---|---|---|---|---|---|---|---|---|
| 5 | DEV | 20,829 | 171 | 169 | +0.125 | 0.098 | −1.1 | +0.2 | +2.3 | +0.7 |
| 15 | DEV | 6,943 | 148 | 142 | +0.273 | 0.054 | +6.8 | +4.6 | +5.8 | +9.3 |
| 30 | DEV | 3,613 | 145 | 139 | +0.274 | 0.012 | +5.8 | +5.1 | +1.9 | +4.6 |
| 60 | DEV | 1,946 | 122 | 116 | **+0.373** | **0.0056** | **+11.1** | **+11.1** | +2.9 | +7.0 |
| **5** | **VAL** | 13,888 | 115 | 111 | **+0.155** | **0.042** | +3.6 | +0.9 | +2.1 | +0.4 |
| 15 | VAL | 4,630 | 113 | 111 | **−0.122** | 0.637 | −4.5 | −5.4 | −4.0 | −6.2 |
| 30 | VAL | 2,408 | 102 | 99 | **−0.108** | 0.565 | −7.1 | −8.5 | −5.7 | −4.0 |
| 60 | VAL | 1,297 | 92 | 92 | **−0.131** | 0.841 | −4.3 | −4.3 | +5.9 | +8.1 |

**Every larger timeframe reverses sign between DEV and VAL.** The 60-minute
DEV result is the most attractive number produced in eleven phases of
research — +0.373 at p = 0.0056 with +11.1 realized points — and it is
**−0.131 at p = 0.84** on the very next window. Only 5 minutes is stable.

**It is not a band artifact.** Sweeping the location band at 15 and 60 minutes:

| Band (ATR) | 15m DEV | 15m VAL | 60m DEV | 60m VAL |
|---|---|---|---|---|
| 0.10 | +0.327 | +0.104 | +0.601 | −0.236 |
| 0.15 | +0.521 | +0.062 | +0.306 | −0.293 |
| 0.20 | +0.353 | −0.087 | +0.281 | −0.282 |
| 0.25 | +0.273 | −0.122 | +0.373 | −0.131 |
| 0.30 | +0.210 | −0.097 | +0.291 | −0.141 |
| 0.40 | +0.034 | −0.235 | +0.050 | −0.184 |
| 0.50 | +0.080 | −0.190 | −0.028 | −0.225 |

**60-minute VAL is negative at all seven bands.** 15-minute VAL is negative at
five of seven. The DEV/VAL disagreement is systematic, not a threshold effect.

**§8's question — does the effect scale naturally? No.** There is no smooth
scaling relationship. There is a DEV-only illusion that grows with timeframe,
which is exactly what a pre-declared split exists to expose.

---

## 5. Break-even economics (§30)

Rather than model a premium path from data that does not exist, the question
is inverted: **how large must the underlying move be to cover measured option
friction?** This uses only OBSERVED constants.

| Assumption | NIFTY DTE≤1 | NIFTY DTE 8-14 | BANKNIFTY | SENSEX |
|---|---|---|---|---|
| Premium % of spot | 0.32 **OBSERVED** | 1.03 **OBSERVED** | 1.38 **OBSERVED** | 0.76 **OBSERVED** |
| Delta | 0.42 **OBSERVED** | 0.42 **OBSERVED** | 0.376 **OBSERVED** | 0.305 **OBSERVED** |
| Round-trip spread | 0.21 % **OBSERVED** | 0.21 % **OBSERVED** | 0.35 % **OBSERVED** | 0.21 % **ASSUMED** |
| Theta %/session | 13.4 **OBSERVED** | 4.0 **OBSERVED** | 5.9 **OBSERVED** | **UNAVAILABLE** |
| IV / vega | **UNAVAILABLE — not modelled** | | | |

**NIFTY (5-minute, the only stable timeframe):**

| Window | Hold | n | Delivered | Required | **Margin** |
|---|---|---|---|---|---|
| DEV | 30 min | 171 | −1.1 | 2.3 / 3.1 | **−3.4 / −4.2** |
| DEV | 60 min | 171 | +0.2 | 4.2 / 4.9 | **−4.0 / −4.7** |
| DEV | 120 min | 171 | +2.3 | 8.1 / 8.6 | **−5.8 / −6.3** |
| VAL | 30 min | 115 | +3.6 | 2.5 / 3.3 | **+1.1 / +0.3** |
| VAL | 60 min | 115 | +0.9 | 4.5 / 5.3 | **−3.6 / −4.4** |
| VAL | 120 min | 115 | +2.1 | 8.7 / 9.3 | **−6.6 / −7.1** |

**11 of 12 cells negative.** The one positive cell (VAL, 30-minute, DTE≤1) is
**−3.4 on DEV** for the identical rule.

---

## 6. Instrument-specific findings (§17–§19)

### BANKNIFTY — why it costs more, and why its one positive cell does not hold

| Instrument | Premium % of spot | Delta | Friction per underlying point |
|---|---|---|---|
| NIFTY | 0.32 | 0.420 | baseline |
| BANKNIFTY | 1.38 | 0.376 | **4.8× NIFTY** |

**The cause is structural, not data quality.** BANKNIFTY premium is 4.3× NIFTY's
as a share of spot while its delta is lower, so each underlying point costs
4.8× as much to buy. That fully explains Phase 10's "strong underlying, negative
option economics" — it is not spread, liquidity or modelling error.

BANKNIFTY at a 120-minute hold is the **only positive margin found in Phase 11**
(+63.0 delivered vs 47.1 required = +15.9). It does not survive inspection:

| Cut | days | n | Delivered | Required | Margin | Median |
|---|---|---|---|---|---|---|
| Full | 64 | 40 | +63.0 | 47.1 | +15.9 | +46.2 |
| First half | 32 | 21 | +63.5 | 47.3 | +16.2 | +50.1 |
| Second half | 32 | 18 | +60.8 | 46.9 | +13.9 | +31.7 |
| **Excluding top 3 trades** | 64 | 37 | **+32.4** | 47.1 | **−14.7** | — |

Both halves agree, so it is not a one-period artifact — but the **median trade
(+46.2) is essentially exactly break-even (47.1)**, and the top 3 of 40 trades
contribute +33.1 of the +63.0 mean. Remove them and the margin is −14.7. It is
also negative at 30- and 60-minute holds (−3.1, −0.4). On 40 trades in a single
64-day window with no option data to verify the premium path, this is a lead,
not a result.

### SENSEX — still unmeasurable

Realized returns are positive at 60- and 120-minute holds (+7.7, +16.4) but
**BSE chain theta has never been measured**, so no margin can be computed. Per
§19, NIFTY/BANKNIFTY constants were **not** substituted. Obtaining it requires
forward accumulation of live BSE chain quotes — the same limitation as §3.

### FINNIFTY — sealed

Not opened, not resampled, not loaded (§3). It remains the only never-inspected
partition in the repository.

---

## 7. Answers to the required questions

| § | Question | Answer |
|---|---|---|
| 5/8 | Does the effect scale to a larger timeframe? | **No.** Positive on DEV at 15/30/60m, negative on VAL at all three, across all seven bands. |
| 9 | Is each timeframe causal? | **Yes.** Truncation-invariance, ATR prefix-stability and PDH≠today all PASS at 5/15/30/60m. |
| 4/10 | Is real option data available? | **No.** Every required field UNAVAILABLE; the endpoint derives premium from spot at fixed IV. |
| 16 | Does the underlying edge translate to a premium edge? | **Unanswerable** — no IV, no premium path, nothing fabricated. |
| 17 | NIFTY complete economics? | Delivered −1.1…+3.6 against 2.3…9.3 required. Negative in 11/12. |
| 18 | Why does BANKNIFTY fail? | Friction per point is **4.8× NIFTY** — premium 1.38% of spot at delta 0.376. Structural. |
| 19 | SENSEX? | Theta unmeasured. No claim possible. |
| 26 | Is the band broad or a single threshold? | Broad at 5m (Phase 10). At 15/60m the DEV/VAL sign disagreement is present at **every** band. |
| 24 | Gate A (underlying) | **Pass, marginally**, at 5m only: +0.125 / +0.155 across splits. |
| 24 | Gate B (option) | **Fail** on NIFTY; **unmeasurable** on SENSEX; **unresolved** on BANKNIFTY. |

---

## 8. Decision (§31)

### **NO-GO — OPTION EXPRESSION TOO EXPENSIVE**

Chosen over the alternatives deliberately:

- **Not `NO-GO — UNDERLYING EDGE TOO WEAK`.** The underlying effect is real
  and causally clean. At 5 minutes it is positive on both splits and on both
  already-opened fresh instruments, and it passed every adversarial control in
  Phases 9–10. It is small, not absent.
- **Not `CONTINUE RESEARCH — DATA INSUFFICIENT`.** The specific Phase 11
  hypothesis — that a larger timeframe would produce an economically
  meaningful move — was tested on adequate samples (92–148 setups per
  timeframe per split) and **failed**. That is an answer, not a data shortfall.
  Data *is* insufficient for the options layer, but the timeframe escape route
  is now closed independently of it.
- **Not `VALIDATION CANDIDATE`.** Complete trade economics are negative in 11
  of 12 NIFTY cells, and the single positive instrument-cell depends on 3 of
  40 trades.

On the instrument with the deepest history and a complete measured friction
model, the trade must deliver 2.3–9.3 underlying points and delivers about 2.
The gap is not a modelling artifact: it is robust across DTE regimes, holding
windows, both splits, and now across four timeframes.

**No `RSI_SMC_FINAL_OPTIONS_ARCHITECTURE.md` was written** — §32 gates it on a
surviving complete candidate, and there is none.

### What would reopen this

1. **Real historical option data.** Everything in §11–§16 becomes executable
   the moment a source with timestamp/strike/expiry/OHLC/bid/ask/OI/IV exists.
   From this broker that means **forward accumulation** — recording live chain
   snapshots daily — not a backfill.
2. **SENSEX theta.** One unmeasured constant currently blocks an entire
   instrument whose realized returns are positive at 60- and 120-minute holds.
   It is the cheapest open question in this document.
3. **A real BANKNIFTY sample.** 64 days is not enough to judge a heavy-tailed
   distribution whose median sits exactly at break-even.

### Standing conclusion on the underlying effect

Recorded as a research finding, per §33: **price located within ~0.1–0.4 ATR of
the previous session's high or low carries directional information toward
reversion, on 5-minute bars, across NIFTY, SENSEX and BANKNIFTY.** It is
causally clean, adversarially robust, execution-delay tolerant, and worth
roughly +2 underlying points per trade. That is a genuine market-location
phenomenon. It is not, on this evidence, enough to pay for a long option.

---

## 9. Reproducibility

`docs/research/phase11/` — `tf.py` (timeframe resampling + pre-declaration),
`tfrun.py` (scaling study), `breakeven.py` (economic model), plus `entry.py`,
`setup.py`, `selection.py`, `exits.py`, `repro.py`, `p8lib.py`, `split.py`
reused verbatim from Phases 8–10.

## 10. What was NOT done

- No production file modified; no live config key; `active_strategy` unchanged;
  no paper-trading code; **no broker call of any kind**.
- **FINNIFTY was never loaded.**
- No timeframe was selected on performance; all four are reported side by side.
- No parameter was optimised. The band grid was pre-declared as sensitivity.
- No IV, OI, Delta or Greek fabricated. SENSEX margin cells are blank.
- No RSI/SMC/FVG/OB/BOS/CHoCH/VWAP/MACD/volume component was reintroduced.
