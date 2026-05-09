"""Strategy Registry for Multi-Strategy Engine.

Allows dynamic registration and execution of multiple trading strategies.
"""

import logging
from typing import Any, Callable, Dict, List

import pandas as pd

logger = logging.getLogger(__name__)


class StrategyRegistry:
    """Registry to manage and execute multiple strategies."""

    def __init__(self):
        self._strategies: Dict[str, Callable] = {}

    def register(self, name: str, strategy_func: Callable) -> None:
        """Register a new strategy function."""
        if name in self._strategies:
            logger.warning("Strategy %s is already registered. Overwriting.", name)
        self._strategies[name] = strategy_func
        logger.info("Registered strategy: %s", name)

    def run_strategy(self, name: str, df: pd.DataFrame, **kwargs) -> pd.Series:
        """Execute a specific registered strategy."""
        if name not in self._strategies:
            raise ValueError(f"Strategy {name} not found in registry.")
        
        logger.debug("Running strategy: %s", name)
        return self._strategies[name](df, **kwargs)

    def run_all(self, df: pd.DataFrame, **kwargs) -> Dict[str, pd.Series]:
        """Execute all registered strategies and return their signals."""
        results = {}
        for name, func in self._strategies.items():
            try:
                results[name] = func(df, **kwargs)
            except Exception as e:
                logger.error("Error running strategy %s: %s", name, e)
        return results

    @property
    def registered_strategies(self) -> List[str]:
        return list(self._strategies.keys())

# Global registry instance
registry = StrategyRegistry()
