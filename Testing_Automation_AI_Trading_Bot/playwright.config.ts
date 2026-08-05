/**
 * Playwright configuration.
 *
 * Projects are the safety boundary, not just an organisational one:
 * `ui-mocked`/`api-mocked` cannot reach the Python backend, and the `*-live`
 * projects only exist when a run explicitly asks for them with
 * `TEST_TARGET=live`. That way "run the suite" can never accidentally mean
 * "drive the live paper-trading engine".
 */
import { defineConfig, devices } from '@playwright/test';
import { env, FRONTEND_ROOT } from './src/config/environment';

const isLive = env.target === 'live';

export default defineConfig({
  testDir: './tests',
  outputDir: './test-results',
  snapshotDir: './tests/__snapshots__',

  fullyParallel: true,
  /** A `.only` left in a spec fails the CI run instead of silently shrinking it. */
  forbidOnly: env.isCI,
  retries: env.retries,
  workers: env.workers ?? (env.isCI ? 2 : undefined),
  timeout: env.testTimeoutMs,
  expect: { timeout: env.expectTimeoutMs },

  reporter: [
    ['list'],
    ['html', { outputFolder: 'reports/html', open: 'never' }],
    ['json', { outputFile: 'reports/results.json' }],
    ...(env.isCI ? ([['github']] as const) : []),
  ],

  use: {
    baseURL: env.baseURL,
    headless: env.headless,
    actionTimeout: env.actionTimeoutMs,
    navigationTimeout: env.actionTimeoutMs * 2,
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    video: env.isCI ? 'retain-on-failure' : 'off',
    testIdAttribute: 'data-testid',
    /** IST, so market-hours logic in the UI behaves as it does in production. */
    timezoneId: 'Asia/Kolkata',
    locale: 'en-IN',
  },

  projects: [
    {
      name: 'ui-mocked',
      testDir: './tests/ui',
      use: { ...devices['Desktop Chrome'] },
    },
    {
      name: 'api-mocked',
      testDir: './tests/api',
      /** Contract specs that assert on shapes, served from fixtures. */
      testMatch: /.*\.contract\.spec\.ts/,
      use: { ...devices['Desktop Chrome'] },
    },
    ...(isLive
      ? [
          {
            name: 'api-live',
            testDir: './tests/api',
            testMatch: /.*\.live\.spec\.ts/,
            use: { ...devices['Desktop Chrome'] },
          },
          {
            name: 'ui-live',
            testDir: './tests/ui',
            testMatch: /.*\.smoke\.spec\.ts/,
            use: { ...devices['Desktop Chrome'] },
          },
        ]
      : []),
  ],

  /**
   * The dashboard has to be running for UI specs either way; `reuseExistingServer`
   * means a developer's own `npm run dev` is used as-is rather than fought over
   * port 3000. Never started in live mode — there the environment is expected
   * to already be up and under observation.
   */
  ...(env.manageFrontend && !isLive
    ? {
        webServer: {
          command: 'npm run dev',
          cwd: FRONTEND_ROOT,
          url: env.baseURL,
          reuseExistingServer: !env.isCI,
          timeout: 180_000,
          stdout: 'ignore' as const,
          stderr: 'pipe' as const,
        },
      }
    : {}),
});
