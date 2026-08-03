# Paper-Trading Validation — Anomaly & Fix Log

Running log of every anomaly, warning, and fix found during the continuous
paper-trading validation window (see `docs/GO_NO_GO_CHECKLIST.md` §2/§3).
Newest entries at the top. All timestamps IST unless noted.

---

## 2026-08-03

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
