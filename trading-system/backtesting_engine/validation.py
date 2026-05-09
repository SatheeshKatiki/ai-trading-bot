"""Walk-Forward Testing validation suite.

Splits historical data into sliding windows of In-Sample (IS) and Out-Of-Sample (OOS)
data to validate that the strategy does not suffer from curve-fitting/overfitting.
"""

import logging
from typing import Dict, List, Tuple

import pandas as pd

from backtesting_engine.run import Backtester

logger = logging.getLogger(__name__)


class WalkForwardValidator:
    """Performs Walk-Forward testing on historical data."""

    def __init__(self, df: pd.DataFrame, initial_capital: float = 10_000.0):
        self.df = df.copy()
        self.initial_capital = initial_capital

    def _generate_windows(self, num_windows: int, train_ratio: float = 0.7) -> List[Tuple[pd.DataFrame, pd.DataFrame]]:
        """Generate sliding windows for In-Sample and Out-Of-Sample data."""
        total_len = len(self.df)
        window_size = int(total_len / (num_windows + (1 - train_ratio)))
        train_size = int(window_size * train_ratio)
        test_size = window_size - train_size

        windows = []
        for i in range(num_windows):
            start_idx = int(i * test_size)
            train_end = start_idx + train_size
            test_end = train_end + test_size

            if test_end > total_len:
                break

            train_df = self.df.iloc[start_idx:train_end]
            test_df = self.df.iloc[train_end:test_end]
            windows.append((train_df, test_df))

        return windows

    def run_walk_forward(self, num_windows: int = 5, train_ratio: float = 0.7) -> Dict[str, Any]:
        """Run the walk-forward testing process.
        
        Returns
        -------
        Dict
            Performance metrics comparing IS (In-Sample) vs OOS (Out-Of-Sample).
            A highly degraded OOS performance indicates curve-fitting.
        """
        windows = self._generate_windows(num_windows, train_ratio)
        if not windows:
            return {"error": "Not enough data to create windows."}

        is_metrics = []
        oos_metrics = []

        for idx, (train_df, test_df) in enumerate(windows):
            logger.info("Running WF Window %d...", idx + 1)
            
            # In-Sample Backtest
            bt_is = Backtester(train_df, initial_capital=self.initial_capital)
            bt_is.run()
            is_res = bt_is.summary()
            is_metrics.append(is_res)

            # Out-Of-Sample Backtest
            bt_oos = Backtester(test_df, initial_capital=self.initial_capital)
            bt_oos.run()
            oos_res = bt_oos.summary()
            oos_metrics.append(oos_res)

        # Calculate average degradation
        avg_is_sharpe = sum(m.get("sharpe", 0) for m in is_metrics) / len(is_metrics)
        avg_oos_sharpe = sum(m.get("sharpe", 0) for m in oos_metrics) / len(oos_metrics)
        
        robustness_index = (avg_oos_sharpe / avg_is_sharpe) if avg_is_sharpe > 0 else 0

        return {
            "num_windows_tested": len(windows),
            "average_in_sample_sharpe": round(avg_is_sharpe, 2),
            "average_out_of_sample_sharpe": round(avg_oos_sharpe, 2),
            "robustness_index_%": round(robustness_index * 100, 2),
            "verdict": "Robust" if robustness_index >= 0.5 else "Overfitted (Curve-fit)",
            "windows_detail": [
                {"window": i+1, "IS_sharpe": is_metrics[i].get("sharpe"), "OOS_sharpe": oos_metrics[i].get("sharpe")}
                for i in range(len(windows))
            ]
        }
