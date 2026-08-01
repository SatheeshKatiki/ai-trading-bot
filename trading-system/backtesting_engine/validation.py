"""Walk-Forward Testing validation suite.

Splits historical data into sliding windows of In-Sample (IS) and Out-Of-Sample (OOS)
data to validate that the strategy does not suffer from curve-fitting/overfitting.
"""

import logging
from typing import Any, Dict, List, Tuple

import pandas as pd

from backtesting_engine.run import run_intraday_backtest
from trading_bot.strategies.registry import registry

logger = logging.getLogger(__name__)


class WalkForwardValidator:
    """Performs Walk-Forward testing on historical data.

    High audit finding this fixes: this class used to run both the
    In-Sample and Out-Of-Sample windows through the simple, correctly-lagged
    `Backtester` class — not `run_intraday_backtest`, the engine actually
    used for tuning/production (confirmed via grid_search.py). A "Robust"
    verdict from the old version said nothing about the engine that
    generates the real strategy numbers operators actually look at. It now
    runs a named, registered strategy's real signals through the same
    run_intraday_backtest() engine grid_search.py and the live dashboard use.
    """

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

            train_df = self.df.iloc[start_idx:train_end].reset_index(drop=True)
            test_df = self.df.iloc[train_end:test_end].reset_index(drop=True)
            windows.append((train_df, test_df))

        return windows

    def _run_segment(self, segment_df: pd.DataFrame, strategy_name: str, strategy_kwargs: dict) -> Dict[str, Any]:
        """Generate real signals for `strategy_name` and run them through the
        actual production backtest engine — not a simplified stand-in."""
        signals_data = registry.run_strategy(strategy_name, segment_df.copy(), **strategy_kwargs)
        signals = signals_data[0] if isinstance(signals_data, tuple) else signals_data
        result = run_intraday_backtest(
            segment_df.copy(), signals, initial_capital=self.initial_capital, **strategy_kwargs
        )
        return result.get("stats", {})

    def run_walk_forward(
        self, strategy_name: str, num_windows: int = 5, train_ratio: float = 0.7, **strategy_kwargs
    ) -> Dict[str, Any]:
        """Run the walk-forward testing process for `strategy_name`.

        Parameters
        ----------
        strategy_name : str
            A strategy registered in trading_bot.strategies.registry — the
            same name used to select a strategy for live trading/backtesting
            elsewhere, so the walk-forward result is about a real,
            identifiable strategy rather than an unnamed default.
        strategy_kwargs : dict
            Forwarded to both the strategy's signal generator and
            run_intraday_backtest (stoploss_pct, target_pct, etc.) — the same
            kwargs a caller would pass to /api/backtest for this strategy.

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
            logger.info("Running WF Window %d for strategy '%s'...", idx + 1, strategy_name)

            is_metrics.append(self._run_segment(train_df, strategy_name, strategy_kwargs))
            oos_metrics.append(self._run_segment(test_df, strategy_name, strategy_kwargs))

        # run_intraday_backtest's stats dict uses "sharpeRatio" (camelCase).
        def _sharpe(m: Dict[str, Any]) -> float:
            val = m.get("sharpeRatio", 0)
            try:
                return float(val)
            except (TypeError, ValueError):
                return 0.0

        avg_is_sharpe = sum(_sharpe(m) for m in is_metrics) / len(is_metrics)
        avg_oos_sharpe = sum(_sharpe(m) for m in oos_metrics) / len(oos_metrics)

        robustness_index = (avg_oos_sharpe / avg_is_sharpe) if avg_is_sharpe > 0 else 0

        return {
            "strategy": strategy_name,
            "num_windows_tested": len(windows),
            "average_in_sample_sharpe": round(avg_is_sharpe, 2),
            "average_out_of_sample_sharpe": round(avg_oos_sharpe, 2),
            "robustness_index_%": round(robustness_index * 100, 2),
            "verdict": "Robust" if robustness_index >= 0.5 else "Overfitted (Curve-fit)",
            "windows_detail": [
                {"window": i + 1, "IS_sharpe": _sharpe(is_metrics[i]), "OOS_sharpe": _sharpe(oos_metrics[i])}
                for i in range(len(windows))
            ],
        }
