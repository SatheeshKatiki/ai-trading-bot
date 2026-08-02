"""Backup and restore for all stateful, non-regenerable data the live
trading engine depends on.

Covers: state.db (equity/PnL/trade history), config/active_positions.json
(open positions — losing this mid-session means the engine forgets it
owns real capital), config/settings.json, config/sessions.json,
config/users.json, config/dashboard_auth.json, the encrypted
broker_credentials.json store, any *_tokens.json cached broker session
tokens, and the audit/ log directory.

Deliberately NOT covered (regenerable, not needed for recovery): trained
model artifacts (models/*.json — retrainable from data), venv, node
caches, and anything already covered by version control.

`create_backup`/`restore_backup` take an explicit `base_dir` so they're
testable against an isolated temp directory instead of the real
trading-system root — see tests/test_disaster_recovery.py.
"""
from __future__ import annotations

import json
import shutil
import sqlite3
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional


# Relative to base_dir (trading-system/). state.db is handled specially
# (via SQLite's online backup API, not a raw file copy) since it may be
# open in WAL mode by a live process.
_JSON_AND_MISC_FILES = [
    "config/active_positions.json",
    "config/settings.json",
    "config/sessions.json",
    "config/users.json",
    "config/dashboard_auth.json",
    "broker_credentials.json",
]
_TOKEN_FILE_GLOB = ".*_tokens.json"
_AUDIT_DIR = "audit"
_STATE_DB = "state.db"
_MANIFEST_NAME = "manifest.json"


@dataclass
class BackupManifest:
    created_at: float
    files: List[str] = field(default_factory=list)
    state_db_included: bool = False
    state_db_last_trade_time: Optional[str] = None


def _latest_trade_time(db_path: Path) -> Optional[str]:
    """Read the most recent trade timestamp (MAX(trades.time)) from a
    state.db, or None if the DB doesn't exist / has no trades yet. Used to
    detect whether a restore would silently discard newer live data than
    the backup has."""
    if not db_path.exists():
        return None
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=5.0)
        try:
            cur = conn.execute("SELECT MAX(time) FROM trades")
            row = cur.fetchone()
            return row[0] if row and row[0] else None
        finally:
            conn.close()
    except sqlite3.Error:
        return None


def create_backup(base_dir: Path, backup_root: Path) -> Path:
    """Create a timestamped backup under `backup_root` of everything listed
    in this module's docstring, found under `base_dir`. Returns the path to
    the created backup directory. Missing files are skipped (e.g. no
    broker_credentials.json yet on a fresh install) rather than treated as
    an error — a partial backup of what exists is still useful.
    """
    base_dir = Path(base_dir)
    backup_root = Path(backup_root)
    stamp = time.strftime("%Y%m%d_%H%M%S")
    dest = backup_root / f"backup_{stamp}"
    dest.mkdir(parents=True, exist_ok=False)

    manifest = BackupManifest(created_at=time.time())

    state_db_path = base_dir / _STATE_DB
    if state_db_path.exists():
        # SQLite's own backup API, not shutil.copy — safe to call even
        # while another process has the DB open in WAL mode, unlike a raw
        # file copy which can grab a half-written page.
        src_conn = sqlite3.connect(f"file:{state_db_path}?mode=ro", uri=True, timeout=10.0)
        try:
            dest_conn = sqlite3.connect(dest / _STATE_DB)
            try:
                src_conn.backup(dest_conn)
            finally:
                dest_conn.close()
        finally:
            src_conn.close()
        manifest.files.append(_STATE_DB)
        manifest.state_db_included = True
        manifest.state_db_last_trade_time = _latest_trade_time(state_db_path)

    for rel_path in _JSON_AND_MISC_FILES:
        src = base_dir / rel_path
        if src.exists():
            target = dest / rel_path
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, target)
            manifest.files.append(rel_path)

    for token_file in base_dir.glob(_TOKEN_FILE_GLOB):
        shutil.copy2(token_file, dest / token_file.name)
        manifest.files.append(token_file.name)

    audit_src = base_dir / _AUDIT_DIR
    if audit_src.exists():
        shutil.copytree(audit_src, dest / _AUDIT_DIR)
        manifest.files.append(_AUDIT_DIR)

    with open(dest / _MANIFEST_NAME, "w", encoding="utf-8") as f:
        json.dump({
            "created_at": manifest.created_at,
            "files": manifest.files,
            "state_db_included": manifest.state_db_included,
            "state_db_last_trade_time": manifest.state_db_last_trade_time,
        }, f, indent=2)

    return dest


class NewerLiveDataError(Exception):
    """Raised when restoring would silently discard trade history newer
    than what the backup contains. Pass force=True to override."""


def restore_backup(backup_dir: Path, base_dir: Path, force: bool = False) -> List[str]:
    """Restore a backup created by create_backup() into base_dir.

    Refuses (raises NewerLiveDataError) if base_dir's current state.db has
    a trade newer than the backup's last recorded trade, unless
    force=True — this is the main way a restore could cause real harm:
    silently rewinding trade/PnL history to an earlier point after the
    engine has already recorded more recent real trades.

    Returns the list of relative paths actually restored.
    """
    backup_dir = Path(backup_dir)
    base_dir = Path(base_dir)
    manifest_path = backup_dir / _MANIFEST_NAME
    if not manifest_path.exists():
        raise FileNotFoundError(f"No manifest.json found in {backup_dir} — not a valid backup directory")

    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    if not force and manifest.get("state_db_included"):
        current_latest = _latest_trade_time(base_dir / _STATE_DB)
        backup_latest = manifest.get("state_db_last_trade_time")
        if current_latest and backup_latest and current_latest > backup_latest:
            raise NewerLiveDataError(
                f"Current state.db has a trade at {current_latest}, newer than this "
                f"backup's latest trade at {backup_latest}. Restoring would discard "
                f"real trade history. Pass force=True if this is intentional."
            )

    restored: List[str] = []

    if manifest.get("state_db_included"):
        src_conn = sqlite3.connect(backup_dir / _STATE_DB)
        try:
            dest_conn = sqlite3.connect(base_dir / _STATE_DB)
            try:
                src_conn.backup(dest_conn)
            finally:
                dest_conn.close()
        finally:
            src_conn.close()
        restored.append(_STATE_DB)

    for rel_path in manifest.get("files", []):
        if rel_path in (_STATE_DB, _AUDIT_DIR):
            continue
        src = backup_dir / rel_path
        if not src.exists():
            continue
        target = base_dir / rel_path
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, target)
        restored.append(rel_path)

    audit_src = backup_dir / _AUDIT_DIR
    if audit_src.exists():
        audit_dest = base_dir / _AUDIT_DIR
        audit_dest.mkdir(parents=True, exist_ok=True)
        for f in audit_src.iterdir():
            shutil.copy2(f, audit_dest / f.name)
        restored.append(_AUDIT_DIR)

    return restored


def list_backups(backup_root: Path) -> List[Path]:
    """Return available backup directories under backup_root, newest first."""
    backup_root = Path(backup_root)
    if not backup_root.exists():
        return []
    return sorted(
        (p for p in backup_root.iterdir() if p.is_dir() and (p / _MANIFEST_NAME).exists()),
        key=lambda p: p.name,
        reverse=True,
    )
