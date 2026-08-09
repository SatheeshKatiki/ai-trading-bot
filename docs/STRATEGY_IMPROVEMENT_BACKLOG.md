# Strategy Improvement Backlog — Evidence-Ranked

**Purpose:** the prioritized queue for evolving existing strategies to
production grade. No new strategies. Each item is executed one at a time
through the full cycle (root cause → minimal change → regression tests →
strategy validation → production-architecture backtest → before/after
comparison → docs → local commit) before the next begins.

**Evidence base:** the static audit (`STRATEGY_AUDIT_2026-08-07.md`, 23
findings across all 12 strategies + shared infra) combined with the
production-architecture backtest
(`PRODUCTION_STRATEGY_VALIDATION_FRAMEWORK.md`, 12 strategies × 123
trading days × 5 regimes). Items are ranked by expected impact on
robustness/consistency/drawdown, **not** by backtest profit alone.

---

## Completed

### ✅ #0 — Regime classifier gap threshold (measurement prerequisite)
- **Type:** validation-harness fix, no live trading impact.
- **Root cause:** hardcoded 0.5% overnight-gap threshold vs. a real NIFTY
  median overnight move of 0.331% — labelled 36% of days as "gap days,"
  and since `gap_day` wins classification priority, those days were also
  stripped from every other regime's sample.
- **Why it had to come first:** 7 of 12 strategies showed sub-1.0 profit
  factor on "gap days" in the first run. Tuning any strategy against that
  signal would have been optimizing on a miscalibrated instrument.
- **Fix:** percentile-based threshold (p90 of the dataset's own overnight
  moves) with a 0.75% absolute floor.
- **Result:** gap days 44/123 (36%) → 13/123 (11%); trending 28→39,
  sideways 45→62. 2 regression tests added.
- **Commit:** `0082cfd`

---

### ✅ #1 — `meta_agent_swarm`: `institutional_momentum` sub-agent silently broken on every call

- **Root cause:** `meta_agent_strategy.py:41` assigned
  `registry._strategies[agent](df, **kwargs)`'s raw return straight into a
  DataFrame column. `institutional_momentum` returns a
  `(signals, rejection_logs)` **tuple** (momentum_strategy/__init__.py:199);
  every other sub-agent returns a bare Series. Proven empirically in
  isolation: the tuple assignment raises
  `ValueError: Length of values (2) does not match length of index (N)` —
  the exact error from the production logs — caught by the loop's broad
  `except`, logged, skipped, on every single call.
- **Why the old implementation was weak:** the swarm ran as a
  **4-of-5-technical-brain consensus, not 5**, for its entire life, while
  its docstring and operator-facing description claimed 5 + sentiment. A
  score threshold (≥3/≤-3) tuned for the full vote pool was being applied
  to a permanently smaller one. `main.py`'s own entry loop already
  unwraps this exact case; this file never replicated it.
- **Why the fix is better:** restores the designed vote pool with a
  2-line change mirroring `main.py`'s existing, proven pattern. No
  philosophy change — the strategy still does exactly what it was
  designed to do, for the first time.
- **Before/after (same 123-day window, production architecture):**

  | Metric | BEFORE (4 brains) | AFTER (5 brains) |
  |---|---|---|
  | Trades | 132 | 242 |
  | Net profit | ₹11,570 | **₹36,290** |
  | Profit factor | 1.07 | **1.13** |
  | Win rate | 67.4% | **70.2%** |
  | Expectancy | ₹87.65 | **₹149.96** |
  | Recovery factor | 0.29 | **0.85** |
  | Max consecutive losses | 6 | **4** |
  | Max drawdown | 40.2% | 42.7% (marginally worse) |
  | Realized R:R | 0.52 | 0.48 (marginally worse) |

- **My stated expectation was WRONG, recorded honestly:** I predicted
  trade count would *fall*, reasoning that a genuine 6th vote makes ±3
  consensus harder to reach. It nearly doubled instead. The mechanism is
  obvious in hindsight — the broken brain contributed **zero** to
  `total_score`, so restoring it lets the score *reach* the threshold more
  often, not less. Worth recording because the same faulty intuition
  ("more filters ⇒ fewer trades") would misprice future consensus-strategy
  work.
- **Actual impact:** materially positive on every quality measure that
  matters (expectancy +71%, recovery factor ~3x, fewer consecutive
  losses), with drawdown essentially flat. Does **not** clear the KEEP bar
  — see the regime split below, which becomes backlog item #2.
- **Post-fix regime profile (corrected labels):** trending PF 1.34
  (+₹31,135), sideways PF 1.24 (+₹31,503) — but high_volatility PF 0.48
  (-₹11,524, 8 trades) and gap_day PF 0.62 (-₹14,639, 21 trades). 207 of
  242 trades are in the two profitable regimes; essentially all the losses
  are concentrated in two regimes it should arguably not trade at all.
- **Tests:** 4 new regression tests, including one asserting all 5
  sub-agents actually contribute (not merely that nothing crashes) and one
  confirming a genuinely broken sub-agent is still isolated. Full suite:
  401 passed.
- **Commit:** see `git log` for the `fix(strategy): meta_agent_swarm` entry.

---

## Queued — ranked by expected impact

### ✅ #0a — MARL_Ultra Capital Protection deadlock — FIXED 2026-08-07

- **Fix:** `RiskAgent` now carries a `_session_date` and an IST-anchored
  `_reset_daily_if_needed()`, mirroring
  `shared/risk/manager.py::RiskManager` exactly. Capital Protection Mode
  expires with the session that earned it — precisely what
  `record_trade_result()`'s docstring always claimed ("stop trading for
  the session"). Protection strength is unchanged: 2 losses still halves
  size, 3 still stops trading, a win still clears the streak.
- **Load-bearing detail:** the reset is checked on the **read** path
  (`get_position_size_multiplier`) as well as the write path. Read-path
  placement is what actually breaks the deadlock — once entries are
  blocked the write path is unreachable by construction, so a write-only
  reset would never fire. A dedicated test pins this
  (`test_reset_happens_on_the_read_path_specifically`).
- **Harness change required to validate it:** a backtest compresses 123
  simulated days into ~90s of wall clock, so against the real clock the
  daily rollover would never fire and the backtest would keep reproducing
  a bug that no longer exists in production. The harness now runs the
  agent on the **simulated** date (`_set_simulated_session_date`). This
  is the faithful model, not a workaround — in production, real days
  genuinely do pass between sessions. The agent's own logic is untouched;
  it is simply told what "today" is.
- **Before/after (same 123-day window):**

  | Metric | BEFORE (deadlocked) | AFTER (fixed) |
  |---|---|---|
  | **Trading days** | **14 of 123** | **122 of 123** |
  | Months traded | February only | Feb, Mar, Apr, May, Jun, Jul |
  | Last trade | 2026-02-19 | 2026-07-31 |
  | Trades | 127 | 976 |
  | Net profit | ₹53,456 | **₹130,399** |
  | Recovery factor | — | 3.16 |
  | Profit factor | 1.41 | 1.10 |
  | Max drawdown | 16.5% | 41.3% |

- **⚠️ Read the PF/DD movement correctly — it is NOT a regression.** The
  "before" figures were never a real six-month result; they were three
  weeks of trading followed by silence. Comparing a 3-week sample against
  a 6-month sample on PF and drawdown is not like-for-like. The apparent
  "degradation" is the removal of an accidental survivorship effect in
  the measurement: the strategy was never achieving PF 1.41 across the
  window, it was achieving it across 14 days and then not trading at all.
  Net profit — the metric least distorted by the truncation — went up
  144%.

- **🔴 The fix exposed a second finding: MARL_Ultra is now a byte-identical
  duplicate of `marl_strategy`.** Post-fix, every single metric matches
  exactly (976 trades, ₹130,399.24, PF 1.10, WR 70.4%, expectancy 133.61,
  DD 41.26%). The only thing distinguishing the two registrations was the
  `record_trade_outcome()` feedback loop, and that loop's only observable
  effect was the permanent deadlock — 3 consecutive losses *within a
  single day* is evidently rare enough never to bind. So MARL_Ultra's
  former "2nd-best profit factor in the suite" was **entirely an artifact
  of the deadlock** truncating it to a favourable 3-week sample.
  **Disposition change:** MARL_Ultra is now a redundancy/consolidation
  candidate — not on performance grounds, but because it is the same
  strategy under a second name. That is a product decision, not a
  unilateral one; flagged, not acted on.
- **Tests:** 9 new regression tests, including the deadlock-breaks-on-new-
  session case and same-session-persistence (protection must survive
  intraday). Full suite: **410 passed**, no regressions.

---

### ~~#0a original finding~~ (kept below for the root-cause record)

### 🔴 MARL_Ultra Capital Protection Mode is a permanent deadlock (HIGH severity, live-reachable)

**This is the most serious finding of the improvement pass and jumps the
queue.** It is a correctness/safety bug, not an optimization.

- **Strategy:** MARL_Ultra (live-reachable today via a one-line
  `active_strategy` settings change; `marl_strategy` shares the same
  singleton but never receives the feedback that triggers it).
- **Root cause chain** (each link verified in source):
  1. `record_trade_outcome()` (`marl_strategy.py:114`) feeds every closed
     MARL_Ultra trade's P&L into a **module-level singleton**
     `_marl_instance`'s `RiskAgent`. `main.py` calls this on every
     position close (two sites: `main.py:836`, `main.py:1272`).
  2. On a loss, `RiskAgent.record_trade_result()`
     (`drl/marl/risk_agent.py:28`) increments `_consecutive_losses`; on a
     **win** it resets to 0 (`risk_agent.py:35`).
  3. At `_consecutive_losses >= 3`, `get_position_size_multiplier()`
     returns `0.0` (`risk_agent.py:55`).
  4. `generate_signals()` calls `is_capital_protection_blocking_entries()`
     and, when true, **blocks every new entry signal for that call**
     (`marl_strategy.py:253-265`).
  5. Blocked entries ⇒ no new positions ⇒ no new closes ⇒
     `record_trade_outcome()` is never called again ⇒ `_consecutive_losses`
     can never reach the win that would reset it.
- **Result: after 3 consecutive losses, MARL_Ultra stops trading
  permanently** — for the entire remaining life of the process. There is
  no daily reset (`RiskAgent` has no `reset_daily`, unlike
  `shared/risk/manager.py::RiskManager._reset_daily_if_needed()`), and
  `_marl_instance` is constructed once per process.
- **The implementation contradicts its own documented intent.**
  `RiskAgent.record_trade_result()`'s docstring
  (`drl/marl/risk_agent.py:31-32`) states the rule as: *"After 2
  consecutive losses, switch to half-size mode. After 3 consecutive
  losses, **stop trading for the session**."* The intent is explicitly
  **session-scoped** — but no session boundary exists anywhere in the
  class: no daily reset, no time decay, no external reset call. The only
  path back to normal is a winning trade, which the block itself makes
  unreachable. This is a missing-reset bug against a clearly stated
  design, not a debatable design choice.
- **Why this was never caught:** the strategy's own comment
  (`marl_strategy.py:257-259`) explicitly assumes *"a fresh backtest
  process/run always starts with a clean RiskAgent... so this never fires
  there."* That assumption held for every previous backtest tool, because
  none of them fed trade outcomes back. This harness does (deliberately,
  for live fidelity) — which is precisely how the deadlock surfaced, in
  the form of `marl_strategy` reporting 0 trades after MARL_Ultra ran
  first and poisoned the shared singleton.
- **Evidence:** `[RiskAgent] 3+ consecutive losses. Position size: 0
  (trading stopped).` repeats ~80 consecutive times at the tail of the
  MARL_Ultra run log, never once recovering.
- **Proposed fix (not yet implemented — needs approval, and it is a risk
  parameter, not an infra bug):** give `RiskAgent` the same IST-anchored
  daily reset `RiskManager` already has, so Capital Protection Mode
  expires at the start of each trading day rather than persisting
  forever. That preserves the intended protection (stop trading after a
  bad streak *today*) while removing the permanent-lock failure mode.
  An alternative — a time-decay or a manual reset endpoint — would also
  work; this needs a decision, not a unilateral change.
- **🔴 MEASURED IMPACT — the deadlock fires early and kills 85% of the
  window.** Tested directly by extracting the trade-date distribution
  from a clean, isolated MARL_Ultra run over the 123-day window:

  | | |
  |---|---|
  | Days evaluated | 123 |
  | Days it actually traded | **14** |
  | First trade day | 2026-02-02 |
  | **Last trade day** | **2026-02-19** |
  | Trading days per month | `{'2026-02': 14}` — February only |

  It hit 3 consecutive losses around 2026-02-19 and **never traded again
  for the remaining ~104 trading days (March–July)**. Its headline
  "PF 1.41 on 127 trades — 2nd-best in the suite" is therefore **three
  weeks of trading, not six months**, and its rank in the comparison
  table is not comparable to strategies that traded the full window.
  The day-isolated harness gives each day a fresh `RiskManager`, but the
  MARL singleton is process-global and outlives that reset — exactly
  mirroring live behavior, where the engine process runs continuously
  across days.
- **Severity upgraded to CRITICAL.** This is not "understated results" —
  the strategy is silently non-functional for the overwhelming majority
  of any period longer than its first loss streak. In live trading it
  would appear healthy at the process level (no crash, no error, signals
  still evaluated) while never taking another trade. That is the exact
  "looks alive, does nothing" failure class this validation window has
  now found four separate times (2026-08-06 tick staleness, the
  EOD-entry-cutoff artifact, `active_strategy` typo silent-retry, and
  this).
- **Confidence: high on the mechanism** (verified line by line) **and now
  high on the impact** (measured directly, reproducible).



### #1a — `meta_agent_swarm`: gate out gap-day and high-volatility regimes (direct follow-on)
- **Evidence:** post-fix, 100% of this strategy's net losses come from
  gap_day (PF 0.62) and high_volatility (PF 0.48) — 29 of 242 trades
  producing -₹26,163, against +₹62,638 from the 207 trending/sideways
  trades.
- **Why this is a genuine control, not curve-fitting:** a consensus-of-
  momentum-brains design has no theoretical reason to work through an
  overnight gap (where the prior session's momentum reading is invalidated
  before the open) or a volatility spike (where the vote pool's individual
  brains all degrade simultaneously). The mechanism justifies the gate;
  the backtest merely confirms it.
- **Expected impact:** net profit toward ~₹62k and PF toward ~1.3 if the
  excluded regimes contribute nothing, with a meaningful DD reduction.
  **Confidence: medium-high** on direction, lower on magnitude.

#### ⚠️ Premise re-verified 2026-08-07 — recommendation NARROWED, and blocked on a design decision

Re-checked against the post-5-brain-fix, corrected-regime data before
implementing. The headline premise holds (losing regimes total -₹26,348
against +₹62,638 from trending/sideways), **but the two regimes are not
equally supportable and must not be treated as one change:**

| Regime | Trades | **Days** | Net | Avg/trade | Max consec. losses |
|---|---|---|---|---|---|
| gap_day | 21 | 13 | -₹14,639 | -₹697 | 1 |
| high_volatility | 8 | **3** | -₹11,524 | -₹1,441 | 3 |
| low_volatility | 6 | 6 | -₹184 | -₹31 | 1 |

- **gap_day gate — defensible.** 21 trades over 13 distinct days, losses
  *dispersed* (max consecutive loss = 1, so this is a persistent drag,
  not one blow-up), and it has an independent mechanism: a
  momentum-consensus design has no reason to hold an edge through an
  overnight gap that invalidates the prior session's momentum reading
  before the open. Mechanism first, statistics confirming — the right
  order.
- **high_volatility gate — NOT defensible, do not implement.** 8 trades
  across **3 days**. Excluding a regime on a 3-day sample is textbook
  curve-fitting, and the -₹1,441/trade average with 3 consecutive losses
  suggests one bad cluster dominating rather than a repeatable regime
  effect. This would be exactly the "optimize blindly on backtest
  profit" failure the project's own rules forbid. Revisit only with a
  materially larger sample (a longer window or additional instruments).
- **low_volatility — ignore.** -₹184 over 6 trades is noise.

**Architectural blocker (needs a decision before any of this can ship):**
regime classification currently lives in `validation_harness/regimes.py`,
which is *validation* code. A production strategy must not import from
the harness — that inverts the dependency. Implementing any regime gate
therefore requires one of:
  1. **Promote regime detection into `shared/`** as production code, with
     the harness then consuming it too (single source of truth, and a
     prerequisite for the eventual Market Regime Strategy Router — likely
     the right long-term call, but a real piece of work).
  2. **Self-contained in-strategy gap check** — `meta_agent_strategy.py`
     computes the overnight gap from the `df` it already receives. Minimal
     and dependency-free, but a second, private definition of "gap day"
     that will drift from the harness's.
  3. Defer until the Router work makes option 1 necessary anyway.

**Recommendation:** option 1, scoped as its own backlog item, then the
gap_day gate on top of it. Not implemented unilaterally — this changes
production architecture, and the sample-size finding means the change is
smaller and less urgent than the original item implied.

### ~~#1~~ (superseded — completed above)
- **Strategy:** meta_agent_swarm (also degrades ultra_meta_dip_swarm's sibling pattern)
- **Root cause:** `meta_agent_strategy.py:41-43` assigns
  `registry._strategies[agent](df, **kwargs)` straight into a DataFrame
  column, but `institutional_momentum`'s `generate_signals()` returns a
  `(signals, rejection_logs)` **tuple**, not a Series. Raises
  `Length of values (2) does not match length of index (N)` on every
  single call; caught by a broad `except Exception`, logged, skipped.
- **Why the existing implementation is weak:** `main.py`'s own entry loop
  handles this exact case correctly
  (`if isinstance(signals_data, tuple): signals, _ = signals_data`) —
  this file never replicated that check. The strategy has therefore been
  running as a **4-of-5-brain consensus, not 5**, for its entire life,
  while its docstring and the operator-facing description both claim 5
  technical brains + 1 sentiment. A consensus threshold tuned for 6 votes
  applied to a 5-vote pool is systematically mis-scaled.
- **Proposed fix:** unwrap the tuple exactly as `main.py` does. ~2 lines.
- **Expected impact:** restores the missing brain to the vote pool.
  Directionally should *reduce* trade count (a genuine 6th vote makes the
  score ≥3 consensus harder to reach by chance) and improve signal
  quality. Current: 132 trades, PF 1.07, 40.2% max DD — the low PF and
  high DD are consistent with a consensus filter that isn't actually
  filtering as designed. **Confidence: high** (mechanism is certain; the
  magnitude of PF/DD improvement is not).
- **Risk:** low. Isolated to one file, no shared infrastructure touched.

### ✅ #2 — `enhanced_ai` RSI dual-confirmation defect — FIXED 2026-08-08 · verdict **IMPROVE**

- **Root cause (measured, not inferred):** the bull and bear RSI
  confirmations were `rsi > 40` and `rsi < 60`. Those ranges **overlap**
  across the entire 40-60 band — where RSI spends most of its life.
  Measured over the real validation window (9,219 bars): the RSI layer
  awarded a confirmation point to **both** directions on **50.6%** of
  bars, and awarded at least one point on **100.0%** of bars. It was
  never silent.
- **Why the old implementation was weak:** a confirmation layer that
  confirms both directions simultaneously carries zero information, yet
  it counted toward the "5 of 6 layers must agree" threshold exactly like
  a genuine one — effectively lowering the real bar to 4-of-5 and
  systematically admitting under-confirmed signals.
- **Fix:** split at the RSI midline so at most one side can claim the
  point, preserving the intended "RSI momentum confirmation" philosophy.
  A guard collapses any overlapping caller/settings values back to the
  midline, so the defect cannot be reintroduced by configuration.
- **Before/after (same 123-day window):**

  | Metric | BEFORE | AFTER |
  |---|---|---|
  | Net profit | -₹22,778 | **-₹16,160** (loss cut 29%) |
  | Expectancy | -₹38.80 | **-₹27.62** |
  | Max drawdown | 61.6% | **55.3%** |
  | Recovery factor | -0.37 | -0.29 |
  | Profit factor | 0.97 | 0.98 |
  | Trades | 587 | 585 |
  | Realized R:R | 0.45 | 0.45 (unchanged) |

  Biggest regime shift: gap_day went from -₹21,062 (PF 0.84) to
  **-₹6,684 (PF 0.95)** — the under-confirmed signals the defect was
  admitting were concentrated exactly where a weak confirmation hurts
  most.
- **A hypothesis I formed and then disproved, recorded honestly:** the
  entire remaining loss sits in `low_volatility` (-₹23,354; everything
  else nets **+₹7,194**). I suspected this was the documented
  5-minute-bar gap-through artifact hitting cheap near-expiry contracts.
  **It is not.** Inspecting all 20 trades: the losses are overwhelmingly
  liquid ₹150-250-band contracts exiting at sensible stop distances
  (228.64→193.69, 182.39→148.92, 199.55→169.56). These are legitimate,
  correctly-executed stop-losses, not measurement artifacts.
- **What the data actually shows:** the losses are *temporally*
  concentrated, not artifactual. The worst 3 trades are 69% of the net
  loss, and **8 of the 9 losing trades fall in five consecutive June
  days** (2026-06-16 → 06-22). "low_volatility" in this window is
  effectively one bad week plus a single April day — 6 days total.
- **Verdict: IMPROVE, not REMOVE.** Removal is not supportable on this
  evidence: excluding one concentrated bad week the strategy is roughly
  breakeven (PF 0.98), and a 6-day regime sample cannot carry a removal
  decision. The fix is a genuine, mechanism-justified improvement and is
  kept. The strategy is *not* production-grade — a 68% win rate against a
  0.45 realized R:R is marginal by construction — but it is a candidate
  for further improvement, not elimination.
- **Next candidate for this strategy (not yet done):** the volume layer
  has the *identical* defect class — `vol_bearish = vol_bullish`, so it
  awards the same point to both directions and cannot discriminate
  either. Whether that is a legitimate "conviction gate" (the code's
  stated intent) or a second free point inflating the 5-of-6 threshold is
  the next thing to test.
- **Tests:** 6 new regression tests pinning mutual exclusivity, the
  settings-overlap guard, and that legitimate non-overlapping custom
  thresholds still pass through. Full suite: **416 passed**.

---

### ~~#2 original~~ — `enhanced_ai` is the only net-negative strategy
- **Strategy:** enhanced_ai (587 trades, PF 0.97, net -₹22,778, 61.6% max DD)
- **Root cause candidates (needs the post-regime-fix data to separate):**
  (a) audit §4.6 — its "Option Chain Analysis" confirmation layer is
  permanently simulated (a 5-period price ROC proxy), never real
  option-chain data, so one of its claimed 6 independent confirmations is
  actually correlated with the momentum layers it's supposed to
  independently confirm; (b) its low-volatility regime PF of 0.34 was the
  worst of any strategy/regime pair in the first run.
- **Why weak:** a "5 of 6 confirmations" threshold is only as strong as
  the independence of those 6 signals. Two-to-three correlated momentum
  proxies masquerading as independent votes makes the filter far weaker
  than its design intends.
- **Proposed fix (staged):** first add a regime/volatility gate to stop it
  trading the conditions where it consistently bleeds; separately, either
  wire real option-chain data or stop counting the simulated layer toward
  the confirmation threshold.
- **Expected impact:** turning off the worst regime alone should move PF
  above 1.0. **Confidence: medium** — needs post-fix regime data first.

### ❌ #2b — `ema_rsi` trailing-offset scale hypothesis — TESTED, REJECTED, NO CHANGE MADE

Recorded because a negative result is evidence, and the project rule is
"improve only if there is measurable evidence; otherwise keep the
strategy unchanged."

- **Hypothesis:** `trailing_offset_pct = 0.35` is an *index-scale*
  parameter (0.35% is a meaningful NIFTY move) applied to *option-premium*
  percentage moves that routinely swing 10-40%. A 0.35pp giveback is
  noise on a premium, so it should be cutting winners far too early —
  the same unit-mismatch bug class as the ATR/premium defect already
  fixed.
- **Supporting evidence that looked damning:** measured premium % move
  captured at exit, `ema_rsi`, 123-day window:

  | Exit type | n | Median % captured |
  |---|---|---|
  | Stop-Loss Hit | 156 | **-16.01%** |
  | Trailing Stop-Loss Hit | 245 | **+5.87%** |
  | Partial Profit Booking | 147 | +17.24% |

  Losses run the full banded stop (~16-18%) while trailing exits cut
  winners at a median of +5.87% — a ~3:1 adverse asymmetry.
- **A/B test of the mechanism** (offset disabled entirely, leaving ATR
  trailing + banded SL + partial booking):

  | Metric | Current (0.35) | Mechanism OFF |
  |---|---|---|
  | Net profit | **₹247,201** | ₹195,956 (-21%) |
  | Profit factor | **1.38** | 1.33 |
  | Win rate | **72.1%** | 66.5% |
  | Max drawdown | 47.9% | **36.1%** |
  | Realized R:R | 0.53 | **0.67** |
  | Recovery factor | 5.16 | **5.43** |

- **Verdict: hypothesis half-confirmed, change REJECTED.** The R:R
  mechanism is real — winners genuinely do run further without the tight
  offset (0.53 → 0.67) and drawdown improves materially (47.9% → 36.1%).
  But net profit falls 21% and win rate falls 5.6pp, because the tight
  offset is not a miscalibration — it is deliberately harvesting a
  high-win-rate scalping edge. This is a **risk/return tradeoff, not a
  defect**, and it is the opposite of the ROI objective. `ema_rsi` is left
  unchanged.
- **Kept for the record because it reframes the drawdown item (#3):**
  ema_rsi's 47.9% drawdown is not a bug to be fixed, it is the *price* of
  its profit profile. Any future attempt to cut that drawdown should
  expect to give up roughly proportional profit unless the edge itself
  improves.
- **Re-tested and re-confirmed 2026-08-08 (#9),** on post-edge-trigger
  numbers and with the unit hypothesis now *measured* rather than
  asserted: premium elasticity is **70.8x**, so 0.35pp of premium is
  ~1.2 NIFTY points against the ~84 the rule was designed for. The
  mechanism is therefore proven — but neutralising it still costs more
  than it returns (net −17%, drawdown 20.84 → 32.27%). Same verdict,
  stronger evidence: **the tight offset is load-bearing for this
  strategy's edge.**

---

### 🔑 #2c — **The single highest-ROI lever, and it is already deferred by design**

Not a defect — a structural observation from the validation data that
directly answers "how do we improve ROI":

- **`ema_rsi` earns ₹230,108 of its ₹247,201 (93%) in ONE regime**
  (sideways, PF 1.71), while:
  - trending contributes only +₹30,264 at PF 1.14 with a 43% drawdown
  - low_volatility **loses** ₹18,293 (PF 0.31)
  - gap_day **loses** ₹5,785 (PF 0.92)
- Simply not trading the two losing regimes is worth **+₹24,078 (~+10%
  ROI)** on this strategy alone, before considering capital
  reallocation toward the sideways edge.
- The same shape holds across the suite (e.g. `enhanced_ai` is
  breakeven-to-positive everywhere except one concentrated week;
  `meta_agent_swarm` earns +₹62,638 in trending/sideways against
  -₹26,348 in gap/high-vol).
- **This is precisely what the Market Regime Detector + Strategy Router
  is for**, which is explicitly scheduled as a separate later
  architectural phase. Flagged here so the ROI case for that phase is
  quantified and waiting when it starts.

### ⚠️ Live risk-tier finding (decision needed, not a unilateral change)

`config/settings.json` does not set `enable_ai_filter`, so it defaults to
`False`, so `main.py` falls back to `confidence = 1.0`, which clears
`RiskConfig.high_confidence_threshold` (0.85) — meaning **every live
trade is sized at `high_confidence_risk_per_trade` = 3.5%, not the 1%
base tier.** All backtest figures in this document are at that 3.5%
tier, which is what produces both the large net-profit numbers and the
large drawdowns.

This is a leverage setting, not an edge setting: moving it changes
returns and drawdown roughly proportionally without improving
risk-adjusted performance. Raising ROI by leaving/raising leverage is not
a strategy improvement. Flagged for an explicit decision — it is a risk
parameter and out of scope for unilateral change.

---

### ❌ #5a — `drl_strategy` — verdict **REMOVE** (execution pending approval)

The only REMOVE verdict issued so far, and the evidence is conclusive
rather than statistical. Two independent faults, both proven by running
the code, not by reading it:

**Fault 1 — broken observation pipeline.** `compute_features()` reads
`'rsi'`/`'macd_hist'`/`'atr'`/`'vol_change'` off the dataframe via
`.get(col, default)`. Those columns do not exist on the raw OHLCV frame
`generate_signals()` receives, so every lookup silently returns its
hardcoded default. The model's observation is the constant
`[50, 0, 0, 0]` on **every bar of every market**. Verified directly: a
strong uptrend and a strong downtrend yield byte-identical feature
vectors.

**Fault 2 — collapsed model artifact.** I attached real,
correctly-computed RSI / MACD-histogram / ATR / volume-change features
(the fix the audit proposed) and re-tested. **It changed nothing.**
Output remained byte-identical across opposite markets and remained
100% one-directional. The trained model has degenerated to a single
action independent of input.

**Decisive test:** a **+7,500-point uptrend** and a **-7,500-point
downtrend** produced *identical* signal sequences — **286 BUY, 0 SELL in
both**.

- **What its production-validation result actually means:** 1,189 trades
  at PF 1.07 — the largest sample in the suite — is **not evidence of a
  market edge**. It is "buy a call on nearly every bar and let the Smart
  Exit Engine manage it." The apparent profit belongs to the exit
  architecture, not to this strategy. (Interesting corollary worth
  noting for the Router phase: the shared exit engine produces a
  positive expectancy even on effectively random, permanently-long
  entries.)
- **Why it cannot be improved with evidence-based changes:** the
  strategy-level fix was attempted and demonstrably failed. The only
  remaining remedy is retraining the RL model — which is *building a new
  strategy*, explicitly out of scope. My feature-pipeline change was
  therefore **reverted**, since it added per-call CPU cost for zero
  behavioural benefit.
- **Encoded as an executable spec** rather than prose:
  `test_drl_strategy_market_blindness.py` asserts what a *correct*
  strategy must do (respond to market data; be able to emit both
  directions), marked `xfail` so the suite stays green while the defect
  stays documented — and flips to XPASS automatically if the model is
  ever retrained properly. A third test pins the constant-observation
  behaviour directly, so fixing the pipeline causes a visible,
  intentional failure rather than passing silently.
- **Removal not executed.** Deleting/deregistering a strategy is a
  destructive, production-affecting change (it is explicitly registered
  in `main.py:128` as well as auto-discovered). Verdict and evidence are
  recorded; the removal itself awaits confirmation.

---

### ❌ #5b — `institutional_momentum` filter-activation hypothesis — TESTED, REJECTED, NO CHANGE MADE

Verdict: **IMPROVE by the letter of the criteria — but it is the
strongest strategy in the suite, and the criteria may be the wrong
gate. See the note at the end.**

**Audit findings re-verified against the live code path — all clean:**
- `donchian_high = high.shift(1).rolling(period).max()` — correctly
  shifted. **No look-ahead / self-reference** in the breakout condition
  (the classic Donchian defect). Verified directly.
- Bear filters correctly mirror bull filters throughout (EMA/VWAP
  inverted; ADX and volume shared, which is correct since both are
  direction-agnostic; RSI and candle-strength properly inverted).
- No non-discriminating "confirms both directions" layer of the kind
  found in `enhanced_ai`.

This strategy is genuinely well-constructed, which is consistent with it
having the best regime consistency in the suite.

**Finding: 7 of its 10 designed filters are OFF by default.** Only
`enable_ema_filter`, `enable_vwap_filter`, `enable_rsi_filter` default
to `True`. Session, volume, ADX, squeeze, extension, CPR and aggression
all default to `False` — with their thresholds (chop-aware ADX 20/25,
volume 1.2x/1.5x) fully designed in but never reached.

**Hypothesis (mechanism-based, not a sweep):** the two disabled filters
most core to an "institutional momentum breakout" thesis are ADX
(trend strength) and volume surge. Both directly target *false
breakouts* — the known failure mode of Donchian systems. Enabling the
strategy's *own* designed filters at its *own* designed thresholds
should raise signal quality.

**Result (123-day window):**

| Config | Trades | Net | PF | DD | Recovery | R:R |
|---|---|---|---|---|---|---|
| **BASELINE (3 filters)** | 319 | **₹78,397** | 1.22 | **16.74%** | **4.68** | 0.46 |
| + ADX | 284 | ₹64,826 | 1.21 | 18.28% | 3.55 | 0.46 |
| + Volume | 175 | ₹55,748 | 1.27 | 26.42% | 2.11 | 0.52 |
| + ADX + Volume | 158 | ₹59,975 | **1.32** | 22.47% | 2.67 | 0.54 |

**Verdict: REJECTED, strategy left unchanged.** Every filtered variant
raises the *ratio* metrics (PF, R:R) while degrading the things that
matter more: net profit (-24%), drawdown (16.7% → 22.5%) and recovery
factor (4.68 → 2.67, nearly halved). Fewer, "higher-quality" signals did
not translate into better risk-adjusted performance.

**⚠️ A metric-gaming trap, named explicitly:** the `+ADX+Volume` variant
reaches **PF 1.32, which clears this framework's own KEEP threshold of
1.30** — while being worse on net profit, drawdown *and* recovery
factor. Enabling it would have "achieved KEEP" by gaming the
classification criteria rather than improving the strategy. It was not
done, and the temptation is recorded so the next person does not fall
into it.

**Open question for the classification criteria themselves (decision, not
a unilateral change):** `institutional_momentum` fails KEEP on exactly
one criterion — PF 1.22 vs the 1.30 bar — while being:
- profitable in **4 of 5 regimes** (best in suite)
- lowest drawdown of any profitable strategy (**16.74%**)
- best recovery factor in the suite (**4.68**)
- free of any defect found in audit or live-code re-verification

A PF ≥ 1.30 gate may simply be the wrong discriminator for an
option-buying system whose realized R:R is structurally < 1 across
*every* strategy (0.45-0.67 suite-wide). Recovery factor and drawdown
arguably describe production-readiness better here. Changing the
criteria to let a strategy pass would be circular reasoning, so it is
flagged for an explicit decision rather than adjusted.

---

### ✅ #6 — `advanced_ai` re-entry churn — FIXED 2026-08-08 · Q2 violation resolved · still IMPROVE

**Two hypotheses tested and DISPROVEN before finding the real cause:**
1. *Gap-through / oversized losses.* Measured actual loss ÷ designed
   per-trade risk: `advanced_ai` 1.27x mean, 1.17x median. But
   `institutional_momentum` — which has a 16.7% drawdown — overshoots
   **more** (1.38x / 1.23x). Per-trade loss size is not the mechanism.
2. *Slippage artifacts.* Same measurement rules this out; only 2% of
   losses exceed 3x designed risk.

**Actual root cause, proven from production code + backtest evidence:**
the ML confidence score stays above threshold for long stretches —
measured **64% of all bars**, in 453 runs averaging 2.2 bars and
reaching 22. Both `main.py`'s live entry path and the harness are
**level-triggered** ("if flat and signal != 0, enter"), so every
stop-out inside a run was immediately followed by re-entry into the
same losing direction, for as long as the run lasted.

Comparison that isolates it: `institutional_momentum` signals on only
**5%** of bars (Donchian breakout is an *event*), giving it a natural
cooldown — and it has the lowest drawdown in the suite.

Measured consequences before the fix: **8.1 trades/day** (vs 2.9),
**52 of 122 days breaching the ₹5,000 daily-loss limit**, worst day
**-₹17,252**.

**Fix (smallest possible):** emit the signal only on the transition into
a run. A sustained run above the confidence threshold is ONE setup, not
one per bar — every setup the strategy detects is preserved, only the
churn is removed. The legacy backtest engine *already* edge-triggers
internally (`sig_vals[i-1] != 1`); this aligns the strategy's own output
with that semantics for the live path, which does not.

**Before/after (123-day window):**

| Metric | BEFORE | AFTER |
|---|---|---|
| **Q2 (DD ÷ explained)** | **2.95** ❌ | **1.32** ✅ |
| Max drawdown | 61.9% | **46.0%** |
| Recovery factor | 4.48 | **7.19** (best in suite) |
| Net profit | ₹277,101 | **₹331,195** (+19.5%) |
| Expectancy | ₹279.05 | **₹363.15** (+30%) |
| Profit factor | 1.24 | **1.32** |
| Win rate | 71.0% | 72.0% |
| Trades | 993 | 912 |
| Realized R:R | 0.51 | 0.51 (unchanged) |
| Max consecutive losses | 6 | 10 |

**Regime detail — the churn was concentrated where it hurt most:**

| Regime | PF before → after | Net before → after |
|---|---|---|
| gap_day | 0.83 → **1.23** | **-₹27,843 → +₹29,186** (+₹57k swing) |
| trending | 1.34 → 1.43 | ₹141,467 → ₹154,311 |
| sideways | 1.35 → 1.37 | ₹178,326 → ₹186,006 |
| low_volatility | 1.12 → 0.70 | +₹4,627 → -₹8,153 (28 trades) |
| high_volatility | 0.17 → 0.00 | -₹19,475 → -₹30,154 (5 trades) |

Gap days swung by ₹57k — exactly where repeatedly re-entering into
violent directional moves was most destructive. The two regressions sit
in thin samples (28 and 5 trades) and are not actionable evidence.

**Honest note on Q2:** it improved both because drawdown fell
(61.9%→46.0%) *and* because max consecutive losses rose (6→10), which
raises the "explained" denominator. The drawdown reduction and the
recovery-factor jump (4.48→7.19) are the unambiguous wins; Q2's
improvement is partly compositional and should be read alongside them,
not alone.

**Verdict: still IMPROVE.** It now passes N1, N2, Q1, Q2 and Q3, but
fails **N4 survivability** — 46.0% drawdown still exceeds the 30% gate
(recovering it requires +85%). A genuine, large improvement that does
not yet reach production-grade.

4 regression tests, including one asserting a genuine direction flip
(+1 → -1) still fires immediately rather than being swallowed as a
duplicate. Full suite: **427 passed, 2 xfailed**.

---

### ✅ #7 — `ema_rsi` re-entry churn — FIXED 2026-08-08 · **IMPROVE → KEEP** (live strategy)

**Mechanism tested, not assumed.** The same diagnostic battery that
proved the defect in `advanced_ai` was run here before any code changed.

*Disproven first:* per-trade loss overshoot (1.29x designed risk —
statistically indistinguishable from `institutional_momentum`'s 1.38x,
which has the lowest drawdown in the suite). Not the mechanism.

*Proven:* direct measurement of re-entry behaviour over the 123-day
window —

| | median gap after exit | re-entry ≤15min | of which SAME direction |
|---|---|---|---|
| **ema_rsi (before)** | **5 min (one bar)** | 64% | **63%** |
| institutional_momentum (best DD) | 20 min | 49% | 49% |

`ema_rsi` re-entered a median of **one bar** after the previous trade
closed, and 63% of those re-entries were in the *same direction as the
trade that had just stopped out*. The EMA/RSI/Supertrend condition holds
for long stretches (21% of bars, runs to 29), and both `main.py` and the
harness are level-triggered — so a stop-out inside a run was immediately
followed by re-entry into the same losing move.

**Fix:** identical to `advanced_ai` — emit only on the transition into a
run. Every setup preserved, only churn removed.

**Before/after (123 days):**

| Metric | BEFORE | AFTER |
|---|---|---|
| **Max drawdown** | 47.89% | **20.84%** (-56%) |
| **Recovery factor** | 5.16 | **9.70** (best in suite) |
| **Q2 (DD ÷ explained)** | **2.74** ❌ | **1.49** ✅ |
| Max consecutive losses | 5 | 4 |
| Win rate | 72.1% | 72.7% |
| Profit factor | 1.38 | 1.37 |
| Net profit | ₹247,201 | ₹202,041 (**-18%**) |
| Expectancy | ₹405.91 | ₹382.65 (-6%) |
| Trades | 609 | 528 |
| Realized R:R | 0.53 | 0.51 |

**Regime detail:**

| Regime | PF before → after | Net before → after |
|---|---|---|
| gap_day | 0.92 → **1.58** | **-₹5,785 → +₹24,642** (+₹30k) |
| sideways | 1.71 → 1.65 | ₹230,108 → ₹178,556 |
| trending | 1.14 → 1.13 | ₹30,264 → ₹23,482 |
| high_volatility | 1.55 → 0.77 | +₹10,907 → -₹4,616 (13 trades) |
| low_volatility | 0.31 → 0.25 | -₹18,292 → -₹20,024 (13 trades) |

Same signature as `advanced_ai`: gap_day swings hardest positive
(+₹30k), because repeatedly re-entering a violent directional move is
where churn is most destructive.

**Verdict: IMPROVE → KEEP.** Now passes every gate — N4 survivability
(20.84% ≤ 30%) and Q2 (1.49 ≤ 2.0) were the two blockers and both
cleared.

**The honest trade-off:** this costs **18% of net profit** (₹247k →
₹202k) to more than halve drawdown (47.9% → 20.8%). Risk-adjusted it is
unambiguous — recovery factor nearly doubled to 9.70, the best in the
suite — and it is the difference between production-ready and not under
the criteria. But it *does* reduce headline ROI, which conflicts with a
pure-ROI objective. Flagging explicitly rather than burying it: if
maximum ROI is preferred over survivability, this fix is the trade to
revisit, though the pre-fix 47.9% drawdown fails the survivability gate
for a reason (recovering it requires +92%).

**Test-suite note:** two pre-existing oracles
(`test_ema_rsi_signals_setitem_regression.py`,
`test_incremental_column_insert_regression.py`) encoded the old
level-triggered output. They exist to pin the CPU-livelock rewrites, not
to freeze signal semantics, so both oracles were updated to model the
deliberate edge-trigger — with a comment saying exactly that, so the
change is not mistaken for weakening a regression test. 4 new
edge-trigger tests. Suite: **431 passed, 2 xfailed**.

---

### 🔑 #8 — Trailing activation is archetype-dependent — MEASURED, **not implemented**, needs an architecture decision

**The most consequential finding of the improvement programme, and a
change I deliberately did NOT ship.**

**Root cause (proven):** `SmartExitEngine` arms its percentage trailing
stop at `trailing_activation_pct` = 1.0% profit — effectively
immediately. Partial Profit Booking fires at 1:1 reward:risk (~15-18% of
premium for typical bands). So trailing **pre-empts partial booking on
most winners**. Measured on `ema_rsi` post-edge-trigger:

| Exit reason | n | Median premium move captured |
|---|---|---|
| Partial Profit Booking | 131 | **+17.54%** |
| Trailing Stop-Loss Hit | 218 | **+5.70%** |
| Stop-Loss Hit | 137 | -16.22% |

Winners are cut at roughly a third of what they reach when allowed to
run — the direct cause of the sub-1.0 realized R:R seen suite-wide.

**Hypothesis tested:** arm trailing only once the position has earned
its own risk unit (1R), so the banded stop governs below 1R and trailing
governs above it. Anchored to the position's own risk, not an arbitrary
number.

**Result — it does NOT generalize. It splits by strategy archetype:**

| Strategy | Archetype | Net | PF | DD | Recovery | R:R |
|---|---|---|---|---|---|---|
| institutional_momentum | trend | **+106%** ₹78k→₹161k | 1.22→**1.43** | 16.7→**11.0%** | 4.68→**14.68** | 0.46→0.73 |
| ema_rsi | trend | **+23%** ₹202k→₹248k | 1.37→**1.45** | 20.8→23.6% | 9.70→**10.51** | 0.51→0.85 |
| buy_the_dip | mean-reversion | **−73%** ₹74k→₹20k | 1.25→1.05 | 22.1→**30.7%** | 3.36→**0.66** | 0.46→0.74 |
| ultra_meta_dip_swarm | mean-reversion | **−53%** ₹58k→₹27k | 1.24→1.09 | 25.0→**31.8%** | 2.32→**0.86** | 0.43→0.76 |

**Why this is mechanistically coherent, not noise:** a trend strategy's
edge *is* the sustained move, so delaying the trailing stop captures it.
A dip-buying strategy's edge is a quick mean-reversion bounce — holding
for 1R before trailing gives the bounce back. R:R improved for **all
four** (0.43-0.51 → 0.73-0.85), but for the dip strategies the win-rate
collapse outweighed it, pushing both **past the 30% survivability gate
and out of KEEP**.

**Why it was not shipped:** `trailing_activation_pct` is a **shared**
`SmartExitEngine` parameter driven by a single global
`settings["trail_trigger"]`. There is no per-strategy override today.
Applying it globally on `ema_rsi`'s evidence alone would have destroyed
two currently-production-ready strategies. This is exactly the failure
mode the "test generalization before shipping" discipline exists to
catch.

**What implementing it properly requires (an architecture decision, not
a parameter tweak):**
1. A per-strategy trailing-activation override — e.g. an optional
   `TRAILING_ACTIVATION_PCT` module constant each strategy may declare,
   read by `main.py` and the harness, defaulting to today's value so
   every non-declaring strategy is bit-identical. Opt-in, zero blast
   radius.
2. Ideally anchored to the position's **actual** initial risk rather
   than a percentage proxy — which also fixes audit §2.3 (partial
   booking currently recomputes its reward:risk ratio against a stop
   that trailing may already have moved). That needs `initial_risk_pct`
   captured on `Position` at entry.

**Estimated value if implemented for the two trend strategies only:**
roughly **+₹128k** over the 123-day window (institutional_momentum
+₹82.8k, ema_rsi +₹45.6k) with *both* drawdowns still inside the gate —
and `institutional_momentum`'s drawdown actually *improving* to 11.0%
with a recovery factor of 14.68, which would make it comfortably the
strongest strategy in the suite.

**Status: measured and documented, awaiting a decision on the
per-strategy override.** Not implemented unilaterally because it changes
shared exit infrastructure used by every strategy and by live trading.

---

### ✅ #9 — `ema_rsi` exit-quality audit → partial-booking runner re-baseline — FIXED 2026-08-08

A dedicated exit-quality and trend-capture audit of `ema_rsi`, run
against production-architecture data before any change was considered.
It produced one shipped fix, one rejected hypothesis, and one finding
that reframes what this strategy actually is.

**Method.** `validation_harness/exit_quality.py` + `run_exit_quality.py`
re-price every simulated trade's full option-premium path — during the
hold *and after the exit* — and measure MFE, capture %, give-back,
post-exit continuation at +5/15/30/60 min, premature-exit rate, trend
capture, and per-mechanism trailing behaviour. Contract reconstruction is
exact (it replays the harness's own `select_option` call rather than
parsing the symbol, which mis-priced 106 of 528 legs on monthly
expiries), and fidelity is asserted on every leg before any conclusion is
drawn: **528/528 legs reproduced with 0.0 premium error.**
`validation_harness/exit_replay.py` then re-runs only `SmartExitEngine`
over those exact paths with entries held fixed; it reproduces the
harness bit-for-bit (net ₹202,040.49616460118, identical reason mix).

**Audit findings** (123 days, 397 positions / 528 legs) —
`validation_harness/results/exit_quality_ema_rsi.md`:

| Finding | Measurement |
|---|---|
| Exit mix (positions) | trailing-offset **54.4%**, stop 34.5%, EOD 10.3%, ATR trail **0.5%**, target **0%** |
| Capture of the in-trade move | median **63.1%**; trailing-offset exits **68.1%** |
| Trend capture vs the day's full available move | median **17.7%**; on days with ≥30% premium available, **14.3%** |
| Premature exits (price exceeded the exit within 60 min) | **84.3%** of all positions; median missed upside **+8.85%**, p90 **+69.5%** |
| Post-exit continuation after a trailing exit | +3.6% at 15 min, +6.0% at 30 min, **+9.0% at 60 min** |
| Partial-booking runners | **75.6%** closed by the trailing offset, median survival **2 bars** |
| `Profit Target Hit` | **0** — inert by design (`target=0.0`), confirmed not silently firing |

**Root cause, quantified.** `trailing_offset_pct` is a give-back in
percentage points of P&L. Its value (0.35 — the engine default *and*
`config/settings.json`) was carried into `SmartExitEngine` by commit
`7e0ec15` from `backtesting_engine/run.py`, which applies it to the P&L %
of the **underlying index** ("Give 0.35% room so we don't exit too early
on volatility"). `SmartExitEngine` only ever manages **option** positions.
Measured premium elasticity over 2,161 held bars is **70.8x**, so:

- 0.35pp of premium = **0.0049% of the index** ≈ **1.2 NIFTY points**,
  about **70x tighter than the rule's own stated design intent** (~84
  points).
- **92.4%** of individual 5-minute bars move the premium by more than the
  entire allowance on their own — the threshold is below one bar's noise
  floor.
- Consequently it is not a trailing stop but "exit on the first close
  below the peak": **70.1%** of offset exits fired on exactly that bar,
  and the realised give-back is 9x the nominal threshold simply because a
  5-minute bar cannot resolve 0.35pp. Live polls at ~1s, so **live is
  worse than the harness shows.**
- The engine's correctly-scaled ATR trailing stop (give-back in the
  option's own premium ATR) fired **2 times in 528 legs** — it is dead
  code, permanently pre-empted.

**Rejected: floor the offset at the ATR distance** (no new constant —
reuses `atr_multiplier`/`current_atr`). The fixed-entry replay screen
liked it (+23% net, sequence drawdown 46.3→39.1). The **full 123-day
day-isolated run did not**: net ₹202,040 → ₹167,518, PF 1.37 → 1.31,
**max drawdown 20.84% → 32.27%**, recovery 9.70 → 5.19. Holding entries
fixed had hidden that longer holds change which later signals become
trades and how they are sized. **The screen is a filter, never a
verdict** — that is now written into `exit_replay.py`'s docstring.
Independently corroborates #2b, on post-anti-churn numbers.

**Shipped: re-baseline the runner's peak at partial booking**
(`exit_engine.py`, one assignment per branch). Partial booking already
re-baselines the position's *risk* — stop to breakeven — but left
`max_pnl_pct` at the peak the **booked half** had reached. Since section
4 returns before section 5 updates the peak, the runner was born in
give-back against a peak it never kept, and the 0.35pp allowance let the
next downtick close it. A state-consistency defect, not a preference — so
applied to every strategy rather than opted into per strategy.

**Full 123-day re-validation, every strategy with a cached baseline**
(`validation_harness/results/ab_validation.md`):

| Strategy | Net | PF | Max DD | Recovery |
|---|---|---|---|---|
| ema_rsi | ₹202,040 → **₹211,316** | 1.37 → **1.39** | 20.84 → **19.01%** | 9.70 → **11.12** |
| institutional_momentum | ₹78,397 → **₹88,511** | 1.22 → **1.25** | 16.74 → **15.12%** | 4.68 → **5.85** |
| enhanced_ai | −₹16,160 → **₹14,711** | 0.98 → **1.02** | 55.31 → **46.97%** | −0.29 → **0.31** |
| MARL_Ultra | ₹130,399 → **₹149,120** | 1.10 → **1.12** | 41.26 → **40.34%** | 3.16 → **3.70** |
| buy_the_dip | ₹74,102 → ₹68,485 | 1.25 → 1.23 | 22.05 → 22.05% | 3.36 → 3.11 |
| ultra_meta_dip_swarm | ₹58,036 → ₹53,892 | 1.24 → 1.22 | 24.99 → 25.50% | 2.32 → 2.11 |

Four improve on return **and** drawdown. The two mean-reversion
strategies give up ~7% of net — their edge is a fast bounce, so the
premature runner exit suited them by accident — but **neither leaves its
drawdown gate**, unlike every previous trailing change tested (#2b, #8),
which pushed them to 30.7%/31.8%.

For `ema_rsi` the gain is **entirely on the loss side**: gross profit
−₹2,264 (flat), gross loss **−₹11,540**. The runner now survives to its
breakeven stop instead of being dumped mid-move. Best regime improvement
is `trending` (₹23,482 → ₹31,506, DD 35.40 → 30.82%), which is what a
trend-capture repair should look like.

**Reframing finding — `ema_rsi` is not primarily a trend strategy.**
Trend capture is 14-18% and 84.3% of exits are premature, yet the
strategy is the suite's most profitable. Its P&L is produced mainly by a
fast, high-win-rate profit-take that the exit engine supplies by
accident, not by the EMA/RSI/Supertrend signal riding moves. Two
independent attempts to make it capture trends (#2b and this audit's
rejected candidate) both raised realised R:R and both cost net profit or
drawdown. **Its 20.8% drawdown is the price of that profile, not a bug** —
consistent with #2b's conclusion. Any future ROI work here should target
the entry edge, not the exit.

**Tests:** 8 new regression tests
(`test_partial_booking_runner_rebaseline.py`), verified to FAIL with the
fix reverted and pass with it, including tests pinning what must *not*
change (booking ratio, quantity, breakeven stop, never-booked positions).
Suite: **439 passed, 2 xfailed.**

**Pre-existing flake noted, not caused here:**
`test_option_premium_atr_integration.py::test_no_duplicate_candle_growth_from_repeated_same_second_ticks`
builds 20 ticks from `time.time()` spanning 19s, so it fails whenever the
run starts within 19s of a minute boundary (~32% of runs).

---

### ✅ #10 — `ema_rsi` entry-quality audit → validation was measuring the wrong entry path — FIXED 2026-08-08

A deep entry-quality audit of `ema_rsi`. It produced **no strategy
change** — every candidate the data was asked about came back negative —
and one genuine defect that invalidates the input to every verdict in
this document.

**Method.** `validation_harness/entry_quality.py` + `run_entry_quality.py`.
The headline measure is deliberately **exit-independent**: for each
position, walk the premium path forward and record which comes first,
**+1R or −1R**, where R is the real `resolve_initial_stop` distance the
live system risks. That asks only "did the market go the signalled way
before it went against us, by the size we were risking" — a bad exit
cannot be mistaken for a bad entry. `false entry` = loss-first. Signal
reconstruction reproduces the day-isolated 30-day warm-up windowing and
is verified before use: **397/397 entries land on an independently
reconstructed signal of the matching direction.**

**Entry quality as measured** (123 days, 397 positions) —
`validation_harness/results/entry_quality_ema_rsi.md`:

| Measure | Result |
|---|---|
| win-first / loss-first / neither | 51.1% / **37.8%** / 11.1% |
| right-first among resolved | **57.5%** (edge **+15.0pp**) |
| premium never rose at all after entry | **10.6%** |
| MFE / MAE, median | **+1.58R** / **−1.13R** |
| rally coverage (runs ≥0.30% with a position open) | **40.9%**; among covered, **32.3%** of the run held |

The entry has a real, modest edge. What it does **not** have is any way
to tell a good setup from a bad one.

**Negative result 1 — the confirmation stack does not discriminate.**
All three conditions must hold for a signal, so none can be tested by
presence; what can be tested is degree. None is monotone:

| Component | Best bucket | Worst bucket |
|---|---|---|
| RSI margin past threshold | 0-2 (**+31.9pp**) | 15+ (+2.3pp) |
| EMA separation | 0.05-0.1% (**+35.2pp**) | 0.4%+ (0.0pp) |
| Supertrend leg age | 2-3 bars (+33.3pp) | 0-1 fresh flip (+7.9pp) |
| Price stretch past fast EMA | 0-0.05% (+31.8pp) | 0.1-0.2% (**−1.5pp**) |
| Volume vs 20-bar average | no pattern | no pattern |

A composite scored from the strategy's own three conditions is
**inverted**: score 0 → +43.4pp edge and ₹88,847 net; score 2 → +2.6pp;
score 3 → −₹2,537. **Stronger setups by the strategy's own criteria
perform worse.** There is therefore no threshold to tune and no
confirmation filter to add that the evidence supports — the obvious
"improvements" are all foreclosed.

**Negative result 2 — the CE/PE asymmetry is an artifact.** Headline:
CE 203 trades net −₹1,926 (+4.4pp edge), PE 194 trades net +₹203,966
(+22.7pp). Controlling for the direction the index actually moved that
day collapses it — aligned trades win and misaligned trades lose,
symmetrically:

| Day | CE | PE |
|---|---|---|
| up day | +17.2pp, n=134 | −27.6pp, n=29 |
| down day | −34.5pp, n=29 | +37.9pp, n=145 |

The window drifted −1.62% (with a −9.94% March), so far more PE
positions were opened on days that went the PE way. **Acting on the
headline split would be fitting the window's drift.**

**Negative result 3 — the misses are not a defect.** Of 225 uncovered
runs: **61.8% had no setup at all** (the strategy's philosophy, not a
bug), **28.0% happened while holding an opposite-direction position**
(would require reversal logic — a philosophy change), **8.4% signalled
but were blocked**, and **1.8% were suppressed by the edge-trigger**.
All 67 risk-gate rejections are `Daily loss limit exceeded` across 21
days — a risk control working as designed. **The anti-churn fix (#7) is
not costing rallies and the data gives no reason to weaken it.**

**The actual defect — the validated entry path is not production's.**
`registry.run_strategy()` applies four institutional filters gated on
`enable_*_filter`. `config/settings.json` has **all four ENABLED**. The
harness called it with `settings={}`, so all four were **OFF** in every
validation number ever produced. Separately `main.py` copies
`max_trades_per_day` (3) into `risk_manager.config.max_trades_per_day`;
the harness left the cap at 0 = unlimited. Production takes **70.8%
fewer signals** (725 → 212 signal bars) than the strategy that was
measured and given its KEEP verdict.

The overlap was checked rather than assumed: of 39 keys in
`settings.json`, the harness path reads 12, and the other 8
(`option_sl_*`, sizing, ITM offset) produce **bit-identical** stops and
sizing to the harness's own defaults across the whole premium range. The
entry path is the only behavioural delta.

**Fix:** `validation_harness/production_settings.py` loads the live
settings; `harness.py` honours the daily cap with `main.py`'s exact key
precedence (the file carries BOTH `max_trades_per_day` and
`max_daily_trades`, so reading the wrong one models a cap production does
not enforce); `run_validation.py` defaults to `--entry-path production`
and stamps the path into every report, with `--entry-path legacy`
reproducing every earlier run. **No strategy code was touched.**

**Before/after, `ema_rsi`, same window, same code:**

| Metric | Legacy (validated) | Production (actual) |
|---|---|---|
| trades / positions | 522 / 392 | 194 / 145 |
| net profit | ₹211,316 | **₹81,922** |
| expectancy | 404.82 | **422.28** |
| profit factor | 1.39 | **1.42** |
| max drawdown | 19.01% | **15.24%** |
| recovery factor | 11.12 | 5.38 |
| win rate | 72.60% | **75.30%** |
| realised R:R | 0.53 | 0.47 |
| false-signal rate | 37.50% | **35.86%** |
| first-touch edge | +13.78pp | **+14.48pp** |
| never-rose | 10.71% | 11.03% |
| rally coverage | 40.94% | 23.36% |
| held % of covered run | 32.29% | 22.22% |
| Q2 violated | No | No |
| **verdict** | KEEP | **KEEP** |

The production filters are mildly **quality-positive per trade** and
heavily **volume-negative**: better PF, win rate, expectancy, drawdown
and false-signal rate, at 61% less profit and roughly half the rally
coverage. Whether that trade is worth making is a **risk-appetite
decision for the operator, not a code change** — both configurations
pass the readiness framework, so `ema_rsi` remains KEEP either way.

**Open follow-up, flagged not actioned:** every other strategy's numbers
and verdict in this document were produced on the legacy path. They are
all measurements of a configuration production does not run and should
be regenerated with `--entry-path production` before any further
verdict is relied on. Not done here — the brief was `ema_rsi` only.

**Tests:** 10 new regression tests
(`test_validation_entry_path_fidelity.py`), verified to fail with the
cap wiring reverted. Suite: **449 passed, 2 xfailed.**

---

### ❌ #11 — `ema_rsi` entry-filter and trade-cap ablation — TESTED, **NO CHANGE MADE**, verdict KEEP

The obvious follow-on to #10: production runs four institutional filters
and a 3-trade daily cap that had never been measured. Every one of them
was audited individually and in combination against the production
baseline. **No configuration change survived the evidence bar, so none
was made.** Recorded in full because the negative result is the deliverable.

**Baseline (production, `config/settings.json`):** 145 positions, net
₹81,922, expectancy 422, PF 1.42, max DD 15.24%, recovery 5.38, win 75.3%,
R:R 0.47, Q2 1.45, false-signal 35.9%, first-touch edge +14.5pp, rally
capture 23.4%. **KEEP.**

**Method.** `run_filter_ablation.py` (17 full 123-day day-isolated runs)
and `run_filter_significance.py`. One variable at a time: leave-one-out
from production, each filter alone against the unfiltered path, and the
cap swept independently. The rally set (381 sustained underlying moves)
is computed once and identical for every configuration, so only coverage
moves.

**What the headline numbers said** — removing `cpr` improved *every*
axis (net +₹27,759, PF +0.05, DD −0.79pp, recovery +2.21, false-signal
−1.9pp, edge +2.5pp, rally +3.4pp), and removing `cpr` + `aggression`
without the cap looked spectacular (net ₹197,009, PF 1.55, recovery
12.23, edge +19.4pp, rally 33.3%). Monthly splits looked consistent, and
leave-one-month-out kept the `cpr` gain positive in all six months.

**What killed it.** Three tests, run symmetrically over all four filters
so nothing was selected after the fact:

| Filter | day-level bootstrap P(Δ>0) | blocked-cohort P(mean>0) | signal-population verdict |
|---|---|---|---|
| squeeze | 38.9% | 48.2% (n=79) | **rejected signals genuinely worse at every threshold** |
| extension | 32.7% | 63.0% (n=13) | no effect, n too small |
| cpr | 77.9% | 86.0% (n=32) | **sign flips with threshold** |
| aggression | 78.8% | 71.8% (n=85) | **sign flips with threshold** |

Every 95% CI for a *change* straddles zero. `ema_rsi` trades ~145-190
positions over 123 days on heavy-tailed option P&L: the single worst day
(−₹23,060) and best day (+₹22,979) each rival the entire ₹27,759 `cpr`
effect, which moved only 26 of 123 days. 78-86% confidence is suggestive,
not defensible.

**The one thing that IS established.** The best-powered test — all 725
signals the unfiltered strategy emits, scored on the underlying's own
first touch of ±T — found `squeeze` is doing real work:

| Threshold | rejected (n=250) | allowed (n=475) | difference | 95% CI | P(rejected worse) |
|---|---|---|---|---|---|
| ±0.15% | −5.2pp | +11.2pp | −16.4pp | [−29.6, −3.1] | 99.2% |
| ±0.21% | −4.8pp | +13.7pp | −18.5pp | [−30.6, −6.0] | 99.7% |
| ±0.30% | −5.2pp | +7.6pp | −12.8pp | [−23.2, −2.5] | 99.3% |

Squeeze rejects signals whose edge is **negative** while passing signals
with strongly positive edge — stable in sign and magnitude across every
threshold, CI excluding zero at all three. It is the only component of
the entry stack with proven value, and the ablation's own headline
(removing it costs net, PF, DD, edge and 6.1pp of first-touch edge)
agrees. **Do not remove it to buy trade count.** For `cpr` and
`aggression` the same test flips sign between thresholds, which is what
"no reliable effect" looks like.

**The daily cap.** It binds on **7 of 123 days** (1.59 trades/day). The
sweep is non-monotone — cap 3 ₹81,922, cap 4 ₹77,342, cap 5 ₹93,151,
cap 6 ₹98,239, unlimited ₹92,023 — which is the signature of noise, not
of a level worth choosing. Removing it entirely looked better (+₹10,101,
DD −0.24pp) but the monthly split is 3-3. **A nearly-inert risk control
should not be loosened for an effect this size.**

**Rejected on risk, separately from significance.** Dropping `aggression`
as well as `cpr` (config E) more than doubled net profit, but: Q2 rose
0.65 → 1.53, and the same pair *with* the cap (config C) hit DD 20.80%
and Q2 1.98 — a hair under the gate. A 4.7pp drawdown swing from the cap
alone, in a configuration where the cap is otherwise nearly inert, is
fragility. March also flips from +₹16,108 to −₹12,556. That is buying
profit with disproportionate and unstable risk.

**Remaining risks if this is revisited.** The `cpr` improvement, though
not significant, is concentrated in `sideways` (+₹41,591 of the +₹27,759
total) and is *offset* by `high_volatility` going +₹16,231 → −₹6,829 on
a 6-7 trade sample. Any future re-test should treat the high-volatility
regime as unsampled rather than as evidence either way.

**Verdict: KEEP the production configuration unchanged.** The honest
summary is that at 123 days this strategy cannot resolve filter-level
differences of the size on offer. The way to settle `cpr` is more
evidence — a longer window or forward paper-trading of the
`cpr`-disabled configuration — not a decision on 86% confidence.

**Tests:** 6 new regression tests
(`test_institutional_filter_isolation.py`) pinning the property the whole
study rests on — each `enable_*_filter` flag controls exactly one mask,
filters compose as an intersection, leave-one-out changes only the
dropped filter, and string `"true"` behaves like `True` so the JSON and
dashboard paths cannot diverge. Suite: **455 passed, 2 xfailed.**

---

### ✅ #12 — `institutional_momentum` took ZERO trades in production — FIXED 2026-08-09 · verdict **REMOVE** on the production configuration

The first strategy audited on the production entry path after #10 exposed
that every earlier verdict was measured on the legacy path. The audit did
not find a weak strategy. It found that this strategy **cannot trade at
all** as production is configured, and had never been able to.

**Method.** `validation_harness/run_strategy_audit.py` — a strategy-
agnostic version of the #9/#10 batteries (first-touch ±1R, MFE/MAE,
entry timing, exit mix, premature exits, trailing behaviour, rally
capture, missed-opportunity causes, sizing/stop bands, risk-gate reasons,
regime split, duty cycle and churn), run over both entry paths.

**The finding: 0 trades, 0 candidate signals, across all 123 days.**
Not a crash, not an exception — the engine evaluates every bar, logs
nothing unusual, and takes no position, ever.

**Root cause — one flag with two opposite meanings, proven by identity
rather than by statistics:**

| Layer | Reads | Semantics |
|---|---|---|
| `momentum_strategy.generate_signals:449,515` | `enable_squeeze_filter` | **REQUIRES** a recent squeeze — rejects bars without one ("Not a fresh breakout") |
| `shared/filters/institutional.py:155-158`, applied on top by `registry.run_strategy` | `enable_squeeze_filter` | **VETOES** a recent squeeze — `bullish & ~squeeze_mask` |

Both compute the same mask from the same formula — verified **0
disagreeing bars out of 9,220**. So the surviving set is `A & ~A`:
**provably empty for any input whatsoever**, not merely empty on this
sample. `config/settings.json` has the flag on.

Measured, isolating each filter over the window:

| Filter enabled alone | signals surviving (of 179) |
|---|---|
| **squeeze** | **0** |
| extension | 179 |
| cpr | 179 |
| aggression | 179 |

The other three are the **same** sign in both layers, so the second
application rejected nothing — which is exactly why only squeeze
annihilated the strategy, and is itself corroborating evidence for the
mechanism.

**Why this is severe beyond one strategy:** `institutional_momentum` is
`main.py`'s **default** `active_strategy` (`main.py:318`, plus three
`.get(..., "institutional_momentum")` fallbacks at 949, 1158, 1371). A
missing or key-less `settings.json` runs a strategy that structurally
cannot take a trade, while reporting healthy at every level. That is the
fifth occurrence of this project's recurring "looks alive, does nothing"
failure class (2026-08-06 tick staleness, EOD-entry-cutoff artifact,
`active_strategy` typo silent-retry, MARL Capital-Protection deadlock,
and this).

**Fix (smallest that addresses the mechanism):** a strategy may declare
`OWNS_INSTITUTIONAL_FILTERS`; `registry.run_strategy` then skips those
filters for that strategy only. The global filter's own behaviour is
**deliberately unchanged** — #11 proved the squeeze veto is the one entry
filter with a statistically defensible effect for `ema_rsi` (99%+ across
every threshold), so flipping its sign globally would destroy a proven
control to fix an unrelated strategy. Neither reading is wrong; applying
both to one signal is.

**Blast radius, measured not asserted** — every registered strategy run
on the production settings, pre-fix vs post-fix signals:

| | pre | post |
|---|---|---|
| institutional_momentum | 0 | **179** |
| ema_rsi | 212 | 212 (bit-identical) |
| advanced_ai, buy_the_dip, drl_strategy, ema_crossover, enhanced_ai, marl_strategy, meta_agent_swarm, ultra_meta_dip_swarm, premium | — | **all bit-identical** |

10 of 11 strategies unchanged to the bar. The legacy path for
`institutional_momentum` is also unchanged (317 legs, ₹88,511, PF 1.25,
DD 15.12%, recovery 5.85 — identical before and after), so every earlier
number in this document still stands.

**Before/after, 123-day production path:**

| Metric | BEFORE (as shipped) | AFTER (fix) |
|---|---|---|
| **Trades / positions** | **0 / 0** | **149 / 116** |
| Candidate signals | 0 | 133 |
| Net profit | ₹0 | −₹8,867 |
| Profit factor | — | 0.95 |
| Max drawdown | — | 42.34% |
| Q2 | — | 2.42 |
| Recovery factor | — | −0.21 |
| Win rate | — | 67.8% |
| Realised R:R | — | 0.45 |
| Max consecutive losses | 0 | 5 |
| False-signal rate | — | 40.5% |
| First-touch edge | — | +5.2pp |
| Rally capture | — | 20.7% |
| **Verdict** | IMPROVE (0 trades — unmeasurable) | **REMOVE** |

**⚠️ Read this correctly — the fix did not make the strategy lose money.**
The fix made an always-latent configuration *visible*. Before it, the
production numbers did not exist to be measured; the strategy was not
safe, it was silent. The losing performance is a property of the
production filter configuration, not of the change.

**Material risk change to flag explicitly:** with `active_strategy` still
`ema_rsi`, live behaviour today is unaffected. But if anyone switches to
`institutional_momentum` — or `settings.json` goes missing and the
default applies — the engine will now **trade** a configuration measured
at PF 0.95 / 42.3% drawdown / REMOVE, where previously it would have
traded nothing. Enabling this strategy is an operator decision and the
evidence says: do not, in its current configuration.

**Production-vs-legacy is a configuration inversion.** The legacy path is
the strategy's *designed* defaults (EMA/VWAP/RSI trend confirmations ON,
the four institutional filters OFF). Production is the exact inverse:

| | legacy = designed | production = as configured |
|---|---|---|
| enable_ema/vwap/rsi_filter | True (defaults) | **False** |
| squeeze/extension/cpr/aggression | False (defaults) | **True** |
| net / PF / DD | ₹88,511 / 1.25 / 15.12% | −₹8,867 / 0.95 / 42.34% |
| first-touch edge | +17.8pp | **+5.2pp** |
| false-signal rate | 34.0% | **40.5%** |
| verdict | **KEEP** | **REMOVE** |

The first-touch edge collapse is exit-independent, so this is genuinely
an entry-quality difference and not an artifact of exits or sizing.

**Audit detail worth carrying forward** (full report:
`validation_harness/results/audit_institutional_momentum.md`; the
zero-trade baseline is preserved as `..._BEFORE.md`):

- **Churn: hypothesis DISPROVEN.** The `ema_rsi`/`advanced_ai` level-
  trigger mechanism does **not** exist here. Median exit→next entry is
  **100 minutes** (vs `ema_rsi`'s pre-fix 5), duty cycle 1.9%, and only
  13.4% of signals repeat the previous bar. Donchian breakout is an
  *event*, not a level. **No anti-churn work is warranted.**
- **Misses are not a defect:** of 302 uncovered rallies, **98.7% had no
  setup at all**; 3 were signalled-but-blocked and 1 was blocked by an
  opposite position. Nothing addressable.
- **Losses concentrate in `trending`** — 43 trades, −₹50,343, PF 0.43,
  DD 50.3% — which is mechanistically backwards for a momentum-breakout
  system and is the strongest single pointer to the missing EMA/VWAP
  trend-structure confirmations.
- **Entry timing:** 12:30-14:00 is −₹43,600 on 31 trades at −35.5pp
  first-touch edge, against +₹30,830 for 11:00-12:30. Suggestive only —
  31 trades cannot carry a session gate, and the strategy already ships
  a `session_filter` for this that is off.
- **Exits:** 81.9% premature, median trend capture 13.4%, `stop` legs
  −₹136,163 against `trail_offset` +₹117,669. The same exit-architecture
  signature #9 documented for `ema_rsi`; not specific to this strategy.
- **Risk controls intact:** daily-loss circuit breaker fired on 6 days,
  `Max trades per day reached (3)` on 5 — both working as designed. Mean
  0.94 trades/day, max 3.

**Next experiment, measured but NOT shipped.** Restoring the strategy's
three designed trend filters on top of the production flags:

| | production as-configured | + EMA/VWAP/RSI restored |
|---|---|---|
| legs | 149 | 75 |
| net | −₹8,867 | **+₹3,043** |
| PF | 0.95 | 1.03 |
| max drawdown | 42.34% | **18.90%** |
| Q2 | 2.42 | 2.70 (worse) |
| verdict | REMOVE | **IMPROVE** |

Directionally strong on drawdown, but it does **not** reach KEEP, halves
an already-small sample, and worsens Q2. Per this project's own rules
that is suggestive, not defensible — settling it needs the #11
significance methodology (day-level bootstrap, leave-one-month-out) and
it is a `settings.json` change, i.e. an operator decision, not a code
one. **Not implemented.**

**Tests:** 7 new regression tests
(`test_registry_owned_filter_skip.py`) — the `A & ~A` annihilation on a
squeeze-requiring strategy, the real strategy end-to-end under the real
production flags (with explicit guards so it cannot pass vacuously on a
fixture that produces no signals), ownership matching what the strategy
actually consumes, and three pinning what must **not** change:
undeclared strategies still get every global filter, undeclared filters
still apply, and ownership is inert when the flag is off. Verified to
fail with the fix reverted (4 of 7 fail; the other 3 pin unchanged
behaviour and correctly stay green).
**Suite: 422 passed, 2 xfailed.** (7 test files — all `api_bridge`-
importing — cannot be collected in this local env: setuptools 83 dropped
`pkg_resources`, which `fyers_apiv3` still imports. Confirmed
pre-existing by reproducing it with the change stashed; unrelated to
strategy code, and CI installs from `requirements.txt` on Python 3.11
where it resolves.)

**Verdict: REMOVE on the production configuration, KEEP on the designed
configuration** — and the gap between those two is a settings decision,
not a strategy defect. Removal is **not** executed: as with #5a, that is
a destructive production-affecting change awaiting confirmation, and here
there is a cheaper first move (correct the configuration inversion, then
re-audit).

---

### #3 — Cross-cutting: drawdown is the single biggest blocker to any KEEP verdict
- **Strategies:** advanced_ai (61.9%), enhanced_ai (61.6%), ema_rsi
  (47.9%), marl_strategy (41.3%), meta_agent_swarm (40.2%), drl (39.2%)
- **Root cause (partly instrumentation, partly real):** the harness found
  a real mechanism — a ₹49.99 premium (₹20-50 band, ~₹8 intended stop)
  crashing to ₹8.97 in a single simulated 5-minute bar near expiry. Live
  ~1-second premium polling would very likely catch that far earlier, so
  these drawdown figures are inflated for cheap short-dated contracts.
  **But** the underlying exposure is real: the premium-banded SL assumes
  a stop can actually be filled near its trigger, which is least true for
  exactly these contracts.
- **Proposed investigation (not yet a fix):** quantify how much of each
  strategy's max DD comes from sub-₹50-premium, ≤1-DTE contracts. If
  concentrated there, the fix is a minimum-premium or minimum-DTE entry
  filter — a genuine risk control, not a backtest-fitting hack.
- **Expected impact:** potentially large DD reduction across 6 strategies
  at once. **Confidence: medium-high** on the mechanism, unknown on
  magnitude until measured.

### #4 — `ema_crossover`: only 25 trades in 123 days
- **Root cause:** unknown — needs the rejection-diagnostic counters
  (`candidate_signals` vs. `rejected_*`) inspected to determine whether
  entries are being generated and filtered out, or barely generated.
- **Why it matters:** best PF in the entire run (1.71) and lowest DD
  (10.1%), but far too few trades to trust or to contribute meaningfully.
  If it's over-filtered rather than genuinely selective, loosening one
  filter could yield the most production-ready strategy in the set.
- **Expected impact:** unknown until diagnosed. **Confidence: low** —
  explicitly a diagnosis task before any change.

### #5 — Strategies with structural dead code (audit §3.1, §4.x)
- `institutional_momentum`: ~half its advertised architecture
  (kill-switch, ITM selector, trade scorer, MTM trailing) is unreachable
  from the live entry path. Notably it still posted the best
  regime-consistency in the first run (profitable in 4/5 regimes, 16.7%
  DD) **without** those components — so wiring them in is a real
  opportunity, not just cleanup.
- `drl_strategy`: model observation vector is permanently constant (audit
  §4.2) — it cannot see the market at all, yet posted PF 1.07 over 1,189
  trades, which is itself strong evidence that its "edge" is an artifact
  of the exit engine rather than the model. Deserves an explicit
  keep-or-remove decision rather than optimization.

---

## Deferred (explicitly out of scope for the improvement pass)

- Backtest engine architecture (audit §2.2) — still simulates the retired
  fixed-%/fixed-target model. Deferred by prior direction.
- Live paper-trading validation of any non-`ema_rsi` strategy — would
  disrupt the running validation clock. Deferred by prior direction.
- Market Regime Strategy Router — the stated end goal, but it is only
  meaningful once individual strategies have trustworthy per-regime
  profiles. Blocked on #1-#4.

---

## Method notes

- **Never optimize on profit alone.** Each item above is justified by a
  mechanism (a bug, a broken independence assumption, an unfillable stop),
  not by a backtest number. Backtest deltas are used to *verify* a fix
  helped, never to *find* the change.
- **One at a time, fully validated.** Regression tests + full suite +
  production-architecture backtest before/after, per item.
- **Preserve trading philosophy.** Every item is a repair or a gate, not
  a redesign of what the strategy is trying to do.
