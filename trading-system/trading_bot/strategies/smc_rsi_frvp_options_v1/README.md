# smc_rsi_frvp_options_v1 (smc1)

SMC + RSI + Fixed Range Volume Profile, intraday NIFTY options buying.
Design of record: [`docs/strategies/smc_rsi_frvp_options_v1/DESIGN.md`](../../../../docs/strategies/smc_rsi_frvp_options_v1/DESIGN.md).

**Status: Phase B (detectors only).** There is no `generate_signals`, so the
strategy registry imports this package but registers nothing and no engine can
select it. Phase B2 measures whether an entry built on these detectors has an
edge large enough to pay for an option; Phase C is built only if it does.

## Layout

| Module | Spec | What it does |
|---|---|---|
| `config.py` | all | Typed defaults; strict loader for `config/strategies/smc_rsi_frvp_options_v1.json` |
| `types.py` | — | `Bar` (start-stamped, validated), `Pivot`, `StructureEvent`, `Zone`, enums |
| `detectors/atr.py` | 3.11 | Wilder ATR (the shared `atr()` is EMA-based and stays untouched) |
| `detectors/pivots.py` | 3.1 | Causal fractal pivots over the shared `detect_pivots` |
| `detectors/structure.py` | 3.2 | BOS / CHoCH on closes, leg origin |
| `detectors/bias.py` | 3.3, 3.4 | 15m bias with the 1H filter; dealing range, EQ, OTE |
| `detectors/fvg.py` | 3.5, 3.6 | Fair value gaps (fill, invalidation) and displacement candles |
| `detectors/order_blocks.py` | 3.7 | Spec order blocks: creation, touches, invalidation, expiry |
| `detectors/liquidity.py` | 3.8 | EQH/EQL, PDH/PDL/PDC, opening range, 15m swings; sweep + reclaim |
| `detectors/frvp.py` | 3.9 | Own profile (never the shared function); exact 5-point grid; counts zero-volume bars, never invents volume |
| `detectors/momentum.py` | 3.10, 3.12 | Shared RSI / ADX, divergence on confirmed pivots, chop filter |
| `detectors/timeframe.py` | — | One timeframe's detectors wired in dependency order |

Every tracker takes closed bars one at a time through `update()` and never
sees a later bar. `test_smc1_no_lookahead.py` asserts that the state after bar
`k` is identical whether a tracker saw the full history or only bars `0..k`.

## Tests

```
cd trading-system
venv/Scripts/python.exe -m pytest ../Testing_Automation_AI_Trading_Bot/python-unit/smc1 -q
venv/Scripts/python.exe -m mypy --strict --follow-imports=silent --ignore-missing-imports \
    trading_bot/strategies/smc_rsi_frvp_options_v1
```

## Data

`scripts/smc1_fetch_futures_history.py` fetches NIFTY continuous futures
history read-only (cached token, no login, only after 15:45 IST or on a
non-trading day, never while an engine manages positions, stopping on any
token or rate-limit error). It writes only under `data/smc1/`, including
`DATA_REPORT.md`.
