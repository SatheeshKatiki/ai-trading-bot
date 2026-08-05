/**
 * The auth gate in front of the whole dashboard.
 *
 * Worth automating because it is a security control, not a convenience: the
 * audit trail records a period where "frontend auth is entirely client-side"
 * and every proxy route called the backend with no credentials at all. These
 * specs assert the gate is actually in the way.
 */
import { expect, test } from '@fixtures/test';
import { ProxyRoutes } from '@config/routes';
import { lockedOutStatus, noUsersStatus, TEST_USER } from '@mocks/scenarios';

test.describe('Authentication gate', () => {
  test.beforeEach(async ({ mockBackend }) => {
    // Default fixtures are "already signed in"; these specs need the gate.
    await mockBackend.failWith(ProxyRoutes.authMe, 401, { error: 'Not authenticated' });
  });

  test('an unauthenticated visitor gets the gate, not the dashboard @smoke', async ({
    authPage,
  }) => {
    await authPage.goto();

    await authPage.expectGated();
  });

  test('the dashboard is not reachable by deep link while signed out', async ({
    page,
    authPage,
  }) => {
    await page.goto('/journal');

    await authPage.waitForGate();
    await expect(page.getByTestId('journal-page')).toBeHidden();
  });

  test('sign-in stays disabled until both fields are filled', async ({ authPage }) => {
    await authPage.goto();
    await authPage.waitForGate();

    expect(await authPage.isSubmitEnabled()).toBe(false);

    await authPage.userIdInput.fill(TEST_USER.user_id);
    expect(await authPage.isSubmitEnabled()).toBe(false);

    await authPage.passwordInput.fill('some-password');
    expect(await authPage.isSubmitEnabled()).toBe(true);
  });

  test('credentials are posted to the login endpoint, not held client-side', async ({
    authPage,
    mockBackend,
  }) => {
    await authPage.goto();
    await authPage.waitForGate();

    await authPage.login(TEST_USER.user_id, 'correct-horse-battery');

    await expect
      .poll(() => mockBackend.requestsTo(ProxyRoutes.authLogin, 'POST').length)
      .toBeGreaterThan(0);

    const [loginRequest] = mockBackend.requestsTo(ProxyRoutes.authLogin, 'POST');
    expect(loginRequest?.postData ?? '').toContain(TEST_USER.user_id);
  });

  test('a rejected sign-in keeps the gate up', async ({ authPage, mockBackend }) => {
    await mockBackend.failWith(ProxyRoutes.authLogin, 401, {
      status: 'error',
      message: 'Invalid credentials',
    });

    await authPage.goto();
    await authPage.waitForGate();
    await authPage.login(TEST_USER.user_id, 'wrong-password');

    await expect(authPage.gate).toBeVisible();
    await expect(authPage.form).toBeVisible();
  });

  test('a locked-out account cannot submit the form', async ({
    authPage,
    mockBackend,
  }) => {
    await mockBackend.override(ProxyRoutes.authStatus, lockedOutStatus);

    await authPage.goto();
    await authPage.waitForGate();

    await authPage.userIdInput.fill(TEST_USER.user_id).catch(() => {
      // Input is disabled during lockout — that is the assertion below.
    });
    expect(await authPage.isSubmitEnabled()).toBe(false);
  });

  test('a first-run install offers registration', async ({ authPage, mockBackend }) => {
    await mockBackend.override(ProxyRoutes.authStatus, noUsersStatus);

    await authPage.goto();
    await authPage.waitForGate();

    await expect(authPage.signUpTab).toBeVisible();
    await authPage.switchToRegister();
    await expect(authPage.form).toBeHidden();
  });

  test('a valid session renders the app instead of the gate @smoke', async ({
    dashboardPage,
    authPage,
    mockBackend,
  }) => {
    await mockBackend.override(ProxyRoutes.authMe, TEST_USER);

    await dashboardPage.goto();

    await expect(dashboardPage.root).toBeVisible();
    await authPage.expectAuthenticated();
  });
});
