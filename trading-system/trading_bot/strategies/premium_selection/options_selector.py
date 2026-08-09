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
from datetime import date, datetime, timedelta
from typing import Literal, Any
import math
import logging
import os
import json

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


def calculate_option_price(spot: float, strike: float, days_to_expiry: float, vol: float = 0.15, option_type: str = "CE") -> float:
    """Black-Scholes theoretical premium — same d1/d2 machinery as
    calculate_greeks() above, added alongside it rather than duplicated,
    since that function computes delta/theta but not the price itself.

    Used by the Production Strategy Validation Harness
    (validation_harness/) to synthesize a plausible premium series from
    historical index OHLCV, since this repository has no real historical
    option-premium data — see validation_harness/premium_simulator.py.
    Also directly usable live as a sanity-check against a fetched
    premium, though nothing currently calls it for that purpose.
    """
    t = max(days_to_expiry / 365.0, 0.0001)
    r = 0.07  # 7% risk-free rate, matching calculate_greeks()
    d1 = (math.log(spot / strike) + (r + 0.5 * vol**2) * t) / (vol * math.sqrt(t))
    d2 = d1 - vol * math.sqrt(t)

    if option_type == "CE":
        price = spot * norm_cdf(d1) - strike * math.exp(-r * t) * norm_cdf(d2)
    else:
        price = strike * math.exp(-r * t) * norm_cdf(-d2) - spot * norm_cdf(-d1)

    return max(price, 0.05)  # a premium can't price below one tick


_LOT_SIZE_CACHE: dict = {}
_LOT_SIZE_CACHE_TTL_S = 300.0  # re-check every 5 minutes


def _get_dynamic_lot_size(instrument: str, default_lot_size: int) -> int:
    """Reads lot size dynamically from the active broker.

    Root-cause fix (Medium audit finding): this used to be wrapped in
    @lru_cache(maxsize=128), which caches forever for the life of the
    process — any intraday lot-size revision from the exchange (has
    happened historically for NIFTY/BANKNIFTY) would be silently
    ignored until the next restart. Replaced with a time-based cache:
    still avoids hitting the broker/settings.json on every call (this
    runs once per option-contract selection, not per tick), but
    re-checks every _LOT_SIZE_CACHE_TTL_S seconds instead of never.
    """
    import time
    cache_key = (instrument, default_lot_size)
    cached = _LOT_SIZE_CACHE.get(cache_key)
    now = time.monotonic()
    if cached is not None and (now - cached[1]) < _LOT_SIZE_CACHE_TTL_S:
        return cached[0]

    value = _fetch_dynamic_lot_size(instrument, default_lot_size)
    _LOT_SIZE_CACHE[cache_key] = (value, now)
    return value


def _fetch_dynamic_lot_size(instrument: str, default_lot_size: int) -> int:
    """Uncached lookup — always does the real broker/settings.json read."""
    try:
        from brokers.broker_factory import BrokerFactory
        broker = BrokerFactory.get_active_broker()
        if broker:
            # Reconstruct broker symbol format: NSE:NIFTY50-INDEX
            sym = instrument.upper()
            if sym == "NIFTY": sym = "NIFTY50"
            if sym == "BANKNIFTY": sym = "NIFTYBANK"
            
            exch = "BSE" if sym == "SENSEX" else "NSE"
            broker_sym = f"{exch}:{sym}-INDEX"
            
            return broker.get_lot_size(broker_sym)
    except Exception as e:
        logger.warning("Failed to fetch dynamic lot size from broker for %s: %s", instrument, e)
        
    # Read from settings.json as fallback.
    # Root-cause fix (Medium audit finding): standardized on
    # trading-system/config/settings.json (the file every other real
    # consumer treats as canonical) instead of the legacy
    # trading-system/settings.json this used to read — see
    # shared/lot_size_updater.py and brokers/base_broker.py for the same fix.
    try:
        import os
        import json
        settings_path = os.path.join(os.path.dirname(__file__), "..", "..", "..", "config", "settings.json")
        if os.path.exists(settings_path):
            with open(settings_path, 'r') as f:
                settings = json.load(f)
                lot_sizes = settings.get("lot_sizes", {})
                for base_name, lot in lot_sizes.items():
                    if base_name in instrument.upper():
                        return lot
    except Exception:
        pass
        
    return default_lot_size


# ──────────────────────────────────────────────
# Instrument configuration registry
# ──────────────────────────────────────────────
INSTRUMENT_CONFIG = {
    # expiry_day verified 2026-08-03 against Fyers' live NSE_FO/BSE_FO symbol
    # master (public.fyers.in/sym_details/) — NSE consolidated weekly index
    # options expiry to Tuesday (NIFTY/BANKNIFTY/FINNIFTY); BSE's SENSEX
    # weekly expiry is Thursday. The previous Thu/Wed/Fri values were stale
    # and caused every computed expiry date (and therefore every option
    # symbol) to reference a non-existent contract.
    "NIFTY": {
        "lot_size": 65,
        "strike_step": 50,
        "expiry_day": 1,        # Tuesday (0=Mon, 1=Tue, ...)
        "exchange": "NSE",
        "index": True,
    },
    "BANKNIFTY": {
        "lot_size": 30,
        "strike_step": 100,
        "expiry_day": 1,        # Tuesday
        "exchange": "NSE",
        "index": True,
    },
    "SENSEX": {
        "lot_size": 20,
        "strike_step": 100,
        "expiry_day": 3,        # Thursday
        "exchange": "BSE",
        "index": True,
    },
    "FINNIFTY": {
        "lot_size": 60,
        "strike_step": 50,
        "expiry_day": 1,        # Tuesday
        "exchange": "NSE",
        "index": True,
    },
}


#: Hard bounds on how far from ATM a selected strike may sit, in strikes.
#: 0 = ATM. Negative would be OTM, which this system never buys — see the
#: clamp in select_option(). MAX_ITM_STRIKES=2 is reserved for the 0DTE
#: Greeks Guard's emergency deep-ITM shift (protects delta/theta on
#: expiry-day entries after 2 PM); ordinary entries use 0 or 1.
MIN_ITM_STRIKES = 0
MAX_ITM_STRIKES = 2


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


def _next_expiry(instrument: str, from_date: date | None = None, broker: Any = None) -> date:
    """
    Find the next weekly expiry date dynamically from Broker API if connected,
    or fallback to current exchange specifications.
    """
    today = from_date or date.today()
    
    # 1. Dynamic Broker Lookup
    if broker and hasattr(broker, 'get_expiry_dates'):
        try:
            expiries = broker.get_expiry_dates(instrument)
            if expiries:
                for exp in expiries:
                    exp_date = datetime.strptime(exp, "%Y-%m-%d").date() if isinstance(exp, str) else exp
                    if exp_date >= today:
                        return exp_date
        except Exception:
            pass

    # 2. Fallback to Exchange Specifications
    cfg = INSTRUMENT_CONFIG.get(instrument.upper(), INSTRUMENT_CONFIG["NIFTY"])
    expiry_weekday = cfg["expiry_day"]

    days_ahead = expiry_weekday - today.weekday()
    if days_ahead < 0:
        days_ahead += 7
    return today + timedelta(days=days_ahead)


def _round_to_strike(price: float, step: int) -> int:
    """Round price to nearest strike step."""
    return int(round(price / step) * step)


# Fyers uses a single-character month code for non-monthly (weekly) option
# symbols: 1-9 for Jan-Sep, then O/N/D for Oct/Nov/Dec.
_WEEKLY_MONTH_CODE = {
    1: "1", 2: "2", 3: "3", 4: "4", 5: "5", 6: "6",
    7: "7", 8: "8", 9: "9", 10: "O", 11: "N", 12: "D",
}


def _is_last_expiry_weekday_of_month(expiry: date) -> bool:
    """True if `expiry` is the last occurrence of its weekday in its month
    (i.e. the monthly contract, not a weekly one)."""
    return (expiry + timedelta(days=7)).month != expiry.month


def _build_symbol(instrument: str, expiry: date, strike: int, option_type: str) -> str:
    """
    Build a Fyers-compatible option symbol, matching the real NSE_FO/BSE_FO
    symbol master convention (verified 2026-08-03):

    Monthly contract (last occurrence of the expiry weekday in its month):
        {EXCH}:{INSTRUMENT}{YY}{MMM}{STRIKE}{CE/PE}   e.g. NSE:NIFTY26AUG17850CE

    Weekly contract (any other occurrence):
        {EXCH}:{INSTRUMENT}{YY}{M}{DD}{STRIKE}{CE/PE} e.g. NSE:NIFTY2680418500CE
        where {M} is a single-char month code (1-9, O, N, D).
    """
    cfg = INSTRUMENT_CONFIG.get(instrument.upper(), INSTRUMENT_CONFIG["NIFTY"])
    exchange = cfg["exchange"]
    # Canonical instrument key (not the caller's raw string) — keeps the
    # symbol correct even if the caller passed a variant like "NIFTY50".
    canonical = instrument.upper() if instrument.upper() in INSTRUMENT_CONFIG else "NIFTY"

    yy = expiry.strftime("%y")

    if _is_last_expiry_weekday_of_month(expiry):
        mon = expiry.strftime("%b").upper()
        return f"{exchange}:{canonical}{yy}{mon}{strike}{option_type}"

    m  = _WEEKLY_MONTH_CODE[expiry.month]
    dd = expiry.strftime("%d")
    return f"{exchange}:{canonical}{yy}{m}{dd}{strike}{option_type}"


def select_option(
    instrument: str,
    spot_price: float,
    direction: Literal["CE", "PE"],
    itm_strikes: int = 0,
    from_date: date | None = None,
    as_of: "datetime | None" = None,
) -> OptionContract:
    """
    Select the best option contract for the given direction.

    Parameters
    ----------
    instrument  : "NIFTY", "BANKNIFTY", "SENSEX", etc.
    spot_price  : current underlying spot price
    direction   : "CE" for Call, "PE" for Put
    itm_strikes : 0 = ATM (preferred), 1 = 1 strike ITM (liquidity fallback).
                  Clamped to [MIN_ITM_STRIKES, MAX_ITM_STRIKES] — see below.
    from_date   : override today's date (for backtesting)
    as_of       : the moment this selection is being made. Defaults to
                  `datetime.now()`, which is correct live and is the
                  historical behaviour.

                  It exists because the Greeks Guard below reads a
                  *clock*, not just a date, and a backtest has no
                  business consulting the machine's. Measured 2026-08-10:
                  replaying 2025-06-10 — a genuine 0 DTE session — the
                  guard computed `days_to_expiry = -426` from the wall
                  clock and could never fire, so the 0DTE-after-14:00
                  deep-ITM protection has never once been exercised in
                  any backtest in this repository. Worse, had only the
                  date been corrected, the guard would then have keyed
                  off the real-world HOUR, making backtest output depend
                  on what time of day the backtest was run.

                  Passing a simulated timestamp fixes both. The default
                  is left as the wall clock deliberately: switching it on
                  unconditionally would start firing the guard inside
                  historical replays and silently change published
                  results. The validation harness opts in via
                  `RealismConfig.simulated_clock`.

    Returns
    -------
    OptionContract with all details needed to place the order.
    """
    # Hard architectural guarantee, not a caller convention: this system
    # only ever buys ATM or ITM option premium, never OTM. A negative
    # itm_strikes would push the strike the wrong side of spot (OTM for
    # both CE and PE, given the sign convention below), and an
    # unreasonably large positive value would go far deeper ITM than "a
    # little" ever means. Clamping here — rather than trusting every
    # current and future caller to only ever pass 0 or 1 — makes an OTM
    # entry structurally impossible regardless of what any config,
    # strategy, or future call site passes in.
    itm_strikes = max(MIN_ITM_STRIKES, min(int(itm_strikes), MAX_ITM_STRIKES))

    cfg = INSTRUMENT_CONFIG.get(instrument.upper(), INSTRUMENT_CONFIG["NIFTY"])
    step = cfg["strike_step"]
    lot_size = _get_dynamic_lot_size(instrument.upper(), cfg["lot_size"])

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
    now = as_of if as_of is not None else datetime.now()
    days_to_expiry = (expiry - now.date()).days
    if days_to_expiry == 0 and now.hour >= 14:
        # Expiry day after 2 PM -> Theta is extreme, Delta drops
        # Force going DEEP ITM to protect Delta and minimize Theta decay
        strike = atm_strike - (2 * step) if direction == "CE" else atm_strike + (2 * step)
        symbol = _build_symbol(instrument, expiry, strike, direction)
        itm_strikes = 2
        logger.warning("Greeks Guard Triggered: 0DTE after 2 PM. Forced Deep ITM (%s) to avoid Theta decay trap.", symbol)

        # Root-cause fix (Medium audit finding): the shift used to be
        # applied blindly with no check that it actually achieved its
        # stated goal (protect delta, reduce theta decay) for the NEW
        # strike. Recompute Greeks for the shifted strike and warn if
        # the delta protection this guard exists for didn't actually
        # materialize (e.g. a very tight strike_step leaving the "deep
        # ITM" strike still close to the money).
        greeks = calculate_greeks(spot_price, strike, days_to_expiry, option_type=direction)
        logger.info("Post-shift Greeks for %s -> Delta: %.2f | Theta: %.2f", symbol, greeks["delta"], greeks["theta"])
        if abs(greeks["delta"]) < 0.7:
            logger.warning(
                "Greeks Guard shift did not achieve the expected deep-ITM delta protection for %s "
                "(Delta: %.2f, expected >= 0.70 in magnitude) — strike_step for %s may be too small "
                "relative to spot to reach deep ITM with a 2-strike offset.",
                symbol, greeks["delta"], instrument,
            )
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
    default = INSTRUMENT_CONFIG.get(instrument.upper(), {}).get("lot_size", 25)
    return _get_dynamic_lot_size(instrument.upper(), default)


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
