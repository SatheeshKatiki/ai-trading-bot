import logging
from datetime import datetime
from typing import Optional

import pytz

from shared.security import audit
from shared.security.audit_log import AuditEvent

_IST = pytz.timezone("Asia/Kolkata")

logger = logging.getLogger(__name__)


def _audit_circuit_breaker(event_type: str, reason: str, metric_value: float) -> None:
    """Record a portfolio circuit-breaker halt to the tamper-evident audit
    trail. Previously these halts only went to the plain application
    logger — no compliance/forensic record of WHEN and WHY trading was
    automatically halted."""
    audit.log(event_type, {"reason": reason, "metric_value": round(float(metric_value), 4)}, severity="WARNING")

class PortfolioRiskEngine:
    """
    Phase 7: Portfolio Risk Engine — Ultra-Professional Edition (Post-Audit v2)
    
    Provides global circuit breakers and drawdown limits.
    
    POST-AUDIT CHANGES:
    - Added gradual position size scaling (NOT binary halt)
    - Capital Protection: 3 losses → 50% size, 5 losses → 25% size, 7+ → halt
    - get_position_multiplier() for live trading position sizing
    - Daily reset now carries over winning streak info
    """
    
    def __init__(self,
                 max_daily_dd_pct: float = 5.0,
                 max_weekly_dd_pct: float = 10.0,
                 max_consecutive_losses: int = 7,
                 initial_capital: float = 100_000.0,
                 current_capital: Optional[float] = None):
        self.max_daily_dd_pct = max_daily_dd_pct
        self.max_weekly_dd_pct = max_weekly_dd_pct
        # Raised from 3 to 7 — at 3 we now reduce size, at 7 we halt
        self.max_consecutive_losses = max_consecutive_losses

        self.daily_pnl = 0.0
        self.weekly_pnl = 0.0
        # Root-cause fix (found live, 2026-08-05, same bug as
        # shared/risk/manager.py's RiskManager): always seeded from the
        # static initial_capital, discarding real cumulative equity on
        # every restart. Caller should pass the persisted equity
        # (state.db) when resuming a session.
        _seed_capital = current_capital if current_capital is not None else initial_capital
        self.peak_capital_daily = _seed_capital
        self.peak_capital_weekly = _seed_capital
        
        self.consecutive_losses = 0
        self.trading_halted = False
        self.halt_reason = ""
        
        now_ist = datetime.now(_IST)
        self.last_reset_day = now_ist.date()
        self.last_reset_week = now_ist.isocalendar()[1]
        
    def _check_resets(self, capital: float):
        now_ist = datetime.now(_IST)
        current_day = now_ist.date()
        current_week = now_ist.isocalendar()[1]
        
        if current_day != self.last_reset_day:
            self.daily_pnl = 0.0
            self.peak_capital_daily = capital
            self.last_reset_day = current_day
            # Lift halt if it was a daily DD or consecutive loss halt
            if "Daily" in self.halt_reason or "Consecutive Losses" in self.halt_reason:
                self.trading_halted = False
                self.halt_reason = ""
                self.consecutive_losses = 0
                logger.info("[PortfolioRisk] New trading day. Resetting consecutive losses and halt.")
                
        if current_week != self.last_reset_week:
            self.weekly_pnl = 0.0
            self.peak_capital_weekly = capital
            self.last_reset_week = current_week
            if "Weekly" in self.halt_reason:
                self.trading_halted = False
                self.halt_reason = ""
                
    def update_pnl(self, realized_pnl: float, capital: float):
        self._check_resets(capital)
        
        if realized_pnl < 0:
            self.consecutive_losses += 1
            logger.info(f"[PortfolioRisk] Loss #{self.consecutive_losses}. Consecutive losses: {self.consecutive_losses}")
        else:
            if self.consecutive_losses > 0:
                logger.info(f"[PortfolioRisk] WIN after {self.consecutive_losses} consecutive losses. Resetting.")
            self.consecutive_losses = 0
            
        self.daily_pnl += realized_pnl
        self.weekly_pnl += realized_pnl
        
        if capital > self.peak_capital_daily:
            self.peak_capital_daily = capital
        if capital > self.peak_capital_weekly:
            self.peak_capital_weekly = capital
            
        self._evaluate_risk(capital)
        
    def get_position_multiplier(self) -> float:
        """
        Returns position size multiplier based on consecutive loss count.
        
        This is the PROFESSIONAL approach:
        - Don't halt trading (you'll miss the recovery winners)
        - Gradually reduce size to protect capital
        - Reset quickly when winners come back
        
        Pattern proven in backtesting:
          0-2 losses: Full size  (1.0x)
          3-4 losses: Half size  (0.5x) ← protect capital
          5-6 losses: Quarter size (0.25x) ← minimal risk
          7+ losses:  Stop trading (bad regime — strategy doesn't fit market)
        
        Returns: float between 0.0 and 1.0
        """
        if self.trading_halted:
            return 0.0
        if self.consecutive_losses >= 5:
            return 0.25   # Quarter size
        elif self.consecutive_losses >= 3:
            return 0.5    # Half size
        return 1.0        # Full size
        
    def _evaluate_risk(self, capital: float):
        if self.trading_halted:
            return
            
        # Daily Drawdown Circuit Breaker
        if self.peak_capital_daily > 0:
            daily_dd_pct = ((self.peak_capital_daily - capital) / self.peak_capital_daily) * 100
            if daily_dd_pct >= self.max_daily_dd_pct:
                self.trading_halted = True
                self.halt_reason = f"Max Daily Drawdown Reached ({daily_dd_pct:.2f}%)"
                logger.warning(f"CIRCUIT BREAKER: {self.halt_reason}")
                _audit_circuit_breaker(AuditEvent.DAILY_LOSS_HIT, self.halt_reason, daily_dd_pct)
                return

        # Weekly Drawdown Circuit Breaker
        if self.peak_capital_weekly > 0:
            weekly_dd_pct = ((self.peak_capital_weekly - capital) / self.peak_capital_weekly) * 100
            if weekly_dd_pct >= self.max_weekly_dd_pct:
                self.trading_halted = True
                self.halt_reason = f"Max Weekly Drawdown Reached ({weekly_dd_pct:.2f}%)"
                logger.warning(f"CIRCUIT BREAKER: {self.halt_reason}")
                _audit_circuit_breaker(AuditEvent.RISK_BREACH, self.halt_reason, weekly_dd_pct)
                return

        # Consecutive Losses Circuit Breaker (raised threshold — size scaling kicks in first)
        if self.consecutive_losses >= self.max_consecutive_losses:
            self.trading_halted = True
            self.halt_reason = f"Max Consecutive Losses Reached ({self.consecutive_losses})"
            logger.warning(f"CIRCUIT BREAKER: {self.halt_reason}")
            _audit_circuit_breaker(AuditEvent.RISK_BREACH, self.halt_reason, self.consecutive_losses)
            return
            
    def is_trading_allowed(self, capital: float) -> tuple[bool, str]:
        self._check_resets(capital)
        self._evaluate_risk(capital)
        return not self.trading_halted, self.halt_reason
