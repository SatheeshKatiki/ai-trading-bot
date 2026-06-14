"""Backtesting runner for the EMA+RSI strategy.

Loads historical OHLCV CSV data, runs the EMA + RSI signal generator, simulates
simple intraday trades (enter at the next candle's open, exit on opposite
signal), and prints a performance summary.

Usage example::

    python -m backtesting_engine.run \
        --data-path data/RELIANCE_1min.csv \
        --symbol RELIANCE
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from typing import List

import numpy as np
import pandas as pd

from shared.indicators import ema, rsi
from trading_bot.strategies.ema_rsi_strategy import generate_signals

# ---------------------------------------------------------------------------
# Helper functions for performance metrics
# ---------------------------------------------------------------------------
def compute_returns(pnl_series: pd.Series) -> pd.Series:
    """Convert a series of trade PnL into cumulative return series.

    The function assumes the PnL series is already expressed in the same unit
    as the initial capital (e.g., dollars). It returns the cumulative net worth
    series (starting at 0) so that downstream calculations (Sharpe, drawdown)
    can operate on a returns‑like array.
    """
    return pnl_series.cumsum()

def sharpe_ratio(returns: pd.Series, period: int = 252) -> float:
    """Annualized Sharpe ratio assuming risk‑free rate = 0.

    Args:
        returns: Series of periodic (here minute) returns.
        period: Number of periods per year (default 252 trading days * 390
                minutes ≈ 98 280; we keep the default simple and let callers set a
                realistic value).
    """
    if returns.empty:
        return 0.0
    mean = returns.mean()
    std = returns.std(ddof=1)
    if std == 0:
        return 0.0
    # Scale to annual using sqrt(periods per year)
    return np.sqrt(period) * mean / std

def max_drawdown(equity_curve: pd.Series) -> float:
    """Maximum drawdown expressed as a positive percentage.

    ``equity_curve`` is the cumulative profit curve.
    """
    if equity_curve.empty:
        return 0.0
    roll_max = equity_curve.cummax()
    drawdowns = (roll_max - equity_curve) / roll_max.replace(to_replace=0, value=np.nan).ffill()
    return drawdowns.max() * 100

def win_rate(pnl_series: pd.Series) -> float:
    """Percentage of winning trades (PnL > 0)."""
    if pnl_series.empty:
        return 0.0
    wins = (pnl_series > 0).sum()
    return wins / len(pnl_series) * 100

# ---------------------------------------------------------------------------
# Simple back-test simulator with slippage & commission
# ---------------------------------------------------------------------------
class Backtester:
    """Simulate intraday trades based on raw signals.

    Features:
    - Slippage simulation (bps)
    - Commission/brokerage simulation
    """

    def __init__(self, df: pd.DataFrame, initial_capital: float = 10_000.0,
                 slippage_bps: float = 2.0, commission_per_trade: float = 20.0):
        self.df = df.copy()
        self.capital = initial_capital
        self.slippage_bps = slippage_bps
        self.commission_per_trade = commission_per_trade
        
        self.position_price: float | None = None
        self.trades: List[float] = []
        self.equity_curve = pd.Series([], dtype=float)

    def _apply_slippage(self, price: float, side: str) -> float:
        """Apply slippage to price (add to BUY, subtract from SELL)."""
        slip_amt = price * (self.slippage_bps / 10000)
        return price + slip_amt if side == "BUY" else price - slip_amt

    def run(self, signals: pd.Series | None = None) -> None:
        if signals is None:
            signals = generate_signals(self.df)
        
        for i in range(len(self.df) - 1):
            signal = signals.iloc[i]
            next_open = self.df["open"].iloc[i + 1]
            
            # Close existing long
            if self.position_price is not None and signal == -1:
                exit_price = self._apply_slippage(next_open, "SELL")
                pnl = exit_price - self.position_price - self.commission_per_trade
                self.trades.append(pnl)
                self.capital += pnl
                self.position_price = None
                
            # Open new long
            if self.position_price is None and signal == 1:
                entry_price = self._apply_slippage(next_open, "BUY")
                self.position_price = entry_price
                self.capital -= self.commission_per_trade  # deduct entry comms
                
            self.equity_curve = pd.concat([self.equity_curve, pd.Series([self.capital])])
            
        # End-of-data cleanup
        if self.position_price is not None:
            final_price = self._apply_slippage(self.df["close"].iloc[-1], "SELL")
            pnl = final_price - self.position_price - self.commission_per_trade
            self.trades.append(pnl)
            self.capital += pnl
            self.position_price = None
            self.equity_curve = pd.concat([self.equity_curve, pd.Series([self.capital])])

    def summary(self) -> dict:
        pnl_series = pd.Series(self.trades)
        equity = pd.Series(self.equity_curve)
        returns = pnl_series / self.capital
        
        # Sortino Ratio (downside risk)
        downside = returns[returns < 0]
        sortino = 0.0
        if not downside.empty and downside.std() > 0:
            sortino = (returns.mean() / downside.std()) * np.sqrt(252)
            
        # Calmar Ratio
        mdd = max_drawdown(equity) / 100
        calmar = 0.0
        if mdd > 0:
            annual_return = (self.capital / 10_000.0) ** (252 / len(self.df)) - 1 if len(self.df) > 0 else 0
            calmar = annual_return / mdd

        return {
            "total_trades": len(self.trades),
            "final_capital": round(self.capital, 2),
            "total_pnl": round(pnl_series.sum(), 2),
            "win_rate_%": round(win_rate(pnl_series), 2),
            "max_drawdown_%": round(mdd * 100, 2),
            "sharpe": round(sharpe_ratio(returns), 2),
            "sortino": round(sortino, 2),
            "calmar": round(calmar, 2)
        }

def run_intraday_backtest(df: pd.DataFrame, signals: pd.Series, initial_capital: float = 100000.0,
                           slippage_bps: float = 2.0, commission_per_trade: float = 20.0, multiplier: int = 10,
                           options_delta: float = 1.0,
                           target_pct: float = 2.0, stoploss_pct: float = 1.0, **kwargs) -> dict:
    """Run a detailed backtest with shorting, slippage, and commission."""
    trades = []
    position = None
    capital = initial_capital
    equity_curve = []
    
    def apply_slippage(price, side):
        slip_amt = price * (slippage_bps / 10000)
        return price + slip_amt if side == "BUY" else price - slip_amt

    # Optimize by converting to numpy arrays for the tight loop
    closes = df['close'].to_numpy()
    if 'datetime' in df.columns:
        times = df['datetime'].apply(lambda x: str(x)[:16] if isinstance(x, str) else "00:00").to_numpy()
    else:
        times = ["00:00"] * len(df)
        
    sig_vals = signals.to_numpy()
    has_st = 'st_direction' in df.columns
    st_dirs = df['st_direction'].to_numpy() if has_st else np.zeros(len(df))
    
    has_custom_sl = 'custom_sl_pct' in df.columns
    custom_sls = df['custom_sl_pct'].to_numpy() if has_custom_sl else np.zeros(len(df))
    
    has_scores = 'call_score' in df.columns and 'put_score' in df.columns
    if has_scores:
        call_scores = df['call_score'].to_numpy()
        put_scores = df['put_score'].to_numpy()
    else:
        call_scores = np.zeros(len(df))
        put_scores = np.zeros(len(df))
        
    has_atr = 'atr' in df.columns
    atr_vals = df['atr'].to_numpy() if has_atr else np.zeros(len(df))
    
    for i in range(len(df)):
        current_price = float(closes[i])
        current_time = times[i]
        signal = sig_vals[i]
        
        # Exit condition
        if position is not None:
            is_long = position["type"] == "BUY"
            
            # Smart Stop Loss (Dynamic Exit based on Supertrend)
            smart_stop_loss = False
            if is_long:
                if has_st and st_dirs[i] == -1:
                    smart_stop_loss = True
            else:
                if has_st and st_dirs[i] == 1:
                    smart_stop_loss = True
                    
            # Exit Logic
            # Calculate PnL based on the FIRST entry price for SL/Target percentage checks
            entry_price = position["entries"][0][0]
            pnl_pct = (current_price - entry_price) / entry_price * 100 if is_long else (entry_price - current_price) / entry_price * 100
            
            # Pyramiding (Scaling In) Simulation
            if kwargs.get("enable_pyramiding", True):
                scales_done = position.get("scales_done", 0)
                if scales_done < kwargs.get("max_scales", 2):
                    pnl_pts = (current_price - entry_price) if is_long else (entry_price - current_price)
                    req_pts = (scales_done + 1) * kwargs.get("scale_points", 40)
                    
                    if pnl_pts >= req_pts:
                        scale_qty = multiplier // 2
                        if scale_qty < 1: scale_qty = 1
                        position["entries"].append((current_price, scale_qty))
                        position["scales_done"] = scales_done + 1
            
            # Track peak profit reached for trailing stop loss
            position["max_pnl_pct"] = max(position.get("max_pnl_pct", 0.0), pnl_pct)
            
            current_sl_pct = position.get("sl_pct", stoploss_pct)
            
            # Trailing Stop Loss / Breakeven Profit Lock
            enable_tsl = kwargs.get("enable_trailing_sl", True) and kwargs.get("trailing_sl", True)
            if enable_tsl:
                trail_trigger = kwargs.get("trail_trigger", 0.8)
                trail_offset = kwargs.get("trail_offset", 0.2)
                
                if position["max_pnl_pct"] >= trail_trigger:
                    # Trailed Stop Loss is set relative to entry (negative current_sl_pct acts as a profit target exit)
                    current_sl_pct = -max(0.0, position["max_pnl_pct"] - trail_offset)
            
            target_hit = pnl_pct >= target_pct
            stoploss_hit = pnl_pct <= -current_sl_pct
            
            # Track if targets were hit (for partial profits if enabled)
            if pnl_pct >= current_sl_pct:
                position["t1_hit"] = True
            if pnl_pct >= (current_sl_pct * 2):
                position["t2_hit"] = True
                
            should_exit = (is_long and signal == -1) or (not is_long and signal == 1) or (i == len(df) - 1) or stoploss_hit or target_hit
            
            if should_exit:
                exit_price = apply_slippage(current_price, "SELL" if is_long else "BUY")
                
                # Determine exit reason
                exit_reason = "SIGNAL"
                if stoploss_hit:
                    exit_reason = "STOPLOSS"
                elif target_hit:
                    exit_reason = "TARGET"
                
                # Base PnL for all scales combined
                if is_long:
                    base_pnl = sum((exit_price - e_price) * qty * options_delta for e_price, qty in position["entries"])
                else:
                    base_pnl = sum((e_price - exit_price) * qty * options_delta for e_price, qty in position["entries"])
                
                # Calculate PnL (Partial Profits vs Full Run)
                pnl = 0
                if kwargs.get("enable_partial_profits", False):
                    rem_weight = 1.0
                    # 30% at 1:1
                    if position.get("t1_hit", False):
                        pnl += (entry_price * (current_sl_pct / 100)) * multiplier * options_delta * 0.3
                        rem_weight -= 0.3
                    # 30% at 1:2
                    if position.get("t2_hit", False):
                        pnl += (entry_price * (current_sl_pct * 2 / 100)) * multiplier * options_delta * 0.3
                        rem_weight -= 0.3
                    # Remaining 40%
                    pnl += base_pnl * rem_weight
                else:
                    pnl = base_pnl
                    
                pnl -= commission_per_trade
                
                capital += pnl
                trades.append({
                    "id": f"T-{len(trades) + 1}",
                    "type": position["type"],
                    "entry": position["entries"][0][0],
                    "exit": exit_price,
                    "scales": position.get("scales_done", 0),
                    "pnl": pnl,
                    "time": position["time"],
                    "score": position.get("score", 0),
                    "exit_reason": exit_reason
                })
                position = None
                
        # Entry condition
        if position is None:
            if signal == 1 and (i == 0 or sig_vals[i-1] != 1):
                entry_price = apply_slippage(current_price, "BUY")
                
                # Dynamic SL/Target based on ATR (Optional) or Custom SL
                if has_custom_sl and custom_sls[i] > 0:
                    current_sl_pct = custom_sls[i]
                elif kwargs.get("enable_dynamic_atr_sl", False):
                    atr = atr_vals[i] if has_atr else entry_price * 0.005
                    current_sl_pct = (atr * 1.5) / entry_price * 100
                else:
                    current_sl_pct = stoploss_pct
                
                score = call_scores[i] if has_scores else 0
                
                position = {"type": "BUY", "entries": [(entry_price, multiplier)], "time": current_time, "sl_pct": current_sl_pct, "score": score}
                capital -= commission_per_trade
            elif signal == -1 and (i == 0 or sig_vals[i-1] != -1):
                entry_price = apply_slippage(current_price, "SELL")
                
                # Dynamic SL/Target based on ATR (Optional) or Custom SL
                if has_custom_sl and custom_sls[i] > 0:
                    current_sl_pct = custom_sls[i]
                elif kwargs.get("enable_dynamic_atr_sl", False):
                    atr = atr_vals[i] if has_atr else entry_price * 0.005
                    current_sl_pct = (atr * 1.5) / entry_price * 100
                else:
                    current_sl_pct = stoploss_pct
                
                score = put_scores[i] if has_scores else 0
                
                position = {"type": "SELL", "entries": [(entry_price, multiplier)], "time": current_time, "sl_pct": current_sl_pct, "score": score}
                capital -= commission_per_trade
                
        if i % max(1, len(df) // 20) == 0:
            equity_curve.append({"name": current_time, "value": capital})
            
    # Calculate stats
    pnl_series = pd.Series([t["pnl"] for t in trades]) if trades else pd.Series([], dtype=float)
    total_pnl = capital - initial_capital
    winning_trades = [t for t in trades if t["pnl"] > 0]
    losing_trades = [t for t in trades if t["pnl"] <= 0]
    
    avg_win_score = sum([t["score"] for t in winning_trades]) / len(winning_trades) if winning_trades else 0
    avg_loss_score = sum([t["score"] for t in losing_trades]) / len(losing_trades) if losing_trades else 0
    
    total_profit = sum([t["pnl"] for t in winning_trades])
    total_loss = abs(sum([t["pnl"] for t in losing_trades]))
    # Advanced Metrics
    avg_win_amount = total_profit / len(winning_trades) if winning_trades else 0
    avg_loss_amount = total_loss / len(losing_trades) if losing_trades else 0
    
    win_rate = len(winning_trades) / len(trades) if trades else 0
    loss_rate = 1 - win_rate
    expectancy = (win_rate * avg_win_amount) - (loss_rate * avg_loss_amount)
    
    # Sharpe & Sortino (Simplified intraday calculation based on trade PnL)
    sharpe_ratio = 0.0
    sortino_ratio = 0.0
    if not pnl_series.empty and pnl_series.std() > 0:
        # Annualized Sharpe (Assuming ~1000 trades a year if 4 trades a day)
        # For simplicity, we just use the raw mean/std of PnL scaled
        mean_pnl = pnl_series.mean()
        std_pnl = pnl_series.std()
        sharpe_ratio = (mean_pnl / std_pnl) * np.sqrt(252) # approximated
        
        downside_pnl = pnl_series[pnl_series < 0]
        if not downside_pnl.empty and downside_pnl.std() > 0:
            sortino_ratio = (mean_pnl / downside_pnl.std()) * np.sqrt(252)
            
    # Fix Profit Factor displaying massive integers
    if total_loss == 0:
        profit_factor = "Infinity" if total_profit > 0 else 0.0
    else:
        profit_factor = round(total_profit / total_loss, 2)
        
    # Calculate Max Drawdown
    peak = initial_capital
    max_dd = 0
    current_cap = initial_capital
    for t in trades:
        current_cap += t["pnl"]
        if current_cap > peak:
            peak = current_cap
        dd = (peak - current_cap) / peak * 100
        if dd > max_dd:
            max_dd = dd
            
    stats = {
        "profitFactor": profit_factor,
        "winRate": f"{(win_rate * 100):.1f}" if trades else "0.0",
        "totalTrades": len(trades),
        "successTrades": len(winning_trades),
        "failedTrades": len(losing_trades),
        "stoplossTrades": sum(1 for t in trades if t.get("exit_reason") == "STOPLOSS"),
        "maxDrawdown": -round(max_dd, 2),
        "netProfit": total_pnl,
        "avgWinScore": f"{avg_win_score:.1f}",
        "avgLossScore": f"{avg_loss_score:.1f}",
        "expectancy": round(expectancy, 2),
        "sharpeRatio": round(sharpe_ratio, 2),
        "sortinoRatio": round(sortino_ratio, 2),
        "targetPct": target_pct,   # Dynamic Echo
        "stoplossPct": stoploss_pct, # Dynamic Echo
        "donchianPeriod": kwargs.get("donchian_period", 10)
    }
    
    return {
        "stats": stats,
        "equityCurve": equity_curve,
        "trades": trades,
        "rejectionLogs": kwargs.get("rejection_logs", [])
    }

# ---------------------------------------------------------------------------
# CLI handling
# ---------------------------------------------------------------------------
def parse_args(argv: List[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Backtest EMA+RSI strategy on historical CSV data"
    )
    parser.add_argument(
        "--data-path",
        type=Path,
        required=True,
        help="Path to CSV file containing OHLCV data (must include columns: open, high, low, close, volume)",
    )
    parser.add_argument(
        "--initial-capital",
        type=float,
        default=10_000,
        help="Starting capital for the simulation (default: 10,000)",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        help="Logging level (DEBUG, INFO, WARNING, ERROR)",
    )
    return parser.parse_args(argv)


def main(argv: List[str] | None = None) -> None:
    args = parse_args(argv)
    logging.basicConfig(level=args.log_level.upper(), format="[%(levelname)s] %(message)s")
    logger = logging.getLogger(__name__)

    if not args.data_path.is_file():
        logger.error("Data file not found: %s", args.data_path)
        sys.exit(1)

    # Load CSV – assume first column is datetime index or a column named 'datetime'
    df = pd.read_csv(args.data_path)
    if "datetime" in df.columns:
        df["datetime"] = pd.to_datetime(df["datetime"])
        df.set_index("datetime", inplace=True)
    else:
        # If there's no explicit datetime column, try parsing the index
        df.index = pd.to_datetime(df.index)

    required = {"open", "high", "low", "close", "volume"}
    if not required.issubset(df.columns):
        logger.error(
            "CSV missing required columns. Expected at least %s, got %s",
            required,
            set(df.columns),
        )
        sys.exit(1)

    backtester = Backtester(df, initial_capital=args.initial_capital)
    backtester.run()
    summary = backtester.summary()
    logger.info("Backtest completed – summary:")
    for k, v in summary.items():
        logger.info("%s: %s", k, v)


if __name__ == "__main__":
    main()
