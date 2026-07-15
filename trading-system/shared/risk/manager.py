"""Institutional-grade Risk Management Engine.

Provides real-time risk controls for the live trading bot:
- Per-trade risk limiting
- Daily loss limit enforcement
- Maximum drawdown control
- Consecutive loss tracking
- Volatility-based risk scaling
- Automatic Risk-Off (halt trading)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import List, Optional

logger = logging.getLogger(__name__)


@dataclass
class TradeRecord:
    """Lightweight record of a completed trade for risk tracking."""
    symbol: str
    side: str          # "BUY" or "SELL"
    entry_price: float
    exit_price: float
    pnl: float
    timestamp: str


@dataclass
class RiskConfig:
    """Risk management configuration parameters."""
    # Per-trade risk as fraction of equity (1% = 0.01)
    risk_per_trade: float = 0.01
    # Maximum daily loss as fraction of equity (5% = 0.05)
    daily_loss_limit: float = 0.05
    # Maximum drawdown before halting (20% = 0.20)
    max_drawdown: float = 0.20
    # Halt after N consecutive losses
    max_consecutive_losses: int = 5
    # Minimum AI confidence to allow a trade
    min_ai_confidence: float = 0.55
    # High volatility threshold (ATR % of price)
    high_volatility_threshold: float = 3.0
    # AI Confidence Override (Increase risk if AI is highly confident)
    high_confidence_threshold: float = 0.85
    high_confidence_risk_per_trade: float = 0.035
    # Maximum trades allowed per day (0 = unlimited, controlled by loss limits)
    max_trades_per_day: int = 0


class RiskManager:
    """Real-time risk management engine.

    The RiskManager tracks equity, daily PnL, drawdown, and consecutive
    losses. It exposes a single ``can_trade()`` method that returns True
    only if all risk checks pass.

    Usage::

        rm = RiskManager(initial_capital=100_000)
        if rm.can_trade(symbol="RELIANCE", side="BUY", risk_amount=1000):
            # place order
            ...
        rm.record_trade(trade)  # after exit
    """

    def __init__(self, initial_capital: float = 100_000.0,
                 config: Optional[RiskConfig] = None,
                 daily_pnl: float = 0.0):
        self.initial_capital = initial_capital
        self.config = config or RiskConfig()

        self.current_equity = initial_capital
        self.peak_equity = initial_capital
        self.daily_pnl = daily_pnl
        self.today: date = date.today()
        self.consecutive_losses = 0
        self.total_trades = 0
        self.trades_today: List[TradeRecord] = []
        self._risk_off = False
        self._risk_off_reason = ""

    # ------------------------------------------------------------------
    # Core risk check
    # ------------------------------------------------------------------

    def can_trade(
        self,
        symbol: str = "",
        side: str = "BUY",
        risk_amount: float = 0.0,
        ai_confidence: float = 1.0,
        current_volatility: float = 0.0,
    ) -> tuple[bool, str]:
        """Check whether a new trade is allowed.

        Returns
        -------
        (allowed, reason) : tuple[bool, str]
            If ``allowed`` is False, ``reason`` explains why.
        """
        self._reset_daily_if_needed()

        # Risk-Off state
        if self._risk_off:
            return False, f"RISK-OFF: {self._risk_off_reason}"

        # Daily loss limit
        daily_limit = self.initial_capital * self.config.daily_loss_limit
        if abs(self.daily_pnl) >= daily_limit and self.daily_pnl < 0:
            self._activate_risk_off(f"Daily loss limit hit ({self.daily_pnl:.2f})")
            return False, f"Daily loss limit exceeded: {self.daily_pnl:.2f}"

        # Max drawdown
        drawdown = (self.peak_equity - self.current_equity) / self.peak_equity
        if drawdown >= self.config.max_drawdown:
            self._activate_risk_off(f"Max drawdown {drawdown:.1%}")
            return False, f"Max drawdown exceeded: {drawdown:.1%}"

        # Consecutive losses
        if self.consecutive_losses >= self.config.max_consecutive_losses:
            return False, f"Consecutive losses: {self.consecutive_losses}"

        # AI confidence
        if ai_confidence < self.config.min_ai_confidence:
            return False, f"AI confidence too low: {ai_confidence:.2f}"

        # Volatility check
        if current_volatility > self.config.high_volatility_threshold:
            return False, f"Volatility too high: {current_volatility:.2f}%"

        # Max trades per day check
        if self.config.max_trades_per_day > 0:
            # We count already recorded (closed) trades today.
            # Using len(self.trades_today) guarantees midnight rollover resets this correctly.
            if len(self.trades_today) >= self.config.max_trades_per_day:
                return False, f"Max trades per day reached ({self.config.max_trades_per_day})"

        # Per-trade risk check (Dynamic override for high confidence)
        allowed_risk_pct = self.config.risk_per_trade
        if ai_confidence >= self.config.high_confidence_threshold:
            allowed_risk_pct = self.config.high_confidence_risk_per_trade
            logger.info("AI Confidence Override active (%.0f%%) -> Risk Limit increased to %.1f%%", ai_confidence*100, allowed_risk_pct*100)
            
        max_risk = self.current_equity * allowed_risk_pct
        if risk_amount > max_risk:
            return False, f"Risk {risk_amount:.2f} exceeds limit {max_risk:.2f}"

        return True, "OK"

    # ------------------------------------------------------------------
    # Trade recording
    # ------------------------------------------------------------------

    def record_trade(self, trade: TradeRecord) -> None:
        """Record a completed trade and update risk metrics."""
        self._reset_daily_if_needed()

        self.current_equity += trade.pnl
        self.daily_pnl += trade.pnl
        self.total_trades += 1
        self.trades_today.append(trade)

        # Update peak equity
        if self.current_equity > self.peak_equity:
            self.peak_equity = self.current_equity

        # Track consecutive losses
        if trade.pnl < 0:
            self.consecutive_losses += 1
        else:
            self.consecutive_losses = 0

        logger.info(
            "Trade recorded: %s %s PnL=%.2f | Equity=%.2f | Daily=%.2f | ConsecLoss=%d",
            trade.side, trade.symbol, trade.pnl, self.current_equity,
            self.daily_pnl, self.consecutive_losses,
        )

    # ------------------------------------------------------------------
    # Position sizing
    # ------------------------------------------------------------------

    def calculate_position_size(
        self,
        entry_price: float,
        stop_loss_price: float,
        method: str = "fixed_fractional",
        ai_confidence: float = 1.0,
    ) -> int:
        """Calculate the number of shares/lots to trade.

        Parameters
        ----------
        entry_price : float
            Planned entry price.
        stop_loss_price : float
            Planned stop-loss price.
        method : str
            ``"fixed_fractional"`` or ``"kelly"``.

        Returns
        -------
        int
            Number of shares (floored to integer).
        """
        risk_per_share = abs(entry_price - stop_loss_price)
        if risk_per_share <= 0:
            return 0

        allowed_risk_pct = self.config.risk_per_trade
        if ai_confidence >= self.config.high_confidence_threshold:
            allowed_risk_pct = self.config.high_confidence_risk_per_trade
            
        max_risk = self.current_equity * allowed_risk_pct

        if method == "fixed_fractional":
            qty = max_risk / risk_per_share
        elif method == "kelly":
            # Simplified Kelly: use win rate from recent trades
            wins = sum(1 for t in self.trades_today if t.pnl > 0)
            total = len(self.trades_today) or 1
            win_rate = wins / total
            avg_win = sum(t.pnl for t in self.trades_today if t.pnl > 0) / max(wins, 1)
            avg_loss = abs(sum(t.pnl for t in self.trades_today if t.pnl < 0) / max(total - wins, 1))
            if avg_loss == 0:
                kelly_pct = allowed_risk_pct
            elif avg_win == 0:
                kelly_pct = 0.0
            else:
                kelly_pct = max(0, win_rate - (1 - win_rate) / (avg_win / avg_loss))
                
            # Prevent 100% Kelly from bankrupting the account!
            kelly_pct = min(kelly_pct, allowed_risk_pct)
            
            qty = (self.current_equity * kelly_pct) / risk_per_share
        else:
            qty = max_risk / risk_per_share

        return max(int(qty), 0)

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------

    def status(self) -> dict:
        """Return current risk status as a dictionary."""
        drawdown = (self.peak_equity - self.current_equity) / self.peak_equity if self.peak_equity > 0 else 0
        return {
            "equity": round(self.current_equity, 2),
            "peak_equity": round(self.peak_equity, 2),
            "daily_pnl": round(self.daily_pnl, 2),
            "drawdown_pct": round(drawdown * 100, 2),
            "consecutive_losses": self.consecutive_losses,
            "trades_today": len(self.trades_today),
            "risk_off": self._risk_off,
            "risk_off_reason": self._risk_off_reason,
        }

    def reset_risk_off(self) -> None:
        """Manually reset the Risk-Off state (use with caution)."""
        self._risk_off = False
        self._risk_off_reason = ""
        logger.warning("Risk-Off state manually reset")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _reset_daily_if_needed(self) -> None:
        """Reset daily counters if the date has changed."""
        if date.today() != self.today:
            logger.info("New trading day - resetting daily counters")
            self.today = date.today()
            self.daily_pnl = 0.0
            self.trades_today = []
            self.total_trades = 0
            self.consecutive_losses = 0
            if self._risk_off and "Daily" in self._risk_off_reason:
                self.reset_risk_off()

    def _activate_risk_off(self, reason: str) -> None:
        """Activate Risk-Off mode."""
        self._risk_off = True
        self._risk_off_reason = reason
        logger.critical("RISK-OFF ACTIVATED: %s", reason)
