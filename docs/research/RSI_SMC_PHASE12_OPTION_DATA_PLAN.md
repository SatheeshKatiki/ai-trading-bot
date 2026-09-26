# Phase 12 — Observed Option Data: audit, schema and collection infrastructure

**Status:** research infrastructure only. Production plane untouched.
`active_strategy` remains `ema9_rsi_momentum`. No live config key, no paper
trading, no orders, no broker call made during this phase. **FINNIFTY remains
sealed.**

**Decision: DATA COLLECTION READY**

---

## 1. Standing research conclusion (§1)

Recorded unchanged, and not re-litigated in this phase:

| Finding | Status |
|---|---|
| Underlying prior-day-extreme effect | **RESEARCH-SUPPORTED** |
| 5-minute underlying magnitude | ~**+2 points/trade** realized, depending on split and exit family |
| Long-premium options implementation | **NOT VALIDATED — NO-GO** |
| Synthetic option history from `api_bridge.py` | **NOT ACCEPTABLE as historical evidence** |
| Real historical option market data | **REQUIRED, and absent** |

Phase 12 changed no part of the signal (§20) and reopened no discarded
hypothesis (§21). It is data infrastructure.

---

## 2. Option-data audit (§2) — verified by data flow, not by comments

Every broker and every persistence path was traced.

| Field | Available | Historical | Real | Granularity | Source |
|---|---|---|---|---|---|
| Spot OHLC | **Yes** | **Yes** | **Yes** | 1/3/5/15 min | `data/*.csv`, `broker.get_historical_data` |
| Option OHLC | Yes (live only) | **No** | **No** | snapshot | `api_bridge._fetch_real_option_chain` → Fyers `options-chain-v3`; **history route returns Black-Scholes from spot** |
| Bid | Yes (live only) | **No** | Yes | snapshot | chain `bid`; `MarketQuote.bid` |
| Ask | Yes (live only) | **No** | Yes | snapshot | chain `ask`; `MarketQuote.ask` |
| Volume | Yes (live only) | **No** | Yes | snapshot | chain `volume` |
| Open Interest | Yes (live only) | **No** | Yes | snapshot | chain `oi`, `oich` |
| Implied Volatility | Yes (live only) | **No** | **Derived** | snapshot | `_implied_vol()` solves it from the real premium |
| Strike | Yes | Yes | Yes | — | chain, `select_option()` |
| Expiry | Yes | Yes | Yes | — | chain `expiryData`, `_next_expiry()` |
| Greeks | Yes (live only) | **No** | **Derived** | snapshot | `_greeks_from_iv()` |

### The three findings that matter

1. **The history endpoint does not return option data.** Request any option
   symbol from `/api/history` and `api_bridge.py:2441` fetches the *underlying*
   and hands it to `generate_option_history_from_spot()`
   (`api_bridge.py:2149`), which prices every candle with Black-Scholes at
   **hardcoded `sigma = 0.18`, `T = 0.02`, `r = 0.07`** — regardless of the
   contract, its expiry, or the prevailing volatility. It is a deterministic
   transform of spot wearing an option symbol.

2. **Real, complete option quotes exist — and are thrown away.** One call site,
   `_fetch_real_option_chain` (`api_bridge.py:4085`), returns genuine bid, ask,
   OI, OI-change, volume, traded premium, the real expiry series and India VIX.
   Every consumer reads the HTTP response in memory. **Nothing persists it.**

3. **Persisted option records carry almost nothing.** `state.db.trades` holds
   `(symbol, side, price, time, qty)` — last price only, executed trades only.
   `paper_obs_logs/` holds 13 real sessions with `entry_premium`,
   `exit_premium`, `opt_delta`, `strike`, `entry_spot` — and **no bid, ask, IV,
   OI, volume or expiry**, for a different strategy's entries.

**Conclusion:** everything needed to answer the options question already flows
through this process every trading day. It is simply not written down. That is
a recorder problem, not a data-availability problem — which is why this phase
ends READY rather than BLOCKED.

---

## 3. What was built

`trading-system/research/option_recorder/` — isolated, importing no broker, no
risk manager, no exit engine and no order type. Tests assert both that and that
production never imports it.

| Module | Role |
|---|---|
| `schema.py` | canonical immutable record, per-field provenance, quality classification, `REQUIRE_OBSERVED_OPTION_DATA` |
| `store.py` | append-only RAW/NORMALIZED/DERIVED/EVENTS store, manifests, integrity verification |
| `collect.py` | the snapshot loop: chain + underlying + frozen signal state, aligned |
| `qa.py` | daily completeness and integrity report |
| `README.md` | how to run it and what it guarantees |

### Canonical record (§4, §5)

`OptionQuote` carries identity (`event_time`, `event_time_utc`,
`session_date`, `available_at`, `underlying`, `option_symbol`, `expiry`,
`strike`, `option_type`), observed market state (`underlying_price`,
`last_price`, `bid`, `ask`, `volume`, `open_interest`, `oi_change`), derived
values (`implied_volatility`, Greeks), expiry structure (`dte`,
`expiry_class`), lineage (`source`, `source_endpoint`, `retrieved_at`,
`original_symbol`, `schema_version`) and quality (`quality`,
`quality_reasons`).

`FIELD_PROVENANCE` marks each field **OBSERVED / DERIVED / INFERRED /
UNAVAILABLE**. IV and the Greeks are DERIVED, not OBSERVED — the broker
publishes neither. Recording them as observed would be a false claim; a test
pins it.

### Quality gates (§9)

`VALID` / `STALE` / `INVALID` / `MISSING` / `SYNTHETIC`, applied per leg.
`SYNTHETIC` **wins over every other verdict** — a modelled premium is not an
observation however well-formed it looks. A zero-bid or zero-ask quote is
`INVALID` rather than passing with a last-price substitute, because §24 forbids
that substitution and such a quote cannot support execution analysis.

### Storage (§14, §32)

```
research_data/
  raw/<instrument>/<session>/chain.jsonl          broker payloads, verbatim
  normalized/<instrument>/<session>/quotes.jsonl  OptionQuote
  derived/<instrument>/<session>/underlying.jsonl UnderlyingSnapshot
  events/<instrument>/<session>/signals.jsonl     SignalEvent
  manifest/<instrument>/<session>.json            SHA-256 + line counts
```

Append-only by construction: writers open in `"a"` mode, and the class exposes
no update, delete, overwrite or truncate method — asserted by test. RAW is
written once and never re-derived. `verify_partition()` re-hashes every file
against the manifest, so a rewritten dataset is detectable; a test proves it
catches tampering. A process killed mid-write loses at most a partial final
line, which the reader skips.

### Causal integrity (§16)

`event_time` is when the market state existed (the close of the last completed
bar). `available_at` is when this process could first have known it. They are
separate fields and are genuinely different values — collapsing them would
quietly hand a future researcher a bar's close at the bar's open.

---

## 4. Collection design

**Frequency (§6): 5 minutes.** The frozen signal is evaluated on 5-minute
closes, so a finer cadence records states no decision could ever have been
taken at. 1-minute would multiply storage fivefold for no research gain at the
frozen signal's resolution. Event-driven capture is unnecessary because the
5-minute grid already contains every decision point.

**The whole chain, not the chosen contract (§7, §11, §13).** Every strike the
broker returns (`strikecount: 20` → roughly ±20 strikes) and both sides, on
every snapshot, whether or not the signal fired. Storing only the contract a
later backtest likes is precisely the selection bias that would make the
eventual contract-selection study worthless.

**Aligned underlying state (§8).** Each snapshot writes an
`UnderlyingSnapshot` with price, PDH, PDL, ATR and the bar OHLC, so a future
researcher can reconstruct exactly what was knowable at that moment.

**Signal events (§10).** When the frozen rule is in band, a `SignalEvent` is
appended carrying `setup_id`, direction, level, distance, ATR and band. The
`setup_id` is the Phase 10 DAY_SIDE identity — `instrument:date:LONG|SHORT` —
so repeated snapshots of one live setup share an id and **cannot later be
counted as independent observations**. That was the single largest measurement
error of Phase 10 and it is designed out here rather than corrected later.

**Recording an event places nothing.** The collector imports no execution code.

---

## 5. Verification

29 tests, all passing, in `test_option_recorder.py`:

| Area | Covered |
|---|---|
| Quote validation | valid two-sided, crossed, one-sided, negative, non-finite |
| Stale detection | age beyond the freshness bound |
| Synthetic separation | SYNTHETIC beats every other verdict, including corrupt synthetic |
| Strike / expiry / CE-PE mapping | every leg mapped; DTE and weekly/monthly classification |
| Timestamps | IST + UTC parseable, session date, `available_at` present and distinct |
| Execution reconstruction | BUY→ask, SELL→bid, `None` when one-sided (no last-price fallback) |
| Append-only | existing bytes preserved verbatim; no update/delete method exists |
| Crash tolerance | truncated final line skipped, not fatal |
| Integrity | manifest written; tampering detected |
| Provenance | observed fields OBSERVED; IV/Greeks DERIVED |
| Research guard | `REQUIRE_OBSERVED_OPTION_DATA` is on |
| Isolation | recorder imports no execution code (AST-checked); production never imports the recorder |
| FINNIFTY | not a default instrument |

**End-to-end pipeline proof** (stubbed chain, no market, no broker): one
snapshot wrote 1 RAW payload, 6 normalized quotes, 1 underlying row and — with
price placed in band — 1 signal event with `setup_id NIFTY:2026-10-01:LONG`,
distance 0.50 against a 9.1-point band, `event_time` 2026-10-01T12:25 versus
`available_at` at collection time. Manifest written, integrity verified. A
chain flagged `synthetic: true` produced 6 SYNTHETIC legs and the QA report
correctly marked the session **unusable**.

Full suite: **1,643 passed, 1 skipped, 2 xfailed** (was 1,614/1/2; +29 new,
zero regressions).

---

## 6. Answers to the required questions (§36)

1. **What real option data is available?** Live only: bid, ask, last price,
   volume, OI, OI-change, strike, expiry, real expiry series, India VIX — from
   one endpoint, never persisted. Historically: **none**.
2. **What fields are missing?** All of them, historically. IV and Greeks are
   not published even live; they are solved from the real premium.
3. **What must be accumulated?** The full chain (every strike, both sides, the
   near expiries) at 5-minute cadence during market hours, plus the aligned
   underlying state and the frozen signal state.
4. **How are raw observations preserved?** Verbatim append-only JSONL,
   per-record checksums, per-session SHA-256 manifests, verification that
   detects rewriting. No update or delete path exists.
5. **How is option data aligned with signals?** Every snapshot writes chain,
   underlying state and (when in band) signal event with the same timestamps
   and session key, joinable on `(instrument, session_date, event_time)`.
6. **How is bid/ask execution reconstructed?** `executable_buy()` returns the
   **ask**, `executable_sell()` the **bid**, and **`None`** when there is no
   two-sided quote. It never substitutes the last traded price.
7. **How are IV/theta/vega handled?** Stored as DERIVED with the raw inputs
   kept, so any later derivation is reproducible and auditable. Never labelled
   observed.
8. **How are gaps detected?** `qa.py` reports snapshots against the 76 expected
   per session, completeness %, valid %, synthetic count, distinct strikes and
   expiries, inter-snapshot gaps over 7.5 minutes, and manifest integrity, with
   a single `usable` verdict per session.
9. **How is future contamination prevented?** `event_time` ≠ `available_at`;
   the signal is computed on the last **completed** bar with the forming bar
   dropped; the store is append-only so a later run cannot retroactively
   improve an earlier record.
10. **How much accumulation is required?** See §7.
11. **What validation protocol?** See §8.

---

## 7. How much data is needed before the options hypothesis can be tested

Derived from what the earlier phases actually needed, not guessed:

| Requirement | Basis |
|---|---|
| **≥ 200 deduplicated setups** | the Phase 9 pre-registration bar |
| **≥ 2 independent windows** (develop + validate) | Phase 8/9 showed single-window results reverse |
| **≥ 1 sealed holdout** | every phase where one was skipped produced a result that later collapsed |

The frozen rule produces ~**0.66 day-side setups per instrument per day**
(Phase 10, measured across five windows). So per instrument:

| Purpose | Setups | Trading days | Calendar |
|---|---|---|---|
| Develop | 200 | ~300 | ~14 months |
| Validate | 100 | ~150 | ~7 months |
| Sealed holdout | 100 | ~150 | ~7 months |
| **Total, one instrument** | **400** | **~600** | **~28 months** |

Collecting NIFTY, BANKNIFTY and SENSEX in parallel gives ~2 setups/day across
the three, but they are **not independent** — they share market regime — so the
calendar requirement does not divide by three. A defensible first checkpoint is
**~6 months (≈125 sessions, ≈80 setups/instrument)**: enough to measure spread,
IV behaviour and realized premium paths, and to settle the two open
instrument-specific questions below, but **not** enough to declare an edge.

**This is the honest cost of the answer.** A shorter run will produce numbers;
it will not produce evidence.

### The two questions a 6-month run already settles

- **SENSEX theta** (§29). One unmeasured constant currently blocks an entire
  instrument whose Phase 11 realized returns were positive at 60- and
  120-minute holds. A few weeks of real BSE chain snapshots measures it. Do not
  substitute NIFTY's.
- **BANKNIFTY premium structure** (§30). Phase 11 showed friction per
  underlying point is **4.8× NIFTY** — premium 1.38 % of spot at delta 0.376 —
  which fully explains "strong underlying, negative option economics" without
  invoking spread or liquidity. Real quotes confirm or refute that from
  observed spread and IV rather than from a modelled constant.

---

## 8. The future validation protocol (§22)

```
RAW OBSERVED DATA          append-only, checksummed, never mutated
        |
   DATA QA                 qa.py; any SYNTHETIC or <80% complete session excluded
        |
 FROZEN DATASET            manifest-verified, copied, version-pinned, read-only
        |
SIGNAL RECONSTRUCTION      frozen Phase 10 rule, DAY_SIDE dedup, Policy A
        |                  filtered on available_at, never event_time
CONTRACT SELECTION         pre-declared families only (ATM / near-ITM /
        |                  near-OTM x near / next expiry) -- sec23, not optimised
REAL EXECUTION MODEL       BUY at ask, SELL at bid, one-sided quotes excluded
        |                  entry delay +1 bar; spread and slippage measured,
        |                  not assumed
 REAL OPTION P&L           observed premiums only; no Black-Scholes anywhere
        |
  OOS VALIDATION           pre-declared split; holdout opened once
        |
ADVERSARIAL VALIDATION     inverted direction, shuffled levels, random times,
                           random contracts, band sweep
```

Every step must be reproducible from stored observations alone. The harness
must assert `REQUIRE_OBSERVED_OPTION_DATA` and **fail closed** if observed data
is absent, rather than silently falling back to the model.

---

## 9. Limitations, stated plainly (§35)

- **No backfill is possible.** Fyers serves no history for expired option
  symbols; a live weekly carries 6–9 days. The only route is forward
  accumulation, and the calendar in §7 is therefore a floor, not an estimate.
- **The collector needs `api_bridge` running with a valid broker session.**
  With it down it logs the failure and records nothing — verified. It does not
  fabricate a fallback.
- **No live broker call was made in this phase.** The audit is from code and
  stored artefacts. The first real capture will confirm the chain's field
  completeness in practice.
- **IV and Greeks remain derived**, not observed, whatever volume of data
  accumulates. That is a property of the data source, not of the recorder.
- **Not scheduled.** The collector is deliberately not wired into
  `auto_daily_session.py`; starting it is a manual decision.

---

## 10. Decision (§37)

### **DATA COLLECTION READY**

The infrastructure exists, is isolated, is tested (29 tests, full suite
1,643 passed), is append-only and integrity-verified, and has been proven
end-to-end on a stubbed chain including the synthetic-rejection path.

Not `DATA PIPELINE BLOCKED`: the required fields **are** obtainable from the
existing broker session — they were simply never persisted. Nothing external
needs to change for collection to begin.

**The strategy remains NO-GO.** Nothing here is a paper-validation candidate
and nothing is production-ready. The next legitimate question stays open until
real data exists to answer it:

> Given real observed option data at the exact signal timestamps, does the
> prior-day-extreme underlying edge translate into positive executable option
> economics after spread, slippage, IV, theta, moneyness and holding time?

**To begin accumulating:** start `api_bridge`, then
`python -m research.option_recorder.collect --interval 300`, and check
`python -m research.option_recorder.qa` at the end of each session.
