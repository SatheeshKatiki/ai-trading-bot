# Observed option data recorder (Phase 12)

**Research infrastructure. Observes and records. Never trades.**

Phases 8–11 established that this repository contains no historical option
data: the only real option quotes obtainable are live, and they are discarded.
This package writes them down so the options question can eventually be
answered from observation instead of from a model.

## Run it

```bash
# see what it would capture, write nothing
python -m research.option_recorder.collect --once --dry-run

# accumulate, 5-minute cadence (matches the frozen signal's bar size)
python -m research.option_recorder.collect --interval 300

# daily completeness / integrity report
python -m research.option_recorder.qa
```

Requires `api_bridge` running locally with a valid broker session — it reads
`/api/option-chain` and `/api/history` rather than opening a second Fyers
session that would contend with the live one for the same token and rate limit.

## What it guarantees

- **Append-only.** No update or delete path exists; a test asserts the class
  exposes none. RAW broker payloads are stored verbatim and checksummed.
- **Observed is never overwritten by modelled.** A chain returning
  `synthetic: true` is recorded and classified `SYNTHETIC`, which the QA report
  treats as unusable. `REQUIRE_OBSERVED_OPTION_DATA` is the guard any future
  validation harness must assert.
- **`event_time` ≠ `available_at`.** The first is when the market state
  existed, the second when this process could have known it. A future backtest
  filters on the second.
- **The whole chain is kept**, every strike and both sides, whether or not the
  frozen signal would have traded — storing only the contract a later backtest
  likes is exactly the selection bias this exists to avoid.
- **Isolated.** It imports no broker, no risk manager, no exit engine and no
  order type; tests assert both that and that production never imports it.

## Field provenance

`bid`, `ask`, `last_price`, `volume`, `open_interest`, `strike`, `expiry` are
**OBSERVED**. `implied_volatility` and the Greeks are **DERIVED** — the broker
publishes neither, so `api_bridge` solves IV from the real premium and derives
the rest. They are stored as derived, with the raw inputs kept so any later
derivation is reproducible and auditable.

## FINNIFTY

Not a default instrument. Its Phase 9 holdout is sealed; collecting it must be
a deliberate act, and newly collected data must be kept separate from that
partition in any later analysis.
