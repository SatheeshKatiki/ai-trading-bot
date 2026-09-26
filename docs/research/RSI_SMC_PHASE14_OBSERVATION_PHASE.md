# Phase 14 — Observation phase: operating the recorder

**Scope: observation and data collection only.** No strategy was activated,
no order or paper order placed, `active_strategy` is unchanged, no `rsi_smc`
production config exists, the frozen prior-day-extreme hypothesis is
untouched, no optimisation was performed, no economic performance was
inspected, and FINNIFTY remains sealed.

**Status: `0 of 20 COMPLETE sessions`. The 20-session checkpoint has not been
reached and no data-quality decision is returned.**

**TRADING: NO-GO** (unchanged).

---

## 1. What this phase could and could not deliver today

The objective is 20 COMPLETE sessions of observed option data. **A session is
a trading day**, so 20 sessions is 20 trading days of real market time. That
cannot be compressed, simulated, or substituted — and manufacturing sessions
from generated data would produce exactly the fabricated dataset every prior
phase was built to prevent.

What the calendar actually permitted:

| Check | Result |
|---|---|
| Today | **Saturday 2026-09-26** — market closed |
| `api_bridge` reachable | **No** — connection refused on 127.0.0.1:8000 |
| Fyers token cached | Yes |
| Pre-flight verdict | **`NO-GO`** (exit code 2), correctly |
| Sessions collectable today | **0** |
| First collectable session | **Monday 2026-09-28** |

So this phase delivered the thing that *was* deliverable: the operational
apparatus §1–§20 require, which did not exist at the end of Phase 13, built
and tested so the first real session is recorded correctly rather than
becoming the session that discovers a gap.

## 2. Gaps found in the Phase 13 recorder

Phase 13 ended at `RECORDER READY FOR OBSERVATION`. Measured against the
Phase 14 requirements, four things were missing outright:

| Requirement | Phase 13 state |
|---|---|
| §3 India VIX recorded | **Not recorded at all** |
| §1 pre-flight is real, not nominal | A dry-run log line for a human to *read and judge* |
| §7 session report | Nine required fields absent (versions, source, start/end, invalid, zero bid/ask, crossed, storage errors, reconnects, restarts, time-integrity violations) |
| §14 20-session audit | No aggregation across sessions existed |

### India VIX (§3)

`api_bridge` already serves a real `indiaVix` from the broker's
`indiavixData`, and the recorder discarded it. It is now captured on the
underlying snapshot with provenance `OBSERVED`.

Absent stays absent. A missing VIX is stored as `null`, never zero and never
carried forward from an earlier snapshot — a stale volatility reading would
silently rewrite the regime a later study attributes its result to.

### The pre-flight is now a gate, not a log line (§1)

`preflight.py` executes every §1 check and returns an exit code: clock is
IST, session date is today, storage writable, endpoint reachable, **chain is
real and not synthetic**, quotes parse, VIX present, history available, and
history has no future-dated bars.

Critical failures block; weekend, closed market, thin chain and missing VIX
are advisory. A degraded chain is still real data worth recording, and
refusing it would hide the degradation.

Run against the live machine today it correctly returned `NO-GO` with exit
code 2, naming the unreachable bridge.

### The session report (§7)

`session_report.py` produces the full §7 structure. Two properties are worth
stating because they are not obvious:

**It reads the checkpoint, not only the data.** Outages, restarts and storage
errors leave no trace in the data files. A report rebuilt from files alone
would show a clean session that in fact dropped twenty minutes.

**It re-derives the timestamp guarantees at read time.** The recorder already
enforces them at write time. A guarantee only ever asserted by the writer is
not a guarantee — if a future normalisation bug breaks it, this is what
notices. Any row whose `available_at` precedes its `event_time` forces the
session `UNUSABLE` regardless of the rest of the scorecard, because that is
look-ahead sitting inside data whose purpose is to prove look-ahead is absent.

### The audit (§14, §19)

`audit.py` aggregates session reports into the §14 checkpoint structure and
tracks storage footprint per layer (§19). It counts **only `COMPLETE`**
sessions toward a target, mechanically, with no override — the temptation at
session 18 is to relax the definition, so the definition is not
hand-applicable. A test asserts the audit output contains no P&L, win rate,
Sharpe or best-strike field, so the checkpoint cannot drift into an economic
review.

## 3. The counters that only the running process knows

`InstrumentState` now tracks storage errors, reconnects, restarts, refused
future bars, synthetic snapshots and thin chains, persisted to the checkpoint
after every snapshot and restored on resume (incrementing `restarts`). This
is what makes §7's persistence section truthful rather than reconstructed.

## 4. Verification

| Check | Result |
|---|---|
| New Phase 14 tests | **42 passed** |
| Phase 13 hardening tests | **69 passed** |
| Phase 12 recorder tests | **29 passed** |
| Offline rehearsal | **13 / 13** |
| Full python unit suite | **1754 passed**, 1 skipped, 2 xfailed — 0 regressions (was 1712) |
| Live pre-flight | `NO-GO`, exit 2, correct |

One class of test bug is worth recording because it would have rotted
silently: fixtures originally dated sessions `2026-09-30`, which is in the
*future* relative to today, and the time-integrity check correctly rejected
them. Anchoring fixtures to the real clock exposed a second version of the
same problem — a full 76-snapshot session runs 09:15→15:35, so a fixture
anchored to *today* passes in the morning and fails after lunch. Fixtures are
now anchored to completed weekdays.

## 5. What has NOT been done, deliberately

* No win rate, P&L, Sharpe, MFE/MAE optimisation, strike/expiry/DTE
  comparison, or contract-selection research (§11, §12).
* No change to `BAND_ATR = 0.25` or `ATR_WINDOW = 14` (§5, frozen).
* No FINNIFTY access; it is absent from both collector and pre-flight
  defaults, asserted by tests (§13).
* No RAW rewriting. Re-normalisation would write a new version with a bumped
  `normalization_version` (§18).
* No strategy activation or production config mutation, asserted by tests
  (§20).

## 6. §15 checkpoint decision

**Not returned.** The 20-session checkpoint requires 20 `COMPLETE` sessions
and zero exist. `docs/research/RSI_SMC_PHASE14_20_SESSION_DATA_AUDIT.md` is
not written, because writing it now would mean inventing its contents.

`audit.py` generates it from real stored reports once the sessions exist, and
currently reports `IN PROGRESS`, `next checkpoint at 20 COMPLETE sessions`.

## 7. What happens next, and who does it

Collection is a **manual daily operation** and cannot be started from here:
it needs a running `api_bridge` with an authenticated Fyers session on the
trading laptop, during market hours.

Each trading day from **Monday 2026-09-28**:

```bash
cd "D:/Projects/AI trading Bot/trading-system"
python -m research.option_recorder.preflight          # must exit 0
python -m research.option_recorder.collect --interval 300
# ... Ctrl+C after 15:30 ...
python -m research.option_recorder.qa
python -m research.option_recorder.audit --target 20
```

Full procedure, the restart drill (§10) and the incident log format (§9):
`trading-system/research/option_recorder/RUNBOOK.md`.

At 20 `COMPLETE` sessions the audit doc gets generated and the §15 decision
returned. **Trading remains NO-GO at that point regardless of the data
verdict** — a clean dataset proves the dataset is clean, nothing more.
