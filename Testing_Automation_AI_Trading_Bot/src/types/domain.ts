/**
 * Payload shapes the platform actually returns.
 *
 * Mirrors `trading-system/api_bridge.py` and `shared/state.py`. These are
 * hand-written rather than generated because the backend publishes no
 * OpenAPI schema for most routes (several return bare dicts assembled
 * inline) — so this file doubles as the written-down contract the API specs
 * assert against. When a spec fails because reality drifted from a type
 * here, that is the suite doing its job.
 */

/** `GET /api/state` — from `shared.state.load_state()`. */
export interface BotState {
  equity: number;
  pnl: number;
  last_update?: string;
  trades?: StateTrade[];
  is_active?: boolean;
  [key: string]: unknown;
}

/** A row of the live order feed (`trades` table). */
export interface StateTrade {
  symbol: string;
  side: string;
  price: number;
  time: string;
  qty: number;
}

/** `GET /api/positions` — `brokers/models.py`'s Position dataclass. */
export interface Position {
  symbol: string;
  side: string;
  quantity: number;
  average_price: number;
  ltp: number;
  unrealized_pnl: number;
  realized_pnl: number;
  product?: string;
  [key: string]: unknown;
}

export interface PositionsResponse {
  status: 'success' | 'error';
  positions: Position[];
  message?: string;
}

/** `GET /api/signals` — assembled in `compute_signals()`. */
export interface SignalsResponse {
  confidence: number;
  status: string;
  bias: string;
  trendData?: TrendPoint[];
  signals?: TradeSignal[];
  direction?: string;
  timestamp?: number;
  error?: string;
}

export interface TrendPoint {
  name: string;
  value: number;
}

export interface TradeSignal {
  symbol: string;
  type: string;
  bias: string;
  strength: string;
  confidence: number;
  time: string;
  reason: string;
}

/** `GET /api/journal` — rows of the `trade_journal` table. */
export interface JournalResponse {
  trades: JournalTrade[];
  error?: string;
}

export interface JournalTrade {
  id?: number;
  trade_date: string;
  symbol: string;
  strategy_name: string;
  direction: string;
  entry_price: number;
  exit_price: number;
  qty: number;
  pnl: number;
  ai_feedback?: string;
  tags?: string;
  [key: string]: unknown;
}

/** `GET /api/auth/status`. */
export interface AuthStatus {
  hasUsers: boolean;
  hasPassword: boolean;
  lockedOut: boolean;
  lockoutSeconds: number;
  userCount?: number;
}

/** `GET /api/auth/me`. */
export interface UserProfile {
  user_id: string;
  name: string;
  email: string;
}

/** `POST /api/auth/login`. */
export interface LoginResponse {
  status?: string;
  token?: string;
  user?: UserProfile;
  message?: string;
}

/** `GET /api/quote`. */
export interface QuoteResponse {
  symbol: string;
  ltp: number;
  change?: number;
  change_pct?: number;
  [key: string]: unknown;
}

/** `GET /api/history`. */
export interface HistoryResponse {
  symbol: string;
  timeframe: string;
  data_points: number;
  data: Candle[];
  underlying?: string;
  strike?: number;
  opt_type?: string;
}

export interface Candle {
  datetime: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
  [key: string]: unknown;
}

/**
 * `GET /api/sentiment` — `shared/sentiment.py`'s cache dict.
 *
 * `top_headlines` is required, not optional: `NewsTicker` reads it without a
 * guard on first render, so an absent key is a crashed dashboard rather than a
 * degraded one.
 */
export interface SentimentResponse {
  score: number;
  label: string;
  top_headlines: SentimentHeadline[];
}

export interface SentimentHeadline {
  title_en: string;
  title_te?: string;
  link?: string;
  published?: string;
  sentiment?: number;
}

/** `GET /api/btst`. */
export interface BtstResponse {
  status: string;
  action: string;
  gapUpProb: number;
  gapDownProb: number;
  reason: string;
  metrics?: { momentum: number; rsi: number };
}

/**
 * `GET /api/option-chain` as delivered by the Next.js proxy, which renames the
 * backend's `call`/`put` legs to `ce`/`pe` before the page sees them.
 */
export interface OptionLeg {
  ltp: number;
  volume: number;
  oi: number;
  oichg: number;
  delta: number;
  gamma: number;
  theta: number;
  vega: number;
}

export interface OptionChainRow {
  strike: number;
  ce: OptionLeg;
  pe: OptionLeg;
}

export interface OptionChainResponse {
  symbol: string;
  underlying_price?: number;
  atm: number;
  maxPain: number;
  pcr: number;
  expiry: string;
  /** Must be non-empty — the Options Desk reduces it without an initial value. */
  chain: OptionChainRow[];
  error?: string;
}

/** `GET /api/engine/status`. */
export interface EngineStatusResponse {
  is_active?: boolean;
  status?: string;
  [key: string]: unknown;
}

/** `GET /api/panic-exit/status`. */
export interface PanicExitStatus {
  emergency_stop: boolean;
  [key: string]: unknown;
}

/** `GET /api/settings` — the whole of `config/settings.json`. */
export interface SettingsResponse {
  active_strategy?: string;
  active_broker?: string;
  emergency_stop?: boolean;
  target_pct?: number;
  stoploss_pct?: number;
  trailing_sl?: boolean;
  [key: string]: unknown;
}

/** `GET /api/strategies`. */
export interface StrategiesResponse {
  strategies: string[];
}

/**
 * `GET /api/analytics` — built by the Next.js route handler from
 * `trading-system/backtest_results.json`. The Analytics page dereferences
 * every one of these fields without a guard, so all are required.
 */
export interface AnalyticsResponse {
  stats: {
    profitFactor: number;
    expectancy: number;
    winRate: number;
    maxDrawdown: number;
    totalTrades: number;
    winningTrades: number;
  };
  winLossData: { name: string; value: number }[];
  dayOfWeekData: { name: string; pnl: number }[];
  expectancyData: { name: string; value: number }[];
  streaks: {
    winning: { count: number; value: number };
    losing: { count: number; value: number };
    avgRatio: number;
  };
}

/** `GET /api/risk` — served by the frontend route handler itself. */
export interface RiskResponse {
  limits: {
    maxDailyLoss: number;
    riskPerTrade: number;
    maxPositions: number;
    circuitBreaker: boolean;
  };
  exposureData: { name: string; value: number }[];
  drawdownData: { day: string; dd: number }[];
  correlationMatrix: { asset: string; values: number[] }[];
}

/** `GET /api/logs`. */
export interface LogsResponse {
  logs: string[];
}
