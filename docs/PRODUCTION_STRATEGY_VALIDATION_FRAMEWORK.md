# Production Strategy Validation Framework — Methodology, Results, Limitations

**Status:** Framework built and run against all 12 registered strategies over a
6-month real-NIFTY window (2026-02-01 → 2026-07-31, 123 trading days). Results are
evidence for prioritizing future work, not a final production sign-off — see §5.

## 1. Why this exists, and what it deliberately does not touch

The shared backtest engine (`backtesting_engine/run.py`) still simulates a
fixed-percentage stop-loss and a fixed profit target — the architecture replaced
live on 2026-08-06. It was explicitly left untouched (audit §2.2, out of scope for
this pass). `validation_harness/` is a new, fully isolated package that instead
reuses the real production pipeline end-to-end: `registry.run_strategy()`,
`PremiumSignalEngine.evaluate()`, `select_option()`, `resolve_initial_stop()`,
`RiskManager`, `SmartExitEngine`, `resolve_option_atr()`,
`is_market_open()`/`is_before_eod_cutoff()`. No risk or exit logic was
reimplemented a second time.

## 2. Methodology

- **Data:** real NIFTY 5-minute OHLCV (`data/NSE_NIFTY50-INDEX_5Min.csv`), spot
  price only — this repository has no historical option-premium data.
- **Option pricing:** entries and every subsequent bar's mark-to-market are priced
  via Black-Scholes (`options_selector.py::calculate_option_price`, added
  alongside the already-live `calculate_greeks` rather than duplicating its math)
  against the actual contract `select_option()` selected, at a flat 15% implied
  volatility. This is a documented approximation, not real market data — see §4.
- **Day-isolated backtesting:** each calendar day is run independently with a
  fresh `RiskManager` (matching this system's actual EOD-square-off, no-overnight-
  carry design), with `_WARMUP_CALENDAR_DAYS`=30 of prior bars supplied as
  indicator context so long-lookback strategies (e.g. `"premium"`'s EMA200) have
  real history, while entries are only permitted within the target day itself.
  This also avoids a real trap: a continuous multi-month run can hit
  `RiskManager`'s max-drawdown halt early and — correctly matching
  production — never auto-clear without manual intervention, silently starving
  the rest of the period of trades.
- **Regime classification:** `classify_daily_regimes()` labels each trading day
  trending/sideways/high-volatility/low-volatility/gap-day from real ADX and
  daily-range percentiles. Verified against this system's real ~14-month history;
  needs a real sample size to be trustworthy (ADX(14)'s own warmup transient can
  dominate a too-short window — see `regimes.py`'s docstring).
- **Metrics:** Net Profit, Profit Factor, Win Rate, Expectancy, Max Drawdown,
  Recovery Factor, Max Consecutive Losses, Avg Trade, Avg Holding Time, realized
  R:R — computed once per strategy overall and once per regime, from a single
  sweep (regime buckets are assigned per-trade after the fact, not by re-running
  the backtest per regime).
- **Classification:** `classify.py`'s `KEEP`/`IMPROVE`/`REMOVE` logic is
  deliberately conservative, matching the explicit "not from a single backtest"
  instruction this framework was built to satisfy — REMOVE requires losing both
  overall AND in most regimes actually traded, with at least 30 aggregate trades;
  KEEP requires the symmetric bar (profitable overall, profitable in nearly every
  regime traded, bounded drawdown). A single good or bad regime cannot flip the
  verdict either way (tested explicitly — see
  `test_validation_harness_classify.py`).

## 2a. Production-readiness criteria — revised 2026-08-08 (PF ≥ 1.30 retired)

The original `profit_factor >= 1.30` primary gate was re-evaluated
objectively and replaced. Full derivation lives in
`validation_harness/classify.py`'s module docstring; summary:

**PF failed as a primary gate for three independent reasons.**
1. *Mechanically redundant.* PF = (WR/(1−WR)) × R:R. Verified against
   actuals: `institutional_momentum` (0.727/0.273)×0.46 = **1.22**
   (observed 1.22); `ema_rsi` = **1.37** (observed 1.38);
   `ema_crossover` = **1.72** (observed 1.71). It adds no signal beyond
   two metrics already reported.
2. *Barely discriminates.* Across 12 strategies PF spans only 0.98–1.71,
   8 of them inside 1.10–1.41. An option-buying system with structurally
   sub-1.0 realized R:R (0.41–0.58 suite-wide — the premium-banded stop
   is wider than the typical trailing exit) cannot produce the PF values
   a futures/equity trend system would. A 1.30 bar imported from that
   context is not meaningful here.
3. *Silent on risk.* Under the old gate `ema_rsi` (PF 1.38) **passed**
   with a 47.9% drawdown while `institutional_momentum` (PF 1.22)
   **failed** with a 16.7% drawdown — the exact inversion of
   production-readiness.

**Replacement framework** (every threshold derived from a principle):

| Gate | Test | Derivation |
|---|---|---|
| N1 | expectancy > 0 and PF > 1.0 | definition of an edge |
| N2 | ≥ 30 trades | central-limit minimum for a mean estimate |
| N3 | no unresolved critical defect | statistics cannot see a broken strategy |
| N4 | drawdown ≤ 30% | recovery asymmetry: D needs D/(1−D); 30%→+43%, 50%→+100% |
| Q1 | recovery factor ≥ 2.0 | earned ≥ 2× its worst drawdown |
| Q2 | DD ÷ (consec_losses × risk/trade) ≤ 2.0 | drawdown explained by the risk model, not by something outside it |
| Q3 | profitable in a majority of sampled regimes | not a single-condition bet |

**Q2 is the genuinely new discriminator.** A strategy risking R per trade
that suffers C consecutive losses should show a drawdown near C×R. A
ratio near 1.0 means drawdown is fully accounted for by ordinary streaks;
a large ratio means risk is arriving from outside the model (correlated
or overlapping losses, or losses exceeding designed per-trade risk via
gap-through/slippage). This is invisible to PF, net profit, and even
recovery factor. Measured spread across the suite: 0.82 → 3.95.

**Evidence the framework is not reverse-engineered:** applying it
**demotes the two highest-net-profit strategies** — `advanced_ai`
(₹277,101) and `ema_rsi` (₹247,201) — on survivability grounds. A gate
fitted to flatter the portfolio would not do that. It also *promoted*
`institutional_momentum`, which the old gate rejected. The reordering
runs in both directions.

## 3. Results summary (2026-02-01 → 2026-07-31)

**3 KEEP · 7 IMPROVE · 2 REMOVE** under the revised framework (§2a).
Full ranked table and per-regime detail:
`validation_harness/results/full_report_2026H1.md`.

| # | Strategy | Verdict | Trades | Net | PF | DD | Blocking gate(s) |
|---|---|---|---|---|---|---|---|
| 1 | institutional_momentum | **KEEP** | 319 | ₹78,397 | 1.22 | 16.7% | — |
| 2 | buy_the_dip | **KEEP** | 306 | ₹74,102 | 1.25 | 22.1% | — |
| 3 | ultra_meta_dip_swarm | **KEEP** | 246 | ₹58,036 | 1.24 | 25.0% | — |
| 4 | advanced_ai | IMPROVE | 993 | ₹277,101 | 1.24 | 61.9% | N4 survivability, Q2 |
| 5 | ema_rsi | IMPROVE | 609 | ₹247,201 | 1.38 | 47.9% | N4 survivability, Q2 |
| 6 | MARL_Ultra | IMPROVE | 976 | ₹130,399 | 1.10 | 41.3% | N4 |
| 7 | marl_strategy | IMPROVE | 976 | ₹130,399 | 1.10 | 41.3% | N4 |
| 8 | meta_agent_swarm | IMPROVE | 242 | ₹36,290 | 1.13 | 42.7% | N4, Q1, Q2 |
| 9 | premium | IMPROVE | 135 | ₹13,915 | 1.17 | 11.5% | Q1 recovery 1.21 |
| 10 | ema_crossover | IMPROVE | 25 | ₹13,239 | 1.71 | 10.1% | N2 sample (25 < 30) |
| 11 | drl_strategy | **REMOVE** | 1,189 | ₹109,161 | 1.07 | 39.2% | N3 market-blind |
| 12 | enhanced_ai | **REMOVE** | 585 | -₹16,160 | 0.98 | 55.3% | N1 no edge |

### Verdict changes worth calling out

- **`institutional_momentum` promoted to KEEP.** The old PF gate rejected
  it at 1.22 despite the lowest drawdown of any profitable strategy
  (16.7%), the best recovery factor (4.68), profitability in 4 of 5
  regimes, and a clean audit + live-code re-verification.
- **`advanced_ai` and `ema_rsi` demoted to IMPROVE** — the two highest
  earners in the suite — purely on survivability (61.9% and 47.9%
  drawdowns, both also failing Q2 at 2.95× and 2.74× the drawdown their
  own loss streaks explain). Their profits are real; their risk profiles
  are not production-grade.
- **`enhanced_ai` moved from my earlier IMPROVE to REMOVE.** I had argued
  IMPROVE on the grounds that its loss concentrates in one bad June week.
  The framework overrides that, and it is right to: negative expectancy
  over **585 trades** is a large sample, and "profitable once you exclude
  its losses" is the reasoning that produces overfitted systems. It also
  already received one genuine mechanism-based fix (the RSI
  dual-confirmation defect, which cut the loss 29%) and remained
  negative. Recording the change of verdict explicitly rather than
  quietly.
- **`MARL_Ultra` and `marl_strategy` are now byte-identical** (976 trades,
  ₹130,399.24, PF 1.10, 41.26% DD) once the capital-protection deadlock
  was fixed. They are the same strategy under two names — a
  consolidation candidate independent of their shared IMPROVE verdict.

**Neither REMOVE has been executed.** Both are recommendations pending
confirmation; deleting/deregistering a strategy is destructive and
production-affecting.

## 4. Known limitations of this evaluation (read before acting on the numbers)

1. **Black-Scholes-simulated premiums, not real market data.** Flat 15% IV,
   no smile/skew, no real IV-crush events. Materially better than the old
   engine's flat delta constant, but still an approximation.
2. **5-minute bar resolution can miss a fast-decaying option's true stop-out
   point.** Found live during harness validation: a ₹49.99 premium (₹20-50 band,
   intended ~₹8 stop) crashed to ₹8.97 in a single simulated bar near expiry — a
   real, large gap-through loss the actual ~1-second live premium polling would
   very likely have caught much earlier. This directly inflates max-drawdown
   figures specifically for cheap, short-dated contracts, and is a strong
   candidate explanation for why several strategies' drawdown numbers came in
   high enough to block a KEEP verdict.
3. **No pyramiding simulated.** Single entry per signal — `shared/exits/
   pyramid_sizer.py` was not wired into the harness. If a strategy's edge depends
   partly on scaling into winners, these results understate it.
4. **AI-confidence filter runs as if disabled** (pinned to 1.0), matching
   `main.py`'s own fallback path rather than reconstructing the live model
   singleton in the harness. Strategies whose real edge depends on the AI filter
   meaningfully rejecting low-confidence signals are not getting that benefit
   here.
5. **Single instrument (NIFTY), single 6-month window.** Broader validation
   (BANKNIFTY/SENSEX/FINNIFTY, more historical windows) was not run this pass.

## 5. A new finding surfaced by actually running this (not previously fixed, flagged for a separate decision)

**`meta_agent_strategy.py`'s `institutional_momentum` sub-agent call is broken on
every single invocation.** Root cause, confirmed directly: the sub-agent loop
(`meta_agent_strategy.py:41`, `registry._strategies[agent](df, **kwargs)`) assigns
the raw return value straight into a DataFrame column
(`votes_df[agent] = signal`), but `institutional_momentum`'s `generate_signals()`
returns a `(signals, rejection_logs)` **tuple**
(`momentum_strategy/__init__.py:199`), not a plain Series — every other sub-agent
(`advanced_ai`, `ema_crossover`, `ema_rsi`, `enhanced_ai`) returns a plain Series,
so this only breaks for this one. `main.py`'s own entry loop correctly unwraps
this exact case (`if isinstance(signals_data, tuple): signals, _ = signals_data`);
`meta_agent_strategy.py` never replicates that check. Caught per-call by a broad
`except Exception`, logged, and skipped — so `meta_agent_swarm` has been running as
a 4-of-5-brain system this entire evaluation (and, per the audit's own finding,
likely for its entire production life), not the 5-of-6 (including sentiment)
consensus its own docstring describes. **Not fixed in this pass** — it's a new
finding outside the pre-approved scope for tonight's work, surfaced only because
this framework actually executes the code rather than reading it statically.
Trivial, low-risk fix once approved: unwrap the tuple the same way `main.py` does.

## 6. What closing the gap to a real KEEP verdict would need

1. Fix the `meta_agent_swarm`/`institutional_momentum` tuple-unwrapping bug (§5).
2. Re-run with pyramiding wired in, for strategies where that's part of the
   documented design.
3. A longer historical window and/or additional instruments, once the above are
   addressed, to build real regime-consistency evidence rather than a single
   6-month sample.
4. Live paper-trading validation for whatever strategy(ies) this narrows down to
   — explicitly deferred this pass per prior direction; the existing 10-session/
   30-trade validation clock discipline applies here too, one strategy at a time,
   without disrupting `ema_rsi`'s currently-running clock.
