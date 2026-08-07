import logging
from datetime import date, datetime

import pytz

from drl.marl.base_agent import BaseAgent

logger = logging.getLogger(__name__)

# Capital Protection Mode is documented as a per-SESSION rule ("stop
# trading for the session"), so its expiry must roll over at midnight IST
# — the market this system trades — not at midnight in whatever timezone
# the host happens to run in. Same rationale and same pattern as
# shared/risk/manager.py's _IST/_today_ist(), reused deliberately rather
# than inventing a second convention.
_IST = pytz.timezone("Asia/Kolkata")


def _today_ist() -> date:
    return datetime.now(_IST).date()

class RiskAgent(BaseAgent):
    """
    The Risk Manager Agent (The Shield) — Professional Edition.
    
    Monitors global PnL, drawdowns, and portfolio heat.
    Has the authority to veto the Execution Agent and force emergency SQUARE_OFF.
    
    Professional addition: Capital Protection Mode
    - After 2 consecutive losing trades, reduce risk appetite
    - After max daily loss, stop trading for the day
    """
    
    def __init__(self, max_drawdown_pct: float = 2.0, take_profit_pct: float = 5.0):
        super().__init__("RiskAgent_Shield")
        self.max_drawdown_pct = max_drawdown_pct
        self.take_profit_pct = take_profit_pct
        
        # Capital Protection Mode tracking
        self._consecutive_losses = 0
        self._last_trade_result = None  # "WIN" or "LOSS"
        self._capital_protection_mode = False
        # Trading session this streak belongs to. Capital Protection is a
        # per-session rule (see record_trade_result's docstring), so the
        # streak must not outlive the day that produced it.
        self._session_date: date = _today_ist()

    def _reset_daily_if_needed(self) -> None:
        """Expire Capital Protection Mode at the start of a new IST
        trading day.

        Root-cause fix (found and measured 2026-08-07): without this, the
        3-consecutive-loss block was PERMANENT, not per-session as its own
        docstring states. The deadlock chain: 3 losses ->
        get_position_size_multiplier() returns 0.0 ->
        marl_strategy.generate_signals() blocks every new entry -> no
        entries means no closes -> record_trade_result() is never called
        again -> the streak can never reach the win that would clear it.
        Measured impact over a 123-day validation window: MARL_Ultra
        traded on 14 days, all in February, and never again after
        2026-02-19 — silently dead for ~104 of 123 days while still
        looking healthy at the process level.

        Deliberately called from the READ path
        (get_position_size_multiplier) as well as the write path
        (record_trade_result). Read-path placement is what actually breaks
        the deadlock: once entries are blocked the write path is
        unreachable by construction, so a write-only reset would never
        fire. This mirrors shared/risk/manager.py::RiskManager, which
        likewise checks on both can_trade() and record_trade().

        The protection itself is unchanged in strength — 2 losses still
        halves size, 3 still stops trading — it simply expires with the
        session it was earned in, exactly as documented.
        """
        today = _today_ist()
        if today != self._session_date:
            if self._consecutive_losses > 0:
                logger.info(
                    "[RiskAgent] New trading session (%s) — clearing Capital "
                    "Protection state from %s (%d consecutive losses).",
                    today, self._session_date, self._consecutive_losses,
                )
            self._session_date = today
            self._consecutive_losses = 0
            self._capital_protection_mode = False
            self._last_trade_result = None

    def record_trade_result(self, pnl: float) -> None:
        """
        Call this after each trade closes to track consecutive losses.
        Professional rule: After 2 consecutive losses, switch to half-size mode.
        After 3 consecutive losses, stop trading for the session.
        """
        self._reset_daily_if_needed()
        if pnl > 0:
            self._consecutive_losses = 0
            self._capital_protection_mode = False
            self._last_trade_result = "WIN"
            logger.info("[RiskAgent] Trade WIN. Consecutive losses reset to 0.")
        else:
            self._consecutive_losses += 1
            self._last_trade_result = "LOSS"
            logger.warning(f"[RiskAgent] Trade LOSS. Consecutive losses: {self._consecutive_losses}")
            
            if self._consecutive_losses >= 2:
                self._capital_protection_mode = True
                logger.warning("[RiskAgent] CAPITAL PROTECTION MODE ACTIVATED. Reducing position size.")
        
    def get_position_size_multiplier(self) -> float:
        """
        Returns position size multiplier based on current risk state.
        - Normal: 1.0 (full size)
        - After 2 consecutive losses: 0.5 (half size)
        - After 3+ consecutive losses: 0.0 (stop trading)

        Checks for a session rollover first — this is the read path that
        actually releases Capital Protection Mode, since once it engages
        the write path (record_trade_result) becomes unreachable. See
        _reset_daily_if_needed().
        """
        self._reset_daily_if_needed()
        if self._consecutive_losses >= 3:
            logger.warning("[RiskAgent] 3+ consecutive losses. Position size: 0 (trading stopped).")
            return 0.0
        elif self._consecutive_losses >= 2:
            logger.warning("[RiskAgent] 2 consecutive losses. Position size reduced to 50%.")
            return 0.5
        return 1.0
        
    def analyze(self, current_pnl_pct: float) -> dict:
        """
        Analyzes the current open portfolio state.
        Returns a dictionary indicating if an emergency override is required.
        """
        if not self.is_active:
            return {"override": False}
            
        risk_plan = {
            "override": False,
            "action": None,
            "reason": "",
            "position_size_multiplier": self.get_position_size_multiplier()
        }
        
        # Max Drawdown Hit - Cut losses instantly
        if current_pnl_pct <= -self.max_drawdown_pct:
            risk_plan["override"] = True
            risk_plan["action"] = "SQUARE_OFF"
            risk_plan["reason"] = f"Max Drawdown Hit ({current_pnl_pct:.2f}%). Emergency Square Off."
            logger.warning(risk_plan["reason"])
            
        # Target Profit Hit - Book profits instantly
        elif current_pnl_pct >= self.take_profit_pct:
            risk_plan["override"] = True
            risk_plan["action"] = "SQUARE_OFF"
            risk_plan["reason"] = f"Target Profit Hit ({current_pnl_pct:.2f}%). Auto Booking."
            logger.info(risk_plan["reason"])
            
        # Capital Protection Mode - block new trades if 3+ consecutive losses
        elif self._consecutive_losses >= 3:
            risk_plan["override"] = True
            risk_plan["action"] = "HOLD"
            risk_plan["reason"] = f"Capital Protection Mode: {self._consecutive_losses} consecutive losses. Trading blocked."
            logger.warning(risk_plan["reason"])
            
        return risk_plan
