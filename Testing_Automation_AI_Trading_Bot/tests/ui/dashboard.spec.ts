/**
 * The dashboard renders what the backend actually returned.
 *
 * These are value assertions, not "the element exists" assertions: the bugs
 * this system has produced were wrong *numbers* and wrong *signs* reaching a
 * screen that looked perfectly healthy.
 */
import { expect, test } from '@fixtures/test';
import { ProxyRoutes } from '@config/routes';
import {
  brokerUnauthenticatedPositions,
  buildLongPosition,
  buildPositionsResponse,
  buildShortPosition,
  buildState,
  emptyPositions,
  flatState,
} from '@mocks/scenarios';

test.describe('Dashboard metrics', () => {
  test('equity and P&L tiles show the backend values @smoke', async ({ dashboardPage }) => {
    await dashboardPage.goto();

    const state = buildState();
    await dashboardPage.expectEquity(state.equity);
    await dashboardPage.expectDailyPnl(state.pnl);
  });

  test('a losing day is presented as a loss', async ({ dashboardPage }) => {
    await dashboardPage.goto();

    // buildState()'s pnl is -74.35 — the sign must survive formatting.
    await dashboardPage.expectDailyPnl(-74.35);
    expect(await dashboardPage.dailyPnl()).toBeLessThan(0);
    expect(await dashboardPage.dailyPnlSign()).toBe('negative');
  });

  test('a fresh account shows starting capital and no P&L', async ({
    dashboardPage,
    mockBackend,
  }) => {
    await mockBackend.override(ProxyRoutes.state, flatState);
    await mockBackend.override(ProxyRoutes.positions, emptyPositions);

    await dashboardPage.goto();

    await dashboardPage.expectEquity(100_000);
    await dashboardPage.expectDailyPnl(0);
  });
});

test.describe('Active positions table', () => {
  test('renders one row per open position @smoke', async ({ dashboardPage }) => {
    await dashboardPage.goto();

    await expect(dashboardPage.positionsTable).toBeVisible();
    await dashboardPage.expectPositionCount(2);
  });

  test('shows each position with its own prices and P&L', async ({ dashboardPage }) => {
    await dashboardPage.goto();
    await dashboardPage.expectPositionCount(2);

    const long = buildLongPosition();
    const rendered = await dashboardPage.positions();
    const renderedLong = rendered.find((row) => row.symbol === long.symbol);

    expect(renderedLong).toBeDefined();
    expect(renderedLong?.averagePrice).toBeCloseTo(long.average_price, 2);
    expect(renderedLong?.ltp).toBeCloseTo(long.ltp, 2);
    expect(renderedLong?.pnl).toBeCloseTo(long.unrealized_pnl, 2);
  });

  /**
   * The regression this suite exists for.
   *
   * A short/PUT position whose premium *fell* is in profit. `exit_engine.py`
   * and then `PyramidSizer` both got this backwards in production — the second
   * time causing the system to scale into a losing position believing it was
   * winning. If the UI ever renders that as a loss, it is showing the operator
   * the same inverted view the engine had.
   */
  test('a short position in profit is shown as profit, not loss', async ({
    dashboardPage,
  }) => {
    await dashboardPage.goto();
    await dashboardPage.expectPositionCount(2);

    const short = buildShortPosition();
    expect(short.ltp).toBeLessThan(short.average_price);
    expect(short.unrealized_pnl).toBeGreaterThan(0);

    const row = await dashboardPage
      .positions()
      .then((rows) => rows.find((candidate) => candidate.symbol === short.symbol));

    expect(row?.pnl).toBeCloseTo(short.unrealized_pnl, 2);
    expect(row?.pnlSign).toBe('positive');
  });

  test('shows an empty state when nothing is open', async ({
    dashboardPage,
    mockBackend,
  }) => {
    await mockBackend.override(ProxyRoutes.positions, emptyPositions);

    await dashboardPage.goto();

    await dashboardPage.expectNoPositions();
  });

  test('an unauthenticated broker leaves the page usable', async ({
    dashboardPage,
    mockBackend,
  }) => {
    // The backend answers 200 with status:"error" here rather than failing —
    // the dashboard must treat that as "no positions", not crash.
    await mockBackend.override(ProxyRoutes.positions, brokerUnauthenticatedPositions);

    await dashboardPage.goto();

    await expect(dashboardPage.root).toBeVisible();
    await dashboardPage.expectNoPositions();
  });

  test('scales to a larger book without dropping rows', async ({
    dashboardPage,
    mockBackend,
  }) => {
    const many = Array.from({ length: 12 }, (_, index) =>
      buildLongPosition({ symbol: `NSE:TESTSYM${index}CE` }),
    );
    await mockBackend.override(ProxyRoutes.positions, buildPositionsResponse(many));

    await dashboardPage.goto();

    await dashboardPage.expectPositionCount(12);
  });
});

test.describe('Dashboard resilience', () => {
  test('survives a backend 500 on state', async ({ dashboardPage, mockBackend }) => {
    await mockBackend.failWith(ProxyRoutes.state, 500);

    await dashboardPage.goto();

    // The shell must still render — a failed poll is not a reason to show
    // the operator a blank screen mid-session.
    await expect(dashboardPage.root).toBeVisible();
    await expect(dashboardPage.sidebar.root).toBeVisible();
  });

  test('survives a slow positions response', async ({ dashboardPage, mockBackend }) => {
    await mockBackend.delay(ProxyRoutes.positions, 3_000);

    await dashboardPage.goto();

    await expect(dashboardPage.root).toBeVisible();
    await expect(dashboardPage.positionsTable).toBeVisible({ timeout: 15_000 });
  });
});
