# Deep Strategy Audit — 2026-08-07

**Type:** Analysis only. No code, logic, or parameters were changed while producing
this document. Every finding below is a candidate for a future, separately-approved
fix pass, prioritized by risk level.

**Method:** Full read-through of every strategy module in `trading_bot/strategies/`
(active, inactive, experimental, legacy, AI/ML/RL, institutional, premium, momentum),
plus the shared cross-cutting infrastructure every strategy ultimately depends on
(exit engine, risk manager, pyramid sizer, state persistence, indicators, AI feature
pipeline, market-hours gates) and the backtest engine. Conducted as one direct
first-principles audit of the shared infrastructure and the backtest engine, plus
four parallel deep-dive audits of the strategy implementations themselves (live path,
`institutional_momentum` package, `premium_selection` signal engine, and the
experimental/legacy AI-ML strategy sweep), each independently cross-checking its
assigned files line by line against the full checklist below and against everything
already found elsewhere. Cross-fork claims were independently re-verified before
inclusion (see §0.1).

**Checklist applied to every module:** entry logic/signal generation; exit logic
integration (SL/trailing/EOD/partial/pyramiding); indicator correctness; data flow
and feature generation; look-ahead bias/repainting/future-data leakage; live vs.
backtest consistency; paper vs. live consistency; multi-timeframe sync; AI/confidence
filter integration; option-buying compatibility; risk-manager integration;
position-sizing compatibility; performance (CPU/memory/repeated DataFrame ops);
thread-safety/async correctness; configuration validation; dead/duplicate code; edge
cases (NaN, empty data, stale/duplicate ticks, missing candles, API failures);
exception handling; maintainability/architecture quality.

**Today's live configuration, for context:** `active_strategy = "ema_rsi"`,
`symbols = ["NSE:NIFTY50-INDEX"]` (NIFTY-only). `institutional_momentum` is the
code-level fallback default but is NOT what's actually running. Every other
strategy audited here is reachable only via a settings change.

---

## 0. Executive summary

**23 findings** across 4 Critical, 10 High, and 9 Medium/Low, spanning shared
infrastructure, the backtest engine, and every strategy module in the repository.
The single most urgent fact from this audit: **the strategy running live right now
(`ema_rsi`) contains an unfixed instance of the exact bug class that caused the
2026-08-06 CPU livelock, sitting upstream of the fix already deployed today** (§1.2).

### 0.1 Cross-fork verification note
`meta_agent_strategy.py`'s dependency on a sub-agent named `"institutional_momentum"`
was flagged by one audit as an unconfirmed possible mismatch. Independently verified
against `momentum_strategy/__init__.py:29` (`STRATEGY_NAME = "institutional_momentum"`)
— **the names match**; this is not a bug. Downgraded to "verified correct" (§5).

### 0.2 Findings by severity

| Severity | Count | Live-path exposure today |
|---|---|---|
| Critical | 4 | 2 (live path); 2 (dormant, one-settings-change away) |
| High | 10 | 4 (live path or shared/always-active); 6 (dormant) |
| Medium | 9 | mixed |
| Low | 6 (folded into sections below) | mostly dormant/documentation |

### 0.3 The five findings to act on first (cross-referenced to full detail below)

1. **§1.2 — `ema_rsi_strategy.py` reproduces the 2026-08-06 livelock's exact
   `Series.__setitem__` pattern**, upstream of today's `registry.py` fix, in the
   strategy that is live right now. Very plausibly explains today's own
   "not conclusively ruled out" post-restart CPU transients.
2. **§2.1 — The ATR fed into every option position's trailing stop is computed from
   the underlying index's own candle range (index points), not the option's own
   premium.** This silently neuters (or erratically over-tightens) the ATR-trailing
   component of `SmartExitEngine` for every single option position in the system,
   live or paper, regardless of which strategy opened it. Independently confirmed to
   recur in `momentum_strategy`'s own exit manager (§3.4) — two separate
   implementations, same root defect.
3. **§2.2 — The general-purpose backtest engine (`run_intraday_backtest`, used by
   `/api/backtest`, `grid_search.py`, `audit_script.py`) still simulates a fixed-%
   stop-loss and a fixed profit target.** Every backtest run since the premium-banded,
   no-fixed-target architecture shipped 2026-08-06 has been validating a strategy that
   is not the one actually running live.
4. **§1.1 — No abort path if `select_option()` throws.** `ema_rsi`'s auto-map-to-option
   entry path falls through to placing an order using the *raw underlying index
   symbol* if strike/expiry selection fails for any reason — a direct, if currently
   unexercised, violation of the option-buying-only mandate.
5. **§4.1-4.3 — Two experimental strategies (`advanced_ai_ml_strategy.py`,
   `buy_the_dip_strategy.py`) independently reintroduce the same DataFrame-mutation
   livelock pattern**, and a third (`drl_strategy.py`) has a permanently-constant
   model input — it cannot see the market at all. None of these are live today, but
   all three are one `active_strategy` typo-free settings edit away from being live,
   with **zero validation anywhere that the configured strategy name is real** (§4.7).

---

## 1. Live path — `ema_rsi` strategy, `registry.py`, option auto-mapping

*(This is what is actually running in production today.)*

### 1.1 CRITICAL — No gate if `select_option()` fails; entry path can fall through to the raw index symbol

- **File(s):** `trading_bot/main.py:1347` (`entry_symbol = s`), `1360-1378`
  (auto-map try/except with no abort), `1463`, `1540`, `1695-1706`
- **Root cause:** `entry_symbol` defaults to the raw underlying index symbol before
  `select_option()` is attempted, and is only overwritten on success. The call is
  wrapped in `try/except Exception as e: logger.error(...)` with no `continue` and no
  flag marking the failure. Execution falls through into the rest of the entry
  pipeline with `entry_symbol` still equal to the index symbol.
- **Technical explanation:** Every later option-vs-not branch point
  (`is_option_trade = "CE" in entry_symbol or "PE" in entry_symbol`) only *switches
  behavior*, never *aborts*. If `select_option()` fails, the index's own LTP gets
  fetched as `entry_premium`, fed into `resolve_initial_stop()` (interpreting an index
  price of ~₹26,900 as an option premium and applying the `>₹250` dynamic 10-12%
  band to it), and a `MARKET` order gets placed directly on the index symbol.
- **Live trading impact:** In paper mode this likely "succeeds" silently, polluting
  `state.db`/journal with a nonsensical trade and corrupting downstream P&L. In live
  mode, behavior is unpredictable — a real broker would probably reject buying an
  index directly, but the retry/error-handling path for that rejection is unverified.
  This is exactly the failure class the whole option-buying architecture exists to
  prevent, currently backstopped only by "hope `select_option()` never throws."
- **Risk level:** Critical
- **Reproducibility:** Conditional — requires `select_option()` to raise. No currently
  known live trigger under today's normal conditions, but the exception handler's
  existence proves the original author anticipated failure was possible.
- **Recommended professional fix:** Track success explicitly (`option_mapped = False`
  until the call succeeds) and `continue` the tick loop if mapping failed, rather than
  falling through.
- **Required regression tests:** Mock `select_option` to raise and assert (a) no order
  is placed, (b) `entry_symbol` never reaches `resolve_initial_stop`/order placement
  still equal to the raw index symbol, (c) the existing successful-mapping path is
  unaffected.

### 1.2 CRITICAL — `ema_rsi_strategy.py` reproduces the 2026-08-06 livelock's exact signature, upstream of today's fix

- **File:** `trading_bot/strategies/ema_rsi_strategy.py:109-111`
  ```python
  signals = pd.Series(0, index=df.index, dtype=int)
  signals[bullish] = 1
  signals[bearish] = -1
  ```
- **Root cause:** Identical pattern to what was found and fixed *today* in
  `registry.py` (`Series.__setitem__` via a boolean mask, routing through
  `_set_with_engine -> Index.get_loc -> Series.__repr__` — the exact call chain seen
  live in the 2026-08-06 CPU-livelock's own `py-spy` dumps). This file was untouched
  by either of today's two fixes. `generate_signals()` is called from
  `registry.run_strategy` (`registry.py:34`) *before* the already-fixed line runs —
  meaning this is the **first** instance of the pattern to execute on every single
  live tick evaluation of the strategy actually running today.
- **Technical explanation:** Per this session's own incident writeup, this class of
  cost is cumulative across many repeated calls within a long-running process, not
  reproducible in a short/fresh benchmark — exactly the conditions under which both
  the 2026-08-06 livelock and today's own unexplained CPU transients occurred.
- **Live trading impact:** Very plausibly a live, ongoing contributor to today's own
  "not conclusively ruled out" 44-47% post-restart CPU transients (documented in
  `anomaly_log.md`'s 2026-08-07 entries) — since `ema_rsi` is the strategy generating
  those exact ticks. Left unfixed, this is a real risk of reproducing the full
  livelock (97-100% CPU, zero forward progress) under sustained live load.
- **Risk level:** Critical — same class of bug as a CONFIRMED production incident, in
  the strategy live today, unpatched.
- **Reproducibility:** Conditional on sustained high-frequency live operation (hours),
  matching the exact conditions that have already caused a full livelock three times
  this validation window.
- **Recommended professional fix:** Same fix pattern as today's `registry.py` change —
  replace with a single `np.select` construction.
- **Required regression tests:** Bit-identical comparison against current behavior
  (no-overlap, all-False, forced-overlap cases), mirroring
  `test_registry_filtered_signals_regression.py`.

### 1.3 HIGH — Dashboard RSI/VWAP controls are completely disconnected from the live strategy

- **File(s):** `frontend/app/strategy/page.tsx` (~608-648),
  `trading_bot/strategies/ema_rsi_strategy.py:46-53`
- **Root cause (three compounding gaps):**
  1. Key-name mismatch: dashboard writes `settings.rsi_sell`/`rsi_buy`;
     `generate_signals()` only reads `rsi_buy_thresh`/`rsi_sell_thresh`. Absorbed
     silently into `**kwargs` and discarded.
  2. Semantic mismatch even if names matched: dashboard labels ("Overbought
     70"/"Oversold 30") describe mean-reversion RSI; the code implements
     momentum-confirmation RSI (buy when RSI **>55**, sell when RSI **<45**) — a
     different strategy, not just different numbers.
  3. `"Enable RSI Filter"`/`"Enable VWAP Filter"` toggles exist in the UI but
     `generate_signals()` has no code path reading either key — RSI is unconditional
     regardless of the toggle, and there is no VWAP logic anywhere in this file at all.
  4. `config/settings.json` currently has none of these keys set — the live strategy
     runs entirely on hardcoded Python defaults regardless of any dashboard state.
- **Live trading impact:** An operator adjusting these controls would reasonably
  believe they changed live behavior. None of it has any effect — a real risk of a
  trader believing entry criteria were tightened/loosened when they weren't.
- **Risk level:** High
- **Reproducibility:** Always — static wiring gap, not conditional.
- **Recommended professional fix:** Either wire the settings through with agreed
  semantics, or visibly disable these controls when `ema_rsi` is active, plus a
  settings-validation warning log for unconsumed strategy-parameter keys.
- **Required regression tests:** Settings round-trip test proving threshold changes
  actually change `generate_signals()`'s output; config-validation test flagging
  unconsumed keys.

### 1.4 HIGH — `options_selector.py`'s expiry/0DTE-guard logic is not IST-anchored

- **File:** `trading_bot/strategies/premium_selection/options_selector.py:188`
  (`date.today()`), `312` (`datetime.now()`)
- **Root cause:** Naive local-system time, unlike `shared/market_hours.py` and
  `shared/risk/manager.py`, which both deliberately anchor to
  `pytz.timezone("Asia/Kolkata")` specifically because this codebase has already been
  bitten by this exact class of bug twice.
- **Technical explanation:** On a non-IST-clocked host (a realistic future deployment
  risk this codebase's own comments already anticipate), expiry-date selection could
  land on the wrong calendar day during the first 5.5 hours of each IST trading day,
  and the 0DTE "after 2 PM, shift deep ITM" Greeks Guard — a safety mechanism against
  catastrophic theta decay on expiry-day afternoons — would trigger at the wrong real
  clock time, silently never firing during actual 0DTE trading hours.
- **Live trading impact:** Currently latent (today's host is IST-aligned); would
  silently stop protecting expiry-day theta risk on the next infrastructure change
  (containerization, cloud migration, VM default timezone).
- **Risk level:** High (safety-critical logic, proven-fragile pattern class in this
  exact codebase, masked only by host configuration).
- **Reproducibility:** Always on a non-IST host; dormant today.
- **Recommended professional fix:** Accept an optional `now: datetime` parameter
  defaulting to `datetime.now(IST)`, mirroring `is_market_open()`'s established
  signature.
- **Required regression tests:** Simulate a UTC-clocked call spanning the IST/UTC
  offset boundary, assert IST-correct behavior regardless of host timezone (mirrors
  `test_market_hours.py`'s existing non-IST-timezone test).

### 1.5 MEDIUM — Diagnostic Greeks computed from a hardcoded 15% vol assumption

- **File:** `premium_selection/options_selector.py:28-41`
- Real index-option IV, especially on 0DTE/expiry days, routinely deviates far from
  15%. Doesn't change trading behavior directly (nothing sizes/blocks off these
  numbers today), but the 0DTE Guard's own effectiveness self-check
  (`if abs(delta) < 0.7: warn`) could itself give a false pass/fail, undermining
  confidence in a safety mechanism exactly when it matters most. **Recommended fix:**
  wire in real IV if available, or clearly label these log lines as approximate.

### 1.6 MEDIUM — `compute_features()` masks RSI's warmup NaN gap but not EMA's identical one

- **File:** `shared/ai/features.py:91-113`; compounded by `shared/indicators/ema.py`'s
  docstring incorrectly claiming NaN padding that `ewm()` doesn't actually produce
  (see §2.5). RSI warmup rows are explicitly masked (`rsi_14.iloc[:14] = np.nan`);
  EMA-derived columns (`ema_fast_slow_diff`, `price_vs_ema9/21`) get no equivalent
  treatment despite the identical still-converging-warmup property. Live inference
  uses `compute_features(df.tail(100)).tail(1)` — a truncated window recomputed every
  call — raising a real, if likely small given fast EMA spans, train/serve-skew risk
  if the training pipeline computes features over full continuous history instead.
  **Recommended fix:** apply the same masking pattern to EMA columns; verify training
  pipeline parity.

### 1.7 MEDIUM — Duplicate/divergent ADX; four exported indicator functions are dead code

- **Files:** `shared/indicators/adx.py`, `macd.py`, `smc.py`, `option_chain.py`
  (all zero live call sites) vs. `shared/ai/features.py`'s own separate, simplified
  `_adx()` (plain rolling mean, not Wilder-smoothed) which **is** live. Two
  implementations of the same indicator produce different numbers for identical
  input. `smc.py` and `option_chain.py`, if ever revived unmodified, would
  immediately reintroduce the incremental-`Series.__setitem__` pattern already fixed
  three times elsewhere — dormant landmines of the same bug class. **Recommended
  fix:** consolidate on one ADX implementation; rewrite `smc.py`/`option_chain.py`
  with the dict-of-Series pattern before ever wiring them up, or remove them.

### 1.8 LOW-MEDIUM — Volume filter is silently inert for every live-traded instrument

- **File:** `ema_rsi_strategy.py:31-43`. `_volume_filter` bypasses to always-pass
  whenever `df["volume"].nunique() <= 1` — true for essentially every index feed this
  system actually trades (NIFTY/BANKNIFTY/SENSEX/FINNIFTY). Deliberate and reasonable
  as a fallback, but silent — no log line surfaces that the filter is inert.
  **Recommended fix:** log once per session when the bypass activates.

### 1.9 LOW — Supertrend period/multiplier hardcoded, ignoring any dashboard control

- `ema_rsi_strategy.py:103`: `supertrend(df, period=10, multiplier=3.0)` — no
  parameter, so any UI control for this would be silently inert, same class as §1.3
  at smaller scale.

### 1.10 Verified correct (live path)
`shared/indicators/atr.py`/`ema.py` (math)/`rsi.py`/`adx.py`/`macd.py`: mathematically
correct and causal. `shared/filters/institutional.py`'s four filters: filter
*direction* correct in every case, no inversion found (performance cost already
documented, not re-flagged). `options_selector.py`'s ATM/ITM clamp, symbol-building,
and dynamic lot-size caching: correct. `shared/ai/model.py`'s atomic persistence,
hot-reload, and accuracy-gated deployment: sound, institutional-grade. `registry.py`'s
post-fix institutional-filter consumption: independently re-verified correct.

---

## 2. Shared infrastructure (affects every strategy, live or dormant)

### 2.1 CRITICAL — ATR fed into option trailing stops is index-scale, not premium-scale

- **File(s):** `trading_bot/main.py:976-984` (ATR computed from
  `aggregator.get_latest_dataframe(sym)`, where `sym` is the **underlying index**
  symbol — the live feed never subscribes to option contracts directly), `1087-1088`
  (passed into `exit_engine.evaluate_exit`); `shared/exits/exit_engine.py:202-221`
  (consumes it against `position.highest_price`, which for an option position is the
  **premium**).
- **Root cause:** `current_atr` is computed from `(df["high"] - df["low"]).abs()`
  rolled over 14 bars of the **index's own** candles — typically 100-375+ NIFTY
  points from real data today — then subtracted directly from an option premium
  (₹15-2400 scale in real trades seen today) with no unit conversion anywhere in the
  call chain.
- **Technical explanation, worked example:** For a ₹100-150 premium option (common in
  today's real trades) with index ATR ~100-375 pts and `atr_multiplier=1.5`, the
  computed `trailing_stop = highest_price - (150 to 560+)` is deeply negative —
  always below the real (positive) banded SL, so the `if trailing_stop >
  position.stop_loss` condition is essentially never true: **the ATR-trailing
  component never tightens the stop for lower-premium options at all.** For the
  ₹2415.20 premium trade seen in today's real logs (delta ≈0.53), the same
  index-point distance is comparable in absolute rupee terms to the premium's own
  scale, so this component can instead yank the SL aggressively based on unrelated
  index chop — potentially triggering "Trailing Stop-Loss Hit" on a premium pullback
  that isn't a real reversal. The mechanism's actual behavior varies essentially
  randomly with option delta/premium rather than being calibrated to the position it
  protects.
- **Live trading impact:** Directly undermines the explicit 2026-08-07 mandate that
  "the entire profit management must remain fully controlled by the existing Trailing
  Stop Loss and Smart Exit Engine" — one of its two trailing mechanisms is either
  inert or erratic for essentially every option position, live or paper. The
  percentage-based trailing-offset mechanism (step 5b in `exit_engine.py`, unit-agnostic by
  design) is the only trailing-stop layer actually functioning as intended for options
  today. **Independently confirmed to recur** in `momentum_strategy`'s own separate
  exit manager (§3.4) — this is not a one-off, it's a systemic unit-conflation issue
  wherever `current_atr` crosses from index-scale computation into premium-scale
  consumption.
- **Risk level:** Critical
- **Reproducibility:** Always, for every open option position, to a degree that
  varies with the option's delta/premium relative to the index's own ATR.
- **Recommended professional fix:** Compute a premium-scale ATR from the option's own
  recent price history when available, or use a percentage-of-premium proxy as the
  primary method (the existing `exit_check_price * 0.005` fallback in `main.py` is
  already unit-correct and could be promoted from a rare fallback to the standard
  approach for options) — never pass raw index-point ATR into premium-scale
  trailing-stop math.
- **Required regression tests:** A test constructing low-premium (~₹100) and
  high-premium (~₹2400) positions with identical *relative* peak-to-trough
  retracement, asserting the ATR-trailing component behaves consistently for both (it
  currently would not).

### 2.2 CRITICAL — Backtest engine models a completely different SL/target architecture than what's live

- **File:** `backtesting_engine/run.py` (`run_intraday_backtest`, lines 58-652), used
  by `grid_search.py`, `WalkForwardValidator`, `/api/backtest`, `audit_script.py`.
- **Root cause:** The live system shipped a premium-banded, no-fixed-target SL
  architecture on 2026-08-06 (`shared/risk/option_stop_loss.py` — profit management
  entirely via trailing stop, explicitly no fixed profit target). The general-purpose
  backtest engine was never updated to match: it still uses a flat `stoploss_pct`
  (`pnl_pct <= -current_sl_pct`) and, more seriously, **still simulates a fixed
  profit target** (`target_pct`/`vol_target_pct`, `target_hit = pnl_pct >=
  base_target`) — a direct architectural contradiction of the explicit "do not
  implement any fixed Target Profit" mandate this session shipped live.
- **Technical explanation:** Any backtest run through this engine since 2026-08-06
  systematically understates real upside (winners get artificially capped at
  `target_pct` instead of running via trailing stop as they would live) and shows a
  fundamentally different trade/exit-reason distribution than live trading actually
  produces. This is why `scripts/validate_option_stop_loss.py` had to be built as a
  separate, purpose-built harness for the new architecture — the general-purpose
  engine cannot validate it at all.
- **Live trading impact:** Any `/api/backtest` result, `grid_search.py` optimization,
  or `audit_script.py` run since 2026-08-06 is evaluating a strategy that is not the
  one actually live. Optimization work done against this engine (e.g., parameter
  tuning via `grid_search.py`) would be tuning for the wrong exit model entirely.
- **Additional consistency gaps found in the same engine, same root cause (engine
  never updated to track the live architecture's evolution):**
  - Consecutive-loss handling philosophically diverges from live: backtest reduces
    position size and keeps trading (¼ size at 5+ losses, ½ at 3+); live
    `RiskManager` hard-halts entirely via `can_trade()` rejection at
    `max_consecutive_losses`. A backtest "surviving" a losing streak by sizing down is
    not evidence live trading would survive it — live would have stopped trading
    entirely.
  - "Stop-Hunt Re-Entry" (automatic re-entry within 5 bars of a stop-out if price
    reverses favorably) and "Dynamic Capital Compounding" (position size scaling up
    to 5x as backtest capital grows) are backtest-only mechanics with no confirmed
    live equivalent — backtest results may not be achievable/replicable live.
  - The Supertrend-based "smart stop loss" (`st_direction`) is explicitly
    self-documented as approximating *only* `momentum_strategy`'s Phase 3 trailing
    rule, not its partial-booking/breakeven/exhaustion-lock/AI-confidence-exit
    behavior — backtests of that strategy are acknowledged-incomplete by the code's
    own comments.
  - The CLI's `argparse` `--help` description (`backtesting_engine/run.py:659`) still
    reads "Backtest EMA+RSI strategy" even though the module's own top docstring
    documents that this exact staleness was already fixed once (for a *different*
    stale reference in the same file) — this second instance was missed. The CLI
    actually defaults to `marl_strategy.generate_signals`.
- **Risk level:** Critical
- **Reproducibility:** Always — structural, not conditional.
- **Recommended professional fix:** Update `run_intraday_backtest` to accept and
  correctly model the premium-banded/no-fixed-target architecture (at minimum as an
  opt-in mode), and update all four callers' documentation to state clearly which
  architecture their results reflect. Fix the residual stale CLI description
  separately (trivial).
- **Required regression tests:** A backtest run on the new architecture's own known
  parameters, cross-checked against `scripts/validate_option_stop_loss.py`'s
  already-built harness for numerical agreement.

### 2.3 HIGH — Partial-booking's reward:risk ratio is computed against a possibly-already-trailed stop, not a fixed initial-risk reference

- **File:** `shared/exits/exit_engine.py:173-193`
- **Root cause:** `risk = abs(position.entry_price - position.stop_loss)` is
  recomputed fresh every tick from whatever `position.stop_loss` currently is. Step 4
  (partial booking) runs *before* step 5 (trailing-stop update) within a tick, but
  across ticks, if trailing already moved the stop up on a prior tick, "risk" shrinks
  accordingly.
- **Technical explanation:** `trailing_activation_pct` (default as low as 0.5% per a
  settings override seen in `main.py`) is a much lower bar than reaching a full 1:1
  reward-to-*initial*-risk ratio, especially given the banded SL architecture's
  typical 10-15% risk. It's entirely plausible for the ATR/offset trailing stop to
  activate and move `stop_loss` up *before* the partial-booking reward ratio would
  naturally reach 1:1 against the *original* risk — at which point "risk" in the
  partial-booking formula recomputes against the new, smaller distance, making the
  1:1 threshold progressively easier to satisfy than "book at 1R" would normally mean.
- **Live trading impact:** Partial profit booking (`partial_target_reward: float =
  1.0`) can fire meaningfully earlier than an operator reading "1R" would expect,
  once trailing has already engaged — a real behavioral surprise, not a crash or
  P&L-losing bug, but a gap between documented intent and actual trigger timing.
- **Risk level:** High
- **Reproducibility:** Conditional — requires trailing to activate before the 1:1
  ratio is naturally reached, which is plausible but not guaranteed for every trade
  given today's SL bands.
- **Recommended professional fix:** Capture `initial_risk` once at entry time (a new
  `Position` field) and use that fixed reference for the partial-booking ratio
  calculation for the life of the position, rather than recomputing against a moving
  stop.
- **Required regression tests:** A test opening a position, letting trailing move the
  stop up, then confirming partial-booking's reward ratio is still measured against
  the *original* risk distance, not the post-trail one.

### 2.4 HIGH — Latent TOCTOU race in risk-gate evaluation across concurrently-evaluated symbols

- **File(s):** `shared/risk/manager.py` (`can_trade`/`record_trade`, no locking),
  `trading_bot/main.py`'s entry loop (`_evaluating_symbols` is a **per-symbol** lock,
  not global; multiple `await asyncio.to_thread(...)` points — AI-confidence predict,
  premium-engine evaluate — sit between signal generation and the final
  `can_trade()`/`record_trade()` calls).
- **Root cause:** asyncio is cooperative-single-threaded, so no bug is exercisable
  *within* a single symbol's evaluation. But if two *different* symbols' entry
  evaluations are concurrently in-flight (interleaved at an `await` point), both can
  read the same `current_equity`/`trades_today` snapshot and both pass the same risk
  gate before either has recorded its trade — potentially exceeding the intended
  aggregate per-trade-risk or daily-trade-cap across symbols in combination.
- **Live trading impact:** Not exercisable today — `symbols` is NIFTY-only, so there
  is only ever one symbol's entry evaluation in flight. **This is a real, latent risk
  specifically for the multi-instrument re-enablement decision that remains explicitly
  open from 2026-08-06** — re-enabling BANKNIFTY/SENSEX/FINNIFTY concurrently would
  make this race exercisable for the first time.
- **Risk level:** High (scoped to the pending multi-instrument decision; zero exposure
  under today's single-instrument config)
- **Reproducibility:** Conditional — requires ≥2 concurrently-watched symbols with
  overlapping entry evaluation windows.
- **Recommended professional fix:** A global (not per-symbol) lock around the
  risk-check-through-record-trade critical section, or serialize entry evaluation
  across symbols entirely for the risk-gate portion.
- **Required regression tests:** A concurrency test with two simulated symbols racing
  through entry evaluation, asserting the aggregate risk taken never exceeds the
  configured per-trade cap even when both evaluations overlap.

### 2.5 LOW — Documentation defects across shared infra (grouped)
- `shared/indicators/ema.py`'s docstring claims `ewm(adjust=False)` produces NaN for
  the first `window-1` entries — **factually wrong**; `ewm()` does not pad with NaN
  the way `.rolling()` does. Could mislead a future developer debugging warmup
  behavior (this exact confusion is the likely root cause of §1.6).
- `shared/risk/option_stop_loss.py`'s malformed-`option_sl_bands`-config fallback is
  silently swallowed with no operator-visible warning logged at the `main.py` call
  site — safe by design (never blocks trading on a config typo) but invisible if it
  ever actually happens.
- `shared/state.py::record_trade()`'s docstring says "flush to disk immediately" but
  the implementation enqueues for a background thread (practically near-instant given
  the 0.05s poll interval, but not literally synchronous as documented).
- `shared/exits/exit_engine.py` checks the EOD time cutoff *before* the hard
  stop-loss check — a position simultaneously past both gets logged as "Time-based
  EOD Exit" rather than "Stop-Loss Hit." Reporting/journal-accuracy nuance only, exit
  price is identical either way — not a P&L bug.

### 2.6 Verified correct (shared infrastructure)
`shared/risk/option_stop_loss.py`'s band interpolation, dynamic taper, and premium
floor clamp: correct, well-designed, pure function, no bugs found beyond the §2.5
silent-fallback note. `shared/exits/pyramid_sizer.py`: correct, unit-agnostic
(percentage-based), no ATR-mismatch exposure. `shared/state.py`: correctly
thread-safe within a process (lock-protected cache, queue-based background flush);
the two separate "record trade" paths (`state.py` for journal/dashboard,
`RiskManager` for risk gating) are correctly paired at every exit call site in
`main.py` — confirmed by direct grep of all call sites, matching the codebase's own
existing verification comment at `main.py:2117-2135`. `shared/risk/manager.py`'s
daily-loss/drawdown/consecutive-loss gates, Kelly-sizing zero-division guards, and
`_reset_daily_if_needed()` IST day-rollover: all correct.

---

## 3. `institutional_momentum` package (`trading_bot/strategies/momentum_strategy/`)

*(Code-level fallback default; not today's live strategy, but switchable via one
settings change.)*

### 3.1 CRITICAL — Roughly half the package's advertised architecture is structurally unreachable dead code

- **Files:** `momentum_strategy/__init__.py` (entry point actually used, L37-171),
  vs. `environment_filter.py`, `signal_engine.py`'s class-based
  `MomentumSignalEngine`, `itm_selector.py`, `execution_sizer.py`, `trade_scorer.py`,
  `mtm_trailing.py` (all effectively dead).
- **Root cause:** `main.py`'s entry-signal path for `active_strategy ==
  "institutional_momentum"` dispatches to the **module-level** `generate_signals()`
  function via `registry.run_strategy()` — a separate, simpler, independently
  written signal generator. It does **not** call `MomentumStrategy.check_signals()`,
  the method the package's own docstring describes as its live-trading entry point.
  Exhaustively grepped every symbol in this cluster across the whole repo:
  `MomentumStrategy.check_signals()` has zero callers anywhere; `ITMOptionSelector`,
  `MarketEnvironmentFilter` (including `is_eod_squareoff()`, doubly orphaned — not
  even called by its own sibling method `.check()`), the class-based
  `MomentumSignalEngine.generate()`, `ExecutionSizer` (all four of
  `calculate_lots`/`can_trade`/`record_trade`/`reset_daily`), and
  `TradeQualityScorer.score()` are all reachable only from within
  `check_signals()` — i.e., not reachable at all.
- **Technical explanation:** Most consequentially, `ExecutionSizer`'s kill-switch —
  max 4 trades/day, a -2% circuit breaker, a consecutive-SL halt, and a 30-minute
  anti-whipsaw cooldown — **never executes under any circumstances**, and
  `MTMTrailingEngine` (the day-level profit-floor ratchet with forced liquidation) is
  instantiated but never invoked from `main.py` under any `active_strategy` value at
  all.
- **Live trading impact:** If switched live, an operator who read this package's own
  docstrings would reasonably expect VIX-gated entries, multi-timeframe confluence,
  ML-style trade scoring, a dedicated ATM selector, a kill-switch, and a day-level
  profit ratchet. **None of it runs.** What actually runs is the standalone
  `generate_signals()` for entries and `TieredExitManager` for exits — materially
  less rigorous than the architecture the code documents. A circuit breaker that
  looks fully implemented and unit-testable but is silently never invoked is worse
  than no circuit breaker at all — it invites false confidence in a design review.
- **Risk level:** Critical (architecture/capital-risk gap the instant this is
  switched on; zero live impact today only because it's dormant)
- **Reproducibility:** Always — structural, not data-dependent.
- **Recommended professional fix:** Either wire `main.py`'s entry path to actually
  call `MomentumStrategy.check_signals()` when this strategy is active (retiring the
  module-level duplicate), or explicitly retire/relabel the entire dead cluster as
  "reference/backtest-only, not wired to live" so the codebase stops asserting
  capabilities it doesn't have. Needs an explicit decision, not a silent continuation.
- **Required regression tests:** An integration test activating this strategy and
  asserting, end-to-end, exactly which functions get called during one simulated
  entry+exit tick cycle — would immediately catch this class of drift if it recurs.

### 3.2 HIGH — `generate_signals()` (the function actually live-reachable) mutates the caller's persistent DataFrame — same anti-pattern as the 2026-08-06 livelock

- **File:** `momentum_strategy/__init__.py:228, 555, 579`
  (`df['st_direction'] = ...`, `df['custom_sl_pct'] = ...`, both writing directly onto
  the caller's DataFrame, not a local copy).
- Same mechanism, same risk class as §1.2 — this file was not touched by any of
  today's fixes either. **Recommended fix:** build outputs as local Series/arrays,
  return them as part of the existing `(signals, rejection_logs)` tuple rather than
  mutating the caller's object. **Required tests:** mutation-safety + bit-identical
  reference comparison, mirroring the existing pattern in this codebase.

### 3.3 HIGH — `TieredExitManager` has no EOD/time-based exit at all

- **Files:** `momentum_strategy/exit_manager.py` (`evaluate()`, no time parameter or
  check anywhere), `environment_filter.py`'s `is_eod_squareoff()` (dead per §3.1).
- **Root cause:** Positions under this strategy are exit-managed exclusively through
  `TieredExitManager`, which entirely bypasses `shared/exits/exit_engine.py` — the
  only component in this codebase with a real EOD force-close (and its newly-added
  entry-side counterpart, `is_before_eod_cutoff()`, deployed earlier today). Those
  gates deliberately never touch the exit path, on the documented assumption that
  *whatever* exit engine is active has its own EOD logic. `SmartExitEngine` does.
  `TieredExitManager` does not.
- **Live trading impact:** If switched live, a position could realistically be
  carried past 15:30 IST close into the next session — in paper mode this reproduces
  the exact mechanism behind the 2026-08-06 02:50 IST stale-snapshot incident (a
  stale premium marked against a fresh index-open tick); in real trading, unintended
  overnight options exposure, or broker-side forced square-off at unfavorable prices.
- **Risk level:** High (would be Critical if live-active today)
- **Reproducibility:** Always, once active — structural, not a rare edge case.
- **Recommended professional fix:** Add an EOD time check to
  `TieredExitManager.evaluate()`, reusing `shared/market_hours.py`'s
  `EOD_ENTRY_CUTOFF_TIME` as the single source of truth rather than a third
  independent constant.
- **Required regression tests:** Advance a position's clock past 15:15 IST with price
  sitting inside every other exit threshold, assert a forced EOD exit fires.

### 3.4 HIGH — The index-vs-premium ATR mismatch (§2.1) recurs independently in this package's own exit manager

- **File:** `momentum_strategy/exit_manager.py:188-209`
  (`_evaluate_exhaustion()`, `profit_points >= 1.5 * current_atr`)
- Same root defect as §2.1, confirmed as a fully independent second implementation
  (this package doesn't share `SmartExitEngine`'s code at all — it has its own).
  Worked example: for a ~₹100-150 premium position (common in today's real trades)
  with a modest 100-point index ATR, the exhaustion-lock check requires the premium
  to more than double before it's even reachable — effectively inert at that scale;
  for the ₹2415 premium trade seen today (delta ≈0.53), the same fixed-index-scale
  threshold could fire off comparatively minor index chop. **Recommended fix:**
  same as §2.1 — compute or proxy a premium-scale ATR instead of consuming the raw
  index-point value.

### 3.5 MEDIUM — `PARTIAL_BOOK_RR` config value (1:3) contradicts the module's own docstring (1:1)

- **Files:** `momentum_strategy/config.py:82-83` vs. `exit_manager.py`'s module
  docstring. Code is internally consistent (uses the config value correctly); the
  docstring is stale. A human trusting the docstring would believe positions de-risk
  to breakeven at a 1:1 move; they actually carry full initial risk until 1:3.
  **Recommended fix:** reconcile — needs a strategy-owner decision on which value is
  actually intended, not just a doc fix, since they materially disagree on when
  capital gets protected. Pin with a test linking the two, mirroring the pattern
  already used today for `EOD_ENTRY_CUTOFF_TIME`.

### 3.6 MEDIUM — `itm_selector.py`'s symbol format is incompatible with the real broker convention (latent — only matters if §3.1 is ever fixed)

- **File:** `momentum_strategy/itm_selector.py:178-182`. Builds symbols with a
  3-letter month abbreviation (`NIFTY26AUG1126950CE`); the real Fyers convention
  (confirmed against today's actual live logs and correctly implemented in
  `premium_selection/options_selector.py`) uses a numeric month
  (`NIFTY2681126950PE`). Currently unreachable per §3.1, but would be an immediate,
  100%-reproducible order-placement failure on every trade the instant that dead-code
  gap is closed without also fixing this. **Recommended fix:** reuse the existing
  correct symbol-construction convention rather than a second, divergent one.

### 3.7 LOW findings (grouped)
- Stale docstrings describing 100-150pt ITM depth when `config.py`'s actual
  `ITM_OFFSET_MIN/MAX` are both `0` (pure ATM, correctly compliant with the house
  mandate) — documentation-only, code is correct.
- No structural ATM/ITM clamp in `itm_selector.py::select_strike()` (unlike the
  live-path `options_selector.py`, which was hardened earlier this session) — relies
  entirely on config staying at safe values, no code-level backstop. Low today
  (dead code); would matter if ever revived.
- Duplicate, independently-maintained risk/exit/indicator infrastructure across this
  entire package vs. the shared modules the rest of the system uses — the root
  architectural explanation for §3.3-3.5 all being separate gaps from what the shared
  infrastructure already handles. A longer-term consolidation decision, not a single
  fixable bug.
- `generate_signals()`'s per-row Python loop (`__init__.py:399-552`) is unvectorized
  O(n) over up to 2000 rows per tick — not yet at 2026-08-06 livelock severity, but
  the same "recompute everything from scratch every tick" category already found
  costly elsewhere this session.

### 3.8 Verified correct (`institutional_momentum`)
`MarketRegimeDetector.detect_vectorized()` (the regime logic that IS live-reachable):
fully vectorized, correctly backward-looking, no repainting found. The dead-code
twin `MomentumSignalEngine.generate()`: internally correct multi-timeframe confluence
logic despite being unreachable. `MTMTrailingEngine`'s ratchet math: correct and
matches its own docstring's worked example exactly (only issue is it's never
invoked, per §3.1). `TieredExitManager`'s stop-loss check and partial-booking
mechanics: correctly premium-scale throughout — the ATR mismatch (§3.4) is isolated
to the exhaustion-exit sub-method specifically. No fixed-profit-target violation
found anywhere in this package — Phase 2/3 correctly runs uncapped per the house
mandate.

---

## 4. Experimental / legacy strategy sweep

*(`advanced_ai_ml_strategy.py`, `drl_strategy.py`, `marl_strategy.py`,
`meta_agent_strategy.py`, `ultra_meta_dip_swarm.py`, `enhanced_ai_strategy.py`,
`ema_crossover_pro_strategy.py`, `buy_the_dip_strategy.py` — none are live today, all
are one settings change away.)*

### 4.1 CRITICAL — `advanced_ai_ml_strategy.py` reintroduces the 2026-08-06 livelock pattern, in a worse (row-by-row) form

- **File:** `trading_bot/strategies/advanced_ai_ml_strategy.py:36-39, 208-209,
  234-238`. Five columns (`call_score`, `put_score`, `custom_sl_pct`,
  `trailing_sl_trigger`, `trailing_sl_offset`) written one scalar cell at a time via
  `df.loc[idx, col] = value` inside a Python `for` loop, directly onto the caller's
  live, persistent, shared candle buffer — not even vectorized, let alone copied
  first. **Recommended fix:** build all five as local arrays/Series, return them
  instead of mutating the caller's DataFrame at all.

### 4.2 CRITICAL — `drl_strategy.py`'s model observation vector is permanently constant — it cannot see the market

- **File:** `trading_bot/strategies/drl_strategy.py:68-81, 91`. `rsi`, `macd_hist`,
  `atr`, `vol_change` are read via `.get(key, default)` from a raw OHLCV dataframe
  that never has those columns computed or attached — every call silently returns
  the hardcoded defaults. `profit_pct` is hardcoded to `0.0`; `current_position` is
  set once in `__init__` and never updated. All six dimensions of the model's
  observation are permanent constants on every call, regardless of real price
  action — only the model's internal LSTM state evolves, in response to an
  unchanging input, never the market. This strategy would pass every internal
  validation (model loads, shapes match) while being **functionally non-functional**
  by construction — a "looks alive, does nothing" failure mode. **Recommended fix:**
  wire real feature computation before calling `compute_features()`; track real
  position/PnL state; add a loud failure (not a silent default) for missing required
  columns.

### 4.3 CRITICAL — `buy_the_dip_strategy.py` — most severe DataFrame-mutation instance found in this audit

- **File:** `trading_bot/strategies/buy_the_dip_strategy.py:19, 22-23, 26, 33, 36, 64,
  70`. Six incremental columns written directly onto the caller's DataFrame with
  **zero `.copy()` protection anywhere in the file** — the most unguarded instance of
  this pattern found across the entire codebase — plus a non-vectorized per-row loop.
  Reachable both directly and indirectly (`ultra_meta_dip_swarm.py` calls this
  strategy's raw signal function on every single invocation — see §4.4).
  **Recommended fix:** same as §4.1.

### 4.4 HIGH — Swarm/meta strategies compound their sub-strategies' bugs invisibly

- **Files:** `ultra_meta_dip_swarm.py:45-49` (calls `buy_the_dip` directly, inheriting
  §4.3), `meta_agent_strategy.py:38-47` (calls `advanced_ai`, inheriting §4.1, among
  four other sub-agents). A single `active_strategy` choice pulls in every
  dependency's defects at once, invisibly. **Note:** the previously-flagged concern
  that `meta_agent_strategy.py`'s `"institutional_momentum"` sub-agent reference
  might not match the actual registered name was checked directly against
  `momentum_strategy/__init__.py:29` and **is confirmed correct** — `STRATEGY_NAME =
  "institutional_momentum"` matches exactly. That specific concern is resolved, not
  a bug.

### 4.5 HIGH — `ultra_meta_dip_swarm.py`'s third "brain" is a near-total no-op that silently weakens its own consensus design

- **File:** `ultra_meta_dip_swarm.py:76-84`. The strategy is explicitly documented as
  requiring "at least 2 of 3 brains agree," but Brain 3's Bollinger-Band condition
  (`close > bb_lower` for calls, `close < bb_upper` for puts) is true on the
  overwhelming majority of ordinary bars — it only fails during a genuine ≥2-sigma
  excursion — so it contributes a near-constant vote regardless of real volatility
  regime. The comparison operators/band references look inverted relative to what a
  genuine "did price actually touch the dip band" check would need. Effectively
  degrades the documented 2-of-3 consensus to a 1-of-2 real-vote system.
  **Recommended fix:** correct the band comparison to genuinely test proximity to the
  *opposite* band per direction.

### 4.6 HIGH — `enhanced_ai_strategy.py`'s "Option Chain Analysis" confirmation layer is permanently simulated, never real, even in live trading

- **File:** `enhanced_ai_strategy.py:71`, `shared/indicators/option_chain.py:1-21`.
  `simulate_option_chain_sentiment()` is a 5-period price ROC proxy — its own
  docstring says a real production environment should query live option-chain data,
  but no conditional branch anywhere ever does so, live or backtest. One of the
  strategy's claimed "6 independent confirmation layers" is statistically correlated
  with pure price momentum, not a genuinely orthogonal signal — the "5 of 6 required"
  threshold is less rigorous than documented. **Recommended fix:** wire real
  option-chain data as the docstring itself says should happen, or honestly
  re-document this as a secondary momentum proxy.

### 4.7 HIGH — No validation anywhere that `active_strategy` is a real, registered strategy name

- **Files:** `trading_bot/main.py:874, 1044, 1257` (all read `active_strategy` with
  no validation), `trading_bot/strategies/registry.py:28-31` (raises `ValueError` if
  unregistered, but that's caught by a broad `try/except Exception` in `main.py` and
  just logged). A typo or a strategy that failed to auto-register due to an import
  error would cause `registry.run_strategy()` to raise on every tick, forever —
  caught, logged, retried next tick, same result. **The bot would report healthy at
  the process/health-check level indefinitely while generating zero real trade
  signals** — the same "looks alive, does nothing" failure class already found
  multiple times this validation window in different forms (2026-08-06 tick
  staleness, today's EOD-entry-cutoff gap). **Recommended fix:** validate
  `active_strategy` against `registry.registered_strategies` at startup and on every
  settings hot-reload, with a loud, actionable alert if invalid — don't let this
  surface only as a per-tick exception buried in a broad catch-all.

### 4.8 MEDIUM findings (grouped)
- Duplicate/inline RSI reimplementations in `buy_the_dip_strategy.py`,
  `ultra_meta_dip_swarm.py`, `marl_strategy.py` use plain rolling-mean smoothing (not
  Wilder EWM) and lack `shared/indicators/rsi.py`'s zero-division epsilon — a
  simultaneous zero-gain/zero-loss bar (dead-flat price run) produces `NaN`,
  silently suppressing signals during flat periods. Rare edge case, self-heals as
  "no signal" rather than crashing.
- Multiple strategies compute a "suggested/custom SL" DataFrame column
  (`advanced_ai_ml_strategy.py`, `ema_crossover_pro_strategy.py`,
  `buy_the_dip_strategy.py`) that the live execution path never reads — every option
  position actually gets the house premium-banded SL regardless of which strategy
  generated the entry. Dead output, no live-behavior impact, but a false sense of
  per-strategy customization for anyone reading the code.
- `marl_strategy.py` and `drl_strategy.py` re-run full-history model inference on
  every single tick (up to ~2000 forward passes per call) rather than caching
  recurrent state and inferring only the newest bar — real per-tick CPU/latency cost
  if ever activated at live tick frequency, compounded by `marl_strategy.py`
  explicitly discarding LSTM state continuity between calls.
- `marl_strategy.py` hardcodes a third, independent intraday cutoff (15:00 IST) via
  raw datetime arithmetic rather than routing through `shared/market_hours.py` —
  currently harmless (more conservative than the 15:15 EOD-entry-cutoff), but a third
  unpinned constant in exactly the class of drift that was found and fixed for the
  other two cutoffs earlier today.
- Likely off-by-window-size indexing bug in `buy_the_dip_strategy.py`'s dip/rally
  reference lookback (`iloc[i-5]` looks like an accidental copy of the rolling-window
  size rather than an intentional lookback offset) — affects entry timing/quality if
  ever activated, not a safety issue.
- `advanced_ai_ml_strategy.py` and `drl_strategy.py` use `print()` instead of the
  standard logger — invisible to `logs/engine.log` and this validation window's
  entire log-based monitoring workflow if ever activated.
- `advanced_ai_ml_strategy.py`'s model file (`models/xgboost_model.json`) is shared
  between live trading and backtesting with no isolation beyond atomic-write
  corruption protection — a concurrent backtest run would not be reproducible against
  a fixed model if live retraining happened mid-run. Research-integrity concern, not
  a live-safety issue.
- `drl_strategy.py`'s module-level singleton shares one LSTM recurrent state across
  all instruments — would corrupt the model's sequential-memory assumption the
  moment both multi-instrument trading and this strategy were ever active together.
  Zero exposure under today's single-instrument config.

### 4.9 Verified correct (experimental sweep)
`shared/indicators/smc.py`: correctly copies input, correctly shift-before-roll, no
look-ahead. `registry.py`'s `autodiscover()`: gracefully degrades on import failures
rather than crashing the whole registry (though see §4.7 for the separate concern
about logically-incomplete-but-importable strategies). `ema_crossover_pro_strategy.py`'s
core crossover/VWAP/ADX logic: correctly copies, correct backward-shift crossover
detection, correct cumulative daily-anchored VWAP, no look-ahead — only its dead
output tail (§4.8) needs cleanup. Every one of the 8 strategies' signal conventions
is consistent with option-buying-only execution — none assume an actual
short-the-underlying position. `advanced_ai_ml_strategy.py`'s train/test split
direction is chronologically correct; its future-return training label is
legitimately training-only, not a live-inference leak.

### 4.10 Strategy maturity summary

| Strategy | Maturity |
|---|---|
| `ema_rsi` (live today) | Functional but with real gaps — see §1 |
| `institutional_momentum` | Architecturally the most compromised — ~half dead code (§3.1) |
| `premium` | Functional with real gaps — see §5 |
| `advanced_ai` | Not production-ready — critical mutation bug, dead SL output |
| `drl_strategy` | Non-functional if activated — cannot see the market at all |
| `MARL_Ultra` | Most mature of the experimental set — visible prior audit fixes; remaining issues are performance/consolidation, not correctness |
| `meta_agent_swarm` | Sound design, inherits `advanced_ai`'s critical bug when active |
| `ultra_meta_dip_swarm` | Not production-ready — inherits `buy_the_dip`'s critical bug; own consensus design partly defeated |
| `enhanced_ai` | Partially honest (self-documents its simulation), needs real data wiring |
| `ema_crossover` | Closest to production-ready of the standalone strategies |
| `buy_the_dip` | Not production-ready — worst mutation bug found, plus a likely indexing bug |

---

## 5. `premium_selection` signal/filter pipeline

*(Used when `active_strategy = "premium"` — not live today; `options_selector.py`
within this same package IS live-shared and already covered in §1.)*

### 5.1 CRITICAL — No-trade filter's `is_trending` threshold contradicts its own two adjacent docstrings

- **File:** `trading_bot/strategies/premium_selection/no_trade_filter.py:62`
  (`df["is_trending"] = df["choppiness_index"] < 61.8`) vs. its own docstrings at
  lines 35-37 and 54, both of which state the standard convention: `<38.2 = strong
  trending`, `>61.8 = choppy`. The code uses the *choppy* threshold where it should
  use the *trending* one, meaning the entire neutral 38.2-61.8 zone is misclassified
  as "trending" — the choppiness no-trade guard now only fires for genuinely choppy
  markets (≥61.8), never for the ambiguous middle zone its own documentation says
  shouldn't count as a strong trend either. Silently widens the tradeable-condition
  window well beyond the file's own stated "capital protection over trade frequency"
  philosophy. **Recommended fix:** change the threshold to `< 38.2`, matching both
  docstrings — an unambiguous implementation bug, not a debatable design choice.

### 5.2 HIGH — `is_tradeable`'s hardcoded 0.75 confidence gate silently overrides the engine's own documented "lowered to 0.60" tuning

- **File:** `signal_engine.py:42` (`is_tradeable` property, hardcoded `>= 0.75`) vs.
  line 206 (internal gate, `if composite < 0.60: NO_TRADE`, with an inline comment
  literally reading "Aggressive tuning -> lowered from 0.75 to 0.60"). For any
  composite score in [0.60, 0.75), the engine does the full work of computing Greeks
  and selecting a strike, then discards the resulting signal via the un-synced
  `is_tradeable` check — the tuning the developer's own comment describes as intended
  never actually takes effect. **Recommended fix:** sync the two thresholds (which
  one is correct needs a product decision; the current state is self-contradictory,
  not an intentional two-tier design — no comment anywhere explains a deliberate
  split).

### 5.3 HIGH — `generate_signals()` (the backtest/registry-compatible path) is a second, diverging implementation with hardcoded max AI confidence and a different threshold than live

- **File:** `signal_engine.py:232-326`. Fully duplicated logic (not a shared call
  into `PremiumSignalEngine`), hardcodes `ai_confidence = 1.0` for every historical
  bar (no model consulted at all) and gates at 0.60, not the real live 0.75 (§5.2).
  Both divergences push toward more trades/higher scores in backtest than live could
  ever produce — a live-vs-backtest consistency defect specific to this strategy,
  independent of §2.2's broader backtest-engine finding. **Recommended fix:** route
  through the same evaluation logic as live, or explicitly flag backtest results for
  this strategy as an AI-filter-blind upper bound.

### 5.4 MEDIUM-HIGH — Volume filter is a permanent no-op for NIFTY/SENSEX — the system's mandated focus instruments

- **File:** `volume_filter.py:23-29`. `nunique() <= 2` (detecting mocked/constant
  index volume) responds by *always passing* rather than reporting neutral — fails
  open, not closed, on ambiguous data, backwards for a filter whose own docstring
  states "capital protection over trade frequency." For the two instruments the house
  mandate says to mainly focus on, "volume confirmation" contributes a fixed 0.667 to
  every composite score, never actually discriminating. **Recommended fix:** skip the
  volume layer's contribution entirely for constant-volume instruments (renormalizing
  remaining weights) rather than pretending it passed.

### 5.5 MEDIUM — `higher_highs`/`lower_lows` compare against a swing reference roughly 2x the intended lookback stale

- **File:** `market_structure.py:37-42`. An extra `.shift(swing_lookback)` applied on
  top of an already-lagged `swing_high`, comparing today's high against a swing level
  from ~20 bars ago rather than "the previous swing high" the docstring describes.
  Flagged at Medium confidence — plausible unintended double-shift, but cannot fully
  rule out a deliberate longer-horizon design choice without the original author's
  intent.

### 5.6 MEDIUM (performance) — Full 6-layer filter pipeline recomputed over the entire dataframe every tick

- **Files:** `signal_engine.py:124-133` and every `compute_*` filter function. Same
  class of issue as `institutional.py`'s already-documented CPR-groupby cost — a
  separate instance in a different file, particularly costly here since
  `no_trade_filter.py`'s time-window check uses a non-vectorized `.apply()` over up
  to 2000 rows every single tick. Not yet exercised live; worth fixing before this
  strategy is ever switched on, so it doesn't become a repeat of the 2026-08-06
  livelock's underlying cost category.

### 5.7 LOW findings (grouped)
- `trend_valid` (the "reject tangled EMA20/EMA50" safety check) is computed but never
  consumed by `signal_engine.py`'s bullish/bearish determination — orphaned dead
  output representing a real, if minor, gap versus documented intent.
- A logically-redundant (but behaviorally inert) `~rsi_no_mans_land` term in
  `momentum_filter.py` — pure readability nit, no behavior change from removing it.

### 5.8 Verified correct (`premium_selection`)
`volatility_filter.py`: correctly reuses `shared/indicators/atr.py`'s proper
true-range ATR against the underlying index's own OHLC for regime detection — a
legitimate, different use case from §2.1's exit-side mismatch (this is about the
index's own volatility regime for signal gating, not sizing an option's trailing
stop; no bug here). `market_structure.py`'s pullback-detection genuine-retest logic:
correctly shift-before-roll, no look-ahead beyond the isolated §5.5 issue.
`PremiumSignalEngine.__init__`: no expensive work, reconstructing it fresh per tick
is not itself a problem (the cost is in `evaluate()`, §5.6). Option-buying direction
semantics: unambiguous. Composite-score layer weights (0.20/0.20/0.15/0.10/0.20/0.15
= 1.0): internally consistent between the live and backtest implementations — only
the *inputs* to those weights diverge (§5.3).

---

## 6. Consolidated risk register

| # | Finding | Section | Severity | Live exposure today |
|---|---|---|---|---|
| 1 | `select_option()` failure falls through to raw index order | §1.1 | Critical | Live path, unexercised |
| 2 | `ema_rsi_strategy.py` reproduces the livelock signature | §1.2 | Critical | **Live path, active today** |
| 3 | ATR unit mismatch breaks option trailing stops | §2.1 | Critical | **Live path, every open position** |
| 4 | Backtest engine models the wrong SL/target architecture | §2.2 | Critical | All backtest/optimization tooling |
| 5 | `momentum_strategy` package ~half dead code | §3.1 | Critical | Dormant (one settings change away) |
| 6 | `advanced_ai_ml_strategy.py` DataFrame mutation | §4.1 | Critical | Dormant |
| 7 | `drl_strategy.py` cannot see the market | §4.2 | Critical | Dormant |
| 8 | `buy_the_dip_strategy.py` DataFrame mutation | §4.3 | Critical | Dormant |
| 9 | Dashboard RSI/VWAP controls disconnected | §1.3 | High | **Live path, active today** |
| 10 | `options_selector.py` not IST-anchored | §1.4 | High | Live path, dormant risk |
| 11 | Partial-booking risk recomputed against trailed stop | §2.3 | High | **Live path, every position** |
| 12 | TOCTOU race across concurrent symbol evaluation | §2.4 | High | Dormant (multi-instrument pending) |
| 13 | `momentum_strategy`'s own DataFrame mutation | §3.2 | High | Dormant |
| 14 | `momentum_strategy` has no EOD exit at all | §3.3 | High | Dormant |
| 15 | ATR mismatch recurs in `momentum_strategy` | §3.4 | High | Dormant |
| 16 | Swarm strategies compound sub-strategy bugs | §4.4 | High | Dormant |
| 17 | `ultra_meta_dip_swarm` consensus partly defeated | §4.5 | High | Dormant |
| 18 | `enhanced_ai`'s option-chain layer is fake | §4.6 | High | Dormant |
| 19 | No validation of `active_strategy` setting | §4.7 | High | **Live-adjacent — a typo away from silent failure** |
| 20 | `premium`'s no-trade filter threshold inverted | §5.1 | Critical | Dormant |
| 21 | `premium`'s `is_tradeable` gate un-synced | §5.2 | High | Dormant |
| 22 | `premium`'s backtest path diverges from live | §5.3 | High | Dormant |

*(Medium/Low findings enumerated in their respective sections above; omitted here for
brevity — 9 Medium, 6+ Low across all sections.)*

**Note on §5.1's severity:** listed as Critical within its own section (an
unambiguous, self-contradicting implementation bug) but scoped to the dormant
`premium` strategy — included in the narrative above rather than the top-line
executive summary count, which focused on live-path/always-active exposure.

---

## 7. What this audit did not cover

- Frontend/dashboard code beyond the specific RSI/VWAP wiring gap in §1.3.
- `api_bridge.py` beyond what was already covered by this session's earlier
  production-monitoring work.
- Broker integration code (`brokers/fyers_broker.py` etc.) beyond call sites directly
  touched while tracing strategy entry/exit flows.
- Database schema/migration correctness beyond what §2.6 already verified for
  `shared/state.py`.
- A live, on-market re-verification of any dormant strategy's behavior (all findings
  above are static-analysis-derived; activating any of these strategies for live
  observation was explicitly out of scope for this audit and was not done).

---

## 8. Suggested fix-priority order (for a future, separately-approved implementation pass)

1. §1.2 — `ema_rsi_strategy.py`'s livelock-pattern line (matches a confirmed incident,
   live today, small/mechanical fix mirroring today's `registry.py` change).
2. §2.1 / §3.4 — ATR unit mismatch (affects every open option position across every
   strategy; needs a real design decision on the replacement premium-scale ATR
   source, not just a mechanical fix).
3. §1.1 — `select_option()` failure abort gate (small, mechanical, closes a real
   though unexercised safety gap).
4. §4.7 — `active_strategy` validation at startup/reload (small, prevents an entire
   class of future silent-failure incidents).
5. §2.2 — Backtest engine architecture update (larger effort; blocks trustworthy
   validation of everything else going forward).
6. Everything else, ranked by the risk register in §6, factoring in which strategies
   are actually candidates for future activation.
