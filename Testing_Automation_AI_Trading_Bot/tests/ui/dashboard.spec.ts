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

/**
 * The P&L tile is "Day's Net P&L" = realized + unrealized.
 *
 * Its two sources measure different things: the live socket's `total_pnl`
 * already includes open mark-to-market, while `/api/state`'s `pnl` is
 * realized only. These specs used to assert the realized-only figure, which
 * passed for the wrong reason -- the page preferred the socket and only fell
 * back to REST when the socket's total was exactly zero, so the tile silently
 * changed meaning with tick timing. Assert the total, and drive the socket
 * when a flat or losing day is what is being described.
 */
test.describe('Dashboard metrics', () => {
  test('equity and P&L tiles show the backend values @smoke', async ({ dashboardPage }) => {
    await dashboardPage.goto();

    const state = buildState();
    const unrealized = buildPositionsResponse().positions.reduce(
      (sum, position) => sum + position.unrealized_pnl,
      0,
    );

    await dashboardPage.expectEquity(state.equity);
    // realized (-74.35) + open mark-to-market, not realized alone.
    await dashboardPage.expectDailyPnl(state.pnl + unrealized);
  });

  test('a losing day is presented as a loss', async ({ dashboardPage, mockBackend }) => {
    // A losing day means the TOTAL is negative; the socket is what the tile
    // reads while it is connected, so the loss has to come from the tick.
    await mockBackend.setTick({ pnl: -74.35, unrealized_pnl: -1_200.4, total_pnl: -1_274.75 });

    await dashboardPage.goto();

    await dashboardPage.expectDailyPnl(-1_274.75);
    expect(await dashboardPage.dailyPnl()).toBeLessThan(0);
    expect(await dashboardPage.dailyPnlSign()).toBe('negative');
  });

  test('a fresh account shows starting capital and no P&L', async ({
    dashboardPage,
    mockBackend,
  }) => {
    await mockBackend.override(ProxyRoutes.state, flatState);
    await mockBackend.override(ProxyRoutes.positions, emptyPositions);
    await mockBackend.setTick({
      pnl: 0,
      unrealized_pnl: 0,
      total_pnl: 0,
      equity: 100_000,
      open_positions_count: 0,
      positions_detail: [],
    });

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
