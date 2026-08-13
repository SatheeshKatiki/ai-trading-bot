# Live-Trading Go/No-Go Checklist

**Current status: NO-GO.** As of commit `fa845f9` (main, 2026-08-03), code and
infrastructure readiness are done — the paper-trading validation window has
not started yet (see §0). This document is the authoritative checklist to
work through before `live_trading_mode` is ever set to `true`.

**2026-08-03 update:** the day's first live paper-trading session (started
from the §0 reset below) surfaced three separate critical bugs — the system
could not place a single option trade until ~10:34 IST, and the one trade
that did execute was never risk-managed at all (its own stop-loss/target
logic was structurally unreachable). A same-day production-readiness audit
found and fixed 8 issues total across entry, exit management, P&L
calculation, and risk-management wiring — full detail in
`docs/paper_trading_validation/production_audit_2026-08-03.md` and
`anomaly_log.md`. **The validation clock restarts from the first session
opened after this audit (i.e. not before 2026-08-04), not from the
2026-08-03 00:50 reset below** — nothing that happened on 2026-08-03 counts
toward §2's 10-session/30-trade window.

**2026-08-04 update:** first real trading activity since the audit (12:00
IST, a compressed PUT entry/scale/exit sequence during a genuine intraday
downtrend) gave the first **live** validation — not just offline tests —
of every exit path fixed the night before: hard target hit, hard
stop-loss hit (correctly recorded as a loss, not a profit), and partial
profit booking, all with P&L manually reconciled to the cent against raw
entry/exit prices. It also found and fixed one more real bug outside the
prior audit's scope: `PyramidSizer` had the identical side-convention bug
already fixed in `exit_engine.py`, causing the system to scale into a
losing PUT position believing it was profitable. Full detail in
`docs/paper_trading_validation/reports/2026-08-04.md` and
`anomaly_log.md`. **Status remains NO-GO** — §2.6 (reconciliation while
holding a position during market hours) and §2.8 (kill-switch) are still
untested, and the pattern of each session finding a new genuine bug in a
previously-unexercised code path needs to visibly taper off before this
is close to ready. The clean 10-session/30-trade count has not started
yet — 2026-08-05 is the earliest possible session 1.

**2026-08-05 update:** §2.6 got its first real exercise this session (a
WebSocket reconnect storm while genuinely holding positions) and **failed**
it — the broker-reconnect reconciliation logic force-closed 3 real
positions using fabricated stop-loss-estimate prices, root-caused to two
bugs (paper mode has no real broker state to reconcile against; the
`active_positions` dict key was reconciled instead of the actual traded
option symbol) plus an unrelated crash bug (`time` variable scope
collision) that caused the reconnect storm itself. All three fixed and
covered by new regression tests; full detail in `anomaly_log.md`. Also
carried over and verified live: the equity/peak-equity restart-persistence
fix and the option-premium fetch throttle fix, both drafted before this
session. Because the reconciliation bug corrupted `state.db` beyond a
reconstructable equity figure (real closures + old test pollution + a
live-verification test artifact), did a full clean reset (backed up to
`trading-system/backups/backup_20260805_104525/`) — same procedure as
2026-08-03's §0 baseline. **Status remains NO-GO. The validation clock
resets again — 2026-08-05 (10:46 IST restart) is the new earliest possible
session 1**, superseding the date above. §2.6 needs a clean pass (reconcile
correctly, not just "get exercised") before it can be marked done.

**2026-08-05 afternoon update:** monitoring the post-reset session
surfaced what first looked like a real circuit-breaker trip and MARL model
failures, but both root-caused to a single infra bug, not live trading
problems: `api_bridge.py` attached its log-rotation handler to the root
logger at import time, so every `pytest` run this morning leaked test
fixture output into the live `fyersApi.log`, indistinguishable from real
CRITICAL alerts without cross-checking `state.db` (which showed only 5
real trades, net +179.15 PnL, no halt). Fixed, verified test runs no
longer touch the file. Also added a singleton-instance guard to
`main.py`/`api_bridge.py` (defense in depth, unrelated to the false alarm)
and closed out an inconclusive `broker_credentials.json` integrity-check
flakiness (doesn't affect paper mode, flagged for the live-mode Go
decision). Full detail in `anomaly_log.md`. **Status remains NO-GO** — no
new trading-logic bugs found this pass (a good sign toward the "session
with zero new findings" bar), but this was infra/logging investigation,
not a full trading-day validation pass — doesn't count toward tapering the
pattern on its own.

**2026-08-05 end-of-day update:** continuous monitoring through market
close found two more real bugs, both fixed and live-verified same day —
full detail in `anomaly_log.md`. (1) The entry-side option-premium fetch
had no rate-limit throttle (the exit-side path was already fixed for this
on 2026-08-04) — caused a ~250-error burst right at close; fixed by
reusing the exit path's throttle plus a new failure-cache. (2) More
significant: `RiskManager.trades_today` never survived a restart (same
class of gap as the equity/peak-equity fix from earlier today, just missed
for this field) — **every one of today's 3 monitoring-driven restarts
reset the daily 3-trade cap to zero**, letting the strategy execute 12
real trades today instead of 3 (4x over cap). Financial impact was zero
(all 9 extra trades closed at exactly breakeven — quiet market, not a
guarantee that holds generally), but this is a genuine risk-control gap:
a restart during a moving market could have let real losses through beyond
the intended daily limit. Fixed by reconstructing today's real trade count
from `state.db` on startup. **Status remains NO-GO.** Today's session
found 4 new bugs total (log leakage, entry-side rate limiting, and this
trade-cap gap being the 3rd/4th) — the "session with zero new findings"
bar has not been met yet. No open positions at market close; equity
99,925.65 (pnl -74.35 today).

**2026-08-05 evening update:** asked to design a safe way to test §2.6/§2.8
ahead of the next live session (market closed, positions flat). Found §2.8
was **completely non-functional**: `/api/panic-exit` only ever called
`broker.get_positions()`/`get_order_book()`, both of which unconditionally
return `[]` in paper mode, and `main.py`/`api_bridge.py` share no
in-memory state across their separate processes anyway — the kill switch
had zero effect end-to-end for the whole validation window, always
reporting fake success. Fixed with a cross-process `emergency_stop` flag
in `settings.json` that `main.py` checks every tick, wired to
`compute_reconciliation()`'s existing (now-extended) exit-price logic;
added `/api/panic-exit/status` and `/clear`. **Live-verified against the
actually-running system tonight** — real trigger → confirmed `main.py`
halted within one tick → confirmed via status → cleared → confirmed
resumption. Still needs one more live pass with a genuinely open position
during market hours (test plan in `anomaly_log.md`) before §2.8 can be
marked done outright. Also found and fixed, independently: a real ~2-hour
full freeze of `api_bridge.py` (three routes called a synchronous Fyers
SDK client directly inside async handlers, blocking the entire single
event loop — no crash, no error, it just silently stopped accepting any
connection, including this engine's own WebSocket feed). Fixed with
`asyncio.to_thread`. **Status remains NO-GO** — 2 more real bugs found
(kill switch, event-loop freeze), the second discovered only because
testing the first required hitting a live endpoint. Also flagged, not yet
investigated: `main.py`↔`api_bridge.py`'s WebSocket has been dropping
with keepalive timeouts roughly every 60-90s since tonight's restart —
well above the §2.11 baseline, reconnecting cleanly each time but worth
its own look.

**2026-08-06 update:** shipped and deployed live, same session: a
premium-banded option stop-loss with no fixed profit target (replacing a
flat 0.45%/3.5% SL/target), a hard ATM/ITM-only strike-selection clamp,
and expansion from NIFTY-only to all four instruments
(NIFTY/BANKNIFTY/FINNIFTY/SENSEX). This was the first live exercise of
all three, and — consistent with this window's established pattern —
found four real, previously-invisible bugs the moment it actually ran:
(1) no detection for a silent tick feed, letting a position opened at
02:50 IST off a stale post-restart snapshot sit with zero risk
management for 7h49m, until real ticks resumed and produced a fake ~36%
price "jump" that triggered real trailing-SL/partial-book/pyramid
decisions off a data artifact; (2) no gate preventing new entries outside
real NSE trading hours at all, root cause of (1); (3) — the most
severe — a CPU livelock (97-100% CPU, zero log output for 20+ minutes at
a time, reproduced on 3 of 4 restarts including once on NIFTY-only alone)
caused by pandas 3.0.3's `Index.insert()` cost under incremental
`df["x"] = value` column assignment in three hot-path functions, called
~5x/second; (4) confirmed but not previously quantified, the AI-confidence
fallback (`enable_ai_filter` off → hardcoded 1.0) makes every trade run at
the elevated 3.5% risk tier instead of the intended 1% base tier. All four
fixed and unit-tested (49 new tests, 313 total); the livelock fix
specifically verified live via repeated `py-spy` process dumps across
multiple monitoring cycles, but has only ~2 hours of clean observation
behind it, not a full trading day. Multi-instrument was rolled back to
NIFTY-only as an emergency stability mitigation during the livelock
investigation — re-enabling it is an explicit open decision, not resolved.
Full detail: `docs/paper_trading_validation/anomaly_log.md`'s 2026-08-06
entries and `docs/paper_trading_validation/reports/2026-08-06.md`.
**Status remains NO-GO — this is the least-clean session yet by bug
count** (4 new findings, one CRITICAL), and the validation clock has not
started for any of today's new code. §2.6 and §2.8 remain completely
untested across the entire validation window to date; today's own trades
are not usable §2.9 evidence (all downstream of the stale-snapshot
incident); §2.7's daily-trade-cap guard got real, repeated live
confirmation (2,112 correct blocks) but the daily-loss circuit breaker
still hasn't fired in any session. §0's Fyers key rotation and plaintext
credential migration remain outstanding, unrelated to today but still
blocking final sign-off regardless of §2.

**2026-08-07 update:** second live day on the SL/ATM-ITM/market-hours-gate
architecture. Quiet morning (0 trades through ~15:00 IST), then two more
real, previously-invisible bugs found the same session: (1) a routine
71.6% CPU-delta check (vs. ~15-17% baseline) traced via `py-spy` to a
*second* incremental-`Series.__setitem__` call site
(`trading_bot/strategies/registry.py`) sharing the exact `get_loc`/
`repr()` call-chain signature seen in 2026-08-06's actual livelock —
yesterday's fix only covered `compute_features`/`supertrend`/
`generate_signals`, never this one. Fixed via `np.select`, deployed
13:49:37 IST with no position at risk, live-verified via `py-spy` and two
subsequent clean CPU-delta checks (14.1%, 14.8%) over the following ~40
minutes. (2) — found only at close-boundary review (16:40 IST), after the
day was expected to log as "0 trades" — `SmartExitEngine`'s EOD
force-close (15:15 IST) had no matching entry-side cutoff: three real
signals opened positions at 15:15:00/28/55 that were each force-closed by
the very next exit tick 50-250ms later at the identical price, burning
the entire daily 3-trade cap on zero real market exposure and blocking
every genuine signal for the rest of the session. Fixed via a new
`shared/market_hours.py::is_before_eod_cutoff()` entry gate (pinned to
`SmartExitEngine.eod_exit_time` via a dedicated test), deployed ~17:00
IST — **market was already closed at deploy time, so this fix has zero
live observation; tomorrow's ~15:15 IST window is its first real test.**
16 new tests, full suite 333 passed (317 + 16), no regressions. Two
commits, both local, neither pushed. Full detail:
`docs/paper_trading_validation/anomaly_log.md`'s 2026-08-07 entries and
`docs/paper_trading_validation/reports/2026-08-07.md`.
**Status remains NO-GO.** Two more new findings means the validation
clock resets again — it has not started for either of today's fixes, and
the EOD-cutoff fix in particular carries less confidence than usual since
it has no live confirmation at all yet. §2.7 (risk guards) got an
informative confirmation today: the daily-trade-cap guard fired correctly
and repeatedly, but on 3 artifacts rather than 3 real trades — itself the
bug being fixed, not a guard failure. §2.9 has no usable evidence from
today (today's only trades are the zero-PnL EOD artifacts). §2.6 and §2.8
remain completely untested, unchanged. Multi-instrument re-enablement
remains an open decision, unchanged. §0's outstanding items remain
undone, independent of §2.

**2026-08-12 update:** unattended monitoring session (10:34–11:20 IST) found
the upstream Fyers WebSocket silently dead for 46 minutes during real market
hours — `api_bridge.py`'s vendored `fyers_apiv3` client never noticed
because its keepalive ping never checks for a pong, so a zombie TCP
connection (immediately following a burst of DNS resolution failures) was
invisible to it. No position was open, so nothing went unmonitored this
time, but it is the identical mechanism to 2026-08-06's 7h49m incident one
layer further upstream — `main.py`'s own `ENGINE STALL` detector caught the
symptom but had no way to recover from it, since its own local socket to
`api_bridge.py` stayed healthy throughout. Fixed with an independent
staleness watchdog (`fyers_feed_watchdog()` in `api_bridge.py`, backed by a
new pure function in `shared/risk/tick_staleness.py`) that force-rebuilds
the upstream socket after 90s of silence during market hours, plus
`/health` now reporting feed age for external monitoring. A bug in the fix
itself (a `time`-name-shadowing `NameError` from an unrelated dead code
branch) broke real tick delivery entirely for ~15 minutes before being
caught and root-caused — full timeline in `anomaly_log.md`'s 2026-08-12
entry. Both the original stall and the self-inflicted regression are
live-verified fixed as of 11:47 IST (`fyers_feed_age_s` holding under ~2s
continuously since). **Status remains NO-GO** — this is a new,
previously-undiscovered feed-reliability gap found live, so the validation
clock resets again; monitoring continues into the afternoon session.

**2026-08-12 afternoon update:** a second, self-inflicted finding — the
morning's `api_bridge.py` restarts (above) each re-ran Fyers auto-login, a
separate process from `main.py`, which invalidated the session token
`main.py`'s own long-lived `FyersBroker._fyers_model` was still using.
`main.py` had no way to detect or recover from that, and the vendored SDK
never raises on it — it silently returned "no quotes" forever. Net effect:
a real NIFTY PE entry signal held continuously from 12:05:47 to 12:59:59
IST (54 minutes), never taken, no trade recorded, no open position at
risk. Fixed with `FyersBroker._refresh_fyers_model()` — detects an
error-shaped quote response and rebuilds the session from the current
cached token, retrying once — scoped to `get_market_data()` only (not the
order-placement/funds/history call sites, which share the same
structural risk but are closer to live-order paths and are flagged here
rather than changed unilaterally). 6 new tests, full suite 579 passed, 2
xfailed. Restarted `main.py` at 13:35 IST (no open position) and
live-verified. Full detail: `anomaly_log.md`'s 2026-08-12 (afternoon)
entry. **Status remains NO-GO** — validation clock resets again, second
new gap found the same day. Worth noting for future incident response:
restarting one Fyers-authenticated process while the other stays running
is not safe in this architecture yet.

**2026-08-13 update:** session start found `Start_AI_Bot.bat` had been
launched twice, producing two live copies each of `api_bridge.py` and
`main.py`; both pairs died mid-startup (root cause not fully isolated —
likely a resource race between the two instances), leaving **zero engine
processes running for ~9 minutes (~09:31–09:40 IST)** during market hours.
No open position throughout, so nothing went unmanaged, but this is a real
gap and a new failure mode (total outage, not a degraded-but-running
state). Restarted one clean instance of each process; startup completed
normally on the retry.

**Correction (found during the same-day deep audit, see below):** the
claim above — "no safeguard against a second concurrent launch" — was
wrong. `shared/singleton_lock.py` already existed and was already wired
into both processes since 2026-08-05, specifically to prevent this exact
scenario. It has a TOCTOU race (check-then-write, not atomic) that let
today's near-simultaneous launch slip through both copies' checks before
either PID was written — the guard exists, it just has a bug. Root cause
and fix in the audit below.

**2026-08-13 (mid-morning) update:** the 2026-08-12 feed-stall watchdog
fired for the first time against a real socket close and immediately hit
a bug in its own reconnect path — `api_bridge.py`'s `on_close` callback
had the wrong signature for the vendored Fyers client's calling
convention, crashing every time a close actually happened and silently
leaving the feed dead (verified via `/health`'s `fyers_feed_age_s`
climbing 1:1 with wall-clock time, i.e. zero ticks, for several minutes;
`main.py`'s own `ENGINE STALL` detector corroborated it). One-line fix
(`on_close(message=None)`, matching the already-correct `on_error`
sibling); restarted only `api_bridge.py`, live-verified feed age back to
~0.1s and `main.py`'s broker WebSocket client reconnecting cleanly on its
own. No open position throughout. Full detail: `anomaly_log.md`'s
2026-08-13 (mid-morning) entry. **Status remains NO-GO** — third
validation-clock reset today.

**2026-08-13 (afternoon) update — HIGH PRIORITY, unresolved:** first
real trade activity of the day (two full cycles, +178.20 then -3,679.00,
portfolio correctly self-halted new entries after hitting its 3.46% max
daily drawdown) was otherwise clean. The significant finding: a
**~39-minute total engine freeze** (14:18–14:57 IST) where not just the
tick feed but `engine.log` itself went completely silent, including a
separate background thread (sentiment fetch) that had been running like
clockwork all day — pointing at the whole process being starved, not a
simple feed gap. No `py-spy` dump was captured during the freeze, so
root cause isn't confirmed, but it's very plausibly the same unresolved
mechanism as the **2026-08-06** incident already documented in
`shared/risk/tick_staleness.py` (CPU-bound, "root cause not fully
pinned down") — this time worse (39min vs 22min) and correlated with an
11-entry burst of Fyers DNS resolution failures plus a known, already-
flagged-but-unfixed gap: `main.py` calls `broker.get_market_data()`
synchronously on the event loop with no throttle on entry-signal
evaluation. No open position during the window this time (incidental
timing, not a property of any fix). Not fixed — market closed within
minutes of this being found, and the underlying gap was explicitly
marked "deliberately not acted on" in a prior audit; reversing that
unilaterally at close without being able to live-verify isn't the right
call. Full detail and recommended next steps: `anomaly_log.md`'s
2026-08-13 (afternoon) entry. **Status remains NO-GO** — this is the
most significant open item from today, worth prioritizing next session
over new feature work.

This is a living document — check items off with a date and evidence
reference as they're actually completed, don't mark something done because
it's expected to pass.

---

## §0. Prerequisites — must happen *before* the validation clock starts

The paper-trading window's "day 1" doesn't start until all of these are true.
Starting the clock before these are done means the validation period doesn't
count.

- [x] **Reset `state.db` / trade journal to a clean baseline.** Done
  2026-08-03. Backed up the full pre-reset state (125 `trades` rows, 4
  `trade_journal` rows, all confirmed non-genuine — old dev/test artifacts
  from 2026-07-10–20 plus this remediation effort's load/rate-limit test
  pollution) to `trading-system/backups/backup_20260803_005033/` before
  touching anything. Stopped both engine processes (`trading_bot/main.py`,
  `api_bridge.py`), cleared `trades` and `trade_journal` to 0 rows, reset
  `sqlite_sequence` counters, set `state` to equity=100000.0/pnl=0.0, and
  restarted both processes clean. Verified post-restart: `trades`=0,
  `trade_journal`=0, `state`=(100000.0, 0.0), `config/active_positions.json`
  = `{}`. `trade_journal` also confirmed (via code search) to have zero live
  write path — only ever populated by `scripts/init_journal.py` (one-time
  seed) and `scripts/e2e_test.py` — so it won't accumulate fake entries
  during the validation window, but the old seed data would have misled
  anyone treating the Journal UI page as evidence. **This reset is Day 1 of
  the validation window; nothing counted before this timestamp.**
- [ ] **Rotate the Fyers API secret/client ID** via the Fyers developer
  portal. The `.env` values sat in git history before being untracked
  earlier in this remediation — untracking doesn't invalidate a key that
  already leaked into history. *(Outstanding since the original audit;
  still not done as of this writing.)*
- [ ] **Migrate or delete `trading-system/settings.json`'s plaintext Fyers
  credentials** (`client_id`, `secret_key`, `totp_secret`, `pin`). Vestigial
  and unread by any code path, but still sitting in plaintext on disk.
  `brokers/credentials.py`'s `save_credentials()` + the new
  `rotate_encryption_key()` give you a real encrypted store to move them
  into. *(Outstanding since the original audit; still not done.)*
- [ ] Confirm `config/settings.json`'s `live_trading_mode` stays `false` for
  the entire duration of §2 below — check this explicitly if the machine is
  ever restarted mid-window.

---

## §1. Code & infrastructure readiness — DONE, re-verify unchanged

| # | Criterion | Pass condition | Status |
|---|---|---|---|
| 1.1 | All 80 original audit findings resolved | Present in `main` history | ✅ merged (PR #1) |
| 1.2 | Critical bugs found by actually running the engine | WS-auth dead connection, ~100x option mispricing, phantom zero-qty entries, silent position-save crash — all fixed | ✅ merged (PR #2) |
| 1.3 | UI/UX audit | 10 issues incl. a `.gitignore` bug that left secret-file protections non-functional | ✅ merged (PR #3) |
| 1.4 | Backend test suite | `pytest tests/ -k "not test_bt"` → 100% pass, 0 failures | ✅ 95 passed (last run) |
| 1.5 | Frontend build | `tsc --noEmit` exit 0 **and** `npm run build` succeeds | ✅ |
| 1.6 | CI | All 3 jobs (Backend/Frontend/Secret-Scan) green on every merged commit | ✅ 3/3 PRs green |
| 1.7 | Disaster recovery | Backup/restore tested against real state, not just synthetic fixtures | ✅ (`docs/DISASTER_RECOVERY.md`) |
| 1.8 | Order-execution rate limiting | Manual order endpoint rejects bursts beyond the configured limit | ✅ tested |
| 1.9 | Credential encryption + rotation capability | `rotate_encryption_key()` exists and is tested | ✅ (capability only — §0 rotation itself still pending) |

**Re-verification command** (run again immediately before starting §2, not
just trusted from this document):
```bash
cd trading-system
./venv/Scripts/python.exe -m pytest tests/ -k "not test_bt" -q
cd ../frontend && npx tsc --noEmit -p tsconfig.json && npm run build
```

---

## §2. Paper-trading validation — measurable Go/No-Go criteria

**Duration:** minimum **10 full NSE trading sessions** (≈2 calendar weeks)
**or** a minimum of **30 real signal-driven paper trades**, whichever comes
later — counted only from the §0 clean-baseline reset, during actual market
hours (idle/market-closed uptime doesn't count toward this).

All of the following must hold across the entire window. Any single failure
resets the clock — fix the root cause, then restart counting from a fresh
baseline.

| # | Criterion | Measurable pass condition |
|---|---|---|
| 2.1 | No crashes | Zero unhandled exceptions / process exits in `trading_bot/main.py` logs (the crash-retry-backoff loop firing even once counts as a failure to investigate, not a pass) |
| 2.2 | No silent save failures | `grep -c "Failed to save active positions" <logs>` → 0 for the whole window |
| 2.3 | No mispriced entries | Every option entry's logged premium is in a realistic range for that instrument (sanity check: NIFTY/BANKNIFTY option premiums are two to three orders of magnitude smaller than the index level — flag anything that isn't) |
| 2.4 | No phantom entries | Zero trades logged with `qty=0` |
| 2.5 | Order idempotency | Zero duplicate order entries for the same signal/timestamp cluster |
| 2.6 | Reconciliation exercised for real | At least **one** genuine WebSocket disconnect+reconnect during actual market hours (not idle time), with the resulting `STATE MISMATCH` / `RECONCILIATION` log lines manually checked against the broker's real order book and confirmed correct |
| 2.7 | Risk guards fire correctly | Daily-loss circuit breaker and max-trades-per-day guard each observed to trigger at least once — either organically or via one deliberate controlled test — and confirmed to actually halt new entries |
| 2.8 | Kill switch works live | Panic-exit tested at least once during the window against the paper broker; confirm it cancels pending orders and flattens all positions |
| 2.9 | P&L math checks out | Manually recompute PnL for at least 5 sampled trades from raw entry/exit prices and confirm it matches what the dashboard/journal shows |
| 2.10 | No performance decay | Engine process still responsive (check via `/health` or the dashboard) after the full multi-day continuous run — no memory growth pattern that suggests a leak |
| 2.11 | Reconnect frequency stays in family | Baseline observed during market-closed idle time: **~1 reconnect every 160 seconds** (50 reconnects over 135 minutes, 2026-08-02 22:16–00:31 IST). During real market hours with actual tick volume, reconnects should not become *more* frequent than this baseline — if they do, treat it as a live-load-specific bug, not noise |

---

## §3. What to monitor daily during the window

Not a one-time check — do this every trading day the engine runs:

- **Logs:** `grep -i "error\|failed\|mismatch" trading_bot/main.py`'s output for the day — anything new needs triage before the next session.
- **`state.db` trades table:** review new rows since the last check; sanity-check symbol/side/price/qty for each.
- **Broker connection:** reconnect count for the day (compare against the §2.11 baseline).
- **Daily P&L vs. `max_daily_loss_pct`:** confirm the circuit breaker would have fired if the loss limit had actually been hit.
- **Disk usage:** `audit/` logs and anything under `backups/` — make sure nothing is growing unbounded.
- **Process health:** the engine and API bridge are both still running (`netstat`/Task Manager) — a silent process death is itself a finding, not just an inconvenience.

---

## §4. Remaining known risks (not blockers — must be understood, not ignored)

- **Single point of failure.** Everything runs on one local Windows machine. No failover, and disaster-recovery backups are local-disk only — a full disk/machine failure loses both the live data and its backup. See `docs/DISASTER_RECOVERY.md`'s own "what this does NOT cover" section.
- **No automated backup schedule.** `scripts/backup_state.py` must be run manually; nothing currently triggers it on a cadence.
- **Paper mode ≠ real execution.** Paper trades never see real slippage, real spread, partial fills, or broker-side rejections. A clean paper-trading track record is evidence of *logic* correctness, not of real fill quality — expect live results to differ, especially on fill price and slippage.
- **Options backtest P&L uses a constant delta approximation** (`backtesting_engine/run.py`), documented as a known limitation. This affects backtest metric accuracy only — the live path was fixed this session to use real Fyers quotes and reject entries when no real premium is available, rather than substituting anything approximate.
- **EMA-crossover strategy fix backtested slightly negative on the most recent data window** (net -8.7% on the full 3.5yr sample, though better on the older 70%). This was a deliberate, user-approved tradeoff (closing a real logic gap took priority over the mixed backtest signal) — worth a second look if live results on this specific strategy underperform expectations.
- **Reconciliation logic is unit-tested but has only been observed against idle-time reconnects so far**, not yet a real disconnect during active market hours with open positions — §2.6 exists specifically to close this gap before sign-off.
- **No stress test for extreme-volatility/circuit-breaker-cascade scenarios** (e.g. a real gap-down open, or a burst of rapid-fire signals during a volatility spike). The paper-trading window is unlikely to naturally produce this; consider it an open gap even after §2 passes.
- **~25 frontend files still have `any`-typed values** in chart components and strategy-settings forms (out of scope, low risk — not on the money-handling path).

---

## §5. Evidence package required for final sign-off

Before `live_trading_mode` is ever flipped to `true`, assemble:

1. A `state.db` export (or `scripts/backup_state.py` snapshot) covering the entire clean validation window, with trade count and date range stated explicitly.
2. Log excerpts demonstrating §2.1–2.5 (zero crashes, zero save failures, zero mispriced/phantom/duplicate entries) across the full window.
3. The specific log lines for the §2.6 real reconnect-during-market-hours event, plus the manual verification against the broker's order book.
4. Documentation of the §2.7 and §2.8 tests (risk guard trigger, kill switch) — what was done, when, and the observed result.
5. The §2.9 manual PnL spot-check for 5 trades, shown side-by-side with what the app displayed.
6. Confirmation the §0 prerequisites are done: rotation date/confirmation for the Fyers key, and confirmation `trading-system/settings.json` no longer holds plaintext credentials.
7. This checklist itself, filled in with actual dates and evidence references — not left as a template.

## §6. Final decision

Once §0–§5 are all satisfied, this is a **human decision, not an automated
one.** The evidence package above is what informs that decision — it doesn't
substitute for it. Even with every box checked, start live trading with the
smallest capital/lot size the system allows, attended (not unattended), with
the panic-exit path within immediate reach.
