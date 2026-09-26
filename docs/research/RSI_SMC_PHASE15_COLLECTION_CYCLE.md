# Phase 15 — Collection cycle: operating the recorder

**Scope: observation only.** No optimisation, no profitability inspection, no
P&L, no contract/strike/expiry comparison, no entry or exit tuning, no paper
trading, no orders, no `active_strategy` change, no production config, no
FINNIFTY. The prior-day-extreme signal is untouched.

**`COMPLETE_SESSIONS = 0` of 20.**

**TRADING = NO-GO** (unchanged).

---

## 1. Why the count is still zero

Phase 15 is an execution-over-calendar-time phase. Its success condition is
twenty *genuine market sessions*, and a session is a trading day. Twenty
sessions is roughly four calendar weeks of real market time that has not
happened yet.

State at the time of writing:

| Check | Result |
|---|---|
| Now | **Saturday 2026-09-26, 12:15 IST** |
| Market | Closed (weekend) |
| `api_bridge` | Unreachable — connection refused on 127.0.0.1:8000 |
| Fyers token | Cached |
| Pre-flight | **`NO-GO`, exit code 2** |
| Sessions collectable today | **0** |
| First collectable session | **Monday 2026-09-28** |

Per §1 this is `SESSION = NOT COLLECTED`. No incident was logged for it: a
Saturday is not a trading day, and filling the log with non-trading days
would bury the entries that matter. The cycle starts Monday.

The one thing that must not happen here is manufacturing the missing
sessions. §26 asks for *genuine* market sessions; generated ones would be the
fabricated dataset every phase since Phase 8 has been built to prevent.

## 2. What was delivered instead

Three things Phase 15 requires that did not exist after Phase 14, chosen
because each removes a way the twenty-session cycle can silently fail.

### The incident log is now a tool, not a template (§11)

Phase 14 left it as a markdown template in the runbook. A template gets
filled in when someone remembers to — and the sessions where something went
wrong are exactly the sessions where the operator is busy dealing with it.

An incident log missing its worst entries is worse than no log, because the
20-session audit would then read as clean. So the record is append-only and
checksummed, its required §11 fields are enforced at write time, twelve
incident types are enumerated, and **the audit reads it directly** rather
than trusting a human to have transcribed it.

Two consequences worth stating:

* A day the pre-flight refused never reaches the store, so it exists only in
  this log. `calendar_sessions_attempted` now counts it — otherwise the audit
  would understate how many trading days were actually lost.
* If stored data is ever altered, the incident must say so
  (`--data-modified`), and the audit then refuses a `DATA QUALITY PASS` until
  it is resolved. §19 calls lineage damage blocking regardless of how healthy
  the counts look.

### End-of-day is one command (§9)

The §9 procedure is eight steps, repeated on twenty separate evenings, by
someone who has just spent a day deliberately not looking at the results.
Eight steps times twenty sessions is where a skipped manifest comes from —
and a session without a manifest can never afterwards prove it was not
altered.

`eod.py` runs all of it: manifest, integrity verification, persisted session
report, incident review, classification, and the `COMPLETE_SESSIONS` counter.

**It exposes no way to override a classification.** §9 forbids a manual
override, so rather than documenting that rule the tool simply has no flag
that could supply one, and a test asserts none appears.

### The audit gained the §14 metrics it lacked and the early rungs

Added: valid / invalid / synthetic / stale / zero-bid-ask / crossed /
malformed / duplicate totals, India VIX availability, and chain coverage
reported as **minimum as well as mean** — a mean hides the one session that
degraded to three strikes.

The checkpoint ladder is now `5 / 10 / 20 / 60 / 125`. The early rungs exist
because a systemic recorder defect found at session 5 costs five sessions and
the same defect found at session 20 costs twenty, while the cost of looking
is one afternoon.

## 3. Workflow rehearsal

The operator sequence was rehearsed end to end offline — five sessions, one
deliberately degraded, one refused day, plus a restart drill:

```
2026-09-18  COMPLETE    +1
2026-09-21  COMPLETE    +1
2026-09-22  COMPLETE    +1
2026-09-23  UNUSABLE    +0      <- 30 snapshots, correctly refused
2026-09-24  COMPLETE    +1

COMPLETE_SESSIONS = 4   next rung 5
attempted 6 (stored 5, not collected 1)
restart drill: True
unresolved: ['2026-09-23 NIFTY: UNUSABLE -- completeness 39% < 60%']
```

The degraded session was refused and not counted, the refused day was counted
as attempted, and the unresolved issue was named rather than averaged away.

## 4. Verification (§24)

| Suite | Result |
|---|---|
| Phase 15 (new) | **33 passed** |
| Phase 14 | 42 passed |
| Phase 13 | 69 passed |
| Phase 12 | 29 passed |
| Offline rehearsal | 13 / 13 |
| Full project suite | **1787 passed**, 1 skipped, 2 xfailed (was 1754) |

One regression was introduced and fixed. Moving the checkpoint ladder from
`20/60/125` to `5/10/20/60/125` broke a Phase 14 test that had pinned the
literal `20` as "the next rung". The test was right to fail — it was
asserting the old ladder — so it now derives the expected rung from
`CHECKPOINTS` rather than hardcoding a value that any future rung change
would break again.

## 5. Production isolation (§25)

Re-asserted by test, not by inspection: `active_strategy` is
`ema9_rsi_momentum`, no `rsi_smc_*` config key exists, **no module under
`trading_bot/` or `brokers/` imports the recorder**, no recorder module
references any order, risk-manager or exit-engine symbol, the signal
definition is still `BAND_ATR = 0.25` / `ATR_WINDOW = 14`, and FINNIFTY
appears in no default.

## 6. §19 decision

**Not returned.** The 20-session decision requires 20 `COMPLETE` sessions and
there are zero. `docs/research/RSI_SMC_PHASE15_20_SESSION_DATA_AUDIT.md` is
not written, because writing it now would mean inventing its twenty required
sections.

`audit.py` generates its content from real stored reports once the sessions
exist. It currently reports `IN PROGRESS`, `next checkpoint at 5 COMPLETE
sessions`.

## 7. The daily cycle, from Monday 2026-09-28

Collection is manual and cannot be started from here: it needs `api_bridge`
running with an authenticated Fyers session on the trading laptop, during
market hours.

```bash
cd "D:/Projects/AI trading Bot/trading-system"

# pre-open -- must exit 0, else log NOT_COLLECTED and skip the day
python -m research.option_recorder.preflight

# 09:15 -- leave running, monitor infrastructure only
python -m research.option_recorder.collect --interval 300

# after 15:30 -- Ctrl+C, then one command for the whole EOD procedure
python -m research.option_recorder.eod
```

Log an incident whenever anything on the §11 list happens. Perform the §12
restart drill once during the cycle; the audit shows `restart drill: NOT
DONE` until it is recorded.

Stop at **5** for the infrastructure checkpoint, at **10** for the full test
and integrity re-run, and at **20** for the final audit and the §19 decision.

**At 20 sessions, trading remains NO-GO regardless of the data verdict.** A
clean dataset proves the dataset is clean. Nothing more is being claimed.
