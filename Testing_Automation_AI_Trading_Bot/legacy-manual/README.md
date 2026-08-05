# Legacy manual probes — NOT part of any automated suite

Everything in this directory was named `test_*.py` and lived in
`trading-system/tests/`, where pytest collected it alongside the real suite.
None of it is a test:

* no assertions — they `print()` and exit
* they need a **live, authenticated Fyers session** (a cached OAuth token)
* two of them (`probe_funds.py`, `probe_nifty.py`) have a **client ID
  hardcoded in the source**
* `probe_backtest.py` was already being excluded in CI by name
  (`pytest -k "not test_bt"`), which is what a permanent exclusion looks like
  when it hasn't been made permanent yet

They were renamed `probe_*.py` so pytest no longer collects them, and moved
here so the automated suite is exactly the things that assert something.
They still have real diagnostic value when the broker connection itself is
in question, so they are kept rather than deleted.

## Running one

They expect the application root as the working directory:

```powershell
cd "trading-system"
.\venv\Scripts\python.exe "..\Testing_Automation_AI_Trading_Bot\legacy-manual\probe_connection.py"
```

| File | What it prints | Needs live broker |
|---|---|---|
| `probe_connection.py` | Fyers profile response for the cached token | yes |
| `probe_funds.py` | Raw `funds()` payload | yes |
| `probe_nifty.py` | Raw NIFTY 50 history response | yes |
| `probe_history.py` | Candle count + a strategy/backtest smoke run | yes |
| `probe_backtest.py` | A full one-year backtest with timings | yes |
| `inject_mock_trade.py` | **See the warning below** | no |

## ⚠️ `inject_mock_trade.py`

Formerly `trading-system/scripts/e2e_test.py`. It opens
`trading-system/state.db` **by absolute path** and `INSERT`s fabricated rows
into `trades` and `trade_journal`.

That is the live paper-trading journal. Rows it writes are
indistinguishable from real fills in the dashboard, in `/api/state`, and in
every P&L figure derived from that table — and pollution of exactly this
kind is what forced the full `state.db` reset on 2026-08-05 (see
`docs/paper_trading_validation/anomaly_log.md`).

**Do not run it during the paper-trading validation window.** If you need
seeded trade data, use the Playwright suite's mocked backend
(`src/mocks/`), which produces the same UI states without writing to any
database. If you must run it, back up `state.db` first —
`trading-system/scripts/backup_state.py` does this.
