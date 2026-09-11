/**
 * Strategy Settings -> Trade Indices (2026-09-11).
 *
 * The live engine now trades ONLY the indices selected here
 * (`settings.symbols`). It used to fall back to all four indices whenever the
 * setting was missing, and the UI had no way to choose them at all.
 *
 * Mocked backend: the save below is captured at the browser boundary and
 * never reaches `settings.json`.
 */
import { expect, test } from '@fixtures/test';
import { ProxyRoutes } from '@config/routes';

const NIFTY = 'NSE:NIFTY50-INDEX';
const SENSEX = 'BSE:SENSEX-INDEX';

test.describe('Trade Indices selector', () => {
  test('shows the saved selection and saves a change', async ({ mockBackend, strategyPage, page }) => {
    await mockBackend.override(ProxyRoutes.settings, { active_strategy: 'ema9_rsi_momentum', symbols: [NIFTY] });
    await strategyPage.goto();

    const selector = page.getByTestId('trading-indices');
    const chip = (name: string) => selector.getByRole('button', { name, exact: true });
    await expect(selector).toBeVisible();
    await expect(chip('NIFTY')).toHaveAttribute('aria-pressed', 'true');
    await expect(chip('SENSEX')).toHaveAttribute('aria-pressed', 'false');
    await expect(selector.getByText('None selected')).toBeHidden();

    await chip('SENSEX').click();
    await expect(chip('SENSEX')).toHaveAttribute('aria-pressed', 'true');

    mockBackend.clearRecorded();
    await page.getByRole('button', { name: 'Save Settings' }).click();
    await page.getByRole('button', { name: 'Save', exact: true }).click();
    await expect.poll(() => mockBackend.requestsTo(ProxyRoutes.settings, 'POST').length).toBe(1);
    const body = JSON.parse(mockBackend.requestsTo(ProxyRoutes.settings, 'POST')[0].postData ?? '{}');
    expect(body.symbols).toEqual([NIFTY, SENSEX]);
  });

  test('warns that nothing will trade when no index is selected', async ({ mockBackend, strategyPage, page }) => {
    await mockBackend.override(ProxyRoutes.settings, { active_strategy: 'ema9_rsi_momentum' });
    await strategyPage.goto();

    const selector = page.getByTestId('trading-indices');
    await expect(selector.getByText('None selected')).toBeVisible();
    for (const name of ['NIFTY', 'BANKNIFTY', 'SENSEX', 'FINNIFTY']) {
      await expect(selector.getByRole('button', { name, exact: true })).toHaveAttribute('aria-pressed', 'false');
    }
  });
});
