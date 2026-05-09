"""Monte Carlo Simulation for Backtest Validation.

Simulates hundreds of randomized trade sequences to evaluate the robustness
of the strategy and calculate the probability of ruin/drawdown.
"""

import logging
import random
from typing import Dict, List

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

class MonteCarloSimulator:
    """Runs Monte Carlo simulations on historical trade PnL data."""

    def __init__(self, trades_pnl: List[float], initial_capital: float = 10_000.0):
        self.trades = trades_pnl
        self.initial_capital = initial_capital

    def simulate(self, num_simulations: int = 1000, num_trades_per_sim: int = 100) -> Dict[str, float]:
        """Run the Monte Carlo simulation by bootstrapping historical trades.
        
        Parameters
        ----------
        num_simulations : int
            Number of parallel universes to simulate.
        num_trades_per_sim : int
            Number of trades to randomly sample (with replacement) per simulation.
            
        Returns
        -------
        Dict
            Statistics including median final equity, max drawdown percentiles, and risk of ruin.
        """
        if not self.trades:
            return {"error": 0.0}

        final_equities = []
        max_drawdowns = []
        ruin_count = 0  # Number of times capital dropped below 50%

        for _ in range(num_simulations):
            # Bootstrap trades with replacement
            sampled_trades = random.choices(self.trades, k=num_trades_per_sim)
            
            capital = self.initial_capital
            peak_capital = self.initial_capital
            max_dd = 0.0
            ruined = False
            
            for pnl in sampled_trades:
                capital += pnl
                if capital > peak_capital:
                    peak_capital = capital
                
                # Calculate drawdown
                if peak_capital > 0:
                    dd = (peak_capital - capital) / peak_capital
                    if dd > max_dd:
                        max_dd = dd
                        
                # Risk of ruin threshold (e.g., losing 50% of capital)
                if capital <= (self.initial_capital * 0.5):
                    ruined = True
                    break
                    
            if ruined:
                ruin_count += 1
                
            final_equities.append(capital)
            max_drawdowns.append(max_dd)

        # Calculate Percentiles
        final_equities_arr = np.array(final_equities)
        max_drawdowns_arr = np.array(max_drawdowns)

        stats = {
            "median_final_capital": round(float(np.median(final_equities_arr)), 2),
            "worst_case_capital_5th_pct": round(float(np.percentile(final_equities_arr, 5)), 2),
            "best_case_capital_95th_pct": round(float(np.percentile(final_equities_arr, 95)), 2),
            "median_max_drawdown_%": round(float(np.median(max_drawdowns_arr) * 100), 2),
            "worst_case_drawdown_95th_pct_%": round(float(np.percentile(max_drawdowns_arr, 95) * 100), 2),
            "risk_of_ruin_%": round((ruin_count / num_simulations) * 100, 2),
        }
        
        return stats
