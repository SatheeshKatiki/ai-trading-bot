# Technical Design — Fixing the ATR/Premium Unit Mismatch (Audit §2.1)

**Status: DESIGN ONLY. No code has been changed to produce this document.**
Waiting for a decision on which approach to implement before writing any code.

## 1. Restating the problem precisely

`trading_bot/main.py`'s exit-check loop computes `current_atr` from the **underlying
index's own candles**:

```python
df = aggregator.get_latest_dataframe(sym)   # sym = the INDEX symbol
tr_series = (df["high"] - df["low"]).abs()
current_atr = tr_series.rolling(min(14, len(df))).mean().iloc[-1]
```

`sym` here is always the underlying index — the live feed never subscribes to
option contracts directly, only the index, so this is the only candle series
available on every tick. From real trades observed this session, this produces an
ATR of roughly **100–375 NIFTY index points**.

That value is then passed straight into `shared/exits/exit_engine.py`'s
`SmartExitEngine.evaluate_exit(position, current_price, current_time, current_atr)`,
where it's used against `position.highest_price` — which for an option position is
the **premium**, ₹15–2400 in real trades seen this session:

```python
trailing_stop = position.highest_price - (current_atr * self.atr_multiplier)
```

An index-point quantity is being subtracted from a rupee-premium quantity with no
conversion. The same `current_atr` value is also passed into `momentum_strategy`'s
independent `TieredExitManager._evaluate_exhaustion()`, so this is not a one-off —
it's a systemic unit-conflation wherever `current_atr` crosses from index-scale
computation into premium-scale consumption.

**Effect on the live system:** for lower-premium/lower-delta options (most trades
seen this session, ₹100–250 range), the computed `trailing_stop` is deeply negative
and never exceeds the existing (positive) stop, so the ATR component **never
tightens the stop** — effectively inert. For higher-premium/higher-delta options
(e.g. the ₹2415 premium trade seen this session, delta ≈0.53), the index-point
distance becomes comparable in absolute rupee terms to the premium itself, so the
same mechanism can instead yank the stop aggressively based on unrelated index
chop — potentially **erratic, premature exits**. The behavior is not calibrated to
the position it's meant to protect; it varies essentially at random with the
option's delta/premium.

## 2. Important context that lowers the urgency (but not the need to fix it)

`SmartExitEngine` already has a **second, independent trailing mechanism** running
alongside the ATR one — step 5b, the percentage-based trailing stop
(`trailing_offset_pct`, tracking `position.max_pnl_pct` and exiting once profit
gives back more than the configured offset from its peak). That mechanism is
**unit-agnostic by construction** (it operates on `%` profit, not absolute price),
so it is not affected by this bug and has been providing real, working
profit-protection this whole time. The ATR-based mechanism is a **secondary,
redundant safety layer on top of an already-functioning primary one**, not the
system's only defense. This matters for choosing a fix: the replacement doesn't need
to be a sophisticated, independently-adaptive volatility measure to meaningfully
improve on today's behavior — it just needs to stop being wrong in units, and
ideally be a reasonable, defensible cushion width.

## 3. Where the fix belongs

**Entirely at the call site — inside `main.py` (and `momentum_strategy`'s
`exit_manager.py` equivalent), before `current_atr` is ever handed to
`SmartExitEngine.evaluate_exit()` / `TieredExitManager.evaluate()`.** None of the
four approaches below require changing `SmartExitEngine`'s or `TieredExitManager`'s
internal math at all — they only change what value gets computed and passed in as
`current_atr`. This is the minimal-footprint option: the existing
`atr_multiplier`-based trailing-stop *logic* is preserved unchanged; only its *input*
becomes unit-correct.

## 4. Four candidate approaches

### Approach 1 — Flat percentage-of-premium proxy

`atr_proxy = current_premium * FIXED_PCT` (e.g. 0.5%). This is **already the exact
formula this codebase uses today** as its own degenerate-case fallback
(`main.py`: `current_atr = exit_check_price * 0.005`, currently only reached when the
real ATR computation returns NaN/zero) — this approach simply promotes that formula
from a rare fallback to the standard path for every option position.

| | |
|---|---|
| **Accuracy** | Low — a static assumption, doesn't reflect the option's actual recent volatility (calm vs. choppy regimes get the same cushion). |
| **Complexity** | Minimal — one constant, zero new data. |
| **Cold-start risk** | None — needs only the current premium, no history. |
| **Production risk** | Very low — this exact formula is already live and proven in production as the fallback path. |
| **Consistency with rest of system** | Introduces a new, unrelated magic-number policy (0.5%) alongside the already-established premium-banded philosophy used for the initial stop. |

### Approach 2 — Premium-banded percentage proxy (reuse the existing initial-stop table)

`atr_proxy = resolve_stop_points(current_premium, settings)` — i.e., literally reuse
`shared/risk/option_stop_loss.py`'s already-shipped, already-tested premium-banded
distance table (the same one that sizes the *initial* stop), recomputed continuously
against the *current* premium as the ATR-trailing cushion width.

| | |
|---|---|
| **Accuracy** | Low-medium — still a static-by-premium-level assumption, not a realized-volatility measure, but the *width* varies sensibly with premium the same way the initial stop already does (tighter % for expensive/deep-ITM contracts, wider % for cheap ones) rather than one flat percentage for every premium level. |
| **Complexity** | Minimal — reuses an existing pure function verbatim, zero new code beyond the call-site wiring. |
| **Cold-start risk** | None — same as Approach 1. |
| **Production risk** | Very low — `resolve_stop_points`/`resolve_initial_stop` is already the most thoroughly-tested module in this codebase (dedicated unit test suite, already used live every entry). |
| **Consistency with rest of system** | Highest of the four — one single source of truth for "how much premium-cushion does a stop need at this price level," used identically for both the initial stop and the trailing cushion, instead of two unrelated philosophies. |

*Semantic note:* `resolve_stop_points` was designed to answer "how far below entry
should the initial stop sit," not "how much of my current gain should volatility be
allowed to take back." Reusing it for the trailing cushion is a deliberate
simplification — it says "the noise band of this contract at its current price level
is X points, whether at entry or while trailing" — which is a coherent, defensible
reading, but is a design choice worth confirming you're comfortable with, not a
free lunch.

### Approach 3 — Delta-adjusted index ATR

`atr_proxy = index_atr * abs(option_delta)` — the standard first-order translation
options traders use (`Δ(option price) ≈ delta × Δ(underlying price)`), applied to the
already-reliable, always-available index ATR.

| | |
|---|---|
| **Accuracy** | Medium — theoretically well-grounded for small moves, but delta itself drifts continuously (that's what gamma measures) and is least accurate exactly during the large, fast moves where a trailing stop matters most. |
| **Complexity** | Medium — needs delta recomputed periodically through the trade's life (today it's only computed once, at entry/selection, via `calculate_greeks()`), and that function itself uses a hardcoded 15% volatility assumption (a separate, already-flagged audit finding, §1.5) — compounding one approximation into another. |
| **Cold-start risk** | None for the index ATR itself, but a stale entry-time-only delta (the simplest version of this approach) would grow less accurate the longer/further a position runs. |
| **Production risk** | Low-medium — no new candle infrastructure needed, but introduces a second place (beyond `options_selector.py`) that depends on the Black-Scholes Greeks calculation and its 15%-vol assumption. |
| **Consistency with rest of system** | Reuses existing Greeks math, but stretches it into a role (continuous risk-management input) it wasn't originally built for (currently just a diagnostic log line). |

### Approach 4 — Real premium-history ATR

Accumulate the option contract's own OHLC candles (a new, position-scoped candle
aggregator, mirroring `CandleAggregator` but keyed to the option symbol) and compute
a genuine Wilder-smoothed ATR from it via the already-correct
`shared/indicators/atr.py`.

| | |
|---|---|
| **Accuracy** | Highest in principle — the only approach that reflects the option's *actually realized* volatility, adapting naturally across moneyness/delta/time-to-expiry without an explicit delta adjustment, and correctly capturing gap risk (which matters more for options than the underlying). |
| **Complexity** | Highest — needs new per-position candle-aggregation infrastructure that doesn't exist today. |
| **Cold-start risk** | Real and material — ATR(14) needs 14 bars of premium history before it's meaningful; early in a trade's life (exactly when a good stop matters most) it would be undefined or unreliable. Many trades in this system are short-duration, so a meaningful fraction of a trade's life could occur during this cold-start window. |
| **Production risk** | Medium-high — the existing option-premium fetch is throttled to ~1/second per symbol specifically to avoid broker rate-limiting (a past incident); building real OHLC bars from throttled point-samples would under-represent true intra-candle range (no genuine high/low captured between polls), so even the "real" ATR this approach produces would itself be an approximation of the true premium range, not a clean improvement proportional to the added complexity. |
| **Consistency with rest of system** | Introduces a new, separate data-plumbing concept alongside the existing throttled-premium-cache mechanism. |

## 5. Recommendation

**Approach 2 (premium-banded percentage proxy, reusing `resolve_stop_points`)** is
the recommended fix.

Reasoning: given §2 above — the ATR layer is a secondary safety net, not the
system's primary profit-protection mechanism — the accuracy gap between Approach 2
and Approaches 3/4 doesn't justify their added complexity and (for Approach 4
specifically) genuine cold-start and data-quality risk. Approach 2 costs the same
implementation effort as Approach 1 (the simplest option) while being materially
more consistent with this system's already-established, already-validated
institutional design philosophy — one coherent "how wide should a stop be at this
premium level" answer, reused for both initial placement and trailing, rather than
introducing a second, disconnected magic-number policy. It also carries the lowest
practical risk of the four: no new data infrastructure, no cold-start window, and it
calls a function that is already this codebase's most thoroughly-tested module.

If, after live observation, Approach 2's cushion width turns out to feel too
tight/wide in practice, Approach 3 (delta-adjusted index ATR) is the natural next
step up in sophistication — it would reuse infrastructure that already exists
(`calculate_greeks()`), just needs it called more than once per position's life.
Approach 4 is not recommended unless real premium-level volatility modeling becomes
a priority in its own right, independent of this specific fix.

## 6. Scope of implementation, once approved

1. `main.py`'s exit-check loop: replace the index-derived `current_atr` computation
   with a call to `resolve_stop_points(exit_check_price, settings)` when the position
   is an option (`is_opt_pos`); leave the existing index-scale computation unchanged
   for any non-option position path.
2. `momentum_strategy/exit_manager.py`'s `_evaluate_exhaustion()` (or its caller in
   `main.py`) needs the equivalent fix independently, since it's a fully separate
   implementation (per audit §3.4) — though this strategy is dormant today, so this
   half of the fix is lower urgency and could be sequenced separately if preferred.
3. New regression tests: a reference-vs-fix comparison confirming the trailing
   cushion is now premium-scale (e.g. ~₹15-20 for a ₹100-150 premium, not
   ~100-375 index points), and that low-premium and high-premium positions with an
   identical *relative* retracement now behave consistently (the exact test the
   audit's §2.1 already specified).
4. No changes needed inside `shared/exits/exit_engine.py` or
   `momentum_strategy/exit_manager.py`'s trailing-stop math itself.

Waiting for your decision on Approach 2 vs. an alternative before touching any code.
