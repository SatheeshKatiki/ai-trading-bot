/** Trading Journal (`/journal`) — the closed-trade record from `trade_journal`. */
import type { Locator, Page } from '@playwright/test';
import { expect } from '@playwright/test';
import { AppRoutes, type AppRoute } from '@config/routes';
import { BasePage } from '@core/base-page';
import { HeaderComponent } from '@pages/components/header.component';
import { SidebarComponent } from '@pages/components/sidebar.component';

export class JournalPage extends BasePage {
  readonly name = 'Trading Journal';
  protected readonly route: AppRoute = AppRoutes.journal;
  protected readonly rootTestId = 'journal-page';

  readonly sidebar: SidebarComponent;
  readonly header: HeaderComponent;

  constructor(page: Page) {
    super(page);
    this.sidebar = new SidebarComponent(page);
    this.header = new HeaderComponent(page);
  }

  get table(): Locator {
    return this.byTestId('journal-table');
  }

  get rows(): Locator {
    return this.byTestId('journal-row');
  }

  row(symbol: string): Locator {
    return this.root.locator(`[data-testid="journal-row"][data-symbol="${symbol}"]`);
  }

  async rowCount(): Promise<number> {
    return this.rows.count();
  }

  /**
   * Retrying row-count assertion. Rows arrive from a `/api/journal` fetch
   * after mount, so a plain `rowCount()` races the render.
   */
  async expectRowCount(expected: number): Promise<void> {
    await expect(this.rows).toHaveCount(expected);
  }

  /** Profit/loss classification per row, as the page computed it. */
  async pnlSigns(): Promise<('positive' | 'negative')[]> {
    const signs = await this.rows.evaluateAll((rows) =>
      rows.map((row) => row.getAttribute('data-pnl-sign')),
    );
    return signs.map((sign) => (sign === 'negative' ? 'negative' : 'positive'));
  }

  async expectRowVisible(symbol: string): Promise<void> {
    await expect(this.row(symbol)).toBeVisible();
  }
}
