# AI Trading Bot - Project Progress & Conversation Summary

This file contains a summary of all the major changes, fixes, and features implemented during our conversation. It serves as a reference and backup.

> **Staleness notice (root-cause fix for a Medium-severity finding in the
> 2026-08-01 full-system audit):** everything below "Work Accomplished &
> Features Added" describes one specific session from mid-May 2026. It
> predates — and does not mention — the DRL/MARL strategy layer, the
> options desk, the current auth/session system, or the 2026-08-01/08-02
> audit remediation pass (80 findings across Critical/High/Medium/Low
> severity, resolved one-by-one with root-cause fixes, tests, and one git
> commit per issue on `trading_bot_v2.10.0`). This file was never a
> formal architecture reference — it's an informal per-session log — so
> rather than reconstruct an exhaustive history this update doesn't have,
> treat this whole file as a historical snapshot of one early session,
> not current documentation. For what's actually true today: `git log
> --oneline` on `trading_bot_v2.10.0` for the real change history, or the
> codebase itself (trading_bot/, brokers/, drl/, shared/, api_bridge.py)
> for current architecture. A brief, accurate current-state summary is
> added at the bottom of this file instead of rewriting the log below.

## 🚀 Work Accomplished & Features Added

### 1. AI Confidence Score Improvements (Smart Circle)
- **Issue:** The AI confidence score was not updating properly and looked generic.
- **Fix:** 
  - Implemented a custom SVG-based **Smart Circle** (circular progress bar) with a dynamic linear gradient (Red to Yellow to Green).
  - Fixed color contrast issues for percentage text in light mode.
  - Removed `df = df.copy()` in `advanced_ai_ml_strategy.py` to allow score updates to reflect in the UI.

### 2. Persistent AI Score After Market Close & Refresh
- **Issue:** Refreshing the page after market hours reset the AI confidence score to `0%` because the latest incomplete candle had no calculation.
- **Fix:**
  - Initialized `call_score` and `put_score` with `None` instead of `0` in `advanced_ai_ml_strategy.py` so `dropna()` correctly finds the last valid score.
  - Modified the WebSocket loop in `api_bridge.py` to **freeze** the score after market hours (3:30 PM) so it doesn't try to fetch non-existent new data.
  - Added a persistent file storage (`last_confidence.json`) to save the last calculated score, so it survives API Bridge restarts!

### 3. Frontend Timeout Fix
- **Issue:** The UI was showing "Scanning..." because the API was timing out.
- **Fix:** Increased the fetch timeout for `/api/signals` from 2000ms to 5000ms in `frontend/app/api/state/route.ts`.

### 4. Live Trade Execution Notifications
- **Issue:** Requested a system to show live notifications when paper trades are executed.
- **Fix:**
  - Implemented a custom notification system in `frontend/app/live/page.tsx` using `framer-motion` for smooth animations.
  - Added a `useEffect` to compare trades and detect new ones.
  - Supported message formats for **BUY, SELL, Target Hit**, and **Stop Loss Hit**.

### 5. Project Migration to D Drive
- **Issue:** C Drive was getting full ("system storage" issue).
- **Fix:**
  - Successfully moved the project from `C:\Users\Windows\Desktop\Claud project\AI trading Bot` to `D:\Projects\AI trading Bot`.
  - Used `robocopy` excluding heavy folders like `node_modules` and `venv`.
  - Reinstalled fresh dependencies in the new location.
  - Updated paths in `startup_commands.txt`.

## 📌 Current State (as of the May 2026 session above — see staleness notice at top)
- **Frontend Path:** `D:\Projects\AI trading Bot\frontend`
- **Backend Path:** `D:\Projects\AI trading Bot\trading-system`
- **Backup of Old Files:** Still present on C drive desktop (User plans to delete after verification).

## 🏗️ Current Architecture Summary (added 2026-08-02, replaces the need to guess from the stale log above)

High-level shape of the system today, not tied to any single session:

- **Frontend** (`frontend/`): Next.js 16 / React 19 dashboard. Next.js API
  routes under `app/api/**` act as a backend-for-frontend proxy layer —
  they attach the caller's session (httpOnly cookie) and forward to the
  FastAPI backend; the browser never talks to the backend directly.
- **Backend, two separate processes:**
  - `api_bridge.py` — FastAPI server the dashboard talks to (settings,
    backtests, journal, auth, panic-exit, etc.). Session-token
    authentication middleware gates every route except a small public
    allowlist (login/register/health).
  - `trading_bot/main.py` — the standalone async live trading engine,
    run separately (`python -m trading_bot.main`), not part of the
    FastAPI process. Consumes broker tick streams, evaluates strategies,
    manages positions/exits, and persists state to SQLite.
- **Brokers** (`brokers/`): a common `BaseBroker` interface with adapters
  for Fyers (default/active), Kite, and Angel One, selected at runtime
  via `BrokerFactory`. Credentials are stored encrypted
  (`brokers/credentials.py`, Fernet).
- **Strategy layer** (`trading_bot/strategies/`): rule-based strategies
  (EMA/RSI, EMA crossover, institutional momentum, premium/options
  selection) alongside a DRL strategy (PPO via `sb3-contrib`) and a MARL
  multi-agent strategy (`drl/marl/` — SignalAgent, ExecutionAgent,
  RiskAgent, AlphaAgent orchestrated by a MasterAgent). Selected via
  `active_strategy` in `trading-system/config/settings.json` — the one
  canonical settings file (two other settings.json files exist
  elsewhere in the repo and are legacy/unused, not sources of truth).
- **Backtesting** (`backtesting_engine/run.py`): one canonical engine,
  `run_intraday_backtest()`, used by every tool that runs a backtest
  (the dashboard's `/api/backtest`, `grid_search.py`, the
  `WalkForwardValidator`, `audit_script.py`).
- **Security**: session-based auth (`shared/security/sessions.py`),
  encrypted broker credentials, and a tamper-evident, HMAC-chained audit
  trail (`shared/security/audit_log.py`) covering trade entries/exits,
  auth events, risk-circuit-breaker trips, and admin actions.
- **Deployment**: Docker Compose (`deployment/docker-compose.yml`) runs
  the live engine and the (legacy) Streamlit dashboard as separate
  containers from a shared, non-root Dockerfile.

For anything more specific than this — exact function signatures, line
numbers, current bug status — read the code directly; this summary will
itself go stale the moment the architecture changes again.

## 📅 Last Updated
*Original log: 14 May 2026. Staleness notice + architecture summary added: 2 August 2026.*
