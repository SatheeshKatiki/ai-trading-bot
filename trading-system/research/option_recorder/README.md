# Observed option data recorder (Phase 12; hardened 13; operated 14)

**Research infrastructure. Observes and records. Never trades.**

Phases 8–11 established that this repository contains no historical option
data: the only real option quotes obtainable are live, and they are discarded.
This package writes them down so the options question can eventually be
answered from observation instead of from a model.

## Run it

```bash
# pre-session go/no-go gate -- exit 0 = GO, exit 2 = do not collect
python -m research.option_recorder.preflight

# see what it would capture, write nothing
python -m research.option_recorder.collect --once --dry-run

# accumulate, 5-minute cadence (matches the frozen signal's bar size)
python -m research.option_recorder.collect --interval 300

# daily health scorecard + integrity report
python -m research.option_recorder.qa

# full evidence report for one session
python -m research.option_recorder.session_report --instrument NIFTY --session YYYY-MM-DD

# progress toward the next checkpoint (20 / 60 / 125 COMPLETE sessions)
python -m research.option_recorder.audit --target 20

# full offline rehearsal: no network, no broker, deletes what it writes
python -m research.option_recorder.selftest
```

**Operating procedure — read this before collecting a real session:**
[`RUNBOOK.md`](RUNBOOK.md). It covers the morning pre-flight that catches a
missing broker session, what each log field means, restart/resume, and the
20 / 60 / 125-session checkpoints.

Requires `api_bridge` running locally with a valid broker session — it reads
`/api/option-chain` and `/api/history` rather than opening a second Fyers
session that would contend with the live one for the same token and rate limit.

## What it guarantees

- **Idempotent.** Every observation has a canonical key; re-polling an
  instant, or restarting mid-session, stores it once. The key set is rebuilt
  from the stored data, so losing the index changes nothing.
- **Durable.** Writes are flushed and `fsync`-ed; checkpoints are written
  atomically. The recorder never reports coverage it does not have.
- **Honest about staleness.** The broker sends no per-leg quote timestamp, so
  `quote_age_seconds` is always `None` — never fabricated. Staleness is
  derived from consecutive observations and kept in its own field.
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
