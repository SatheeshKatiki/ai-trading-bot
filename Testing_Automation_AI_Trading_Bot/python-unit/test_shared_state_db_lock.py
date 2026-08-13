"""Regression test for shared/state.py under real SQLite lock contention.

Both trading_bot/main.py and api_bridge.py are separate OS processes that
both touch the same state.db file. shared/state.py already mitigates this
with WAL mode (set once in _init_db, persists for the file) and
timeout=30.0 on every connection (SQLite's busy_timeout -- the retry/
backoff mechanism for "database is locked"). No test previously proved
this actually holds under a real competing lock; this one does, against a
real SQLite file in an isolated tmp_path (never the actual project's
state.db).
"""
import sqlite3
import threading
import time

import pytest

import _bootstrap  # noqa: F401  (side-effect: puts trading-system/ on sys.path)

import shared.state as state


@pytest.fixture
def isolated_state_db(tmp_path, monkeypatch):
    """Points shared.state at a fresh, isolated state.db and resets its
    module-level cache so each test genuinely exercises the DB, not a
    previous test's (or the real project's) in-memory cache."""
    db_path = tmp_path / "state.db"
    monkeypatch.setattr(state, "_STATE_DB", db_path)
    monkeypatch.setattr(state, "_CACHE", {})
    monkeypatch.setattr(state, "_dirty", False)
    monkeypatch.setattr(state, "_state_loaded_at", 0.0)
    return db_path


def test_save_state_waits_out_a_transient_competing_write_lock(isolated_state_db):
    """A second connection holds an uncommitted write (mirroring main.py
    and api_bridge.py both touching state.db around the same moment) for
    ~1s, then releases. shared.state's timeout=30.0 busy_timeout must let
    save_state's write succeed once the lock clears -- not immediately
    raise "database is locked", and not silently skip/corrupt the write.
    """
    state._ensure_loaded()  # creates the DB/tables via _init_db()

    holder_ready = threading.Event()
    release_lock = threading.Event()
    holder_error = []

    def _hold_competing_lock():
        try:
            conn = sqlite3.connect(isolated_state_db, timeout=30.0)
            conn.execute("BEGIN IMMEDIATE")
            conn.execute("UPDATE state SET equity = 999999 WHERE id = 1")
            holder_ready.set()
            release_lock.wait(timeout=10)
            conn.commit()
            conn.close()
        except Exception as e:
            holder_error.append(e)

    holder = threading.Thread(target=_hold_competing_lock)
    holder.start()
    assert holder_ready.wait(timeout=5), "competing lock was never acquired"

    def _release_after_delay():
        time.sleep(1.0)
        release_lock.set()

    threading.Thread(target=_release_after_delay, daemon=True).start()

    start = time.monotonic()
    state.save_state({"equity": 42.0, "pnl": 1.0, "trades": [], "last_update": "test"})
    elapsed = time.monotonic() - start

    holder.join(timeout=5)
    assert holder_error == []

    # Must have genuinely waited for the competing lock to clear (proving
    # the busy_timeout retry actually engaged), not returned instantly
    # having silently no-op'd, and the write must have actually landed.
    assert elapsed >= 0.5, (
        f"save_state returned in {elapsed:.2f}s -- expected it to block "
        f"on the competing lock for close to the full ~1s hold"
    )
    reloaded = state.load_state(reload_state=True)
    assert reloaded["equity"] == 42.0


def test_record_trade_survives_a_competing_lock_on_the_trades_table(isolated_state_db):
    """Same scenario, but for the immediate-flush trade-write path
    (record_trade), which is the more safety-critical of the two --
    trades must never be silently dropped under contention."""
    state._ensure_loaded()

    holder_ready = threading.Event()
    release_lock = threading.Event()

    def _hold_competing_lock():
        conn = sqlite3.connect(isolated_state_db, timeout=30.0)
        conn.execute("BEGIN IMMEDIATE")
        conn.execute("UPDATE state SET pnl = 12345 WHERE id = 1")
        holder_ready.set()
        release_lock.wait(timeout=10)
        conn.commit()
        conn.close()

    holder = threading.Thread(target=_hold_competing_lock)
    holder.start()
    assert holder_ready.wait(timeout=5)
    threading.Timer(1.0, release_lock.set).start()

    state.record_trade("NSE:NIFTY50-INDEX", "BUY", 100.0, "2026-08-14T00:00:00", qty=50)
    # record_trade enqueues to the background flusher thread rather than
    # writing inline -- give it a moment to actually land.
    deadline = time.monotonic() + 10
    landed = False
    while time.monotonic() < deadline:
        conn = sqlite3.connect(isolated_state_db, timeout=5.0)
        row = conn.execute(
            "SELECT symbol, side, price, qty FROM trades WHERE symbol = ?",
            ("NSE:NIFTY50-INDEX",),
        ).fetchone()
        conn.close()
        if row is not None:
            landed = True
            break
        time.sleep(0.2)

    holder.join(timeout=5)
    assert landed, "trade was never written to the DB despite the competing lock clearing"
    assert row == ("NSE:NIFTY50-INDEX", "BUY", 100.0, 50)
