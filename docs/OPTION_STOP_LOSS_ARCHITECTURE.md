# Option Stop-Loss Architecture

Premium-banded initial stop-loss for NIFTY option buying, with no fixed profit
target. Implemented 2026-08-06 on branch `trading_bot_v2.10.0`.

---

## 1. Root cause — why the previous design could not work

The entry path priced every stop as a flat percentage of the entry premium:

```python
sl_price  = entry_premium * (1 - sl_pct)      # stoploss_pct
tgt_price = entry_premium * (1 + target_pct)  # target_pct
```

`config/settings.json` carried `stoploss_pct: 0.45`. On a ₹120 premium that
is a **₹0.54** stop — inside the bid/ask spread of most NIFTY strikes. The
position was not being stopped out because the trade was wrong; it was being
stopped out by the spread.

The deeper problem is that a single percentage cannot describe option risk.
Premium is not a linear instrument: rupee volatility scales with the
contract's price, but *percentage* volatility falls as it goes deeper ITM.
0.45% is simultaneously meaningless for a ₹5 lottery strike (₹0.02) and far
too tight for a ₹300 deep-ITM contract. Any single number is wrong at one end
of the chain or the other.

The paired `target_pct: 3.5` capped every winner at +3.5% while losers ran to
whatever the spread did — the inverse of what option buying needs, where a
minority of trades must be allowed to run far enough to pay for the majority
that decay to zero.

**Backtest evidence** (22,801 simulated trades, 22,733 real NIFTY 5-min
candles, see §5): the flat 0.45% stop produced a 33.7% win rate with 64% of
all trades closing as stop-outs, average hold **2.5 bars**. Positions were
being killed before the strategy could be right or wrong.

---

## 2. Implementation

### 2.1 `shared/risk/option_stop_loss.py` (new)

Single source of truth. Pure function, no I/O, called once per entry:

```python
resolve_initial_stop(premium, settings) -> StopLossDecision
```

Band table as specified:

| Premium | Stop distance |
|---|---|
| < ₹10 | ₹2 – ₹3 |
| ₹10 – ₹20 | ₹3 – ₹5 |
| ₹20 – ₹50 | ₹5 – ₹8 |
| ₹50 – ₹100 | ₹10 – ₹15 |
| ₹100 – ₹150 | ₹15 – ₹20 |
| ₹150 – ₹250 | ₹20 – ₹30 |
| > ₹250 | 12% tapering to 10% |

**Within a band the stop is linearly interpolated**, not fixed at a midpoint.
Two reasons: the stop then rises continuously with premium instead of stepping
at each boundary, and the ₹150-250 band hands over to the percentage band
exactly — interpolation reaches ₹30 at ₹250, and 12% of ₹250 is also ₹30. The
mode is configurable (`interpolate` | `min` | `mid` | `max`).

Verified against live settings:

```
 premium |       SL |  risk/u |    pct | band
    5.00 |     2.50 |    2.50 |  50.0% | ₹0-10 (banded)
   12.00 |     8.60 |    3.40 |  28.3% | ₹10-20 (banded)
   25.00 |    19.50 |    5.50 |  22.0% | ₹20-50 (banded)
   60.00 |    49.00 |   11.00 |  18.3% | ₹50-100 (banded)
  120.00 |   103.00 |   17.00 |  14.2% | ₹100-150 (banded)
  245.00 |   215.50 |   29.50 |  12.0% | ₹150-250 (banded)
  300.00 |   265.20 |   34.80 |  11.6% | >₹250 (dynamic_pct)
  800.00 |   720.00 |   80.00 |  10.0% | >₹250 (dynamic_pct)
```

Safety rails: stops round to the ₹0.05 tick so they are placeable as SL-M
triggers; a stop may never risk more than `option_sl_max_pct_of_premium`
(default 60%) of the contract; a premium too small to carry a stop at least
one tick below entry returns `is_tradeable=False` and the entry path skips it
rather than opening a position with a stop at its own entry price. A malformed
band table in settings falls back to the defaults instead of raising — this
runs inside the live entry path, and a config typo must not be able to stop
the engine trading.

### 2.2 No fixed profit target

Option entries are written with `target = 0.0`, meaning unlimited upside.
Profit management belongs entirely to the trailing stop and `SmartExitEngine`.

**This required a prerequisite fix.** `SmartExitEngine.evaluate_exit`
compared `current_price >= position.target` with no positivity guard, so a
target of 0.0 would have fired **"Profit Target Hit" on the first tick of
every position**, closing it at entry. `main.py`'s own hard-TP interceptor
already guarded on `target > 0`; the exit engine did not, so the two exit
layers disagreed about what zero meant.

That was also a latent pre-existing bug: `_load_positions` restores
`target=p.get("target", 0.0)`, so any position restored from disk without a
target would have been closed instantly on the next tick.

### 2.3 Risk-based sizing for options

With a fixed `quantity: 65`, rupee risk becomes a function of stop width —
exactly backwards. The banded stop varies ~15x across the table (₹2 to ₹30),
so a fixed size would risk ₹130 on one trade and ₹1,950 on the next with no
relationship to the account.

Option entries now solve quantity from the stop distance
(`option_risk_based_sizing`, default on), so risk per trade stays roughly
constant regardless of which strike is selected. **Non-option trades are
untouched** — this change is scoped to option buying.

### 2.4 Minimum-lot risk override

An option lot is indivisible. With banded stops, one NIFTY lot (75) of a ₹245
contract risks ₹2,212 — 2.2% of a ₹1L account, above the 1% per-trade cap.
Previously `can_trade` would simply return `False`, and the only trace was a
log line: the engine would look healthy while silently rejecting every
high-premium signal.

`can_trade(..., is_minimum_tradeable_size=True)` now allows that specific case
and emits a `RISK-CAP OVERRIDE` warning stating the true exposure. **It
relaxes the per-trade cap only** — risk-off, daily loss limit, drawdown,
consecutive losses, AI confidence, volatility and the daily trade cap all
still apply, each covered by its own regression test.

### 2.5 Configuration

All of it is settings-driven, in `config/settings.json` and as defaults in
`main.py::_load_settings`:

| Key | Default |
|---|---|
| `option_sl_bands` | the table above |
| `option_sl_band_mode` | `interpolate` |
| `option_sl_dynamic` | `{lower: 250, start_pct: 12, end_pct: 10, taper_to: 500}` |
| `option_sl_max_pct_of_premium` | `60.0` |
| `option_sl_tick_size` | `0.05` |
| `option_risk_based_sizing` | `true` |

`stoploss_pct` / `target_pct` remain in force for non-option (index/equity)
trades.

---

## 3. Files changed

| File | Change |
|---|---|
| `shared/risk/option_stop_loss.py` | **new** — band resolver |
| `shared/risk/__init__.py` | exports |
| `shared/risk/manager.py` | `is_minimum_tradeable_size` override |
| `shared/exits/exit_engine.py` | `target > 0` guard |
| `trading_bot/main.py` | entry path: banded SL, zero target, risk-based sizing, min-lot flag, settings defaults, honest logs |
| `config/settings.json` | band configuration |
| `scripts/validate_option_stop_loss.py` | **new** — backtest harness |
| `Testing_Automation_AI_Trading_Bot/python-unit/test_option_stop_loss.py` | **new** — 33 tests |
| `.../test_no_fixed_target.py` | **new** — 8 tests |
| `.../test_risk_min_lot_override.py` | **new** — 12 tests |

---

## 4. Compatibility audit

| Area | Result |
|---|---|
| Paper trading | Verified — engine restarted 02:46 IST, clean boot, WS connected, settings loaded |
| Live trading | Exchange SL-M order uses `pos_obj.stop_loss`, unchanged path, now a placeable distance |
| Pyramiding | `PyramidSizer` keys off `entry_price` and `pct_trigger` — untouched by SL/target |
| Reconciliation | `compute_reconciliation` uses `stop_loss` only as its estimate fallback; a wider stop makes that estimate more realistic. No target usage |
| Risk manager | Extended, not altered; all other gates regression-tested |
| Dashboard | `target` is broadcast but rendered nowhere in the frontend — no misleading ₹0.00 |
| Reporting / journal / PnL | Computed from entry/exit prices only — unaffected |
| Trailing stop / Smart Exit | Now the sole profit manager, as required |
| Non-option trades | Entirely unchanged code path |

**Regression:** 206/206 pytest, 56/56 Playwright.

---

## 5. Backtest validation

`scripts/validate_option_stop_loss.py`. `backtesting_engine/run.py` could not
be used: it backtests the underlying index with percentage stops and has no
concept of an option premium, so it structurally cannot evaluate a table
denominated in option rupees.

The harness derives option premium series from real NIFTY 5-min candles using
the same Black-Scholes derivation the dashboard already uses, then walks each
trade through the **real `SmartExitEngine`** — not a reimplementation — so
trailing, partial booking and EOD behaviour are exactly what live trading
does. Only the initial stop differs between arms.

22,801 trades, 7 strikes × CE/PE, entries every 12 bars, sized to a fixed
₹1,000 risk budget per trade (as production now does):

| Metric | Banded SL, no target | Flat 0.45% + 3.5% target |
|---|---|---|
| Win rate | **64.5%** | 33.7% |
| Profit factor | 1.06 | 1.05 |
| Avg bars held | **11.7** | 2.5 |
| Stop-outs | 4,957 (22%) | 14,629 (64%) |
| **Avg loss vs risk budget** | **0.43x** | **4.62x** |
| **Worst loss vs risk budget** | **2.47x** | **103.7x** |
| Dominant exit | Trailing (12,573) | Stop-loss (14,629) |

The last two rows are the result that matters. Sizing to ₹1,000 of intended
risk, the old architecture's average *losing* trade actually lost ₹4,622 and
its worst lost ₹103,703 — because price gapped straight through a stop only
₹3.85 wide before it could be acted on. **Its risk was never the risk that
was sized for.** The banded stop's average loss is 0.43x budget and its worst
case 2.47x, i.e. the stop is doing its job.

Profit factor is near-identical (1.06 vs 1.05) because entries here are
mechanical, not strategy-driven — this harness measures stop behaviour, not
edge. The trailing stop becoming the dominant exit (12,573 of 22,801) is the
direct confirmation that profit management moved to where it was asked to be.

---

## 6. Trade-offs and limitations

1. **Wider stops mean larger individual losses in rupees per unit.** Offset by
   risk-based sizing and a ~2x lower stop-out rate; net effect is fewer, more
   meaningful losses rather than constant small ones.
2. **Partial profit booking now triggers later.** It keys off R = |entry −
   stop|, which went from ₹0.54 to ~₹17 on a ₹120 premium. It now fires on a
   genuine move rather than on noise — an improvement, but a behaviour change.
3. **Deep-ITM contracts dominate the backtest sample** (13,051 of 22,801 hits
   were the >₹250 band) because the Black-Scholes derivation across ±4%
   strikes produces many high-premium series. Band-level results should be
   read with that weighting in mind.
4. **The harness is not a strategy backtest.** Mechanical entries, no signal
   filter, no slippage or brokerage modelling.
5. **Paper-trading verification is partial.** Clean restart and configuration
   load confirmed at 02:46 IST 2026-08-06; a real banded stop on a real entry
   can only be observed during market hours (09:15–15:30 IST).

---

## 7. Open items flagged, not changed

Both are risk-policy thresholds rather than wiring, so they are raised rather
than altered unilaterally.

1. **Every trade currently runs at the elevated 3.5% risk tier.**
   `RiskConfig.high_confidence_risk_per_trade` (3.5%) replaces the 1% cap
   whenever `ai_confidence >= 0.85`. With `enable_ai_filter` off, `main.py`
   sets `confidence = 1.0` as a *fallback constant* — not a model output — so
   the override is permanently active. This mattered little when stops were
   ₹0.54; it now directly drives position size. Either enable the AI filter or
   set the fallback confidence below 0.85 so sizing uses the base tier.

2. **The ATR trailing stop uses the wrong unit for options.** `current_atr`
   (`main.py:923`) is computed from the **underlying index** dataframe, then
   applied to **option premium** in `exit_engine.py`
   (`highest_price - current_atr × 2.0`). NIFTY ATR of ~15-25 points
   subtracted from a ₹120 premium is not a meaningful trailing distance. The
   percentage-based trail (`trail_offset`) is unaffected and is what fires in
   practice (12,573 of 12,628 trailing exits in the backtest). A correct fix
   would scale the underlying ATR by the option's delta; that changes exit
   behaviour, so it is listed here rather than bundled into this change.
