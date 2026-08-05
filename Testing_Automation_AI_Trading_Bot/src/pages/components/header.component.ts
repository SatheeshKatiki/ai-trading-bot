/**
 * The top bar: market-open state and the real-time P&L pill fed by the
 * live WebSocket.
 */
import type { Locator, Page } from '@playwright/test';
import { expect } from '@playwright/test';

export class HeaderComponent {
  constructor(private readonly page: Page) {}

  get root(): Locator {
    return this.page.getByTestId('app-header');
  }

  get marketStatus(): Locator {
    return this.page.getByTestId('market-status');
  }

  get livePnl(): Locator {
    return this.page.getByTestId('header-live-pnl');
  }

  /** Whether the dashboard currently holds an open tick socket. */
  async isWebSocketConnected(): Promise<boolean> {
    return (await this.root.getAttribute('data-ws-connected')) === 'true';
  }

  async isMarketOpen(): Promise<boolean> {
    return (await this.marketStatus.getAttribute('data-market-open')) === 'true';
  }

  /**
   * Sign of the displayed live P&L, read from the component's own state
   * rather than inferred from CSS colour — the colour is a styling detail,
   * the sign is the assertion.
   */
  async pnlSign(): Promise<'positive' | 'negative'> {
    const sign = await this.livePnl.getAttribute('data-pnl-sign');
    return sign === 'negative' ? 'negative' : 'positive';
  }

  async openPositionsCount(): Promise<number> {
    const raw = await this.livePnl.getAttribute('data-open-positions');
    return Number.parseInt(raw ?? '0', 10);
  }

  async expectLivePnlVisible(): Promise<void> {
    await expect(this.livePnl).toBeVisible();
  }
}
