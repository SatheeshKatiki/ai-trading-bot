/**
 * Single source of truth for "what is this run pointed at, and what is it
 * allowed to do".
 *
 * The platform under test has no isolated test instance: `api_bridge.py`
 * hardcodes port 8000, holds a singleton lock, and reads/writes the same
 * `state.db`, `config/settings.json` and `config/active_positions.json` that
 * the live paper-trading engine depends on. A suite that talks to it
 * carelessly does not just produce flaky results — it corrupts the trading
 * journal that the go/no-go validation window is built on (this has already
 * happened once; see docs/paper_trading_validation/anomaly_log.md,
 * 2026-08-05).
 *
 * So the target is an explicit, validated decision made once, here, rather
 * than an ad-hoc `process.env.X ?? default` scattered across specs.
 */
import { config as loadDotenv } from 'dotenv';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

const HERE = path.dirname(fileURLToPath(import.meta.url));

/** `<repo>/Testing_Automation_AI_Trading_Bot` */
export const SUITE_ROOT = path.resolve(HERE, '..', '..');
/** `<repo>` */
export const REPO_ROOT = path.resolve(SUITE_ROOT, '..');
/** `<repo>/frontend` — the Next.js app the UI specs drive. */
export const FRONTEND_ROOT = path.join(REPO_ROOT, 'frontend');

loadDotenv({ path: path.join(SUITE_ROOT, '.env'), quiet: true });

/**
 * What the suite talks to.
 *
 * - `mocked` (default): the real Next.js frontend, with every `/api/**`
 *   response served from fixtures inside the browser context. Deterministic,
 *   parallel-safe, and physically incapable of reaching the Python backend.
 * - `live`: the real FastAPI backend on port 8000. Opt-in, and still
 *   read-only unless {@link Environment.allowMutations} is set.
 */
export type TestTarget = 'mocked' | 'live';

function parseTarget(raw: string | undefined): TestTarget {
  const value = (raw ?? 'mocked').trim().toLowerCase();
  if (value === 'mocked' || value === 'live') return value;
  throw new Error(
    `Invalid TEST_TARGET "${raw}". Expected "mocked" (default) or "live".`,
  );
}

function parseBoolean(raw: string | undefined, fallback = false): boolean {
  if (raw === undefined || raw.trim() === '') return fallback;
  return ['1', 'true', 'yes', 'on'].includes(raw.trim().toLowerCase());
}

function parseInteger(raw: string | undefined, fallback: number): number {
  if (raw === undefined || raw.trim() === '') return fallback;
  const parsed = Number.parseInt(raw, 10);
  if (Number.isNaN(parsed)) {
    throw new Error(`Expected an integer, got "${raw}".`);
  }
  return parsed;
}

export interface Environment {
  /** Where responses come from. See {@link TestTarget}. */
  readonly target: TestTarget;
  /** Next.js dashboard base URL. */
  readonly baseURL: string;
  /** FastAPI `api_bridge.py` base URL — only reachable when `target` is `live`. */
  readonly backendURL: string;
  /**
   * Whether specs may call endpoints that write to the trading system
   * (`/api/order/execute`, `/api/panic-exit`, `POST /api/settings`,
   * `/api/engine/toggle`, ...). Off by default even in live mode; see
   * {@link module:core/mutation-guard}.
   */
  readonly allowMutations: boolean;
  /** Credentials for the live-mode dashboard session. */
  readonly credentials: { readonly userId: string; readonly password: string };
  /** Start `npm run dev` for the frontend if nothing answers on `baseURL`. */
  readonly manageFrontend: boolean;
  readonly isCI: boolean;
  readonly retries: number;
  readonly workers: number | undefined;
  readonly actionTimeoutMs: number;
  readonly expectTimeoutMs: number;
  readonly testTimeoutMs: number;
  readonly headless: boolean;
  /** Emit framework-level diagnostics (mock hits, guard decisions, API calls). */
  readonly verbose: boolean;
}

function build(): Environment {
  const isCI = parseBoolean(process.env.CI);
  const target = parseTarget(process.env.TEST_TARGET);
  const allowMutations = parseBoolean(process.env.ALLOW_MUTATIONS);

  if (allowMutations && target !== 'live') {
    throw new Error(
      'ALLOW_MUTATIONS is only meaningful with TEST_TARGET=live; in mocked ' +
        'mode nothing reaches the backend to mutate.',
    );
  }
  if (allowMutations && isCI) {
    throw new Error(
      'ALLOW_MUTATIONS must never be set in CI — it authorises writes ' +
        'against a real trading backend.',
    );
  }

  return {
    target,
    baseURL: process.env.BASE_URL ?? 'http://localhost:3000',
    backendURL: process.env.BACKEND_URL ?? 'http://127.0.0.1:8000',
    allowMutations,
    credentials: {
      userId: process.env.TEST_USER_ID ?? '',
      password: process.env.TEST_USER_PASSWORD ?? '',
    },
    manageFrontend: parseBoolean(process.env.MANAGE_FRONTEND, true),
    isCI,
    retries: parseInteger(process.env.TEST_RETRIES, isCI ? 2 : 0),
    workers: process.env.TEST_WORKERS
      ? parseInteger(process.env.TEST_WORKERS, 1)
      : undefined,
    actionTimeoutMs: parseInteger(process.env.ACTION_TIMEOUT_MS, 15_000),
    expectTimeoutMs: parseInteger(process.env.EXPECT_TIMEOUT_MS, 10_000),
    testTimeoutMs: parseInteger(process.env.TEST_TIMEOUT_MS, 60_000),
    headless: parseBoolean(process.env.HEADLESS, true),
    verbose: parseBoolean(process.env.VERBOSE_LOGS),
  };
}

/** Resolved once per process; importing this module never has side effects
 *  beyond reading `.env`. */
export const env: Environment = build();

export const isLive = (): boolean => env.target === 'live';
export const isMocked = (): boolean => env.target === 'mocked';
