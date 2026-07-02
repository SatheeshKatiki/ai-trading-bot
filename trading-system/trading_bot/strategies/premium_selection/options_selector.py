"""Options Selector — ATM/ITM Strike, Expiry, and Lot Size Engine.

Selects the correct option contract for execution:
  - Instrument: NIFTY, BANKNIFTY, SENSEX
  - Strike: ATM or slight ITM (high liquidity)
  - Expiry: nearest weekly expiry (Thursday for NIFTY/BANKNIFTY)
  - Symbol: builds the exact Fyers-compatible option symbol string
  - Lot size: enforced per instrument
"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Literal
import math
import logging

logger = logging.getLogger(__name__)

# Basic Black-Scholes Math Helper
def norm_cdf(x: float) -> float:
    return (1.0 + math.erf(x / math.sqrt(2.0))) / 2.0

def norm_pdf(x: float) -> float:
    return math.exp(-0.5 * x * x) / math.sqrt(2.0 * math.pi)

def calculate_greeks(spot: float, strike: float, days_to_expiry: float, vol: float = 0.15, option_type: str = "CE") -> dict:
    t = max(days_to_expiry / 365.0, 0.0001)
    r = 0.07 # 7% risk-free rate
    d1 = (math.log(spot / strike) + (r + 0.5 * vol**2) * t) / (vol * math.sqrt(t))
    d2 = d1 - vol * math.sqrt(t)
    
    if option_type == "CE":
        delta = norm_cdf(d1)
        theta = (-(spot * norm_pdf(d1) * vol) / (2 * math.sqrt(t)) - r * strike * math.exp(-r * t) * norm_cdf(d2)) / 365.0
    else:
        delta = norm_cdf(d1) - 1.0
        theta = (-(spot * norm_pdf(d1) * vol) / (2 * math.sqrt(t)) + r * strike * math.exp(-r * t) * norm_cdf(-d2)) / 365.0
        
    return {"delta": delta, "theta": theta}


# ──────────────────────────────────────────────
# Instrument configuration registry
# ──────────────────────────────────────────────
INSTRUMENT_CONFIG = {
    "NIFTY": {
        "lot_size": 65,
        "strike_step": 50,
        "expiry_day": 3,        # Thursday (0=Mon, 3=Thu)
        "exchange": "NSE",
        "index": True,
    },
    "BANKNIFTY": {
        "lot_size": 15,
        "strike_step": 100,
        "expiry_day": 2,        # Wednesday
        "exchange": "NSE",
        "index": True,
    },
    "SENSEX": {
        "lot_size": 10,
        "strike_step": 100,
        "expiry_day": 4,        # Friday
        "exchange": "BSE",
        "index": True,
    },
    "FINNIFTY": {
        "lot_size": 40,
        "strike_step": 50,
        "expiry_day": 1,        # Tuesday
        "exchange": "NSE",
        "index": True,
    },
}


@dataclass
class OptionContract:
    """Represents a selected option contract."""
    instrument: str
    strike: int
    option_type: Literal["CE", "PE"]
    expiry: date
    lot_size: int
    symbol: str                 # Fyers-compatible symbol string
    itm_offset: int = 0        # 0 = ATM, 1 = 1 strike ITM, etc.

    @property
    def is_call(self) -> bool:
        return self.option_type == "CE"

    @property
    def is_put(self) -> bool:
        return self.option_type == "PE"


def _next_expiry(instrument: str, from_date: date | None = None) -> date:
    """Find the next weekly expiry date for the given instrument."""
    cfg = INSTRUMENT_CONFIG.get(instrument.upper(), INSTRUMENT_CONFIG["NIFTY"])
    expiry_weekday = cfg["expiry_day"]
    today = from_date or date.today()

    # Find next occurrence of expiry_weekday
    days_ahead = expiry_weekday - today.weekday()
    if days_ahead <= 0:     # Target day already passed this week
        days_ahead += 7
    return today + timedelta(days=days_ahead)


def _round_to_strike(price: float, step: int) -> int:
    """Round price to nearest strike step."""
    return int(round(price / step) * step)


def _build_symbol(instrument: str, expiry: date, strike: int, option_type: str) -> str:
    """
    Build Fyers-compatible option symbol.

    Format: NSE:NIFTY{YY}{MMM}{DD}{STRIKE}{CE/PE}
    Example: NSE:NIFTY25MAY2222400CE
    """
    cfg = INSTRUMENT_CONFIG.get(instrument.upper(), INSTRUMENT_CONFIG["NIFTY"])
    exchange = cfg["exchange"]

    yy  = expiry.strftime("%y")          # e.g. "25"
    mon = expiry.strftime("%b").upper()  # e.g. "MAY"
    dd  = expiry.strftime("%d")          # e.g. "22"

    return f"{exchange}:{instrument.upper()}{yy}{mon}{dd}{strike}{option_type}"


def select_option(
    instrument: str,
    spot_price: float,
    direction: Literal["CE", "PE"],
    itm_strikes: int = 0,
    from_date: date | None = None,
) -> OptionContract:
    """
    Select the best option contract for the given direction.

    Parameters
    ----------
    instrument  : "NIFTY", "BANKNIFTY", "SENSEX", etc.
    spot_price  : current underlying spot price
    direction   : "CE" for Call, "PE" for Put
    itm_strikes : 0 = ATM, 1 = 1 strike ITM (recommended for liquidity), 2 = 2 strikes ITM
    from_date   : override today's date (for backtesting)

    Returns
    -------
    OptionContract with all details needed to place the order.
    """
    cfg = INSTRUMENT_CONFIG.get(instrument.upper(), INSTRUMENT_CONFIG["NIFTY"])
    step = cfg["strike_step"]
    lot_size = cfg["lot_size"]

    # ATM strike
    atm_strike = _round_to_strike(spot_price, step)

    # Apply ITM offset: for CE → go lower (ITM call), for PE → go higher (ITM put)
    if direction == "CE":
        strike = atm_strike - (itm_strikes * step)
    else:
        strike = atm_strike + (itm_strikes * step)

    expiry = _next_expiry(instrument.upper(), from_date)
    symbol = _build_symbol(instrument, expiry, strike, direction)

    # ── GREEKS GUARD (Delta/Theta Filter) ──
    from datetime import datetime
    now = datetime.now()
    days_to_expiry = (expiry - now.date()).days
    if days_to_expiry == 0 and now.hour >= 14:
        # Expiry day after 2 PM -> Theta is extreme, Delta drops
        # Force going DEEP ITM to protect Delta and minimize Theta decay
        strike = atm_strike - (2 * step) if direction == "CE" else atm_strike + (2 * step)
        symbol = _build_symbol(instrument, expiry, strike, direction)
        itm_strikes = 2
        logger.warning("Greeks Guard Triggered: 0DTE after 2 PM. Forced Deep ITM (%s) to avoid Theta decay trap.", symbol)
    else:
        greeks = calculate_greeks(spot_price, strike, days_to_expiry, option_type=direction)
        logger.info("Computed Greeks for %s -> Delta: %.2f | Theta: %.2f", symbol, greeks["delta"], greeks["theta"])

    return OptionContract(
        instrument=instrument.upper(),
        strike=strike,
        option_type=direction,
        expiry=expiry,
        lot_size=lot_size,
        symbol=symbol,
        itm_offset=itm_strikes,
    )


def get_lot_size(instrument: str) -> int:
    """Return the fixed lot size for a given instrument."""
    return INSTRUMENT_CONFIG.get(instrument.upper(), {}).get("lot_size", 65)


def calculate_lots(
    capital: float,
    option_premium: float,
    instrument: str,
    risk_pct: float = 0.02,
) -> int:
    """
    Calculate how many lots to buy given available capital and risk constraint.

    Parameters
    ----------
    capital        : available trading capital
    option_premium : LTP of the option contract
    instrument     : instrument name
    risk_pct       : maximum % of capital to risk on this trade

    Returns
    -------
    int: number of lots (minimum 1)
    """
    lot_size = get_lot_size(instrument)
    cost_per_lot = option_premium * lot_size
    if cost_per_lot <= 0:
        return 1

    max_capital_to_risk = capital * risk_pct
    lots = int(max_capital_to_risk / cost_per_lot)
    return max(1, lots)
