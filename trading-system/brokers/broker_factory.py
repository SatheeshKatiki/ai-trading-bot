"""Broker Factory — registry, creation, and single-active-broker management.

Design
------
* Only ONE broker is active at any point (enforced by the singleton ``_active``).
* Brokers are registered at import time via ``BrokerFactory.register()``.
* ``BrokerFactory.get_active_broker()`` returns the live singleton, creating it
  if needed.
* ``BrokerFactory.switch_broker(broker_id)`` tears down the current broker,
  loads saved credentials, instantiates and authenticates the new one.
* The active broker ID is persisted in ``settings.json`` so it survives restarts.

Usage example
-------------
    from brokers import BrokerFactory

    broker = BrokerFactory.get_active_broker()
    resp   = await broker.place_order_async(request)
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Dict, Optional, Type

from .base_broker import BaseBroker
from .credentials import load_credentials
from .exceptions import BrokerNotConfiguredError, BrokerNotFoundError
from .models import BrokerInfo

logger = logging.getLogger(__name__)

# Settings file (shared with dashboard and trading engine)
_SETTINGS_FILE = Path(__file__).resolve().parents[1] / "settings.json"


class BrokerFactory:
    """Class-only factory — never instantiated.

    Registry is a class-level dict so all modules share the same view.
    """

    # broker_id → broker class
    _registry: Dict[str, Type[BaseBroker]] = {}

    # The single active broker instance (None until first get_active_broker call)
    _active: Optional[BaseBroker] = None

    # ------------------------------------------------------------------
    # Registry
    # ------------------------------------------------------------------

    @classmethod
    def register(cls, broker_class: Type[BaseBroker]) -> None:
        """Register a broker class.  Called once per class at module import."""
        bid = broker_class.BROKER_ID
        if not bid:
            raise ValueError(f"{broker_class.__name__}.BROKER_ID must not be empty.")
        cls._registry[bid] = broker_class
        logger.debug("BrokerFactory: registered '%s' → %s", bid, broker_class.__name__)

    @classmethod
    def available_brokers(cls) -> Dict[str, BrokerInfo]:
        """Return metadata for all registered brokers."""
        return {bid: cls._registry[bid].info() for bid in cls._registry}

    # ------------------------------------------------------------------
    # Active broker lifecycle
    # ------------------------------------------------------------------

    @classmethod
    def get_active_broker(cls) -> BaseBroker:
        """Return the active broker singleton, creating it on first call.

        Reads the active broker ID from ``settings.json``.
        If no broker is configured, falls back to FyersBroker in paper mode.
        """
        if cls._active is not None:
            return cls._active

        broker_id = cls._read_active_broker_id()
        cls._active = cls._create(broker_id)
        return cls._active

    @classmethod
    def switch_broker(cls, broker_id: str) -> BaseBroker:
        """Tear down the current broker and activate ``broker_id``.

        Raises ``BrokerNotFoundError`` if ``broker_id`` is not registered.
        Raises ``BrokerNotConfiguredError`` if credentials are missing.
        """
        if broker_id not in cls._registry:
            raise BrokerNotFoundError(
                f"Broker '{broker_id}' is not registered.  "
                f"Available: {list(cls._registry)}",
                broker_id=broker_id,
            )

        # Tear down old broker
        if cls._active is not None:
            try:
                cls._active.close()
            except Exception as exc:
                logger.warning("Error closing old broker: %s", exc)
            cls._active = None

        # Persist new choice
        cls._write_active_broker_id(broker_id)

        # Instantiate and authenticate
        cls._active = cls._create(broker_id)
        return cls._active

    @classmethod
    def close_active(cls) -> None:
        """Shut down the active broker and clear the singleton."""
        if cls._active is not None:
            try:
                cls._active.close()
            except Exception as exc:
                logger.warning("Error during broker close: %s", exc)
            cls._active = None
            logger.info("BrokerFactory: active broker closed.")

    @classmethod
    def get_active_broker_id(cls) -> str:
        """Return the currently configured broker ID (from settings)."""
        return cls._read_active_broker_id()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @classmethod
    def _create(cls, broker_id: str) -> BaseBroker:
        """Instantiate and authenticate a broker, returning the instance."""
        if broker_id not in cls._registry:
            logger.warning(
                "BrokerFactory: broker '%s' not found — falling back to Fyers paper mode.",
                broker_id,
            )
            broker_id = "fyers"

        broker_class = cls._registry[broker_id]
        credentials  = load_credentials(broker_id)
        
        # Read settings to check live_trading_mode
        live_trading_mode = False
        if _SETTINGS_FILE.is_file():
            try:
                data = json.loads(_SETTINGS_FILE.read_text(encoding="utf-8"))
                live_trading_mode = data.get("live_trading_mode", False)
            except Exception:
                pass
                
        # Paper mode is active if live trading is disabled OR credentials are missing
        paper_mode = not live_trading_mode or not bool(credentials)

        if paper_mode:
            logger.warning(
                "BrokerFactory: Paper mode active (live_trading_mode=False or missing credentials)."
            )

        instance = broker_class(credentials=credentials, paper_mode=paper_mode)

        try:
            instance.authenticate()
        except Exception as exc:
            logger.error(
                "BrokerFactory: authentication failed for '%s': %s — falling back to paper mode.",
                broker_id, exc,
            )
            instance.paper_mode = True
            instance._authenticated = True   # synthetic paper mode — always "authenticated"

        logger.info(
            "BrokerFactory: active broker set → %s (paper=%s)",
            broker_id, instance.paper_mode,
        )
        return instance

    @classmethod
    def _read_active_broker_id(cls) -> str:
        """Read active_broker from settings.json, defaulting to 'fyers'."""
        if _SETTINGS_FILE.is_file():
            try:
                data = json.loads(_SETTINGS_FILE.read_text(encoding="utf-8"))
                return data.get("active_broker", "fyers")
            except Exception:
                pass
        return "fyers"

    @classmethod
    def _write_active_broker_id(cls, broker_id: str) -> None:
        """Persist the selected broker ID into settings.json."""
        data: dict = {}
        if _SETTINGS_FILE.is_file():
            try:
                data = json.loads(_SETTINGS_FILE.read_text(encoding="utf-8"))
            except Exception:
                pass
        data["active_broker"] = broker_id
        tmp = _SETTINGS_FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=4), encoding="utf-8")
        tmp.replace(_SETTINGS_FILE)
        logger.info("BrokerFactory: active_broker persisted → '%s'", broker_id)


# ------------------------------------------------------------------
# Auto-register all built-in adapters
# ------------------------------------------------------------------
# Import here (after the class is defined) to avoid circular imports.

def _register_built_ins() -> None:
    from .fyers_broker import FyersBroker
    from .kite_broker  import KiteBroker
    from .angel_broker import AngelBroker

    BrokerFactory.register(FyersBroker)
    BrokerFactory.register(KiteBroker)
    BrokerFactory.register(AngelBroker)


_register_built_ins()
