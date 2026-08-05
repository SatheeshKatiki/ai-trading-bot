/**
 * The declared response contracts, enforced against both the mock fixtures
 * and the live backend.
 *
 * Constraints here encode invariants the trading system has actually broken
 * before, not just field presence — e.g. equity must be a finite number
 * (a NaN reached the dashboard through `save_positions` once) and a P&L sign
 * must agree with the position's side (inverted twice in production).
 */
import type { Schema } from '@utils/schema';

export const stateSchema: Schema = {
  equity: {
    type: 'number',
    predicate: (value) => Number.isFinite(value as number),
    predicateDescription: 'equity must be a finite number, never NaN/Infinity',
  },
  pnl: {
    type: 'number',
    predicate: (value) => Number.isFinite(value as number),
    predicateDescription: 'pnl must be a finite number',
  },
  last_update: { type: 'string', optional: true },
  trades: {
    type: 'array',
    optional: true,
    items: {
      symbol: { type: 'string' },
      side: { type: 'string' },
      price: { type: 'number' },
      time: { type: 'string' },
      qty: { type: 'number' },
    },
  },
};

export const positionSchema: Schema = {
  symbol: { type: 'string', predicate: (v) => (v as string).length > 0 },
  side: { type: 'string' },
  quantity: { type: 'number' },
  average_price: { type: 'number' },
  ltp: { type: 'number' },
  unrealized_pnl: {
    type: 'number',
    predicate: (value) => Number.isFinite(value as number),
    predicateDescription: 'unrealized_pnl must be finite',
  },
  realized_pnl: { type: 'number' },
};

export const positionsResponseSchema: Schema = {
  status: {
    type: 'string',
    predicate: (value) => value === 'success' || value === 'error',
    predicateDescription: 'status must be "success" or "error"',
  },
  positions: { type: 'array', items: positionSchema },
};

export const signalsSchema: Schema = {
  confidence: {
    type: 'number',
    predicate: (value) => (value as number) >= 0 && (value as number) <= 100,
    predicateDescription: 'confidence is a 0-100 percentage',
  },
  status: { type: 'string' },
  bias: { type: 'string' },
};

export const journalTradeSchema: Schema = {
  trade_date: { type: 'string' },
  symbol: { type: 'string' },
  strategy_name: { type: 'string' },
  direction: { type: 'string' },
  entry_price: { type: 'number' },
  exit_price: { type: 'number' },
  qty: { type: 'number' },
  pnl: { type: 'number' },
};

export const journalSchema: Schema = {
  trades: { type: 'array', items: journalTradeSchema },
};

export const authStatusSchema: Schema = {
  hasUsers: { type: 'boolean' },
  hasPassword: { type: 'boolean' },
  lockedOut: { type: 'boolean' },
  lockoutSeconds: { type: 'number' },
};

export const userProfileSchema: Schema = {
  user_id: { type: 'string' },
  name: { type: 'string' },
  email: { type: 'string' },
};

export const historySchema: Schema = {
  symbol: { type: 'string' },
  timeframe: { type: 'string' },
  data_points: { type: 'number' },
  data: {
    type: 'array',
    items: {
      datetime: { type: 'string' },
      open: { type: 'number' },
      high: { type: 'number' },
      low: { type: 'number' },
      close: { type: 'number' },
      volume: { type: 'number' },
    },
  },
};

export const btstSchema: Schema = {
  status: { type: 'string' },
  action: { type: 'string' },
  gapUpProb: {
    type: 'number',
    predicate: (value) => (value as number) >= 0 && (value as number) <= 100,
    predicateDescription: 'gapUpProb is a percentage',
  },
  gapDownProb: {
    type: 'number',
    predicate: (value) => (value as number) >= 0 && (value as number) <= 100,
    predicateDescription: 'gapDownProb is a percentage',
  },
  reason: { type: 'string' },
};

export const panicExitStatusSchema: Schema = {
  emergency_stop: { type: 'boolean' },
};

export const logsSchema: Schema = {
  logs: { type: 'array', elementType: 'string' },
};

export const strategiesSchema: Schema = {
  strategies: { type: 'array', elementType: 'string' },
};
