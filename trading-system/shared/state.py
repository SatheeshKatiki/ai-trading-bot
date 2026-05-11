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

import json
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

# Resolve the project root (two levels up from this file)
_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_STATE_FILE    = _PROJECT_ROOT / "state.json"

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

def _ensure_loaded() -> None:
    """Load state from disk into the cache if not yet loaded."""
    global _CACHE
    if _CACHE:
        return
    if _STATE_FILE.is_file():
        try:
            with open(_STATE_FILE, "r", encoding="utf-8") as f:
                _CACHE = json.load(f)
        except (json.JSONDecodeError, OSError):
            _CACHE = dict(_DEFAULT_STATE)
    else:
        _CACHE = dict(_DEFAULT_STATE)
        _flush_to_disk()


def _flush_to_disk() -> None:
    """Write the current cache to disk atomically (caller must hold _LOCK)."""
    global _dirty, _last_flush
    tmp = _STATE_FILE.with_suffix(".tmp")
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(_CACHE, f, indent=2)
        tmp.replace(_STATE_FILE)
        _dirty = False
        _last_flush = time.monotonic()
    except OSError as exc:
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

def load_state() -> Dict[str, Any]:
    """Return a copy of the current state.  Reads from in-memory cache."""
    with _LOCK:
        _ensure_loaded()
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


def record_trade(symbol: str, side: str, price: float, timestamp: str) -> None:
    """Append a trade and flush to disk immediately (trades are critical data)."""
    if side not in {"BUY", "SELL"}:
        raise ValueError("side must be 'BUY' or 'SELL'")
    with _LOCK:
        _ensure_loaded()
        _CACHE.setdefault("trades", [])
        _CACHE["trades"].append(
            {"symbol": symbol, "side": side, "price": price, "time": timestamp}
        )
        # Keep only the last 100 trades
        if len(_CACHE["trades"]) > 100:
            _CACHE["trades"] = _CACHE["trades"][-100:]
        _CACHE["last_update"] = datetime.now(timezone.utc).isoformat()
        _flush_to_disk()  # Always flush trades immediately
