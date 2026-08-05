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
