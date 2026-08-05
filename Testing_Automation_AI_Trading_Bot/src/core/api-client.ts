/**
 * Typed access to the platform's HTTP surface for API specs.
 *
 * Wraps Playwright's `APIRequestContext` so specs never hand-roll a URL, a
 * bearer header, or a `response.json()` cast — and so every outbound call
 * passes the mutation guard first.
 */
import type { APIRequestContext, APIResponse } from '@playwright/test';
import { env } from '@config/environment';
import { assertRequestAllowed } from '@core/mutation-guard';
import { createLogger } from '@core/logger';

const log = createLogger('ApiClient');

export interface ApiCallOptions {
  /** Query parameters; `undefined` values are dropped rather than sent as "undefined". */
  params?: Record<string, string | number | boolean | undefined>;
  headers?: Record<string, string>;
  data?: unknown;
  /** Skip the automatic `Authorization` header (for auth-gate negative tests). */
  anonymous?: boolean;
  timeoutMs?: number;
}

/** A response plus its parsed body, so specs can assert on both. */
export interface ApiResult<T> {
  readonly status: number;
  readonly ok: boolean;
  readonly body: T;
  readonly raw: APIResponse;
  readonly durationMs: number;
}

export class ApiClient {
  private readonly baseURL: string;

  constructor(
    private readonly request: APIRequestContext,
    private readonly sessionToken: string | undefined,
    baseURL: string = env.backendURL,
  ) {
    this.baseURL = baseURL.replace(/\/$/, '');
  }

  /** A client for the same backend with no session token attached. */
  anonymous(): ApiClient {
    return new ApiClient(this.request, undefined, this.baseURL);
  }

  get<T = unknown>(path: string, options: ApiCallOptions = {}): Promise<ApiResult<T>> {
    return this.send<T>('GET', path, options);
  }

  post<T = unknown>(path: string, options: ApiCallOptions = {}): Promise<ApiResult<T>> {
    return this.send<T>('POST', path, options);
  }

  put<T = unknown>(path: string, options: ApiCallOptions = {}): Promise<ApiResult<T>> {
    return this.send<T>('PUT', path, options);
  }

  delete<T = unknown>(path: string, options: ApiCallOptions = {}): Promise<ApiResult<T>> {
    return this.send<T>('DELETE', path, options);
  }

  private async send<T>(
    method: string,
    path: string,
    options: ApiCallOptions,
  ): Promise<ApiResult<T>> {
    const url = `${this.baseURL}${path}`;
    assertRequestAllowed(method, url);

    const headers: Record<string, string> = { ...options.headers };
    if (!options.anonymous && this.sessionToken) {
      headers.Authorization = `Bearer ${this.sessionToken}`;
    }

    const startedAt = Date.now();
    const response = await this.request.fetch(url, {
      method,
      headers,
      params: cleanParams(options.params),
      ...(options.data === undefined ? {} : { data: options.data }),
      timeout: options.timeoutMs ?? env.actionTimeoutMs,
      failOnStatusCode: false,
    });
    const durationMs = Date.now() - startedAt;

    log.debug(`${method} ${path} → ${response.status()} (${durationMs}ms)`);

    return {
      status: response.status(),
      ok: response.ok(),
      body: await parseBody<T>(response),
      raw: response,
      durationMs,
    };
  }
}

function cleanParams(
  params: ApiCallOptions['params'],
): Record<string, string | number | boolean> | undefined {
  if (!params) return undefined;
  const entries = Object.entries(params).filter(
    (entry): entry is [string, string | number | boolean] => entry[1] !== undefined,
  );
  return entries.length > 0 ? Object.fromEntries(entries) : undefined;
}

/**
 * Parse JSON, but never throw on a non-JSON body — an HTML error page or an
 * empty 502 is a legitimate thing for a spec to assert about, and losing it
 * to a parse exception hides the actual failure.
 */
async function parseBody<T>(response: APIResponse): Promise<T> {
  const text = await response.text();
  if (text.trim() === '') return undefined as T;
  try {
    return JSON.parse(text) as T;
  } catch {
    return text as unknown as T;
  }
}
