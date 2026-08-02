"""Regression tests for shared/disaster_recovery.py.

Root-cause fix (production-readiness audit finding): there was no backup
or restore capability anywhere in this codebase — a corrupted state.db,
an accidentally deleted config/active_positions.json, or a lost
broker_credentials.json had no recovery path other than losing that
data outright. These tests exercise real backup/restore round-trips
against real SQLite databases and real files in isolated temp
directories (never the actual project's state files), including the
safety check that refuses to silently discard newer trade history.
"""
import json
import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

import pytest

from shared.disaster_recovery import (
    NewerLiveDataError, create_backup, list_backups, restore_backup,
)


def _make_state_db(path: Path, trades: list[tuple[str, str, float, int, str]], equity: float = 100000.0, pnl: float = 0.0) -> None:
    """Create a real state.db matching shared/state.py's actual schema."""
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE state (id INTEGER PRIMARY KEY, equity REAL, pnl REAL, last_update TEXT)")
    conn.execute("CREATE TABLE trades (id INTEGER PRIMARY KEY AUTOINCREMENT, symbol TEXT, side TEXT, price REAL, qty INTEGER DEFAULT 1, time TEXT)")
    conn.execute("INSERT INTO state (id, equity, pnl, last_update) VALUES (1, ?, ?, ?)", (equity, pnl, "2026-08-02T10:00:00"))
    for symbol, side, price, qty, ts in trades:
        conn.execute("INSERT INTO trades (symbol, side, price, qty, time) VALUES (?, ?, ?, ?, ?)", (symbol, side, price, qty, ts))
    conn.commit()
    conn.close()


@pytest.fixture
def sandbox():
    """An isolated base_dir + backup_root, cleaned up after the test."""
    tmp = Path(tempfile.mkdtemp(prefix="dr_test_"))
    base_dir = tmp / "trading-system"
    backup_root = tmp / "backups"
    (base_dir / "config").mkdir(parents=True)
    yield base_dir, backup_root
    shutil.rmtree(tmp, ignore_errors=True)


def test_backup_captures_state_db_and_config_files(sandbox):
    base_dir, backup_root = sandbox
    _make_state_db(base_dir / "state.db", trades=[("NIFTY25AUG24000CE", "SELL", 135.0, 65, "2026-08-02T10:15:00")])
    (base_dir / "config" / "active_positions.json").write_text('{"NIFTY25AUG24000CE": {"quantity": 65}}')
    (base_dir / "config" / "settings.json").write_text('{"active_strategy": "premium"}')
    (base_dir / "broker_credentials.json").write_text('{"encrypted": "fake-ciphertext"}')

    dest = create_backup(base_dir, backup_root)

    assert (dest / "state.db").exists()
    assert (dest / "config" / "active_positions.json").exists()
    assert (dest / "config" / "settings.json").exists()
    assert (dest / "broker_credentials.json").exists()
    assert (dest / "manifest.json").exists()

    manifest = json.loads((dest / "manifest.json").read_text())
    assert manifest["state_db_included"] is True
    assert manifest["state_db_last_trade_time"] == "2026-08-02T10:15:00"
    assert "config/active_positions.json" in manifest["files"]


def test_backup_skips_missing_files_without_erroring(sandbox):
    base_dir, backup_root = sandbox
    # Nothing exists yet (fresh install scenario) except the empty config dir.
    dest = create_backup(base_dir, backup_root)
    manifest = json.loads((dest / "manifest.json").read_text())
    assert manifest["files"] == []
    assert manifest["state_db_included"] is False


def test_restore_round_trip_preserves_trade_history_exactly(sandbox):
    base_dir, backup_root = sandbox
    _make_state_db(
        base_dir / "state.db",
        trades=[
            ("NIFTY25AUG24000CE", "BUY", 100.0, 65, "2026-08-02T10:00:00"),
            ("NIFTY25AUG24000CE", "SELL", 135.0, 65, "2026-08-02T10:15:00"),
        ],
        equity=105275.0, pnl=2275.0,
    )
    (base_dir / "config" / "active_positions.json").write_text("{}")

    backup_dir = create_backup(base_dir, backup_root)

    # Simulate disaster: state.db corrupted/deleted, position file wiped.
    (base_dir / "state.db").unlink()
    (base_dir / "config" / "active_positions.json").write_text("CORRUPTED")

    restored = restore_backup(backup_dir, base_dir)

    assert "state.db" in restored
    assert "config/active_positions.json" in restored

    conn = sqlite3.connect(base_dir / "state.db")
    trades = conn.execute("SELECT symbol, side, price, qty, time FROM trades ORDER BY id").fetchall()
    equity_row = conn.execute("SELECT equity, pnl FROM state WHERE id = 1").fetchone()
    conn.close()

    assert trades == [
        ("NIFTY25AUG24000CE", "BUY", 100.0, 65, "2026-08-02T10:00:00"),
        ("NIFTY25AUG24000CE", "SELL", 135.0, 65, "2026-08-02T10:15:00"),
    ]
    assert equity_row == (105275.0, 2275.0)
    assert (base_dir / "config" / "active_positions.json").read_text() == "{}"


def test_restore_refuses_to_discard_newer_trade_history_without_force(sandbox):
    base_dir, backup_root = sandbox
    _make_state_db(base_dir / "state.db", trades=[("NIFTY", "BUY", 100.0, 1, "2026-08-02T09:00:00")])
    backup_dir = create_backup(base_dir, backup_root)

    # A newer trade lands after the backup was taken (e.g. trading continued).
    conn = sqlite3.connect(base_dir / "state.db")
    conn.execute("INSERT INTO trades (symbol, side, price, qty, time) VALUES (?, ?, ?, ?, ?)",
                 ("NIFTY", "SELL", 105.0, 1, "2026-08-02T11:00:00"))
    conn.commit()
    conn.close()

    with pytest.raises(NewerLiveDataError):
        restore_backup(backup_dir, base_dir)

    # Confirm it genuinely didn't touch anything on refusal.
    conn = sqlite3.connect(base_dir / "state.db")
    count = conn.execute("SELECT COUNT(*) FROM trades").fetchone()[0]
    conn.close()
    assert count == 2  # both the original and the newer trade still present, untouched


def test_restore_with_force_overrides_the_newer_data_check(sandbox):
    base_dir, backup_root = sandbox
    _make_state_db(base_dir / "state.db", trades=[("NIFTY", "BUY", 100.0, 1, "2026-08-02T09:00:00")])
    backup_dir = create_backup(base_dir, backup_root)

    conn = sqlite3.connect(base_dir / "state.db")
    conn.execute("INSERT INTO trades (symbol, side, price, qty, time) VALUES (?, ?, ?, ?, ?)",
                 ("NIFTY", "SELL", 105.0, 1, "2026-08-02T11:00:00"))
    conn.commit()
    conn.close()

    restored = restore_backup(backup_dir, base_dir, force=True)
    assert "state.db" in restored

    conn = sqlite3.connect(base_dir / "state.db")
    count = conn.execute("SELECT COUNT(*) FROM trades").fetchone()[0]
    conn.close()
    assert count == 1  # rewound to the backup's single trade, as explicitly forced


def test_list_backups_returns_newest_first(sandbox):
    base_dir, backup_root = sandbox
    b1 = create_backup(base_dir, backup_root)
    import time as _time
    _time.sleep(1.1)  # backup dir names are second-resolution timestamps
    b2 = create_backup(base_dir, backup_root)

    backups = list_backups(backup_root)
    assert backups[0] == b2
    assert backups[1] == b1


def test_restore_raises_on_invalid_backup_directory(sandbox):
    base_dir, backup_root = sandbox
    not_a_backup = backup_root / "not_a_real_backup"
    not_a_backup.mkdir(parents=True)
    with pytest.raises(FileNotFoundError):
        restore_backup(not_a_backup, base_dir)
