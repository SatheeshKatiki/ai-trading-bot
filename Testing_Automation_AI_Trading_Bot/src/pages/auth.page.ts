/**
 * The auth gate that wraps the entire dashboard.
 *
 * `AuthProvider` renders one of three things at the root: a loading state, the
 * sign-in/sign-up card, or the app itself. Nothing else in the suite can be
 * reached until this is satisfied, which is why it is a page object of its
 * own rather than a helper.
 */
import type { Locator, Page } from '@playwright/test';
import { expect } from '@playwright/test';
import { env } from '@config/environment';
import { createLogger } from '@core/logger';

const log = createLogger('AuthPage');

export class AuthPage {
  readonly name = 'Authentication';

  constructor(private readonly page: Page) {}

  get gate(): Locator {
    return this.page.getByTestId('auth-gate');
  }

  get loadingState(): Locator {
    return this.page.getByTestId('auth-loading');
  }

  get form(): Locator {
    return this.page.getByTestId('login-form');
  }

  get userIdInput(): Locator {
    return this.page.getByTestId('login-user-id');
  }

  get passwordInput(): Locator {
    return this.page.getByTestId('login-password');
  }

  get submitButton(): Locator {
    return this.page.getByTestId('login-submit');
  }

  get signInTab(): Locator {
    return this.page.getByTestId('auth-tab-login');
  }

  get signUpTab(): Locator {
    return this.page.getByTestId('auth-tab-register');
  }

  async goto(): Promise<void> {
    await this.page.goto('/', { waitUntil: 'domcontentloaded' });
  }

  async waitForGate(): Promise<void> {
    await expect(this.gate).toBeVisible({ timeout: env.expectTimeoutMs });
  }

  /** Fill and submit the sign-in form. Does not assert the outcome. */
  async login(userId: string, password: string): Promise<void> {
    log.debug(`Signing in as ${userId}`);
    await this.userIdInput.fill(userId);
    await this.passwordInput.fill(password);
    await this.submitButton.click();
  }

  /** The submit button stays disabled until both fields have content. */
  async isSubmitEnabled(): Promise<boolean> {
    return this.submitButton.isEnabled();
  }

  async switchToRegister(): Promise<void> {
    await this.signUpTab.click();
  }

  async switchToSignIn(): Promise<void> {
    await this.signInTab.click();
  }

  /** Assert the app is gated — i.e. the dashboard is NOT reachable. */
  async expectGated(): Promise<void> {
    await expect(this.gate).toBeVisible();
    await expect(this.page.getByTestId('sidebar')).toBeHidden();
  }

  /** Assert the gate has been passed and the app shell is rendering. */
  async expectAuthenticated(): Promise<void> {
    await expect(this.page.getByTestId('sidebar')).toBeVisible({
      timeout: env.expectTimeoutMs,
    });
    await expect(this.gate).toBeHidden();
  }
}
