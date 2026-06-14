import logging
from datetime import datetime

logger = logging.getLogger(__name__)

class PortfolioRiskEngine:
    """
    Phase 7: Portfolio Risk Engine
    Provides global circuit breakers and drawdown limits.
    Operates independently of individual strategy risk.
    """
    
    def __init__(self, 
                 max_daily_dd_pct: float = 5.0, 
                 max_weekly_dd_pct: float = 10.0,
                 max_consecutive_losses: int = 3):
        self.max_daily_dd_pct = max_daily_dd_pct
        self.max_weekly_dd_pct = max_weekly_dd_pct
        self.max_consecutive_losses = max_consecutive_losses
        
        self.daily_pnl = 0.0
        self.weekly_pnl = 0.0
        self.peak_capital_daily = 0.0
        self.peak_capital_weekly = 0.0
        
        self.consecutive_losses = 0
        self.trading_halted = False
        self.halt_reason = ""
        
        self.last_reset_day = datetime.now().date()
        self.last_reset_week = datetime.now().isocalendar()[1]
        
    def _check_resets(self, capital: float):
        now = datetime.now()
        current_day = now.date()
        current_week = now.isocalendar()[1]
        
        if current_day != self.last_reset_day:
            self.daily_pnl = 0.0
            self.peak_capital_daily = capital
            self.last_reset_day = current_day
            # Only lift halt if it was a daily DD or daily consecutive loss halt
            if "Daily" in self.halt_reason or "Consecutive Losses" in self.halt_reason:
                self.trading_halted = False
                self.halt_reason = ""
                self.consecutive_losses = 0
                
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
        else:
            self.consecutive_losses = 0
            
        self.daily_pnl += realized_pnl
        self.weekly_pnl += realized_pnl
        
        if capital > self.peak_capital_daily:
            self.peak_capital_daily = capital
        if capital > self.peak_capital_weekly:
            self.peak_capital_weekly = capital
            
        self._evaluate_risk(capital)
        
    def _evaluate_risk(self, capital: float):
        if self.trading_halted:
            return
            
        # Daily Drawdown
        if self.peak_capital_daily > 0:
            daily_dd_pct = ((self.peak_capital_daily - capital) / self.peak_capital_daily) * 100
            if daily_dd_pct >= self.max_daily_dd_pct:
                self.trading_halted = True
                self.halt_reason = f"Max Daily Drawdown Reached ({daily_dd_pct:.2f}%)"
                logger.warning(f"CIRCUIT BREAKER: {self.halt_reason}")
                return
                
        # Weekly Drawdown
        if self.peak_capital_weekly > 0:
            weekly_dd_pct = ((self.peak_capital_weekly - capital) / self.peak_capital_weekly) * 100
            if weekly_dd_pct >= self.max_weekly_dd_pct:
                self.trading_halted = True
                self.halt_reason = f"Max Weekly Drawdown Reached ({weekly_dd_pct:.2f}%)"
                logger.warning(f"CIRCUIT BREAKER: {self.halt_reason}")
                return
                
        # Consecutive Losses
        if self.consecutive_losses >= self.max_consecutive_losses:
            self.trading_halted = True
            self.halt_reason = f"Max Consecutive Losses Reached ({self.consecutive_losses})"
            logger.warning(f"CIRCUIT BREAKER: {self.halt_reason}")
            return
            
    def is_trading_allowed(self, capital: float) -> tuple[bool, str]:
        self._check_resets(capital)
        self._evaluate_risk(capital)
        return not self.trading_halted, self.halt_reason
