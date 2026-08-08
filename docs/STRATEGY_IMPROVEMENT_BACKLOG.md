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
