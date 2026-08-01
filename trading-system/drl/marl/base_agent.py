from abc import ABC, abstractmethod
import logging

logger = logging.getLogger(__name__)

class BaseAgent(ABC):
    """
    The Base Class for all AI Sub-Agents in the MARL system.
    Every specialized agent must inherit from this and implement the `analyze` method.
    """
    
    def __init__(self, name: str):
        self.name = name
        self.is_active = True
        logger.info(f"Initialized Agent: {self.name}")

    @abstractmethod
    def analyze(self, **kwargs) -> dict:
        """
        Takes inputs (state, order book, greeks, etc.) and returns an analysis dict.
        Must be implemented by child classes.
        """
        pass
