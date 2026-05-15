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

    def get_parameters(self, name: str) -> Dict[str, Any]:
        """Get the parameters of a registered strategy."""
        import inspect
        if name not in self._strategies:
            raise ValueError(f"Strategy {name} not found in registry.")
        
        func = self._strategies[name]
        sig = inspect.signature(func)
        
        params = {}
        for param_name, param in sig.parameters.items():
            if param_name in ['df', 'kwargs']:
                continue
            params[param_name] = {
                "default": param.default if param.default is not inspect.Parameter.empty else None,
                "type": str(param.annotation) if param.annotation is not inspect.Parameter.empty else "Any"
            }
        return params

    def autodiscover(self) -> None:
        """Scan the strategies directory and register valid strategies."""
        import os
        import importlib
        from pathlib import Path
        
        current_dir = Path(__file__).parent
        logger.info(f"Auto-discovering strategies in: {current_dir}")
        
        for file in os.listdir(current_dir):
            if file.endswith(".py") and file not in ["__init__.py", "registry.py"]:
                module_name = file[:-3]
                try:
                    # Import the module dynamically
                    module = importlib.import_module(f"trading_bot.strategies.{module_name}")
                    
                    # Look for generate_signals function
                    if hasattr(module, "generate_signals"):
                        # Use STRATEGY_NAME variable if defined, else fallback to module_name
                        strat_name = getattr(module, "STRATEGY_NAME", module_name)
                        self.register(strat_name, module.generate_signals)
                except Exception as e:
                    logger.error(f"Failed to auto-discover strategy in {file}: {e}")

# Global registry instance
registry = StrategyRegistry()
registry.autodiscover()
