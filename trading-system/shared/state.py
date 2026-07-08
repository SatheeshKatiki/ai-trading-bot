"""Thread-safe JSON state persistence for live trading.

Performance upgrades vs. original:
  - ``update_equity()`` is now write-through to an **in-memory cache** and
    only flushes to disk every ``_FLUSH_INTERVAL_S`` seconds (default 3 s).
    This eliminates ~dozens of disk reads/writes per minute that were
    blocking the async event-loop thread.
  - ``record_trade()`` still flushes immediately (trades are critical data).
  - A background flush-thread ensures the cache always reaches disk even if
    no further calls are made.
"""

from __future__ import annotations

import contextlib
import json
import sqlite3
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

# Resolve the project root (two levels up from this file)
_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_STATE_DB      = _PROJECT_ROOT / "state.db"

# Flush interval for equity-only updates (seconds).
# Trades always flush immediately regardless of this setting.
_FLUSH_INTERVAL_S: float = 3.0

# ------------------------------------------------------------------
# In-memory cache + lock
# ------------------------------------------------------------------
_LOCK  = threading.Lock()
_CACHE: Dict[str, Any] = {}
_dirty = False           # True when cache differs from what's on disk
_last_flush: float = 0.0 # monotonic timestamp of last disk write

_DEFAULT_STATE: Dict[str, Any] = {
    "equity": 0.0,
    "pnl": 0.0,
    "trades": [],
    "last_update": None,
}


# ------------------------------------------------------------------
# Internal helpers
# ------------------------------------------------------------------

def _init_db() -> None:
    """Initialize the SQLite database with tables if they don't exist."""
    with contextlib.closing(sqlite3.connect(_STATE_DB, timeout=15.0)) as conn:
        cursor = conn.cursor()
        cursor.execute("PRAGMA journal_mode=WAL;")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS state (
                id INTEGER PRIMARY KEY,
                equity REAL,
                pnl REAL,
                last_update TEXT
            )
        """)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT,
                side TEXT,
                price REAL,
                qty INTEGER DEFAULT 1,
                time TEXT
            )
            ''')
            
        # Migration: Add qty column if it doesn't exist
        try:
            cursor.execute("ALTER TABLE trades ADD COLUMN qty INTEGER DEFAULT 1")
        except sqlite3.OperationalError:
            pass # Column already exists
        # Insert default state if empty
        cursor.execute("SELECT COUNT(*) FROM state")
        if cursor.fetchone()[0] == 0:
            cursor.execute("INSERT INTO state (id, equity, pnl, last_update) VALUES (1, 0.0, 0.0, ?)", (datetime.now(timezone.utc).isoformat(),))
        conn.commit()

def _ensure_loaded() -> None:
    """Load state from database into the cache if not yet loaded."""
    global _CACHE
    if _CACHE:
        return
        
    _init_db()
    
    try:
        with contextlib.closing(sqlite3.connect(_STATE_DB, timeout=15.0)) as conn:
            cursor = conn.cursor()
            
            # Load state
            cursor.execute("SELECT equity, pnl, last_update FROM state WHERE id = 1")
            row = cursor.fetchone()
            
            # Load trades
            cursor.execute("SELECT symbol, side, price, time, qty FROM trades ORDER BY id DESC LIMIT 100")
            trades = [{"symbol": r[0], "side": r[1], "price": r[2], "time": r[3], "qty": r[4] if len(r)>4 else 1} for r in cursor.fetchall()]
            trades.reverse() # Restore chronological order
            
            _CACHE = {
                "equity": row[0],
                "pnl": row[1],
                "trades": trades,
                "last_update": row[2]
            }
    except Exception as exc:
        import logging
        logging.getLogger(__name__).error("Failed to load state from DB: %s", exc)
        _CACHE = dict(_DEFAULT_STATE)


def _flush_to_disk() -> None:
    """Write the current cache to database (caller must hold _LOCK)."""
    global _dirty, _last_flush
    try:
        with contextlib.closing(sqlite3.connect(_STATE_DB, timeout=15.0)) as conn:
            cursor = conn.cursor()
            
            # Update state
            cursor.execute(
                "UPDATE state SET equity = ?, pnl = ?, last_update = ? WHERE id = 1",
                (_CACHE["equity"], _CACHE["pnl"], _CACHE["last_update"])
            )
            
            conn.commit()
        
        _dirty = False
        _last_flush = time.monotonic()
    except Exception as exc:
        import logging
        logging.getLogger(__name__).error("State flush failed: %s", exc)


def _background_flusher() -> None:
    """Daemon thread: periodically flush dirty state to disk."""
    while True:
        time.sleep(_FLUSH_INTERVAL_S)
        with _LOCK:
            if _dirty:
                _flush_to_disk()


# Start the background flusher once at import time
_flusher_thread = threading.Thread(
    target=_background_flusher, daemon=True, name="StateFlusher"
)
_flusher_thread.start()


# ------------------------------------------------------------------
# Public API  (same signatures as before — fully backward-compatible)
# ------------------------------------------------------------------

def load_state(reload_trades: bool = False) -> Dict[str, Any]:
    """Return a copy of the current state.  Reads from in-memory cache."""
    with _LOCK:
        _ensure_loaded()
        if reload_trades:
            try:
                import sqlite3
                with contextlib.closing(sqlite3.connect(_STATE_DB, timeout=15.0)) as conn:
                    cursor = conn.cursor()
                    cursor.execute("SELECT symbol, side, price, time, qty FROM trades ORDER BY id DESC LIMIT 100")
                    rows = cursor.fetchall()
                    trades = []
                    for r in rows:
                        trades.append({"symbol": r[0], "side": r[1], "price": r[2], "time": r[3], "qty": r[4] if len(r)>4 else 1})
                    _CACHE["trades"] = trades
            except Exception as e:
                pass
                
        return dict(_CACHE)


def save_state(state: Dict[str, Any]) -> None:
    """Replace the cache with ``state`` and flush to disk immediately."""
    global _CACHE, _dirty
    with _LOCK:
        _CACHE = state
        _dirty = True
        _flush_to_disk()


def update_equity(equity: float, pnl: float) -> None:
    """Update equity/pnl in cache. Deferred flush — does NOT block.

    The background flusher writes through to disk within
    ``_FLUSH_INTERVAL_S`` seconds.  This is safe for dashboard display
    which already auto-refreshes every 5 s.
    """
    global _dirty
    with _LOCK:
        _ensure_loaded()
        _CACHE["equity"] = equity
        _CACHE["pnl"]    = pnl
        _CACHE["last_update"] = datetime.now(timezone.utc).isoformat()
        _dirty = True
        # Only write immediately if it has been long enough since last flush
        if time.monotonic() - _last_flush >= _FLUSH_INTERVAL_S:
            _flush_to_disk()


def record_trade(symbol: str, side: str, price: float, timestamp: str, qty: int = 1) -> None:
    """Append a trade and flush to disk immediately (trades are critical data)."""
    if side not in {"BUY", "SELL"}:
        raise ValueError("side must be 'BUY' or 'SELL'")
    with _LOCK:
        _ensure_loaded()
        
        # Update cache
        _CACHE.setdefault("trades", [])
        _CACHE["trades"].append(
            {"symbol": symbol, "side": side, "price": price, "qty": qty, "time": timestamp}
        )
        if len(_CACHE["trades"]) > 100:
            _CACHE["trades"] = _CACHE["trades"][-100:]
        _CACHE["last_update"] = datetime.now(timezone.utc).isoformat()
        
        # Persist to DB immediately
        try:
            with contextlib.closing(sqlite3.connect(_STATE_DB, timeout=15.0)) as conn:
                cursor = conn.cursor()
                
                # Insert trade
                cursor.execute(
                    "INSERT INTO trades (symbol, side, price, time, qty) VALUES (?, ?, ?, ?, ?)",
                    (symbol, side, price, timestamp, qty)
                )
                
                # Update state (last_update)
                cursor.execute(
                    "UPDATE state SET last_update = ? WHERE id = 1",
                    (_CACHE["last_update"],)
                )
                
                conn.commit()
        except Exception as exc:
            import logging
            logging.getLogger(__name__).error("Failed to record trade in DB: %s", exc)
