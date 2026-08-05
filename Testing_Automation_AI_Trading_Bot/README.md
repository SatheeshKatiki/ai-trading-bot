# Testing_Automation_AI_Trading_Bot

All automated testing for the QuantAI trading platform lives here.

| Directory | What it is | Runner |
|---|---|---|
| `tests/ui/` | Browser end-to-end specs against the Next.js dashboard | Playwright + TypeScript |
| `tests/api/` | Contract specs for the FastAPI surface and the framework's own safety logic | Playwright + TypeScript |
| `src/` | The framework: config, fixtures, page objects, mock backend, API client | TypeScript |
| `python-unit/` | The backend unit/integration suite, migrated from `trading-system/tests/` | pytest |
| `legacy-manual/` | Assertion-free broker probes and the `state.db` seeder — **not** part of any suite | manual |

## Quick start

```bash
cd Testing_Automation_AI_Trading_Bot
npm install
npx playwright install chromium
npm test
```

That runs the full mocked suite. It needs no Python backend, no broker
session, and no market data — the frontend is real, everything behind it is
served from fixtures.

## The safety model

The platform has no isolated test instance. `api_bridge.py` hardcodes port
8000, holds a singleton lock, and reads and writes the same `state.db`,
`config/settings.json` and `config/active_positions.json` that the live
paper-trading engine depends on. Test pollution here is not a flaky-test
problem — it corrupted the trading journal badly enough on 2026-08-05 to
force a full reset and restart the validation clock.

So the suite is layered by how much it is allowed to touch:

| Target | Command | Reaches the backend? | Can write? |
|---|---|---|---|
| `mocked` (default) | `npm test` | **No** — `/api/**` is intercepted in the browser | n/a |
| `live`, read-only | `npm run test:live:api` | Yes, GETs only | No — guard blocks writes |
| `live`, unlocked | `TEST_TARGET=live ALLOW_MUTATIONS=1 npx playwright test` | Yes | Yes — deliberate, local only |

`ALLOW_MUTATIONS` is refused outright when `CI=1`, and refused in mocked mode.
The endpoints it gates are catalogued in `src/config/routes.ts` under
`ApiEndpoints.mutating` — order execution, panic exit, engine toggle, settings
writes.

## Commands

```bash
npm test                 # full mocked suite (UI + contracts)
npm run test:ui          # UI specs only
npm run test:api         # contract specs only
npm run test:smoke       # everything tagged @smoke
npm run test:headed      # watch it drive a real browser
npm run test:debug       # Playwright inspector
npm run test:live:api    # read-only specs against the real backend
npm run report           # open the last HTML report
npm run typecheck        # tsc --noEmit
npm run lint             # eslint (typed rules)
npm run verify           # typecheck + lint + test
npm run py:test          # the migrated pytest suite
```

The Python suite runs from the application root, which is where its own
`conftest.py` puts it:

```powershell
cd trading-system
.\venv\Scripts\python.exe -m pytest ..\Testing_Automation_AI_Trading_Bot\python-unit
```

## Configuration

Copy `.env.example` to `.env`. Every value has a safe default; an empty file
runs the mocked suite. The interesting ones:

- `TEST_TARGET` — `mocked` (default) or `live`
- `ALLOW_MUTATIONS` — unlock write endpoints in live mode
- `TEST_USER_ID` / `TEST_USER_PASSWORD` — dashboard account for live specs
- `MANAGE_FRONTEND` — start `npm run dev` if nothing is on port 3000
- `VERBOSE_LOGS` — framework diagnostics (mock hits, guard decisions, timings)

## Writing a spec

Import from the fixture module, never from `@playwright/test` directly — that
is what wires in the mock backend, the page objects, and the guard.

```ts
import { expect, test } from '@fixtures/test';
import { ProxyRoutes } from '@config/routes';
import { emptyPositions } from '@mocks/scenarios';

test('shows an empty state when nothing is open', async ({ dashboardPage, mockBackend }) => {
  await mockBackend.override(ProxyRoutes.positions, emptyPositions);

  await dashboardPage.goto();

  await dashboardPage.expectNoPositions();
});
```

Rules that keep this suite from rotting:

1. **No raw locators in specs.** If you need a new element, add it to the page
   object. Specs contain assertions, not selectors.
2. **Use the retrying assertions** (`expectPositionCount`, `expectEquity`,
   `expect(locator).toHaveCount(...)`). Data arrives after mount; a bare
   `count()` races the render and passes for the wrong reason.
3. **Fixtures must match the real payload.** `tests/api/fixtures.contract.spec.ts`
   enforces this against the same schemas the live specs use.
4. **Prefer `data-testid`.** The frontend is instrumented for this; add an
   attribute rather than keying off copy or DOM structure.

See `docs/ARCHITECTURE.md` for how the layers fit together and why.
