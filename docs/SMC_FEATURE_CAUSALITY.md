# SMC Feature Causality — Audit and Classification

**Scope:** every Smart Money Concepts field produced anywhere in this
repository, traced to its implementation, classified by whether it depends on
future candles, and by when it actually becomes knowable.

**Method:** each confirmation point below was first *derived* from the source
and then *measured* — recompute the engine on `df[:k]` for increasing `k` and
record the first `k` at which the object appears. Nothing here is inferred
from a docstring or guessed from a field name.

**Governing rule.** For every feature the strategy uses:

> Could the live trading engine have known this exact value using only
> information available at or before `decision_time`?

If yes, it is eligible. If no, it is blocked until its confirmation timestamp.
A field is never assumed causal merely because it exists in the DataFrame.

---

## 1. Where SMC is calculated — three independent implementations

| # | Implementation | Language | Consumers | Feeds a trading decision? |
|---|---|---|---|---|
| 1 | `shared/indicators/smart_money_concepts.py::calculate_smc` (LuxAlgo/ICT model, 27 KB) | Python | `shared/agents/smc_confluence_agent.py`, `tests/test_smc_confluence.py`, and now `rsi_smc_options_buyer` | **Yes**, via `rsi_smc_options_buyer` only |
| 2 | `shared/indicators/smc.py::smc_features` (naive: 3-candle FVG, 10-bar rolling BOS) | Python | `advanced_ai_ml_strategy`, `enhanced_ai_strategy` | **Yes** — see §5, unaudited |
| 3 | `frontend/lib/indicators-engine.ts::computeSMC` (833 lines) | TypeScript | `frontend/components/native-chart.tsx` | **No** — display only |

Before this work, implementation #1 was consumed by **nothing but a test
file** — a complete, documented SMC engine wired to no strategy, no API route
and no chart.

---

## 2. Classification table

`calculate_smc` (implementation #1). "Confirmation point" is positional, in
bars, relative to the object's own origin bar.

| Feature | Future-data dependency | Confirmation point | Chart usage | Strategy usage | Verdict |
|---|---|---|---|---|---|
| `smc_bos` (series) | No — engine defers pivots by `conf_idx = i - effective_swing_len` | origin bar (lag 0) | available | **used** | **SAFE** |
| `smc_choch` (series) | No — same deferral | origin bar (lag 0) | available | **used** | **SAFE** |
| `smc_bullish_fvg` / `smc_bearish_fvg` (series) | No — formed by the 3rd of 3 candles | origin bar (lag 0) | available | **used** | **SAFE** |
| `FairValueGap` objects | No | `bar_index` (**measured lag 0**) | available | **used**, gated | **SAFE** |
| `FairValueGap.mitigated_index` | Engine scans forward | index itself is the answer to "as of bar i" | available | **used** as `mitigated_index > i` | **SAFE** |
| `OrderBlock` objects | **Yes** — created at a later structure break | first same-direction `SMCStructureEvent` after origin (**measured lag 1–16, median ≈ 4**) | available from origin, labelled CANDIDATE | **available, gated**; trigger OFF by default | **SAFE WHEN GATED** |
| `OrderBlock.invalidated` | **Yes** — frame-wide boolean, **no index** | re-derived here with the engine's own rule (close beyond the far side) | available | used only as "invalidated as of bar i" | **SAFE WHEN RE-DERIVED** |
| `LiquidityPool` (EQH/EQL) | **Yes** — built from `detect_pivots(length=internal)`, and the EQH/EQL builder applies **no** confirmation delay | `max(bar_indices) + effective_internal_len` (**measured: 5 at internal=5, 2 at effective internal=2**) | available | **used**, delayed | **SAFE WHEN DELAYED** |
| `LiquidityPool.swept` / `sweep_index` | — | **never assigned by the engine** | — | not used (sweeps detected separately) | **DEAD FIELD** |
| Swing pivots (`detect_pivots`) | **Yes** — strict extremum over `[p-L, p+L]` | `pivot_index + L` | available | used via the lifecycle model | **SAFE WHEN DELAYED** |
| `strong_high` / `weak_high` / `strong_low` / `weak_low` | **Yes** — final loop values | end of frame only | **analytical only**, `as_of` stamped | **BLOCKED** | UNSAFE per-bar |
| `active_swing_high` / `active_swing_low` | **Yes** — trailing window at the last bar | end of frame only | **analytical only** | **BLOCKED** | UNSAFE per-bar |
| `equilibrium_price`, `smc_equilibrium` | **Yes** — computed over `[-lookback:]` at the last bar, then **broadcast to every row** | end of frame only | **analytical only** | **BLOCKED** | UNSAFE per-bar |
| `premium_zone` / `discount_zone` | **Yes** — derived from `equilibrium` | end of frame only | **analytical only** | **BLOCKED** | UNSAFE per-bar |
| `ote_zone` | **Yes** — derived from the same range | end of frame only | **analytical only** | **BLOCKED** | UNSAFE per-bar |
| `trend` / `smc_trend` | **Yes** — `current_trend` after the loop, **broadcast to every row** | end of frame only | **analytical only** | **BLOCKED** | UNSAFE per-bar |
| `smc_candle_color` | **Yes** — derived from `smc_trend` | end of frame only | **analytical only** | **BLOCKED** | UNSAFE per-bar |
| `mtf_levels` (Daily/Weekly/Monthly) | Partly — the current period is incomplete | previous completed period | available | not used (this strategy derives PDH/PDL itself, causally) | SAFE IF SHIFTED |
| `SMCStructureEvent` | No | its own `bar_index` | available | used | **SAFE** |

### The three traps worth naming

1. **Columns that look per-bar and are not.** `calculate_smc` assigns
   `res_df['smc_trend'] = current_trend.value` and
   `res_df['smc_equilibrium'] = equilibrium` — *scalars*, broadcast across
   every row. Reading either per-bar injects the end-of-frame answer into
   every historical row. A backtest would show a near-perfect trend filter
   that does not exist.

2. **Liquidity pools with no delay.** The BOS/CHoCH loop carefully defers
   pivot consumption; the EQH/EQL builder does not. Pools were knowable 5 bars
   (25 minutes on a 5-minute chart) later than their `bar_indices` suggest —
   ample hindsight to manufacture a fake edge in a sweep-based strategy.

3. **Order Blocks with no creation index.** `OrderBlock.bar_index` is the
   *source candle*, not the bar the block was discovered on. The creation bar
   is discarded inside the engine loop — but it is **recoverable** from
   `structure_events`, because the block is appended in the same loop
   iteration as the break that produced it.

---

## 3. Data separation as implemented

```
                       MARKET DATA
                            |
                   calculate_smc()   (once per closed bar, cached)
                            |
                   smc_lifecycle.py
          recover origin / confirmation / invalidation
                            |
             +--------------+---------------+
             |                              |
             v                              v
    CAUSAL STRATEGY FEATURES        ANALYTICAL / VISUAL FEATURES
    structure.SmcView               structure.SmcAnalyticalView
    IS_CAUSAL = True                IS_ANALYTICAL = True
    only what was knowable          full lifecycle + end-of-frame
    at or before bar i              scalars, `as_of` stamped
             |                              |
             v                              v
      STRATEGY ENGINE                CHART / RESEARCH / DEBUG
             |                              |
             v                              v
        ENTRY / EXIT                  VISUALIZATION
```

**Enforcement, not convention:**

- `structure.build()` returns the causal surface; `build_analytical()` the
  other. They share one cached `calculate_smc` run, so asking for both is free.
- `signal_engine.build()` calls `structure.assert_causal(view)`, which raises
  `LookAheadError` on anything carrying `IS_ANALYTICAL`.
- `SmcView.__getattr__` raises `LookAheadError` for all 14 non-causal field
  names rather than returning a value.
- `assert_no_forbidden_columns(frame)` refuses a raw `calculate_smc` DataFrame
  reaching the rule path.
- Every object exposes `state_at(i)` → `CANDIDATE | CONFIRMED | MITIGATED |
  INVALIDATED` and `active_mask(n)`, so "usable at bar i" is one call.

## 4. Lifecycle model

```
CANDIDATE  ──►  CONFIRMED  ──►  MITIGATED
                     │
                     └───────►  INVALIDATED
```

`SmcObject` carries `origin_index/time`, `confirmation_index/time`,
`mitigation_index/time`, `invalidation_index/time`. Worked example from the
NIFTY fixture:

| Object | origin | confirmation | at origin+1 | at confirmation |
|---|---|---|---|---|
| `OB_BULL_310` | bar 310 | bar 313 | CANDIDATE | CONFIRMED |
| `OB_BULL_356` | bar 356 | bar 357 | CANDIDATE | CONFIRMED |
| `OB_BEAR_550` | bar 550 | bar 551 | CANDIDATE | CONFIRMED |

Chart at bar 311 may draw `OB_BULL_310` as a developing zone. The strategy at
bar 311 **must not** see it. At 313 both may use it, the chart re-labelling it
CONFIRMED.

## 5. Findings recorded, deliberately NOT acted on

These are outside the scope of the new strategy and touching them would change
existing behaviour. Reported for a future decision.

1. **`smc_features` (implementation #2) is unaudited and feeds two live
   strategies.** `advanced_ai` and `enhanced_ai` consume `bos_bullish` /
   `bullish_fvg` from a 10-bar rolling high with no confirmation delay. Its
   BOS uses `df['high'].shift(1).rolling(10).max()`, which is causal; its FVG
   uses `low_3 > high_1` on a 3-candle window, also causal. **Both appear
   causal**, but neither carries a lifecycle and neither has been measured the
   way implementation #1 has. `enhanced_ai` is already a REMOVE verdict on
   other grounds.

2. **The chart computes its own SMC (implementation #3).** `computeSMC` uses a
   5-bar pivot (`i+1`, `i+2` — future candles) with no confirmation delay. That
   is *correct for a chart* and it feeds no trading decision. But it is a third
   definition, and it will disagree with the Python engine. The repository has
   already been bitten by a chart drawing markers the engine would never act on
   (`computeAutoSignalMarkers`, removed 2026-09-22). **Recommendation:** if SMC
   zones are ever surfaced as decision support, serve them from
   `build_analytical()` through an endpoint rather than recomputing in the
   browser.

3. **`LiquidityPool.swept` / `sweep_index` are declared and never assigned.**
   No sweep detection exists in the SMC engine. `rsi_smc_options_buyer`
   detects sweeps separately, pinned by an equivalence test against
   `LiquiditySweepDetector`.

4. **`LiquiditySweepDetector` is dead code.** Constructed at
   `momentum_strategy/trade_scorer.py:25`, never called. It remains the
   reference definition.

5. **`show_order_blocks` on `LuxAlgoSMCConfig` is declared and never read.**
   Order blocks are built unconditionally.

## 6. Backtest / replay / live consistency

| Path | SMC source | Consistent? |
|---|---|---|
| Live (`main.py` → `registry.run_strategy`) | `structure.build()` | yes |
| Validation harness (`run_strategy_backtest`) | same call, same code | yes |
| Shadow/paper book | same call, same code | yes |
| Chart (`native-chart.tsx`) | its own TypeScript engine | **no — display only, by design** |

One call site, one cache, one definition for every path that can place an
order. The chart is deliberately separate and deliberately non-decisional.

## 7. Tests pinning all of this

`Testing_Automation_AI_Trading_Bot/python-unit/`

- `test_rsi_smc_causality.py` — prefix stability; measured pool lag; measured
  FVG lag; **derived-equals-measured OB confirmation**; forbidden-field guard;
  minimum-bars gate; the direct no-look-ahead assertion (signals must not
  change when future bars arrive); cache bounds.
- `test_rsi_smc_lifecycle.py` — every SMC kind retained for analysis;
  end-of-frame scalars retained with `as_of`; analytical view refused by the
  causal guard; guard actually wired; state transitions monotonic;
  confirmation never precedes origin; one `calculate_smc` run feeds both
  surfaces; entry rules unchanged with the OB trigger off.
- `test_rsi_smc_isolation.py` — shared modules carry no reference to this
  strategy; filter opt-out does not leak.
