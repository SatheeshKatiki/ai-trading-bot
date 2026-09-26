# Option recorder — operating procedure

**Research infrastructure. It observes and writes files. It never places an
order, never touches `active_positions.json`, `state.db` or dashboard equity,
and nothing starts it automatically.**

It is started by hand and stopped by hand. That is deliberate: an automatic
recorder that fails quietly collects months of holes nobody notices.

---

## Before the session (once, ~09:00 IST)

1. **The API bridge must be up and logged in.** The recorder reads
   `http://127.0.0.1:8000/api/option-chain`, which serves the broker's real
   chain *only when a Fyers session exists*. With no session the endpoint
   falls back to a Black–Scholes model chain flagged `synthetic: true`.

2. **Run the pre-flight gate.** It writes nothing and checks every condition
   mechanically, because the one failure that matters — a synthetic chain from
   a missing broker session — looks completely normal at a glance and costs a
   whole trading day:

   ```bash
   cd "D:/Projects/AI trading Bot/trading-system"
   python -m research.option_recorder.preflight
   ```

   It verifies the clock is IST, the session date is today, storage is
   writable, the chain endpoint is reachable, **the chain is real and not
   synthetic**, quotes parse and classify, India VIX is present, history is
   available, and history contains no future-dated bars.

   * **exit code 0 → `GO`** — start the recorder.
   * **exit code 2 → `NO-GO`** — do not collect. The failing checks are listed.

   `warn` lines (weekend, market closed, thin chain, missing VIX) are
   advisory and never block: a degraded chain is still real data worth
   recording, and dropping it would hide the degradation.

3. Optionally rehearse the whole pipeline offline (no network, no broker,
   deletes everything it writes):

   ```bash
   python -m research.option_recorder.selftest
   ```

---

## Starting (by 09:15 IST)

```bash
cd "D:/Projects/AI trading Bot/trading-system"
python -m research.option_recorder.collect --interval 300
```

Defaults: `NIFTY BANKNIFTY SENSEX`, 5-minute cadence, market hours only.

**FINNIFTY is deliberately not a default.** Its Phase 9 holdout is sealed.
Newly recorded FINNIFTY data would be a separate dataset, but keeping the two
apart afterwards is easy to get wrong, so the default avoids the question.

Leave the window open. Each snapshot logs one line per instrument:

```
2026-09-30 NIFTY quotes=42 new=42 dup=0 quality={'VALID': 42} strikes=21 signal=None
```

* `new` vs `dup` — `dup` above zero is normal after a restart and means
  deduplication is working, not that something is wrong.
* `quality` — any `SYNTHETIC` means stop and fix the broker session.
* `strikes` — a sudden drop means the chain is degrading.

---

## If it stops (crash, reboot, closed laptop)

**Just start it again with the same command.** Restarting mid-session is safe
and expected:

* the already-recorded observations are loaded back before the first
  snapshot, so nothing is recorded twice;
* the checkpoint restores the session counters;
* the first log line after a restart will show a large `dup=` count. That is
  the resume working.

Nothing needs to be deleted, moved or repaired by hand. Do **not** delete
partition files to "start clean" — the store is append-only on purpose, and
the manifest will report any file that changed.

---

## Stopping (after 15:30 IST)

`Ctrl+C`. On the way out it writes a manifest (SHA-256 of every file) for each
instrument-session it touched. That manifest is what later proves the day's
data has not been altered.

---

## After the session — one command

```bash
python -m research.option_recorder.eod
```

That runs the entire end-of-day procedure for today: manifest, integrity
verification, session report (persisted), incident review, classification and
the `COMPLETE_SESSIONS` counter. Pass `--session YYYY-MM-DD` for an earlier
day. It is re-runnable.

**It cannot override a classification, by design.** The status comes from the
QA rules and there is no flag that could supply one; a test asserts none
exists.

The individual commands remain available:

```bash
python -m research.option_recorder.qa                       # one line per session
python -m research.option_recorder.session_report     --instrument NIFTY --session YYYY-MM-DD --write         # full evidence record
python -m research.option_recorder.audit --target 20        # cumulative audit
```

```
instrument  session       snaps  compl%  quotes  valid%  synth  dup  events  gaps  score      status
NIFTY       2026-09-30       76    100%    3192     98%      0    0       3     0   0.97    COMPLETE
```

Read the **`status`** column, not the score. The score ranks sessions at a
glance; the status decides usability and is a floor over the six dimensions,
so one fatal problem cannot be averaged away by five healthy ones.

| Status | Meaning |
|---|---|
| `COMPLETE` | full coverage, fresh, intact — counts toward the target |
| `INCOMPLETE` | real data with gaps — keep it, but it is not a full session |
| `UNUSABLE` | synthetic, corrupt, duplicated, malformed, or under 60% — does **not** count |
| `EMPTY` | nothing collected |

Any `BLOCKER:` line printed under a session says exactly which bound failed.

---

## The session report

`session_report` is the per-day evidence record: metadata and versions, data
quality (valid / invalid / stale / synthetic / zero bid-ask / crossed /
duplicates / malformed / missing intervals), persistence (raw and normalized
row counts, setups, storage errors, reconnects, restarts) and time integrity
(timezone, future timestamps, `available_at` vs `event_time`).

Two things it does that `qa` cannot:

* **It reads the checkpoint.** Outages, restarts and storage errors leave no
  trace in the data files, so a report rebuilt from data alone would show a
  clean session.
* **It re-derives the timestamp guarantees from stored data.** The recorder
  enforces them at write time; the report checks them again at read time. A
  guarantee only ever asserted by the writer is not a guarantee. Any row whose
  `available_at` precedes its `event_time` forces the session `UNUSABLE`,
  whatever the rest of the scorecard says.

## Incident log

Every failure gets an entry. The log is a tool rather than a markdown file
because the sessions where something went wrong are exactly the sessions
where the operator is busy dealing with it — and an incident log missing its
worst entries is worse than none, since the 20-session audit would then read
as clean.

```bash
python -m research.option_recorder.incidents log     --session 2026-09-28 --instrument NIFTY --type API_OUTAGE     --detected 11:20 --last-valid 11:15     --cause "api_bridge restarted"     --action "recorder restarted 11:24, resumed from checkpoint"     --usable INCOMPLETE

python -m research.option_recorder.incidents list
python -m research.option_recorder.incidents summary
```

Types: `TOKEN_UNAVAILABLE`, `SYNTHETIC_CHAIN`, `API_OUTAGE`,
`RECORDER_CRASH`, `STORAGE_FAILURE`, `TIMEZONE_MISMATCH`,
`DUPLICATE_CORRUPTION`, `FUTURE_TIMESTAMP`, `MALFORMED_CHAIN`,
`NOT_COLLECTED`, `RESTART_DRILL`, `OTHER`.

**A day the pre-flight refused must be logged as `NOT_COLLECTED`.** It never
reaches the store, so it exists only here; without the entry the audit would
understate how many trading days were actually lost. (Weekends and holidays
are not trading days and are not logged.)

The log is append-only and checksummed. A mistaken entry is corrected by
appending a correction, never by editing.

**Never patch a historical record to make a session look better.** If a
normalisation bug is found later, write a NEW normalized version with a
bumped `normalization_version`; RAW is never rewritten. If data ever *is*
altered, the incident must say so (`--data-modified`) — the audit then
refuses a `DATA QUALITY PASS` until it is resolved.

## Restart drill (§10)

Once during the first 20 sessions, prove resume works on real data. Do it
mid-session, when a missed snapshot costs one interval rather than the day:

1. Note the snapshot count in the log.
2. `Ctrl+C` the recorder.
3. Start it again with the same command.
4. Confirm the log says `resumed from checkpoint ... (restart #1)`.
5. Confirm the next line shows a large `dup=` and `new=0` for the repeated
   instant.
6. After the session, confirm `duplicates: 0` in the session report and that
   integrity still passes.

Record it in the incident log as a planned drill.

## Checkpoints

The recorder exists to answer one question that cannot be answered today:
*does the Phase 10 entry survive real option friction?* That needs sessions,
and sessions only arrive one per day.

| After | What to do |
|---|---|
| **5 COMPLETE sessions** | Infrastructure-only checkpoint: continuity, quote quality, storage and timestamp integrity, reconnect behaviour, unresolved defects. A systemic recorder defect found here costs 5 sessions instead of 20 — stop and fix before continuing. |
| **10 COMPLETE sessions** | Re-run the recorder tests, schema validation, cumulative QA, duplicate/timestamp/storage audits. Require `0 unexplained critical data-integrity defects` before continuing. |
| **20 COMPLETE sessions** | Infrastructure review only. Confirm coverage, freshness and integrity are holding. **No strategy analysis** — 20 sessions cannot answer an economic question, and looking early is how a result gets chosen rather than measured. |
| **60 COMPLETE sessions** | First look at option friction: measured spread, measured theta per session per DTE regime. Descriptive only, still no go/no-go. |
| **125 COMPLETE sessions** (~6 months) | The pre-declared economic validation from Phase 11 may run, on `available_at`-filtered data, with the DEV/VAL/HOLDOUT split declared **before** the data is examined. |

Sessions marked `INCOMPLETE` or `UNUSABLE` do not count toward these totals.

---

## What would invalidate the dataset

Stated in advance, so it cannot be rationalised later:

* Any `SYNTHETIC` quote treated as an observation.
* Any backfill of a missing day from a model. A gap stays a gap.
* Editing a stored partition file. The manifest will detect it.
* Changing `BAND_ATR` or `ATR_WINDOW` mid-collection — the signal definition
  is frozen. If it must change, the dataset restarts with a new
  `recorder_version`, and the two are never pooled.
