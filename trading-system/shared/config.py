"""Configuration utilities.

Loads environment variables from a ``.env`` file (if present) and provides a typed
``Config`` dataclass with the most common settings used across the project.
"""

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

# Load .env from trading-system directory or project root if present
_LOCAL_ENV = Path(__file__).resolve().parents[1] / ".env"
_ROOT_ENV = Path(__file__).resolve().parents[2] / ".env"

if _LOCAL_ENV.is_file():
    load_dotenv(_LOCAL_ENV)
elif _ROOT_ENV.is_file():
    load_dotenv(_ROOT_ENV)


def _get_fyers_cred(field: str, default: str = "") -> str:
    """Read Fyers credential from environment or encrypted vault."""
    env_val = os.getenv(f"FYERS_{field.upper()}", "").strip()
    if env_val:
        return env_val
    try:
        from brokers.credentials import load_credentials
        creds = load_credentials("fyers")
        return creds.get(field, default)
    except Exception:
        return default


def _get_telegram_cred(field: str) -> str:
    """Read credential from environment or encrypted vault."""
    env_val = os.getenv(f"TELEGRAM_{field.upper()}", "").strip()
    if env_val:
        return env_val
    try:
        from brokers.credentials import load_credentials
        creds = load_credentials("telegram")
        return creds.get(field, "")
    except Exception:
        return ""


@dataclass(frozen=True)
class Config:
    # Broker / API credentials (Loaded from encrypted vault or .env)
    FYERS_CLIENT_ID: str = _get_fyers_cred("client_id")
    FYERS_SECRET_KEY: str = _get_fyers_cred("secret_key")
    FYERS_REDIRECT_URI: str = _get_fyers_cred("redirect_uri", "https://localhost")
    # General settings
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    # Risk parameters (defaults – can be overridden per‑strategy)
    RISK_PER_TRADE: float = float(os.getenv("RISK_PER_TRADE", "0.01"))  # 1 % of equity
    DAILY_LOSS_LIMIT: float = float(os.getenv("DAILY_LOSS_LIMIT", "0.05"))  # 5 % of equity
    MAX_DRAWDOWN: float = float(os.getenv("MAX_DRAWDOWN", "0.2"))  # 20 % max drawdown

    # Telegram Notifications (Loaded from encrypted vault or .env)
    TELEGRAM_BOT_TOKEN: str = _get_telegram_cred("bot_token")
    TELEGRAM_CHAT_ID: str = _get_telegram_cred("chat_id")
    ALERT_LANGUAGE: str = os.getenv("ALERT_LANGUAGE", "te")

    @property
    def is_fyers_configured(self) -> bool:
        return all([self.FYERS_CLIENT_ID, self.FYERS_SECRET_KEY])

# Export a singleton for easy import
CONFIG = Config()
