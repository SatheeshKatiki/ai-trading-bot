# ATM/ITM Strike Guarantee + Multi-Instrument Focus

Implemented 2026-08-06 on branch `trading_bot_v2.10.0`, immediately following
the option stop-loss architecture (`docs/OPTION_STOP_LOSS_ARCHITECTURE.md`).

## 1. Requirements

1. Trade only ATM or slightly ITM options — never OTM. ATM is the maximum
   preference; slight ITM is an acceptable liquidity fallback.
2. Always resolve the nearest expiry, across NIFTY, BANKNIFTY, FINNIFTY and
   SENSEX — with NIFTY and SENSEX as the primary focus.

## 2. Findings from the deep-analysis pass

Before changing anything: both real call sites of `select_option()`
(`trading_bot/main.py`'s index-to-option auto-map, and the "premium"
strategy's internal wiring) already passed `itm_strikes=1` — slight ITM.
Nothing in the live system was trading OTM today. But that held only because
every current caller happened to pass a safe value; nothing in
`select_option()` itself prevented a caller — this one or a future one —
from passing a negative offset (which pushes the strike the wrong side of
spot, i.e. OTM) or an unreasonably large one. That gap is what made this a
"could still trade OTM" system, not just a "doesn't trade OTM today" one.

Two further findings, both real bugs, found while implementing:

- **`momentum_strategy/itm_selector.py` hardcoded Thursday as NIFTY's expiry
  weekday.** Stale — NSE consolidated NIFTY/BANKNIFTY weekly options expiry
  to Tuesday (verified 2026-08-03 against Fyers' live symbol master, already
  fixed in `options_selector.py`'s `INSTRUMENT_CONFIG`; this module simply
  never got the same fix). This module is currently dormant — only wired to
  `institutional_momentum`, not the active `ema_rsi` strategy — so it was
  latent, not live, but would have built a symbol for a non-existent
  contract on every entry had that strategy ever been selected.
- **The "premium" strategy's instrument extraction never stripped a `"BSE:"`
  prefix.** A SENSEX signal through that branch built the instrument key
  `"BSE:SENSEX"` instead of `"SENSEX"`, silently failing to match
  `INSTRUMENT_CONFIG`. Fixed as a side effect of consolidating both call
  sites onto one shared normalizer (§3).
- **The dashboard's history-fallback lookup would have mislabeled FINNIFTY
  candles as NIFTY's.** `"FINNIFTY"` contains the substring `"NIFTY"`, and
  the fallback chain's generic NIFTY branch came before a dedicated FINNIFTY
  check — the exact class of bug that branch's own docstring already
  describes fixing for RELIANCE.

## 3. Implementation

### 3.1 Hard OTM guarantee (`options_selector.py`)

```python
MIN_ITM_STRIKES = 0   # ATM
MAX_ITM_STRIKES = 2   # reserved for the 0DTE Greeks Guard's emergency shift

itm_strikes = max(MIN_ITM_STRIKES, min(int(itm_strikes), MAX_ITM_STRIKES))
```

Clamped at the top of `select_option()`, before any strike math. This is an
architectural guarantee, not a caller convention: an OTM entry is now
structurally impossible regardless of what any current or future caller,
strategy, or config passes in. `select_option()`'s own default (no
`itm_strikes` argument) was already `0` — ATM — matching "maximum preferred
ATM only" with no change needed there; both live call sites explicitly
opt into `1` (slight ITM) for liquidity, now read from the new
`option_strike_itm_offset` setting (default `1`) instead of being hardcoded.

### 3.2 One instrument normalizer, not two drifting copies

New `shared/instruments.py`:

```python
normalize_instrument("NSE:NIFTY50-INDEX")    # -> "NIFTY"
normalize_instrument("NSE:NIFTYBANK-INDEX")  # -> "BANKNIFTY"
normalize_instrument("BSE:SENSEX-INDEX")     # -> "SENSEX"
normalize_instrument("NSE:FINNIFTY-INDEX")   # -> "FINNIFTY"
```

Both call sites in `main.py` now compute this once per symbol per tick
(`instrument_key`) instead of re-deriving it inline — which is what fixed
the `"BSE:SENSEX"` bug in §2 for free, by construction rather than by patch.

### 3.3 Per-instrument confidence gating (`shared/risk/instrument_focus.py`)

"Mainly focus NIFTY and SENSEX" needed a concrete mechanism, not a
preference. Applied the exact lever the codebase already used to gate a
stricter strategy — `enhanced_ai`'s 0.85 vs the default 0.60 minimum AI
confidence — keyed per-instrument instead of per-strategy:

```python
resolve_min_confidence(instrument, base_min_confidence, settings)
```

NIFTY and SENSEX trade at whatever bar the active strategy already computed.
BANKNIFTY and FINNIFTY need at least `secondary_instrument_min_confidence`
(default 0.85) — never a value lower than the strategy's own bar, so a
strategy already stricter than 0.85 (like `enhanced_ai`) is never relaxed.

Deliberately touches nothing else: position sizing, risk-based lot
calculation, and every cap in `RiskManager` stay completely uniform across
all four instruments. Focus is expressed purely as a signal-quality gate.

### 3.4 Multi-instrument watchlist

`config/settings.json`'s `symbols` list (previously absent, defaulting to
NIFTY only) now carries all four, NIFTY/SENSEX first:

```json
"symbols": ["NSE:NIFTY50-INDEX", "BSE:SENSEX-INDEX", "NSE:NIFTYBANK-INDEX", "NSE:FINNIFTY-INDEX"]
```

This required one infrastructure fix without which it would have been
cosmetic: `api_bridge.py`'s `_subscribed_symbols` (the static seed for what
the upstream Fyers WebSocket actually subscribes to) never included
FINNIFTY. `/ws/live` clients — including `main.py`'s own broker WS client —
are purely passive; they only ever see whatever `current_market_data` holds,
which is only populated for subscribed symbols. The existing "dynamic
subscription" path only adds a symbol *after* a position already exists for
it, which doesn't help an underlying index a strategy needs live ticks for
just to evaluate a signal in the first place. Without this fix, FINNIFTY
could have sat in the watchlist forever, fully configured, and never receive
a single tick.

## 4. Configuration

All settings-driven, defaults in `main.py::_load_settings` and mirrored in
`config/settings.json`:

| Key | Default | Effect |
|---|---|---|
| `symbols` | all 4, NIFTY/SENSEX first | live watchlist |
| `option_strike_itm_offset` | `1` | 0=ATM, 1=slight ITM; clamped to [0,2] regardless |
| `focus_instruments` | `["NIFTY","SENSEX"]` | trade at the strategy's own confidence bar |
| `secondary_instrument_min_confidence` | `0.85` | floor for everything else |

## 5. Compatibility audit

| Area | Result |
|---|---|
| Pyramiding, exit engine, reconciliation, risk manager | Untouched — this change only affects strike selection and signal-gating, not exits, sizing math, or reconciliation |
| Non-focus instruments (BANKNIFTY/FINNIFTY) | Trade normally, just behind a stricter confidence bar; sizing and risk caps identical to NIFTY/SENSEX |
| Dashboard / journal / PnL | No schema change; `entry_symbol`/`instrument` values are unaffected by the normalizer refactor (same strings produced, just from one function instead of two) |
| `institutional_momentum` strategy (dormant) | `itm_selector.py`'s expiry weekday fixed; behavior otherwise unchanged |

**Regression:** 264/264 pytest (58 new: `test_instruments.py`,
`test_instrument_focus.py`, `test_strike_selection.py`,
`test_momentum_itm_selector.py`), 56/56 Playwright.

## 6. Live verification

Both `api_bridge.py` and `trading_bot/main.py` restarted 10:38–10:39 IST
2026-08-06. Confirmed from `logs/engine.log`, same session, market open:

- All four instruments preloaded (1,667 candles each); FINNIFTY's cache file
  did not exist and was created automatically from a real broker fetch on
  first preload (`Saved Fyers historical data to fresh cache:
  NSE_FINNIFTY-INDEX_5Min.csv`).
- `Starting live stream for symbols: NSE:NIFTY50-INDEX, BSE:SENSEX-INDEX,
  NSE:NIFTYBANK-INDEX, NSE:FINNIFTY-INDEX` — all four requested.
- Real signals auto-mapped correctly for **SENSEX** (`BSE:SENSEX2680657800CE`)
  and **BANKNIFTY** (`NSE:BANKNIFTY2681178600CE`, `...2681157800CE`) within
  minutes of restart — both decode to a **2026-08-11 Tuesday** expiry,
  confirming the corrected calendar live, not just in tests.
- A real SENSEX signal at ₹418.35 premium correctly resolved through the
  (previously implemented) banded stop-loss architecture: `SL BAND >₹250 |
  premium ₹418.35 -> SL ₹373.80 (risk ₹44.55/unit, 10.65%, dynamic_pct)` —
  confirms the two pieces of work integrate cleanly end to end.
- Zero errors or tracebacks across the observation window.

Not yet observed live: an actual BANKNIFTY/FINNIFTY entry being *held back*
by the stricter 0.85 confidence bar specifically. See §7 — the same
pre-existing condition already flagged in the stop-loss report currently
makes every signal's confidence a constant 1.0, which trivially clears any
threshold up to 1.0. The gate is correct and unit-tested; it will only
produce an observable difference once that condition is resolved.

## 7. Trade-offs and open items

1. **The AI-confidence gate is currently a no-op in practice** — same root
   cause already flagged in `docs/OPTION_STOP_LOSS_ARCHITECTURE.md` §7:
   with `enable_ai_filter` off, `main.py` sets `confidence = 1.0` as a
   fallback constant, which clears both the 0.60 base bar and the new 0.85
   secondary bar unconditionally. The per-instrument gate is real and
   correctly wired, but "mainly focus NIFTY/SENSEX" will not visibly change
   entry frequency for BANKNIFTY/FINNIFTY until the AI filter is enabled (or
   the fallback is changed) — the same open item as before, not a new one.
2. **FINNIFTY has no committed CSV fallback for the dashboard's `/api/history`
   endpoint.** The live engine doesn't need it (confirmed self-healing via a
   real broker fetch on first preload, §6), but the dashboard's read path
   would return empty rather than mislabeled data if the broker were ever
   unreachable for FINNIFTY specifically. Flagged rather than fabricating a
   fallback file.
3. **Yahoo Finance has no reliable FINNIFTY ticker**, so `api_bridge.py`'s
   no-token yfinance-polling fallback (only active when there is no cached
   broker token at all — normally dormant) cannot serve FINNIFTY ticks.
   Documented in place rather than guessing a ticker that may not exist.
4. **Four concurrent instruments instead of one materially changes exposure
   shape** — up to 4 simultaneous open positions instead of 1 (each symbol
   still limited to one position at a time), and 4x the per-tick evaluation
   work. Position sizing and every risk cap are per-trade and per-day, not
   per-instrument, so aggregate exposure is bounded by the existing daily
   trade cap and daily loss limit, not a new mechanism — worth being aware
   of, not a defect.
