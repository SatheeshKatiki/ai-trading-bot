/**
 * The suite's `test` object. Specs import from here, never from
 * `@playwright/test` directly.
 *
 * Everything a spec needs is a declared fixture, so a spec body contains
 * assertions and nothing else — no `new DashboardPage(page)`, no manual mock
 * installation, no login boilerplate. Fixtures are lazy: a spec that asks for
 * `dashboardPage` pays for that page object only.
 */
import { test as base, expect, type Page } from '@playwright/test';
import { env } from '@config/environment';
import { ApiClient } from '@core/api-client';
import { createLogger } from '@core/logger';
import { MockBackend } from '@mocks/backend-mock';
import { AuthPage } from '@pages/auth.page';
import { DashboardPage } from '@pages/dashboard.page';
import { JournalPage } from '@pages/journal.page';
import {
  AboutPage,
  AnalyticsPage,
  BacktestPage,
  BrokerPage,
  DocsPage,
  LiveTradingPage,
  OptionsDeskPage,
  RiskPage,
  SettingsPage,
  SignalsPage,
  StrategyPage,
} from '@pages/shell.pages';
import { HeaderComponent } from '@pages/components/header.component';
import { SidebarComponent } from '@pages/components/sidebar.component';

const log = createLogger('Fixtures');

export interface TestFixtures {
  /** Fixture-backed backend. Installed before the page navigates anywhere. */
  mockBackend: MockBackend;
  /** Typed HTTP client for API specs, pre-authenticated in live mode. */
  api: ApiClient;

  authPage: AuthPage;
  dashboardPage: DashboardPage;
  journalPage: JournalPage;
  liveTradingPage: LiveTradingPage;
  backtestPage: BacktestPage;
  signalsPage: SignalsPage;
  strategyPage: StrategyPage;
  optionsDeskPage: OptionsDeskPage;
  analyticsPage: AnalyticsPage;
  brokerPage: BrokerPage;
  riskPage: RiskPage;
  settingsPage: SettingsPage;
  docsPage: DocsPage;
  aboutPage: AboutPage;

  sidebar: SidebarComponent;
  header: HeaderComponent;
}

export interface WorkerFixtures {
  /** Session token for live-mode API calls; empty in mocked mode. */
  sessionToken: string;
}

export const test = base.extend<TestFixtures, WorkerFixtures>({
  /**
   * One login per worker rather than per test — the backend's login path runs
   * PBKDF2 and has account-lockout counters, so logging in on every test both
   * slows the run and can trip the lockout the auth specs rely on.
   */
  sessionToken: [
    async ({ playwright }, use) => {
      if (env.target !== 'live') {
        await use('');
        return;
      }

      const { userId, password } = env.credentials;
      if (!userId || !password) {
        throw new Error(
          'TEST_TARGET=live needs TEST_USER_ID and TEST_USER_PASSWORD (see .env.example).',
        );
      }

      const context = await playwright.request.newContext({ baseURL: env.backendURL });
      const response = await context.post('/api/auth/login', {
        data: { user_id: userId, password },
        failOnStatusCode: false,
      });

      if (!response.ok()) {
        throw new Error(
          `Live login failed (${response.status()}): ${await response.text()}`,
        );
      }

      const body = (await response.json()) as { token?: string };
      if (!body.token) {
        throw new Error('Live login returned no token.');
      }

      log.info('Live session established for API specs');
      await use(body.token);
      await context.dispose();
    },
    { scope: 'worker' },
  ],

  /**
   * Auto-used on purpose.
   *
   * Interception has to be in place before the first navigation, including
   * for specs that never mention `mockBackend`. Making it a normal fixture
   * would leave those specs racing the mock and reaching the real backend for
   * their first request; overriding `page` instead would form a fixture cycle.
   */
  mockBackend: [
    async ({ page }, use) => {
      const mock = new MockBackend(page);
      if (env.target === 'mocked') {
        await mock.install();
      }
      await use(mock);
    },
    { auto: true },
  ],

  api: async ({ request, sessionToken }, use) => {
    await use(new ApiClient(request, sessionToken || undefined));
  },

  authPage: async ({ page }, use) => use(new AuthPage(page)),
  dashboardPage: async ({ page }, use) => use(new DashboardPage(page)),
  journalPage: async ({ page }, use) => use(new JournalPage(page)),
  liveTradingPage: async ({ page }, use) => use(new LiveTradingPage(page)),
  backtestPage: async ({ page }, use) => use(new BacktestPage(page)),
  signalsPage: async ({ page }, use) => use(new SignalsPage(page)),
  strategyPage: async ({ page }, use) => use(new StrategyPage(page)),
  optionsDeskPage: async ({ page }, use) => use(new OptionsDeskPage(page)),
  analyticsPage: async ({ page }, use) => use(new AnalyticsPage(page)),
  brokerPage: async ({ page }, use) => use(new BrokerPage(page)),
  riskPage: async ({ page }, use) => use(new RiskPage(page)),
  settingsPage: async ({ page }, use) => use(new SettingsPage(page)),
  docsPage: async ({ page }, use) => use(new DocsPage(page)),
  aboutPage: async ({ page }, use) => use(new AboutPage(page)),

  sidebar: async ({ page }, use) => use(new SidebarComponent(page)),
  header: async ({ page }, use) => use(new HeaderComponent(page)),
});

export { expect };
export type { Page };
