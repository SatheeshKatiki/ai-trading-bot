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

### #0a — 🔴 MARL_Ultra Capital Protection Mode is a permanent deadlock (HIGH severity, live-reachable)

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
- **Expected impact:** MARL_Ultra currently posts the 2nd-best profit
  factor in the entire suite (1.41) on only 127 trades. If it is
  deadlocking partway through the validation window, its true trade count
  and profit are both being understated, and in live trading it would
  silently stop working after any 3-loss streak.
- **Confidence: high** on the mechanism (verified line by line);
  **unknown** on how much of its current backtest is affected.



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

### #2 — Cross-cutting: `enhanced_ai` is the only net-negative strategy
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
