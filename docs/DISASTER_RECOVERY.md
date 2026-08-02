# Disaster Recovery Runbook

Covers backup and restore for the live trading engine's stateful data.
Implementation: `trading-system/shared/disaster_recovery.py`, exercised via
`trading-system/scripts/backup_state.py` and `.../scripts/restore_state.py`,
tested in `trading-system/tests/test_disaster_recovery.py`.

## What's backed up

| File | Why it matters |
|---|---|
| `state.db` | Equity, PnL, full trade history |
| `config/active_positions.json` | Open positions the engine believes it owns — losing this while a position is genuinely open means the engine no longer knows it has real capital at risk |
| `config/settings.json` | Active strategy, risk limits, filters |
| `config/sessions.json`, `config/users.json`, `config/dashboard_auth.json` | Dashboard login state |
| `broker_credentials.json` | Encrypted broker API credentials |
| `.fyers_tokens.json` / `.<broker>_tokens.json` | Cached encrypted broker session tokens |
| `audit/` | Append-only compliance/audit log |

Not backed up (deliberately): trained model artifacts under `models/` (retrain
from data instead of restoring stale weights), `venv/`, `node_modules/`,
anything already in version control.

## Taking a backup

```bash
cd trading-system
python scripts/backup_state.py
```

Creates `trading-system/backups/backup_<YYYYMMDD_HHMMSS>/` with a
`manifest.json` listing what was captured. `state.db` is copied via
SQLite's own online backup API (safe even while the live engine has it
open in WAL mode) — never copy `state.db` with a plain file copy while
the engine is running, you can grab a half-written page.

`backups/` is gitignored — it contains encrypted credentials and cached
broker tokens verbatim. Do not commit it, and do not copy backups outside
this machine without treating them with the same care as the live
credentials themselves.

**When to run it:** before any deploy, before rotating broker credentials,
before manual DB surgery, and on a periodic schedule (cron / Windows
Task Scheduler) if you want point-in-time recovery beyond "immediately
before the last risky change."

## Restoring a backup

```bash
cd trading-system
python scripts/restore_state.py --list
python scripts/restore_state.py --backup backups/backup_20260802_170651
```

The restore script **always takes a fresh safety backup of the current
state before overwriting anything** — a restore is itself always
reversible.

If the live `state.db` has a trade recorded *after* the backup you're
restoring, the script refuses and prints `REFUSED: ...` rather than
silently rewinding trade history. This is the main way a restore could
cause real harm — you'd be telling the system to forget trades (and the
PnL they represent) that actually happened. If you're certain that's what
you want (e.g. you know the newer "trades" were corrupted/bogus), re-run
with `--force`.

## Scenario playbook

**Corrupted or deleted `state.db` (engine won't start / dashboard shows
garbage equity):**
1. Stop the engine if it's still running.
2. `python scripts/restore_state.py --list` to find the most recent good backup.
3. `python scripts/restore_state.py --backup <path>`.
4. Restart the engine, confirm equity/PnL/trade history in the dashboard
   look right before resuming live trading.

**Lost/corrupted `config/active_positions.json` while a real position is
open:**
1. **Do not just restore blindly** — the position may have moved since the
   backup. First check the broker's own positions/order book directly
   (dashboard's Positions tab, or the broker's own app) to see real
   current exposure.
2. Restore `config/active_positions.json` from the most recent backup as a
   starting point.
3. On next engine start, the existing reconnect-reconciliation logic
   (`trading_bot/reconciliation.py`) will reconcile local state against
   what the broker actually reports the next time a WebSocket reconnect
   fires — but don't rely on that alone if you know a position closed;
   verify manually first.

**Lost `broker_credentials.json` / cached tokens:**
1. Restore from backup if you have one from before the loss.
2. If no backup exists, credentials must be re-entered from scratch via
   the normal broker-connect flow (`brokers/credentials.py` /
   `scripts/auth/auto_login_fyers.py`) — there is no way to recover an
   encrypted credential file without either the backup or the original
   plaintext values.
3. **Rotate the credentials afterward regardless** — if the loss was due to
   a compromised machine/disk, treat the old credentials as potentially
   exposed.

**Full machine loss (disk failure, machine destroyed):**
1. This system currently runs on a single local machine with backups
   stored on the same disk (`trading-system/backups/`) — a full disk/
   machine failure with no external copy means **total data loss**, not
   just an inconvenience. If you want real disaster tolerance (not just
   crash recovery), copy `backups/` to a separate physical location or
   external/cloud storage on some cadence — this is not currently
   automated.
2. Once a new machine is provisioned: clone the repo, restore the most
   recent off-machine backup copy into place, re-authenticate broker
   credentials if the tokens have since expired, verify equity/PnL/trade
   history before resuming live trading.

## What this does NOT cover

- **Off-machine/offsite backup replication.** Backups currently live next
  to the data they protect. A single-disk failure takes out both.
- **Automated scheduled backups.** `backup_state.py` must be run manually
  or wired into a scheduler (cron/Task Scheduler) — it isn't triggered
  automatically by anything today.
- **Broker-side state** (actual open positions/orders/funds at the
  broker). This system's backups only cover *this engine's local view* —
  always cross-check against the broker's own records after any restore.
