import logging
from drl.marl.base_agent import BaseAgent

logger = logging.getLogger(__name__)

class ExecutionAgent(BaseAgent):
    """
    The Execution Agent (The Options Desk).
    Takes a direction signal and determines the exact execution parameters:
    Strike Price (ATM/ITM), Option Type (CE/PE), and Lot Size based on IV/Greeks.
    """
    
    def __init__(self):
        super().__init__("ExecutionAgent_OptionsDesk")
        # In a real environment, this agent would subscribe to a live Greeks/IV feed.
        
    def analyze(self, signal_action: int, current_spot: float, is_high_iv: bool = False) -> dict:
        """
        Analyzes how to execute the given signal.
        signal_action: 1 (Long), 2 (Short), 3 (Close)
        """
        if not self.is_active or signal_action in (0, 3):
            return {"execute": False}
            
        execution_plan = {
            "execute": True,
            "option_type": None,
            "strike_offset": 0, # 0 = ATM, negative = ITM, positive = OTM
            "reason": ""
        }
        
        # Long Signal -> Always Buy CE for daily scalping
        if signal_action == 1:
            execution_plan["option_type"] = "CE_BUY"
            execution_plan["strike_offset"] = 0 # ATM
            execution_plan["reason"] = "Options Scalping: Buying ATM Call"
                
        # Short Signal -> Always Buy PE for daily scalping
        elif signal_action == 2:
            execution_plan["option_type"] = "PE_BUY"
            execution_plan["strike_offset"] = 0 # ATM
            execution_plan["reason"] = "Options Scalping: Buying ATM Put"
                
        return execution_plan
