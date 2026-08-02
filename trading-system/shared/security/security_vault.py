import os
import json
import base64
import logging
import secrets
import stat
from pathlib import Path
from typing import Dict, Any, Optional
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

logger = logging.getLogger(__name__)

# High audit finding: this class used to hardcode both the master passphrase
# ("QUANT_AI_SUPER_SECRET_KEY") and the PBKDF2 salt directly in source. Since
# both were visible to anyone with repo access, the derived Fernet key was
# never actually secret, regardless of iteration count — the "AES-256
# encryption" this class advertises provided no real protection. It has zero
# call sites anywhere in the codebase today, but the insecure default would
# have been a landmine the moment something started using it. Now sourced
# the same way brokers/credentials.py already handles its own Fernet key: an
# env var override, or an auto-generated value persisted to a gitignored
# file on first use — never a hardcoded constant.
_VAULT_DIR = Path(__file__).resolve().parents[2]  # trading-system/
_PASSPHRASE_FILE = _VAULT_DIR / ".vault_passphrase"
_SALT_FILE = _VAULT_DIR / ".vault_salt"
_ENV_PASSPHRASE_VAR = "VAULT_MASTER_PASSPHRASE"


def _write_secret_file(path: Path, data: bytes) -> None:
    path.write_bytes(data)
    try:
        path.chmod(stat.S_IRUSR | stat.S_IWUSR)
    except Exception:
        pass


def _get_or_create_passphrase() -> str:
    env_val = os.getenv(_ENV_PASSPHRASE_VAR, "")
    if env_val:
        return env_val
    if _PASSPHRASE_FILE.is_file():
        return _PASSPHRASE_FILE.read_text(encoding="utf-8").strip()
    passphrase = secrets.token_urlsafe(32)
    _write_secret_file(_PASSPHRASE_FILE, passphrase.encode("utf-8"))
    logger.info("SecurityVault: generated a new master passphrase -> %s", _PASSPHRASE_FILE)
    return passphrase


def _get_or_create_salt() -> bytes:
    if _SALT_FILE.is_file():
        return _SALT_FILE.read_bytes()
    salt = secrets.token_bytes(16)
    _write_secret_file(_SALT_FILE, salt)
    return salt


class SecurityVault:
    """
    Enterprise-Grade Security Vault (AES-256 Encryption)

    Protects broker API credentials, access tokens, and sensitive system parameters.
    Provides emergency kill-switch capability on network disconnects.
    """

    def __init__(self, master_passphrase: Optional[str] = None):
        passphrase = master_passphrase or _get_or_create_passphrase()
        salt = _get_or_create_salt()
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=100_000,
        )
        key = base64.urlsafe_b64encode(kdf.derive(passphrase.encode()))
        self.cipher = Fernet(key)

    def encrypt(self, plain_text: str) -> str:
        """Encrypt plain text string into AES-256 token."""
        if not plain_text:
            return ""
        encrypted_bytes = self.cipher.encrypt(plain_text.encode('utf-8'))
        return encrypted_bytes.decode('utf-8')

    def decrypt(self, token_str: str) -> str:
        """Decrypt AES-256 token string into original plain text."""
        if not token_str:
            return ""
        try:
            decrypted_bytes = self.cipher.decrypt(token_str.encode('utf-8'))
            return decrypted_bytes.decode('utf-8')
        except Exception as e:
            logger.error(f"SecurityVault: Decryption failed! Error: {e}")
            return ""

    def sanitize_dict(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Redacts sensitive key fields from dictionaries for safe logging."""
        sanitized = data.copy()
        sensitive_keys = ["api_key", "secret", "token", "password", "app_secret", "client_id"]
        for k in sanitized:
            if any(s in k.lower() for s in sensitive_keys):
                val = str(sanitized[k])
                if len(val) > 6:
                    sanitized[k] = val[:3] + "..." + val[-3:]
                else:
                    sanitized[k] = "***"
        return sanitized


class KillSwitch:
    """
    Emergency Network / Hardware Disconnect Circuit Breaker.
    """
    
    def __init__(self, max_disconnect_seconds: int = 15):
        self.max_disconnect_seconds = max_disconnect_seconds
        self.is_triggered = False
        self.trigger_reason = ""

    def evaluate_connection(self, last_heartbeat_timestamp: float, current_timestamp: float) -> bool:
        """Checks if connection heartbeat delay exceeds maximum threshold."""
        delay = current_timestamp - last_heartbeat_timestamp
        if delay > self.max_disconnect_seconds:
            self.is_triggered = True
            self.trigger_reason = f"Emergency Kill-Switch Triggered: Heartbeat lost for {delay:.1f}s (> {self.max_disconnect_seconds}s limit)"
            logger.critical(self.trigger_reason)
            return True
        return False
