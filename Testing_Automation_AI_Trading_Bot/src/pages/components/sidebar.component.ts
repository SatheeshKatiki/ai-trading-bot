/**
 * The left navigation, shared by every page.
 *
 * A component object rather than a method on each page object — the sidebar
 * is rendered by all 13 pages, and duplicating its locators across them is
 * how a nav change turns into 13 failing suites.
 */
import type { Locator, Page } from '@playwright/test';
import { expect } from '@playwright/test';
import { AppRoutes, NavigationItems } from '@config/routes';

export type NavKey = keyof typeof AppRoutes;

/** `data-testid` of a nav link, derived the same way the component builds it. */
function navTestId(href: string): string {
  return `nav-link-${href === '/' ? 'dashboard' : href.slice(1)}`;
}

export class SidebarComponent {
  constructor(private readonly page: Page) {}

  get root(): Locator {
    return this.page.getByTestId('sidebar');
  }

  /** Broker connection pill at the foot of the sidebar. */
  get brokerStatus(): Locator {
    return this.page.getByTestId('broker-connection-status');
  }

  link(key: NavKey): Locator {
    return this.page.getByTestId(navTestId(AppRoutes[key]));
  }

  async navigateTo(key: NavKey): Promise<void> {
    await this.link(key).click();
    await this.page.waitForURL(new RegExp(`${AppRoutes[key].replace('/', '\\/')}/?$`));
  }

  /** Labels of every nav entry, in render order. */
  async visibleLabels(): Promise<string[]> {
    const labels = await this.root.locator('a[data-testid^="nav-link-"]').allInnerTexts();
    return labels.map((label) => label.trim()).filter(Boolean);
  }

  /** The entry currently marked active by the component. */
  activeLink(): Locator {
    return this.root.locator('a[data-active="true"]');
  }

  async expectActive(key: NavKey): Promise<void> {
    await expect(this.link(key)).toHaveAttribute('data-active', 'true');
  }

  async expectAllItemsPresent(): Promise<void> {
    for (const item of NavigationItems) {
      await expect(this.page.getByTestId(navTestId(item.href))).toBeVisible();
    }
  }

  async isBrokerConnected(): Promise<boolean> {
    return (await this.brokerStatus.getAttribute('data-connected')) === 'true';
  }
}
