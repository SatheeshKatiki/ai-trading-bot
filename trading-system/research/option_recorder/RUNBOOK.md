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

2. **Prove the session is real before committing the day**:

   ```bash
   cd "D:/Projects/AI trading Bot/trading-system"
   python -m research.option_recorder.collect --once --dry-run
   ```

   Look at the `quality=` field in the log line:

   | What you see | What it means | What to do |
   |---|---|---|
   | `{'VALID': 300}` or similar | real broker chain | start the recorder |
   | any `SYNTHETIC` | **no broker session** | fix the login first — a synthetic day is worth nothing |
   | `ERROR=chain unavailable` | bridge down or not listening | start the bridge |
   | `strikes=3` (thin) | chain is degraded | start anyway; the day will be marked, not lost |

   A dry run writes nothing at all, so it is always safe.

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

## After the session

```bash
python -m research.option_recorder.qa
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

## Checkpoints

The recorder exists to answer one question that cannot be answered today:
*does the Phase 10 entry survive real option friction?* That needs sessions,
and sessions only arrive one per day.

| After | What to do |
|---|---|
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
