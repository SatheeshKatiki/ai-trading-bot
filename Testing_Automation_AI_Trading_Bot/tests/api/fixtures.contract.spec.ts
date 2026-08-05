/**
 * The mock fixtures must satisfy the same contracts the live backend is held
 * to.
 *
 * Without this, a mocked suite slowly becomes a suite that tests a backend
 * that does not exist: someone edits a fixture to make a UI spec pass, the
 * shape drifts from what FastAPI actually returns, and the whole UI layer is
 * green against fiction. Running the identical schemas here and in
 * `*.live.spec.ts` is what keeps the mocked runs honest.
 */
import { expect, test } from '@fixtures/test';
import {
  authStatusSchema,
  btstSchema,
  historySchema,
  journalSchema,
  logsSchema,
  positionsResponseSchema,
  signalsSchema,
  stateSchema,
  strategiesSchema,
  userProfileSchema,
} from '@utils/api-contracts';
import { assertSchema, validate } from '@utils/schema';
import * as scenario from '@mocks/scenarios';

test.describe('Mock fixtures honour the API contracts', () => {
  test('state fixtures', () => {
    assertSchema(scenario.buildState(), stateSchema, 'buildState()');
    assertSchema(scenario.flatState, stateSchema, 'flatState');
  });

  test('positions fixtures', () => {
    assertSchema(scenario.buildPositionsResponse(), positionsResponseSchema, 'buildPositionsResponse()');
    assertSchema(scenario.emptyPositions, positionsResponseSchema, 'emptyPositions');
    assertSchema(
      scenario.brokerUnauthenticatedPositions,
      positionsResponseSchema,
      'brokerUnauthenticatedPositions',
    );
  });

  test('signals fixtures', () => {
    assertSchema(scenario.buildSignals(), signalsSchema, 'buildSignals()');
    assertSchema(scenario.calculatingSignals, signalsSchema, 'calculatingSignals');
  });

  test('journal fixtures', () => {
    assertSchema(scenario.buildJournal(), journalSchema, 'buildJournal()');
    assertSchema(scenario.emptyJournal, journalSchema, 'emptyJournal');
  });

  test('auth fixtures', () => {
    assertSchema(scenario.authenticatedStatus, authStatusSchema, 'authenticatedStatus');
    assertSchema(scenario.noUsersStatus, authStatusSchema, 'noUsersStatus');
    assertSchema(scenario.lockedOutStatus, authStatusSchema, 'lockedOutStatus');
    assertSchema(scenario.TEST_USER, userProfileSchema, 'TEST_USER');
  });

  test('market-data fixtures', () => {
    assertSchema(scenario.buildHistory(), historySchema, 'buildHistory()');
    assertSchema(scenario.btst, btstSchema, 'btst');
    assertSchema(scenario.logs, logsSchema, 'logs');
    assertSchema(scenario.strategies, strategiesSchema, 'strategies');
  });
});

test.describe('Fixture invariants', () => {
  test('P&L is derived from prices, not hardcoded', () => {
    const long = scenario.buildLongPosition();
    const short = scenario.buildShortPosition();

    expect(long.unrealized_pnl).toBeCloseTo(
      (long.ltp - long.average_price) * long.quantity,
      2,
    );
    // A short in profit: LTP below entry must produce a POSITIVE P&L.
    expect(short.unrealized_pnl).toBeCloseTo(
      (short.average_price - short.ltp) * short.quantity,
      2,
    );
    expect(short.ltp).toBeLessThan(short.average_price);
    expect(short.unrealized_pnl).toBeGreaterThan(0);
  });

  test('candle fixtures are internally consistent', () => {
    for (const candle of scenario.buildCandles(30)) {
      expect(candle.high).toBeGreaterThanOrEqual(Math.max(candle.open, candle.close));
      expect(candle.low).toBeLessThanOrEqual(Math.min(candle.open, candle.close));
      expect(candle.volume).toBeGreaterThan(0);
    }
  });

  test('fixtures are deterministic across calls', () => {
    expect(scenario.buildState()).toEqual(scenario.buildState());
    expect(scenario.buildCandles(10)).toEqual(scenario.buildCandles(10));
    expect(scenario.buildJournal()).toEqual(scenario.buildJournal());
  });

  test('the schema checker actually rejects bad shapes', () => {
    // A validator that never fails would make every check above meaningless.
    const broken = validate({ equity: 'not-a-number', pnl: 0 }, stateSchema);
    expect(broken.valid).toBe(false);
    expect(broken.errors.join(' ')).toContain('expected number');

    const missing = validate({ pnl: 0 }, stateSchema);
    expect(missing.valid).toBe(false);
    expect(missing.errors.join(' ')).toContain('required field is missing');

    const nan = validate({ equity: Number.NaN, pnl: 0 }, stateSchema);
    expect(nan.valid).toBe(false);
  });
});
