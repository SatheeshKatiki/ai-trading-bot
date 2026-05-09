"""Tamper-evident append-only audit logger.

Design
------
* Every record is a JSON line (NDJSON format) written to a daily log file:
    audit/audit_YYYY-MM-DD.log
* Each line carries an HMAC-SHA256 of (timestamp + event_type + json_data +
  previous_line_hmac).  This creates a cryptographic chain — any deletion or
  tampering of a record breaks the chain and is detectable.
* The HMAC key is derived from the same encryption key used for broker
  credentials (or a fallback per-machine key).
* All write operations are protected by a threading.Lock — safe to call from
  the async trading loop.

Usage::

    from shared.security import audit

    audit.log("TRADE_ENTRY", {"symbol": "NSE:NIFTY", "qty": 1, "price": 22000.0})
    audit.log("AUTH_SUCCESS", {"broker": "fyers"})
    audit.log("RISK_BREACH",  {"reason": "daily_loss_limit", "pnl": -5000.0})
    audit.verify_integrity()   # returns True/False + list of broken links
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Audit log directory (trading-system/audit/)
# Path: shared/security/audit_log.py → parents[0]=security, [1]=shared, [2]=trading-system
_AUDIT_DIR  = Path(__file__).resolve().parents[2] / "audit"
_HMAC_KEY   = b""   # populated lazily


def _get_hmac_key() -> bytes:
    """Derive an HMAC key from the broker encryption key (or a machine fallback)."""
    global _HMAC_KEY
    if _HMAC_KEY:
        return _HMAC_KEY
    try:
        # Reuse the broker encryption key so there is only one secret to protect
        from brokers.credentials import _get_or_create_fernet_key
        raw = _get_or_create_fernet_key()
        # Derive a separate sub-key for HMAC via PBKDF2 so the same key
        # cannot be used to both encrypt credentials AND forge audit records.
        _HMAC_KEY = hashlib.pbkdf2_hmac("sha256", raw, b"audit-log-salt", iterations=100_000)
    except Exception:
        # Fallback: hash of machine hostname
        import socket
        _HMAC_KEY = hashlib.sha256(socket.gethostname().encode()).digest()
    return _HMAC_KEY


def _compute_hmac(data: str) -> str:
    return hmac.new(_get_hmac_key(), data.encode(), hashlib.sha256).hexdigest()


# ---------------------------------------------------------------------------
# Event types (for documentation / type safety in callers)
# ---------------------------------------------------------------------------
class AuditEvent:
    TRADE_ENTRY      = "TRADE_ENTRY"
    TRADE_EXIT       = "TRADE_EXIT"
    ORDER_PLACED     = "ORDER_PLACED"
    ORDER_CANCELLED  = "ORDER_CANCELLED"
    ORDER_REJECTED   = "ORDER_REJECTED"
    AUTH_SUCCESS     = "AUTH_SUCCESS"
    AUTH_FAILURE     = "AUTH_FAILURE"
    BROKER_SWITCH    = "BROKER_SWITCH"
    RISK_BREACH      = "RISK_BREACH"
    DAILY_LOSS_HIT   = "DAILY_LOSS_HIT"
    CRED_SAVED       = "CRED_SAVED"
    CRED_DELETED     = "CRED_DELETED"
    DASHBOARD_LOGIN  = "DASHBOARD_LOGIN"
    DASHBOARD_LOGOUT = "DASHBOARD_LOGOUT"
    DASHBOARD_FAIL   = "DASHBOARD_FAIL"
    BOT_START        = "BOT_START"
    BOT_STOP         = "BOT_STOP"
    VALIDATION_ERROR = "VALIDATION_ERROR"


# ---------------------------------------------------------------------------
# AuditLogger
# ---------------------------------------------------------------------------
class AuditLogger:
    """Thread-safe, append-only, HMAC-chained audit logger."""

    def __init__(self) -> None:
        self._lock       = threading.Lock()
        self._prev_hmac  = "GENESIS"   # chain starts here
        self._today_path: Optional[Path] = None
        _AUDIT_DIR.mkdir(parents=True, exist_ok=True)
        self._init_chain()

    # ------------------------------------------------------------------
    # Initialise chain from the last line of today's file
    # ------------------------------------------------------------------
    def _today_file(self) -> Path:
        date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        return _AUDIT_DIR / f"audit_{date}.log"

    def _init_chain(self) -> None:
        path = self._today_file()
        if path.is_file():
            last_line = ""
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        last_line = line
            if last_line:
                try:
                    rec = json.loads(last_line)
                    self._prev_hmac = rec.get("hmac", "GENESIS")
                except Exception:
                    pass

    # ------------------------------------------------------------------
    # Core log method
    # ------------------------------------------------------------------
    def log(
        self,
        event_type: str,
        data: Optional[Dict[str, Any]] = None,
        severity: str = "INFO",
    ) -> None:
        """Append an auditable record to today's log file."""
        data = data or {}
        # Sanitise: remove any values that look like secrets
        data = _sanitise_dict(data)

        ts = datetime.now(timezone.utc).isoformat()
        chain_input = f"{ts}|{event_type}|{json.dumps(data, sort_keys=True)}|{self._prev_hmac}"
        entry_hmac  = _compute_hmac(chain_input)

        record: Dict[str, Any] = {
            "ts":         ts,
            "event":      event_type,
            "severity":   severity,
            "data":       data,
            "hmac":       entry_hmac,
        }
        line = json.dumps(record, separators=(",", ":"))

        with self._lock:
            path = self._today_file()
            if path != self._today_path:
                # Day rolled over — re-init chain
                self._today_path = path
                self._init_chain()
            with open(path, "a", encoding="utf-8") as f:
                f.write(line + "\n")
            self._prev_hmac = entry_hmac

        # Also emit to the standard logger (at a lower visibility level)
        logger.debug("AUDIT [%s] %s %s", severity, event_type, data)

    # ------------------------------------------------------------------
    # Convenience helpers
    # ------------------------------------------------------------------
    def trade(self, event_type: str, symbol: str, side: str, qty: int, price: float,
              broker: str = "", pnl: float = 0.0, **extra) -> None:
        self.log(event_type, {"symbol": symbol, "side": side, "qty": qty,
                               "price": price, "broker": broker, "pnl": pnl, **extra})

    def auth(self, event_type: str, broker: str, success: bool, reason: str = "") -> None:
        self.log(event_type, {"broker": broker, "success": success, "reason": reason},
                 severity="WARNING" if not success else "INFO")

    def risk(self, reason: str, details: Optional[Dict] = None) -> None:
        self.log(AuditEvent.RISK_BREACH, {"reason": reason, **(details or {})},
                 severity="WARNING")

    # ------------------------------------------------------------------
    # Chain integrity verification
    # ------------------------------------------------------------------
    def verify_integrity(
        self, date: Optional[str] = None
    ) -> Tuple[bool, List[str]]:
        """Verify the HMAC chain for a given date (default: today).

        Returns (is_intact, list_of_error_messages).
        """
        if date is None:
            path = self._today_file()
        else:
            path = _AUDIT_DIR / f"audit_{date}.log"

        if not path.is_file():
            return True, []   # empty = no tampering

        errors: List[str] = []
        prev = "GENESIS"

        with open(path, "r", encoding="utf-8") as f:
            for i, raw_line in enumerate(f, start=1):
                raw_line = raw_line.strip()
                if not raw_line:
                    continue
                try:
                    rec  = json.loads(raw_line)
                    ts   = rec["ts"]
                    ev   = rec["event"]
                    data = rec["data"]
                    hmac_stored = rec["hmac"]

                    chain_input = f"{ts}|{ev}|{json.dumps(data, sort_keys=True)}|{prev}"
                    expected    = _compute_hmac(chain_input)

                    if not hmac.compare_digest(expected, hmac_stored):
                        errors.append(f"Line {i}: HMAC mismatch — record may have been tampered with.")

                    prev = hmac_stored
                except Exception as exc:
                    errors.append(f"Line {i}: parse error — {exc}")

        return len(errors) == 0, errors


# ---------------------------------------------------------------------------
# Sanitise sensitive keys from data dicts before they enter the log
# ---------------------------------------------------------------------------
_SECRET_KEYS = {
    "secret_key", "api_secret", "mpin", "totp_secret", "access_token",
    "password", "token", "secret", "key", "auth_code", "request_token",
}


def _sanitise_dict(d: Dict[str, Any]) -> Dict[str, Any]:
    out = {}
    for k, v in d.items():
        if k.lower() in _SECRET_KEYS:
            out[k] = "***REDACTED***"
        elif isinstance(v, dict):
            out[k] = _sanitise_dict(v)
        else:
            out[k] = v
    return out


# ---------------------------------------------------------------------------
# Global singleton
# ---------------------------------------------------------------------------
audit = AuditLogger()
