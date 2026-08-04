# Paper-Trading Validation — Anomaly & Fix Log

Running log of every anomaly, warning, and fix found during the continuous
paper-trading validation window (see `docs/GO_NO_GO_CHECKLIST.md` §2/§3).
Newest entries at the top. All timestamps IST unless noted.

---

## 2026-08-04 — live validation day (post-audit)

Validation clock restarts today per the 2026-08-03 audit note. Engine has
been running continuously since 2026-08-03 21:58 IST (no restart needed —
survived the overnight gap and midnight IST rollover cleanly).

### 12:00 IST — CRITICAL FIX (found ~23:24 IST review): PyramidSizer used the wrong convention for PUTs, same bug class as the exit-engine fix
Live-reproduced during today's first real trade sequence: a PUT position
(entry 55.15) triggered a pyramid scale-in at price 54.95 — **below**
entry — logged as `"Profit hit +0.36%"`. A price drop is a loss for a
bought PUT, not a profit.

**Root cause:** `shared/exits/pyramid_sizer.py`'s `PyramidSizer.evaluate_scale()`
had the exact same bug already fixed in `exit_engine.py` on 2026-08-03:
`if position.side == 1: profit = current - entry else: profit = entry -
current` — correct for a genuine short-the-underlying position, wrong
for a bought PUT (`side=-1` there encodes the directional bet, not
"short the contract" — this system only ever buys options). Net effect:
**the system would scale up (add more capital to) a losing PUT position
while believing it was compounding a winner** — the inverse of prudent
risk management, and one of the more dangerous classes of bug for
real-money trading. I did not check this class (zero test coverage
anywhere) during the 2026-08-03 audit — only `exit_engine.py` was
reviewed.

**Fix:** identical pattern — `effective_side = 1 if is_option else
position.side`, used for the profit-points calculation. `position.side`
itself untouched.

**Verified:** new `tests/test_pyramid_sizer.py` (6 tests, 0 prior
coverage) — PUT/CALL scale-in on rising vs falling premium, max-scales
respected, second-scale threshold higher than first. Full suite
114/114, no regressions. Restarted engine clean (no open position at
restart time).

**Reassuring finding while investigating this:** despite the *decision*
bug, the *quantity bookkeeping* around today's actual scale-in was fully
self-consistent — 65 (entry) + 32 (scale) = 97, exited via 48 (partial
booking) + 49 (final target) = 97, exactly reconciling. The bug affected
*when* to scale, not the arithmetic once a scale happened.

**Also noted, not fixed (cosmetic only):** the `PYRAMID SCALE` log/alert
text always shows `"SELL"` for a PUT scale-in (computed via a naive
`"BUY" if pos.side==1 else "SELL"`, not `is_opt`-aware) — misleading to
read, but confirmed the *actual* order construction two lines below
already correctly checks `is_opt` first (`OrderSide.BUY if is_opt else
...`), so this never affected real order sides or quantities.

### 10:31 IST — FIX: engine logging went silent while the process kept trading fine
At the 10:25 check-in, `engine.log` had stopped receiving any new lines
at 10:08:16 IST, ~20 minutes earlier — but `state.db`'s `last_update`
timestamp was still advancing in lockstep with wall-clock time (the
per-tick unrealized-P&L block writes it on every tick), proving the live
engine process was still running and trading normally. This was a
logging/observability bug, not a trading bug — verified before doing
anything else, specifically to avoid mis-diagnosing a healthy process as
broken.

**What actually happened:** right before the log went dark, `engine.log`
briefly filled with clearly non-live content — a "SECURITY ALERT:
broker_credentials.json integrity check FAILED", an "Iceberg Slice
failed: insufficient margin" from the **live-mode** order path (this
system is in paper mode — that branch is unreachable in real operation),
five different circuit-breaker trips firing back-to-back, an LSTM state
load referencing `__no_such_model__.zip.zip`, and a log line stating
"today is 2099-01-01". All of this is unmistakably a test run (almost
certainly the test suite, or a script exercising the live-order/LSTM
code paths with fixtures) — not this session's actual trading.

**Root cause:** `trading_bot/main.py` attached its `RotatingFileHandler`
for `engine.log` at **module level** (added last night, 2026-08-03,
alongside the original durable-logging fix) — meaning it ran on *any*
import of `trading_bot.main`, including by the test suite. When
something else imported this module around 10:08 IST, it attached a
*second*, independent handler instance pointed at the exact same file
path from a separate process. Whatever the precise OS-level interaction
(Windows file handle semantics around a second writer opening/rotating
the same path), the net effect was that the live engine's own handler
stopped successfully writing to the file after that point, silently (no
exception surfaced anywhere I could find) — while the trading logic
itself was completely unaffected throughout.

**Fix:** moved the file-handler setup from module level into the
`if __name__ == "__main__":` block, so only the actual live-engine
process ever attaches a handler to `engine.log` — importing this module
(tests, other scripts) no longer touches it at all.

**Verified:** full suite 108/108 (this itself exercises the exact import
path that caused the bug — confirms it no longer attaches a handler).
Restarted the engine; logging resumed immediately and normally. State
was consistent before restart (no open position), so no reconciliation
fired, correctly.

**Note for interpreting today's evidence:** none of the alarming-looking
lines described above (security alert, margin rejection, circuit
breakers, LSTM errors) reflect anything that happened in this session's
actual paper-trading engine — they're test-run artifacts that leaked
into the shared log file. Not counted as findings against today's
session.

### 10:07 IST — Engine down ~20 min during market hours, restarted
Check-in at 10:06 found `api_bridge` running under fresh PIDs (no
redirected log file — bare terminal invocation, same signature as the
user's manual restarts last night) but **no engine process at all**.
`engine.log` stopped cleanly at 09:46:48 with no error/traceback — not a
crash, just stopped. No code files had changed recently (api_bridge.py
last modified 20:56 IST *yesterday*), so this doesn't look like an
active edit-and-restart cycle either; most likely a manual restart that
didn't get followed up with restarting the engine.

**This is a real coverage gap:** the engine was not running for
~20 minutes of live market hours (09:47–10:07 IST), missing whatever
price action/signals occurred in that window. No supervisor/watchdog
exists to auto-restart it (a standing, previously-noted gap). Restarted
cleanly per the established procedure (state.db/active_positions.json
were consistent — 0 open positions, no stale data — so no reconciliation
event fired, correctly). Full suite re-verified (108/108) before
restart.

### 09:44 IST — Session-start check-in: healthy, quiet
- Both processes single-instance, `/health` OK.
- Zero crashes, zero "Failed to save active positions", zero phantom/
  mispriced trades so far today.
- One clean WebSocket reconnect during actual market hours (09:21:16 IST)
  — no position was open at the time, so this doesn't yet fully satisfy
  checklist §2.6 (which wants one verified *while holding a position*),
  but it's a real, clean market-hours reconnect/recovery cycle.
- Overnight (00:32–00:47 IST, pre-market) had a reconnect cluster — ~1
  per 87s, denser than the checklist's documented idle baseline (~1 per
  160s). Watching whether this recurs during market hours; not a §2.11
  violation on its own since it happened outside market hours.
- No trading signal yet 26 minutes into the session — confirmed this is
  quiet strategy behavior, not a stall: `state.db`'s `last_update`
  timestamp is advancing in lockstep with wall-clock time (the M2M
  unrealized-PnL block runs on every tick), so ticks are being received
  and processed normally; the `ema_rsi` strategy's own filters (squeeze/
  extension/CPR/aggression all enabled) simply haven't aligned yet, and
  the first 15 minutes have their own intentional no-trade window
  (`no_trade_filter.py`: opening-auction volatility, 9:15–9:30).
- Minor, low-priority cosmetic finding: `shared/sentiment` logs a
  "Translation failed" WARNING almost every ~5-minute sentiment fetch
  cycle (news headlines it can't translate). Harmless log noise, not
  fixed — flagging in case it's worth quieting for a cleaner audit trail
  over a multi-day window.

## 2026-08-03

### 21:58 IST — FIX: consecutive-loss circuit breaker halted at 3 losses, not the documented 7
`PortfolioRiskEngine` (`trading_bot/portfolio_risk.py`) is explicitly
designed and documented for gradual position-size scaling rather than a
binary halt: `get_position_multiplier()`'s own docstring says 3-4
consecutive losses → half size, 5-6 → quarter size, 7+ → halt, and its
class docstring says "Raised from 3 to 7 — at 3 we now reduce size, at 7
we halt." But `main.py`'s constructor call (`portfolio_risk =
PortfolioRiskEngine(..., max_consecutive_losses=3, ...)`) still passed
the pre-refactor value of 3 — so `_evaluate_risk()` fully halted trading
at exactly the loss count where size-reduction was supposed to begin.
The gradual-scaling behavior the class exists for could never actually
engage. Safe direction of failure (halts too early, doesn't expose more
risk than intended), but contradicts the system's own documented design
and would surprise anyone relying on that documentation. Fixed:
`max_consecutive_losses=7`, matching the class's own default and
documented intent.

Also fixed in the same pass, lower severity: the `max_daily_dd_pct`
settings-override fallback default was `0.05` against code that compares
on a 0-100 percentage scale (constructor default is `5.0` == 5%) — not
currently reachable since `max_daily_loss_pct` is always present in
`settings.json`, but would have meant an effective 0.05% daily-drawdown
halt if that key were ever missing. Fixed the fallback to `5.0` for
consistency.

Verified: full suite 108/108 passing (existing `test_risk_management.py`
constructs `PortfolioRiskEngine` with its own explicit params per test,
unaffected by this call-site fix). Restarted engine, healthy.

### 21:50 IST — FIX: live occurrence of the §2.2 zero-tolerance "Failed to save active positions" failure
Not a hypothetical — this happened live tonight during the audit, at
21:20:04.239 IST: `Failed to save active positions: [WinError 5] Access
is denied: '...active_positions_tmp_1tsia7wp.json' ->
'...active_positions.json'`, right after two back-to-back paper
entry/EOD-exit cycles. `_save_positions()`'s atomic-write pattern
(temp file + `os.replace()`) is correct in principle, but `os.replace()`
can transiently fail on Windows with WinError 5 if another process (most
likely `api_bridge.py` serving a dashboard request) has the destination
file open at that exact instant. The in-memory position state stayed
correct (the exit itself succeeded, PnL recorded correctly), but
`active_positions.json` on disk was left permanently stale — still
showing the closed position as open — until manually corrected.

**Fix:** wrapped only the `os.replace()` step in a bounded retry (5
attempts, 50ms×attempt backoff) — this is a transient OS-level lock
contention issue, not a real error, so retrying is appropriate here
(unlike this codebase's general style of failing fast rather than
masking real problems). Manually corrected the stale on-disk file to
`{}` (verified correct against `state.db`'s trade record before writing
it) and restarted — clean reload, no spurious reconciliation this time.

**Verified:** full suite still 108/108 after the fix; live restart
confirmed the stale-file correction stuck and no bogus "STATE MISMATCH"
fired since `active_positions.json` now matched reality.

### 21:40 IST — FIX: dashboard unrealized P&L always showed $0 for open option positions
Found while fixing the PnL sign bug above (same code region,
`main.py`'s section "3. Calculate Unrealized M2M PNL and update
dashboard"). Same root architectural gap as the exit-monitoring bug
fixed earlier tonight, but in yet another, separate code path I hadn't
touched: this section looked up an open option position's current price
via `aggregator.get_latest_dataframe(position.symbol)` — but the
aggregator only ever holds candles for subscribed symbols (the
underlying index), never an option's own symbol, so this always fell
through to `current_premium = entry_premium`, making the *displayed*
unrealized P&L for any open option position exactly $0 all session,
regardless of real movement. Fixed by fetching the option's live premium
on demand (reusing the same value already fetched this tick by the
exit-check block, via a small per-tick cache, to avoid a duplicate
broker call) plus the same PnL-sign fix as above.

### 22:00 IST — CRITICAL FIX: SmartExitEngine's hard SL/target/trailing logic used the wrong convention for PUT options
Found while writing regression tests for `shared/exits/exit_engine.py`
(zero existing test coverage anywhere) to validate the exit-monitoring
fix, independent of live market hours (which had ended, and EOD
square-off correctly preempts everything else right now, hiding this
bug from live observation).

**Root cause:** `SmartExitEngine.evaluate_exit()` branches on
`position.side` throughout (extremes tracking, hard SL/target, partial
booking, trailing stop) using the convention "side=1 → SL below entry
target above; side=-1 → SL above entry, target below" — correct for a
genuine short position in the underlying. But `trading_bot/main.py` sets
SL/target for **options** with SL always below entry and target always
above, *regardless of CE/PE* (its own comment: "Option buying means we
buy premium, so target is UP and SL is DOWN") — because this system only
ever buys options, and a bought PUT profits from a rising premium
exactly like a bought CALL. For a PUT (`side=-1`), those two conventions
directly conflict: with SL below/target above (option convention) fed
into logic expecting SL above/target below (short-underlying
convention), `current_price >= stop_loss` is true for almost any
in-band price, so the hard-SL branch fired "Stop-Loss Hit" immediately
for nearly any price at or above the numeric stop-loss value — which is
effectively always, except right after a sharp drop.

**Impact:** every section of `evaluate_exit()` was affected for PUT
positions — wrong extremes tracked (`lowest_price` instead of
`highest_price`), wrong hard SL/target evaluation, wrong trailing-stop
direction, wrong partial-booking profit calc. In practice, `main.py`'s
own separate, correctly `is_opt_pos`-aware hard interceptor (already
fixed earlier tonight) runs *before* this engine is reached and often
caught real SL/target crosses first — but any PUT position that stayed
in-band for a while (not this session's actual trade, whose premium
swung through both levels within 5 minutes) would have been killed
almost immediately by this bug, mislabeled as a stop-loss hit.

**Fix:** compute `is_option` once at the top of `evaluate_exit()` and use
`effective_side = 1 if is_option else position.side` for every
directional branch in the function. `position.side` itself is untouched
(other code still needs its original CE/PE meaning) — only this
function's internal decision logic changed.

**Verified:** new `tests/test_exit_engine.py` (15 tests, previously zero
coverage) — hard SL/target for both PUT and CALL, EOD cutoff behavior
and its date-prefix parsing, extremes tracking, ATR trailing-stop
ratcheting for both position types, partial profit booking. Full suite
108/108 passing (up from 93), no regressions. Minor, non-functional
observation from writing these: the distinct "Trailing Stop-Loss Hit"
label is effectively unreachable in the current code structure (the hard
SL check in section 3 always catches a retraced price first, since it
re-reads the same `stop_loss` field the trailing logic already ratcheted
on an earlier call) — exits still fire at the financially correct price,
just always logged as "Stop-Loss Hit". Cosmetic only; not fixed.

### 21:09 IST — CRITICAL, FIXED (21:45 IST): option PnL sign is inverted for PUTs
Found while validating the exit-monitoring fix (restart triggered
reconciliation on the stale position — see below). The reconciliation
log showed a **stop-loss hit recorded as a +21.95 profit**, which is
self-evidently wrong: a stop-loss exists to cap a loss, it cannot
produce a gain by definition.

**Root cause:** both `trading_bot/main.py`'s live exit path (`pnl =
(exit_check_price - open_position.entry_price) * qty_to_close *
open_position.side`) and `trading_bot/reconciliation.py`'s
`compute_reconciliation()` (`pnl = (exit_price - local_pos.entry_price)
* local_pos.quantity * local_pos.side`) multiply premium P&L by
`side`. For options this system only ever BUYS (long) — `side` is
repurposed at entry to mean "CE (+1) vs PE (-1)" directionally, not
"long vs short the contract." Since the trader is long the option
either way, profit should always be `(exit - entry) * qty`, full stop —
the CE/PE choice already encodes the directional bet by which contract
was bought. The `* side` multiplier is only correct for a genuine short
position in the underlying (confirmed intentional there — see
`test_closed_short_index_position_uses_buy_exit_side` in
`tests/test_reconciliation.py`, which explicitly asserts "negative side
flips the sign" for a short index position). Applying the same
convention to a bought PUT inverts its sign.

**Evidence this was never caught:** `tests/test_reconciliation.py` only
covers a CE with `side=1` (sign bug invisible, ×1 doesn't change
anything) and a short INDEX position with `side=-1` (correct use of the
flip). There is no test for a PE (`side=-1`, `is_option=True`) — exactly
the combination that's broken, and exactly what happened today.

**Impact:** every PUT trade's recorded PnL sign is inverted, in both the
live exit path and the reconciliation fallback path. This is a
checklist §2.9 ("P&L math checks out") blocker on its own, independent
of the exit-monitoring fix.

**Status: FIXED (21:45 IST), as part of the production-readiness audit.**
Fixed at all four call sites found: `main.py`'s paper-mode exit path
(`on_tick`), `main.py`'s live-mode exit path (`background_iceberg_exit`
— which had a *second*, related bug: it computed `is_opt` by checking
`"CE"/"PE" in sym`, but `sym` in that function is the base/underlying
key, e.g. `"NSE:NIFTY50-INDEX"`, never the option symbol — always False,
so the live exit path's `state_action` would have used the wrong
BUY/SELL convention for closing an option too; fixed by checking
`exit_req.symbol` instead), `main.py`'s unrealized M2M P&L calc for the
dashboard (§ below — this one had a second bug of its own), and
`trading_bot/reconciliation.py`. All four now use
`1 if is_option else side` instead of a bare `side` multiplier. New
regression tests added to `tests/test_reconciliation.py` covering the
exact previously-untested PE+option combination. Full suite passing, no
regressions.

### 21:05 IST — FIX implemented: option-position exit monitoring was structurally broken
Implemented the fix proposed below (user sign-off given). In `on_tick()`:
the position-matching fallback now includes option positions (previously
explicitly excluded); when the matched position is an option, its live
premium is fetched on demand via `broker.get_market_data()` (same call
already used at entry) into a new `exit_check_price`, which now feeds
every exit-side decision that previously used the raw index tick's `ltp`
— hard TP/SL interceptor, the `institutional_momentum` and default
(`exit_engine.evaluate_exit`) exit paths, exit order pricing, PnL calc,
and trade/alert recording. Also fixed the identical bug in the adjacent
pyramiding (scale-in) block, which had the same "index price fed into
option-premium comparison" defect — same root cause, same fix pattern,
found while making this change. If the on-demand premium fetch fails for
an option position, the exit check is skipped for that tick (logged) and
retried on the next one, rather than proceeding with a wrong price.
Left the ATR-from-candles calculation itself untouched (still an
index-based approximation for options — a real option-specific ATR would
need a live option candle series, which doesn't exist; flagged as a known
limitation, not fixed, since building that is new functionality, not a
plumbing fix).

Verified: `py_compile` clean, full test suite (`pytest tests/ -k "not
test_bt"`) 95/95 passing, no regressions.

**Incident during verification:** running that test suite wrote 2 fake
`NIFTY-RATELIMIT-TEST` rows directly into the live `state.db`
(`tests/test_order_rate_limit.py` hits the real `/api/order/execute`
endpoint with no DB isolation — the exact same class of test pollution
the original pre-2026-08-03 audit already flagged once). Caught
immediately via a routine trade-count check, deleted the 2 polluted rows,
reset `sqlite_sequence`. **Do not run the full `pytest tests/` suite
against this live environment without first confirming `state.db`
isolation** — `test_order_rate_limit.py` at minimum needs to be run
against an isolated DB path, or this will keep recurring every time the
suite runs here.

### CRITICAL — Open option positions can never be exited by the system (found ~20:30 IST, end-of-day review)
**Symptom:** the one trade placed today (10:34:10, `NSE:NIFTY2680424600PE`)
stayed open, untouched, for the rest of the session — `active_positions.json`
still shows `highest_price`/`lowest_price` frozen at the entry price.

**Root cause:** `trading_bot/main.py`'s `on_tick()` only evaluates exit
conditions (SL/target/trailing) when the incoming tick's symbol matches
`position.symbol` exactly, with a fallback that explicitly excludes
options. The live stream only subscribes to the underlying index
(`NSE:NIFTY50-INDEX`), never the option contract, and `get_market_data()`
is called exactly once in the entire file — at entry. A comment
referencing an "EOD exit at 15:15 IST" has no corresponding
implementation anywhere. **Net effect: once an option position opens, the
system's own stop-loss/target/trailing/EOD rules are structurally
incapable of ever firing.**

**Quantified impact:** the option's actual premium swung from 74.50 to a
high of 77.70 and a low of 71.00 within the very first 5-minute candle
after entry — target and stop-loss were both touched almost immediately.
Had the exit mechanism run at all, this trade would have closed near
breakeven. Instead the premium drifted to ~59–60 by end of day (session
low 52.10), an unrealized mark-to-market loss of roughly -21% to -30% on
premium that never got the chance to be capped at the configured 0.45%
stop.

**Status:** NOT YET FIXED — flagged for user sign-off before touching the
live position-management hot path (see `reports/2026-08-03.md` §7 for the
proposed fix). This finding supersedes the 10:34 entry below as the day's
most severe issue.

**Validation clock impact:** resets per checklist rule — today's session
does not count. See `reports/2026-08-03.md` §7.5.

### 10:34 IST — Session stabilized, first clean trade recorded
After the fixes below, engine restarted cleanly with a single `main.py` +
single `api_bridge.py` instance. First real paper trade of the validation
window: `BUY PUT NSE:NIFTY2680424600PE qty=65 @ 75.05 | SL=74.71 | TGT=77.68`
— recorded correctly in `state.db` (trade id 1) and `active_positions.json`.
Realistic premium, real qty, correct SL/target math. No crashes since.

### 10:20 IST — Process collision with user's own manual restart
While restarting the engine to pick up fixes, the user independently
restarted `api_bridge.py` from their own terminal at the same time. My
`main.py` instance died silently with no traceback (most likely killed
manually, not a crash — the log simply stopped, stderr was empty). No
corruption resulted (state.db stayed at 0 trades throughout). Confirmed with
user and proceeded to bring the engine back up cleanly. **Not a code
issue** — a coordination gap between concurrent operators on the same
machine. Noted here as an operational reminder, not a system defect.

### 10:19 IST — FIX (root cause): `active_broker` misconfiguration caused every broker call to tear down and recreate the singleton
**Symptom:** every option-entry attempt logged
`Could not fetch live option premium for <symbol> — skipping this entry`,
100% of the time, regardless of symbol correctness.

**Root cause:** `config/settings.json` had `"active_broker": "dummy_test_broker"`,
an unregistered broker ID. `BrokerFactory.get_active_broker()` (`brokers/broker_factory.py`)
compares the *configured* broker ID against the *resolved* one on every
call; since `"dummy_test_broker"` can never equal the actual fallback
(`"fyers"`), **every single call anywhere in the process** (not just
`run_live_bot`'s own) was treated as "configuration changed" and tore the
broker down (`close()` → `_fyers_model = None`) and rebuilt it.
`trading_bot/main.py`'s `run_live_bot()` fetches `broker` once at startup
(line 349) and reuses that reference for the rest of the session. The very
first options signal independently calls `BrokerFactory.get_active_broker()`
again (via `_fetch_dynamic_lot_size()` in `options_selector.py`), which
tore down the instance `run_live_bot()` was still holding — permanently
nulling its `_fyers_model`, so every subsequent `get_market_data()` call
returned `{}` for the rest of the process's life.

**Fix:** `config/settings.json` — `active_broker` changed from
`"dummy_test_broker"` to `"fyers"` (the broker it was always silently
falling back to anyway; this makes the resolved and configured IDs match,
so the spurious teardown never fires). Pure config fix, no code touched
for this one, no strategy logic affected.

**Verified:** restarted engine — zero `"configuration changed, refreshing
active broker"` log lines after startup, and the very first option signal
successfully fetched a real premium and placed a trade (see 10:34 entry).

### ~10:12 IST — FIX: option symbols were being built with an invalid instrument prefix and the wrong expiry weekday
**Symptom:** every constructed option symbol
(e.g. `NSE:NIFTY5026AUG0624600PE`) was rejected by Fyers with
`"Please provide a valid symbol"` — confirmed via direct Fyers `quotes()`
call outside the app. This alone would have permanently blocked every
option entry for the whole validation window, independent of the broker
bug above.

**Root cause, two compounding bugs:**
1. `trading_bot/main.py` (~line 1113) derived the options instrument name
   by naive string-stripping the underlying data symbol
   (`"NSE:NIFTY50-INDEX"` → strip `NSE:`/`-INDEX` → `"NIFTY50"`), but the
   real Fyers option series is `"NIFTY"`, not `"NIFTY50"`. This fed
   `"NIFTY50"` into the symbol builder as the instrument prefix.
2. `trading_bot/strategies/premium_selection/options_selector.py`'s
   `INSTRUMENT_CONFIG["NIFTY"]["expiry_day"]` was hardcoded to Thursday
   (3). Verified against Fyers' live `NSE_FO`/`BSE_FO` symbol master
   (`public.fyers.in/sym_details/`) that NSE has consolidated NIFTY/
   BANKNIFTY/FINNIFTY weekly index-options expiry to **Tuesday**, and
   SENSEX (BSE) weekly expiry is **Thursday**, not Friday. The stale
   config computed a non-existent expiry date, compounding the invalid
   symbol. Also, `_build_symbol()`'s format
   (`{YY}{MMM 3-letter}{DD}{STRIKE}{TYPE}`) never matches any real Fyers
   convention — real weekly symbols use a single-character month code
   (`1`-`9`, `O`, `N`, `D`) with no letter month, and real monthly
   (last-occurrence-of-weekday-in-month) symbols drop the day entirely
   (`{YY}{MMM}{STRIKE}{TYPE}`).

**Fix:**
- `main.py`: map `"NIFTY50"` → `"NIFTY"` and `"NIFTYBANK"` → `"BANKNIFTY"`
  before passing the instrument name to `select_option()`.
- `options_selector.py`: corrected `expiry_day` for NIFTY/BANKNIFTY (Thu/Wed
  → Tue) and SENSEX (Fri → Thu); FINNIFTY was already correct (Tue).
  Rewrote `_build_symbol()` to produce the real monthly-vs-weekly format,
  and to use the canonical instrument key rather than the caller's raw
  string.

**Verified:** built symbols for both a weekly (`NSE:NIFTY2680424650PE`) and
a monthly-boundary case (`NSE:NIFTY26AUG24600PE`) and confirmed both
resolve to real, live Fyers quotes (₹101.25 and ₹219.55 respectively at
the time of testing) via a direct out-of-process `quotes()` call.

### 09:59 IST — FIX: Fyers "no candles yet today" response misclassified as an error
**Symptom:** `fyersApi.log` showed `Fyers history API chunk failed (Attempt
1/2/3)` repeatedly, every ~15-20s, coinciding with the dashboard's chart
auto-refresh. Each occurrence burned 3 retries + ~6s of backoff for a
call that was never going to succeed differently.

**Root cause:** `brokers/fyers_broker.py`'s history-chunk retry loop only
recognized the string `"No data available"` as a legitimate empty
response; Fyers actually returns `{"s": "no_data", "code": 200, ...}` for
a date range with no candles yet (e.g. today's still-forming bars), which
fell into the retry/failure branch instead.

**Fix:** treat `resp.get("s") == "no_data"` the same as the
`"No data available"` string match — accept it immediately, no retries.

**Verified:** confirmed the real Fyers response shape directly
(`{'candles': [], 'code': 200, 'message': '', 'nextTime': ..., 's':
'no_data'}`) before and after the fix.

### 09:59 IST — FIX (infra): `trading_bot/main.py` had no durable log file
Only logged to its own console window (`logging.basicConfig(stream=sys.stdout)`),
invisible to anything monitoring the process from outside — unlike
`api_bridge.py`, which already rotates to `fyersApi.log`. Added a
`RotatingFileHandler` (5MB × 5 backups) writing to `trading-system/logs/engine.log`,
alongside the existing stdout stream. This is the log this validation
window's monitoring reads from. No behavior change to the engine itself.

### 09:50 IST — Process hygiene: killed an accidental duplicate `main.py`
While bringing the system up, briefly ran a second `trading_bot.main`
instance in parallel with one the user had already started at 09:40 IST
(before I began working). Caught it immediately via process/command-line
inspection before either produced a trade or touched `state.db`, killed
the duplicate. No corruption — `trades` stayed at 0 throughout. Documented
as a reminder that this system does **not** guard against multiple
concurrent engine instances; process hygiene has to be enforced externally
every time it's (re)started.

### Pre-existing, not caused by this session — Fyers history REST calls fail during paper mode by design
`brokers/fyers_broker.py`'s `authenticate()` skips real authentication
entirely in paper mode (`Fyers: paper mode — skipping real authentication`)
and only initializes a data-fetching model if a cached token happens to
exist. Live ticks come through `api_bridge`'s authenticated WebSocket feed,
not this path — so this is expected, not a defect. Noted for context, not
tracked as an open issue.

---

## Severity / disposition summary (as of 2026-08-03 10:35 IST)

| Finding | Severity | Status |
|---|---|---|
| `active_broker` misconfig causing broker-singleton teardown loop | **Critical** — blocked 100% of option entries | Fixed, verified |
| Invalid option symbol construction (instrument name + expiry weekday + format) | **Critical** — blocked 100% of option entries | Fixed, verified |
| `no_data` misclassified as history-fetch error | Low — log noise + wasted retries, no trading impact | Fixed, verified |
| No durable engine log file | Medium — blocked all external monitoring | Fixed |
| Duplicate engine process (self-inflicted, caught immediately) | N/A — process hygiene note | Resolved, no impact |

**Validation clock:** per `GO_NO_GO_CHECKLIST.md` §2, "any single failure
resets the clock." The two critical fixes above mean no option-strategy
trade could have completed correctly before 10:34 IST today — clean
counting for §2 starts from **2026-08-03 10:34 IST**, not from the
`state.db` reset earlier in the day. `trades` table remains a true record
either way (0 rows before this trade), so no data was lost or needs
re-baselining — only the clock's start reference for the 10-session/
30-trade criterion moves to reflect when the system was actually capable
of trading correctly.
