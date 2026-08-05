/**
 * The main dashboard (`/`): equity and P&L tiles, the active-positions table,
 * and the execution terminal.
 */
import type { Locator, Page } from '@playwright/test';
import { expect } from '@playwright/test';
import { AppRoutes, type AppRoute } from '@config/routes';
import { BasePage } from '@core/base-page';
import { HeaderComponent } from '@pages/components/header.component';
import { SidebarComponent } from '@pages/components/sidebar.component';

/** One row of the active-positions table, as rendered. */
export interface RenderedPosition {
  symbol: string;
  averagePrice: number;
  ltp: number;
  pnl: number;
  pnlSign: 'positive' | 'negative';
}

export class DashboardPage extends BasePage {
  readonly name = 'Dashboard';
  protected readonly route: AppRoute = AppRoutes.dashboard;
  protected readonly rootTestId = 'dashboard-page';

  readonly sidebar: SidebarComponent;
  readonly header: HeaderComponent;

  constructor(page: Page) {
    super(page);
    this.sidebar = new SidebarComponent(page);
    this.header = new HeaderComponent(page);
  }

  get equityTile(): Locator {
    return this.byTestId('metric-equity');
  }

  get dailyPnlTile(): Locator {
    return this.byTestId('metric-daily-pnl');
  }

  get positionsTable(): Locator {
    return this.byTestId('positions-table');
  }

  get positionRows(): Locator {
    return this.byTestId('position-row');
  }

  get positionsEmptyState(): Locator {
    return this.byTestId('positions-empty');
  }

  /** Equity as a number, with the en-IN grouping stripped. */
  async equity(): Promise<number> {
    return this.parseCurrency(await this.textOf(this.equityTile));
  }

  async dailyPnl(): Promise<number> {
    return this.parseCurrency(await this.textOf(this.dailyPnlTile));
  }

  /**
   * Wait for the equity tile to settle on a value.
   *
   * The tile renders its `useState` default (₹100,000.00) before the first
   * `/api/state` response lands, so a plain read can catch the placeholder.
   */
  async expectEquity(expected: number): Promise<void> {
    await expect.poll(() => this.equity()).toBeCloseTo(expected, 2);
  }

  async expectDailyPnl(expected: number): Promise<void> {
    await expect.poll(() => this.dailyPnl()).toBeCloseTo(expected, 2);
  }

  /** Sign as the component computed it, not as the CSS class suggests. */
  async dailyPnlSign(): Promise<'positive' | 'negative'> {
    const sign = await this.dailyPnlTile.getAttribute('data-pnl-sign');
    return sign === 'negative' ? 'negative' : 'positive';
  }

  async positionCount(): Promise<number> {
    return this.positionRows.count();
  }

  /**
   * Wait for the table to hold exactly `expected` rows.
   *
   * Positions arrive from a `/api/positions` fetch after mount, so a bare
   * `count()` races the render and passes or fails depending on machine
   * speed. Every spec that reads position data should await this first — it
   * is the retrying assertion that makes the subsequent reads deterministic.
   */
  async expectPositionCount(expected: number): Promise<void> {
    await expect(this.positionRows).toHaveCount(expected);
  }

  /** Read the whole positions table back as data. */
  async positions(): Promise<RenderedPosition[]> {
    const count = await this.positionRows.count();
    const rows: RenderedPosition[] = [];

    for (let index = 0; index < count; index += 1) {
      const row = this.positionRows.nth(index);
      const pnlCell = row.getByTestId('position-pnl');
      rows.push({
        symbol: (await row.getByTestId('position-symbol').innerText()).trim(),
        averagePrice: this.parseCurrency(await row.getByTestId('position-avg-price').innerText()),
        ltp: this.parseCurrency(await row.getByTestId('position-ltp').innerText()),
        pnl: this.parseCurrency(await pnlCell.innerText()),
        pnlSign:
          (await pnlCell.getAttribute('data-pnl-sign')) === 'negative'
            ? 'negative'
            : 'positive',
      });
    }
    return rows;
  }

  /** The row for one symbol, for per-position assertions. */
  positionRow(symbol: string): Locator {
    return this.root.locator(
      `[data-testid="position-row"][data-symbol="${symbol}"]`,
    );
  }

  async expectNoPositions(): Promise<void> {
    await expect(this.positionsEmptyState).toBeVisible();
    await expect(this.positionsTable).toBeHidden();
  }
}
