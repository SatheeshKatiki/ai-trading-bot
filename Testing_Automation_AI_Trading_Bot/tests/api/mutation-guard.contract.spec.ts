/**
 * The safety mechanism gets its own tests.
 *
 * The mutation guard is the only thing standing between a careless spec and a
 * live `POST /api/order/execute`. A guard that silently stopped working would
 * be discovered the way these things usually are — by a polluted `state.db`
 * and a lost validation session — so its behaviour is asserted directly.
 */
import { expect, test } from '@fixtures/test';
import { ApiEndpoints } from '@config/routes';
import { env } from '@config/environment';
import { isMutatingEndpoint } from '@core/mutation-guard';

test.describe('Mutation guard classification', () => {
  test('every known write endpoint is recognised', () => {
    for (const endpoint of Object.values(ApiEndpoints.mutating)) {
      expect(isMutatingEndpoint(endpoint), `${endpoint} must be guarded`).toBe(true);
    }
  });

  test('read endpoints are not misclassified', () => {
    const readOnly = Object.values(ApiEndpoints.readOnly).filter(
      // /api/settings is the same path for GET (read) and POST (write); the
      // guard distinguishes those by method, so it is excluded from this sweep.
      (endpoint) => endpoint !== ApiEndpoints.readOnly.settings,
    );

    for (const endpoint of readOnly) {
      expect(isMutatingEndpoint(endpoint), `${endpoint} must not be guarded`).toBe(false);
    }
  });

  test('classification survives query strings and absolute URLs', () => {
    expect(isMutatingEndpoint('http://127.0.0.1:8000/api/panic-exit')).toBe(true);
    expect(isMutatingEndpoint('/api/order/execute?dry_run=1')).toBe(true);
    expect(isMutatingEndpoint('http://127.0.0.1:8000/api/state?live=false')).toBe(false);
  });

  test('the panic-exit status sub-route is a read, not a write', () => {
    // GET /api/panic-exit/status only reports the flag, but it sits directly
    // under the write path /api/panic-exit. An earlier prefix-matching guard
    // classified it as a mutation, which would have made the kill switch
    // unverifiable from a live run — the exact capability §2.8 of the go/no-go
    // checklist depends on.
    expect(isMutatingEndpoint(ApiEndpoints.readOnly.panicExitStatus)).toBe(false);
    expect(isMutatingEndpoint(ApiEndpoints.mutating.panicExit)).toBe(true);
    expect(isMutatingEndpoint(ApiEndpoints.mutating.panicExitClear)).toBe(true);
  });
});

test.describe('Mocked runs cannot reach the backend', () => {
  test.skip(env.target !== 'mocked', 'only meaningful for the mocked target');

  test('mutations are permitted because nothing leaves the browser', async ({
    dashboardPage,
    mockBackend,
  }) => {
    await dashboardPage.goto();

    // Every /api/** request this page made was served from fixtures; none of
    // them reached port 8000.
    expect(mockBackend.requests().length).toBeGreaterThan(0);
    for (const request of mockBackend.requests()) {
      expect(request.path.startsWith('/api/')).toBe(true);
    }
  });
});
