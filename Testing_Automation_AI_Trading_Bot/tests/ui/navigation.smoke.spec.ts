/**
 * Every screen is reachable and renders its own shell.
 *
 * The broadest, cheapest signal the suite has: it catches a page that crashes
 * on mount, a route that 404s after a rename, and a nav link pointing at the
 * wrong href — all of which are invisible to the Python test suite and to
 * `next build`, which only proves the code compiles.
 */
import { expect, test } from '@fixtures/test';
import { AppRoutes, NavigationItems } from '@config/routes';
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

test.describe('Navigation @smoke', () => {
  test('sidebar renders every navigation entry', async ({ dashboardPage, sidebar }) => {
    await dashboardPage.goto();

    await expect(sidebar.root).toBeVisible();
    await sidebar.expectAllItemsPresent();

    const labels = await sidebar.visibleLabels();
    expect(labels).toEqual(NavigationItems.map((item) => item.label));
  });

  test('the current page is marked active in the sidebar', async ({
    dashboardPage,
    sidebar,
  }) => {
    await dashboardPage.goto();
    await sidebar.expectActive('dashboard');

    await sidebar.navigateTo('journal');
    await sidebar.expectActive('journal');
    await expect(sidebar.activeLink()).toHaveCount(1);
  });

  /**
   * Constructed from `page` rather than pulled from a fixture by name:
   * Playwright decides which fixtures to build by reading the destructured
   * parameter names, so a dynamic `fixtures[name]` lookup yields `undefined`.
   */
  const pageObjects = [
    { key: 'dashboard', Klass: DashboardPage },
    { key: 'liveTrading', Klass: LiveTradingPage },
    { key: 'backtest', Klass: BacktestPage },
    { key: 'signals', Klass: SignalsPage },
    { key: 'strategy', Klass: StrategyPage },
    { key: 'journal', Klass: JournalPage },
    { key: 'optionsDesk', Klass: OptionsDeskPage },
    { key: 'analytics', Klass: AnalyticsPage },
    { key: 'broker', Klass: BrokerPage },
    { key: 'risk', Klass: RiskPage },
    { key: 'settings', Klass: SettingsPage },
    { key: 'docs', Klass: DocsPage },
    { key: 'about', Klass: AboutPage },
  ] as const;

  for (const { key, Klass } of pageObjects) {
    test(`${key} page loads and renders its shell`, async ({ page, sidebar }) => {
      const pageObject = new Klass(page);

      await pageObject.goto();

      await expect(pageObject.root).toBeVisible();
      await pageObject.expectAtRoute();
      await expect(sidebar.root).toBeVisible();
    });
  }

  test('an unknown route does not render an app shell', async ({ page }) => {
    const response = await page.goto('/this-route-does-not-exist');

    expect(response?.status()).toBe(404);
    await expect(page.getByTestId('dashboard-page')).toBeHidden();
  });

  test('every catalogued route is covered by a spec above', () => {
    // Guards the table above against drifting behind config/routes.ts —
    // a new page added to the app without a smoke test fails here.
    const covered = new Set(pageObjects.map(({ key }) => AppRoutes[key]));
    const catalogued = Object.values(AppRoutes);

    expect([...covered].sort()).toEqual([...catalogued].sort());
  });
});
