# Phase 13 — Recorder hardening and validation

**Scope: infrastructure only.** No strategy code, exit logic, contract
selection, signal definition or parameter was changed. `active_strategy`
remains `ema9_rsi_momentum`. The RSI_SMC strategy remains **NO-GO** and
inactive. FINNIFTY remains **sealed**.

**Verdict: `RECORDER READY FOR OBSERVATION`** — with one operational
precondition stated in §8 that the recorder cannot enforce on its own.

---

## 1. Why this phase existed

Phase 12 built a recorder and declared it *data-collection ready*. That
declaration was based on the recorder producing plausible output, not on it
having been attacked. The distinction matters here more than usual:

**The recorder gets exactly one attempt at each trading day.** A defect found
on session 40 does not cost a debugging afternoon, it costs 40 sessions and
two months. The economic question from Phases 8–11 needs ~125 sessions. A
silent corruption discovered at session 100 would push the answer past the
middle of 2027.

So this phase assumed the Phase 12 recorder was broken and tried to prove it.

## 2. Audit: what was actually wrong

Eight failure modes were confirmed empirically against the Phase 12 code —
each one executed and observed, not inferred from reading:

| # | Failure | Evidence | Consequence if left |
|---|---|---|---|
| 1 | **No deduplication** | 3 identical polls → 6 stored rows | One moment votes 3× in any later statistic |
| 2 | **Staleness could never fire** | `classify_quote(age_seconds=None)` hardcoded | A frozen quote reads as a fresh one |
| 3 | **No checkpoint or resume** | no such concept in the store | A restart re-records the morning |
| 4 | **No retry** | single attempt, returns `None` | One network blip = a permanent hole |
| 5 | **No recorder/normalization version** | only `schema_version` | A behaviour change mid-collection becomes untraceable |
| 6 | **No session status** | only a boolean `usable` | "Partly collected" indistinguishable from "fine" |
| 7 | **Buffered writes, no fsync** | no `fsync` in `append` | Power loss silently drops quotes already reported written |
| 8 | **No coverage validation** | stores whatever arrives | A 3-strike chain looks like a 21-strike chain months later |

Every one of these corrupts data **silently**. None would have produced an
error, and all eight would have been invisible in the Phase 12 daily report.

## 3. What was built

### Deduplication with a canonical key (§6)

```
observation_key = underlying | event_time | option_symbol | expiry | strike(2dp) | option_type
```

The key deliberately **excludes price and quality**. A retry that returns a
slightly different premium for the same instant is still that one instant;
keying on price would store both and let a single moment be counted twice.
Strike is formatted to 2dp so `24000` and `24000.0` collide, as they must.

`append_deduped()` skips keys already stored. The key set is rebuilt **from
the stored data itself**, not only from the sidecar index — deleting the
index changes nothing, because the data is the source of truth.

### Staleness, without inventing a timestamp (§7)

`api_bridge._chain_leg` was checked directly: it maps ltp, bid, ask, oi,
volume and nothing temporal. **The broker supplies no per-leg quote
timestamp.** An exchange quote age therefore does not exist, and the recorder
does not manufacture one — `quote_age_seconds` is permanently `None`, and a
test asserts it stays that way.

What *is* observable is whether a contract's quote changed between two of our
own snapshots. `unchanged_for_seconds` is computed from consecutive stored
observations, is reproducible from them, is labelled DERIVED, and drives a
STALE verdict past 600 s. It is kept in a separate field precisely so it can
never be mistaken for an exchange timestamp.

This is the §7 requirement met honestly rather than met nominally.

### Durability and failure handling (§17, §18)

* `append()` flushes and `fsync`s. Without it the recorder could report
  coverage it did not have — worse than a visible gap.
* `_get()` retries 3× with 1 s/3 s backoff, bounded well inside one 5-minute
  interval so a retry can never push a snapshot into the next bar.
* A chain outage is logged, counted, and the session continues.
* Missing underlying history still records the chain.
* A truncated final line from a killed process is skipped, not fatal.

### Checkpoint and resume (§21)

Written atomically (temp file + `os.replace`) after every snapshot. A
half-written checkpoint would be worse than none, because a reader cannot
tell it is truncated. A corrupt checkpoint returns `None` rather than
throwing. On restart the recorder loads the stored keys and re-records
nothing.

### Coverage validation (§10)

A thin chain is **recorded and flagged**, never dropped. Discarding it would
hide the very degradation the flag exists to surface.

### Six-dimension health scorecard (§13, §14)

Coverage · completeness · freshness · validity · integrity · continuity.

`status` is a **floor over the dimensions, not an average** — the composite
score is for ranking sessions at a glance only. A session with 76/76
snapshots, perfect integrity and one synthetic quote scores 0.84 and is still
`UNUSABLE`. A weighted average is exactly how a broken feed passes a health
check.

States: `COMPLETE` / `INCOMPLETE` / `UNUSABLE` / `EMPTY`.

## 4. Two real bugs the tests found

Both were found by tests written against the requirement, not by reading code:

**The QA tool crashed on corrupt data.** A row missing `event_time` raised
`TypeError` inside `session_report`. A QA tool that throws on bad data is a QA
tool that never reports bad data. It now counts malformed rows and marks the
session `UNUSABLE`.

**Nothing verified the recorded bar was in the past.** The recorder trusted
the history endpoint's last closed bar unconditionally. A timezone fault or
bad payload would have written a row whose `available_at` *precedes* its
`event_time` — a look-ahead-shaped record sitting in data intended to prove
the absence of look-ahead. The recorder now refuses a future-dated bar,
logs it, and counts a failure. A visible gap is recoverable; a poisoned row
is not.

## 5. The offline rehearsal (§22)

`research/option_recorder/selftest.py` replays a full 76-snapshot session
through the real `snapshot()`, the real store and the real scorecard, with
only the two fetchers substituted. It injects a broker outage, a thin chain,
frozen quotes, a duplicate poll, a process restart, a day roll and a tampered
file, then prints the daily report. Everything is written to a temp directory
that is deleted on exit.

**13/13 checks pass.**

The rehearsal earned its place immediately. Its first run failed two checks,
both because all 76 snapshots executed inside the same wall-clock second:
deduplication correctly collapsed them and staleness never accumulated. The
production code was right; the harness was unrealistic. That produced the one
change made to production code purely for testability — a `_now()` clock seam
— because staleness, day rolls and snapshot spacing are all clock-dependent
and none can be tested honestly against a clock that cannot move.

## 6. Verification

| Check | Result |
|---|---|
| Audit gaps closed | **8 / 8**, re-verified by execution |
| New hardening tests | **69 passed** |
| Phase 12 recorder tests | **29 passed**, unchanged |
| Offline rehearsal | **13 / 13** |
| Full python unit suite | see §9 |

The Phase 12 tests passing untouched after a `SCHEMA_VERSION` bump and six new
fields is itself the backward-compatibility check: a frozen dataset written by
the old recorder still reads.

## 7. What this phase deliberately did **not** do

* No strategy, exit, contract-selection, signal or parameter change.
* No change to `BAND_ATR = 0.25` or `ATR_WINDOW = 14` — the signal stays frozen.
* No FINNIFTY access; it is still not a collector default.
* No synthetic backfill of any kind. A missing day stays missing.
* No strategy search, per the standing instruction to prove the recorder first.

## 8. The one thing the recorder cannot guarantee

**A real broker session must exist before collection starts.** Without a
cached Fyers token the chain endpoint silently serves a Black–Scholes model
chain. The recorder handles this correctly — it stores the payload, classifies
every leg `SYNTHETIC`, warns in the log, and marks the session `UNUSABLE` —
but it cannot *create* a session. A day started without one is a day lost.

The `--dry-run` pre-flight in the runbook exists solely to catch this, and it
writes nothing, so there is no cost to running it every morning.

## 9. Verdict

**`RECORDER READY FOR OBSERVATION`**

Every §31 requirement is met and verified by execution. The failure modes that
would have corrupted the dataset silently now either cannot occur or announce
themselves in the daily report. The recorder's own honesty about what it does
not have — no exchange quote timestamp, no IV or Greeks from the broker, no
historical backfill — is enforced by tests rather than by comments.

This authorises **observation only**. It does not authorise activating the
strategy, paper trading, or any economic conclusion. The Phase 11 validation
may not run until 125 `COMPLETE` sessions exist, on a split declared before
the data is examined.

Operating procedure, failure handling and the 20 / 60 / 125-session
checkpoints: `trading-system/research/option_recorder/RUNBOOK.md`.
