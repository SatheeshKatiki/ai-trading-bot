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

## 3. Results summary (2026-02-01 → 2026-07-31)

**0 KEEP, 12 IMPROVE, 0 REMOVE.** Full ranked table and per-strategy/per-regime
detail: `validation_harness/results/full_report_2026H1.md`, raw data in the
sibling `.json`.

No strategy cleared the KEEP bar in this window — every one either showed
regime-inconsistent profitability (profitable in some but not most regimes
traded) or a drawdown at or above the 30% threshold. No strategy hit the
conservative REMOVE bar either — even `enhanced_ai` (the only strategy with a net
loss, -₹22,778) was profitable in 3 of 5 regimes traded, meaning the aggregate
loss reflects a minority of bad conditions dragging down an otherwise mixed
picture, not a uniform absence of edge — exactly the situation the "not from a
single backtest" rule exists to prevent from becoming a false REMOVE.

**This "zero KEEP" result should be read as "nothing here is validated as
production-ready yet," not "everything is broken."** See §4 for why the bar was
hard to clear given this run's specific limitations, and §5 for what closing that
gap would need.

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
