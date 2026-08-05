/**
 * Shared behaviour for every page object.
 *
 * Page objects expose intent ("open the journal", "read the equity figure")
 * and keep locators private. Specs that reach for `page.locator(...)`
 * directly are the reason UI suites rot, so the only `Page` handle a spec
 * ever touches is the one a page object hands it deliberately.
 */
import type { Locator, Page, Response } from '@playwright/test';
import { expect } from '@playwright/test';
import { env } from '@config/environment';
import type { AppRoute } from '@config/routes';
import { createLogger } from '@core/logger';

const log = createLogger('Page');

export abstract class BasePage {
  /** Path this page lives at, e.g. `/live`. */
  protected abstract readonly route: AppRoute;
  /** `data-testid` of the element that proves this page rendered. */
  protected abstract readonly rootTestId: string;
  /** Human name used in step titles and failure messages. */
  abstract readonly name: string;

  constructor(protected readonly page: Page) {}

  /** The page's root container — present only once the page has rendered. */
  get root(): Locator {
    return this.page.getByTestId(this.rootTestId);
  }

  /** Navigate here and wait until it is genuinely usable. */
  async goto(): Promise<Response | null> {
    log.debug(`goto ${this.name} (${this.route})`);
    const response = await this.page.goto(this.route, { waitUntil: 'domcontentloaded' });
    await this.waitUntilReady();
    return response;
  }

  /**
   * Wait for the page's own root, not for `networkidle`.
   *
   * This dashboard polls `/api/state`, `/api/signals` and `/api/quote` on
   * intervals and holds an open WebSocket, so network activity never settles
   * — `waitUntil: 'networkidle'` would time out on a perfectly healthy page.
   */
  async waitUntilReady(): Promise<void> {
    await expect(this.root).toBeVisible({ timeout: env.expectTimeoutMs });
  }

  async isDisplayed(): Promise<boolean> {
    return this.root.isVisible();
  }

  /** Assert the browser is actually on this page's route. */
  async expectAtRoute(): Promise<void> {
    await expect(this.page).toHaveURL(new RegExp(`${escapeRegExp(this.route)}/?$`));
  }

  /** A `data-testid` lookup scoped to this page. */
  protected byTestId(testId: string): Locator {
    return this.root.getByTestId(testId);
  }

  /** Text of the first match, trimmed; empty string when absent. */
  protected async textOf(locator: Locator): Promise<string> {
    if ((await locator.count()) === 0) return '';
    return (await locator.first().innerText()).trim();
  }

  /**
   * Parse an Indian-formatted currency string (`+₹1,23,456.78`) into a number.
   *
   * Written once here because every metric on this dashboard renders through
   * `toLocaleString('en-IN')`, whose lakh/crore grouping breaks a naive
   * `parseFloat` — and a P&L assertion that silently parses to `NaN` passes
   * for the wrong reason.
   */
  protected parseCurrency(raw: string): number {
    const cleaned = raw.replace(/[^0-9.+-]/g, '');
    if (cleaned === '' || cleaned === '+' || cleaned === '-') {
      throw new Error(`Could not parse a number out of "${raw}".`);
    }
    const value = Number.parseFloat(cleaned);
    if (Number.isNaN(value)) {
      throw new Error(`Could not parse a number out of "${raw}".`);
    }
    return value;
  }
}

function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}
