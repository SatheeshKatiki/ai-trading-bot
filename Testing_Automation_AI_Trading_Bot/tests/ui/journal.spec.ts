/** Trading Journal — the closed-trade record operators reconcile P&L against. */
import { expect, test } from '@fixtures/test';
import { ProxyRoutes } from '@config/routes';
import { buildJournal, buildJournalTrade, emptyJournal } from '@mocks/scenarios';

test.describe('Trading journal', () => {
  test('lists every closed trade @smoke', async ({ journalPage }) => {
    await journalPage.goto();

    await expect(journalPage.table).toBeVisible();
    await journalPage.expectRowCount(buildJournal().trades.length);
  });

  test('classifies wins and losses by their P&L sign', async ({ journalPage }) => {
    await journalPage.goto();
    await journalPage.expectRowCount(2);

    // Fixture holds one winner (+1132.50) and one loser (-918.75).
    expect(await journalPage.pnlSigns()).toEqual(['positive', 'negative']);
  });

  test('renders an empty journal without breaking the page', async ({
    journalPage,
    mockBackend,
  }) => {
    await mockBackend.override(ProxyRoutes.journal, emptyJournal);

    await journalPage.goto();

    await expect(journalPage.root).toBeVisible();
    await journalPage.expectRowCount(0);
  });

  test('a break-even trade is not reported as a win', async ({
    journalPage,
    mockBackend,
  }) => {
    // Not academic: the 2026-08-05 over-cap incident produced nine trades that
    // all closed at exactly breakeven, and they must not inflate a win count.
    await mockBackend.override(ProxyRoutes.journal, {
      trades: [
        buildJournalTrade({
          id: 99,
          symbol: 'NSE:NIFTY2580724600CE',
          entry_price: 100,
          exit_price: 100,
          qty: 75,
          pnl: 0,
          tags: 'BREAKEVEN',
        }),
      ],
    });

    await journalPage.goto();

    await journalPage.expectRowCount(1);
    expect(await journalPage.pnlSigns()).toEqual(['negative']);
  });

  test('survives a journal fetch failure', async ({ journalPage, mockBackend }) => {
    await mockBackend.failWith(ProxyRoutes.journal, 500);

    await journalPage.goto();

    await expect(journalPage.root).toBeVisible();
  });
});
