# QuantAI Trading Bot — Complete End-to-End Project Guide

> **What this document is.** A single, self-contained walkthrough of the entire
> repository: what exists, why it exists, how a trade actually flows from a
> market tick to a Telegram message, and the order in which the system was
> built. Read it top to bottom once and you will know the whole project.
>
> **Generated:** 2026-09-19 · **Branch:** `trading-bot_V3.15.0` · **Commits:** 318
> · **Python:** ~43,700 lines across 307 files · **Frontend:** 46 TSX + 70 TS files
> · **Tests:** 110 Python unit files + 8 Playwright specs

---

## Table of Contents

1. [What This System Actually Does](#1-what-this-system-actually-does)
2. [The 10,000-Foot Map](#2-the-10000-foot-map)
3. [The Repository, Folder by Folder](#3-the-repository-folder-by-folder)
4. [A Trading Day, Minute by Minute](#4-a-trading-day-minute-by-minute)
5. [The Trade Decision Pipeline](#5-the-trade-decision-pipeline)
6. [The Strategy Layer](#6-the-strategy-layer)
7. [The Risk & Exit Layer](#7-the-risk--exit-layer)
8. [The Broker Layer](#8-the-broker-layer)
9. [The AI / ML Layer](#9-the-ai--ml-layer)
10. [The Research & Validation Layer](#10-the-research--validation-layer)
11. [The API Bridge (FastAPI)](#11-the-api-bridge-fastapi)
12. [The Frontend (Next.js)](#12-the-frontend-nextjs)
13. [State, Config & Persistence](#13-state-config--persistence)
14. [Security](#14-security)
15. [Reliability: Watchdogs & Recovery](#15-reliability-watchdogs--recovery)
16. [Testing & CI](#16-testing--ci)
17. [How This Project Was Built — The Real Timeline](#17-how-this-project-was-built--the-real-timeline)
18. [Design Principles That Emerged](#18-design-principles-that-emerged)
19. [Current Status & What Remains](#19-current-status--what-remains)
20. [Quick Reference](#20-quick-reference)

---

## 1. What This System Actually Does

In one sentence: **it buys NIFTY / BANKNIFTY / SENSEX index options intraday,
based on an EMA/RSI momentum crossover, with institutional-grade risk controls,
and squares everything off the same day.**

Key facts that define every design decision in the codebase:

| Fact | Consequence throughout the code |
|---|---|
| **It only ever BUYS options.** Never sells, never trades the index itself. | Every signal must map to a real CE/PE contract. If the mapping fails, the trade is *abandoned* — never falls back to the index. |
| **Intraday only.** Square-off is hard at 15:15 IST. | Entry cutoff at 15:00, EOD watchdog, no overnight risk, theta modelled everywhere. |
| **0DTE on expiry days is intentional.** | The owner's design; not a bug to "fix". |
| **No fixed profit target.** | A ratcheting stop-loss ladder replaces the target — the trade runs until the market reverses. |
| **Indian market (NSE/BSE).** | Everything is IST-anchored; exchange holiday calendar; lot sizes 65/30/20; Tue/Thu weekly expiries. |
| **Paper first, live second.** | Two parallel books (live engine + paper observer) that must NEVER run together. |

---

## 2. The 10,000-Foot Map

```
                   ┌─────────────────────────────────────────┐
                   │  Start_Zero_Touch.bat / Windows Task     │
                   └────────────────────┬────────────────────┘
                                        ▼
                   ┌─────────────────────────────────────────┐
                   │  auto_daily_session.py  (ORCHESTRATOR)   │
                   │  08:45 wake → 15:35 sleep, every day     │
                   └────┬─────────────┬─────────────┬─────────┘
                        │             │             │
            ┌───────────▼──┐   ┌──────▼───────┐  ┌──▼──────────────┐
            │ auto_login   │   │ api_bridge   │  │ THE BOOK        │
            │ _fyers.py    │   │ .py :8000    │  │ (exactly one)   │
            │ TOTP + PIN   │   │ FastAPI      │  │ main.py (LIVE)  │
            └──────┬───────┘   └───┬──────┬───┘  │   ── or ──      │
                   │               │      │      │ paper_observer  │
                   ▼               │      │      └──┬──────────────┘
            ┌──────────────┐       │      │         │
            │ Fyers API    │◄──────┘      │         │
            │ REST + WS    │              │         ▼
            └──────┬───────┘              │   ┌──────────────────┐
                   │ ticks                │   │ strategies/      │
                   ▼                      │   │ risk/  exits/    │
            ┌──────────────┐              │   │ brokers/         │
            │ Candle       │              │   └────┬─────────────┘
            │ Aggregator   │              │        │
            └──────────────┘              │        ▼
                                          │   ┌──────────────────┐
            ┌──────────────┐              │   │ state.db         │
            │ Next.js :3000│◄─────────────┘   │ active_positions │
            │ Dashboard    │  REST + /ws/live │ paper_obs_logs/  │
            └──────────────┘                  └────┬─────────────┘
                                                   ▼
                                          ┌──────────────────┐
                                          │ Telegram alerts  │
                                          │ + 4K EOD card    │
                                          └──────────────────┘
```

There are **four long-running processes** on a normal day:

1. `auto_daily_session.py` — the supervisor. Starts everything, watches it, kills it at EOD.
2. `api_bridge.py` (port 8000) — FastAPI. Owns the Fyers WebSocket, broadcasts ticks, serves ~50 REST endpoints.
3. **One** trading book — `trading_bot/main.py` (live) *or* `paper_observer.py` (paper). Never both.
4. `ema9_variant_observer.py` — isolated research books (5m/ATM control vs 15m/ITM candidate).

Plus the Next.js dashboard on port 3000.

---

## 3. The Repository, Folder by Folder

```
AI trading Bot/
├── Start_AI_Bot.bat              Manual 3-window launcher (refuses if a session is live)
├── Start_Zero_Touch.bat          Menu: daemon / run-now / test-login / test-EOD
├── setup_windows_task.bat        Registers the 08:45 Windows Scheduled Task
├── CLAUDE.md, PROJECT_MAP.md     Repo guidance
├── .github/workflows/ci.yml      Lint + tests + build + secret scan
│
├── frontend/                     Next.js 16 · React 19 · Tailwind 4 · Zustand
│   ├── app/                      12 pages + 37 API proxy routes
│   ├── components/               25 shared components
│   ├── lib/backend.ts            The ONLY place that talks to :8000
│   └── store/                    3 Zustand stores
│
├── trading-system/               Python backend — the real system
│   ├── api_bridge.py             4,697 lines. FastAPI + WS + watchdogs
│   ├── auto_daily_session.py     1,440 lines. Zero-touch daily orchestrator
│   ├── paper_observer.py         1,052 lines. Main paper book
│   ├── ema9_variant_observer.py    740 lines. Shadow research books
│   │
│   ├── trading_bot/
│   │   ├── main.py               3,243 lines. THE live engine (async tick loop)
│   │   ├── portfolio_risk.py     Circuit breakers
│   │   ├── reconciliation.py     Broker-vs-book truth resolution
│   │   ├── iceberg_manager.py    Large-order slicing
│   │   ├── api/fyers_client.py   Thin Fyers REST wrapper
│   │   └── strategies/           12 registered strategies (see §6)
│   │
│   ├── brokers/                  Fyers (active) · Kite · Angel One
│   ├── shared/
│   │   ├── risk/                 RiskManager, option SL bands, portfolio guard
│   │   ├── exits/                SmartExitEngine, exit analyzer, pyramid sizer
│   │   ├── ai/                   XGBoost/RF trade filter + feature engineering
│   │   ├── alerts/               Telegram (HTML/Telugu) + 4K EOD card generator
│   │   ├── indicators/           EMA, RSI, ATR, MACD, ADX, Supertrend, SMC
│   │   ├── security/             Sessions, audit log, rate limiter, vault
│   │   ├── market_calendar.py    Exchange-sourced holidays
│   │   ├── instruments.py        Canonical symbol normalisation
│   │   └── state.py              SQLite + JSON persistence
│   │
│   ├── backtesting_engine/       Intraday option backtester + Monte Carlo
│   ├── validation_harness/       23 research scripts (see §10)
│   ├── drl/                      PPO env + 5-agent MARL swarm
│   ├── scripts/                  Auth, training, backups, audits
│   ├── config/                   settings.json + live runtime state
│   ├── data/  models/  logs/     CSV history, .pkl/.json models, logs
│   └── audit/                    Tamper-evident audit trail
│
├── Testing_Automation_AI_Trading_Bot/
│   ├── python-unit/              110 pytest files
│   ├── tests/ui/, tests/api/     8 Playwright specs
│   └── legacy-manual/            Probe scripts needing a live session
│
└── docs/                         16 design/audit/validation documents
    └── paper_trading_validation/
        ├── anomaly_log.md        4,701 lines — every incident, root-caused
        └── reports/              Per-session reports
```

---

## 4. A Trading Day, Minute by Minute

This is `auto_daily_session.py::run_session_flow()`. It is the spine of the
whole system.

### 08:45 — Wake & gate
- `is_trading_day()` checks weekend + `shared/market_calendar.py` holidays.
- The calendar is **fetched from the exchange** and cached (`config/market_holidays.json`).
  The old hardcoded table was wrong seven ways — it missed Ganesh Chaturthi on
  2026-09-14 and a full session ran into a closed exchange.
- `_guard_single_instance()` refuses to start if a session already runs.
- `session_already_ran(day)` makes a missed start recoverable without double-running.

### 08:46 — Headless authentication
- `scripts/auth/auto_login_fyers.py`: app-id + secret → auth URL → TOTP (`pyotp`)
  → PIN → access token.
- Token is cached **encrypted** in `.fyers_tokens.json` (AES-256-GCM, key in `.broker.key`).
- Bounded with a timeout — an unbounded hang here once blocked an entire session.

### 08:50 — Cleanup
- `kill_process_on_ports([8000, 3000])` — exact PID matching, not blind kills.
- `shared/maintenance.py` rotates logs, purges stale sessions.
- `shared/fyers_log_hygiene.py` bounds the Fyers SDK's own unbounded log files
  (they had grown to 38 MB and 54 MB).

### 09:00 — Boot the backend
- `api_bridge.py` starts on :8000, then polls `/health` until green.
- On startup it opens the Fyers WebSocket (`start_fyers_socket`) and launches
  three background schedulers: daily AI retrain, lot-size refresh, and the
  WebSocket broadcaster.

### 09:14 — Launch today's book

```python
live = live_trading_mode()          # reads settings.json → live_trading_mode
clear_stray_books()                 # nothing else may be holding the books
start_session_books(live)
```

- **Live mode** → `trading_bot/main.py` (places real orders).
- **Paper mode** → `paper_observer.py` (virtual fills at real bid/ask).
- Plus `ema9_variant_observer.py` in *both* modes — it is isolated research.

> **Why "exactly one"?** Both books write `config/active_positions.json` and
> both write equity. Running the pair corrupts each other's account view. This
> was learned the hard way and is now structurally enforced.

### 09:15 – 15:15 — The session

`ServiceSupervisor` polls each child process. If one dies it restarts it with
backoff; if it dies repeatedly and fast, it escalates to Telegram instead of
relaunching blindly.

Meanwhile `api_bridge.py` runs its own watchdogs (§15) and `main.py` runs the
tick loop (§5).

### 15:15 — Square-off
- Both paper engines close on a time-driven loop.
- The live engine's EOD exit lives inside `on_tick` — so a quiet feed used to
  mean **nothing closed and the position carried overnight**. Fixed 2026-09-19:
  `eod_squareoff_watchdog()` runs on a 30-second timer, fetches a fresh quote
  past the cutoff and drives `on_tick` directly — reusing the one exit path.
- A `✅ All opened positions are closed` confirmation is sent once, so silence
  never has to be read as "probably fine".

### 15:30 — EOD report
`generate_and_send_eod_report()` reads the day's session logs and produces:
- Win rate, P&L, ROI, trade-by-trade audit list
- A **4K "MANA AI" luxury card** rendered by `shared/alerts/image_generator.py`
- Telugu/English HTML Telegram message

### 15:35 — Teardown
`stop_all_subprocesses()`, `mark_session_done(day)`, sleep until tomorrow.

---

## 5. The Trade Decision Pipeline

This is `trading_bot/main.py::on_tick()` — ~1,300 lines, and the single most
important function in the repository. Every tick from the Fyers WebSocket runs
through it.

### Phase 0 — Kill switches (before anything else)

```
tick arrives
   │
   ├─ settings.emergency_stop?  ──► emergency_flatten_all_positions() ──► return
   │                                 (actively closes, not just freezes)
   ├─ exit_requests.json non-empty? ──► close_requested_positions()
   │                                 (dashboard "exit this position")
   └─ settings.is_active == False? ──► return  (halt, positions unmanaged)
```

Order matters: panic-exit is checked *ahead* of the plain halt, because
`is_active=False` only freezes processing — the wrong behaviour when the owner
needs everything flattened.

### Phase 1 — Manage open positions

For an option position, the incoming tick is the **index** price, not the
option's. So the engine fetches the option's real live premium on demand and
uses *that* for every exit decision. (An index level compared against a premium
stop is meaningless — a position once sat unmanaged for a full session while
its premium round-tripped through both target and stop.)

Exit checks, in order:

1. **The ratcheting stop ladder** (`exit_ladder.py`) — stop only ever moves up.
2. **EMA/RSI reversal exit** (`premium_health.py::evaluate_protective_exit`).
3. **SmartExitEngine** — ATR trailing, partial booking, time exit.
4. **AI Exit Analyzer** — urgency score on give-back from peak.
5. **EOD square-off** at 15:15.

### Phase 2 — Look for a new entry

Evaluated at most every **200 ms**. Every one of these gates must pass:

| # | Gate | Where | Why |
|---|---|---|---|
| 1 | Symbol has no open position, not already evaluating | `main.py` | One position per symbol |
| 2 | ≥ 50 warm-up bars | `CandleAggregator` | Indicators need history |
| 3 | **Latest bar is fresh** | `shared/market_hours.py` | Never trade a stale price. Holiday / feed outage / dead session all look identical, and the answer to all three is the same |
| 4 | AI confidence ≥ threshold | `shared/ai/model.py` | 0.60 default, 0.85 for `enhanced_ai` |
| 5 | **Per-instrument confidence** | `shared/risk/instrument_focus.py` | NIFTY/SENSEX at the strategy's bar; BANKNIFTY/FINNIFTY need 0.85 |
| 6 | Strategy returns ±1 | `registry.run_strategy` | The actual signal |
| 7 | Global institutional filters | `shared/filters/institutional.py` | Volume/EMA/VWAP/RSI/squeeze/CPR — unless the strategy owns them |
| 8 | **Option mapping succeeds** | `premium_selection/options_selector.py` | Spot > 0, strike computed, real contract exists. **Fails → abandon the trade** |
| 9 | Market hours | `shared/market_hours.py` | A real broker enforces this structurally; paper mode did not |
| 10 | **Entry cutoff 15:00** | `is_before_eod_cutoff` | Measured over 582 sessions: 15:05–15:15 entries lose −0.91%/trade; 22 of 23 died at the forced square-off |
| 11 | Macro sentiment | `shared/sentiment.py` | Blocks CE if sentiment < −0.5, PE if > +0.5 |
| 12 | Option stop-loss is tradeable | `shared/risk/option_stop_loss.py` | Premium-banded stop must be wider than the spread |
| 13 | **Portfolio guard** | `shared/risk/portfolio_guard.py` | Daily stop · max 1 same-direction position · per-trade risk ceiling |
| 14 | RiskManager `can_trade()` | `shared/risk/manager.py` | Daily loss %, drawdown, consecutive losses, trade cap (6/day) |
| 15 | `auto_trade_enabled` | settings | Master switch |
| 16 | Order rate limiter | `shared/security/rate_limiter.py` | Broker API protection |

### Phase 3 — Execute

```
sizing  → RiskManager.calculate_position_size(entry_premium, sl_price, confidence)
        × PortfolioRiskEngine.get_position_multiplier()   # capital protection
        → rounded to lot size (65 / 30 / 20)
        │
order   → OrderRequest → broker.place_order_async()
        → iceberg slicing if large (iceberg_manager.py)
        → exchange stop-loss order placed alongside
        │
record  → active_positions.json (atomic write)
        → state.db (SQLite)
        → audit log (tamper-evident)
        → Telegram trade alert
        → WebSocket broadcast to the dashboard
```

### Phase 4 — Mark to market

Unrealised M2M is recomputed and `update_equity()` is called. Option positions
are marked to the contract's **real bid** (what you'd actually get), while
entries fill at the **ask**. That asymmetry is deliberate realism.

---

## 6. The Strategy Layer

### How strategies are discovered

`trading_bot/strategies/registry.py` scans its own directory at import time.
Any `.py` file or package exposing `generate_signals(df, **kwargs)` is
auto-registered under its `STRATEGY_NAME`.

```python
registry = StrategyRegistry()
registry.autodiscover()        # ← runs at import
```

A strategy returns a `pandas.Series` of `1` (buy CE) / `-1` (buy PE) / `0`.

Two module constants let a strategy opt out of the global filter layer:
`OWNS_INSTITUTIONAL_FILTERS` ("I already applied these myself") and
`SKIP_INSTITUTIONAL_FILTERS` ("these don't apply to my design"). They are kept
separate on purpose — they are different claims, and a reader has to be able to
tell which is being made. This matters: `institutional_momentum` and the global
layer read `enable_squeeze_filter` with *opposite* signs, making the surviving
set `A & ~A` — zero trades, for that strategy's entire life.

### The 12 registered strategies

| Name | Kind | Status |
|---|---|---|
| **`ema9_rsi_momentum`** | EMA 9/20 cross + RSI 14 vs its EMA 20 | **DEFAULT — the owner's strategy** |
| `ema_rsi` | Original EMA/RSI | Legacy baseline |
| `ema_crossover` | Pure EMA cross | Baseline |
| `advanced_ai` | XGBoost predictions | IMPROVE |
| `enhanced_ai` | AI + RSI confirmation | Fixed 2026-08-08 (it confirmed both directions at once) |
| `institutional_momentum` | 8-layer institutional filter | Took zero trades for its entire life until 2026-08-09 |
| `premium` | Premium-selection engine, picks the contract itself | Special entry path |
| `momentum_15_5` | 15-min structure / 5-min trigger | Research |
| `structure_break` | Event-triggered clean-sheet baseline | Research |
| `buy_the_dip` | Mean reversion | Baseline |
| `meta_agent_swarm` | 5 sub-agents voting | Was silently running 4 |
| `ultra_meta_dip_swarm` | Swarm + dip | Research |
| `drl_strategy` | RecurrentPPO | **Verdict: REMOVE — market-blind** |
| `marl_strategy` | 5-agent MARL | Capital-protection deadlock fixed |

### The default strategy in detail: `ema9_rsi_momentum`

A package, not a file — because it has real structure:

```
ema9_rsi_momentum/
├── __init__.py          generate_signals() + evaluate_protective_exit()
├── config.py            Every knob, as a frozen dataclass
├── signal_engine.py     The actual cross logic
├── indicators.py        EMA/RSI computation (reuses shared/indicators)
├── premium_health.py    Post-entry decay classification + reversal exit
├── strike_selection.py  ATM vs ITM (target delta 0.70)
└── exit_ladder.py       The ratcheting stop ladder
```

**Entry rule:** EMA 9 crosses EMA 20 *and* RSI 14 crosses its own EMA 20 —
**on the same closed candle**. Plus ADX ≥ 18, time window 09:25–15:00, and an
EMA-touch filter.

**Edge-triggered.** `_signal_utils.edge_trigger` ensures the signal fires once
at the cross, not continuously while the state holds. This one change took
`ema_rsi` drawdown from 47.9% → 20.8%.

**Momentum bands** (RSI 40/50/60) are *informational only* — logged with every
signal, never an independent trigger.

**What it deliberately does NOT reimplement.** The module docstring is explicit:
ATM/ITM selection, stop-loss/target/sizing, institutional filters and the AI gate
all already exist and are reused via `main.py`'s generic tick loop. The only
genuinely new integration point is the EMA/RSI reversal *protection* layer, which
runs **alongside** (never instead of) `SmartExitEngine`.

**Configuration flows** `settings.json` → `ema9_rsi_<field>` keys →
`Ema9RsiMomentumConfig.from_settings()` → frozen dataclass per call. No shared
mutable state across calls.

### The ema9 variant book (ongoing experiment)

Since 2026-09-11, `ema9_variant_observer.py` runs two books in one process:

| Variant | Chart | Strike | Backtest (578 NIFTY sessions, after costs) |
|---|---|---|---|
| `5m_atm` | 5-min | ATM | **−2.89% per trade** (control = today's default) |
| `15m_itm` | 15-min | ITM (δ≈0.70) | **+2.25% per trade** (candidate) |

Both books share each poll's data: one 5-minute history fetch per index, from
which the 15-minute bars are built exactly as the backtest built them.

Defaults stay at 5m/ATM until the scorecard verdict (20 sessions + 20 trades,
~3 months). This is deliberately *not* rushed into production — 10- and 20-minute
charts lose, 2024 was flat, and SENSEX loses.

> **Why a separate observer at all?** `paper_observer.py` enters when
> `/api/signals` "bias" flips — a trend *state* where ADX and the EMA-touch rule
> only add or withhold points, never block. It takes trades the strategy
> refuses. On 2026-09-11 both its afternoon entries came on crosses the strategy
> blocked (ADX 14.5 and 16.4 < 18). Its results cannot measure the strategy.

### Option contract selection

`premium_selection/options_selector.py` holds `INSTRUMENT_CONFIG`, verified
against Fyers' live symbol master:

| Instrument | Lot | Strike step | Weekly expiry | Exchange |
|---|---|---|---|---|
| NIFTY | 65 | 50 | Tuesday | NSE |
| BANKNIFTY | 30 | 100 | Tuesday | NSE |
| SENSEX | 20 | 100 | Thursday | BSE |

The previous Thu/Wed/Fri values were stale, which made every computed expiry —
and therefore every option symbol — reference a contract that did not exist.

---

## 7. The Risk & Exit Layer

### Four independent layers of capital protection

**Layer 1 — `shared/risk/manager.py` · RiskManager (per-trade)**
- Position sizing from stop distance, scaled by AI confidence
- Daily loss limit (3% default), max drawdown, consecutive-loss tracking
- Daily counters roll over at **midnight IST**, not host-timezone midnight
  (a UTC-clocked server rolls over 5.5 hours late)
- Auto Risk-Off: halts trading and sends an alert

**Layer 2 — `trading_bot/portfolio_risk.py` · PortfolioRiskEngine (circuit breakers)**
- Returns a `position_multiplier` that shrinks size as drawdown grows
- Full halt at threshold, recorded to the tamper-evident audit trail

**Layer 3 — `shared/risk/portfolio_guard.py` · one rule for every engine**

The live engine, the main paper book and the variant books all call the same
`entry_block_reason()`, so a paper result stays a faithful preview of live.
Measured over 49 sessions where all three indices have data:

| rule | worst day | max drawdown | days < −3% |
|---|---|---|---|
| no cap (per-index only) | −10,282 | −53,899 | 12 |
| max 1 same-direction position | −6,861 | −41,446 | 6 |
| **+ 3% daily stop** | **−4,736** | **−35,538** | 8 |

The three indices move together (5-min return correlation 0.75–0.91; 61% of
signals have a same-direction signal on another index within 15 minutes) — so
three open CEs are **one bet taken three times**.

**Layer 4 — `shared/risk/option_stop_loss.py` · premium-banded stops**

A flat percentage stop does not survive contact with an option book. The live
setting was 0.45%: on a ₹120 premium that is a **₹0.54 stop — inside the
bid/ask spread**, guaranteeing a noise stop-out. The same percentage is
simultaneously far too wide for a ₹5 lottery strike (0.45% = ₹0.02) and far too
tight for a ₹300 deep-ITM contract.

Option premium is not a linear instrument: *rupee* volatility scales with price,
but *percentage* volatility falls as the contract goes deeper ITM. A single
percentage cannot express that; a band table can.

So: a **band table**, linearly interpolated within each band (so the stop rises
continuously instead of stepping at boundaries), handing over to a tapering
percentage above ₹250. Bands live in `settings.json` — tuning them never touches
the entry path.

### The exit: a ratcheting ladder, no fixed target

The owner's own words (2026-09-12): *"we use a trailing stop, so there is no
fixed target — if the move has room, the target should move up by itself, and
the trailing stop should keep moving up too, until the market reverses."*

```
rung reached (% gain):   15    33    50    75   100   150   200
stop moves to:            0    15    33    50    75   100   150
                     (breakeven)
```

Opening stop: 15% under entry. The stop **only ever moves up** — a stop already
higher is kept, and tick rounding always rounds *down* so it never tightens
past its rung. The "target" shown for a position is only ever the next rung.

A trade ends when: the stop is hit · the EMA/RSI reversal fires · or the 15:15
square-off. **Never because a target was reached.**

Measured before adoption (578 NIFTY sessions, same harness as every other result):

| | fixed 33% target | this ladder |
|---|---|---|
| 15-min ITM | +1.99%/trade, best +31% | **+2.25%/trade, best +106%** |
| 5-min ATM | −3.20%/trade | −2.89%/trade |

The first rung is the owner's original "stop to breakeven at +15%"; the second
is the old 33% target — now a rung to pass, not a place to stop.

### `shared/exits/exit_engine.py` · SmartExitEngine

Runs *alongside* (never instead of) the ladder: ATR-based dynamic trailing,
partial profit booking, time-based exit, volatility exit, and an opt-in
Fibonacci trail. One engine — no parallel exit systems.

---

## 8. The Broker Layer

```
BaseBroker (ABC)
    ├── FyersBroker    ← ACTIVE
    ├── KiteBroker     (Zerodha)
    └── AngelBroker    (Angel One)
```

`BrokerFactory` enforces a **single active broker** singleton, persisted in
`settings.json` so it survives restarts. Switching tears down the old one,
loads saved credentials, instantiates and authenticates the new one.

The abstract contract: `authenticate`, `place_order`, `cancel_order`,
`get_order_status`, `modify_order`, `get_positions`, `get_balance`,
`get_order_book`, `get_market_data`, `get_lot_size`, `get_historical_data`,
`stream_quotes`, `close`.

**Fyers specifics that mattered:**
- `_TimeoutHTTPAdapter` — every REST call is bounded. An unbounded hang once
  cost a ~2-hour undetected live-feed outage through market open.
- `_find_matching_pending_order` — prevents **duplicate orders** when a retry
  follows a transient failure.
- `history_cache.py` — caches OHLCV. It once persisted *forming* bars and kept
  stale ones; now it stores closed bars only and honours the requested range.
- `token_cache.py` — AES-256-GCM encrypted token storage.
- `on_close` callback signature was wrong, breaking every feed reconnect
  (fixed 2026-08-13 after four disconnects in one day).
- `lot_size_updater.py` — a scheduler refreshes lot sizes; exchanges change them.

---

## 9. The AI / ML Layer

### The trade filter (in production, optional)

`shared/ai/model.py` · `TradeFilterModel` — Random Forest with optional
XGBoost. It does **not** generate signals; it *scores* signals the strategy
already produced, and low-confidence ones are rejected.

- Features: `shared/ai/features.py` — price action, momentum, volatility,
  volume dynamics, ATR, ADX
- Artifacts: `models/xgboost_model.json`, `models/trade_filter_rf.pkl`
- Retraining: `scripts/train_ai_model.py`, scheduled daily by `api_bridge.py`
- **Gated deployment** — a fresh model is not auto-promoted; inline retrains
  during a session were removed (they blocked the event loop)
- Controlled by `enable_ai_filter`; when off or untrained, confidence = 1.0 and
  the system is purely rules-based
- Prediction runs on `asyncio.to_thread` and only on the last 100 rows — the
  full frame was a severe CPU bottleneck and latency spike

### Deep RL (research only)

- `drl/trading_env.py` — Gym environment
- `drl/train.py` + `scripts/train_drl_model.py` — RecurrentPPO (sb3-contrib)
- **`drl_strategy` verdict: REMOVE.** A test (`test_drl_strategy_market_blindness.py`)
  proved it produces the same action regardless of market input.

### MARL swarm (research only)

`drl/marl/` — five agents under a master: `alpha_agent` (signal quality),
`signal_agent`, `risk_agent`, `execution_agent` (IV-aware strike/theta/gamma),
`master_agent` (arbitration). Its LSTM state is now reset on restart rather
than reusing stale memory, and its capital-protection lock expires per IST
session instead of deadlocking permanently (it had traded 14 of 123 days, all
in February).

---

## 10. The Research & Validation Layer

This is what separates this project from a hobby bot. `validation_harness/`
(23 scripts) exists to answer *"does this change actually help?"* with numbers
instead of opinion.

| Script | Question it answers |
|---|---|
| `harness.py` | Core runner — reuses **real production components**, not a re-implementation |
| `run_strategy_audit.py` | Full audit of all 12 strategies |
| `classify.py` | KEEP / IMPROVE / REMOVE verdict per strategy |
| `entry_quality.py` | Are the entries any good? |
| `exit_quality.py` / `exit_replay.py` | Is the exit capturing the trend? |
| `run_filter_ablation.py` | What does each filter actually contribute? |
| `run_filter_significance.py` | Is that contribution statistically real? |
| `run_ab_validation.py` | A/B two configurations |
| `drawdown_attribution.py` | Where does the drawdown come from? |
| `regimes.py` | Performance by market regime |
| `market_realism.py` / `premium_simulator.py` | Costs, spread, intraday theta, simulated clock |
| `run_entry_information_test.py` | Does the entry carry information at all? |
| `run_selection_features.py` | Day/direction-level selection features |
| `monte_carlo.py` | Distribution of outcomes, not a single path |

**The 2026-08-08 audit outcome:** all 12 strategies classified — **3 KEEP,
7 IMPROVE, 2 REMOVE**. The original `PF ≥ 1.30` gate was replaced with a
derived production-readiness framework, because a fixed profit-factor bar is a
metric-gaming trap.

**Hypotheses tested and REJECTED** (documented, not quietly dropped):
- `institutional_momentum` filter hypothesis
- `ema_rsi` trailing-offset hypothesis
- Trailing activation is archetype-dependent — measured, **not shipped**,
  flagged as needing an architecture decision
- Entry-cutoff extension to 15:15 — measured, **kept at 15:00**
- A cooldown rule (2026-09-15) — measured **worse**

**A measurement bug that distorted everything:** the gap-day regime threshold
was mislabeling 36% of days, skewing every regime's statistics. Found and fixed
2026-08-07 — a reminder that the measuring instrument needs auditing too.

The backtester (`backtesting_engine/run.py`) charges brokerage + STT + slippage,
models **intraday theta on the premium**, and computes a dynamic Black-Scholes
delta (it used a flat 0.5 constant until 2026-08-18).

---

## 11. The API Bridge (FastAPI)

`api_bridge.py` — 4,697 lines, port 8000. It is the only process that talks to
the Fyers WebSocket, and everything else reads from it.

**Structure:**
- **Middleware** — `require_session_auth` validates a real server-side session token on every request
- **Startup** — log rotation, Fyers socket, three schedulers, watchdogs
- **`/ws/live`** — the broadcaster. Cadence *adapts* to load rather than a fixed interval
- **~50 REST endpoints**

**Endpoint groups:**

| Group | Endpoints |
|---|---|
| Market data | `/api/quote` `/api/history` `/api/option-chain` `/api/option-greeks` `/equity-data` |
| Signals | `/api/signals` `/api/strategies` `/api/strategy/parameters` |
| Trading | `/api/order/execute` `/api/positions` `/api/positions/exit` `/api/panic-exit` |
| Engine | `/api/engine/status` `/api/engine/toggle` `/api/bot/start` `/api/state` |
| Research | `/api/backtest` `/api/ai/status` `/api/ai/retrain` |
| Journal | `/api/journal` (full CRUD) |
| Config | `/api/settings` (GET/POST) `/api/risk` |
| Auth | `/api/auth/{status,me,register,login,logout,reset,setup}` |
| Broker | `/api/broker-auth-url` `/api/broker-login` `/api/test_connection` `/api/funds` |
| Ops | `/health` `/api/logs` `/api/inspect` `/api/trading-mode` |

**The hard rule this file learned:** *never fabricate market data.* The
2026-09-09 audit found the frontend inventing prices, signals and balances, and
option Greeks priced off a model rather than the real chain. Now:
`_fetch_real_option_chain()` uses the actual Fyers chain, India VIX is real,
max-pain/PCR/expiry are real, and when data is unavailable the endpoint **says
so** instead of guessing. The engine is gated on tick provenance.

**A quiet one worth knowing:** this file's root logger silently dropped every
INFO log since day one, found 2026-08-20. Everything looked fine because nothing
was being written at all.

---

## 12. The Frontend (Next.js)

**Stack:** Next.js 16 · React 19 · Tailwind 4 · Zustand · Recharts ·
lightweight-charts · framer-motion · sonner.

### Pages (`frontend/app/`)

| Route | What it is |
|---|---|
| `/` | Mission Control dashboard — equity, P&L, positions, kill switch |
| `/live` | Live trading terminal — chart, option chain, execution feed, trade panel |
| `/signals` | AI signal monitor |
| `/strategy` | Parameter tuning — 8 tabs (strategy, indicators, risk, execution, AI filters, option chain, notifications, advanced) |
| `/backtest` | Backtest runner + results |
| `/analytics` | Performance analytics + heatmaps |
| `/journal` | Trading journal (CRUD, backed by SQLite) |
| `/risk` | Risk management settings |
| `/broker` | Broker configuration and login |
| `/options` | Institutional options desk — Greeks, max pain, PCR |
| `/settings` | App preferences |
| `/docs` | In-app documentation |

### The proxy pattern

The browser **never** talks to :8000 directly. Every call goes through a Next.js
route handler in `app/api/*`, which uses `lib/backend.ts`:

```ts
export const BACKEND_URL = process.env.BACKEND_URL || 'http://127.0.0.1:8000';

export async function backendFetch(path, init = {}) {
  const token = await getSessionToken();        // httpOnly cookie
  headers.set('Authorization', `Bearer ${token}`);
  return fetch(`${BACKEND_URL}${path}`, { ...init, headers });
}
```

Two audit findings are closed by this one file: ~27 routes had hardcoded
`http://127.0.0.1:8000` (impossible to deploy split), and none forwarded
credentials (because the backend didn't check any).

### State

- `useLiveMarketStore` — ticks, positions, P&L (fed by `/ws/live`)
- `useLiveSettingsStore` — live trading preferences
- `useChartSettingsStore` — chart config

### The charting decision

TradingView was **replaced** (2026-06-16) with a custom `NativeChart` built on
`lightweight-charts`, fed directly from Fyers data. The system needed the chart
to show exactly what the engine sees, which an embedded third-party widget on
its own data feed cannot do.

---

## 13. State, Config & Persistence

| File | Holds | Written by |
|---|---|---|
| `config/settings.json` | **Single source of truth** for every tunable | UI → `/api/settings` |
| `config/active_positions.json` | Open positions — survives a crash | The active book (atomic write) |
| `config/exit_requests.json` | IPC: dashboard → engine "close this" | `api_bridge.py` |
| `config/market_holidays.json` | Exchange-fetched holiday cache | `market_calendar.py` |
| `config/sessions.json` | Server-side auth sessions | `shared/security/sessions.py` |
| `config/users.json` | Dashboard users (salted hashes) | `api_bridge.py` |
| `state.db` (SQLite) | Equity curve, trade history, journal | `shared/state.py` |
| `paper_obs_logs/` | Per-session paper trade logs | `paper_observer.py` |
| `paper_obs_logs/variants/` | Shadow-book logs (kept separate so EOD globs never mix them) | `ema9_variant_observer.py` |
| `models/` | Trained ML artifacts | Training scripts |
| `audit/` | Tamper-evident audit trail | `shared/security/audit_log.py` |

**`shared/state.py` design:** equity updates are write-through to an in-memory
cache and flushed every 3 seconds by a background thread — dozens of disk
round-trips per minute were blocking the async event loop. **Trades still flush
immediately** (critical data). Writes are atomic (temp file + replace, with
retry past transient Windows file locks).

**`settings.json` is read on every tick** — but `_load_settings()` caches by
file mtime, so it's a cheap `stat()` call and only re-parses when the file has
actually changed. That's what makes live parameter changes from the dashboard
take effect within one tick.

---

## 14. Security

| Concern | Implementation |
|---|---|
| Credentials at rest | AES-256-GCM, key in `.broker.key`, `shared/security/security_vault.py` |
| Token cache | Encrypted (`brokers/token_cache.py`) |
| Key rotation | `scripts/rotate_credential_key.py` |
| Auth | Real server-side sessions with unguessable tokens (`shared/security/sessions.py`) |
| Passwords | Salted hashes + complexity validation |
| Transport | httpOnly session cookie → Bearer token, never in `localStorage` |
| Rate limiting | `shared/security/rate_limiter.py` on order placement |
| Input validation | `shared/security/validator.py`, `symbol_parser.py` |
| Audit trail | `shared/security/audit_log.py` — every order, halt, circuit breaker |
| Log hygiene | `shared/security/log_filter.py` redacts secrets |
| CI | Secret scan on every push |

**The August 2026 security sprint** fixed three critical issues: the token cache
was unencrypted and tracked in git; the "session token" was a predictable
unsigned string (`mana_ai_auth_{user_id}_valid`) that anyone could fabricate for
any user id; and the dashboard Kill Switch wasn't wired to the real panic-exit
endpoint.

`save_broker_creds.py` also silently wiped unrelated credential fields until
2026-08-15 — a partial write that looked like a successful one.

---

## 15. Reliability: Watchdogs & Recovery

This layer is the largest single body of work in the repository, and every
piece of it exists because something failed in a real session.

### The watchdogs

| Watchdog | Lives in | Watches for |
|---|---|---|
| `fyers_feed_watchdog` | `api_bridge.py` | Upstream feed stalls (a silent 46-min stall happened) |
| `main_process_watchdog` | `api_bridge.py` | Engine freeze — detects and safely auto-recovers |
| `tick_staleness_watchdog` | `main.py` | An open position's underlying has stopped ticking |
| `heartbeat_writer` | `main.py` | "Is the event loop alive" signal, written via `asyncio.to_thread` |
| `position_reconciler` | `main.py` | Polls broker truth instead of only waiting for a reconnect |
| `eod_squareoff_watchdog` | `main.py` | Guarantees the 15:15 close even with no ticks |
| `ServiceSupervisor` | `auto_daily_session.py` | Child processes, with backoff and escalation |

### Real incidents this system has survived (all in `anomaly_log.md`)

- **39-minute total engine freeze** (2026-08-06, recurred) — root-caused to a
  `Series.__setitem__` antipattern causing a CPU livelock; fixed by rebuilding
  the filtered signal with `np.select`. A regression test now guards it, and the
  same antipattern was found again in a live strategy on 2026-08-28.
- **~12-hour heartbeat-write freeze** — the heartbeat write froze *itself*;
  wrapped in `asyncio.to_thread`.
- **~9.5-hour watchdog silence** — root-caused to Windows Modern Standby on
  battery. Not a code bug; the machine slept. (Wi-Fi power saving + missing
  battery wake timers.)
- **~2-hour undetected live-feed outage through market open** — unbounded
  startup auto-login subprocess call; now bounded.
- **Four WebSocket disconnects in one day** — `on_close` callback signature was
  wrong; self-healed after the fix.
- **Duplicate-launch outage** — two sessions fighting over the same ports and
  positions file. Now `Start_AI_Bot.bat` refuses to start while a session runs,
  and the orchestrator holds a singleton lock (with the TOCTOU race closed).
- **`api_bridge.py` uncollectable at startup** — blocked an entire paper session.
- **A network outage read as a closed exchange** — fixed 2026-09-16 by separating
  the two questions (`exchange_verdict()` weighs cached bars, network
  reachability, and silence duration).
- **History cache corruption** — persisted forming bars, kept stale ones.
- **Reconciliation matched options by substring**, not suffix.
- **Alerter.send_alert didn't exist** — three call sites were calling a method
  that was never defined.

### Disaster recovery

`shared/disaster_recovery.py` + `scripts/backup_state.py` /
`scripts/restore_state.py`. State survives contention and interruption — proved
under test (`test_disaster_recovery.py`), including the reconnect-while-holding-
a-position case.

Telegram alerts have an **outbox**: if a send fails, it spools to disk and
flushes on the next opportunity. An alert is never lost.

---

## 16. Testing & CI

### `Testing_Automation_AI_Trading_Bot/` — a separate, dedicated suite

- **110 Python unit files** (`python-unit/`) — pytest
- **8 Playwright specs** — `tests/ui/` (dashboard, journal, auth gate,
  navigation smoke, trading indices) and `tests/api/` (live backend, fixture
  contracts, mutation guard)
- **`legacy-manual/`** — 5 assertion-free probe scripts that need a live broker
  session; deliberately *not* collected by CI

**Test naming tells the story** — most are named after the bug they prevent:
`test_edge_trigger_livelock_regression.py`, `test_crash_retry_backoff.py`,
`test_drl_strategy_market_blindness.py`, `test_api_bridge_fyers_feed_watchdog.py`,
`test_daily_trade_cap_persistence.py`, `test_declared_dependencies.py`.

> **Operational rule:** always run the UI suite with `--workers=1`. Parallel runs
> against `npm run dev` produced 11 false failures on an unchanged tree.

### CI (`.github/workflows/ci.yml`)

Gates **every branch**: Python 3.11 backend tests (ruff syntax lint → pytest →
indicator smoke tests) + Node 20 frontend type-check and production build +
secret scan. All npm vulnerabilities cleared 2026-09-09.

---

## 17. How This Project Was Built — The Real Timeline

318 commits across five months. The shape of the effort is itself informative:

```
2026-05   ███ 7          Foundation
2026-06   ███████ 15     Features & UI
2026-07   ████ 8         Advanced strategies
2026-08   ████████████████████████████████████████████████ 219   THE HARDENING
2026-09   ███████████████ 69   Honesty & production readiness
```

### Phase 1 — Foundation (May 2026, v1.0–v1.5)

`78b86a5 Initial commit v1.0.0`

- Next.js dashboard + FastAPI bridge + Fyers integration
- Fyers WebSocket streaming and price-accuracy work
- Institutional UI standardisation, live ticker, persistent journal, panic exit
- Credential encryption and auto-verification

### Phase 2 — Features & UI (June 2026, v1.6–v2.1)

- **Automated Fyers login (TOTP/PIN)** — the foundation everything zero-touch
  would later stand on
- Institutional momentum strategy + 8-layer premium selection
- Advanced institutional filters wired into both bot and dashboards
- Continuous AI retraining pipeline + UI dashboard
- **TradingView replaced with a custom NativeChart** on real Fyers data
- GitHub Actions CI added
- Log and `.db` files untracked from git

### Phase 3 — Advanced strategies (July 2026, v2.2–v2.8)

- HFT upgrades, WebSocket-optimised UI rendering, AI Live Analyst
- Ultra Meta-Dip Swarm; stable backtesting engine; pyramiding fix; 1-year Fyers
  cache fix
- Institutional Options Desk (Greeks, max pain, PCR)
- Deep RL (PPO) with 20-year historical training
- Auth UI redesign
- State recovery and breaking-news alerts

### Phase 4 — **The Hardening** (August 2026 — 219 commits)

This is where the project changed character. It began with
`c2b4f09 chore: checkpoint pre-audit WIP` on 2026-08-01, and everything after
is a response to what the audit found.

**Week 1 — Security & correctness blitz (2026-08-01)**

Eleven fixes in one day: encrypted token cache · real server-verified auth ·
kill switch actually wired · duplicate-order prevention on retry · in-flight
lock on pyramid scale-in · real exit price on reconnect (it was assuming
stop-loss) · cross-process equity cache refresh · **stopped fabricating
strategy validation statistics** · MARL LSTM state reset.

**Week 2 — The validation harness (2026-08-07 → 08-10)**

`e398604 feat(validation): Production Strategy Validation Harness — isolated
backtest framework reusing real production components`

Then the discipline that follows from having one:
- Regime thresholds were mislabeling 36% of days, distorting every statistic
- `meta_agent_swarm` was running 4 brains, not 5
- `institutional_momentum` took **zero trades on the production path** — for its
  entire life — and its production exit path had never executed either
- `drl_strategy` is market-blind → **REMOVE**
- `enhanced_ai`'s RSI layer confirmed BOTH directions at once
- `ema_rsi` and `advanced_ai` re-entry churn fixed by edge-triggering
- All 12 strategies classified: 3 KEEP / 7 IMPROVE / 2 REMOVE
- Two hypotheses tested and **rejected**, documented as rejections

**Week 3 — Live-incident hardening (2026-08-12 → 08-21)**

Every commit in this stretch is a root-caused production incident: heartbeat,
freeze detection, singleton-lock TOCTOU, feed reconnect, Modern Standby,
unbounded subprocess calls, the silently-dropped root logger. The reliability
audit on 2026-08-14 returned **GO for that audit's scope**.

**Week 4 — Research tooling** (2026-08-26, v2.11.0)

Institutional Paper Observer, advanced option chart, system resilience. Plus a
DRL training pipeline and broker/lot-size/risk regression coverage.

### Phase 5 — Honesty & production readiness (September 2026, v2.12 → v3.15)

**v2.12.0 (09-01)** — EMA9/RSI Momentum strategy, live chart enhancements,
smart exit engine, broker resilience.

**v3.13.0 (09-08)** — MANA AI 4K EOD card, Telugu HTML alerts, **zero-touch
daily orchestrator**, perpetual paper trading.

**2026-09-09 — the fabricated-data audit.** 22 findings in 13 commits. The
headline: **fabricated market data had reached the live engine.** Fixed in one
sweep — the real Fyers option chain wired, Greeks stop being priced off a guess,
the frontend stops inventing prices/signals/balances, the engine is gated on
tick provenance, XGBoost artifacts anchored and their deployment gated, the
orchestrator supervises children instead of relaunching them blindly.

**v3.14.0 (09-09)** — strategy-aware signals, EMA9/RSI as the default.

**September 10–19 — the options-buyer audit.** The most careful work in the
project:
- Fill at the ask, mark to the bid, real theta
- Charge option carrying costs on the premium; model theta in the backtest
- The owner's ratcheting ladder in *every* engine — no option hair-trigger trail
- One portfolio rule shared by every engine
- Entry IV and India VIX recorded; optional VIX gate (off by default)
- The 15m/ITM shadow book, run beside a 5m/ATM control, in one process
- History cache stops persisting forming bars
- Live trades only UI-selected indices; paper tests all three
- 2026-09-15: **first profitable paper session**
- **v3.15.0**: holidays from the exchange · launcher refuses a double session ·
  the Live/Paper toggle decides what actually runs · dashboard exits route
  through the engine · guaranteed 15:15 square-off with Telegram confirmation

### What the shape of the timeline says

Months 1–3 built features. Month 4 discovered that several of them did not do
what they claimed. Month 5 made the system tell the truth about itself. The
219-commit August is not a detour — it is where this became a system you could
put money behind.

---

## 18. Design Principles That Emerged

These are not stated anywhere as rules; they are visible in how the code is
written and in what got rejected.

**1. Never fabricate data.**
The single most-repeated fix. If a price, a Greek, a volume or a statistic
isn't real, the system says so rather than inventing a plausible number. An
invented number in a trading system is worse than an error, because it looks
like an answer.

**2. Root-cause everything, then write the test.**
Almost every fix commit explains *what happened in production*, with a date.
Most have a regression test named after the bug. `anomaly_log.md` is 4,701
lines of this.

**3. One rule, one place.**
`shared/instruments.py` exists because the same symbol remap was re-derived
inline at two call sites and they drifted (`"BSE:SENSEX"` silently failed to
match `INSTRUMENT_CONFIG`). `portfolio_guard.py` exists so paper and live can't
diverge. `lib/backend.ts` exists so 27 routes don't each hardcode a URL.

**4. Measure before shipping; document rejections.**
The entry-cutoff extension, the trailing offset, the momentum filter hypothesis,
the cooldown rule — all measured, all rejected, all written down. Rejected
hypotheses are as valuable as accepted ones, and only exist if you record them.

**5. Improve the owner's strategy; don't substitute your own.**
When a strategy underperforms, the work is to find the defect in *it* — not to
propose a different strategy. The 15m/ITM variant is an execution variant of
the same rules, run as a shadow book, not a replacement.

**6. Paper must be a faithful preview of live.**
Same portfolio guard, same exit ladder, same fills-at-ask / marks-at-bid, same
costs and theta. A paper result that flatters you is worse than no paper result.

**7. Exactly one book.**
Two engines sharing a positions file corrupt each other. Structurally enforced
at three levels now: the orchestrator picks one, the launcher refuses, the
singleton lock blocks.

**8. Prefer a verdict to a default.**
The 15m/ITM variant is measurably better in backtest and is *still* not the
default — it waits for 20 live paper sessions and 20 trades.

**9. Comments carry the incident, not the mechanics.**
The codebase's comments rarely say what a line does; they say what went wrong
without it, with a date. That's why this document could be written from the
source at all.

---

## 19. Current Status & What Remains

**Branch:** `trading-bot_V3.15.0` · **Mode:** paper · **Verdict:** NO-GO for live

The production-readiness clock (`docs/GO_NO_GO_CHECKLIST.md`) has been reset
several times — most recently twice on 2026-08-12 — because the rule is that a
clean, uninterrupted validation window is required, and each unexplained
anomaly restarts it. Check `docs/paper_trading_validation/anomaly_log.md`
before assuming readiness.

**Open items:**

| Item | Status |
|---|---|
| ema9 variant scorecard (20 sessions + 20 trades) | In progress since 2026-09-11 |
| Trailing activation architecture decision | Measured, not shipped — needs a decision |
| `drl_strategy` removal | Verdict REMOVE, execution pending approval |
| `.env` secrets + `settings.json` credential migration | User action |
| `docs/TRADING_SYSTEM_ARCHITECTURE_GUIDE_TELUGU.md` | Untracked — not yet committed |

**Known-good operational facts:**
- 2026-09-15 was the first profitable paper session
- A cooldown rule was tested and measured **worse**
- The 15:00 entry cutoff is measured and kept
- Both engines now confirm the square-off on Telegram

---

## 20. Quick Reference

### Start the system

```bash
# Zero-touch daemon (recommended) — wakes at 08:45 every trading day
Start_Zero_Touch.bat          → option 1

# Run today's session immediately
cd trading-system && .\venv\Scripts\python.exe auto_daily_session.py --now

# Manual 3-window launch
Start_AI_Bot.bat

# Individual services
cd trading-system && uvicorn api_bridge:app --port 8000
cd frontend && npm run dev
```

### Common tasks

```bash
# Fyers login
cd trading-system && python scripts/auth/auto_login_fyers.py

# Backtest
python scripts/run_backtest.py

# Train the AI filter
python scripts/train_ai_model.py

# Full strategy audit
python validation_harness/run_strategy_audit.py

# Health check
python scripts/paper_trading_healthcheck.py

# Tests
cd Testing_Automation_AI_Trading_Bot
npm run py:test                      # 110 Python unit tests
npx playwright test --workers=1      # UI — ALWAYS serial
```

### Key files, by "I need to change X"

| I want to change… | Edit |
|---|---|
| Any tunable parameter | `trading-system/config/settings.json` (or the `/strategy` UI) |
| The entry rule | `trading_bot/strategies/ema9_rsi_momentum/signal_engine.py` |
| The exit ladder | `trading_bot/strategies/ema9_rsi_momentum/exit_ladder.py` |
| Stop-loss bands | `settings.json` → `option_sl_bands` |
| Portfolio limits | `shared/risk/portfolio_guard.py` |
| The daily schedule | `auto_daily_session.py` |
| A REST endpoint | `api_bridge.py` + a proxy in `frontend/app/api/` |
| Telegram message format | `shared/alerts/telegram.py` |
| The EOD card | `shared/alerts/image_generator.py` |
| Lot sizes / expiry days | `premium_selection/options_selector.py` → `INSTRUMENT_CONFIG` |

### Critical invariants — do not break these

1. **Exactly one book runs.** Never `main.py` and `paper_observer.py` together.
2. **Options only.** If option mapping fails, abandon the trade — never trade the index.
3. **Never fabricate a price, Greek, or statistic.** Say "unavailable".
4. **The stop only ratchets up.** Never widens.
5. **Live trades only UI-selected indices.** Paper tests all three.
6. **The UI test suite runs `--workers=1`.**
7. **Daily counters roll at midnight IST**, not host-local midnight.
8. **Signals are edge-triggered**, never level-triggered.

---

### Related documents

| Document | What it covers |
|---|---|
| `docs/TRADING_SYSTEM_ARCHITECTURE_GUIDE_TELUGU.md` | File-by-file guide in Telugu (what/why/benefit per file) |
| `docs/GO_NO_GO_CHECKLIST.md` | The production-readiness gate (43 KB) |
| `docs/paper_trading_validation/anomaly_log.md` | Every incident, root-caused (4,701 lines) |
| `docs/STRATEGY_AUDIT_2026-08-07.md` | The 12-strategy audit (68 KB) |
| `docs/STRATEGY_IMPROVEMENT_BACKLOG.md` | Open research items (93 KB) |
| `docs/OPTION_STOP_LOSS_ARCHITECTURE.md` | Why premium-banded stops |
| `docs/ATR_TRAILING_STOP_DESIGN_2026-08-07.md` | Trailing-stop design work |
| `docs/PRODUCTION_STRATEGY_VALIDATION_FRAMEWORK.md` | How strategies are judged |
| `docs/DISASTER_RECOVERY.md` | Backup/restore procedure |
| `docs/ATM_ITM_AND_MULTI_INSTRUMENT_ARCHITECTURE.md` | Strike selection and multi-index design |

---

*Generated by analysing 318 commits, ~43,700 lines of Python, 116 frontend
files, 118 test files, and 16 design documents.*
