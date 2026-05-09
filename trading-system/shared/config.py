"""Configuration utilities.

Loads environment variables from a ``.env`` file (if present) and provides a typed
``Config`` dataclass with the most common settings used across the project.
"""

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

# Load .env from the project root if it exists
PROJECT_ROOT = Path(__file__).resolve().parents[2]
_DOTENV_PATH = PROJECT_ROOT / ".env"
if _DOTENV_PATH.is_file():
    load_dotenv(_DOTENV_PATH)


@dataclass(frozen=True)
class Config:
    # Broker / API credentials
    FYERS_CLIENT_ID: str = os.getenv("FYERS_CLIENT_ID", "")
    FYERS_SECRET_KEY: str = os.getenv("FYERS_SECRET_KEY", "")
    FYERS_REDIRECT_URI: str = os.getenv("FYERS_REDIRECT_URI", "https://localhost")
    # General settings
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    # Risk parameters (defaults – can be overridden per‑strategy)
    RISK_PER_TRADE: float = float(os.getenv("RISK_PER_TRADE", "0.01"))  # 1 % of equity
    DAILY_LOSS_LIMIT: float = float(os.getenv("DAILY_LOSS_LIMIT", "0.05"))  # 5 % of equity
    MAX_DRAWDOWN: float = float(os.getenv("MAX_DRAWDOWN", "0.2"))  # 20 % max drawdown

    @property
    def is_fyers_configured(self) -> bool:
        return all([self.FYERS_CLIENT_ID, self.FYERS_SECRET_KEY])

# Export a singleton for easy import
CONFIG = Config()
