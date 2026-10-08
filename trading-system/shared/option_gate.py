"""
=============================================================================
  SHARED OPTION CONFLUENCE GATE (Universal Option Chart Gatekeeper)
=============================================================================
Perspective : 30+ Years Floor Trader & Systematic Options Architect
Mission     : Validates whether the specific option contract (CE/PE) confirms
              the underlying Spot breakout BEFORE order execution.

Core Pillars:
  1. Option VWAP Gate (LTP >= Option VWAP / ATP)
     - Never buy a Call or Put trading below its intraday institutional average.
       Trading below VWAP signals option writer/seller control and theta decay trap.
  2. Option Liquidity & Spread Protection (Spread % <= max_spread_pct)
     - Prevents getting trapped in wide-spread, illiquid strikes with immediate slippage.
  3. Market Open Warmup Guard (09:15 - 09:18 IST)
     - The first 3 minutes of the trading day have low volume; avoids false VWAP rejections.
  4. Local Option Momentum Confirmation (Optional candle check)
     - Validates that option price is not in a free-fall or severe breakdown.

STRICT ISOLATION GUARANTEE:
  - Plug-and-play architecture for any strategy in the ecosystem.
  - Active by default for 'ema9_rsi_momentum'.
  - Other strategies (SMC, Momentum, Structure Break, etc.) are BYPASSED with
    passed=True and status='STRATEGY_BYPASS' unless explicitly enabled in settings.
  - ZERO IMPACT on other strategies.
=============================================================================
"""

from __future__ import annotations

import datetime as _dt
import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

logger = logging.getLogger("OptionGate")

# Default Configuration Constants
DEFAULT_MAX_SPREAD_PCT: float = 1.2        # Max acceptable (Ask - Bid) / Ask %
DEFAULT_REQUIRE_ABOVE_VWAP: bool = True     # Require Option LTP >= Option VWAP
DEFAULT_MIN_VOLUME: int = 50               # Minimum traded volume for VWAP reliability
DEFAULT_WARMUP_MINUTES: int = 3            # 09:15 to 09:18 IST warmup window
DEFAULT_ENABLED_STRATEGIES = ("ema9_rsi_momentum",)


@dataclass(frozen=True)
class OptionGateResult:
    """The structured result of the option chart confluence evaluation."""

    passed: bool
    status: str              # "PASS", "REJECT", "WARMUP_BYPASS", "STRATEGY_BYPASS", "DATA_UNAVAILABLE_BYPASS", "DISABLED"
    reason: str              # Human-readable explanation
    ltp: float
    vwap: Optional[float]
    spread_pct: Optional[float]
    volume: Optional[int]
    strike: Optional[float] = None
    opt_type: Optional[str] = None
    details: Optional[Dict[str, Any]] = None

    def __str__(self) -> str:
        verdict = "PASS" if self.passed else "REJECT"
        return f"[{verdict} - {self.status}] {self.reason}"


def is_market_opening_warmup(current_time: Optional[_dt.datetime] = None, warmup_minutes: int = DEFAULT_WARMUP_MINUTES) -> bool:
    """Returns True if current time is within the market opening warmup window (09:15 - 09:15+warmup_minutes IST)."""
    try:
        import pytz
        IST = pytz.timezone("Asia/Kolkata")
    except Exception:
        IST = None

    if current_time is None:
        current_time = _dt.datetime.now(IST) if IST else _dt.datetime.now()
    elif current_time.tzinfo is not None and IST:
        current_time = current_time.astimezone(IST)

    open_min = 9 * 60 + 15
    warmup_end_min = open_min + warmup_minutes
    cur_min = current_time.hour * 60 + current_time.minute
    return open_min <= cur_min < warmup_end_min


def calculate_option_vwap(
    opt_info: Dict[str, Any],
    option_candles: Optional[List[Dict[str, Any]]] = None,
) -> Optional[float]:
    """Extract or calculate the option contract's intraday VWAP / ATP."""
    # 1. Direct broker ATP / VWAP field from quote
    direct_vwap = opt_info.get("vwap") or opt_info.get("atp")
    if direct_vwap is not None:
        try:
            v = float(direct_vwap)
            if v > 0:
                return round(v, 2)
        except (TypeError, ValueError):
            pass

    # 2. Derive from intraday option candles if provided
    if option_candles and len(option_candles) > 0:
        total_vol = 0
        total_pv = 0.0
        for c in option_candles:
            vol = int(c.get("volume") or 0)
            typical = (float(c.get("high") or c.get("close", 0)) +
                       float(c.get("low") or c.get("close", 0)) +
                       float(c.get("close", 0))) / 3.0
            if vol > 0 and typical > 0:
                total_vol += vol
                total_pv += (typical * vol)
            elif typical > 0:
                total_vol += 1
                total_pv += typical

        if total_vol > 0 and total_pv > 0:
            return round(total_pv / total_vol, 2)

    # 3. Fallback to Day Typical Price from quote if high/low/close are available
    high = opt_info.get("high")
    low = opt_info.get("low")
    close = opt_info.get("ltp") or opt_info.get("close")
    if high is not None and low is not None and close is not None:
        try:
            h = float(high)
            l = float(low)
            c = float(close)
            if h > 0 and l > 0 and c > 0:
                return round((h + l + c) / 3.0, 2)
        except (TypeError, ValueError):
            pass

    return None


def validate_option_entry(
    symbol: str,
    direction: str,
    opt_info: Dict[str, Any],
    strategy_name: str = "ema9_rsi_momentum",
    settings: Optional[Dict[str, Any]] = None,
    option_candles: Optional[List[Dict[str, Any]]] = None,
    current_time: Optional[_dt.datetime] = None,
) -> OptionGateResult:
    """
    Universal Option Chart Confluence Gatekeeper.
    
    Validates whether the option contract confirms the spot breakout.
    Guarantees strict isolation: if strategy_name is not in enabled strategies,
    it returns passed=True immediately with status 'STRATEGY_BYPASS'.
    """
    settings = settings or {}
    gate_cfg = settings.get("option_chart_gate", {})
    
    # Check if global toggle disabled
    is_enabled = gate_cfg.get("enabled", True)
    if not is_enabled:
        return OptionGateResult(
            passed=True,
            status="DISABLED",
            reason="Option chart gate is globally disabled.",
            ltp=float(opt_info.get("ltp") or 0.0),
            vwap=None,
            spread_pct=None,
            volume=None,
            strike=opt_info.get("strike"),
            opt_type=opt_info.get("type"),
        )

    # Strict Isolation: Check strategy opt-in
    enabled_strats = gate_cfg.get("enabled_strategies", DEFAULT_ENABLED_STRATEGIES)
    global_override = gate_cfg.get("global_enable_all_strategies", False)
    
    # Also support per-strategy config flag: e.g. settings.get(f"{strategy_name}_option_gate_enabled")
    strat_specific_flag = settings.get(f"{strategy_name}_enable_option_gate")

    is_strategy_targeted = (strategy_name in enabled_strats) or global_override or (strat_specific_flag is True)
    if not is_strategy_targeted:
        return OptionGateResult(
            passed=True,
            status="STRATEGY_BYPASS",
            reason=f"Option gate bypassed for strategy '{strategy_name}' (strict isolation guarantee).",
            ltp=float(opt_info.get("ltp") or 0.0),
            vwap=None,
            spread_pct=None,
            volume=None,
            strike=opt_info.get("strike"),
            opt_type=opt_info.get("type"),
        )

    # Extract leg details
    ltp = float(opt_info.get("ltp") or 0.0)
    bid = float(opt_info.get("bid") or 0.0)
    ask = float(opt_info.get("ask") or 0.0)
    strike = opt_info.get("strike")
    opt_type = opt_info.get("type") or opt_info.get("opt_type")
    volume = opt_info.get("volume")
    vol_int = int(volume) if volume is not None else 0

    if ltp <= 0:
        return OptionGateResult(
            passed=False,
            status="REJECT",
            reason="Option contract has no valid tradeable LTP.",
            ltp=0.0,
            vwap=None,
            spread_pct=None,
            volume=vol_int,
            strike=strike,
            opt_type=opt_type,
        )

    # ─────────────────────────────────────────────────────────────────
    # 1. Bid-Ask Spread & Liquidity Gate
    # ─────────────────────────────────────────────────────────────────
    max_spread_pct = float(gate_cfg.get("max_spread_pct", DEFAULT_MAX_SPREAD_PCT))
    spread_pct = opt_info.get("spread_pct")
    if spread_pct is None and ask > 0 and bid > 0:
        spread_pct = round((ask - bid) / ask * 100.0, 2)
    elif spread_pct is not None:
        spread_pct = round(float(spread_pct), 2)

    if spread_pct is not None and spread_pct > max_spread_pct:
        reason = (
            f"Option bid-ask spread too wide ({spread_pct:.2f}% > {max_spread_pct:.1f}%). "
            f"Bid: Rs.{bid:.2f}, Ask: Rs.{ask:.2f}. Refusing illiquid strike to avoid immediate slippage."
        )
        return OptionGateResult(
            passed=False,
            status="REJECT",
            reason=reason,
            ltp=ltp,
            vwap=None,
            spread_pct=spread_pct,
            volume=vol_int,
            strike=strike,
            opt_type=opt_type,
        )

    # ─────────────────────────────────────────────────────────────────
    # 2. Market Opening Warmup Guard (09:15 - 09:18 IST)
    # ─────────────────────────────────────────────────────────────────
    warmup_minutes = int(gate_cfg.get("warmup_minutes", DEFAULT_WARMUP_MINUTES))
    min_vol = int(gate_cfg.get("min_volume", DEFAULT_MIN_VOLUME))
    
    if is_market_opening_warmup(current_time, warmup_minutes=warmup_minutes) and vol_int < min_vol:
        return OptionGateResult(
            passed=True,
            status="WARMUP_BYPASS",
            reason=(
                f"Market opening warmup active (09:15-09:{15+warmup_minutes:02d} IST, volume: {vol_int} < {min_vol}). "
                f"Option VWAP check safely bypassed to allow early momentum."
            ),
            ltp=ltp,
            vwap=None,
            spread_pct=spread_pct,
            volume=vol_int,
            strike=strike,
            opt_type=opt_type,
        )

    # ─────────────────────────────────────────────────────────────────
    # 3. Option VWAP Gate (The Institutional Alignment Rule)
    # ─────────────────────────────────────────────────────────────────
    require_above_vwap = gate_cfg.get("require_above_vwap", DEFAULT_REQUIRE_ABOVE_VWAP)
    vwap = calculate_option_vwap(opt_info, option_candles)

    if require_above_vwap and vwap is not None and vwap > 0:
        vwap_tol_pct = float(gate_cfg.get("vwap_tolerance_pct", 0.0))
        min_allowed_ltp = vwap * (1.0 - (vwap_tol_pct / 100.0))

        if ltp < min_allowed_ltp:
            reason = (
                f"Option premium Rs.{ltp:.2f} is BELOW intraday VWAP Rs.{vwap:.2f} "
                f"({(ltp - vwap) / vwap * 100.0:+.1f}%). Institutional option writers are in control; "
                f"skipping to prevent theta decay trap."
            )
            return OptionGateResult(
                passed=False,
                status="REJECT",
                reason=reason,
                ltp=ltp,
                vwap=vwap,
                spread_pct=spread_pct,
                volume=vol_int,
                strike=strike,
                opt_type=opt_type,
            )

    # ─────────────────────────────────────────────────────────────────
    # 4. Local Option Momentum (Optional candle check)
    # ─────────────────────────────────────────────────────────────────
    if option_candles and len(option_candles) >= 3:
        last_candle = option_candles[-1]
        prev_candle = option_candles[-2]
        c_close = float(last_candle.get("close") or ltp)
        p_low = float(prev_candle.get("low") or 0.0)
        
        # If option price collapsed far below previous candle low
        if p_low > 0 and c_close < (p_low * 0.95):
            reason = (
                f"Option premium in severe local breakdown (Close Rs.{c_close:.2f} < 95% of previous low Rs.{p_low:.2f})."
            )
            return OptionGateResult(
                passed=False,
                status="REJECT",
                reason=reason,
                ltp=ltp,
                vwap=vwap,
                spread_pct=spread_pct,
                volume=vol_int,
                strike=strike,
                opt_type=opt_type,
            )

    # All checks passed!
    vwap_str = f" >= VWAP Rs.{vwap:.2f}" if vwap else " (VWAP unquoted)"
    reason = (
        f"Option Chart Confluence Confirmed: {symbol} {strike} {opt_type} LTP Rs.{ltp:.2f}{vwap_str}, "
        f"Spread: {spread_pct or 0.0:.2f}%."
    )
    return OptionGateResult(
        passed=True,
        status="PASS",
        reason=reason,
        ltp=ltp,
        vwap=vwap,
        spread_pct=spread_pct,
        volume=vol_int,
        strike=strike,
        opt_type=opt_type,
    )
