# smc_rsi_frvp_options_v1 (smc1) — changelog

All work is on branch `feature/smc1`. Nothing is registered with the strategy
registry or selectable by any engine.

## Phase B — detectors (2026-10-01)

### Added
- `trading_bot/strategies/smc_rsi_frvp_options_v1/`: typed config with a
  strict JSON loader; value types; step-by-step causal detectors for pivots,
  BOS/CHoCH, 15m bias with the 1H filter, dealing range (EQ, OTE), FVGs,
  displacement candles, order blocks, liquidity levels (EQH/EQL, PDH/PDL/PDC,
  opening range, 15m swings) with sweep-and-reclaim, fixed range volume
  profiles (previous day, impulse leg, session to date; computed in smc1, never
  by the shared volume-profile function), RSI, divergence, ADX
  and the chop filter; Wilder ATR (owner decision D6).
- `config/strategies/smc_rsi_frvp_options_v1.json` with every detector
  parameter at the spec default.
- `scripts/smc1_fetch_futures_history.py`: read-only NIFTY continuous futures
  fetch with a data-quality report, under the owner's conditions (DESIGN.md
  §18.3).
- 157 tests in `Testing_Automation_AI_Trading_Bot/python-unit/smc1/`,
  including a no-lookahead property test and the D1 disagreement test against
  `calculate_smc`; fixture `fixtures/data/smc1_nifty_5m_2026-06.csv`.

### Changed
- `Testing_Automation_AI_Trading_Bot/python-unit/test_rsi_smc_isolation.py`:
  one line, adding `smc_rsi_frvp_options_v1` to the known strategy packages
  (owner approval, 2026-10-01). Nothing else outside the new files.

## Phase A — design (2026-10-01)
- DESIGN.md: audit, reuse map, project fit, owner decisions, revised phase
  plan with the B2 GO/NO-GO gate (theta counted).
