"""CLI: restore live trading state from a backup created by backup_state.py.

Usage:
    python scripts/restore_state.py --list
    python scripts/restore_state.py --backup backups/backup_20260802_120000
    python scripts/restore_state.py --backup backups/backup_20260802_120000 --force

Refuses to restore over a state.db that has trade history newer than the
backup being restored, unless --force is passed — see
docs/DISASTER_RECOVERY.md for when that's actually the right call.

Always takes a fresh safety backup of the CURRENT state before
overwriting anything, so a restore is itself always undoable.
"""
import argparse
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from shared.disaster_recovery import create_backup, list_backups, restore_backup, NewerLiveDataError

BASE_DIR = Path(__file__).resolve().parents[1]
BACKUP_ROOT = BASE_DIR / "backups"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backup", type=str, help="Path to the backup directory to restore")
    parser.add_argument("--list", action="store_true", help="List available backups and exit")
    parser.add_argument("--force", action="store_true", help="Restore even if it would discard newer trade history")
    args = parser.parse_args()

    if args.list or not args.backup:
        backups = list_backups(BACKUP_ROOT)
        if not backups:
            print(f"No backups found under {BACKUP_ROOT}")
        else:
            print("Available backups (newest first):")
            for b in backups:
                print(f"  {b}")
        if not args.backup:
            return

    backup_dir = Path(args.backup)
    if not backup_dir.is_absolute():
        backup_dir = BASE_DIR / backup_dir

    # A restore is itself always undoable: snapshot current state first.
    safety_backup = create_backup(BASE_DIR, BACKUP_ROOT)
    print(f"Safety backup of current state taken at: {safety_backup}")

    try:
        restored = restore_backup(backup_dir, BASE_DIR, force=args.force)
    except NewerLiveDataError as e:
        print(f"REFUSED: {e}")
        print("Re-run with --force if you're certain you want to discard that newer history.")
        sys.exit(1)

    print(f"Restored from {backup_dir}:")
    for f in restored:
        print(f"  {f}")


if __name__ == "__main__":
    main()
