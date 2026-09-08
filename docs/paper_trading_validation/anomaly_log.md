# Paper-Trading Validation — Anomaly & Fix Log

Running log of every anomaly, warning, and fix found during the continuous
paper-trading validation window (see `docs/GO_NO_GO_CHECKLIST.md` §2/§3).
Newest entries at the top. All timestamps IST unless noted.

---

## 2026-09-09 — FIX: the entire Options Desk was fiction — fake India VIX, fake IV Rank, "Max Pain" that was just the ATM strike, a random PCR, and an expiry six weeks in the past

**How it surfaced:** chasing the fabricated `India VIX` pill
(`14.2 + Math.sin(Date.now()/60000) * 1.5`) found by the audit, then reading
what else the `/api/option-chain` payload actually contained.

**Root cause:** `get_option_chain()` is a Black-Scholes *model*, not a broker
feed — its own docstring says "live or simulated" — and everything derived
from it was presented as market data:

| Field | What it really was |
|---|---|
| `India VIX` (UI) | `14.2 + Math.sin(Date.now()/60000) * 1.5`, colour-coded red above 18 as a risk signal |
| `IV Rank` (UI) | `35 + Math.sin(Date.now()/90000) * 20` |
| `maxPain` | `atm_strike` — the ATM strike relabelled. By construction "distance to max pain" was **always zero** |
| `pcr` | `deterministic_random(base_price, 99, 0.6, 1.4)` — an MD5 hash of the spot price, unrelated to the OI table printed beside it |
| `expiry` | hardcoded `"2026-07-25"` — already six weeks in the past |
| premiums / Greeks / OI / volume | Black-Scholes on a `deterministic_random()` implied vol |
| header badge | a green **"LIVE"** over all of the above |

This matters beyond display: `paper_observer.select_best_option()` reads
`ltp`, `delta` and `pcr` from this chain to choose strikes and set entry
premiums, so paper-trade fills are theoretical prices. Real NIFTY weekly
premiums diverge from Black-Scholes by bid-ask spread, volatility skew and
liquidity, so the validation window's P&L measures the model, not the market.

**Fix — real where real is possible, honest everywhere else:**

* **India VIX is now real.** It is an ordinary NSE index; subscribed as
  `NSE:INDIA VIX-INDEX` on the live Fyers feed alongside the other indices and
  served on the chain payload as `indiaVix` with `src`/`ts`, or `null`. The UI
  shows an em-dash when it is unavailable rather than inventing one.
* **IV Rank removed, not faked.** It is by definition the current IV
  percentile against a trailing (typically 1-year) IV history, and this system
  stores no historical implied-volatility series, so it cannot be computed
  from anything available. Deleted rather than approximated.
* **Max pain is now actually computed** — the strike minimising total
  intrinsic value owed to buyers — so it can finally diverge from ATM and mean
  something.
* **PCR is computed from this chain's own open interest**, so it is at least
  internally consistent with the table beside it; `null` when there is no CE OI.
* **Expiry** delegates to `premium_selection._next_expiry()`, the same
  resolver the live strike selector uses, so the desk and the trading path can
  never disagree about the contract series. Resolves to 2026-09-15 today.
* **Provenance is stated, loudly.** The payload carries
  `synthetic: true`, `priceSource: "black_scholes_model"` and
  `realFields: ["underlying_price", "indiaVix"]`. The UI replaces the green
  "LIVE" badge with an amber **"MODEL CHAIN"** and shows a banner above
  the table saying in plain words that only spot and VIX are real and that
  P&L booked against the chain measures the model.

**Verification:** `test_option_chain_metrics.py` (9 tests, new) pins the max
pain and PCR maths against hand-computed books — including a skewed chain
where max pain lands at 23700 while ATM is 24000, the divergence the old
`maxPain: atm_strike` could never express — and asserts the expiry resolves,
is not in the past, and matches the live strike selector. Suite **730 passed
/ 2 xfailed**. `tsc` clean, build green.

**Still open — needs a decision (not fixed here):** the chain remains model
output. The real fix is wiring Fyers' actual option-chain endpoint so premiums,
OI and IV are traded values. Until then, paper-trading P&L should not be read
as evidence of live performance. Related: `MarketEnvironmentFilter`'s "VIX safe
band" gate and `institutional_momentum`'s adaptive-Donchian `daily_vix` are
never given a value by `main.py` (default 15.0), so both run blind — now
fixable since a real VIX exists, but wiring it changes trade admission and
wants a backtest first.

---

## 2026-09-09 — FIX (CRITICAL): six code paths fabricated market prices, and they reached the live trading engine — not just the dashboard

**How it surfaced:** a full read-only project audit noticed that v3.13.0's
yfinance fallback in `api_bridge.py` manufactured five interpolated
"micro-ticks" per second between real polls. Tracing who consumes them turned
a display concern into a critical one.

**Root cause — the consumption path nobody had traced:**

```
current_market_data          (api_bridge.py)
  -> snapshot                (websocket_broadcaster)
  -> websocket_data["raw_ticks"]
  -> /ws/live
  -> FyersBroker.stream_quotes()          (brokers/fyers_broker.py:807)
       await on_tick({"symbol": sym, "ltp": val["lp"], ...})
  -> trading_bot/main.py on_tick()        <-- NO market-hours or quality gate
  -> CandleAggregator -> strategy -> ENTRY / EXIT / mark-to-market P&L
```

Every price was a bare `{"lp", "chp"}` pair with no record of where it came
from, and **six** separate places were allowed to invent one:

| # | Location | What it invented |
|---|---|---|
| 1 | `current_market_data`'s literal seed | NIFTY 23820.35 / SENSEX 76015.28 / BANKNIFTY 51000.00, served as real from process start |
| 2 | `websocket_broadcaster`'s `if not current_market_data:` re-seed | a *different* invented set (23971.88) |
| 3 | `get_sim_tick()` | sine-ish wiggle broadcast whenever the market was closed |
| 4 | v3.13.0 yfinance fallback | 5 interpolated micro-ticks/sec, falling back to hardcoded 23840 / 57080 / 76260 if yfinance itself failed |
| 5 | `useLiveMarketStore.ts` initial state | same three hardcoded index quotes, client-side |
| 6 | `live-ticker.tsx` initial state | five invented quotes incl. RELIANCE 2950.00, TCS 3950.00, on the main dashboard |

Paths 1–4 all fed `raw_ticks`, so the strategy could open and close positions
against prices that never existed. Path 4's failure mode is the realistic one:
`run_auto_auth()` failing does not abort the session, so a token-less morning
would have had the engine trading a sine wave while the EOD Telegram card
reported the resulting P&L as a real result.

**Fix — a price now carries its provenance, and nothing fabricates one:**

* `make_tick(lp, chp, src, ts)` is the only way to construct a market-data
  entry. `src` ∈ `fyers` / `broker` / `yfinance` / `pending`, `ts` is the real
  observation time.
* `current_market_data` starts **empty**. An empty feed is an honest feed.
* All six fabrication sites removed. The yfinance fallback now publishes only
  what it actually observed (real `lastPrice`, real `previousClose`-derived
  change%, 5s cadence — the old 1s hammering bought no information, these
  quotes are delayed anyway) tagged `src="yfinance"`.
* **The engine gate**: `select_tradeable_ticks()` — a pure, directly-testable
  function — is now the single definition of "tradeable". `raw_ticks` carries
  only ticks that are authoritative (`fyers`/`broker`), priced (> 0) and fresh
  (≤ 30 s). Everything else is still broadcast for display, clearly tagged,
  but the engine receives nothing for it and therefore does nothing — the
  correct behaviour when you cannot see the market.
* The broadcast gained a `feed` block (`status: live|degraded|down`, sources,
  tradeable count, `simulated: false`) so the UI states feed health instead of
  inferring it from socket liveness — the 2026-08-12 zombie-socket incident
  was exactly a healthy socket carrying no data.
* `market-ticker.tsx` renders `—  NO FEED` for a missing price and a muted
  `YFINANCE · DELAYED` badge for a non-tradeable one. It previously rendered
  `?? 0`, i.e. a confident "₹0.00" with a green up-arrow. `live-ticker.tsx`
  shows "Waiting for market data feed…".

**Verification:** `test_market_data_provenance.py` (16 tests, new) pins the
gate — yfinance, pending, zero-price, stale, and legacy untagged ticks are all
rejected; authoritative fresh ticks pass; malformed entries do not crash it.
An end-to-end scenario run confirms the engine receives **nothing** in all
five failure states (cold boot, old seed values, yfinance fallback, stale
market-closed tick, unpriced subscription) and only trades on a genuine live
Fyers tick. Full backend suite **721 passed / 2 xfailed**; `tsc --noEmit`
clean; `npm run build` green.

**Behaviour change worth knowing:** index prices no longer drift after market
close, because the sine-wave generator is gone. A flat price when the market
is shut is correct; the previous movement was fabricated.

---

## 2026-09-09 — FIX: the zero-touch watchdog relaunched the Paper Observer 370 times and burned the first two hours of the 2026-09-07 session

**How it surfaced:** a full read-only project audit grepped
`logs/daily_orchestrator.log` and found the same WARNING line 370 times:

```
[2026-09-07 09:14:24] [WARNING] Paper Observer process stopped unexpectedly! Auto-restarting...
   ... one every 20 seconds ...
[2026-09-07 11:17:29] [WARNING] Paper Observer process stopped unexpectedly! Auto-restarting...
```

`logs/paper_observer_stdout.log` shows the matching child side — 372 copies
of the startup banner, each followed immediately by:

```
  [AUDIT COMPLETE] All 3 live trading sessions completed!
```

**Root cause:** the observer was **not crashing**. That run was still the
pre-v3.13.0 3-day-capped build, so it hit its own `break`, printed the audit
scorecard and exited **cleanly with returncode 0** in about two seconds,
every single time. The watchdog in `auto_daily_session.py` only asked:

```python
if observer_proc and observer_proc.poll() is not None:
    logger.warning("Paper Observer process stopped unexpectedly! Auto-restarting...")
    start_paper_observer()
```

`poll() is not None` is true for *any* exit. The supervisor had no notion of
**why** a child stopped, so it spent two hours fighting the child's own
deliberate, successful decision to stop. Net effect: **no paper trading at
all for the first two hours of the session**, plus 370 identical "Market is
OPEN" Telegram messages (the announcement lived inside the launch function)
and 372 leaked stdout file handles (`open(...)` on every restart, `close()`
never).

The v3.13.0 "perpetual paper trading" change removed *one specific trigger*
for this — the 3-day cap — but left the watchdog defect itself completely
untouched. Any future early exit would reproduce it exactly.

**Fix:** replaced the poll-and-relaunch watchdog with a real
`ServiceSupervisor` that decides whether an exit is even worth restarting:

| Exit condition | Old behaviour | New behaviour |
|---|---|---|
| `returncode == 0` (observer) | relaunch forever | honour it, escalate **once**, stand down |
| `returncode != 0` | relaunch every 20 s | restart behind a `0/5/15/30/60/120/300 s` backoff ladder, ceiling of 5 per burst, then escalate and stand down |
| crash after a long healthy run | — | uptime ≥ 120 s starts a **fresh** burst, so a service that stays healthy is never abandoned |
| `returncode == 0` (API bridge) | relaunch forever | still a fault — a server is never "done" — so it *is* retried, but under the same ladder and ceiling |

Also fixed in the same pass, all consequences of the same defect:

* the "Market is OPEN" Telegram announcement now fires only on launch #1;
* `ServiceSupervisor` owns the child's stdout handle and closes the previous
  one on every restart and on `stop()`;
* `reset()` clears the give-up latch at the start of each session, since the
  supervisors are module singletons that outlive a day in `--daemon` mode
  (without it a Monday give-up would leave the service unsupervised all week);
* the **same thrash defect one level up**: `run_daemon_loop()` re-entered
  `run_session_flow()` immediately whenever it returned early (e.g. "Failed to
  start backend service. Aborting session."), re-running auto-auth and port
  kills in a tight loop for the rest of the day. Now capped at 3 attempts per
  day with a 5-minute cool-off and a one-time alert.

**Verification:** `test_orchestrator_supervisor.py` (8 tests, new) replays the
real timeline — a child exiting code 0 after 2 s against 370 twenty-second
watchdog ticks. Old code: 370 launches. New code: **1 launch**, one alert,
`given_up = True`. The suite also pins the backoff ladder spacing, the
crash ceiling, the healthy-uptime burst reset, the API-bridge clean-exit
exception, the give-up latch reset, and file-handle release. Full backend
suite: **705 passed, 2 xfailed**.

**Still open (not a code fault):** the observer that ran on 2026-09-07 was a
stale build. Worth confirming the orchestrator always launches the current
checkout before the next unattended session.

---

## 2026-08-28 (16:00 IST) — FIX: the CPU-livelock `Series.__setitem__` antipattern was re-introduced into the live-active strategy on 2026-08-08

**How it surfaced:** a status-check of the running engine (started late, 13:20
IST — well into the session) found `main.py`'s worker process holding
~50–70% of a CPU core with `engine.log` showing nothing past `Connected to
API Bridge WebSocket!` for 2.5 h. `py-spy dump` on the live PID caught the
hot thread here:

```
generate_signals (trading_bot/strategies/ema_rsi_strategy.py:147)
  Series.__setitem__ -> Series._set_with_engine -> Index.get_loc
  -> Series.__repr__ -> to_string -> adjoin   (pandas/io/formats/printing.py)
```

**Root cause:** the edge-trigger step added to `ema_rsi` on 2026-08-08
(commit `36afdc0`) was written as a boolean-mask assignment —

```python
signals[(signals == signals.shift(1)) & (signals != 0)] = 0
```

— which is the *exact* signature the 2026-08-06/07 audits rewrote
`registry.py` and this same file's signal *construction* to avoid (see the
2026-08-06/07 entries below and the module-level comment at
`ema_rsi_strategy.py` ~line 110). Under a `DatetimeIndex` that is
duplicate-laden or non-monotonic, pandas stops treating the mask as
boolean and routes the assignment through `_set_with_engine ->
Index.get_loc`, doing a label lookup *and building a full-Series repr for
the resulting error message* per row. `ema_rsi` is the live-active
strategy and this runs on every evaluation. The `Series.__repr__` /
`to_string` / `adjoin` frames in the dump are the tell — that is pandas
constructing an exception message, not doing arithmetic.

The identical line had been copied into two other strategies in the same
2026-08-08 edge-trigger pass / earlier: `advanced_ai_ml_strategy.py:274`
(commit `5be0d66`, plus a dead no-op `.where(...)` line above it) and
`ultra_meta_dip_swarm.py:91-92` (`signals[valid_call] = 1` /
`signals[valid_put] = -1`, construction-side, dating to 2026-07-09 —
missed by the original audit).

**Fix:** new shared helper
`trading_bot/strategies/_signal_utils.py::edge_trigger(signals)` computes
the same result on the underlying numpy array (`np.where` on a shifted
comparison), no `Series.__setitem__`. All three strategies now call it
(`ultra_meta_dip_swarm` uses the `np.select` construction form already
used by `registry.py` / `ema_rsi`). Semantics are unchanged — a run of an
identical non-zero signal still collapses to its opening bar, a direction
flip still fires immediately, bar 0 is always kept.

**Tests:** new
`Testing_Automation_AI_Trading_Bot/python-unit/test_edge_trigger_livelock_regression.py`
— pins `edge_trigger` equivalence to the pre-fix setitem oracle,
hand-worked edge cases, sub-1 s completion on a 1500-row duplicate
`DatetimeIndex` (the shape that triggers the livelock), a guard that no
strategy keeps a live boolean-mask edge-trigger in code, and an
end-to-end "each strategy completes fast on a duplicate index" check.
Full suite: **643 passed, 2 xfailed** (pre-existing `drl_strategy`
market-blindness).

**Verified live:** killed the wedged pre-fix worker (PID 7408), relaunched
`main.py` (PID 21668) with the fix. `py-spy` on the new process no longer
shows the `get_loc -> __repr__ -> adjoin` signature anywhere; the
`ema_rsi` strategy profiles at ~92 ms/call on 1800 rows (was effectively
unbounded on the bad index). Market was closed by restart time, so the
first *market-hours* confirmation is still pending — next live session
should re-check `py-spy` and per-eval latency.

**Still open (flagged, not fixed — needs a human call):** `on_tick`'s
"ZERO-LATENCY HFT TRIGGER" re-evaluates the *entire* feature +
strategy + institutional-filter stack on the full candle DataFrame at up
to 5×/s (200 ms throttle), driven by `api_bridge.py`'s
`websocket_broadcaster` which pushes a snapshot every 50 ms **regardless
of whether a new tick arrived, and regardless of whether the market is
open**. Even with this livelock fixed that is ~140–180 ms of work every
200 ms → ~70% of a core burned continuously, 24/7. It is what turned this
livelock from "slow" into "engine silent for 2.5 h". Options: gate the
eval loop on `market_open`, only re-evaluate on a genuinely new
bar/tick, or evaluate on `df.tail(N)` instead of the whole history.
Deferred because throttle/cadence is a design decision, not a wiring bug.

**Note:** `engine.log` being quiet during a session is now partly
expected — the `shared.sentiment` INFO chatter that used to dominate it
moved to `api_bridge.py`'s `fyersApi.log` in v2.11.0. It is not, by
itself, a sign the engine is wedged; cross-check `py-spy` / CPU / the
`main_heartbeat.txt` mtime.

---

## 2026-08-28 — FIX: two `trading_bot/main.py` infra issues found reviewing `engine.log` for 2026-08-24–26 (no session was run those days; found via a status review, not live monitoring)

**Finding #1 — option auto-map crashed on a zero spot price:**
`engine.log` showed 12 occurrences on 2026-08-25 of `Failed to auto-map
option for NSE:NIFTY50-INDEX: expected a positive input, got 0.0`.
Root cause: `on_tick`'s auto-map block passed `ltp = tick["ltp"]`
straight into `options_selector.select_option()` → `calculate_greeks()`'s
`math.log(spot / strike)` with no check that `ltp` was a real, positive
price — a malformed/keepalive tick with `ltp=0.0` hit `math.log(0.0)`,
which raises exactly that message. Caught by the auto-map block's own
broad `except Exception`, so no crash — `option_mapping_succeeded` stayed
`False` and the existing `_should_abort_missing_option_mapping` gate
(2026-08-07 audit fix) correctly skipped the entry — but it was noisy and
one data-validity check away from being unnecessary. **Fix:** extracted
`_has_valid_spot_price_for_option_mapping(ltp)` and guard the auto-map
attempt with it — a non-positive `ltp` now logs a clear warning and skips
straight to the existing abort gate, never reaching the Black-Scholes
math. Regression tests:
`Testing_Automation_AI_Trading_Bot/python-unit/test_option_mapping_invalid_spot_price.py`
(pins the guard predicate and documents `calculate_greeks(0.0, ...)`'s
exact failure mode).

**Finding #2 — heartbeat writes logged spurious ERRORs on a known race:**
6× `Heartbeat write failed: [WinError 5] Access is denied` clustered
2026-08-26 14:35–14:41 IST. Same mechanism `_save_positions` was already
fixed for on 2026-08-03 (`api_bridge.py`'s `main_process_watchdog` reads
`main_heartbeat.txt` via `Path.read_text()` every 30s, racing `main.py`'s
`os.replace()` of the same file every ~15s) — `_write_heartbeat` just
never got the same bounded retry, on the reasoning that losing a single
write is harmless (next write is ≤15s away). That reasoning still holds,
but the transient failure doesn't need to be a logged ERROR either.
**Fix:** applied `_save_positions`' existing 5-attempt bounded-retry
pattern (0.05s × attempt backoff) to `_write_heartbeat`'s `os.replace()`
call — same tolerance for a genuine miss, just rarer now. Regression
tests added to
`Testing_Automation_AI_Trading_Bot/python-unit/test_main_heartbeat.py`
(`test_write_heartbeat_retries_past_a_transient_replace_failure`,
`test_write_heartbeat_gives_up_after_five_persistent_replace_failures`).

**Verification:** `python -m py_compile trading_bot/main.py` clean; full
`Testing_Automation_AI_Trading_Bot/python-unit` suite — 635 passed, 2
pre-existing unrelated xfails (both `drl_strategy` model-collapse, see
that test's own docstring), 0 failures. Not yet verified against a live
running engine — the engine was not running at the time of this fix (no
python process found); next live session will be the first real exercise
of both.

**Not a strategy/risk-parameter change** — both fixes are input
validation and file-write robustness in the tick-processing/heartbeat
infra.

---

## 2026-08-21 — ROOT CAUSE FOUND (operational, not code): overnight machine sleep on battery caused a ~9.5hr feed/engine stall through market open; fixed by disabling DC sleep

**Symptom:** `api_bridge.py`'s `fyers_feed_watchdog` and `main_process_watchdog`
liveness logs (added 2026-08-20) both ran normally every ~5 min from
00:49:48 through 01:10:14, then went **completely silent until 10:20:18** —
a genuine ~9h10m gap in the watchdog loops themselves, not just a missed
detection. `api_bridge.py` finally logged `FYERS FEED STALL: no message ...
in 34087s` at 10:17:59, forced a fresh WS connection, and one second later
`main.py`'s own independent staleness check fired `ENGINE STALL: no tick
received for ANY watched symbol in 28641s during market hours`, plus a
one-off `Heartbeat write failed: [WinError 5] Access is denied` in the same
second (transient, self-resolved — subsequent heartbeat writes succeeded).
`main_process_watchdog` restarted `main.py` at 10:18:41 (new PID); both
processes have run cleanly since. **No open position existed at any point**
(`active_positions.json` was `{}` throughout) and zero trades were possible
before 10:18 anyway (pre-open + stall), so no risk was actually taken — but
this is a real ~1hr blind spot into the 09:15 open, and the third time this
validation window has hit an "hours of silence, self-healed on manual/
lucky check" pattern (2026-08-19's ~2hr feed outage, 2026-08-20's silently-
dropped INFO logs, now this).

**Root cause, actually found this time:** this machine only supports
Modern Standby (`powercfg /a`: "Standby (S0 Low Power Idle) Network
Connected", no legacy S1-S3). Its **DC (battery) "sleep after" timeout was
600s (10 min)** while AC was already `0` (never). The machine was running
on battery (confirmed: `Win32_Battery` showed `Discharging`, 26% charge) —
so ~10 minutes after whoever was working at 01:10 AM stepped away, Windows
put the whole machine into Modern Standby, freezing every process
(including both watchdog asyncio loops, mid-loop) until something woke it
around 10:17 AM. This retroactively explains why the 2026-08-19 and
2026-08-20 investigations could each fix a real, independently-legitimate
bug (a no-timeout subprocess call; a silently-dropped log level) without
ever fully closing out *why* the silence lasted so specifically long each
time — they were chasing software explanations for what was actually the
machine going to sleep on battery. The watchdogs themselves were doing
their job correctly (self-healing on wake); the machine just shouldn't
have been asleep while a live session needs to keep running.

**Fix:** `powercfg /change standby-timeout-dc 0` — DC sleep-after now
`0` (never), matching AC. This is a machine-wide Windows power setting,
not a code or config-file change, so there's nothing to commit; noting it
here since it's the actual fix. **Does not prevent a real power loss**
(dead battery, unplugged charger with 0% left) — only Modern Standby's
idle-timeout suspend. The battery was at 26% and discharging at the time
of this fix; flagged to the user directly, not something to act on
unilaterally.

**Not yet done:** hasn't been observed running a full uninterrupted
overnight+market-open cycle since the fix — today's session should confirm
whether this fully closes the pattern or whether another contributing
cause still exists.

---

## 2026-08-20 — Root-caused yesterday's silent watchdogs: `logging.info()` has been a no-op in `api_bridge.py` since the beginning, on every process run

**Follow-up to 2026-08-19's ~2hr undetected feed outage.** That entry left
one thing unconfirmed: why did neither watchdog log *anything at all* —
not even the except-and-log wrapper's own error line — for two hours of
genuine staleness? Added periodic INFO-level liveness logging to both
watchdogs to get a direct answer next time, and in doing so found the
real, structural bug immediately: **`root_logger.getEffectiveLevel()` in
the live `api_bridge.py` process is `WARNING`, not `INFO` — confirmed by
importing the module and checking directly.** Every `logger.info(...)`
call anywhere in this file has been silently dropped before reaching any
handler (including `fyersApi.log`) since this codebase's logging was set
up, not just recently. This retroactively explains a lot: the freeze
watchdog's own "restart succeeded" / "restart did not come up healthy"
confirmation lines that were never seen in the 2026-08-18 entries below,
and quite plausibly other "why didn't this log anything" mysteries from
earlier in this validation window that got written off as inconclusive.

**Mechanism:** `trading_bot/main.py` — transitively imported by
`api_bridge.py` for its strategy registrations — calls
`logging.basicConfig(level=CONFIG.LOG_LEVEL, ...)` unconditionally at
module import time (not inside `if __name__`). `logging.basicConfig()`
is a documented no-op if the root logger already has a handler attached
by the time it runs (from some even-earlier import) — leaving the root
logger at Python's own built-in default level, `WARNING`, which was
never actually `NOTSET`/unconfigured. `api_bridge.py`'s own
`_setup_log_rotation()` had a guard — `if not root_logger.level:
setLevel(INFO)` — intended to only act if nothing had configured a level
yet, but `WARNING` (30) is truthy, so the guard always skipped, and
`INFO` was never actually forced.

**Fixed:** changed the guard to explicitly check for `NOTSET` *or*
anything less verbose than `INFO` (`root_logger.level == logging.NOTSET
or root_logger.level > logging.INFO`), so it now correctly overrides an
accidental `WARNING` default rather than trusting an ambiguous truthy
check. Verified directly: root logger effective level is `INFO` after
the fix, and live redeploy immediately showed `logger.info()` lines that
had never appeared before — `"Auto-login completed successfully..."`,
`"fyers_feed_watchdog: task scheduled and running."`,
`"main_process_watchdog: task scheduled and running."`.

**Also added:** a periodic ~5-minute liveness log in both watchdog loops
(`fyers_feed_watchdog`, `main_process_watchdog`) — previously they only
ever logged on trigger, so a dead/never-scheduled task and a healthy idle
one were indistinguishable after the fact. If either watchdog ever goes
silent again, its liveness trail stopping is now direct, unambiguous
evidence, not something to infer from the absence of other log lines.

Full suite (628 tracked) green before and after. Redeployed live,
verified: `/health` healthy, `main.py` reconnected on its own, no open
position, trades unchanged.

**Not fully closed:** this explains why yesterday's outage was
*undetectable after the fact*, but doesn't by itself prove it explains
why the watchdogs didn't *act* — that still traces to whatever the
2026-08-19 entry's lifespan-timeout fix addressed (or didn't). The new
liveness logging is what will actually confirm or rule that out if this
recurs.

---

## 2026-08-19 — HIGH PRIORITY: ~2-hour undetected live-feed outage through market open, missed entirely by both auto-recovery watchdogs; manual catch and fix

**Symptom:** session check at 11:16 IST (market open since 09:15, ~2h1m
in) found `fyers_feed_age_s: 80171.7` (22+ hours stale) despite
`main.py`'s heartbeat being fresh (9.4s) — the process was alive and
looping, just receiving zero real ticks, and had been since the last
confirmed message at 2026-08-18 13:46:07 IST. `fyersApi.log` showed
*only* a tight, repeating loop of `Could not authenticate the user`
(Fyers error code -16) against the `/history` REST endpoint every ~30s
from at least 11:14 IST onward — no `FYERS FEED STALL`, no `MAIN.PY
FROZEN`, no auto-login trigger, nothing else, for the entire overnight
window and into market hours. **Both of the auto-recovery watchdogs that
exist specifically to catch this class of failure never fired.**

**Verified safe:** `active_positions.json` was empty and `trades` stayed
at 40 (unchanged since 2026-08-18) for the whole gap — no position was
ever unmanaged. But this is nonetheless a genuine, real live-trading
blind spot: for ~2 hours during actual market hours, the system could not
have received an entry signal even if one existed, and nothing detected
or alerted on it. Only found because this session happened to check.

**Action taken:** confirmed safe, restarted `api_bridge.py` then
`trading_bot/main.py` (both had to be started — killing api_bridge alone
left main.py down too). Feed came back immediately (`fyers_feed_age_s:
0.4`→`0.0`), `/history` auth errors stopped as soon as api_bridge got a
fresh login. The system then traded normally the rest of the session:
3 clean round-trips on `NSE:NIFTY26AUG24100PE` (trades #41–46), ending
flat with **+₹802.90** on the day, no open position at close.

**Root cause: partially identified, one real gap fixed, full mechanism
not confirmed.** Investigated `fyers_feed_watchdog`'s
`should_rebuild_stale_feed()` (`shared/risk/tick_staleness.py`) — its
logic is correct on inspection (non-zero `last_message_at` + market open
+ over-threshold ⇒ rebuild) and `_last_fyers_message_at` is never reset
to `0.0` anywhere except at process start, so this alone doesn't explain
a watchdog that fires normally (as it did repeatedly the day before) and
then goes completely silent for hours. What *is* confirmed as a real,
separate bug: `api_bridge.py`'s `lifespan()` startup handler
(api_bridge.py:~824-836) runs
`subprocess.run(["...", "scripts/auth/auto_login_fyers.py"], check=True,
capture_output=True, text=True)` with **no timeout**, awaited before the
app finishes starting *and* before `fyers_feed_watchdog()` /
`main_process_watchdog()` ever get scheduled via `asyncio.create_task()`.
`auto_login_fyers.py`'s own HTTP calls got timeouts in yesterday's fix,
but the vendored `fyers_apiv3` SDK's `session.generate_token()` call
inside it did not — if that hangs, this specific `subprocess.run` would
block the entire startup sequence indefinitely, delaying or preventing
the watchdogs from ever being scheduled on a given process (re)start.
Whether this exact mechanism explains last night's specific process
history couldn't be confirmed retroactively (no PID/creation-time
history was captured before the processes were replaced) — flagging
honestly rather than claiming certainty.

**Fixed regardless:** added `timeout=60` (+ a caught `TimeoutExpired`)
to that `subprocess.run` call, matching the same pattern already applied
to the `on_error` callback's identical call site yesterday. Full suite
(628 tracked) green after the change; redeployed live, verified `main.py`
reconnects on its own as expected.

**Still open for next session:** why did *neither* watchdog log anything
at all (not even a `fyers_feed_watchdog error:` from the except-and-log
wrapper) for ~2 hours of genuine, market-hours staleness that should have
tripped `should_rebuild_stale_feed` well within its first 15s check?
The lifespan-timeout fix above closes one plausible contributor but
doesn't prove it was *the* cause. Worth a dedicated look with better
process-lifetime logging (e.g. log the watchdog tasks' own scheduling at
startup) rather than inferring from `fyersApi.log` after the fact.

---

## 2026-08-18 (afternoon) — Recurring DNS-resolution outage caused two more `main.py` freezes; auto-recovery watchdog caught both, no position at risk, but recovery took far longer than its own code should allow

**Symptom, part 1 (environmental):** starting ~10:36 IST and recurring in a
dense cluster from ~13:00–13:14 IST, `getaddrinfo failed` (Windows error
11001, DNS resolution failure) started appearing against
`api-t1.fyers.in` for both the REST history endpoint and the raw Fyers
WebSocket, roughly every 30s during the worst cluster (matching
`main.py`'s history-fetch retry cadence). At 13:14:21 the **same error
also broke the Discord alert webhook**
(`shared.alerts.discord_alerter: [Alerts] Failed to send Discord alert:
<urlopen error [Errno 11001] getaddrinfo failed>`) — since that call goes
to `discord.com`, not Fyers, this confirms the failure is this machine's
DNS resolution broadly misbehaving, not anything Fyers-side or specific
to this codebase. Nothing in `trading-system/` can fix a host-level DNS
problem; flagging for the user to check locally (router/ISP/VPN/security
software) if it recurs.

**Symptom, part 2 (consequence):** this DNS instability correlates with
two `main.py` freezes today, each caught by the freeze-auto-recovery
watchdog added in the 2026-08-13/14 reliability audit
(`api_bridge.py::main_process_watchdog`):
- **12:44:25 IST** — `MAIN.PY FROZEN: heartbeat stale for 122s (PID 1540
  still alive). Open positions: none.` New process confirmed up at
  **12:53:26** (`engine.log`: fresh "Starting live bot..." from a new
  PID) — **~9 minutes** between detection and confirmed recovery.
- **13:14:21 IST** — `MAIN.PY FROZEN: heartbeat stale for 653s (PID 5800
  still alive). Open positions: none.` New process confirmed up at
  **13:46:06** — **~32 minutes** between detection and confirmed
  recovery.

**Verified safe both times:** `active_positions.json` was empty at each
freeze (logged directly in the alert line) and stayed empty throughout —
confirmed independently via `state.db`/`active_positions.json` after the
fact. `trades` count never changed from 40 all day; `ema_rsi` (the active
strategy) simply never signaled, so there's no way to know whether a real
entry was missed during either gap.

**Not fully root-caused — two things worth flagging even though the
system did recover both times:**
1. `_check_and_recover_main_process()`'s own code (terminate w/ 10s
   timeout → kill fallback → respawn → poll heartbeat for up to 90s)
   has a worst-case of roughly 2 minutes from detection to giving up, not
   9 or 32 minutes. The actual respawn clearly did eventually happen (new
   PIDs, fresh heartbeats), so the function didn't error out — but
   something stretched the terminate/respawn/first-heartbeat sequence far
   past what the code's own timeouts should allow. Most likely
   explanation, not confirmed: the new process's own startup (which
   synchronously fetches historical data from the same DNS-failing Fyers
   REST endpoint before it can log "Starting live bot" or write its
   first heartbeat) was itself retrying against the same broken DNS,
   which isn't bounded by any of the watchdog's own timeouts.
2. Neither `main.py restart succeeded` nor `main.py restart did not come
   up healthy` (the function's own unconditional end-of-run log lines)
   ever appeared in `fyersApi.log` for either recovery, despite recovery
   clearly happening. Suspected cause: the success line is `logger.info`
   and the root logger's effective level may have been raised above INFO
   by something else in the import chain before `_setup_log_rotation()`
   runs its `if not root_logger.level: setLevel(INFO)` guard (a no-op if
   the level was already non-zero) — unconfirmed, would need to check the
   live process's actual effective log level to be sure. Low priority
   (doesn't affect trading correctness), but worth fixing since it means
   this watchdog's own success/failure signal is currently invisible in
   the log operators actually watch.

**End of day:** market closed at 15:30 IST; system confirmed healthy and
still running as of 21:14 IST (heartbeat 11s old, `state.db` updating).
`trades`=40 (unchanged all session), no open position. **Status remains
NO-GO** — validation clock stays reset from this morning's 09:33 IST
restart; today produced no clean session (two freezes) and zero trades to
evidence against anyway.

---

## 2026-08-18 — Both engine processes found dead at session start; ~49min gap, no position at risk; root cause inconclusive (no captured traceback)

**Symptom:** session start (09:26 IST) found zero `python.exe` processes
running at all — `api_bridge.py` and `main.py` both dead, no ports
listening on 8000/3000. Log evidence:
- `main.py`'s heartbeat file (`run/main_heartbeat.txt`) last wrote at
  **08:44:13 IST** — `engine.log` itself went silent at the same point
  (last line: "Connected to API Bridge WebSocket!" at 08:38:56), no
  traceback, no shutdown message. Consistent in shape with the prior
  unresolved silent-freeze pattern (2026-08-06, 2026-08-13 afternoon)
  but this time the process is fully gone, not just frozen.
- `api_bridge.py` kept running until **09:22:40 IST**, when the feed-stall
  watchdog fired (`FYERS FEED STALL: no message ... in 39498s` — note:
  39498s ≈ 11h, suggesting the watchdog's staleness reference wasn't
  reset on a prior reconnect; not yet root-caused, flagged for a future
  session), got a `Token is expired` error, and triggered
  `scripts/auth/auto_login_fyers.py` via a blocking `subprocess.run(...,
  check=False)` inside the WS client's `on_error` callback
  (`api_bridge.py:478-484`). No log line after "Triggering auto-login..."
  — the process was gone by the time this session started (09:26).

**Verified safe before acting:** `config/active_positions.json` == `{}`
and `state.db`'s last trade was 2026-08-13 — no open position during the
outage, so nothing went unmanaged.

**Root cause: inconclusive.** Neither process's stdout was captured to a
durable file — `Start_AI_Bot.bat` launches both via `cmd /k` with no
output redirection, and by 09:26 both cmd windows were already gone (not
found in the process list), so any crash traceback is unrecoverable.
Genuine unknown whether this was the same freeze mechanism as
2026-08-06/08-13, an external kill, or something in the auto-login path.

**Real bug found and fixed along the way (regardless of whether it
caused today's outage):** `auto_login_fyers.py`'s 4 `requests.post(...)`
calls (OTP send, TOTP verify, PIN verify, token exchange) had no
`timeout=`, and the `subprocess.run(...)` that invokes it from
`api_bridge.py`'s `on_error` callback also had no timeout. A hang on any
of Fyers's auth endpoints would block that callback indefinitely with no
way to recover short of killing the process. Added `timeout=15` to all
four requests and `timeout=60` to the `subprocess.run` call (generous —
covers OTP+TOTP+PIN+token-exchange round trip — with a caught
`TimeoutExpired` that logs and returns instead of hanging the WS
client's error-handling thread forever).

**Action taken:** confirmed no open position, cleared stale `run/*.pid`
files, restarted `api_bridge.py` and `main.py` individually (not via the
`.bat`, to get durable stdout capture this time —
`logs/api_bridge_manual_20260818_093112.out.log`,
`logs/main_manual_*.out.log`) plus the frontend dev server. Verified
single-instance (no duplicate-launch race), `/health` returned
`fyers_feed_age_s` near 0, heartbeat fresh. Full outage window:
**08:44:13–09:33:00 IST (~49 minutes)**, entirely within market hours,
zero trades placed or missed-and-logged during the gap (none were open
going in; whether a real entry signal was missed and never taken isn't
knowable from the available logs).

**Status: validation clock resets again** — 2026-08-18 09:33 IST is the
new earliest possible session 1. Recommended follow-up, not done yet:
redirect `Start_AI_Bot.bat`'s two `python.exe` invocations to durable
log files so a future silent death is actually diagnosable, and consider
the same feed-stall-watchdog staleness-reference bug (39498s reading)
worth a dedicated look next session.

---

## 2026-08-17 — CRITICAL, uncommitted WIP left `api_bridge.py` uncollectable, silently killing the entire trading day

**Symptom:** asked to start paper trading and monitor today's session at what
was believed to be market open. `engine.log` showed three separate
`main.py` startup attempts already this morning (09:41:07, 09:43:20,
09:56:17 IST, none by this session — the user's own attempts) followed by
a continuous stream of `API Bridge WebSocket disconnected or failed:
[WinError 1225] The remote computer refused the network connection` —
`api_bridge.py` was never actually up to connect to. `state.db`'s `trades`
table confirms zero real trades for all of 2026-08-17 — the entire NSE
session (09:15–15:30 IST) passed with the engine unable to place a single
trade.

**Root cause:** working-tree-only (uncommitted, never live-tested)
feature work — a trade-journal CRUD API, a `/api/sentiment` endpoint, and
a `/api/trading-mode` endpoint — added `class JournalEntryCreate(BaseModel)`
at module level (`api_bridge.py:1097`) with no `BaseModel` import in
scope; the only `from pydantic import BaseModel` in the file was a stray
inline import ~150 lines further down, after the point of use. Python
raised `NameError: name 'BaseModel' is not defined` at import time,
meaning `api_bridge.py` could not even be collected — not a runtime bug,
a startup-time crash. It has apparently been in this broken state since
before market open today; nothing in this validation window's tooling
caught it because it was never committed or run through CI, and nobody
had restarted `api_bridge.py` since 2026-08-14's heartbeat fix until this
morning's (failed) attempts.

**Fix:** moved `from pydantic import BaseModel` to the top-level import
block (alongside the other FastAPI imports), so it's in scope for every
class that uses it regardless of where in the file they're defined. Pure
ordering fix, no logic touched. Full backend suite (migrated location,
`Testing_Automation_AI_Trading_Bot/python-unit/`) went from 8 collection
errors to **628 passed, 2 xfailed** (the 2 xfails are the pre-existing,
documented `drl_strategy` market-blindness ones). Restarted both
`api_bridge.py` and `trading_bot.main` — `/health` responds, feed age
~2.6s, `main.py`'s WebSocket connected to the bridge successfully at
22:24:20 IST.

**Not fixed / flagged, not mine to decide unilaterally:** the rest of
that same uncommitted diff (journal CRUD, sentiment endpoint,
trading-mode badge, a 4-hourly lot-size refresh scheduler, plus separate
uncommitted changes to `drl/marl/execution_agent.py`,
`backtesting_engine/run.py`, and an untracked `trading-system/tests/`
directory with 5 new test files) is still sitting in the working tree,
unreviewed and uncommitted, from a prior session. It's live-deployed now
(restarting the process picked it up) and the full suite passes with it
in place, but I did not write it, wasn't asked to commit it, and haven't
independently reviewed the journal/sentiment/execution-agent logic for
correctness the way this window's process expects — flagging as backlog,
not silently committing on someone else's behalf.

**Validation clock:** resets again. Zero real trades today means no §2
evidence either way for 2026-08-17 — today is a wash, not a session with
findings, not a clean session. **Status remains NO-GO.**

---

## 2026-08-14 — CRITICAL, ironic: last night's own heartbeat fix froze the engine for ~12 hours; the watchdog it shipped alongside caught and recovered it correctly

**Symptom:** a large gap opened up in overnight monitoring cadence
(wakeups didn't fire as scheduled for an extended stretch). On resuming
active monitoring at 21:50 IST, `main.py` (PID 15892 — the exact
process the 2026-08-13/14 reliability audit's live watchdog-recovery
test had respawned around 00:37 IST) was found completely silent in
`engine.log` from `00:37:01` through `12:34:54` — **~12 hours**, worse
than the original 2026-08-13 39-minute freeze this same audit had just
fixed. The only log line anywhere in that window: `[2026-08-14
12:34:54] ERROR __main__: Heartbeat write failed: [WinError 5] Access
is denied: ...heartbeat_tmp_... -> ...main_heartbeat.txt`, logged the
instant `api_bridge.py`'s new `main_process_watchdog` detected the
stale heartbeat and force-terminated the frozen process.

**Verified before concluding anything:** `config/active_positions.json`
was `{}` and `state.db` showed zero trades for 2026-08-14 — no capital
was at risk during the freeze, and the watchdog's own restart (also
logged: `main.py restart succeeded -- fresh heartbeat confirmed`) had
already produced a healthy replacement process (PID 7920→child 26552)
that ran normally for the rest of the day with no further incident.

**Root cause:** the previous night's heartbeat fix
(`heartbeat_writer`'s loop) called `_write_heartbeat()` — a synchronous
`tempfile.mkstemp` + `os.replace` — directly, unwrapped, on the event
loop. This is the *exact* anti-pattern the 2026-08-13 `get_market_data()`
freeze fix existed to eliminate, freshly reintroduced by the very fix
built to detect freezes. The single `WinError 5` logged at the moment
of forced termination is strong circumstantial evidence this write hung
on a Windows-level file lock (antivirus real-time scan, indexer, or
similar) for the whole window and took the entire event loop down with
it — ironically freezing the freeze-detector itself. No `py-spy` dump
exists from during the freeze (same limitation noted in the original
39-minute incident's writeup), so the exact lock-holder isn't
confirmed, only the mechanism.

**What worked correctly, worth stating plainly:** this is the first
real, naturally-occurring confirmation that the heartbeat +
`main_process_watchdog` mechanism built the previous night actually
works end-to-end against a genuine freeze, not just the simulated
off-hours test run during that same session. Detection, alerting,
termination, and recovery all fired correctly and automatically, with
zero manual intervention, entirely unattended, exactly as designed.

**Fix:** wrapped `_write_heartbeat` in `asyncio.to_thread` inside
`heartbeat_writer`'s loop — identical pattern to the `get_market_data()`
fix. New freeze-injection test (`test_a_hanging_write_does_not_stall_a_
concurrent_task`, mirroring `test_engine_freeze_prevention.py`'s for
`get_market_data`) proves a hanging write no longer stalls a concurrent
task. Full suite: 628 passed (up from 627), zero regressions. Deployed
live at 22:01 IST — no open position, restarted cleanly, resumed with
correct prior PnL (0.0), heartbeat confirmed genuinely updating on the
15s cadence post-fix.

**Not yet addressed, flagged:** `_save_positions()` has the identical
synchronous `tempfile`+`os.replace` shape (already defended with a
5-attempt retry for *fast-failing* `OSError`, but not for a genuine
*hang*) and is called directly, unwrapped, from multiple places in
`on_tick`. Given tonight's evidence that Windows file I/O in this
environment can apparently hang outright (not just fail fast), the same
`asyncio.to_thread` treatment may be worth applying there too — flagged
for the next session rather than changed unilaterally at this hour,
since it's a higher-traffic call site (every entry/exit) and deserves
its own careful pass rather than a rushed late-night change.

**Validation clock:** resets again — a ~12-hour total freeze is a new,
worse instance of the same failure class, even though the recovery
mechanism itself is now proven live-working.

---

## 2026-08-13 (afternoon) — HIGH PRIORITY, unresolved: a ~39-minute total engine freeze (all threads, not just the tick feed) — the same unfixed 2026-08-06 class of bug, recurring worse

**Symptom:** `ENGINE STALL` fired at 14:18:45 (551s stale) and again at
14:57:25 reporting **2320s (~39 minutes)** — a huge jump given the
300s re-alert cooldown should have produced roughly 7-8 intermediate
alerts if the process were merely idle-but-running. It did not log a
single one. More tellingly, `engine.log` has **zero lines of any kind**
— not just tick-driven ones — between 14:18:45 and 14:57:25, including
the sentiment background fetcher, which runs on its own separate OS
thread on a fixed ~5min cadence and had been firing like clockwork all
day. A genuinely separate thread going silent too, not just the asyncio
tick path, points at the whole process being starved, not merely an
upstream feed gap. No position was open during this window (the day's
one loss had already closed at 13:54:39), so nothing went unmanaged
this time — but that was incidental timing, not a property of the fix.

**Working hypothesis, not confirmed (no `py-spy` dump was captured
during the freeze — it had already passed by the time this was
noticed):** this is very plausibly the same unresolved mechanism as the
**2026-08-06** incident already documented in
`shared/risk/tick_staleness.py`'s module docstring — `main.py` going
CPU-bound on synchronous pandas/indicator work for 22+ minutes with zero
log output, "root cause not fully pinned down." Today's window
coincides with an 11-entry burst of DNS resolution failures in
`fyersApi.log` (`api-t1.fyers.in` unreachable). `trading_bot/main.py`
calls `broker.get_market_data(...)` **synchronously, directly on the
event loop, with no `asyncio.to_thread` wrapping and no throttle** —
this is an already-known, already-flagged gap (see the comment above
line ~1001 in `main.py`: *"there's nothing else in this codebase
throttling get_market_data calls... a position sat completely
unmanaged for the better part of a session because of this... DATA_LIMITER
exists but was never wired to anything — a gap flagged but deliberately
not acted on during the 2026-08-03 audit"*). A synchronous call blocking
on repeated DNS-failure retries, fired once per tick with no cooldown,
would starve the entire single-threaded asyncio loop for its duration —
and, via the GIL, could plausibly also starve the separate sentiment
thread, matching what was actually observed. Not confirmed as *the*
mechanism, only as the most consistent explanation available from the
evidence in hand.

**Why not fixed now:** market closed within minutes of this being
found; wiring up the existing (unused) `DATA_LIMITER` touches a call
site explicitly marked as "deliberately not acted on" by a prior,
apparently intentional decision whose full reasoning isn't in this
session's context — reversing that unilaterally, at close, without
being able to live-verify a fix, isn't the right call. Flagging
prominently instead.

**Recommended for the next session, in priority order:** (1) if this
recurs, capture a `py-spy dump` *during* the freeze, not after — that's
the one piece of evidence that would actually confirm or rule out the
CPU-bound hypothesis; (2) revisit whether `DATA_LIMITER` should finally
be wired to `get_market_data` call sites, or at minimum whether those
calls should move off the event loop via `asyncio.to_thread` regardless
of throttling; (3) this is the second occurrence of an unexplained
total-process stall (2026-08-06: 22min: today: 39min) — worth treating
as a live pattern, not two unrelated one-offs.

**Validation clock impact:** this is a new, real gap — even though no
position was open this time, a process that can go fully unresponsive
for 39 minutes during market hours with no diagnosis is squarely a
reason `§2`'s "pattern tapering off" bar hasn't been met yet. Validation
clock resets again.

---

## 2026-08-13 (afternoon) — Not a bug: first real trade activity of the day, and the first live exercise of the 2026-08-12 quote-refresh fix with a genuine position on the line

**Trade activity (all normal, no findings):** first signal of the day at
13:35:00 — entered `NSE:NIFTY2681824400PE` (BUY PUT, qty 260 @ 90.35, SL
76.30). Pyramided twice (13:35:01, 13:35:02) as price moved favorably,
then hit its trailing stop-loss at 13:35:14 for **+₹178.20**, immediately
followed by a fresh entry on a new signal (same option, qty 260 @ 90.90,
SL 76.80). That second position ran until 13:54:39, when it hit its hard
stop-loss (LTP 76.75 ≤ SL 76.80) for **-₹3,679.00** — PnL math verified
exact: (90.90 − 76.75) × 260 = 3,679.00. Net day so far: -₹3,500.80,
1 consecutive loss. Equity now 102,560.40. No position open as of this
entry.

**Notable:** at 13:52:45, with the second position still open, `Fyers
/quotes returned an error (Bad request)` — the exact condition
`FyersBroker._refresh_fyers_model()` (added 2026-08-12, see that date's
afternoon entry) exists to catch. This is the first time it's fired
live with real capital-equivalent risk on the line rather than a flat
book. It refreshed the session and retried once, quotes resumed cleanly
(no repeated errors), and the hard-SL exit ~2 minutes later fired
correctly and on time. Positive live validation of that fix under the
condition it was actually built for; no code change here.

---

## 2026-08-13 (early afternoon) — Fourth WS disconnect today (12:50 IST), only 25min after the third; self-healed instantly via the vendored client's own reconnect, ruled out a thread-leak theory

Fourth `[WinError 10054]` close. Interval since the third dropped to
~25min (vs ~67min and ~55min before that) — checked whether this was a
resource leak from repeated forced rebuilds (`api_bridge.py`'s `python.exe`
worker showed 42 threads / 512 handles / 432MB after running since 10:27
through 3 of the day's 4 disconnects). Ruled out on the evidence
available: (1) this disconnect didn't even need a forced rebuild — no
`FYERS FEED STALL` log, self-healed via the vendored client's own
`reconnect=True` on the *same* socket object, same as incident #2, so no
new thread spawn happened here at all; (2) neither of the two forced
rebuilds today (#1, #3) ever logged `Error closing the stale Fyers
socket`, meaning `close_connection()` completed cleanly each time —
and reading the vendored library directly, a clean `close_connection()`
does `.join()` both its message and ping threads before returning, so a
clean close shouldn't leak. 42 threads is plausibly just this app's
normal baseline (asyncio's default thread-pool executor plus a couple of
persistent library threads), not accumulation — no prior-restart baseline
was captured to compare against, so this isn't fully ruled out, just not
supported by the evidence in hand. No open position, no code change.
Watching whether the interval keeps shortening.

---

## 2026-08-13 (early afternoon) — Third WS disconnect today (12:25 IST); clean, fast, forced rebuild — the best confirmation yet of the morning's `on_close` fix, plus a pattern worth watching

A third `[WinError 10054]` upstream close, this time genuinely exercising
the full forced-rebuild path (`FYERS FEED STALL: ... in 166s`, `main.py`'s
matching `ENGINE STALL: ... in 166s`). No `on_close` crash, no lingering
staleness — `/health` was back to sub-second `fyers_feed_age_s` well
within the same minute. This is the cleanest recovery of the three
today, and the first one to actually exercise the watchdog's forced
rebuild without a crash getting in the way, end to end. No open position,
no code change.

**Pattern worth watching, not yet acted on:** three separate upstream WS
closes today (10:23, 11:30, 12:25 IST), roughly a little under an hour
apart, all the same `WinError 10054` signature, at least one (11:30)
correlated with a burst of DNS resolution failures for `api-t1.fyers.in`.
Could be this machine's local network/DNS, could be upstream Fyers-side
behavior — not enough samples yet to tell, and the existing watchdog+fix
is handling each one correctly. Flagging in case the cadence continues
or shortens; not a code change to make on the current evidence.

---

## 2026-08-13 (late morning) — A second, brief real WS disconnect self-healed via this morning's `on_close` fix; a ~15min engine-wide tick gap on `main.py`'s side is a known, by-design observability-only limitation, not a new bug

**Symptom:** at 11:30:37 IST, a burst of DNS resolution failures for
`api-t1.fyers.in` (both `/history` and `/quotes` REST calls, plus the
live WebSocket itself: `Fyers WS Error: [WinError 10054] An existing
connection was forcibly closed by the remote host`) — a real, brief
upstream network blip, not an application bug. `main.py`'s own `ENGINE
STALL` detector fired at 11:45:27 reporting 889s (~14.8min) with no tick
for any watched symbol. No open position throughout.

**What happened differently this time (confirms this morning's fix):**
unlike the 10:23 incident, `on_close` did **not** crash — no
`TypeError`, no repeat of the earlier bug. No `FYERS FEED STALL` forced-
rebuild was even needed: the vendored client's own `reconnect=True`
evidently succeeded on its own well under the watchdog's 800s trigger
threshold, something it couldn't reliably do before today's fix since a
crashing `on_close` was interfering with its internal close-handling.
Verified recovery directly: `/health`'s `fyers_feed_age_s` sampled four
times over ~20s stayed pinned near 0 (0.3/0.2/0.3/0.0s, not climbing
with wall-clock), and `data/NSE_NIFTY50-INDEX_5Min.csv` picked up a
fresh 11:45:00 candle with an 11:47 file mtime.

**Why `main.py` still saw an ~889s gap despite `api_bridge`'s upstream
recovering faster:** this is the exact, already-documented mechanism
in `api_bridge.py` (comment above `_last_fyers_message_at`, written
after the 2026-08-06 7h49m incident): `main.py`'s *local* socket to
`api_bridge`'s `/ws/live` stays healthy throughout an upstream-only
outage (ping/pong fine) — the gap is entirely about `current_market_data`
not being fresh upstream, not a local disconnect, so `main.py`'s own
stall detector can only warn, not itself recover. That's by design; the
recovery mechanism lives entirely on `api_bridge`'s side (this morning's
fix). Not re-verified with byte-for-byte certainty that `main.py`'s own
`_last_tick_at` had caught back up by the time of writing (no direct
introspection endpoint for it) — inferred from `api_bridge`'s sustained
health plus the fresh candle append, and treated as resolved pending the
next monitoring pass (no further `ENGINE STALL` within its 300s re-alert
window would confirm; one recurring beyond that would not).

**No code change this entry** — this is a live validation of this
morning's fix plus a documentation cross-reference, not a new finding.
The ~15min gap length (vs. instant historically) is noted as worth
watching if it recurs; a single sample isn't enough to call it a pattern.

---

## 2026-08-13 (mid-morning) — CRITICAL: the 2026-08-12 feed-stall watchdog's own reconnect handler had a callback signature bug, silently breaking recovery the first time it hit a real socket close

**Symptom:** at 10:23:01 IST, `fyers_feed_watchdog()` (added 2026-08-12,
`api_bridge.py`) correctly detected the upstream Fyers WebSocket gone
silent and forced a rebuild — but the very next log line was `Fyers WS
Error: start_fyers_socket.<locals>.on_close() takes 0 positional
arguments but 1 was given`. No further connection activity followed:
no "Fyers WS Connected!", no ticks. `/health`'s `fyers_feed_age_s`
climbed in exact lockstep with wall-clock time since the watchdog's
reset (verified by sampling it twice with precise timestamps — the
delta matched to within measurement noise), proving zero ticks arrived
for the several minutes it was checked, not just a slow reconnect.
`main.py`'s own independent `ENGINE STALL` detector fired at the same
moment (799s), confirming the gap was real, not a monitoring artifact.
No open position throughout.

**Root cause:** `on_close()` was defined with zero parameters, but the
vendored `fyers_apiv3` client invokes it as `self.OnClose(message)`
(passing the close reason) — see `data_ws.py`'s `on_close` method. Every
real socket close raised `TypeError` inside the vendored library's own
close-handling path, one layer beneath `fyers_feed_watchdog()`'s manual
rebuild logic (which itself is structured so this crash, being caught
by `on_close`'s caller inside the vendored library rather than our own
try/except, doesn't stop the watchdog's `threading.Thread(target=
start_fyers_socket, ...)` from firing — but the *new* socket registers
the identical broken `on_close`, so the instant Fyers's server closed
that connection too, the same crash repeated). This is exactly the kind
of previously-unexercised path the validation phase keeps finding: the
2026-08-12 fix's happy path (successful reconnect) was live-verified,
but a close event serious enough to reach `on_close` with a real message
never happened in that session — `sibling on_error(message)` already
had the correct one-argument signature; `on_close` was the one closure
that didn't match.

**Fix:** `on_close(message=None)`, logging the message. One-line, mirrors
`on_error`'s existing signature. Not independently unit-testable without
extracting these closures to module scope (same as `on_error`/`on_open`,
which also have no direct test coverage) — verified live instead:
restarted `api_bridge.py` only (not `main.py`, which talks to Fyers only
via this process's local `/ws/live`, not directly — no cross-process
token-invalidation risk this time), confirmed `fyers_feed_age_s` dropped
to ~0.1s and stayed there across repeated checks, and confirmed
`main.py`'s own broker WebSocket client (which had itself been
retrying every 5s since the stall) reconnected cleanly at 10:27:51
without needing its own restart.

**Minor, unrelated observation (not fixed):** `on_open`'s "Fyers WS
Connected!" info-level log line doesn't actually appear in `fyersApi.log`
even on a known-successful connect (confirmed via `/health`) — an
existing logging-level/handler gap, not a functional issue, not touched
here to stay in scope.

**Validation clock:** resets again — this is a second, independent gap
today. Full timeline above; see `GO_NO_GO_CHECKLIST.md` for the current
status note.

---

## 2026-08-13 (morning) — Process hygiene: duplicate `api_bridge.py`/`main.py` instances from two `Start_AI_Bot.bat` launches; both pairs died mid-startup, leaving the system fully offline for ~9 minutes during market hours

**Symptom:** at session start, process inspection found **two** copies each
of `api_bridge.py` (PIDs 17616, 17920) and `trading_bot/main.py` (PIDs
17584, 12892), all four with identical start timestamps (09:27:08–09
IST) — `Start_AI_Bot.bat` had been launched twice in quick succession.
Confirmed via `Win32_Process` that only one `Start_AI_Bot.bat`/cmd-tree
was still traceable at inspection time; the other launch's parent
console had already exited, leaving its two child processes as orphans
indistinguishable from the "current" pair without timestamps.

**Verified before acting:** `state.db` showed 0 trades today and
`config/active_positions.json` was `{}` — safe to kill a pair before
either engine could act on a live signal.

**What happened next:** killed one `api_bridge.py` + one `main.py`
(the pair that looked like the accidental duplicate). Within the next
process check, **all four** processes were gone, not just the two
targeted — the untouched pair had also died. `engine.log` showed only
one `main.py` startup sequence had ever completed (09:28:45–54), and it
hit `Fyers history API chunk failed ... Could not authenticate the user`
on every retry (falling back to cache) — consistent with two processes
racing for the same Fyers paper-mode token/session state during
concurrent startup, though the exact mechanism (log file lock, token
file race, or the second `api_bridge.py` failing to bind :8000 and the
first `main.py` losing its WebSocket peer mid-handshake) wasn't fully
isolated since neither dying process's own console output was captured.
Net effect: **zero engine processes running from ~09:31 to ~09:40 IST**,
9 minutes of the market open with no monitoring or risk management —
though with 0 open positions throughout, nothing was left unmanaged.

**Fix (this session):** restarted one clean instance each of
`api_bridge.py` and `main.py` directly (bridge first, confirmed
listening on :8000, then the engine). Verified single logical instance
of each (the two-PIDs-per-process appearance for background-launched
Windows executables is Git Bash's normal parent/child wrapper, not a
duplicate — confirmed via `ParentProcessId`: the second PID's parent is
the first). This time startup completed cleanly: real Fyers history
fetch succeeded (no auth failures), `Resuming session with previous
PNL: 0.0`, WebSocket connected. No code change — this is the same
known gap noted in `production_readiness_phase.md`: **the system does
not guard against multiple concurrent engine instances**; still nothing
in code detects or prevents a second launch. Worth a real fix (e.g. a
PID-file/lock on startup) rather than relying on external process
hygiene every time, given this is the second time in the validation
window a double-launch has caused a real gap.

**Validation clock:** resets again — a ~9-minute total-outage window
during market hours is a fresh gap, independent of 2026-08-12's two
resets. See `docs/GO_NO_GO_CHECKLIST.md` for the current status note.

---

## 2026-08-12 (afternoon) — CRITICAL: a real PE entry signal held for 54 minutes, silently blocked by main.py's own Fyers session going stale as a side effect of this morning's api_bridge.py restarts

**Symptom:** from 12:05:47 to 12:59:59 IST, `engine.log` shows a NIFTY PE
signal continuously mapped to `NSE:NIFTY2681824350PE` on nearly every
tick (1,028 "Auto-mapped" lines), with 581 "Could not fetch live option
premium for ... — skipping this entry" warnings over the same window —
the entry was never taken. No open position, so nothing went
unmanaged, but a real, otherwise-valid signal was blocked for the entire
window and simply vanished with no trade recorded.

**Verification before concluding it was a bug:** cross-checked
`fyersApi.log` — exactly 581 matching entries in the same window,
confirming the warning traced to real API responses, not a local logic
error. First ~10 were `{"code": -15, "message": "Please provide valid
token"}`; the rest were a generic `"Expecting value: line 1 column 1"`
JSON-decode failure from the vendored SDK's own error handling (see the
fix below for why both are the same underlying condition). Directly
tested the *current* cached token by hand, fresh, outside the running
process — it worked immediately and returned a valid NIFTY quote. That
ruled out "Fyers is down" or "the token is genuinely expired" and pointed
squarely at the long-running `main.py` process holding something stale.

**Root cause:** self-inflicted, by this morning's own incident response.
`brokers/fyers_broker.py`'s `FyersBroker._fyers_model` (the object used
for all REST calls — quotes, history, funds, orders) is built once inside
`authenticate()`, at process startup, and never rebuilt afterward.
`.fyers_tokens.json`'s mtime (11:32 IST) lines up with the `api_bridge.py`
restarts done to fix the morning's feed-stall incident — its `lifespan()`
runs a full Fyers auto-login (`scripts/auth/auto_login_fyers.py`) on
every startup, a completely separate process from `main.py`. Fyers
invalidates the previous session token when a new login for the same
app/user completes. `main.py`, running continuously since 09:38 IST, had
no idea its own `_fyers_model`'s token had just been invalidated by a
totally unrelated process — and the vendored `fyers_apiv3` SDK's
`get_call()` never raises on this; it always returns a dict, just shaped
`{"s": "error", ...}` instead of `{"d": [...]}`, so `get_market_data()`
silently read it as "no quotes for this symbol" forever, with nothing
to detect or recover from short of restarting `main.py` itself — which
is exactly what fixing it required, live, at 13:35 IST.

**Fix:** `FyersBroker._refresh_fyers_model()` rebuilds `_fyers_model` from
whatever token is currently cached on disk. `get_market_data()` now
checks `resp.get("s") == "error"` after every `.quotes()` call and, on a
hit, refreshes and retries exactly once before giving up (still returns
`{}` on a genuine outage — no crash, matches the pre-fix "skip this
entry" behavior when there's truly nothing to recover from). Scoped
deliberately to `get_market_data()` only, not `place_order`/`funds`/
`orderbook`/`history` — those share the same structural risk but sit
closer to live-order and risk-management paths, flagged here rather than
changed unilaterally.

**Tests:** new `test_fyers_broker_stale_session_recovery.py`, 6 cases —
transparent self-heal on a stale-then-fresh token, no-op on a healthy
session (doesn't double-call), still-empty-not-a-crash when there's truly
no fresh token anywhere, no-cached-token edge case, and the real
`_refresh_fyers_model()` implementation exercised end to end (not just
stubbed). Full suite: 579 passed, 2 xfailed (was 573). Restarted `main.py`
at 13:35 IST (no open position, confirmed via `active_positions.json`
before touching it) — live-verified via a fresh historical-candle fetch
and `state.db`'s heartbeat matching wall clock immediately after.

**Process note, not a code fix:** this is the second incident today
caused by iterating on a fix while the *other* long-running process kept
running unrestarted. Restarting one Fyers-authenticated process while
another stays up is not really safe in this architecture yet — worth
remembering next time either process needs a live restart mid-session.

**Validation clock:** resets again — a second new, previously-undiscovered
gap found live today. See `docs/GO_NO_GO_CHECKLIST.md`'s 2026-08-12
entries.

---

## 2026-08-12 — CRITICAL: upstream Fyers feed silently dead for 46 minutes during market hours; auto-recovery watchdog added; a bug in the fix itself caught and fixed before it could ship broken

**Timeline**

- **09:38** — session started clean, `main.py` (PID 6328) and `api_bridge.py`
  (PID 16276) both up, WebSocket connected, first hour traded flat/healthy.
- **10:33:53–10:34:26** — six DNS resolution failures for `api-t1.fyers.in`
  in `fyersApi.log` (`NameResolutionError`), a transient local network
  blip. No further log activity of any kind from either process after
  this.
- **11:16:30** — `main.py`'s own stall detector fired: `ENGINE STALL: no
  tick received for ANY watched symbol in 2516s during market hours`
  (2516s ≈ since 10:34:34, i.e. immediately after the DNS blip). Caught on
  the very next scheduled monitoring check.
- **11:19** — verified against ground truth before acting: no open
  positions (`active_positions.json` empty, last real trade was
  2026-08-07), so no risk-managed position was silently unmonitored this
  time — but the mechanism is identical to the 2026-08-06 7h49m incident
  and would have been just as dangerous with a position open.
- **11:19:37** — killed and restarted `api_bridge.py` (PID 16276 → 23160).
  `main.py` immediately detected the now-actually-closed socket ("no close
  frame received or sent") and reconnected cleanly by 11:20:18. Ticks
  resumed instantly — confirmed the fault was entirely upstream of
  `main.py`'s own connection.

**Root cause**

The vendored `fyers_apiv3` client's own `reconnect=True`
(`api_bridge.py`'s `start_fyers_socket()`) never fires for this failure
mode. Read directly from `venv/Lib/site-packages/fyers_apiv3/
FyersWebsocket/data_ws.py`: its keepalive (`__ping`) sends a ping frame
every 10s as long as the OS socket merely reports itself `connected` —
it never waits for or checks a pong. A network blip that leaves the OS
socket in a false-`connected` zombie state (exactly what the DNS-failure
burst above looks like) is therefore completely invisible to it —
`on_close`/`on_error` never fire, so the library's own reconnect logic
never runs. Nothing on the receiving side tracked "have I actually heard
from Fyers lately" independently, so nothing could catch what the library
missed — the same class of gap fixed for `main.py` itself on 2026-08-06
(`ENGINE STALL`), just one layer further upstream, and worse: that
detector could only warn, never recover, because *its own* local socket
to `api_bridge.py` stayed perfectly healthy (ping/pong fine) throughout —
the dead zombie was entirely on api_bridge's side, invisible to main.py.

**Fix**

- `shared/risk/tick_staleness.py`: added `should_rebuild_stale_feed()` (+
  `DEFAULT_FEED_REBUILD_THRESHOLD_S = 90.0`, matching
  `DEFAULT_ENGINE_STALL_WARNING_S`) — pure function, same style as
  `seconds_since_any_tick`/`find_stale_positions` already in this module.
- `api_bridge.py`: `on_message` now stamps `_last_fyers_message_at =
  time.time()` on every message (not just priced ticks — any message
  proves the socket is alive). A new `fyers_feed_watchdog()` background
  task polls `should_rebuild_stale_feed()` every 15s during market hours
  and, on a stall, force-closes (`close_connection()`) and rebuilds the
  Fyers socket from scratch — the same recovery my manual process restart
  achieved, now automatic. `/health` now also reports `fyers_feed_age_s`
  for external monitoring.
- **Caught before it shipped broken:** deploying the above immediately
  broke `on_message` on the very first real message —
  `NameError: cannot access free variable 'time'`. Root cause: a stray
  `import time` inside this same function's dead yfinance-fallback branch
  (only reached when there's no cached Fyers token) made `time` a LOCAL
  name of the *entire* enclosing `start_fyers_socket()` — Python decides a
  name is local to a function from any assignment/import anywhere in its
  body, regardless of which branch actually runs at call time. Every
  nested closure below it (`on_message`, `on_error`, ...) inherited `time`
  as an unbound free variable, raised only when one of them actually tried
  to use it — invisible until a real message arrived, exactly like the
  bug it was fixing. Fixed by deleting the redundant local import (`time`
  is already imported at module level); root-caused rather than worked
  around locally, so no other closure in this function can hit the same
  trap later. Live-verified this time: `/health` held `fyers_feed_age_s`
  under ~2s continuously after redeploy.

**Tests:** `test_tick_staleness.py` (`should_rebuild_stale_feed`, 7 new
cases) + new `test_api_bridge_fyers_feed_watchdog.py`, which exercises the
*real* `on_message` closure (not a reimplementation) via a stub
`FyersDataSocket`, so a regression of the shadowing bug fails it directly.
Full suite: 573 passed, 2 xfailed (up from 571 passed pre-session, no
regressions).

**Validation clock:** per `GO_NO_GO_CHECKLIST.md` §2, this resets the
clean-session count — a genuine, previously-undiscovered feed-reliability
gap surfaced live during real market hours, not flakiness. No trading-day
report for today; monitoring continues into the afternoon session.

---

## 2026-08-07 (late evening) — Fix #2: real option-premium-candle ATR architecture; Fix #4/#5 re-verified

Continuation of the same evening's remediation sprint (see the entry immediately
below). Market remained closed throughout — all validation tonight is offline
(unit + integration tests, clean-boot/`py-spy` confirmation) unless noted
otherwise.

### Fix #2 — ATR/premium unit mismatch (audit §2.1, §3.4)

Explicit direction was given to implement the "real option-premium-candle ATR"
architecture (the design doc's Approach 4) rather than the originally-recommended
Approach 2 (premium-banded proxy) — spot data for entry decisions only, option
premium data for all position management. Full comparison and the
as-built architecture are in `docs/ATR_TRAILING_STOP_DESIGN_2026-08-07.md` (updated
tonight with a new §7 documenting exactly what was built and why one detail — how
"subscribe" was interpreted — deviated from a literal reading, with the reasoning
laid out explicitly rather than silently assumed).

**What changed:**
- **New module `shared/risk/option_atr.py`** — `resolve_option_atr()`: computes a
  genuine Wilder ATR(14) from the option contract's own candles (reusing
  `shared/indicators/atr.py` verbatim, zero duplicate ATR math) once
  `MIN_CANDLES_FOR_OPTION_ATR` (14) of the option's own history exists; falls back
  to the already-shipped premium-banded distance table
  (`option_stop_loss.py::resolve_stop_points`) during the unavoidable post-entry
  cold-start window. The underlying index's ATR is never consulted for an option
  position, in either branch. Pure function, 9 new unit tests.
- **`trading_bot/main.py`'s exit-check loop:** every fresh option premium sample
  already being fetched (the existing ~1/sec throttled `broker.get_market_data()`
  poll) is now also fed into the same `CandleAggregator` that builds the index's
  own candles, keyed by the option's own contract symbol
  (`aggregator.add_tick({...})`). `current_atr`'s computation now branches on
  `is_opt_pos`: options resolve via the new `resolve_option_atr()` against their own
  candle series; non-option positions keep the exact prior index-ATR computation
  unchanged (audit's own "preserve existing behaviour for non-option workflows"
  requirement).
- **New pure helper `_stale_option_candle_symbols()`** + a sweep wired into the
  existing 30s tick-staleness watchdog loop — evicts an option contract's candle
  buffer once its position closes (checked every cycle, regardless of market hours
  or whether any position is currently open), preventing unbounded memory growth
  over a long-running process trading many different contracts across many days.
  Never touches an underlying index symbol's own candle buffer. 6 new unit tests.
- **5 new integration tests** using the REAL `CandleAggregator` class (not a mock)
  covering: building a real candle series from fed ticks, isolation (option ticks
  never contaminate the index's own series), the cold-start-to-warm transition,
  sweep eviction after the real aggregator has tracked a symbol, and same-interval
  tick merging (confirming reuse of the aggregator's existing, already-tested
  bucketing logic rather than any new/duplicate aggregation code).

**Single fix point covers both live consumers.** `current_atr` is computed exactly
once per exit-check tick and passed to both the generic/`ema_rsi` path
(`SmartExitEngine.evaluate_exit()`) and the dormant `institutional_momentum` path
(`TieredExitManager.manage_active_trades()`, via `m_strategy.manage_active_trades(...,
current_atr=current_atr)`) — confirmed by direct grep of every `current_atr`
reference in `main.py`. Fixing the one computation site resolves audit finding §3.4
as a side effect, with zero changes needed inside `momentum_strategy/exit_manager.py`
itself.

**Compatibility, addressed by construction (not touched, therefore not broken):**
`shared/exits/exit_engine.py`'s `SmartExitEngine.evaluate_exit()` internals are
completely unchanged — only the *value* handed to it as `current_atr` changed for
option positions. Same for `shared/risk/manager.py` (Risk Manager), `shared/exits/
pyramid_sizer.py` (Pyramid — and since a pyramid scale-in adds to the *same* symbol,
its candle series continues building uninterrupted, no special-casing needed),
reconciliation, dashboard (state.db writes untouched), and journal/PnL recording
(untouched). The full 371-test suite (up from 350 this morning) passing with zero
failures is the regression evidence for all of the above — in particular
`test_panic_exit.py`, `test_reconciliation.py`, and every pyramid/risk-manager test
already in the suite passed unchanged.

**Evidence against the specific risks the scope called out:**
- *Duplicate ATR implementations:* none introduced — `option_atr.py` calls
  `shared/indicators/atr.py::atr()` directly; a dedicated test
  (`test_matches_shared_atr_indicator_directly`) pins the two never drifting apart.
- *Memory leaks / unbounded candle growth:* addressed by the eviction sweep;
  covered by both unit and integration tests.
- *Subscription leaks / duplicate subscriptions:* no new subscription mechanism was
  introduced (see the design doc's §7.1 for why) — the existing throttled
  poll-and-cache already prevents duplicate fetches, and the candle feed naturally
  only runs while a position is open.
- *Race conditions:* the tick-feed (`add_tick`) and the sweep (`aggregator.candles
  .pop()`) both run on the single-threaded asyncio event loop with no `await` in
  the middle of either operation — cooperative scheduling means neither can
  interleave with the other mid-mutation. No new locking was needed or added.
- *Performance:* the new per-tick cost is one dict feed (already-throttled to
  ~1/sec) plus, on the existing 30s watchdog cycle, an O(n) scan over currently-
  tracked symbols — both negligible relative to the strategy-evaluation and
  institutional-filter costs already documented elsewhere this validation window.

**Deployment.** No open position, market closed (19:41 IST) — zero risk window.
Restarted only the `main.py` pair (PID 19416/16796 → 3820/26064); `api_bridge`/
frontend untouched. Clean boot confirmed (candles preloaded, WS reconnected, prior
PNL/trade cap restored, `/health` OK), `py-spy` dump shows all threads idle/normal,
no crash from any of the new code paths executing at startup.

**Honesty about validation status.** This is the audit's most significant fix and
has the least live evidence of the three completed tonight: **the entire
candle-feeding pipeline has never processed a real option premium tick** — no
option position has been open since this was deployed, and none will be until
tomorrow's live session. The unit and integration tests prove the pipeline is wired
correctly and behaves correctly against realistic synthetic data (including using
the real `CandleAggregator`, not a mock), but genuinely new: (a) how quickly a real
position accumulates 14 candles at whatever the system's configured timeframe is
(if 5-minute, that's 70 minutes — a meaningful fraction of many trades' actual
lifetime, meaning the cold-start proxy path may be what's actually governing
trailing behavior for a large share of real trades, exactly as anticipated in the
design doc's own risk discussion); (b) whether the throttled ~1/sec premium poll
produces a genuinely representative candle range compared to what a real
tick-by-tick feed would show; (c) whether the eviction sweep behaves correctly
under real, possibly-rapid open/close/reopen sequences (the EOD-cutoff incident
from earlier today showed this system is capable of producing exactly that
pattern). **Pending: tomorrow's live session — specifically watching the first
option position opened, confirming candles accumulate as expected in the logs, and
watching CPU/behavior through at least one full cold-start-to-warm transition.**

### Fix #4 re-verification — every entry path checked, not just the one already fixed

Grepped every `entry_symbol =` assignment site in `main.py` (3 total, not 2) to
confirm full coverage:
1. The generic/`ema_rsi` auto-map path — already fixed this evening (see the entry
   below), covered by `_should_abort_missing_option_mapping()`.
2. The `"premium"` strategy's own `option_symbol = sig.option.symbol if sig.option
   else s` — **investigated fresh, confirmed already safe by a different, existing
   mechanism** (not by this evening's fix): `select_option()`'s return type never
   permits `None` without raising, and `PremiumSignalEngine.evaluate()`'s lack of a
   try/except around that call means a raise propagates all the way out to
   `main.py`'s own outer per-tick exception handler, which safely abandons the tick.
   Locked in with a new, dedicated test
   (`test_premium_signal_engine_option_selection_safety.py`) rather than left as an
   inference from reading the code. Documented in `STRATEGY_AUDIT_2026-08-07.md`
   §1.1 as an addendum.
3. The auto-map success path itself (`entry_symbol = opt.symbol`) — unaffected,
   correct by construction.

**Conclusion: every entry path in this codebase is now confirmed incapable of
placing an order on the raw underlying index symbol when option mapping was
required**, via either an explicit gate (path 1) or a pre-existing exception-
propagation safety net (path 2), both now covered by tests.

### Fix #5 re-verification — startup, reload, and fallback behavior confirmed

- **Reload path (the common case):** already covered by this evening's 6 tests;
  re-confirmed still passing after tonight's additional changes.
- **Startup (first load) path:** `_load_settings()` calls `_load_settings()` at
  `run_live_bot()`'s very start (line ~497), before `broker.stream_quotes(...)` ever
  runs — validation happens before any live tick is processed, as early as this
  architecture allows.
- **Missing-settings-file edge case (new observation, not a defect):** if
  `config/settings.json` doesn't exist at all, `_load_settings()`'s file-existence
  guard means `_validate_active_strategy()` is never called for that load — but the
  hardcoded `defaults["active_strategy"]` value used in that fallback path is
  `"institutional_momentum"`, itself always a valid, registered strategy name, so
  there is no actual risk from this gap — just a code path where the new validation
  function doesn't happen to run because it doesn't need to. Noted as a remaining
  observation, not fixed (no real defect to fix).
- **Malformed-JSON edge case (verified safe):** a `json.load()` failure is caught by
  the pre-existing broad `except Exception as e: logger.error(...)` around the
  reload block, before reaching the validation call — `_settings_cache` retains
  whatever the last-known-good value was (or the safe hardcoded `defaults` on a
  first-ever failed load), never a corrupted or partially-applied state.
- **"Fail fast" interpretation, made explicit:** the fix logs a `CRITICAL` line
  immediately (operator-visible) the first time an invalid `active_strategy` value
  is loaded, but deliberately does **not** crash the engine process or halt trading
  outright. Reasoning: this process also manages every currently-open position's
  exits; a config-validation failure crashing the whole engine would strip risk
  management from any open position purely because of an unrelated typo in a
  different setting — the exact class of incident this entire validation window
  exists to prevent, not something to reintroduce as a side effect of a safety fix.
  A loud, deduplicated, immediate log line is judged the correct "fail fast for the
  operator" behavior without the operational risk of a full process crash.

Full suite: **371 passed** (350 this morning + 21 new tonight: 9 option_atr + 6
stale-candle-sweep + 5 integration + 1 premium-path-safety), zero regressions.

---

---

## 2026-08-07 (evening, post-close) — remediation sprint: 3 of the 5 top-priority findings from today's STRATEGY_AUDIT fixed and deployed

Market closed at 15:30 IST; this is a post-close fix pass against
`docs/STRATEGY_AUDIT_2026-08-07.md`'s consolidated risk register, scoped
to exactly the three findings approved for tonight (§1.1, §1.2, §4.7).
§2.1 (ATR unit mismatch) is design-only tonight per explicit instruction —
see the companion doc `docs/ATR_TRAILING_STOP_DESIGN_2026-08-07.md`, no
code touched for it. §2.2 (backtest engine architecture) explicitly out of
scope, not touched.

**Fix 1 — `ema_rsi_strategy.py`'s own instance of the 2026-08-06 livelock
signature (audit §1.2).** `generate_signals()`'s `signals[bullish] = 1` /
`signals[bearish] = -1` rebuilt via a single `np.select` call, identical
fix shape to yesterday's `registry.py` change. This is the strategy
actually live today (`active_strategy = "ema_rsi"`) and this line runs
upstream of `registry.py`'s already-fixed instance on every tick — the
most likely explanation for the "not conclusively ruled out" post-restart
CPU transients logged earlier today. 6 new tests
(`test_ema_rsi_signals_setitem_regression.py`), including an end-to-end
bit-identical comparison against the pre-fix implementation on realistic
OHLCV data.

**Fix 2 — no abort when `select_option()` fails (audit §1.1).** Entry path
used to fall through with `entry_symbol` still equal to the raw
underlying index symbol if option strike/expiry selection raised for any
reason — every downstream check would then treat the index's own price as
an option premium, a direct violation of the option-buying-only mandate.
Fixed by tracking `option_mapping_required`/`option_mapping_succeeded`
explicitly and aborting the tick via a new pure helper,
`_should_abort_missing_option_mapping()`, extracted specifically for
testability (mirrors this file's own existing precedent —
`_count_trades_already_executed_today`, `_build_preload_failure_alert`).
5 new tests (`test_option_mapping_abort_gate.py`) covering all four
required/succeeded combinations plus the `"premium"` strategy's exemption
(it never uses this code path at all — already gated by its own
`sig.is_tradeable` check).

**Fix 3 — no validation that `active_strategy` is a real registered
strategy name (audit §4.7).** A typo, or a strategy that failed to
auto-register due to an import error, would make
`registry.run_strategy()` raise on every tick forever, caught by a broad
handler and just logged — the engine would report healthy at the
process/health-check level while generating zero real trade signals
indefinitely. Fixed with `_validate_active_strategy()`, called once per
actual settings (re)load (not per-tick, so it can't itself become a
log-spam or CPU source) from inside `_load_settings()`. Logs one
`CRITICAL` line the first time a bad value is seen, stays quiet on
repeats of the *same* bad value, and warns again if that same bad value
reappears later after being corrected in between. 6 new tests
(`test_active_strategy_validation.py`), including one that pins
`institutional_momentum`'s registered name against
`momentum_strategy/__init__.py`'s actual `STRATEGY_NAME` so the two can't
silently drift apart (closing the exact class of doubt one of today's
audit forks flagged and this session then resolved by direct grep).

**Full suite: 350 passed (333 + 17 new across the three fixes), no
regressions.**

**Deployment.** No open position at deploy time (`active_positions.json`
was `{}`), market already closed — zero risk window. Restarted only the
`main.py` pair (PID 29784/16892 → 19416/16796); `api_bridge`/frontend
untouched. Clean boot confirmed: 1725 candles preloaded, WS reconnected,
prior day's PNL (+9,743.05) and the 3-trade daily cap correctly restored,
`/health` OK, no spurious `CRITICAL` from the new `active_strategy`
validation (today's real value, `"ema_rsi"`, correctly passes). `py-spy`
dump post-restart shows all threads idle/normal — no stuck pattern.

**Honesty about validation status — market is closed, none of these three
fixes have been live-exercised yet:**
- Fix 1 (ema_rsi livelock line): **cannot be live-verified tonight** —
  meaningfully re-checking this needs sustained live tick volume over
  hours, exactly the condition that triggers the pathology in the first
  place. **Pending: tomorrow's live session, watching CPU-delta trend
  across the full day rather than just the post-restart window.**
- Fix 2 (option-mapping abort gate): the failure condition it guards
  against (`select_option()` raising) has no known live trigger under
  today's normal conditions — there is nothing to observe live tonight or
  tomorrow that would exercise this path under normal operation. Verified
  via the extracted pure-function unit tests only. **Pending: no specific
  live re-verification plan beyond continued normal monitoring**, since
  forcing a live failure injection wasn't in tonight's scope.
  - Also noticed, not a bug, worth a note: `select_option()`'s Greek
    computation for a rejected (out-of-market-hours) candidate still runs
    to completion, i.e. before the market-hours/EOD-cutoff gates reject
    it later in the same tick — a real, if today's session confirmed
    small, wasted-computation ordering issue observed live at 18:34-18:35
    IST post-close, correctly rejected with no order placed or position
    left open. Not part of tonight's approved scope; flagged for a future
    pass, not fixed tonight.
- Fix 3 (`active_strategy` validation): confirmed live at boot tonight
  that today's real, valid `active_strategy="ema_rsi"` does NOT trigger a
  false-positive `CRITICAL`. The actual failure path (a genuinely invalid
  `active_strategy` value) has not been exercised against a real running
  process tonight. **Pending: no specific live re-verification planned**
  — this is a startup/config-validation code path, not tick-frequency
  behavior, so tonight's clean-boot confirmation is the primary evidence
  this fix needs.

**None of tonight's three fixes should be treated as fully validated until
Fix 1 specifically has survived a full live trading day with the CPU-delta
trend staying at or below the established ~15-17% baseline throughout —
not just immediately post-restart.**

---

## 2026-08-07 (close) — CRITICAL: new entries allowed right up to the EOD force-close cutoff, burning the entire daily trade cap on three sub-250ms fake round-trips

**Symptom.** Checking `state.db` at close-boundary time (16:40 IST) — not
the "0 trades" expected from the day's earlier quiet monitoring cycles —
found 6 trade rows, all from 15:15 IST: three BUY/SELL pairs, each pair at
the **identical price**, closed **50-250ms** after opening.

**Investigation.** Cross-referenced `logs/engine.log` for
2026-08-07 15:15:00, 15:15:28, 15:15:55: each shows a normal `ENTRY BUY
PUT ...` line (correct SL band, correct "TGT=NONE"), immediately followed
by `shared.exits.exit_engine: EOD Exit triggered ... at 2026-08-07
15:15:0X` and an `EXIT ... (Time-based EOD Exit)` line, all within the
same second. After the third round-trip, every subsequent real candidate
signal for the rest of the day was rejected with `Trade BLOCKED ...: Max
trades per day reached (3)` — the daily cap, meant to limit real trading
risk, was instead fully consumed by three trades that were never live
market exposure at all.

**Root cause.** `SmartExitEngine` (`shared/exits/exit_engine.py`)
force-closes every open position at/after `eod_exit_time` (default
`"15:15:00"`) — a sensible safety net against holding into the last
volatile minutes or a delayed close. But the entry path in `main.py` had
no matching cutoff: a signal could open a brand-new position at, say,
15:15:00.881, and the very next exit-evaluation tick (15:15:01.088, ~200ms
later) would immediately force-close it via that same EOD rule. This
repeated three times in 55 seconds before the daily cap itself stopped
further attempts. Net effect: the trade-cap counter, `state.db`, and the
day's realized-trade history all got polluted with fake round-trips that
carried real (if brief) position risk in a live paper account, and every
genuine late-session signal for the rest of the day was blocked purely
because the cap was already exhausted on these artifacts. This is exactly
the kind of production risk this validation window exists to catch before
it could happen with real capital.

**Why the earlier `is_market_open()` gate (2026-08-06) didn't catch this.**
That gate stops entries outside 09:15-15:30 IST; 15:15 is still well
inside that window by design — the EOD cutoff is a separate, tighter
constraint specific to the exit engine's own square-off time, which the
entry path never knew about.

**Fix.** Added `shared/market_hours.py::is_before_eod_cutoff()` +
`EOD_ENTRY_CUTOFF_TIME` (`15:15`, deliberately kept equal to
`SmartExitEngine`'s `eod_exit_time` default), following the exact same
shape/scope as the existing `is_market_open()` gate (NEW entries only —
already-open positions keep full exit management, including this same
EOD rule, regardless of time of day). Wired into `main.py`'s entry path
immediately after the market-hours check. 16 new tests in
`test_market_hours.py`, including one that pins `is_before_eod_cutoff`'s
cutoff constant against `SmartExitEngine().eod_exit_time` directly so the
two can't silently drift apart again. Full suite: 333 passed (317 + 16
new), no regressions.

**Deployment.** Market was already closed (16:40+ IST) and no position
was open at deploy time — zero risk window. Restarted only the `main.py`
pair (PID 20580/5380 -> 29784/16892); `api_bridge`/frontend untouched.
Clean boot confirmed: 1725 candles preloaded, WS reconnected, prior PNL
resumed, and the persisted daily-trade-cap mechanism (fixed 2026-08-05)
correctly restored "3 trade(s) already executed today" rather than
resetting to 0. **Not live-verified against a real 15:15 entry attempt**
— market is closed for the day, so this gate's first live exercise will
be tomorrow's session; verification today is unit-test-only.

**Today's other finding:** see the CPU/registry.py `np.select` fix
earlier in today's entries (deployed 13:49:37 IST, confirmed holding —
CPU settled to 14.1-14.8% across two clean post-fix cycles before this
EOD-cutoff issue was found at close).

**Trade-cap accounting note.** The 3 phantom round-trips are not undone —
`state.db`'s trade rows and the persisted daily-cap counter for
2026-08-07 are left as the true record of what actually executed, matching
this log's established practice of never rewriting historical state. This
matters for any future PnL/trade-count read of today: **3 of today's
trades are known non-representative artifacts, not real strategy
performance**, in the same spirit as the 2026-08-06 stale-snapshot entry's
flagged-unreliable trades.

**Status: today's session found 2 new issues** (the registry.py CPU
finding and this EOD-entry-cutoff finding), both fixed and unit-tested,
only the first live-reverified before close. **Not a "zero new findings"
session** — the validation clock resets again from today.

---

## 2026-08-07 (midday) — elevated CPU (58-71% vs. ~15-17% baseline) traced to a second, previously-unfixed incremental-`Series.__setitem__` call site; fixed and redeployed

**Symptom.** Routine monitoring cadence (09:52/10:22/10:57 IST CPU-delta
checks all read 15.2-17.5%, the established quiet-market baseline). The
11:22 IST check read **71.6%** — no new trade/signal-candidate log lines
explained it (only sentiment heartbeats since the last bookmark), so per
the standing escalation rule (50%+ CPU → `py-spy dump`) this was
investigated rather than assumed benign.

**Investigation.** Several `py-spy dump --pid <pid>` snapshots a few
seconds apart: MainThread was idle in every dump (the event loop itself
was never blocked — the 2026-08-06 livelock's most dangerous symptom was
absent), and the worker thread (`asyncio_0`, correctly running via
`asyncio.to_thread`) showed genuinely different call chains each time —
`get_cpr_rejection_masks`'s groupby aggregation, `supertrend`/`atr`
computation, then one dump caught `StrategyRegistry.run_strategy`
(`trading_bot/strategies/registry.py:51`, `filtered_signals[f_bull] = 1`)
active inside `Series.__setitem__ -> _set_with_engine -> Index.get_loc ->
Series.__repr__ -> to_string -> _get_formatted_values`. This is a
livelock-shaped stack (real work, forward progress, no repeated-frame
hang) rather than a deadlock, but that exact `get_loc`/`repr()` call-chain
signature also appears in the 2026-08-06 CPU-livelock investigation's own
`py-spy` dumps (see that entry, "The stack changed between every dump" —
one of the listed frames is "a `KeyError`/`repr()` path (`Series.__repr__`
via `get_loc`)"). That day's fix only targeted the three incremental-
*column*-insert call sites (`compute_features`, `supertrend`,
`generate_signals`); it never touched this incremental-*boolean-mask*-
assignment call site in `registry.py`, which is architecturally the same
class of problem (an incremental `Series`/`DataFrame` mutation hitting a
costly pandas/pyarrow index-machinery path under this app's specific
long-running-process conditions) at a fourth call site nobody had looked
at. Re-checked: no open position at the time (last trade was yesterday,
2026-08-06 10:43 IST) — zero capital risk while investigating.

**Root cause.** `run_strategy`'s post-institutional-filter signal
construction built `filtered_signals` via two incremental boolean-mask
`Series.__setitem__` calls (`filtered_signals[f_bull] = 1`,
`...[f_bear] = -1`) instead of building the result in one vectorized call.
An isolated 200-call offline benchmark showed this is ~5x more expensive
than the alternative even at a small scale (0.59ms vs. 0.11ms mean per
call on a 2000-row frame) — real but modest in isolation, consistent with
2026-08-06's own finding that isolated short benchmarks understate this
class of cost, which "accumulates across many repeated calls within one
process's lifetime" rather than showing up in a fresh, short-lived
interpreter.

**Fix.** `trading_bot/strategies/registry.py`: `filtered_signals` now
built via a single `np.select([f_bear.to_numpy(), f_bull.to_numpy()],
[-1, 1], default=0)` call, eliminating both `Series.__setitem__` calls on
it entirely (bear listed first so it wins on the — structurally
impossible in real usage, since `bullish`/`bearish` derive from mutually
exclusive signal values — overlap case, preserving the original overwrite
order). 4 new regression tests
(`test_registry_filtered_signals_regression.py`): bit-for-bit match
against the pre-fix implementation on a real boolean-mask distribution,
an all-False case, a forced-overlap case confirming overwrite-order
parity, and an end-to-end `run_strategy` call through real institutional
filters. Full suite: 317 passed (313 + 4 new), no regressions.

**Deployment.** No open position → safe window. Stopped and restarted
only the `main.py` process pair (PID 476/24764 → 20580/5380), leaving the
healthy `api_bridge` pair and frontend untouched. Clean boot: 1705
candles preloaded, WebSocket reconnected, prior day's PNL (+9,743.05)
correctly resumed, `/health` OK. Post-restart `py-spy` dumps (5 taken
across ~10s) show no recurrence of the `get_loc`/`repr()` signature at
`registry.py:51` — the fixed line specifically is confirmed gone from the
observed call chains.

**Honesty about confidence level.** CPU-delta readings in the first ~60-90s
post-restart ran 44.7-46.7% — elevated vs. the ~15-17% established
baseline, but 2026-08-06's own restart showed the identical pattern
(59-67% in the first ~90s, said there to be "plausibly just real
intraday tick volume... not conclusively ruled out"). This fix closes one
concretely-identified, previously-unaddressed contributor sharing the
exact call-chain signature seen in the actual livelock, verified via
bit-identical tests and live `py-spy` confirmation that the specific line
is no longer reproducing — but it is **not** proven to be the sole or
complete explanation for the 58-71% readings, and the same "not fully
proven under sustained load" caveat from 2026-08-06 applies here too.
Continuing to monitor at a tightened cadence to see whether CPU settles
toward baseline as the post-restart transient passes, per the same
practice as every prior restart this validation window.

---

## 2026-08-06 (midday) — CRITICAL: the 4-instrument engine livelocks on ~2 of 3 restarts; temporarily reverted to NIFTY-only

Found during the first continuous-monitoring cycle after deploying the
tick-staleness/market-hours fixes below. This is the most severe finding
of the day and **blocks any GO recommendation on its own** — §2.10 of
`docs/GO_NO_GO_CHECKLIST.md` requires "no performance decay... engine
process still responsive," and this violates it directly and repeatedly.

**Symptom.** After restarting `main.py` with all four instruments
(NIFTY/SENSEX/BANKNIFTY/FINNIFTY) live, the process would sometimes go
completely silent — zero new `engine.log` lines, zero sentiment-fetch
heartbeat (normally every ~5 min) — while `Get-Process`'s CPU counter
showed **97–100% sustained utilization** (confirmed via two independent
before/after CPU-delta measurements a few seconds apart, not a single
misleading cumulative-counter snapshot). The process was never
unresponsive at the OS level (`/health` always returned 200) and never
crashed — it just stopped doing anything useful while consuming an
entire CPU core. Reproduced on 2 of 3 restarts today; the one restart
that looked clean (13:11 IST) was only observed for ~10 minutes before
being superseded, so it may simply not have been watched long enough to
catch onset.

**Investigation.** `py-spy dump --pid <pid>` (installed fresh into the
venv for this — not previously available) taken repeatedly across both
livelocked instances, several seconds apart each time:
- The stack **changed between every dump** — `get_aggression_masks`
  (institutional filters) → `supertrend`'s indicator loop →
  `ema_rsi_strategy.generate_signals` → pandas Arrow-string `.insert()`
  internals → a `KeyError`/`repr()` path (`Series.__repr__` via
  `get_loc`) → `rsi()`'s `.clip()`. This rules out a **deadlock** (which
  would show the identical frame every time) — it is a **livelock**:
  real, ordinary indicator/strategy computation genuinely executing and
  completing, just never finishing a full evaluation cycle across all
  four symbols before the next tick makes it start falling behind again.
- One dump caught the computation running directly on **MainThread**
  (not the `asyncio.to_thread` worker) inside `rsi()` — meaning
  `compute_features()`, which `on_tick` calls synchronously
  (unlike `registry.run_strategy`, correctly wrapped in
  `asyncio.to_thread`), can itself block the event loop directly when
  slow. This is the more dangerous of the two: while it's running,
  *nothing* else can happen on that tick, including exit-checks for any
  open position on a different symbol.
- Offline benchmark, to rule out "the code itself is just slow": loaded
  the full 22,781-row real NIFTY cache and timed `registry.run_strategy
  ('ema_rsi', ...)` and `compute_features()` directly — **0.1s and
  0.03s respectively**, nowhere close to explaining a 20+ minute stall.
  The problem is not raw per-call cost; it's aggregate load (up to 4
  symbols' worth of full re-evaluation contending every ~0.2s) crossing
  a threshold this architecture cannot sustain, likely worsened by
  `compute_features` running unthreaded on the event loop and/or a
  WebSocket keepalive-timeout reconnect (`1011 keepalive ping timeout`,
  observed in `fyersApi.log` at 13:20:12) delivering a backlog of ticks
  that all demand evaluation near-simultaneously.

**Root cause: not fully pinned to one line.** This is stated plainly
rather than overclaiming certainty the evidence doesn't support. What
*is* established with high confidence: (1) it is compute-bound
aggregate load from the multi-instrument expansion, not a hang/deadlock;
(2) `compute_features` runs synchronously on the event loop where
`registry.run_strategy` does not, which is architecturally the riskier
half; (3) it reproduces at a real rate (~2/3 today) specifically with 4
concurrent instruments and has never once been observed with NIFTY
alone, today or in any prior session across this entire validation
window.

**Immediate mitigation — reverted `symbols` to NIFTY-only.**
`config/settings.json`'s `symbols` list temporarily set back to
`["NSE:NIFTY50-INDEX"]`, restarted, confirmed stable (~18–19% CPU across
two consecutive 10s delta measurements, vs. 82–100% on the 4-symbol
config). This is a live-system stability rollback, not a reversal of the
earlier "enable all 4 now" decision — the multi-instrument code itself
(strike selection, confidence gating, symbol normalization) is unaffected
and re-tested; only how many instruments are concurrently watched was
turned back down until the performance issue has a real fix. **Flagging
for an explicit decision on the path forward** rather than silently
guessing at one: profile and fix `compute_features`/indicator cost
properly (move it off the event loop, cache/incrementally update instead
of full-recompute per tick), reduce eval frequency for secondary
instruments specifically, or keep NIFTY+SENSEX only until BANKNIFTY/
FINNIFTY get their own performance pass.

**Also fixed today, as a direct result of this investigation — engine-
wide stall detection.** `find_stale_positions` (from the earlier entry
below) only ever checks symbols with an open position, by design. This
incident happened while completely flat, so it went undetected by that
watchdog and was only caught by a human manually cross-referencing
process CPU against log timestamps — exactly the kind of check this
continuous-monitoring session exists to do, but it should not require a
human doing it by hand. Added `shared/risk/tick_staleness.py::
seconds_since_any_tick()` (pure function, engine-wide instead of
per-position) and wired it into the same watchdog task, gated to real
market hours via today's `is_market_open()`. Logs a `WARNING` and a new
`AuditEvent.ENGINE_STALL` audit record if no tick has landed for *any*
watched symbol within `engine_stall_warning_s` (default 90s), regardless
of open positions. 5 new tests. Deployed with the NIFTY-only restart
above.

**Update — real root cause found and fixed** (same investigation,
continued). The livelock reproduced a THIRD time — this time on the
NIFTY-only rollback itself, 11 minutes into an otherwise-idle restart
(`py-spy dump` again: MainThread itself stuck, not just the worker
thread, inside `compute_features -> DataFrame.__setitem__ -> _set_item
-> Index.insert()`). This disproved the "4-instrument load" theory —
the trigger is not instrument count, it is **pandas 3.0.3's
`Index.insert()` cost for incremental `df["new_col"] = value` column
assignment**, hit by three call sites on every evaluation cycle:
`shared/ai/features.py::compute_features` (19 incremental columns, called
~5x/second — by far the dominant contributor), `shared/indicators/
supertrend.py::supertrend` (6 incremental columns on a fresh copy every
call), and `trading_bot/strategies/ema_rsi_strategy.py::generate_signals`
(4 incremental columns, written directly onto the live aggregator's own
stored DataFrame). Two isolated offline benchmarks (a fresh CSV read, and
a `pd.DataFrame(list-of-dicts)` construction matching the live
aggregator's own shape) both stayed fast — ruling out "the code is
inherently slow" and pointing at something that accumulates across many
repeated calls within one process's lifetime (a known category of issue
with pandas' PyArrow-backed string-dtype machinery), not a function of
input size.

**Fix:** rewrote all three functions to build every intermediate value as
a plain `Series`/array first and construct the output DataFrame exactly
once with every column already known (`pd.DataFrame(columns_dict,
index=...)`), instead of growing the column index one `Index.insert()`
call at a time. Verified bit-for-bit identical output against the
pre-fix implementation on real data (100/500/full-22,787-row samples for
`compute_features`; 100/500/full-22,788-row for `supertrend`;
200/1,700/full-22,789-row for `generate_signals` — every value matches
to floating-point equality, same columns, same index, and neither
`supertrend` nor `generate_signals` mutates its caller's DataFrame,
matching prior behavior). 11 new regression tests
(`test_incremental_column_insert_regression.py`), including a bounded
repeated-call smoke check.

**Honesty about confidence level.** A 6,000-call offline stress test
(simulating ~20 minutes of real eval cadence) showed per-call cost was
flat for the first ~4,000 calls then climbed 2.4x (13ms -> 33ms) — better
than the unbounded pre-fix growth, but not proven to be perfectly flat
forever. Tried globally disabling pandas' `future.infer_string` option as
a possible deeper fix; inconclusive and the test run itself became
markedly slower, so that avenue was abandoned as more likely to introduce
new risk than resolve this one within the time available — flagged as a
follow-up avenue (a pandas version pin/downgrade), not pursued further
today. Live-verified after deploying: `py-spy dump` immediately post-fix
showed the classic pre-fix signature gone (no thread stuck reproducing
the same call chain across repeated dumps) — 3 rapid successive dumps
showed the process genuinely alternating between idle and brief active
bursts, the expected healthy pattern, rather than the permanently-stuck
signature of every single pre-fix dump today. CPU-delta readings in the
first ~90s post-restart ran higher (59-67%) than the very first healthy
baseline observed hours earlier (18%) — plausibly just real intraday tick
volume rather than a residual problem, but not conclusively ruled
out. **Continuing to monitor closely, tight cadence, rather than
declaring this fully closed.**

**Status: today's session has now found 4 new issues** (tick staleness,
market-hours gate, engine-wide stall detection, and this CPU livelock),
**3 of 4 fully fixed and verified, 1 (engine-stall detection) mitigating
rather than eliminating its trigger** — the livelock's root cause is now
understood and fixed with high confidence, but not yet proven under
sustained real-world load for long enough to close outright. Far from a
"zero new findings" session.

---

## 2026-08-06 (morning) — deployed the new option stop-loss + ATM/ITM/multi-instrument architecture; found a position that traded and then sat unmonitored for 7h49m

Session context: the previous evening's work (still same continuous
session) implemented (1) premium-banded initial stop-loss with no fixed
profit target, (2) a hard ATM/ITM-only clamp on strike selection, and (3)
expansion from NIFTY-only to all four instruments (NIFTY, BANKNIFTY,
FINNIFTY, SENSEX) with NIFTY/SENSEX given a lower AI-confidence bar. Both
were unit-tested (206 + 58 = 264 tests) and briefly live-verified at
restart, but neither had been through a real continuous-monitoring
session yet — today is genuinely session 1 for this code, regardless of
what came before it for the old flat-percentage-SL code path.

### CRITICAL (found, root-caused, partially fixed; part flagged as policy) — a position opened at 02:50 IST off a stale post-restart snapshot, then received ZERO risk management for 7h49m because nothing detects a silent tick feed

**Symptom, found while doing the routine pre-monitoring state.db check:**
`trades` row id 24 — `NSE:NIFTY2681124600CE BUY qty=130 @ 132.95` —
timestamped `2026-08-06T02:50:00`, hours before NSE market open (09:15
IST) and minutes after an unrelated process restart (02:46:43 IST, done
to deploy the stop-loss architecture itself).

**Investigation.** `engine.log` lines 28924–28978 are the complete record
of that process's life before the next restart at 10:39:28 IST — 54
lines total, and every one of them accounted for:
```
02:46:46  Starting live bot with symbols: ['NSE:NIFTY50-INDEX']
02:46:47  Connected to API Bridge WebSocket!
02:50:00  Auto-mapped NIFTY CE signal to Option: NSE:NIFTY2681124600CE
02:50:00  SL BAND ₹100-150 | premium ₹132.95 -> SL ₹114.65 (banded)
02:50:00  ENTRY BUY CALL ... qty=130 @ 132.95 | TGT=NONE (trailing/smart-exit)
10:09:47  Settings reloaded instantly from disk.        <- next line, 7h19m later
```
Between `02:50:00,193` and `10:39:28` — **7 hours 49 minutes** — there is
no other line referencing this symbol, no tick, no exit-check, nothing.
`trading_bot.main.on_tick()` is invoked purely by the broker's WS message
callback (`brokers/fyers_broker.py:697`); there is no independent timer.
Every piece of exit management (trailing stop, hard SL, partial booking,
pyramiding) lives inside `on_tick`. **If the tick feed goes quiet while a
position is open, nothing manages that position for as long as the
silence lasts, and nothing existing reports that this is happening.**

The entry itself: one tick evaluated at `02:50:00` (3m13s after WS
connect — consistent with the strategy's warm-up threshold on a single
static post-connect snapshot, not a live stream), a signal fired on it,
and the engine happily opened a real paper position using that snapshot
premium at half past two in the morning. A real broker would reject any
order placed outside the exchange session; nothing in this system does.

**What happened when ticks finally resumed** (10:39:28, first tick after
market reopened elsewhere in symbols/restart): the position's premium
appeared to the engine to have moved from 132.95 to ~181.00 in a single
step — a ~36% "jump" that is not a real market move, it is the gap
between a stale snapshot and the first live quote 7h49m later. That
single evaluation cascaded: `TRAILING SL MOVED 114.65 -> 132.95`,
`Partial Profit Booking (1:1.0)`, then two immediate `PYRAMID SCALE`
entries (32 qty @ 181.00 and 32 qty @ 180.45) — all real exit/sizing
decisions made in response to a data artifact, not genuine price
discovery. This directly contaminates today's headline equity/PnL figures
(equity 109,668.70, pnl +9,743.05 as of the restart) — a meaningful share
of that gain is the stale-to-live snapshot gap, not trading skill or real
market movement. **Today's PnL figures must not be used as-is for the
§2.9 evidence package** without excluding this trade or noting the
distortion explicitly.

**Root cause, precisely:** two independent gaps, not one bug:
1. No gate prevents a *new* entry from executing outside real exchange
   trading hours.
2. No mechanism detects or reports that an *already-open* position has
   gone unmonitored because the tick feed has been silent.

**Fix applied — (2) only, as pure observability, no behavior change:**
new `shared/risk/tick_staleness.py` (`find_stale_positions`, pure
function) plus a background `tick_staleness_watchdog()` task in
`main.py`, checking every 30s whether any open position's underlying has
gone >= `tick_staleness_warning_s` (default 90s — above the §2.11 idle
reconnect baseline of ~160s between individual reconnects, but well
below "hours") without a tick, logging a `WARNING` and a new
`AuditEvent.TICK_STALENESS` audit record (re-alert throttled to once per
5 minutes per symbol to avoid log spam on an ongoing gap). This does
**not** halt trading, block entries, or touch any position — it only
makes a previously-invisible condition visible. Generalizes beyond the
overnight case: the identical mechanism would leave a position equally
unmonitored during a genuine multi-minute WebSocket outage in real
market hours with real capital at risk, which is the reason this was
fixed immediately rather than filed as "overnight-only, low priority."
10 new tests (`test_tick_staleness.py`). Deployed and live-verified: main.py
restarted 11:17:33 IST, clean boot, zero errors, watchdog confirmed silent
(as expected — no open positions, and the market is open so this
session's ticks are flowing normally).

**Update — market-hours gate confirmed and implemented.** Flagged as a
policy decision above; asked, and confirmed: add a hard market-hours gate
on new entries, existing open positions unaffected. Implemented as
`shared/market_hours.py::is_market_open()` (pure function, weekday +
09:15–15:30 IST, mirrors `frontend/lib/ist-time.ts`'s `isMarketOpenIST()`
exactly so both sides of the system agree on the definition — no holiday
calendar, matching the existing frontend indicator rather than
introducing a second, stricter standard). Wired into `main.py`
immediately after `if latest_signal == 0: continue`, common to both
entry paths (the "premium" strategy branch and the generic index
auto-map branch both converge there) — before any SL/sizing/order-
placement work happens, and never consulted anywhere on the exit path.
An explicit, loud `market_hours_override` settings key exists for
deliberate manual testing outside real hours, distinct from silently
disabling the gate. 23 new tests (`test_market_hours.py`) covering the
exact incident timestamp, both window boundaries, weekends, timezone
conversion, and the override. Deployed and live-verified: `main.py`
restarted 12:04:33 IST (no open positions at restart, so no disruptive
re-evaluation this time), clean boot, zero errors.

### Also observed, not new — the AI-confidence override is unconditionally active on every trade
Every entry log line today shows `AI Confidence Override active (100%)
-> Risk Limit increased to 3.5%`. This is the same root cause already
documented in `docs/OPTION_STOP_LOSS_ARCHITECTURE.md` §7 and
`docs/ATM_ITM_AND_MULTI_INSTRUMENT_ARCHITECTURE.md` §7 (with
`enable_ai_filter` off, `main.py` falls back to a hardcoded
`confidence = 1.0`, which is `>= high_confidence_threshold` (0.85) by
construction) — noted here only because today's live logs are the first
direct, concrete confirmation that it fires on *literally every single
entry*, not an occasional edge case. Concretely: every trade today has
been sized at the elevated 3.5% per-trade risk tier, not the intended
base 1% tier. Not a new finding; re-flagged because the concrete evidence
belongs in this log alongside today's other findings, and because it
means today's position sizes (and therefore PnL swings) are ~3.5x larger
than the base-tier config would produce.

**Status: today's session already has 1 new bug found and fixed (tick
staleness observability) plus 1 new policy question raised (market-hours
entry gate) before market-hours continuous monitoring has even properly
begun.** Continuing the "session with zero new findings" pattern from
prior days — not yet met.

---

## 2026-08-05 (evening) — designing a safe §2.8 kill-switch test found it was completely non-functional; also found and fixed a real ~2-hour full-server freeze

Tasked with designing a safe way to test §2.6/§2.8 ahead of the next live
session (market closed, positions flat — the right time to poke at this).

### CRITICAL — the kill switch (`/api/panic-exit`) never actually closed anything in paper mode, and had zero cross-process effect even conceptually
**Investigation, not yet a symptom anyone had seen — found by reading the
code before trying to test it:** `panic_exit()` only ever called
`broker.get_positions()` / `broker.get_order_book()` / `broker.place_order()`
directly. Confirmed via `brokers/fyers_broker.py`: `get_positions()` and
`get_order_book()` **both unconditionally return `[]` in paper mode**
(no persistent broker-side state, same root fact behind the 2026-08-05
morning reconciliation incident). So the endpoint would always report
`closed=0, cancelled=0` and never touch anything, no matter what
`trading_bot/main.py` actually had open.

Worse, independent of paper/live mode: `main.py` and `api_bridge.py` are
**separate OS processes** with no shared in-memory state at all. Even a
real broker order placed by `panic_exit()` would leave main.py's own
`active_positions` dict and risk state completely unaware anything
happened — it could keep "managing" (or scaling into) a position that was
just manually flattened, or place a duplicate closing order of its own
later. The kill switch was non-functional end-to-end for the entire
validation window to date, in a way that would never have been visible
except by deliberately testing it — the endpoint always returned
`{"status": "success"}` regardless.

**Fix:**
1. Extended `compute_reconciliation()` (the same pure, 11-test-covered
   decision logic behind WebSocket-reconnect reconciliation) with an
   optional `live_prices` parameter — a fresh quote per symbol, checked
   after a real order-book fill but before the stop-loss estimate
   fallback. 5 new tests (`tests/test_reconciliation.py`, 16 total now),
   all existing tests unchanged/still passing (fully backward compatible).
2. Added `emergency_flatten_all_positions()` to `main.py`: fetches a live
   quote per open position and reuses `compute_reconciliation()` to decide
   exit price/PnL/state_action — not a second hand-rolled copy of that
   math.
3. Added a cross-process `emergency_stop` flag in `config/settings.json`
   (main.py already reloads that file every tick for other settings, so
   this needed no new polling mechanism). `on_tick()` checks it first,
   ahead of the existing `is_active` halt (which only freezes processing —
   wrong behavior for a panic exit that needs to actively flatten
   positions, not just stop touching them).
4. `panic_exit()` now sets this flag as its primary action (the
   broker-level cancel/close calls are demoted to a best-effort,
   live-mode-only layer that can no longer block the response on failure).
   Added `GET /api/panic-exit/status` and `POST /api/panic-exit/clear`
   (localhost-only, like the trigger) so an operator can confirm the
   engine actually went flat and deliberately re-arm normal trading.
5. New `EMERGENCY_STOP` audit-log event type.
6. 13 new tests (`tests/test_panic_exit.py`) exercising the real FastAPI
   app via TestClient, isolated to a `tmp_path` config directory so
   nothing ever touches this machine's real, disk-backed
   `settings.json`/`active_positions.json` (the exact hazard
   `test_order_rate_limit.py`'s own docstring already documents from a
   past incident).

**Live-verified end to end against the actually-running system** (safe to
do — positions were flat, so there was nothing to actually close): created
a real session token, called the real `/api/panic-exit` → confirmed
`emergency_stop: true` written to the real `config/settings.json` →
confirmed via `engine.log` that `main.py` picked it up on its very next
settings reload and stopped all further signal evaluation immediately →
confirmed via `/api/panic-exit/status` → called `/api/panic-exit/clear` →
confirmed normal tick processing resumed. This is a real, live pass of the
cross-process wiring; **still needs one more live confirmation with an
actual open position during market hours** (see the test plan below) to
fully close out §2.8 — tonight only proved "empty positions" flattens
correctly (trivially true) and that the halt/resume signal reaches
main.py, not that a real position gets closed at a real price.

### CRITICAL — found while trying to run the drill above: api_bridge.py had been completely frozen for ~2 hours, silently
**Symptom:** every request (including the public, no-auth `/health`
endpoint) got `Connection refused`, despite the process still showing as
`LISTENING` on port 8000 in `netstat` and consuming real CPU/kernel time.
`main.py`'s own WebSocket client had been failing every reconnect attempt
with `timed out during opening handshake` continuously since ~18:19 IST —
over 2 hours, completely unnoticed, because my own process-health checks
all day checked "is the process alive" (via `tasklist`/`wmic`) and "are
logs still advancing," never "does it actually respond to a request."

**Root cause:** three FastAPI route handlers (`/api/funds`, `/api/quote`,
`/api/option-chain`) each instantiate `fyers_apiv3`'s `FyersModel` with
`is_async=False` — a **synchronous, blocking** HTTP client — and call it
directly inside an `async def` handler with no `await`. uvicorn's default
config here is a single process, single event loop: a blocking call
anywhere freezes literally everything else being served by that process —
every other HTTP route, every open WebSocket connection (including
keepalive pings, which is exactly what made `main.py`'s tick feed die),
until that one blocking call returns. `api_bridge.py`'s own logs show its
last successful request was `/api/option-chain?symbol=NIFTY` at 18:19:11 —
consistent with a subsequent call to the same endpoint (dashboard-tab
polling) hanging on Fyers' API and never returning, taking the whole
server down with it. No crash, no exception, no error logged anywhere —
it just silently stopped accepting anything.

**Fix:** wrapped all three blocking `FyersModel` calls in
`asyncio.to_thread(...)`, offloading them to a thread pool so the event
loop stays free to keep serving everything else while a slow/hung Fyers
response is in flight. Minimal, behavior-preserving change (same calls,
same return values, just non-blocking). Restarted api_bridge.py to deploy;
confirmed clean startup and a real `/health` 200 OK afterward.

**Process lesson, folded into future monitoring:** "is the process alive"
and "are logs advancing" are not sufficient to confirm an HTTP server is
actually serving requests — a hung single-threaded event loop can look
perfectly healthy by both of those signals while refusing every
connection. Future health checks should include an actual request (even
just `/health`), not just process/log inspection.

**Not investigated further tonight (pre-existing, not part of this
incident):** `main.py`↔`api_bridge.py`'s WebSocket connection has been
dropping with `1011 keepalive ping timeout` roughly every 60-90 seconds
continuously since the api_bridge restart, each time reconnecting
successfully within ~5 seconds. Reconnects are clean (paper mode
correctly no-ops reconciliation each time, per this morning's fix) and
nothing is lost, but this frequency is far above the §2.11 baseline
(~1 reconnect/160s) and should be looked at as its own item — flagging
rather than chasing tonight given the two fixes above already covered a
lot of ground.

### Live test plan for tomorrow's market open (to fully close out §2.8)
1. Let a real signal open a small position normally (or use the dashboard
   to place one deliberately, if idle).
2. Call `/api/panic-exit` while it's genuinely open.
3. Confirm within ~1 tick: `engine.log` shows an `EMERGENCY STOP: closed
   ... at ...` line, `config/active_positions.json` goes back to `{}`,
   `state.db`'s `trades` table gets the closing leg, and equity/pnl update
   correctly.
4. Manually recompute the PnL from raw entry/live-exit price and confirm
   it matches (this doubles as part of §2.9's evidence).
5. Call `/api/panic-exit/clear`, confirm a fresh signal can open a new
   position normally afterward (proves the halt doesn't get "stuck").
6. Record the exact log lines and `state.db` rows as the §5 evidence
   package's §2.8 entry — this is the first genuinely real trigger, not a
   synthetic/empty-position one like tonight's.

---

## 2026-08-05 — end-of-day wrap-up

**Session:** continuous monitoring from ~12:57 IST through market close
(15:30 IST) and past it to 16:47 IST, on top of the morning's own
full-reset session (10:46 IST restart, see below). ~18-minute check
cadence during market hours per established preference.

**Trades:** 12 completed option round-trips today (23 raw BUY/SELL rows
in `state.db`, all NIFTY weekly CE/PE — see the entries above for the
detailed breakdown). Should have been 3 — the other 9 came from the
now-fixed daily-cap-doesn't-survive-restart bug,
each triggered by one of my own monitoring/fix-deploy restarts. All 9
"extra" trades closed at exactly breakeven (flat market each time), so
**zero net financial impact**, but this could have gone differently in a
moving market — see the trade-cap entry above for the honest accounting.
Final state: equity 99,925.65, daily pnl -74.35, `active_positions.json`
flat (`{}`) at close.

**Findings today (4, all fixed and live-verified same day):**
1. Test-suite output leaking into the live `fyersApi.log` (via
   `api_bridge.py`'s root-logger handler attached at import time) —
   caused 4 false "circuit breaker tripped" alarms across the day.
2. (Investigated, no fix needed) SignalAgent LSTM "model not found" /
   "today is 2099" errors — same test-log-leakage bug, not live.
3. Entry-side option-premium fetch had no rate-limit throttle — caused a
   ~250-error burst right at market close.
4. `RiskManager.trades_today` never survived a restart — let the daily
   3-trade cap be silently reset (and re-hit) up to 4 times today.

Also investigated but left unresolved (non-blocking, documented above):
the intermittent `broker_credentials.json` integrity-check false alarm
(paper mode never reads these credentials, so zero effect on validation —
flagged for the live-mode Go decision) and confirmed the "duplicate
process" pattern from this morning is a benign git-bash/venv launch
artifact, not a real competing-engine risk.

**Current GO/NO-GO status: NO-GO**, unchanged. Today did not produce a
"zero new findings" session — 4 genuine bugs found and fixed. Per the
checklist's own rule, today does not advance the clean-session count.
§2.6 (reconciliation while holding a position) and §2.8 (kill-switch) are
still untested. Two items still need the user's own action (Fyers
API-key rotation; migrating/deleting `trading-system/settings.json`'s
plaintext legacy credentials) — unchanged from earlier reports, mentioning
again since it's been a few sessions.

**Process observation worth carrying forward:** 3 of today's 4 bugs
(everything except the credentials flakiness) were only discoverable by
actually restarting the live engine to test a fix — and one of those
restarts itself (finding #4) was a genuine new risk introduced by the
monitoring/fixing process itself, not something that existed before today.
Worth keeping in mind: a restart during active monitoring is not a free
action even when done carefully with `active_positions.json` checked
first.

Continuous monitoring stopped for today (market closed, positions flat,
no rescheduled check pending). Will resume next live session.

---

## 2026-08-05 (market-close session) — entry-side quote-fetch rate-limit burst at close; daily trade cap didn't survive a restart

### 15:37-15:40 IST — real burst of ~250 Fyers /quotes rate-limit + empty-body errors right at market close
**Symptom:** `fyersApi.log` showed a genuine (not leaked-test-output this time)
burst of ~130 "Expecting value: line 1 column 1" JSON-decode errors and
~250 "request limit reached" (429) errors from Fyers' `/quotes` endpoint,
concentrated in a 2-3 minute window right around the 15:30 IST close.
Distinct from the already-fixed 10:00 IST burst (which had fully tapered
off through 11:00-14:00) — this was a new pattern.

**Root cause:** `trading_bot/main.py`'s entry-candidate premium fetch
(`broker.get_market_data([entry_symbol])`, ~line 1350) had no throttle at
all, unlike the exit-check path a few hundred lines below it which was
already throttled on 2026-08-04 for the identical reason. Near/after
market close, elevated volatility drives rapid re-evaluation across many
different candidate strikes in quick succession, each firing its own
unthrottled quote fetch — self-inflicted rate-limiting, same failure mode
as the earlier exit-side incident, just on the entry side and triggered by
a different condition (strike churn near close vs. per-tick exit checks).

**Fix:** reused the exact same per-symbol `(timestamp, premium)` cache and
1-second throttle interval already used by the exit-check path. Also added
a *separate* short-lived failure cache (`_entry_premium_failure_cache`) —
the success-only cache alone didn't help here, since after close quotes
mostly never succeed at all, so a cache that only remembers successes never
engages. The failure cache also throttles the "could not fetch premium"
warning log itself (was logging on every single throttled attempt).
**Verified live:** redeployed at 16:20 IST — rate-limit/JSON-decode errors
dropped from ~250/2min to **zero** in the following window, and the
"could not fetch" warning frequency dropped from several times/second to
roughly once/second per symbol as intended.

### Found while fixing the above — daily trade cap (max 3/day) did not survive a restart; real cap exceeded 4x today
**How this was found:** deploying the fix above required 3 separate
`main.py` restarts today (13:05 for the log-leakage fix, 15:53 and 16:20
for this fix). After the 16:20 restart, `state.db` showed **12** real
option-exit trades today instead of the configured cap of 3.

**Root cause:** `shared/risk/manager.py`'s `RiskManager.trades_today` is a
plain in-memory list, always initialized empty (`self.trades_today: List =
[]`) with no restoration from persisted state — unlike `daily_pnl` and
`current_equity`, which were already fixed for this exact restart-survival
reason earlier today (see the 2026-08-05 §0-adjacent entries above). Every
`main.py` restart during the trading day silently reset the count to zero,
and the strategy correctly re-hit the "fresh" 3-trade cap each time:
3 trades at 11:55 (organic, before any restart today), 3 more at 13:45
(after the 13:05 restart), 3 more at 16:15 (after the 15:53 restart), 3
more at 16:20 (after the 16:20 restart) — 12 total, 4x the intended daily
limit, entirely because of restarts I performed to deploy other fixes.

**Financial impact: zero.** All 9 "extra" trades (beyond the first
legitimate 3) show identical buy and sell price per leg — the market was
flat/quiet in each case, so every extra round-trip closed at exactly
breakeven. `state.db`'s equity/pnl are unchanged by this finding. This
does not generalize to future occurrences, though — a restart during an
actively-moving market could have let extra trades through at real risk,
not breakeven.

**Fix:** added `_count_trades_already_executed_today()` (pure, unit-tested
in `tests/test_daily_trade_cap_persistence.py`) to `trading_bot/main.py`,
which reconstructs today's real completed-trade count from `state.db`'s
raw trade rows (options-only exits are unambiguous: this system only ever
buys options, so an exit is always tagged `side="SELL"` on a CE/PE symbol,
entries never are) and seeds `risk_manager.trades_today` with that many
placeholder records on startup. **Verified live:** the 16:47 IST restart
logged `Restored 12 trade(s) already executed today into the daily trade
cap (was about to reset to 0)` — correctly reflecting today's real count
and preventing the cap from silently resetting again.

**Process note for future restarts during market hours:** every deploy
that requires restarting `main.py` mid-session now needs to happen with
this in mind — the fix prevents the cap from resetting, but a restart
still costs a few seconds of the engine being down, and (before today's
fix) could silently blow through a real risk limit. Confirmed
`active_positions.json` was `{}` before every restart performed today.

---

## 2026-08-05 (afternoon session) — false-alarm circuit-breaker trip caused by test-log leakage; process-launch investigation

### 12:00:08 IST (and 11:01:31, 11:42:41, 11:43:59) — NOT REAL: "CIRCUIT BREAKER: Max Consecutive Losses Reached (10)" / "Max Daily Drawdown Reached" in fyersApi.log
**Symptom:** `fyersApi.log` showed repeated CRITICAL-looking circuit-breaker
trip warnings (consecutive losses = 10, daily drawdown = 3.00%/3.50%/5.24%,
weekly drawdown = 9.00%) at four different times today. `state.db`'s
`trades` table only had 5 rows since the 10:46 reset (net PnL +179.15,
no halt), and `trade_journal` was empty — the real engine never actually
breached any circuit breaker.

**Root cause:** `api_bridge.py` called `_setup_log_rotation()`
unconditionally at *module import time*, attaching a `RotatingFileHandler`
for `fyersApi.log` onto the **root logger**. Because Python logging
propagates to the root logger by default, this meant any process that
merely *imports* `api_bridge` — including 5 test files that use
`TestClient(app)` — silently redirected every logger call in that same
pytest process into the live production log for the rest of the run. The
four timestamps above line up exactly with `tests/test_risk_management.py`'s
own scenario values (3.5% DD test, 9% weekly DD test, 3-loss and 10-loss
consecutive-loss tests, three separate 3.0%-threshold tests) — this was
test output, not live trading activity. This is the same class of bug
already fixed once before for `trading_bot/main.py`'s `engine.log` handler
(2026-08-04) but the identical fix was never applied to `api_bridge.py`'s
own log-rotation setup.

**Fix:** moved `_setup_log_rotation()` out of module level and into
`api_bridge.py`'s `if __name__ == "__main__":` block (mirrors main.py's
existing pattern exactly), so only the actual live `python api_bridge.py`
process ever attaches the handler. Verified: ran the relevant test files
before and after — `fyersApi.log`'s line count and last line were
byte-identical across the run (previously they always grew and captured
new false-alarm content).

**Also added (defense in depth, `shared/singleton_lock.py`):** neither
`main.py` nor `api_bridge.py` had any guard against being started twice —
worth closing regardless of what triggered today's investigation. Both
entrypoints now refuse to start (fatal exit, clear message) if a live
process matching the same script is already running, verified against a
real live PID and a stale/reused-PID case. 5 new regression tests in
`tests/test_singleton_lock.py`.

**Investigated but revised conclusion — process-launch pattern:** initial
triage saw 2 `main.py` PIDs and 2 `api_bridge.py` PIDs running
concurrently (e.g. 23212+30404 from the 10:46 reset, 20288+30020 from a
12:09 restart) and suspected a genuine accidental double-launch /
competing-engine risk. Deeper check (parent PID + real CPU-time
accounting via `wmic`, cross-checked against `ps aux` from bash's own
process view) showed this is consistently one thin, 0%-CPU "stub" process
(the one bash's own `ps` considers its child) plus one real worker child
doing all the actual work — an artifact of how this venv's `python.exe`
gets launched through git-bash's pty layer on Windows, not two competing
trading engines. No evidence of duplicate trades or corrupted state from
either incident today supports the "real double-engine" reading. Confirmed
this pattern still occurs (harmlessly) after today's restart deploying the
above fixes. The singleton-lock guard is being kept anyway as legitimate
defense against a genuinely different failure mode (a human/script
actually invoking the start command twice from separate terminals), and
correctly does *not* reject the benign stub/child pattern (verified live).

### Investigated, not a real bug — "SignalAgent failed to load LSTM model: __no_such_model__.zip.zip" / "today is 2099-01-01" in fyersApi.log
Also a symptom of the same test-log-leakage bug fixed above, not a live
defect. `"__no_such_model__.zip"` and the 2099-01-01 date are literal
fixture values from `tests/test_signal_agent_lstm_state.py` (its
`SignalAgent(model_path="__no_such_model__.zip")` fixture and a mocked
`datetime(2099, 1, 1, ...)`). The `.zip.zip` doubling is stable_baselines3's
own internal retry-with-suffix-appended fallback when the given path
(already deliberately nonexistent, by test design) fails to load — not a
path-construction bug in this codebase. Confirmed the real live model path
(`trading-system/best_model.zip`, used by `MARLStrategy`) exists on disk,
and confirmed today's actual `active_strategy` is `ema_rsi`, not
`MARL_Ultra` — so this code path isn't even exercised live today. No code
change needed; already resolved by the log-rotation fix above.

### Investigated, inconclusive — 9x "SECURITY ALERT: broker_credentials.json integrity check FAILED" today (10:11-12:00 IST)
Checked whether this is a real tamper/corruption risk. `broker_credentials.json`
itself has been byte-identical (confirmed via mtime, unsigned/legacy
format, no `# MAC:` trailer) since **2026-08-01 17:55** — untouched all
day today. Since `_load_file()`'s MAC-mismatch branch can only fire when a
MAC trailer is actually present, and the file on disk has never had one
today, something must have been reading a transient in-memory or
partially-written state distinct from the file's resting content —
grepped every writer of this file (`brokers/credentials.py`,
`scripts/auth/{save_broker_creds,resign_creds}.py`, `token_cache.py`,
`disaster_recovery.py`) and found none that both run automatically today
and would produce this. Not chasing further right now: **paper mode never
reads broker credentials at all** (`Fyers: paper mode — skipping real
authentication`, confirmed live in today's logs), so this has zero effect
on the current validation window's correctness — but it should be
revisited before any live-mode Go decision, since a flaky integrity check
against real broker secrets is a legitimate concern for that phase.

**Deployed:** killed all 4 pre-fix processes at 13:05 IST (verified
`active_positions.json` was `{}` first — no open positions, zero-risk
restart window), restarted both with the fixes above. Confirmed clean
startup, single logical instance each, live WebSocket reconnected,
`engine.log`/`fyersApi.log` writing normally, session PnL resumed
correctly from persisted equity (179.15).

---

## 2026-08-05 — three real positions force-closed by a reconciliation bug; full state.db reset

Session picked up mid-flight: `shared/risk/manager.py`/`portfolio_risk.py`
(equity not persisted across restarts) and `main.py`'s option-premium
fetch throttle (self-inflicted rate-limiting leaving positions unmanaged)
had already been drafted and were sitting uncommitted from an interrupted
prior session. Verifying and deploying those fixes triggered a much
bigger, previously-untested code path — §2.6's broker-reconnect
reconciliation, holding a real position, for the first time this
validation window. It failed, three separate times.

### 10:22–10:25 IST — CRITICAL: broker-reconnect reconciliation force-closed 3 real positions using fabricated exit prices
**Symptom:** immediately after restarting the engine to deploy the
premium-throttle fix, the log showed `STATE MISMATCH: Local position
NSE:NIFTY50-INDEX exists but broker is flat` followed by `RECONCILIATION:
... falling back to the stop-loss price ... as an ESTIMATE`, closing the
real open `NSE:NIFTY2681123750CE` position (entered 10:05 IST) within
seconds of the restart. Two more real positions (`NSE:NIFTY2681124550CE`,
opened and closed within ~6 seconds of each other) were hit the same way
during a reconnect storm at 10:25 IST — before this was caught.

**Root cause (two independent bugs in `trading_bot/reconciliation.py` /
`main.py`'s `sync_broker_state()`):**
1. `FyersBroker.get_positions()` unconditionally returns `[]` in paper
   mode (no persistent broker-side state across restarts). Reconciliation
   treated that as "the broker confirms this position is closed" on
   *every* WebSocket (re)connect, including the very first connect after
   a fresh process start — meaning it would force-close any real open
   position on every single restart in paper mode, using the stop-loss
   price as a fabricated estimate.
2. Independently, `compute_reconciliation()` reconciled against the
   `active_positions` dict *key* instead of `local_pos.symbol`. Option
   strategies are deliberately keyed by the *underlying* (e.g.
   `NSE:NIFTY50-INDEX` — see the "We MUST key active_positions by the
   base symbol" comment at `main.py`'s entry sites), not the traded
   option itself (e.g. `NSE:NIFTY2681123750CE`). This means reconciliation
   has likely never correctly matched a single option position against
   the broker/order-book in this codebase's history — it was always
   checking whether the underlying index was flat, which is trivially
   always true (this system never holds the index itself).

**Fix:** `sync_broker_state()` now skips reconciliation entirely when
`broker.paper_mode` is true (there is no real broker account to reconcile
against — `active_positions.json` is already authoritative). Separately,
`compute_reconciliation()` now reconciles against `local_pos.symbol` (the
real traded instrument) for both the broker-position and order-book
lookups, and returns a new `local_key` field so the caller deletes the
right dict entry. Added 2 regression tests
(`test_option_position_keyed_by_underlying_reconciles_against_its_own_symbol`,
`..._resolves_and_reports_local_key`) covering the exact key/symbol split
that masked this for so long — every prior test happened to use the same
string for both.

**A second, related bug found while root-causing why reconciliation kept
re-firing:** the premium-throttle fix (see below) added a
`now_mono = time.monotonic()` call early in `on_tick()`. Two *pre-existing*
local `import time` statements deeper in that same function (added before
this session, now redundant since `main.py` already imports `time` at
module level) made `time` a function-scope-local name in Python — so the
new, earlier use crashed with `cannot access local variable 'time' where
it is not associated with a value` on almost every tick cycle.
`fyers_broker.py`'s `stream_quotes()` caught this exception and logged it
as "WebSocket disconnected or failed", reconnecting every ~2–5 minutes —
which is what repeatedly re-triggered the reconciliation bug above on
whatever position happened to be open at the time. Fixed by deleting both
redundant local imports (`main.py` lines that were at ~1148 and ~1520);
also removed an equivalent harmless-but-redundant local import in
`fyers_broker.py`'s `stream_quotes()` for consistency. Verified: engine
ran 90+ seconds post-fix with zero disconnects, versus a disconnect every
2–5 minutes before. (One `keepalive ping timeout` disconnect at 10:27/10:29
looks unrelated/transient — not chased further, watching for recurrence.)

**Damage this caused before the fix landed (all real, now baked into the
state.db reset below):**
- `NSE:NIFTY2681123750CE` (entered 898.40, 10:05 IST) force-closed at
  10:22:49 using the stop-loss price (894.36) as an estimate. True exit
  price is unrecoverable — the option's real premium wasn't being sampled
  during the window it was open, itself a symptom of the (separately
  fixed) rate-limit bug.
- Two `NSE:NIFTY2681124550CE` positions force-closed the same way at
  10:25 IST during the reconnect storm.
- Also discovered: 4 `NIFTY-RATELIMIT-TEST` rows in the `trades` table.
  Initially assumed leftover from the interrupted prior session — actually
  a long-standing documented hazard (first flagged 2026-08-03, see that
  date's entry below: "this will keep recurring every time the suite runs
  here") that I re-triggered myself: `tests/test_order_rate_limit.py`
  hits the real `/api/order/execute` endpoint with `record_trade()`
  unmocked, writing straight into the real `state.db` on every `pytest`
  run. Two more rows appeared mid-session from my own test-suite runs,
  re-polluting a reset I'd just done. Fixed properly this time — see the
  dedicated `fix(tests)` commit — by mocking `shared.state.record_trade`
  in both tests that reach it, instead of just re-flagging the hazard.
- My own mistake: live-verifying the reconciliation fix, I injected a
  synthetic position using a non-CE/PE-shaped symbol
  (`NSE:NIFTY-RECONCILE-FIX-VERIFY-TEST`) to confirm it would survive a
  restart. It did — but its symbol didn't match the option-detection
  check, so the exit logic compared the raw underlying LTP (24565.90)
  against my placeholder `target=120.00`, immediately "hit" it, and wrote
  a fabricated ₹15,90,283.50 profit into `state.db`.

**Resolution:** given the mix of real bug-driven closures, old test
pollution, and my own test artifact, reconstructing a trustworthy equity
number by hand wasn't possible — decided (with explicit user confirmation)
to do a full clean reset, same procedure as 2026-08-03's §0 baseline:
backed up `state.db` + `config/active_positions.json` to
`trading-system/backups/backup_20260805_104525/`, stopped both engine
processes, cleared `trades` to 0 rows (reset `sqlite_sequence`), reset
`state` to equity=100000.0/pnl=0.0, cleared `active_positions.json` to
`{}`, and restarted both processes clean. Verified post-restart: `trades`
= 0, `state` = (100000.0, 0.0), reconciliation correctly skipped with no
position to falsely close, WebSocket stable with no disconnects.

**Validation clock:** per the checklist's own rule, this resets the clock
again — **2026-08-05 (this restart) is the new earliest possible session
1.** Nothing before this counts toward §2's 10-session/30-trade window.
§2.6 (reconciliation while holding a position) is arguably now "tested" in
the sense that it was exercised and found broken and fixed — but should
be watched closely across the next several sessions before being marked
passing, per the same standard applied to every other fix this window.

### (carried over from before this session — found & fixed, not yet verified live at the time) Equity/peak-equity discarded on every restart
`RiskManager`/`PortfolioRiskEngine` only ever restored `daily_pnl` from
`state.db` on restart — `current_equity`/`peak_equity` (and
`peak_capital_daily`/`peak_capital_weekly`) silently reset to the static
`initial_capital` every time, discarding real cumulative P&L and drawdown
headroom across any restart. Fixed by threading the persisted equity
(`state.db`'s `equity` column, already written by `update_equity()`)
through to both engines' constructors via new optional
`current_equity`/`current_capital` params, defaulting to the old
behavior when omitted. 4 new regression tests
(`test_current_equity_restores_across_a_restart`,
`test_current_equity_omitted_defaults_to_initial_capital`,
`test_current_capital_restores_peak_across_a_restart`,
`test_current_capital_omitted_defaults_to_initial_capital`). Verified
live across all three restarts this session — equity/pnl correctly
carried forward each time (until the deliberate reset above).

### (carried over from before this session) Option premium fetch self-rate-limited every tick, leaving a position unmanaged
Exit-check logic fetched the option's live premium unconditionally on
**every** tick — ticks arrive far faster than Fyers' real rate limit
(~100/min per `DATA_LIMITER`'s own comment, never actually wired to
anything). Live result: a position sat completely unmanaged for most of a
session because every fetch attempt came back empty, almost certainly
from self-inflicted rate limiting (`Exit check skipped for ... — could
not fetch live option premium this tick`, repeating every tick). Fixed by
throttling to at most one real fetch per second per symbol, reusing the
last known premium (or a recent-enough stale one on a failed fetch) in
between — SL/target checks still effectively run every tick, just against
a premium that's at most ~1s old.

---

### 23:24 IST — Session close: full report compiled
Market closed 15:30 IST; engine ran continuously 10:31–23:35 without
further restart (13+ hrs, stable). Full day's evidence (first live
exit-path validation, the PyramidSizer fix, quantity/PnL reconciliation,
checklist §2 status) written up in
`docs/paper_trading_validation/reports/2026-08-04.md`. See that report
for the complete picture — this log has the chronological blow-by-blow.

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
