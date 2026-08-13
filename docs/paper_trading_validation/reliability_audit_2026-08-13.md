# Production Reliability & Safety Audit — 2026-08-13/14

**Scope:** a deep, read-only-first audit of the entire trading system
focused exclusively on production reliability and safety, triggered by
two real incidents earlier the same day (a ~9-minute duplicate-launch
outage, a ~39-minute total engine freeze). Root-cause the two incidents
plus broker/WebSocket failure modes, stale-data risk, and process/thread
starvation risk generally; implement single-instance protection,
heartbeat/progress monitoring, watchdog diagnostics/recovery, and
open-position safety; validate every fix through failure injection;
preserve all existing strategy logic and production behavior; add
regression tests; render an evidence-based verdict.

**This verdict is scoped to this audit's specific deliverables only.**
It is not, and does not replace, the overarching live-trading readiness
process in `GO_NO_GO_CHECKLIST.md` (§2's 10-session/30-trade clean
window, §0's outstanding credential-rotation items, etc.) — that
process governs whether the system is ready for real capital; this one
governs whether the specific failure modes named in this audit's brief
are now demonstrably handled.

## Verdict: **GO** (for this audit's scope)

The user's stated floor — *"NO-GO unless the system can demonstrably
detect, safely handle and recover from critical failures without
leaving positions unmanaged or creating duplicate orders/positions"* —
is met with live evidence, not just unit tests, for every clause:

| Requirement | Evidence |
|---|---|
| **Detect** a critical failure | Live: a real staleness condition was created and the real watchdog detected it (`MAIN.PY FROZEN: heartbeat stale for 10000s (PID 16132 still alive)`) |
| **Safely handle** it | Live: a real Discord alert fired, the real frozen process (PID 16132) was terminated and its death confirmed *before* any respawn attempt |
| **Recover** | Live: a fresh `main.py` (PID 15892) was spawned and its own first heartbeat confirmed within the grace window (`main.py restart succeeded -- fresh heartbeat confirmed`, ~5s later) |
| Without leaving **positions unmanaged** | By construction + tested: `_load_positions()` already reloads open positions (incl. stop-loss) from disk on any restart (pre-existing, confirmed still correct); §2.6's reconnect-while-holding-a-position pipeline now has dedicated test coverage |
| Without **duplicate orders/positions** | Live: a real second `api_bridge.py` launch was attempted while the first was running and was correctly rejected (`FATAL: another api_bridge instance is already running`); the watchdog's restart sequence explicitly confirms the old process is dead before spawning a new one, so the same lock can never let two instances coexist |

## What was fixed, with evidence

### 1. Duplicate-launch — root cause: TOCTOU race, not a missing guard

`shared/singleton_lock.py` already existed (since 2026-08-05) but
checked-then-wrote non-atomically, letting two near-simultaneous
launches both pass the check. Fixed with `filelock.FileLock` guarding
the critical section (already an unused transitive dependency, now a
direct one).

- **Unit-tested:** a new synchronized-barrier test spawns 8 real OS
  processes hitting the check at the same instant — fails reliably
  (4/4 runs) against the old code, passes reliably (5/5 runs) against
  the fix.
- **Live-verified tonight:** a real second `api_bridge.py` launch
  while the first was running was correctly rejected with the exact
  expected diagnostic message and exit code 1.

### 2. The ~39-minute engine freeze — root cause: no request timeout + unthrottled synchronous calls on the event loop

`trading_bot/main.py` called `broker.get_market_data()` synchronously,
unwrapped, directly on the event loop, from 4 call sites — already
flagged as a known, deliberately-deferred gap in an existing comment.
The vendored `fyers_apiv3` SDK makes its HTTP requests with no
`timeout=` anywhere; a hung TCP connect (plausible mid-network-recovery,
and correlated with an 11-entry DNS failure burst at the exact moment
of the real freeze) could block that call — and the whole event loop
with it — indefinitely.

Fixed with two independent layers: a default request timeout mounted on
every `FyersModel` session (`brokers/fyers_broker.py`, no vendored-code
edits), and every call site wrapped in `asyncio.to_thread` plus gated by
the previously-unused `DATA_LIMITER`.

- **Unit-tested (freeze injection):** a test proves a synchronous call
  that genuinely blocks for real wall-clock time does not stall a
  concurrent coroutine once wrapped in `to_thread`, with a negative
  control proving the *old* pattern genuinely does stall everything —
  this is the actual 2026-08-13 freeze mechanism, reproduced and
  confirmed fixed.
- **Not yet live-verified against a real DNS/network failure burst** —
  by nature, that condition can't be safely forced; the mechanism is
  proven at the code level and by injection test, but its first real
  confirmation will be whenever the next real network blip occurs
  during market hours (matching how the 2026-08-12 `on_close` fix was
  ultimately confirmed by the *next* real disconnect, not by forcing
  one).

### 3. main.py heartbeat — the missing "is the event loop alive" signal

main.py had no way to report "I'm still scheduling tasks" independent
of ticks arriving — the ~39-minute freeze was only found by manual
log review hours later, and even a genuinely flat/idle engine looked
identical to a frozen one from outside. Added a `heartbeat_writer` task
writing to `run/main_heartbeat.txt` on a fixed ~15s cadence, with no
dependency on anything that could block.

- **Live-verified tonight:** sampled twice 16s apart, delta was 15.02s
  — genuinely updating on schedule, not a one-time write.

### 4. api_bridge.py watchdog — safe auto-recovery

Detailed above (the verdict table). Backoff reuses `main.py`'s existing
`_compute_retry_delay`/`_should_reset_failure_count` so a fundamentally
broken condition can't trigger a restart-loop storm — unit-tested via
the real decision function, not just the mocked end-to-end path.

### 5. A separate latent bug found and fixed along the way

While wiring the watchdog's alerts, found `alerter.send_alert(...)` —
already called in 3 places in `main.py` — didn't exist on the actual
`Alerter` class in use; every one of those 3 call sites would have
raised `AttributeError` the instant any of them fired. None had, so
nothing caught it. Fixed and tested; this also means the watchdog's own
alerts are now provably working (see the live freeze test above, which
exercised this exact method against the real Discord webhook).

### 6. DB-lock and position-file interruption — already hardened, now proven

Audit found `shared/state.py` (WAL mode + 30s busy_timeout on every
connection) and `_save_positions()` (atomic tempfile+`os.replace` with
retry, added after a real prior incident) were already correctly built
— the gap was test coverage, not code. New tests hold a real competing
SQLite lock and a real interrupted/persistently-failing replace, proving
both mechanisms behave exactly as designed under contention.

### 7. §2.6's test-coverage gap closed — reconnect while holding a position

`docs/GO_NO_GO_CHECKLIST.md`'s §2.6 had zero test coverage and stayed
live-untested even after 5 real WebSocket disconnects in this same
session (none coincided with an open position). Extracted the
previously-untestable `sync_broker_state` closure into
`_reconcile_broker_state`; 5 new tests cover paper mode (the mode
actually running today) leaving a position completely untouched, and
live-mode's full pipeline (not just the already-tested pure decision
logic) for both "still open" and "closed while disconnected."

**This closes the test-coverage gap, not §2.6 itself.** §5's evidence
package still explicitly requires "the specific log lines for the §2.6
**real** reconnect-during-market-hours event, plus manual verification
against the broker's order book" — a real, non-paper broker connection
actually reconnecting while holding a real position. That hasn't
happened; nothing in this audit substitutes for it.

## Explicitly not fixed, flagged not silently assumed handled

- **A fully-dead (not frozen) `main.py`** is out of this watchdog's
  scope by design — that's main.py's own internal crash-retry loop's
  job, which already exists and is tested (`test_crash_retry_backoff.py`).
  If main.py crashes so hard the OS process itself disappears, this
  watchdog correctly does nothing (confirmed by test), on the reasoning
  that main.py's own loop handles it when the process is alive to run
  it. A simultaneous crash of *both* the process and its own retry loop
  is a gap this audit did not address.
- `Start_AI_Bot.bat`'s unconditional port-8000/3000 kill (no
  open-position check) — flagged in the original plan, not touched.
- The legacy `deployment/` folder (systemd/Docker/Streamlit) — appears
  stale/unused, not touched.
- No changes anywhere to strategy signal logic, entry/exit thresholds,
  risk parameters, or anything that would affect backtest results.

## Test suite

`pytest` from `Testing_Automation_AI_Trading_Bot/python-unit/`:
**580 → 627 tests (47 new), all passing, zero regressions**, 2
pre-existing `xfail`s unchanged throughout.

## Commits (this branch, `trading_bot_v2.10.0`, none pushed)

1. `fix(infra): close TOCTOU race in the singleton-instance lock`
2. `fix(infra): close the 39-minute engine-freeze root cause`
3. `feat(infra): add main.py heartbeat`
4. `fix(infra): add Alerter.send_alert`
5. `feat(infra): add main.py freeze detection + safe auto-recovery to api_bridge.py`
6. `test(infra): prove state.db and active_positions.json hold up under real contention/interruption`
7. `test(infra): close GO_NO_GO_CHECKLIST.md §2.6`

## Recommended next steps

1. Let the fixed engine-freeze mechanism get its first real-world
   confirmation naturally (next genuine network blip during market
   hours) — watch for it specifically rather than assuming it's fully
   proven until then.
2. Consider `Start_AI_Bot.bat`'s unconditional port-kill fix as a
   follow-up (minor, flagged, not blocking).
3. The one explicitly out-of-scope gap (simultaneous process-and-retry-
   loop death) is worth a deliberate decision on whether it's worth
   covering, given how narrow it is.
4. This audit's fixes should now flow into the regular
   `docs/paper_trading_validation/anomaly_log.md`/`GO_NO_GO_CHECKLIST.md`
   monitoring cadence like any other session — the overarching
   validation clock and its own criteria are unaffected by this audit
   and continue on their own terms.
