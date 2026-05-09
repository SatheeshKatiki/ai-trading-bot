"""Secure credential storage for broker API keys.

Storage format
--------------
``broker_credentials.json`` (in trading-system root) contains per-broker
credential dicts.  Values are encrypted with Fernet (AES-128-CBC + HMAC)
when the ``cryptography`` package is installed; otherwise stored as
base64-obfuscated strings with a visible warning.

Integrity protection
--------------------
Every write appends an HMAC-SHA256 of the JSON body.  ``_load_file()``
verifies the MAC before returning data — any tampering triggers a
CRITICAL log and refuses to return credentials.

Encryption key
--------------
Priority order:
  1. ``BROKER_ENCRYPTION_KEY`` environment variable (base64-url-safe Fernet key)
  2. Auto-generated key stored in ``.broker.key`` (project root, chmod 600)

Credentials file
----------------
  { "fyers": {"client_id": "<enc>", ...},
    "kite":  {"api_key":   "<enc>", ...},
    "_schema": "1" }
  # MAC:<hex>
"""

from __future__ import annotations

import base64
import hashlib
import hmac as _hmac
import json
import logging
import os
import stat
from pathlib import Path
from typing import Any, Dict

logger = logging.getLogger(__name__)

# Paths
_ROOT          = Path(__file__).resolve().parents[1]   # trading-system/
_CREDS_FILE    = _ROOT / "broker_credentials.json"
_KEY_FILE      = _ROOT / ".broker.key"
_ENV_KEY_VAR   = "BROKER_ENCRYPTION_KEY"

# Sentinel so we know whether the cryptography package is available
_FERNET_AVAILABLE = False
try:
    from cryptography.fernet import Fernet, InvalidToken
    _FERNET_AVAILABLE = True
except ImportError:
    logger.warning(
        "cryptography package not installed — credentials will be stored with "
        "base64 obfuscation only.  Run `pip install cryptography` for proper encryption."
    )


# ------------------------------------------------------------------
# Key management
# ------------------------------------------------------------------

def _get_or_create_fernet_key() -> bytes:
    """Return a valid Fernet key, creating one if needed."""
    env_key = os.getenv(_ENV_KEY_VAR, "")
    if env_key:
        return env_key.encode()
    if _KEY_FILE.is_file():
        return _KEY_FILE.read_bytes().strip()
    if _FERNET_AVAILABLE:
        from cryptography.fernet import Fernet as _F
        key = _F.generate_key()
    else:
        import secrets
        key = base64.urlsafe_b64encode(secrets.token_bytes(32))
    _KEY_FILE.write_bytes(key)
    try:
        _KEY_FILE.chmod(stat.S_IRUSR | stat.S_IWUSR)
    except Exception:
        pass
    logger.info("Generated new broker encryption key → %s", _KEY_FILE)
    return key


# ------------------------------------------------------------------
# Integrity MAC
# ------------------------------------------------------------------

def _file_mac(content: bytes) -> str:
    """Compute HMAC-SHA256 of raw JSON bytes using the Fernet key."""
    key = _get_or_create_fernet_key()
    return _hmac.new(key, content, hashlib.sha256).hexdigest()


# ------------------------------------------------------------------
# Encrypt / Decrypt
# ------------------------------------------------------------------

def _encrypt(plaintext: str) -> str:
    if not plaintext:
        return ""
    if _FERNET_AVAILABLE:
        from cryptography.fernet import Fernet as _F
        f = _F(_get_or_create_fernet_key())
        return f.encrypt(plaintext.encode()).decode()
    return "b64:" + base64.b64encode(plaintext.encode()).decode()


def _decrypt(ciphertext: str) -> str:
    if not ciphertext:
        return ""
    if ciphertext.startswith("b64:"):
        return base64.b64decode(ciphertext[4:]).decode()
    if _FERNET_AVAILABLE:
        from cryptography.fernet import Fernet as _F, InvalidToken
        try:
            f = _F(_get_or_create_fernet_key())
            return f.decrypt(ciphertext.encode()).decode()
        except InvalidToken:
            logger.error("Failed to decrypt credential — wrong key or corrupted data.")
            return ""
    return ciphertext


# ------------------------------------------------------------------
# File-level CRUD  (with integrity MAC)
# ------------------------------------------------------------------

def _save_file(data: Dict[str, Any]) -> None:
    """Persist ``data`` atomically with an HMAC-SHA256 integrity signature."""
    data["_schema"] = "1"
    content = json.dumps(data, indent=2).encode("utf-8")
    mac     = _file_mac(content)
    payload = content + b"\n# MAC:" + mac.encode()
    tmp = _CREDS_FILE.with_suffix(".tmp")
    tmp.write_bytes(payload)
    tmp.replace(_CREDS_FILE)
    try:
        _CREDS_FILE.chmod(stat.S_IRUSR | stat.S_IWUSR)
    except Exception:
        pass


def _load_file() -> Dict[str, Any]:
    """Load and verify the credentials file.  Returns {} on integrity failure."""
    if not _CREDS_FILE.is_file():
        return {"_schema": "1"}
    try:
        raw = _CREDS_FILE.read_bytes()
        if b"\n# MAC:" in raw:
            json_bytes, mac_part = raw.rsplit(b"\n# MAC:", 1)
            stored_mac   = mac_part.decode().strip()
            expected_mac = _file_mac(json_bytes)
            if not _hmac.compare_digest(stored_mac, expected_mac):
                logger.critical(
                    "SECURITY ALERT: broker_credentials.json integrity check FAILED. "
                    "The file may have been tampered with outside the application. "
                    "Refusing to load credentials."
                )
                return {"_schema": "1", "_integrity_error": True}
            return json.loads(json_bytes.decode("utf-8"))
        else:
            # Legacy file without MAC — load as-is; next save re-signs it
            logger.warning(
                "broker_credentials.json has no integrity MAC (legacy format). "
                "It will be re-signed on the next credential save."
            )
            return json.loads(raw.decode("utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        logger.error("Could not read %s: %s", _CREDS_FILE, exc)
        return {"_schema": "1"}


# ------------------------------------------------------------------
# Public API
# ------------------------------------------------------------------

def save_credentials(broker_id: str, credentials: Dict[str, str]) -> None:
    """Encrypt, sign, and persist ``credentials`` for ``broker_id``."""
    data = _load_file()
    data[broker_id] = {k: _encrypt(v) for k, v in credentials.items() if v}
    _save_file(data)
    logger.info("Credentials saved for broker: %s", broker_id)
    try:
        from shared.security.audit_log import audit, AuditEvent
        audit.log(AuditEvent.CRED_SAVED, {"broker": broker_id})
    except Exception:
        pass


def load_credentials(broker_id: str) -> Dict[str, str]:
    """Return decrypted credentials for ``broker_id``, or empty dict on failure."""
    data = _load_file()
    if data.get("_integrity_error"):
        logger.critical("Refusing to return credentials — integrity check failed.")
        return {}
    raw = data.get(broker_id, {})
    return {k: _decrypt(v) for k, v in raw.items()}


def delete_credentials(broker_id: str) -> None:
    """Remove saved credentials for ``broker_id``."""
    data = _load_file()
    data.pop(broker_id, None)
    _save_file(data)
    logger.info("Credentials deleted for broker: %s", broker_id)
    try:
        from shared.security.audit_log import audit, AuditEvent
        audit.log(AuditEvent.CRED_DELETED, {"broker": broker_id})
    except Exception:
        pass


def credentials_exist(broker_id: str) -> bool:
    """Return True if non-empty credentials are saved for ``broker_id``."""
    return bool(load_credentials(broker_id))


def list_saved_brokers() -> list:
    """Return broker IDs that have saved credentials."""
    data = _load_file()
    return [k for k in data if not k.startswith("_")]
