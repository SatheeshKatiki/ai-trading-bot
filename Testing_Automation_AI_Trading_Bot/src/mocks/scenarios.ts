/**
 * Deterministic payload builders — the data half of the mocked backend.
 *
 * Two rules these follow, both learned from the live system:
 *
 * 1. **No `Math.random()`, no `Date.now()` in default payloads.** A dashboard
 *    that renders a different P&L on every run cannot be asserted against.
 *    Anything time-shaped is either fixed or derived from an explicit seed.
 * 2. **Signs and sides are modelled honestly.** A short/PUT position at a
 *    lower LTP is a *profit*; that exact convention was inverted in
 *    production code twice (`exit_engine.py`, then `PyramidSizer`). Fixtures
 *    that quietly get it wrong would let the same bug pass through the UI
 *    layer unnoticed, so the builders compute P&L rather than hardcode it.
 */
import type {
  AnalyticsResponse,
  AuthStatus,
  BotState,
  BtstResponse,
  Candle,
  EngineStatusResponse,
  HistoryResponse,
  JournalResponse,
  JournalTrade,
  LogsResponse,
  OptionChainResponse,
  OptionLeg,
  Position,
  PositionsResponse,
  RiskResponse,
  SentimentResponse,
  SettingsResponse,
  SignalsResponse,
  StateTrade,
  StrategiesResponse,
  UserProfile,
} from '@domain/domain';

/** Anchor for every timestamp in the fixtures: 2026-08-05 10:30 IST. */
export const FIXED_TRADING_DAY = '2026-08-05';

export const TEST_USER: UserProfile = {
  user_id: 'QAI100001',
  name: 'Automation Test User',
  email: 'automation@example.invalid',
};

/** Long option position sitting in profit. */
export function buildLongPosition(overrides: Partial<Position> = {}): Position {
  const quantity = 75;
  const averagePrice = 120.5;
  const ltp = 138.25;
  return {
    symbol: 'NSE:NIFTY2580724500CE',
    side: 'BUY',
    quantity,
    average_price: averagePrice,
    ltp,
    unrealized_pnl: round2((ltp - averagePrice) * quantity),
    realized_pnl: 0,
    product: 'INTRADAY',
    ...overrides,
  };
}

/**
 * Short/PUT position whose LTP fell — i.e. **in profit**.
 *
 * Deliberately included: this is the exact configuration that two separate
 * production bugs got backwards, so at least one fixture must exercise it.
 */
export function buildShortPosition(overrides: Partial<Position> = {}): Position {
  const quantity = 50;
  const averagePrice = 210.0;
  const ltp = 185.5;
  return {
    symbol: 'NSE:NIFTY2580724300PE',
    side: 'SELL',
    quantity,
    average_price: averagePrice,
    ltp,
    unrealized_pnl: round2((averagePrice - ltp) * quantity),
    realized_pnl: 0,
    product: 'INTRADAY',
    ...overrides,
  };
}

export function buildPositionsResponse(
  positions: Position[] = [buildLongPosition(), buildShortPosition()],
): PositionsResponse {
  return { status: 'success', positions };
}

export const emptyPositions: PositionsResponse = { status: 'success', positions: [] };

export const brokerUnauthenticatedPositions: PositionsResponse = {
  status: 'error',
  message: 'Broker not authenticated',
  positions: [],
};

export function buildStateTrades(): StateTrade[] {
  return [
    { symbol: 'NSE:NIFTY2580724500CE', side: 'BUY', price: 120.5, time: `${FIXED_TRADING_DAY} 10:12:04`, qty: 75 },
    { symbol: 'NSE:NIFTY2580724300PE', side: 'SELL', price: 210.0, time: `${FIXED_TRADING_DAY} 11:03:47`, qty: 50 },
    { symbol: 'NSE:NIFTY2580724450CE', side: 'BUY', price: 96.75, time: `${FIXED_TRADING_DAY} 12:41:19`, qty: 75 },
  ];
}

export function buildState(overrides: Partial<BotState> = {}): BotState {
  return {
    equity: 99_925.65,
    pnl: -74.35,
    last_update: `${FIXED_TRADING_DAY} 15:29:58`,
    is_active: true,
    trades: buildStateTrades(),
    ...overrides,
  };
}

/** Fresh account: starting capital, nothing traded yet. */
export const flatState: BotState = {
  equity: 100_000,
  pnl: 0,
  last_update: `${FIXED_TRADING_DAY} 09:15:00`,
  is_active: true,
  trades: [],
};

export function buildSignals(overrides: Partial<SignalsResponse> = {}): SignalsResponse {
  return {
    confidence: 81,
    status: 'Institutional Call Buy Setup',
    bias: 'BUY BIAS',
    direction: 'BUY',
    timestamp: 1_785_000_000,
    trendData: Array.from({ length: 20 }, (_, index) => ({
      name: `1${String(index).padStart(2, '0')}`,
      value: 40 + ((index * 7) % 55),
    })),
    signals: [
      {
        symbol: 'NIFTY',
        type: 'CALL BUY',
        bias: 'BUY',
        strength: 'Strong',
        confidence: 88,
        time: '10:10',
        reason: 'Institutional crossover with score 88',
      },
      {
        symbol: 'NIFTY',
        type: 'PUT BUY',
        bias: 'SELL',
        strength: 'Moderate',
        confidence: 71,
        time: '11:00',
        reason: 'Institutional crossover with score 71',
      },
    ],
    ...overrides,
  };
}

/** What the endpoint returns while `compute_signals` is still running. */
export const calculatingSignals: SignalsResponse = {
  confidence: 50,
  status: 'Scanning...',
  bias: 'NEUTRAL BIAS',
  direction: 'CALCULATING',
};

export function buildJournalTrade(overrides: Partial<JournalTrade> = {}): JournalTrade {
  const entry = 210.0;
  const exit = 285.5;
  const qty = 15;
  return {
    id: 1,
    trade_date: FIXED_TRADING_DAY,
    symbol: 'NSE:NIFTY2580724300PE',
    strategy_name: 'AI Momentum Breakout',
    direction: 'LONG',
    entry_price: entry,
    exit_price: exit,
    qty,
    pnl: round2((exit - entry) * qty),
    ai_feedback: 'Exit taken at resistance; target met.',
    tags: 'PROFIT',
    ...overrides,
  };
}

export function buildJournal(): JournalResponse {
  return {
    trades: [
      buildJournalTrade(),
      buildJournalTrade({
        id: 2,
        symbol: 'NSE:NIFTY2580724500CE',
        direction: 'LONG',
        entry_price: 120.5,
        exit_price: 108.25,
        qty: 75,
        pnl: round2((108.25 - 120.5) * 75),
        ai_feedback: 'Hard stop-loss hit.',
        tags: 'LOSS',
      }),
    ],
  };
}

export const emptyJournal: JournalResponse = { trades: [] };

export function buildHistory(points = 60): HistoryResponse {
  return {
    symbol: 'NSE:NIFTY50-INDEX',
    timeframe: '5 Min',
    data_points: points,
    data: buildCandles(points),
  };
}

/** Deterministic sawtooth OHLCV — shaped like real data, identical every run. */
export function buildCandles(count: number, startPrice = 24_500): Candle[] {
  const candles: Candle[] = [];
  let close = startPrice;
  for (let index = 0; index < count; index += 1) {
    const drift = ((index % 7) - 3) * 4.5;
    const open = close;
    close = round2(open + drift);
    const hour = 9 + Math.floor((15 + index * 5) / 60);
    const minute = (15 + index * 5) % 60;
    candles.push({
      datetime: `${FIXED_TRADING_DAY} ${pad(hour)}:${pad(minute)}:00`,
      open,
      high: round2(Math.max(open, close) + 6),
      low: round2(Math.min(open, close) - 6),
      close,
      volume: 45_000 + (index % 11) * 1_500,
    });
  }
  return candles;
}

export const authenticatedStatus: AuthStatus = {
  hasUsers: true,
  hasPassword: true,
  lockedOut: false,
  lockoutSeconds: 0,
  userCount: 1,
};

export const noUsersStatus: AuthStatus = {
  hasUsers: false,
  hasPassword: false,
  lockedOut: false,
  lockoutSeconds: 0,
  userCount: 0,
};

export const lockedOutStatus: AuthStatus = {
  hasUsers: true,
  hasPassword: true,
  lockedOut: true,
  lockoutSeconds: 240,
  userCount: 1,
};

export const settings: SettingsResponse = {
  active_strategy: 'ema_rsi',
  active_broker: 'fyers',
  emergency_stop: false,
  target_pct: 2.5,
  stoploss_pct: 0.5,
  trailing_sl: true,
  ema_fast: 20,
  ema_slow: 50,
  rsi_window: 14,
  rsi_buy: 55,
  rsi_sell: 45,
  max_daily_trades: 3,
  max_daily_loss_pct: 3.0,
};

export const strategies: StrategiesResponse = {
  strategies: ['ema_rsi', 'advanced_ai_ml', 'donchian_breakout', 'vwap_reversion'],
};

export const engineRunning: EngineStatusResponse = { is_active: true, status: 'running' };
export const engineHalted: EngineStatusResponse = { is_active: false, status: 'halted' };

/**
 * `GET /api/sentiment`, shaped exactly as `shared/sentiment.py` returns it:
 * `{score, label, top_headlines[]}`.
 *
 * The field names matter more than they look. `NewsTicker` assigns the
 * response straight into state and then reads `top_headlines[index]` with no
 * guard, so a payload missing that key takes down the entire dashboard with a
 * runtime TypeError — which is exactly what an earlier, plausible-looking
 * version of this fixture did.
 */
export const sentiment: SentimentResponse = {
  score: 0.2,
  label: 'Bullish',
  top_headlines: [
    {
      title_en: 'Nifty holds gains into the close',
      title_te: 'నిఫ్టీ ముగింపులో లాభాలను నిలుపుకుంది',
      link: 'https://example.invalid/nifty-close',
      published: `${FIXED_TRADING_DAY} 15:31`,
      sentiment: 0.45,
    },
    {
      title_en: 'IT stocks lead the advance',
      title_te: 'ఐటీ షేర్లు ముందంజలో',
      link: 'https://example.invalid/it-stocks',
      published: `${FIXED_TRADING_DAY} 14:02`,
      sentiment: 0.2,
    },
  ],
};

/** Backend still warming its RSS cache — headlines empty but keys present. */
export const sentimentLoading: SentimentResponse = {
  score: 0.0,
  label: 'Loading...',
  top_headlines: [],
};

/**
 * `GET /api/option-chain`, in the shape `frontend/app/api/option-chain/route.ts`
 * emits (`ce`/`pe` legs, not the Python backend's `call`/`put` — the proxy
 * transforms them before the page sees them).
 *
 * A non-empty `chain` is not optional: the Options Desk computes its ATM
 * strike with `chain.reduce(...)` and no initial value, so an empty array
 * throws "Reduce of empty array" and takes the page down.
 */
export function buildOptionLeg(overrides: Partial<OptionLeg> = {}): OptionLeg {
  return {
    ltp: 120.5,
    volume: 145_000,
    oi: 2_450_000,
    oichg: 3.2,
    delta: 0.52,
    gamma: 0.0031,
    theta: -8.4,
    vega: 12.1,
    ...overrides,
  };
}

export function buildOptionChain(spot = 52_100, strikes = 9): OptionChainResponse {
  const step = 100;
  const atm = Math.round(spot / step) * step;
  const start = atm - Math.floor(strikes / 2) * step;

  return {
    symbol: 'NSE:BANKNIFTY-INDEX',
    underlying_price: spot,
    atm,
    maxPain: atm,
    pcr: 0.92,
    expiry: '2026-08-07',
    chain: Array.from({ length: strikes }, (_, index) => {
      const strike = start + index * step;
      const moneyness = (strike - atm) / step;
      return {
        strike,
        ce: buildOptionLeg({
          ltp: round2(Math.max(2, 150 - moneyness * 25)),
          delta: round2(Math.min(0.95, Math.max(0.05, 0.5 - moneyness * 0.08))),
        }),
        pe: buildOptionLeg({
          ltp: round2(Math.max(2, 150 + moneyness * 25)),
          delta: round2(Math.max(-0.95, Math.min(-0.05, -0.5 - moneyness * 0.08))),
        }),
      };
    }),
  };
}

export const btst: BtstResponse = {
  status: 'active',
  action: 'CARRY CALL',
  gapUpProb: 72,
  gapDownProb: 28,
  reason: 'Strong daily rally holding well into EOD. High probability of Gap Up.',
  metrics: { momentum: 0.62, rsi: 61.4 },
};

/**
 * `GET /api/analytics` — assembled by the Next.js route handler from
 * `trading-system/backtest_results.json`.
 *
 * Every field here is dereferenced unguarded by the Analytics page
 * (`stats.expectancy.toLocaleString(...)` among them), so a partial payload
 * crashes the page rather than degrading it. This fixture matches the shape
 * the route returns even for a missing results file.
 */
export const analytics: AnalyticsResponse = {
  stats: {
    profitFactor: 1.84,
    expectancy: 412.35,
    winRate: 58,
    maxDrawdown: 6.4,
    totalTrades: 31,
    winningTrades: 18,
  },
  winLossData: [
    { name: 'Winning Trades', value: 58 },
    { name: 'Losing Trades', value: 42 },
  ],
  dayOfWeekData: [
    { name: 'Mon', pnl: 1240.5 },
    { name: 'Tue', pnl: -320.25 },
    { name: 'Wed', pnl: 880.0 },
    { name: 'Thu', pnl: 1610.75 },
    { name: 'Fri', pnl: -145.5 },
  ],
  expectancyData: [
    { name: 'Trade 1', value: 412.35 },
    { name: 'Trade 2', value: 388.1 },
  ],
  streaks: {
    winning: { count: 4, value: 3120.5 },
    losing: { count: 2, value: -640.25 },
    avgRatio: 1.72,
  },
};

/** No backtest results on disk — the route's own empty-state payload. */
export const analyticsEmpty: AnalyticsResponse = {
  stats: {
    profitFactor: 0,
    expectancy: 0,
    winRate: 0,
    maxDrawdown: 0,
    totalTrades: 0,
    winningTrades: 0,
  },
  winLossData: [],
  dayOfWeekData: [],
  expectancyData: [],
  streaks: {
    winning: { count: 0, value: 0 },
    losing: { count: 0, value: 0 },
    avgRatio: 0,
  },
};

export const risk: RiskResponse = {
  limits: { maxDailyLoss: 10_000, riskPerTrade: 1.5, maxPositions: 5, circuitBreaker: true },
  exposureData: [
    { name: 'Nifty 50', value: 45 },
    { name: 'Bank Nifty', value: 35 },
    { name: 'IT Sector', value: 20 },
  ],
  drawdownData: [
    { day: 'Mon', dd: 2 },
    { day: 'Tue', dd: 5 },
    { day: 'Wed', dd: 1 },
    { day: 'Thu', dd: 8 },
    { day: 'Fri', dd: 3 },
  ],
  correlationMatrix: [
    { asset: 'Nifty 50', values: [1.0, 0.82, 0.45] },
    { asset: 'Bank Nifty', values: [0.82, 1.0, 0.12] },
    { asset: 'IT Index', values: [0.45, 0.12, 1.0] },
  ],
};

export const logs: LogsResponse = {
  logs: [
    `[${FIXED_TRADING_DAY} 10:12:04] INFO trading_bot.main: Entry signal accepted (score 88)`,
    `[${FIXED_TRADING_DAY} 10:12:05] INFO brokers.fyers_broker: Paper order filled @ 120.50`,
    `[${FIXED_TRADING_DAY} 11:03:47] INFO trading_bot.exit_engine: Partial profit booked`,
  ],
};

function round2(value: number): number {
  return Math.round(value * 100) / 100;
}

function pad(value: number): string {
  return String(value).padStart(2, '0');
}
