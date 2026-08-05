# Architecture

## Layers

```
tests/                    specs — assertions only
  ui/                     browser journeys
  api/                    contract + safety specs
        ↓ imports
src/fixtures/test.ts      the single entry point specs import
        ↓ provides
src/pages/                page objects (intent, not selectors)
src/mocks/                fixture-backed backend + payload builders
src/core/                 api client · mutation guard · base page · logger
src/config/               environment · route + endpoint catalogue
src/types/  src/utils/    payload types · schema checker · contracts
```

Dependencies point one way: specs → fixtures → page objects → core → config.
Nothing in `src/` imports from `tests/`.

## Why the mocked target is the default

The application under test is a live trading system with a single shared
instance. `api_bridge.py` binds port 8000 unconditionally, `main.py` reloads
`config/settings.json` every tick, and both processes read and write
`state.db`. There is no way to start a second, isolated backend without
changing application code.

That makes the usual "run E2E against a dev stack" answer unsafe here. The
project's own history is the argument: on 2026-08-05 a combination of test
output and reconciliation bugs corrupted `state.db` beyond reconstruction,
forcing a full reset and restarting the go/no-go validation clock. The
Python suite already carries a docstring warning about a test that once wrote
to the real `settings.json`.

So the default target intercepts every `/api/**` request inside the browser
(`src/mocks/backend-mock.ts`). The Next.js frontend is real — routing,
rendering, state management, error boundaries all execute — but no request
reaches the Python process. Runs are deterministic, parallel-safe, and can
execute during market hours while the engine is trading.

### What that costs, and how it is paid for

A mocked suite can drift into testing a backend that does not exist. Two
mechanisms prevent it:

1. **Shared schemas.** `src/utils/api-contracts.ts` declares each response
   shape once. `tests/api/fixtures.contract.spec.ts` enforces it against the
   fixtures; `tests/api/backend.live.spec.ts` enforces the *same* schemas
   against the real backend. A contract change fails one side or the other.
2. **Fixtures derived from the source.** Every fixture's shape was read out of
   the code that produces it (`shared/sentiment.py`, the Next.js proxy routes,
   `brokers/models.py`), not invented. Where a mismatch slipped in, the UI
   specs caught it immediately — see below.

## The mutation guard

`src/core/mutation-guard.ts` is deny-by-default: against a live backend, every
`POST`/`PUT`/`PATCH`/`DELETE` throws unless `ALLOW_MUTATIONS=1` is set, which
is itself rejected in CI and in mocked mode.

The endpoint catalogue in `src/config/routes.ts` splits `readOnly` from
`mutating`. That split is load-bearing, not documentation — and it is tested
(`tests/api/mutation-guard.contract.spec.ts`), because a guard that silently
stopped working would be discovered by a polluted database.

One subtlety worth knowing: classification is **exact-match**, not
prefix-match. `/api/panic-exit/status` is a read that sits directly beneath
the write path `/api/panic-exit`. An earlier prefix-matching implementation
classified it as a mutation, which would have made the kill switch
unverifiable from a live run — the exact capability §2.8 of the go/no-go
checklist needs. Safety is not lost by being exact: unknown write paths are
still blocked by the method check.

## Fixtures and page objects

`src/fixtures/test.ts` exports the `test` object specs import. Everything is
lazy — asking for `dashboardPage` builds only that.

`mockBackend` is an **auto** fixture. Interception must be installed before
the first navigation, including in specs that never mention it; making it
opt-in would leave those specs racing the mock, and overriding the built-in
`page` fixture instead creates a fixture cycle (Playwright rejects it).

`sessionToken` is **worker-scoped**: the backend's login path runs PBKDF2 and
has account-lockout counters, so logging in per test would be both slow and
capable of tripping the lockout the auth specs assert on.

Page objects extend `BasePage`, which waits on each page's own root element
rather than `networkidle` — this dashboard polls several endpoints on
intervals and holds an open WebSocket, so network activity never settles and
`networkidle` would time out on a perfectly healthy page.

## Test data

`src/mocks/scenarios.ts` builds every payload deterministically: no
`Math.random()`, no `Date.now()`, timestamps anchored to a fixed trading day.
P&L is computed from prices rather than hardcoded, and one fixture is a
**short position in profit** (LTP below entry) — the exact configuration that
`exit_engine.py` and later `PyramidSizer` both got backwards in production.

## Bugs this suite found while being written

Not hypothetical value — these came out of the first runs:

- **The dashboard crashes if `/api/sentiment` omits `top_headlines`.**
  `NewsTicker` assigns the response into state and reads `top_headlines[i]`
  with no guard, so a partial payload takes down the entire page with a
  runtime `TypeError` rather than degrading.
- **The Options Desk crashes on an empty option chain.** `getPayoffData()`
  calls `chain.reduce(...)` with no initial value → "Reduce of empty array".
- **The Analytics page crashes on a partial payload.** `stats.expectancy` and
  friends are dereferenced unguarded.

All three are real robustness gaps in the frontend — a backend hiccup that
returns a shape other than the happy path blanks the screen instead of
degrading. The fixtures were corrected to match the real contracts (so the
specs pass), and the gaps are written up rather than silently worked around.

## The Python suite

`python-unit/` is the suite migrated out of `trading-system/tests/`. It stays
pytest because most of it instantiates Python objects in-process
(`SmartExitEngine`, `PyramidSizer`, `RiskManager`, reconciliation logic) —
TypeScript cannot replace that, and rewriting it as HTTP-level tests would
lose the unit-level coverage that took several incidents to build.

`_bootstrap.py` is the single place that knows where the application code is;
`conftest.py` imports it and `chdir`s to `trading-system/`, preserving the
working directory the tests were written against.

Five files did not move with it. `probe_connection.py`, `probe_funds.py`,
`probe_nifty.py`, `probe_history.py` and `probe_backtest.py` are in
`legacy-manual/`: they have no assertions, need a live broker session, and two
had a client ID hardcoded. `inject_mock_trade.py` (formerly
`scripts/e2e_test.py`) is there too — it writes fabricated rows into the live
trading journal, and now refuses to run without an explicit
`--write-to-live-journal` flag.
