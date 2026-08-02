import logging
import pandas as pd
from typing import Dict, Any

from drl.marl.signal_agent import SignalAgent
from drl.marl.execution_agent import ExecutionAgent
from drl.marl.risk_agent import RiskAgent
from drl.marl.alpha_agent import AlphaAgent

logger = logging.getLogger(__name__)

class MasterAgent:
    """
    The Orchestrator (The Boss).
    It manages the Signal, Execution, and Risk agents.
    It receives their inputs, resolves conflicts, and produces the final trading decision.
    """
    
    def __init__(self, model_path: str):
        self.name = "MasterAgent_Orchestrator"
        logger.info("Initializing Master Agent and its Sub-Agents...")
        
        # Initialize Sub-Agents
        self.signal_agent = SignalAgent(model_path)
        self.execution_agent = ExecutionAgent()
        self.risk_agent = RiskAgent(max_drawdown_pct=2.0, take_profit_pct=5.0)
        self.alpha_agent = AlphaAgent()
        
    def analyze_market(self, df: pd.DataFrame, obs: Any, current_spot: float, current_pnl_pct: float, is_high_iv: bool = False, symbol: str = "NSE:NIFTY50-INDEX", broker: Any = None) -> dict:
        """
        The main async-like execution loop for the MARL system.
        In a true asynchronous system, these calls would be dispatched via ThreadPool or asyncio.gather.
        For now, they run sequentially but represent logically independent agents.
        """
        
        final_decision = {
            "action": "HOLD",
            "option_type": None,
            "strike_offset": 0,
            "reason": ""
        }
        
        # 1. Ask Risk Agent first (Highest Priority)
        risk_plan = self.risk_agent.analyze(current_pnl_pct)
        if risk_plan.get("override"):
            final_decision["action"] = risk_plan["action"]
            final_decision["reason"] = risk_plan["reason"]
            return final_decision
            
        # 1.5 Ask Alpha Agent for Market Context (Expiry / Volatility / Regime overrides)
        alpha_context = self.alpha_agent.analyze(df, symbol=symbol, broker=broker)
        if not alpha_context.get("allowed_to_trade"):
            final_decision["action"] = "HOLD"
            final_decision["reason"] = alpha_context.get("reason")
            return final_decision
            
        # 2. Ask Signal Agent (The Sniper) for direction
        signal_plan = self.signal_agent.analyze(obs)
        raw_action = signal_plan.get("action", 0)
        
        if raw_action in (0, 3): # Hold or Close
            final_decision["action"] = signal_plan.get("action_name", "HOLD")
            final_decision["reason"] = f"Signal Agent suggests {final_decision['action']}"
            return final_decision
            
        # 3. Ask Execution Agent (Options Desk) how to execute the signal
        # If alpha context is SCALP, we can pass this hint to the execution agent
        exec_plan = self.execution_agent.analyze(
            raw_action, 
            current_spot, 
            is_high_iv or (alpha_context.get("mode") == "SCALP")
        )
        
        if exec_plan.get("execute"):
            final_decision["action"] = signal_plan.get("action_name")
            final_decision["option_type"] = exec_plan.get("option_type")
            final_decision["strike_offset"] = exec_plan.get("strike_offset")
            final_decision["reason"] = exec_plan.get("reason")
            
        return final_decision
