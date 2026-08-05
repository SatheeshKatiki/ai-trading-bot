/**
 * Serves the whole backend from fixtures, inside the browser context.
 *
 * Every dashboard page fetches `/api/**` from the Next.js proxy routes, which
 * forward to FastAPI on port 8000. Intercepting at the browser boundary means
 * a UI run never reaches the Python process at all: no `state.db` write, no
 * `settings.json` reload, no order ever placed — and no dependence on what
 * the market happened to be doing when the suite ran.
 *
 * Defaults cover every route the app calls, so a spec only declares the parts
 * it actually cares about:
 *
 * ```ts
 * await mockBackend.override(ProxyRoutes.positions, emptyPositions);
 * await mockBackend.failWith(ProxyRoutes.state, 500);
 * ```
 */
import type { Page, Route, WebSocketRoute } from '@playwright/test';
import { ProxyRoutes } from '@config/routes';
import { createLogger } from '@core/logger';
import * as scenario from '@mocks/scenarios';

const log = createLogger('MockBackend');

/** A fixture payload, or a function that builds one from the request. */
export type MockResponder =
  | unknown
  | ((route: Route) => unknown | Promise<unknown>);

interface MockRule {
  status: number;
  responder: MockResponder;
  delayMs: number;
}

export interface RecordedRequest {
  method: string;
  path: string;
  postData: string | null;
}

/** Default response for every `/api/**` path the dashboard calls. */
function defaultRules(): Map<string, MockRule> {
  const ok = (responder: MockResponder): MockRule => ({
    status: 200,
    responder,
    delayMs: 0,
  });

  return new Map<string, MockRule>([
    [ProxyRoutes.authStatus, ok(scenario.authenticatedStatus)],
    [ProxyRoutes.authMe, ok(scenario.TEST_USER)],
    [ProxyRoutes.authLogin, ok({ status: 'success', user: scenario.TEST_USER })],
    [ProxyRoutes.authLogout, ok({ status: 'success' })],
    [ProxyRoutes.authRegister, ok({ status: 'success', user_id: scenario.TEST_USER.user_id })],
    [ProxyRoutes.authReset, ok({ status: 'success' })],
    [ProxyRoutes.state, ok(() => scenario.buildState())],
    [ProxyRoutes.positions, ok(() => scenario.buildPositionsResponse())],
    [ProxyRoutes.signals, ok(() => scenario.buildSignals())],
    [ProxyRoutes.journal, ok(() => scenario.buildJournal())],
    [ProxyRoutes.risk, ok(scenario.risk)],
    [ProxyRoutes.logs, ok(scenario.logs)],
    [ProxyRoutes.settings, ok(scenario.settings)],
    [ProxyRoutes.strategies, ok(scenario.strategies)],
    [ProxyRoutes.strategyParameters, ok({ parameters: {} })],
    [ProxyRoutes.history, ok(() => scenario.buildHistory())],
    [ProxyRoutes.optionChain, ok(() => scenario.buildOptionChain())],
    [ProxyRoutes.sentiment, ok(scenario.sentiment)],
    [ProxyRoutes.btst, ok(scenario.btst)],
    [ProxyRoutes.analytics, ok(scenario.analytics)],
    [ProxyRoutes.aiStatus, ok({ status: 'ready', model_version: 'test-1' })],
    [ProxyRoutes.engineStatus, ok(scenario.engineRunning)],
    [ProxyRoutes.health, ok({ status: 'ok' })],
    [ProxyRoutes.wsToken, ok({ token: 'mock-ws-token' })],
    [ProxyRoutes.testConnection, ok({ status: 'success', balance: 100_000 })],
    [ProxyRoutes.backtest, ok({ trades: [], stats: { winRate: 0, profitFactor: 0, maxDrawdown: 0 } })],
    [ProxyRoutes.aiRetrain, ok({ status: 'started' })],
    [ProxyRoutes.botStart, ok({ status: 'success' })],
    [ProxyRoutes.brokerLogin, ok({ status: 'success' })],

    // Write endpoints. Mocked so the UI flow completes and the spec can
    // assert on the *request* the app sent — the real ones place orders and
    // halt the engine, and are never reachable from a mocked run.
    [ProxyRoutes.engineToggle, ok({ status: 'success', is_active: false })],
    [ProxyRoutes.orderExecute, ok({ status: 'success', order_id: 'MOCK-ORDER-1' })],
    [ProxyRoutes.panicExit, ok({ status: 'success', closed: 0, cancelled: 0 })],
  ]);
}

/** Live tick frame pushed over the mocked WebSocket. */
function defaultTick(): Record<string, unknown> {
  const positions = scenario.buildPositionsResponse().positions;
  const unrealized = positions.reduce((sum, position) => sum + position.unrealized_pnl, 0);
  return {
    NIFTY: { lp: 24_512.35, chp: 0.42 },
    BANKNIFTY: { lp: 52_140.8, chp: 0.31 },
    SENSEX: { lp: 80_355.1, chp: 0.38 },
    pnl: -74.35,
    unrealized_pnl: Math.round(unrealized * 100) / 100,
    total_pnl: Math.round((unrealized - 74.35) * 100) / 100,
    equity: 99_925.65,
    open_positions_count: positions.length,
    positions_detail: positions,
  };
}

export class MockBackend {
  private readonly rules = defaultRules();
  private readonly recorded: RecordedRequest[] = [];
  private installed = false;

  constructor(private readonly page: Page) {}

  /** Intercept all `/api/**` traffic and the live-tick WebSocket. */
  async install(): Promise<void> {
    if (this.installed) return;

    await this.page.route('**/api/**', async (route) => {
      const url = new URL(route.request().url());
      const path = url.pathname;

      this.recorded.push({
        method: route.request().method(),
        path,
        postData: route.request().postData(),
      });

      const rule = this.rules.get(path);
      if (!rule) {
        // Loud on purpose: an unmocked call means the app grew a route the
        // fixtures do not know about, which would otherwise show up as a
        // confusing UI assertion failure.
        log.warn(`Unmocked ${route.request().method()} ${path} → 501`);
        await route.fulfill({
          status: 501,
          contentType: 'application/json',
          body: JSON.stringify({ error: `No mock registered for ${path}` }),
        });
        return;
      }

      if (rule.delayMs > 0) {
        await new Promise((resolve) => setTimeout(resolve, rule.delayMs));
      }

      const payload =
        typeof rule.responder === 'function'
          ? await (rule.responder as (route: Route) => unknown)(route)
          : rule.responder;

      log.debug(`${route.request().method()} ${path} → ${rule.status}`);
      await route.fulfill({
        status: rule.status,
        contentType: 'application/json',
        body: JSON.stringify(payload ?? {}),
      });
    });

    await this.installWebSocket();
    this.installed = true;
  }

  /**
   * Answer the live-tick socket locally.
   *
   * Without this the browser tries `ws://<host>:8000/ws/live`, which either
   * hangs (nothing listening) or — worse in live mode — subscribes to the
   * real engine's broadcast. `routeWebSocket` keeps it in-process.
   */
  private async installWebSocket(): Promise<void> {
    await this.page.routeWebSocket('**/ws/live**', (ws: WebSocketRoute) => {
      log.debug('WebSocket connected (mocked)');
      ws.send(JSON.stringify(defaultTick()));
      ws.onMessage(() => ws.send(JSON.stringify(defaultTick())));
    });
  }

  /** Replace one route's payload. Pass a function for per-request behaviour. */
  async override(path: string, responder: MockResponder, status = 200): Promise<void> {
    this.rules.set(path, { status, responder, delayMs: this.rules.get(path)?.delayMs ?? 0 });
  }

  /** Make a route return an error status, for degraded-UI assertions. */
  async failWith(path: string, status: number, body: unknown = { error: 'mocked failure' }): Promise<void> {
    this.rules.set(path, { status, responder: body, delayMs: 0 });
  }

  /** Delay a route's response, for loading-state and race assertions. */
  async delay(path: string, delayMs: number): Promise<void> {
    const existing = this.rules.get(path);
    this.rules.set(path, {
      status: existing?.status ?? 200,
      responder: existing?.responder ?? {},
      delayMs,
    });
  }

  /** Every `/api/**` request the page made, in order. */
  requests(): readonly RecordedRequest[] {
    return this.recorded;
  }

  /** Requests to one path, optionally filtered by method. */
  requestsTo(path: string, method?: string): RecordedRequest[] {
    return this.recorded.filter(
      (request) =>
        request.path === path &&
        (method === undefined || request.method === method.toUpperCase()),
    );
  }

  clearRecorded(): void {
    this.recorded.length = 0;
  }
}
