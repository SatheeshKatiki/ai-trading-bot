/**
 * Stops a test run from writing to the live trading system by accident.
 *
 * Why this exists rather than "just don't write those specs": the backend's
 * write endpoints are ordinary-looking JSON routes. `POST /api/settings`
 * rewrites the file `main.py` reloads every tick. `POST /api/order/execute`
 * places an order. `POST /api/panic-exit` halts the engine and flattens
 * every open position. A single mis-typed path in a spec, or a page object
 * that submits a form during a live-mode run, is enough to disturb a
 * validation session that takes a full trading day to replace.
 *
 * The guard is deliberately deny-by-default and refuses loudly. It is not a
 * warning system.
 */
import { env } from '@config/environment';
import { MutatingEndpoints } from '@config/routes';
import { createLogger } from '@core/logger';

const log = createLogger('MutationGuard');

const WRITE_METHODS = new Set(['POST', 'PUT', 'PATCH', 'DELETE']);

export class MutationBlockedError extends Error {
  constructor(
    readonly method: string,
    readonly url: string,
    reason: string,
  ) {
    super(
      `Blocked ${method} ${url}: ${reason}\n` +
        'This endpoint writes to the live trading system. To allow it for a ' +
        'local, deliberate run: TEST_TARGET=live ALLOW_MUTATIONS=1. It can ' +
        'never be enabled in CI.',
    );
    this.name = 'MutationBlockedError';
  }
}

/**
 * Does `url`'s path hit one of the known write endpoints?
 *
 * Exact match, not prefix match. Prefix matching looks safer but is wrong
 * here: `/api/panic-exit/status` is a *read* that sits under the write path
 * `/api/panic-exit`, and misclassifying it would make the kill switch
 * unverifiable from a live run. Being exact costs nothing in safety, because
 * `assertRequestAllowed` blocks every write method against a live backend
 * regardless of whether the path is catalogued — the catalogue only sharpens
 * the error message.
 */
export function isMutatingEndpoint(url: string): boolean {
  const path = extractPath(url);
  return MutatingEndpoints.includes(path);
}

function extractPath(url: string): string {
  try {
    return new URL(url, 'http://placeholder.invalid').pathname;
  } catch {
    return url;
  }
}

/**
 * Throw unless this request is allowed to reach a real backend.
 *
 * In mocked mode everything is permitted — nothing leaves the browser
 * context, so a "write" is just a fixture lookup.
 */
export function assertRequestAllowed(method: string, url: string): void {
  if (env.target === 'mocked') return;

  const normalisedMethod = method.toUpperCase();
  const isWrite = WRITE_METHODS.has(normalisedMethod);

  if (!isWrite && !isMutatingEndpoint(url)) return;

  if (!isWrite && isMutatingEndpoint(url)) {
    // A GET on a write path (e.g. /api/panic-exit/status) reads state only.
    return;
  }

  if (isMutatingEndpoint(url) && !env.allowMutations) {
    throw new MutationBlockedError(
      normalisedMethod,
      url,
      'it is a known state-changing endpoint and ALLOW_MUTATIONS is not set',
    );
  }

  if (!env.allowMutations) {
    throw new MutationBlockedError(
      normalisedMethod,
      url,
      `${normalisedMethod} requests are treated as writes against a live backend`,
    );
  }

  log.warn('Permitting a live write — ALLOW_MUTATIONS is set', {
    method: normalisedMethod,
    url,
  });
}
