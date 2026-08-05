/**
 * The application's surface, catalogued once.
 *
 * Every page object and API spec addresses the app through these constants
 * rather than through string literals, so a renamed route is one edit here
 * instead of a grep across the suite. Mirrors `frontend/app/**` (pages and
 * proxy handlers) and `trading-system/api_bridge.py` (the FastAPI routes).
 */

/** Dashboard pages — `frontend/app/<route>/page.tsx`. */
export const AppRoutes = {
  dashboard: '/',
  liveTrading: '/live',
  backtest: '/backtest',
  signals: '/signals',
  strategy: '/strategy',
  journal: '/journal',
  optionsDesk: '/options',
  analytics: '/analytics',
  broker: '/broker',
  risk: '/risk',
  settings: '/settings',
  docs: '/docs',
  about: '/about',
} as const;

export type AppRoute = (typeof AppRoutes)[keyof typeof AppRoutes];

/** Sidebar entries, in render order — `frontend/components/sidebar.tsx`. */
export const NavigationItems = [
  { label: 'Dashboard', href: AppRoutes.dashboard },
  { label: 'Live Trading', href: AppRoutes.liveTrading },
  { label: 'Backtesting', href: AppRoutes.backtest },
  { label: 'AI Signals', href: AppRoutes.signals },
  { label: 'Strategy Settings', href: AppRoutes.strategy },
  { label: 'Trading Journal', href: AppRoutes.journal },
  { label: 'Options Desk', href: AppRoutes.optionsDesk },
  { label: 'Analytics', href: AppRoutes.analytics },
  { label: 'Broker Settings', href: AppRoutes.broker },
  { label: 'Risk Management', href: AppRoutes.risk },
  { label: 'Settings', href: AppRoutes.settings },
  { label: 'Documentation', href: AppRoutes.docs },
  { label: 'About', href: AppRoutes.about },
] as const;

/**
 * Backend endpoints, grouped by what they do to the system.
 *
 * The split is not cosmetic: {@link MutatingEndpoints} is what the mutation
 * guard blocks in live mode, so an endpoint landing in the wrong group is a
 * safety bug, not a style issue.
 */
export const ApiEndpoints = {
  /** Safe to call against a live backend — no writes, no order flow. */
  readOnly: {
    health: '/health',
    authStatus: '/api/auth/status',
    authMe: '/api/auth/me',
    state: '/api/state',
    positions: '/api/positions',
    signals: '/api/signals',
    quote: '/api/quote',
    history: '/api/history',
    optionChain: '/api/option-chain',
    journal: '/api/journal',
    logs: '/api/logs',
    strategies: '/api/strategies',
    strategyParameters: '/api/strategy/parameters',
    settings: '/api/settings',
    sentiment: '/api/sentiment',
    btst: '/api/btst',
    aiStatus: '/api/ai/status',
    engineStatus: '/api/engine/status',
    panicExitStatus: '/api/panic-exit/status',
    equityData: '/equity-data',
    backtest: '/api/backtest',
  },
  /**
   * Writes to the trading system. Blocked unless a run explicitly opts in
   * (`ALLOW_MUTATIONS=1`, live target, never in CI).
   */
  mutating: {
    orderExecute: '/api/order/execute',
    panicExit: '/api/panic-exit',
    panicExitClear: '/api/panic-exit/clear',
    engineToggle: '/api/engine/toggle',
    saveSettings: '/api/settings',
    botStart: '/api/bot/start',
    brokerLogin: '/api/broker-login',
    aiRetrain: '/api/ai/retrain',
    authRegister: '/api/auth/register',
    authReset: '/api/auth/reset',
  },
} as const;

/** Path prefixes that mutate state, used by the guard for `POST`/`PUT`/`DELETE`. */
export const MutatingEndpoints: readonly string[] = Object.values(
  ApiEndpoints.mutating,
);

/**
 * Frontend proxy routes (`frontend/app/api/**`) the browser actually calls.
 *
 * This list is exhaustive by construction — it is every `fetch('/api/...')`
 * reachable from client components. That matters for the mocked target: an
 * un-intercepted path is one that reaches the Next.js handler, which forwards
 * it server-side to the real FastAPI backend where `page.route` cannot follow.
 */
export const ProxyRoutes = {
  authStatus: '/api/auth/status',
  authMe: '/api/auth/me',
  authLogin: '/api/auth/login',
  authLogout: '/api/auth/logout',
  authRegister: '/api/auth/register',
  authReset: '/api/auth/reset',
  state: '/api/state',
  positions: '/api/positions',
  signals: '/api/signals',
  journal: '/api/journal',
  risk: '/api/risk',
  logs: '/api/logs',
  settings: '/api/settings',
  strategies: '/api/strategies',
  strategyParameters: '/api/strategy/parameters',
  history: '/api/history',
  optionChain: '/api/option-chain',
  sentiment: '/api/sentiment',
  btst: '/api/btst',
  analytics: '/api/analytics',
  aiStatus: '/api/ai/status',
  engineStatus: '/api/engine/status',
  engineToggle: '/api/engine/toggle',
  health: '/api/health',
  wsToken: '/api/ws-token',
  testConnection: '/api/test_connection',
  backtest: '/api/backtest',
  orderExecute: '/api/order/execute',
  panicExit: '/api/panic-exit',
  aiRetrain: '/api/ai/retrain',
  botStart: '/api/bot/start',
  brokerLogin: '/api/broker-login',
} as const;
