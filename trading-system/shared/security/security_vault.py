import os
import json
import base64
import logging
from typing import Dict, Any, Optional
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

logger = logging.getLogger(__name__)

class SecurityVault:
    """
    Enterprise-Grade Security Vault (AES-256 Encryption)
    
    Protects broker API credentials, access tokens, and sensitive system parameters.
    Provides emergency kill-switch capability on network disconnects.
    """
    
    _DEFAULT_SALT = b"ai_trading_bot_secure_salt_2026"

    def __init__(self, master_passphrase: str = "QUANT_AI_SUPER_SECRET_KEY"):
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=self._DEFAULT_SALT,
            iterations=100_000,
        )
        key = base64.urlsafe_b64encode(kdf.derive(master_passphrase.encode()))
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
