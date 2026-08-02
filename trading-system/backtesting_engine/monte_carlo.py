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

    def simulate(self, num_simulations: int = 1000, num_trades_per_sim: int = 100, block_size: int = 5) -> Dict[str, float]:
        """Run the Monte Carlo simulation by block-bootstrapping historical trades.

        Parameters
        ----------
        num_simulations : int
            Number of parallel universes to simulate.
        num_trades_per_sim : int
            Number of trades to randomly sample per simulation.
        block_size : int
            Length of each contiguous run of trades resampled together.

        Returns
        -------
        Dict
            Statistics including median final equity, max drawdown percentiles, and risk of ruin.

        Root-cause fix (Medium audit finding): this previously used
        random.choices(self.trades, k=...) — an i.i.d. bootstrap that
        draws each trade independently, completely discarding the
        original sequence's order. Real trade sequences exhibit
        autocorrelation/regime clustering (losing streaks tend to cluster
        during a bad regime, not scatter uniformly at random), and i.i.d.
        resampling artificially breaks that clustering apart — a real
        historical 5-loss streak gets diluted across many simulated
        paths that interleave it with unrelated winning trades from
        elsewhere in the series, making simulated risk-of-ruin/drawdown
        look better (less risky) than the strategy's real historical
        behavior. Switched to a moving block bootstrap (the standard
        remedy for exactly this critique): each simulated path is
        assembled from contiguous blocks of `block_size` trades pulled
        from random starting points in the original sequence (wrapping
        around), preserving local autocorrelation within each block
        while still randomizing which historical period contributes and
        how blocks are stitched together across the simulated path.
        """
        if not self.trades:
            return {"error": 0.0}

        final_equities = []
        max_drawdowns = []
        ruin_count = 0  # Number of times capital dropped below 50%
        n = len(self.trades)
        effective_block_size = max(1, min(block_size, n))

        for _ in range(num_simulations):
            # Block bootstrap: assemble the path from contiguous runs of
            # trades (preserving their original order/clustering within
            # each block) rather than drawing every trade independently.
            sampled_trades: List[float] = []
            while len(sampled_trades) < num_trades_per_sim:
                start = random.randint(0, n - 1)
                for offset in range(effective_block_size):
                    sampled_trades.append(self.trades[(start + offset) % n])
                    if len(sampled_trades) >= num_trades_per_sim:
                        break
            
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
