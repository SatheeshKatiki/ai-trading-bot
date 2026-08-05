/**
 * Read-only verification against the real FastAPI backend.
 *
 * Opt-in: `npm run test:live:api` (TEST_TARGET=live). Every call here is a
 * GET on a read endpoint — this suite is safe to run while the paper-trading
 * engine is live, and the mutation guard enforces that rather than trusting
 * it.
 *
 * These are the specs that would have caught, from the outside:
 *   - the auth gate regressing to unauthenticated market-data routes
 *   - the kill-switch status endpoint disappearing
 *   - the ~2h event-loop freeze, as a /health timeout
 */
import { expect, test } from '@fixtures/test';
import { ApiEndpoints } from '@config/routes';
import { env } from '@config/environment';
import {
  authStatusSchema,
  journalSchema,
  panicExitStatusSchema,
  positionsResponseSchema,
  signalsSchema,
  stateSchema,
  strategiesSchema,
} from '@utils/api-contracts';
import { assertSchema } from '@utils/schema';

test.describe('Live backend contracts', () => {
  test.skip(env.target !== 'live', 'requires TEST_TARGET=live');

  test('health responds promptly @smoke', async ({ api }) => {
    const response = await api.get(ApiEndpoints.readOnly.health, { anonymous: true });

    expect(response.status).toBe(200);
    // A slow /health is the signature of a blocked event loop: the server has
    // one, and a synchronous broker call inside an async handler stalls
    // everything, including this route. It froze for ~2h on 2026-08-05.
    expect(response.durationMs).toBeLessThan(2_000);
  });

  test('state matches its contract', async ({ api }) => {
    const response = await api.get(ApiEndpoints.readOnly.state);

    expect(response.status).toBe(200);
    assertSchema(response.body, stateSchema, 'GET /api/state');
  });

  test('positions match their contract', async ({ api }) => {
    const response = await api.get(ApiEndpoints.readOnly.positions);

    expect(response.status).toBe(200);
    assertSchema(response.body, positionsResponseSchema, 'GET /api/positions');
  });

  test('signals match their contract', async ({ api }) => {
    const response = await api.get(ApiEndpoints.readOnly.signals, {
      params: { symbol: 'NIFTY' },
    });

    expect(response.status).toBe(200);
    assertSchema(response.body, signalsSchema, 'GET /api/signals');
  });

  test('journal matches its contract', async ({ api }) => {
    const response = await api.get(ApiEndpoints.readOnly.journal);

    expect(response.status).toBe(200);
    assertSchema(response.body, journalSchema, 'GET /api/journal');
  });

  test('strategies are discoverable', async ({ api }) => {
    const response = await api.get(ApiEndpoints.readOnly.strategies);

    expect(response.status).toBe(200);
    assertSchema(response.body, strategiesSchema, 'GET /api/strategies');
    expect((response.body as { strategies: string[] }).strategies.length).toBeGreaterThan(0);
  });

  test('the kill switch reports its state and is disarmed', async ({ api }) => {
    const response = await api.get(ApiEndpoints.readOnly.panicExitStatus);

    expect(response.status).toBe(200);
    assertSchema(response.body, panicExitStatusSchema, 'GET /api/panic-exit/status');
    // Reading it is safe; a run that finds it armed should fail loudly,
    // because the engine is halted and nothing else in the suite is valid.
    expect((response.body as { emergency_stop: boolean }).emergency_stop).toBe(false);
  });
});

test.describe('Live backend auth gate', () => {
  test.skip(env.target !== 'live', 'requires TEST_TARGET=live');

  test('auth status is public by design', async ({ api }) => {
    const response = await api.get(ApiEndpoints.readOnly.authStatus, { anonymous: true });

    expect(response.status).toBe(200);
    assertSchema(response.body, authStatusSchema, 'GET /api/auth/status');
  });

  const protectedEndpoints = [
    ApiEndpoints.readOnly.state,
    ApiEndpoints.readOnly.positions,
    ApiEndpoints.readOnly.journal,
    ApiEndpoints.readOnly.history,
    ApiEndpoints.readOnly.quote,
    ApiEndpoints.readOnly.optionChain,
    ApiEndpoints.readOnly.settings,
    ApiEndpoints.readOnly.logs,
  ];

  for (const endpoint of protectedEndpoints) {
    test(`${endpoint} rejects an unauthenticated caller`, async ({ api }) => {
      const response = await api.anonymous().get(endpoint);

      expect(
        response.status,
        `${endpoint} answered ${response.status} without a session token`,
      ).toBe(401);
    });
  }

  test('a forged bearer token is rejected', async ({ api }) => {
    const response = await api.get(ApiEndpoints.readOnly.state, {
      anonymous: true,
      headers: { Authorization: 'Bearer not-a-real-session-token' },
    });

    expect(response.status).toBe(401);
  });
});

test.describe('Live backend write protection', () => {
  test.skip(env.target !== 'live', 'requires TEST_TARGET=live');

  test('the suite refuses to place an order unless explicitly unlocked', async ({
    api,
  }) => {
    test.skip(env.allowMutations, 'ALLOW_MUTATIONS is set — the guard is off by request');

    await expect(
      api.post(ApiEndpoints.mutating.orderExecute, {
        data: { symbol: 'NSE:NIFTY50-INDEX', side: 'BUY', quantity: 1 },
      }),
    ).rejects.toThrow(/Blocked POST/);
  });

  test('the suite refuses to trigger the kill switch unless explicitly unlocked', async ({
    api,
  }) => {
    test.skip(env.allowMutations, 'ALLOW_MUTATIONS is set — the guard is off by request');

    await expect(api.post(ApiEndpoints.mutating.panicExit)).rejects.toThrow(/Blocked POST/);
  });
});
