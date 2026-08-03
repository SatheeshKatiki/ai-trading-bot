# Production-Readiness Audit — 2026-08-03

Full-system audit across trading logic, P&L, order execution, risk
management, position reconciliation, exit management, broker integration,
data integrity, concurrency, and recovery, run against the live paper-mode
engine on 2026-08-03. This supplements `anomaly_log.md` (full chronological
detail, timestamps, evidence for every entry below) and
`reports/2026-08-03.md` (the day's trading-session report). This document
is the consolidated verdict.

**Scope honesty check, up front:** this audit ran entirely outside real
NSE market hours (from ~21:00 IST onward, market closed at 15:30). Every
fix below is verified by: full test suite (108/108 passing throughout),
targeted new regression tests for the exact gaps found, live restarts
against the running paper engine, and — where the fix touched something
observable live tonight (reconciliation, WebSocket reconnects, the daily
trade cap) — direct evidence from tonight's logs. What is **not** yet
verified: the corrected hard-SL/target/trailing-stop paths firing against
a freshly-opened position during real intraday price movement, since every
position opened tonight was immediately caught by the (now-fixed, also
verified) EOD square-off. That needs tomorrow's live session.

---

## Fixes shipped tonight (8 commits, chronological)

| # | Area | Finding | Severity | Fix verified |
|---|---|---|---|---|
| 1 | Broker integration | `active_broker: "dummy_test_broker"` caused every `BrokerFactory.get_active_broker()` call to tear down and rebuild the singleton, nulling the reference `run_live_bot()` held after the first options signal | Critical — blocked 100% of option entries | Live: first real trade since the fix |
| 2 | Data integrity | Option symbols built with invalid instrument prefix + wrong expiry weekday (Thu hardcoded; NSE moved to Tue) + wrong month-code format | Critical — blocked 100% of option entries, compounding #1 | Verified against Fyers' live symbol master |
| 3 | Exit management | `on_tick()` could never evaluate exit conditions for an option position — only the underlying was subscribed, and the position-match fallback explicitly excluded options | Critical — SL/target/trailing/EOD structurally unreachable for any option position | Live: EOD exit now fires correctly (see below) |
| 4 | P&L calculation | `pnl = (exit-entry)*qty*side` inverts sign for PUTs at 4 call sites (paper exit, live exit, unrealized M2M, reconciliation) — `side` encodes CE/PE direction, not long/short stance, and this system only ever buys options | Critical — every PUT trade's recorded PnL had the wrong sign | 108/108 tests incl. 2 new regressions for the exact untested PE+option case |
| 5 | Exit management | `SmartExitEngine.evaluate_exit()`'s hard SL/target/trailing/extremes logic used the short-underlying convention for `side=-1`, conflicting with how PUT SL/target are actually set (option-buying convention) — fired "Stop-Loss Hit" for almost any in-band PUT price | Critical | New `tests/test_exit_engine.py`, 15 tests, 0 prior coverage |
| 6 | Data integrity | Live occurrence: `active_positions.json` save failed with WinError 5 (transient Windows lock, likely a concurrent dashboard read), leaving it permanently stale — exactly the §2.2 zero-tolerance failure | Critical (reproduced live, not hypothetical) | Bounded retry added; live restart confirmed clean |
| 7 | Risk management | `PortfolioRiskEngine` constructed with `max_consecutive_losses=3`, contradicting its own documented 7-loss halt threshold and defeating the gradual size-scaling (0.5x/0.25x) it was built for | Serious (safe-direction failure — halts too early, not too late) | 108/108, isolated test construction unaffected |
| 8 | Risk management | `max_daily_dd_pct` settings-override fallback default (`0.05`) didn't match the percentage-scale (0-100) comparison it feeds | Minor, not currently reachable | Same pass as #7 |

All 8 are committed individually on `trading_bot_v2.10.0` with full
root-cause writeups. None touch strategy signal logic, entry/exit
*thresholds*, or risk *parameters* — every fix is plumbing, data-sourcing,
sign-convention, or wiring correctness.

---

## Areas reviewed with no fix needed

- **Order execution / idempotency** (`iceberg_manager.py`, rate limiter,
  `background_iceberg_entry/exit/scale`): single-threaded asyncio tick
  loop means no real concurrent-access race window; lock flags
  (`is_exiting`/`is_scaling`) are set synchronously before background
  tasks spawn; the code already shows awareness of "state may have
  changed while awaiting" in its own comments. `RateLimiter` (token
  bucket) is correctly thread-safe and mathematically sound.
- **Risk manager core** (`shared/risk/manager.py`): `can_trade()` is
  correctly wired into the entry path (confirmed via tonight's live
  "Trade BLOCKED... Max trades per day reached (3)" evidence — the daily
  cap fired exactly as configured). Daily IST-based reset logic has
  dedicated existing test coverage (`test_risk_daily_reset_ist.py`).
- **Credential handling**: Fernet (AES-128-CBC + HMAC-SHA256) with
  constant-time MAC comparison and key-rotation support — solid, already
  covered by the prior audit round (§1.9 of the Go/No-Go checklist).
  Outstanding items (Fyers key rotation, plaintext credential file
  cleanup) are pre-existing §0 action items, not new findings.
- **State persistence** (`shared/state.py`): WAL-mode SQLite, proper
  locking, background flush thread. One minor documentation/design
  nuance noted, not fixed: `record_trade()`'s docstring says trades
  "flush to disk immediately," but the actual mechanism enqueues to a
  background thread (typically <50ms latency) — a vanishingly small crash
  window could theoretically lose a trade record between the call
  returning and the flush completing. Not fixed tonight; flagged for
  awareness, not urgent (equity/pnl already reload from disk with a 1s
  TTL specifically to guard against exactly this class of staleness).
- **Reconciliation** (`trading_bot/reconciliation.py` beyond the PnL sign
  fix): the order-book-fill-vs-estimate resolution logic, short/long
  exit-side matching, and "still open on broker" skip logic are sound.
  Exercised live twice tonight (both real restarts), correctly.

## Found, not fixed — flagged for your decision

- **No market-hours gate on new entries.** The strategy happily generates
  and fills new signals long after real NSE close (repeatedly observed
  tonight, e.g. 21:20 and 21:45 IST) — there is no code anywhere that
  checks "is the exchange actually open" before evaluating or placing an
  entry. In live mode the exchange itself would reject the order, so this
  isn't a path to an erroneous *fill*, but it does mean wasted
  API/compute and log noise indefinitely outside hours, and it's the
  reason tonight's fix validation kept getting preempted by EOD
  square-off. Not fixed — this is a policy/session-hours decision, not a
  pure bug, and deserves your input on where the boundary should be
  (hard 9:15–15:30 gate? pre-market data allowed but no entries? etc.).
- **`DATA_LIMITER` (rate limiter for `get_market_data`/quote calls) is
  defined but wired to nothing**, anywhere in the codebase — including
  the new per-tick option-premium fetches my exit-monitoring fix added.
  Deliberately did not wire this in tonight: `DATA_LIMITER`'s current
  30/min budget looks calibrated for occasional polling, not a
  continuous per-tick position-monitoring loop, and getting the threshold
  wrong could cause missed exit checks (worse than the theoretical risk
  it protects against). Needs deliberate tuning, not a rushed patch.
- **"Trailing Stop-Loss Hit" label is effectively dead code** in
  `SmartExitEngine` — the hard SL check always catches a retraced price
  first since it re-reads the same, already-ratcheted `stop_loss` field.
  Cosmetic only (exits still fire at the financially correct price); not
  fixed.

---

## What still needs live market hours to fully close out

1. **Hard SL/target/trailing-stop paths, live, for a freshly-opened
   position** — every position opened tonight was caught by EOD
   square-off before these paths could fire against real, moving price
   data. Covered offline by the new 15-test `test_exit_engine.py` suite,
   but that's not a substitute for one real intraday cycle.
2. **A genuine WebSocket disconnect/reconnect during actual market hours
   with an open position** (checklist §2.6) — tonight's two reconnects
   (21:45, 22:02 IST) both happened after hours with no open position at
   the time.
3. **Kill-switch / panic-exit test** (§2.8) — not exercised this session.
4. **Manual 5-trade PnL spot-check** (§2.9) — meaningful once real
   intraday trades accumulate under the corrected PnL formula.

## Validation clock

Per `GO_NO_GO_CHECKLIST.md`'s own rule, any single failure resets the
window. Given the depth of what changed tonight (three separate critical
bugs across entry, exit, and PnL), the clean count restarts from
**tomorrow's first session opened after this audit**, not from any
earlier point today.
