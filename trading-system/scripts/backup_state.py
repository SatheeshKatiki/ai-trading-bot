"""CLI: back up all live trading state (positions, trade history, config,
credentials, audit log) to backups/backup_<timestamp>/.

Usage:
    python scripts/backup_state.py

Intended to be run manually before risky operations (deploys, credential
rotation, manual DB surgery) and can be put on a cron/scheduled task for
periodic backups. See docs/DISASTER_RECOVERY.md for the full runbook.
"""
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from shared.disaster_recovery import create_backup

BASE_DIR = Path(__file__).resolve().parents[1]
BACKUP_ROOT = BASE_DIR / "backups"


def main() -> None:
    dest = create_backup(BASE_DIR, BACKUP_ROOT)
    manifest = dest / "manifest.json"
    print(f"Backup created at: {dest}")
    print(f"Manifest: {manifest}")


if __name__ == "__main__":
    main()
