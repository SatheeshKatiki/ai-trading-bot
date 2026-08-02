import { cookies } from 'next/headers';

// Root-cause fix for the audit finding "frontend auth is entirely client-side":
// every proxy route used to call the Python backend with no credentials at
// all, because the backend didn't check for any either. Now that the
// backend requires a real session token (see
// trading-system/shared/security/sessions.py), every proxy route needs to
// forward one. This helper is the single place that does it, instead of
// each of the ~25 route handlers reimplementing the same header logic.

// High audit finding: every one of the ~27 proxy routes hardcoded
// 'http://127.0.0.1:8000' directly, making it impossible to deploy the
// frontend and backend on separate hosts/containers without editing every
// file. Reads from BACKEND_URL (falling back to the previous hardcoded
// value for local dev, so nothing breaks for anyone not setting it) — set
// this in the environment when the backend isn't reachable at localhost.
export const BACKEND_URL = process.env.BACKEND_URL || 'http://127.0.0.1:8000';
export const SESSION_COOKIE = 'session_token';

/** Read the caller's session token straight from the httpOnly cookie. */
export async function getSessionToken(): Promise<string | undefined> {
  const cookieStore = await cookies();
  return cookieStore.get(SESSION_COOKIE)?.value;
}

/** Return an `Authorization` header object (empty if not logged in) — for
 * route handlers that build their own fetch calls (e.g. with a custom
 * timeout/AbortController wrapper) instead of using {@link backendFetch}. */
export async function getAuthHeaders(): Promise<Record<string, string>> {
  const token = await getSessionToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

/**
 * Fetch a backend API path, automatically attaching the caller's session
 * token (read from the httpOnly session cookie) as a Bearer token.
 *
 * Use this instead of calling `fetch(BACKEND_URL + path)` directly in any
 * route handler that talks to a route the backend requires auth for.
 */
export async function backendFetch(path: string, init: RequestInit = {}): Promise<Response> {
  const token = await getSessionToken();

  const headers = new Headers(init.headers);
  if (token) {
    headers.set('Authorization', `Bearer ${token}`);
  }

  return fetch(`${BACKEND_URL}${path}`, { ...init, headers });
}
