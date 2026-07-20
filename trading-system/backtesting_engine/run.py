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
from trading_bot.strategies.momentum_strategy import generate_signals

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
            "calmar": round(calmar, 2),
        }

def run_intraday_backtest(df: pd.DataFrame, signals: pd.Series, initial_capital: float = 100000.0,
                           slippage_bps: float = 2.0, commission_per_trade: float = 20.0, multiplier: int = 10,
                           options_delta: float = 0.5,
                           target_pct: float = 2.0, stoploss_pct: float = 1.0, **kwargs) -> dict:
    """Run a detailed backtest with shorting, slippage, and commission."""
    trades = []
    position = None
    capital = initial_capital
    equity_curve = []
    
    # ── Data Continuity Validation ───────────────────────────────────────
    if 'datetime' in df.columns and len(df) > 100:
        dates = pd.to_datetime(df['datetime']).dt.date.unique()
        if len(dates) > 1:
            diffs = pd.Series(dates).diff().dt.days.dropna()
            max_gap = diffs.max()
            if max_gap > 14:  # A gap of more than 14 days (e.g., missed 100-day chunk) is abnormal
                logger.warning(f"Data Continuity Warning: Found a massive gap of {max_gap} days in the dataset!")
                kwargs["rejection_logs"] = kwargs.get("rejection_logs", []) + [f"Data Continuity Warning: Massive {max_gap}-day gap detected!"]
    # ─────────────────────────────────────────────────────────────────────
    # ── Daily Risk Controls ──────────────────────────────────────────────
    max_daily_loss_pct  = kwargs.get("max_daily_loss_pct", 3.0)   # stop trading day if capital drops X%
    max_daily_trades    = kwargs.get("max_daily_trades", 6)         # max trades per day
    daily_capital_start = initial_capital                          # resets each new day
    daily_pnl           = 0.0
    daily_trades_count  = 0
    total_brokerage     = 0.0
    total_slippage      = 0.0
    trading_halted_day  = None                                     # date string when halt triggered
    current_day         = None
    # ─────────────────────────────────────────────────────────────────────

    def apply_slippage(price, side):
        slip_amt = price * (slippage_bps / 10000)
        return price + slip_amt if side == "BUY" else price - slip_amt

    # Optimize by converting to numpy arrays for the tight loop
    closes = df['close'].to_numpy()
    if 'datetime' in df.columns:
        times = df['datetime'].apply(lambda x: str(x)[:16] if isinstance(x, str) else "00:00").to_numpy()
        total_trading_days = len(set([str(x)[:10] for x in df['datetime']]))
    else:
        times = ["00:00"] * len(df)
        total_trading_days = 0

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
        
        # ── Daily Reset & Loss-Limit Guard ───────────────────────────────
        candle_day = current_time[:10] if len(current_time) >= 10 else current_time
        if candle_day != current_day:
            # New trading day: reset daily counters
            current_day         = candle_day
            daily_pnl           = 0.0
            daily_trades_count  = 0
            daily_capital_start = capital

        # If daily loss limit hit → skip entries for the rest of this day
        daily_loss_pct = (daily_pnl / daily_capital_start * 100) if daily_capital_start > 0 else 0
        daily_limit_hit = daily_loss_pct <= -max_daily_loss_pct
        
        # Treat max_daily_trades = 0 as unlimited
        if max_daily_trades <= 0:
            daily_trades_hit = False
        else:
            daily_trades_hit = daily_trades_count >= max_daily_trades
        # ─────────────────────────────────────────────────────────────────
        
        if "last_sl_trade" not in locals():
            last_sl_trade = None
            
        # ── Phase 4: Stop-Hunt Re-Entry (Fakeout Catcher) ──
        multiplier_override = None
        if position is None and last_sl_trade is not None:
            bars_passed = i - last_sl_trade["idx"]
            if bars_passed <= 5 and not daily_limit_hit and not daily_trades_hit:
                if last_sl_trade["dir"] == 1 and current_price > last_sl_trade["entry"]:
                    signal = 1
                    multiplier_override = multiplier # Full size re-entry (must respect lot size)
                    last_sl_trade = None
                elif last_sl_trade["dir"] == -1 and current_price < last_sl_trade["entry"]:
                    signal = -1
                    multiplier_override = multiplier
                    last_sl_trade = None
            elif bars_passed > 5:
                last_sl_trade = None
        
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
            enable_pyramiding_flag = kwargs.get("enable_pyramiding", True)
            if str(enable_pyramiding_flag).lower() == "true":
                scales_done = position.get("scales_done", 0)
                if scales_done < kwargs.get("max_scales", 2):
                    pnl_pts = (current_price - entry_price) if is_long else (entry_price - current_price)
                    pts_per_scale = entry_price * (kwargs.get("scale_pct", 0.2) / 100.0)
                    # Each scale triggers at a DIFFERENT level: scale1 at 1x, scale2 at 2x etc
                    req_pts = (scales_done + 1) * pts_per_scale

                    if pnl_pts >= req_pts and not position.get(f"scale_{scales_done}_done", False):
                        # Momentum-Weighted Pyramiding
                        # Must respect base lot size multiples
                        scale_qty = multiplier # Base 1x scale
                        
                        if has_atr and i >= 3:
                            atr_now = atr_vals[i]
                            atr_prev = atr_vals[i-3]
                            if atr_now > atr_prev * 1.05:
                                # Phase 4: Options Delta Rolling (Compounding Leverage)
                                # Volatility expanding -> Momentum accelerating -> Scale heavier (2x lot size)
                                scale_qty = multiplier * 2
                            elif atr_now < atr_prev * 0.95:
                                # Volatility contracting -> Momentum fading -> Skip scale to protect capital
                                scale_qty = 0
                                
                        if scale_qty > 0:
                            scale_entry = apply_slippage(current_price, position["type"])
                            position["entries"].append((scale_entry, scale_qty))
                            capital -= commission_per_trade
                            total_brokerage += commission_per_trade
                            total_slippage += abs(current_price - scale_entry) * scale_qty * options_delta
                            position["scales_done"] = scales_done + 1
                        # Mark this specific scale as done to prevent re-triggering every candle
                        position[f"scale_{scales_done}_done"] = True
                        # Shift SL to weighted average entry (breakeven protection)
                        total_qty = sum(q for _, q in position["entries"])
                        total_value = sum(p * q for p, q in position["entries"])
                        avg_price = total_value / total_qty
                        # Store average price directly — SL will trail from avg_price
                        position["avg_entry_price"] = avg_price
                        # Breakeven Snap: Move stop loss to the ORIGINAL entry price when pyramiding
                        # ONLY IF the strategy didn't provide a custom structural Stop Loss.
                        if not position.get("has_custom_sl", False):
                            position["sl_pct"] = 0.0
                        else:
                            # Retain the original structural SL
                            pass

            # Track peak profit reached for trailing stop loss
            position["max_pnl_pct"] = max(position.get("max_pnl_pct", 0.0), pnl_pct)

            # Use the position's current SL (may be updated by pyramiding)
            ml_sl_pct = custom_sls[i] if has_custom_sl and pd.notna(custom_sls[i]) and custom_sls[i] > 0 else None
            
            # If strategy provides a custom dynamic SL, ALWAYS trust it, even over Pyramiding Breakeven Snap!
            if ml_sl_pct is not None:
                raw_sl_pct = ml_sl_pct
            else:
                base_sl = stoploss_pct
                raw_sl_pct = position.get("sl_pct", base_sl)
                
            # After breakeven snap, sl_pct=0.0 means exit at entry — use a tiny floor
            # so the engine doesn't hold losing trades forever at breakeven
            current_sl_pct = raw_sl_pct if raw_sl_pct > 0 else min(stoploss_pct * 0.5, 0.05)

            # 3-Phase Trailing Stop Loss
            enable_tsl = kwargs.get("enable_trailing_sl", True) and kwargs.get("trailing_sl", True)
            if enable_tsl:
                ml_tsl_trigger = df['trailing_sl_trigger'].iloc[i] if 'trailing_sl_trigger' in df.columns else None
                trail_trigger = ml_tsl_trigger if pd.notna(ml_tsl_trigger) else kwargs.get("trail_trigger", 0.8)
                trail_offset = kwargs.get("trail_offset", 0.2)

                if position["max_pnl_pct"] >= trail_trigger:
                    # Phase 3: Hyper-tight trail if we exceed 2x the trigger (Super Trend Run)
                    if position["max_pnl_pct"] >= (trail_trigger * 2.0):
                        locked_profit = max(0.0, position["max_pnl_pct"] - 0.05) # Extremely tight 0.05% trail
                    else:
                        # Phase 2: Standard trailing
                        locked_profit = max(0.0, position["max_pnl_pct"] - trail_offset)
                    
                    position["tsl_locked_pct"] = locked_profit

            # Stoploss check: exit if pnl drops below -current_sl_pct (losing trade)
            stoploss_hit = pnl_pct <= -current_sl_pct

            # Trailing SL hit: exit if profit falls below the locked profit level
            tsl_locked = position.get("tsl_locked_pct")
            tsl_hit = (tsl_locked is not None) and (pnl_pct < tsl_locked)

            # Phase 4: Volatility-Adaptive Targets
            # If the market is highly volatile, dynamically expand the target
            base_target = position.get("target_pct", target_pct)
            target_hit = pnl_pct >= base_target
            
            # Hard monetary stoploss check (e.g. 2500 INR max loss per trade)
            max_inr_loss = kwargs.get("max_trade_loss_inr", 2500.0)
            if is_long:
                current_inr_pnl = sum((current_price - e_price) * qty * options_delta for e_price, qty in position["entries"])
            else:
                current_inr_pnl = sum((e_price - current_price) * qty * options_delta for e_price, qty in position["entries"])
            hard_monetary_hit = current_inr_pnl <= -max_inr_loss

            # Track if partial profit targets were hit (use original stoploss_pct as R unit)
            if pnl_pct >= stoploss_pct:
                position["t1_hit"] = True
            if pnl_pct >= (stoploss_pct * 2):
                position["t2_hit"] = True
                
            should_exit = (is_long and signal == -1) or (not is_long and signal == 1) or (i == len(df) - 1) or stoploss_hit or tsl_hit or target_hit or hard_monetary_hit

            if should_exit:
                exit_price = current_price
                exit_reason = "SIGNAL"
                
                total_qty = sum(qty for _, qty in position["entries"])
                avg_e = sum(p*q for p, q in position["entries"]) / total_qty

                if hard_monetary_hit:
                    exit_reason = "MAX_LOSS_LIMIT"
                    loss_pts = max_inr_loss / (total_qty * options_delta)
                    if is_long:
                        exit_price = avg_e - loss_pts
                    else:
                        exit_price = avg_e + loss_pts
                elif stoploss_hit:
                    exit_reason = "STOPLOSS"
                    last_sl_trade = {"idx": i, "entry": position["entries"][0][0], "dir": 1 if is_long else -1}
                    if is_long:
                        exit_price = entry_price * (1 - current_sl_pct / 100.0)
                    else:
                        exit_price = entry_price * (1 + current_sl_pct / 100.0)
                elif tsl_hit:
                    exit_reason = "TRAILING_SL"
                    if is_long:
                        exit_price = entry_price * (1 + tsl_locked / 100.0)
                    else:
                        exit_price = entry_price * (1 - tsl_locked / 100.0)
                elif target_hit:
                    exit_reason = "TARGET"
                    exit_t_pct = position.get("target_pct", target_pct)
                    if is_long:
                        exit_price = entry_price * (1 + exit_t_pct / 100.0)
                    else:
                        exit_price = entry_price * (1 - exit_t_pct / 100.0)
                
                exit_price_applied = apply_slippage(exit_price, "SELL" if is_long else "BUY")
                # Base PnL for all scales combined
                if is_long:
                    base_pnl = sum((exit_price_applied - e_price) * qty * options_delta for e_price, qty in position["entries"])
                else:
                    base_pnl = sum((e_price - exit_price_applied) * qty * options_delta for e_price, qty in position["entries"])
                total_qty = sum(qty for _, qty in position["entries"])
                
                total_brokerage += commission_per_trade
                total_slippage += abs(exit_price - exit_price_applied) * total_qty * options_delta
                
                # Deduct exit commission directly from capital (entry was already deducted when opened)
                capital -= commission_per_trade 
                
                # Calculate trade net PnL (Base PnL minus total commissions for entry+scales+exit)
                trade_net_pnl = base_pnl - (commission_per_trade * (len(position["entries"]) + 1))
                    
                # Calculate PnL (Partial Profits vs Full Run)
                if kwargs.get("enable_partial_profits", False):
                    partial_pnl = 0.0
                    rem_weight = 1.0
                    if position.get("t1_hit", False):
                        partial_pnl += (entry_price * (stoploss_pct / 100)) * multiplier * options_delta * 0.3
                        rem_weight -= 0.3
                    if position.get("t2_hit", False):
                        partial_pnl += (entry_price * (stoploss_pct * 2 / 100)) * multiplier * options_delta * 0.3
                        rem_weight -= 0.3
                    trade_net_pnl = partial_pnl + (base_pnl * rem_weight) - (commission_per_trade * (len(position["entries"]) + 1))

                capital += base_pnl
                daily_pnl += trade_net_pnl          # ← track daily P&L
                daily_trades_count += 1   # ← track daily trade count
                trades.append({
                    "id": f"T-{len(trades) + 1}",
                    "type": position["type"],
                    "entry": avg_e,
                    "exit": exit_price,
                    "qty": total_qty,
                    "scales": position.get("scales_done", 0),
                    "pnl": trade_net_pnl,
                    "time": position["time"],
                    "score": position.get("score", 0),
                    "exit_reason": exit_reason
                })
                position = None
                
        # Entry condition — skip if daily loss limit or trade cap reached
        if position is None and not daily_limit_hit and not daily_trades_hit:
            if signal == 1 and (i == 0 or sig_vals[i-1] != 1):
                entry_price = apply_slippage(current_price, "BUY")

                # Dynamic SL/Target based on ATR (Optional) or Custom SL
                pos_has_custom_sl = False
                if has_custom_sl and custom_sls[i] > 0:
                    current_sl_pct = custom_sls[i]
                    pos_has_custom_sl = True
                elif kwargs.get("enable_dynamic_atr_sl", False):
                    atr = atr_vals[i] if has_atr else entry_price * 0.005
                    current_sl_pct = (atr * 1.5) / entry_price * 100
                else:
                    current_sl_pct = stoploss_pct

                # Phase 4: Volatility-Adaptive Target
                atr = atr_vals[i] if has_atr else entry_price * 0.005
                vol_target_pct = (atr * 3.0) / entry_price * 100 # 3x ATR target
                dynamic_target = max(target_pct, vol_target_pct)

                score = call_scores[i] if has_scores else 0
                actual_mult = multiplier_override if multiplier_override is not None else multiplier

                position = {"type": "BUY", "entries": [(entry_price, actual_mult)], "time": current_time, "sl_pct": current_sl_pct, "target_pct": dynamic_target, "score": score, "has_custom_sl": pos_has_custom_sl}
                capital -= commission_per_trade
                total_brokerage += commission_per_trade
                total_slippage += abs(current_price - entry_price) * actual_mult * options_delta
            elif signal == -1 and (i == 0 or sig_vals[i-1] != -1):
                entry_price = apply_slippage(current_price, "SELL")

                # Dynamic SL/Target based on ATR (Optional) or Custom SL
                pos_has_custom_sl = False
                if has_custom_sl and custom_sls[i] > 0:
                    current_sl_pct = custom_sls[i]
                    pos_has_custom_sl = True
                elif kwargs.get("enable_dynamic_atr_sl", False):
                    atr = atr_vals[i] if has_atr else entry_price * 0.005
                    current_sl_pct = (atr * 1.5) / entry_price * 100
                else:
                    current_sl_pct = stoploss_pct

                # Phase 4: Volatility-Adaptive Target
                atr = atr_vals[i] if has_atr else entry_price * 0.005
                vol_target_pct = (atr * 3.0) / entry_price * 100 # 3x ATR target
                dynamic_target = max(target_pct, vol_target_pct)

                score = put_scores[i] if has_scores else 0
                actual_mult = multiplier_override if multiplier_override is not None else multiplier

                position = {"type": "SELL", "entries": [(entry_price, actual_mult)], "time": current_time, "sl_pct": current_sl_pct, "target_pct": dynamic_target, "score": score, "has_custom_sl": pos_has_custom_sl}
                capital -= commission_per_trade
                total_brokerage += commission_per_trade
                total_slippage += abs(current_price - entry_price) * actual_mult * options_delta
                
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
        "totalTradingDays": total_trading_days,
        "successTrades": len(winning_trades),
        "failedTrades": len(losing_trades),
        "stoplossTrades": sum(1 for t in trades if t.get("exit_reason") in ("STOPLOSS", "TRAILING_SL")),
        "maxDrawdown": -round(max_dd, 2),
        "netProfit": total_pnl,
        "avgWinScore": f"{avg_win_score:.1f}",
        "avgLossScore": f"{avg_loss_score:.1f}",
        "expectancy": round(expectancy, 2),
        "sharpeRatio": round(sharpe_ratio, 2),
        "sortinoRatio": round(sortino_ratio, 2),
        "targetPct": target_pct,   # Dynamic Echo
        "stoplossPct": stoploss_pct, # Dynamic Echo
        "donchianPeriod": kwargs.get("donchian_period", 10),
        "totalBrokerage": round(total_brokerage, 2),
        "totalSlippage": round(total_slippage, 2)
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
