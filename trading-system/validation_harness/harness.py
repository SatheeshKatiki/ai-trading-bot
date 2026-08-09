"""Core event-loop: replays historical underlying bars through the real
production signal/risk/exit pipeline for one strategy at a time.

Reuses, unmodified: `registry.run_strategy()` (signal generation +
institutional filters), `PremiumSignalEngine.evaluate()` (the "premium"
strategy's own entry path — not vectorizable, so it's called per-bar,
matching exactly how main.py calls it live), `select_option()` (strike/
expiry/lot-size selection), `resolve_initial_stop()` (premium-banded SL),
`RiskManager` (position sizing + all risk gates), `SmartExitEngine`
(trailing/SL/partial-booking/EOD exit), `resolve_option_atr()`
(premium-scale ATR feeding the trailing stop), `is_market_open()` /
`is_before_eod_cutoff()` (entry-time gates).

Known, documented scope limitations (not silently assumed — see each
comment inline): no pyramid scale-in simulation (single entry per
signal); AI-confidence filter runs as if `enable_ai_filter=False`
(confidence pinned to 1.0), matching the fallback path main.py itself
uses when the filter is disabled, rather than reconstructing the live
model singleton here; option premiums are Black-Scholes-simulated, not
real market data (see `premium_simulator.py`).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

import pandas as pd

from shared.exits.exit_engine import Position, SmartExitEngine
from shared.market_hours import is_before_eod_cutoff, is_market_open
from shared.risk import RiskManager, TradeRecord, resolve_initial_stop, resolve_option_atr
from trading_bot.strategies.premium_selection.options_selector import (
    OptionContract,
    calculate_option_price,
    select_option,
)
from trading_bot.strategies.momentum_strategy.exit_manager import TieredExitManager
from trading_bot.strategies.premium_selection.signal_engine import PremiumSignalEngine
from trading_bot.strategies.registry import registry

from .premium_simulator import DEFAULT_IV
from .production_settings import resolve_max_trades_per_day

__all__ = ["SimTrade", "BacktestResult", "run_strategy_backtest"]

# "MARL_Ultra" only exists as a registry entry as a side effect of
# importing trading_bot.main (its own explicit
# `registry.register("MARL_Ultra", marl_signals)` call, main.py:129) --
# this harness deliberately never imports main.py (heavy live-process
# side effects), so without this, "MARL_Ultra" would be silently absent
# from `registry.registered_strategies` and skipped entirely (found live
# during the first full validation run: it never appeared in results at
# all). Registering it here, pointing at the exact same
# `marl_strategy.generate_signals` main.py itself uses, closes that gap
# without importing main.py. "MARL_Ultra" and the separately-autodiscovered
# "marl_strategy" name call identical signal-generation code but are NOT
# behaviorally identical: MARL_Ultra additionally receives closed-loop P&L
# feedback on every exit (`record_trade_outcome`, wired into
# `_close_position` below) that feeds `marl_strategy`'s module-level
# adaptive risk-agent singleton -- the plain "marl_strategy" registration
# never gets this feedback call anywhere in this codebase.
if "MARL_Ultra" not in registry.registered_strategies:
    from trading_bot.strategies.marl_strategy import generate_signals as _marl_signals
    registry.register("MARL_Ultra", _marl_signals)


@dataclass
class SimTrade:
    symbol: str
    direction: str            # "CE" | "PE"
    entry_time: Any
    entry_premium: float
    exit_time: Any
    exit_premium: float
    quantity: int
    lot_size: int
    pnl: float
    exit_reason: str
    holding_minutes: float
    sl_method: str
    sl_band_label: str


@dataclass
class BacktestResult:
    strategy_name: str
    trades: list[SimTrade] = field(default_factory=list)
    final_equity: float = 0.0
    initial_capital: float = 0.0
    candidate_signals: int = 0     # every non-zero signal bar, whether or not it became a trade
    rejected_untradeable_sl: int = 0
    rejected_risk_gate: int = 0
    rejected_market_hours: int = 0


def _entry_gate_ok(ts: pd.Timestamp, settings: dict) -> bool:
    return is_market_open(now=ts, settings=settings) and is_before_eod_cutoff(now=ts, settings=settings)


def _generic_signal_series(strategy_name: str, df: pd.DataFrame, settings: dict) -> pd.Series:
    """Vectorized signal generation for every registered strategy except
    "premium" (see module docstring for why that one is per-bar)."""
    result = registry.run_strategy(strategy_name, df, **settings)
    signals = result[0] if isinstance(result, tuple) else result
    return signals


def run_strategy_backtest(
    strategy_name: str,
    underlying_df: pd.DataFrame,
    instrument: str = "NIFTY",
    initial_capital: float = 100_000.0,
    settings: Optional[dict] = None,
    vol: float = DEFAULT_IV,
    min_bars_for_premium_engine: int = 200,
    tradeable_dates: Optional[set] = None,
) -> BacktestResult:
    """Replay `underlying_df` (a DatetimeIndex-ed OHLCV frame) through the
    real production pipeline for `strategy_name`, returning every
    simulated trade plus rejection counters for diagnosing a strategy
    that never trades (vs. one that trades and loses).

    Parameters
    ----------
    tradeable_dates
        If given, NEW entries are only allowed on bars whose calendar
        date is in this set — `underlying_df` may still contain earlier
        bars purely as indicator-warmup context (e.g. EMA200 needs 200+
        bars of history, far more than a single trading day's ~75 5-min
        bars provides). Signals are still generated across the full
        `underlying_df` (so indicators see real history), only entry
        eligibility is restricted. `None` means every bar is eligible
        (the default, single-continuous-run behavior).
    """
    settings = dict(settings or {})
    risk_manager = RiskManager(initial_capital=initial_capital)

    # Daily trade cap, wired the way main.py wires it (same key precedence,
    # same target attribute). Without this the harness left the cap at
    # RiskConfig's default of 0 = unlimited while production ran a real cap,
    # so the harness could take entries production would have refused. 0
    # keeps the previous unlimited behaviour, so a caller passing no
    # settings is unaffected.
    max_trades = resolve_max_trades_per_day(settings)
    if max_trades > 0:
        risk_manager.config.max_trades_per_day = max_trades
    exit_engine = SmartExitEngine(atr_multiplier=1.5, partial_booking_pct=50.0)

    # `institutional_momentum` is the one strategy main.py does NOT manage
    # with SmartExitEngine: its exit branch calls
    # MomentumStrategy.manage_active_trades -> TieredExitManager and never
    # touches the generic engine (main.py's `if strategy_name ==
    # "institutional_momentum" ... else:`). Validating it with
    # SmartExitEngine measured an engine production does not run for it —
    # the same class of defect as #10's entry-path divergence, on the exit
    # side. See `_evaluate_tiered_exit` for exactly what is mirrored.
    tiered = TieredExitManager() if strategy_name == "institutional_momentum" else None
    result = BacktestResult(strategy_name=strategy_name, initial_capital=initial_capital)

    is_premium = strategy_name == "premium"
    signals = None if is_premium else _generic_signal_series(strategy_name, underlying_df, settings)
    premium_engine = (
        PremiumSignalEngine(
            instrument=instrument,
            capital=initial_capital,
            min_ai_confidence=settings.get("min_ai_confidence", 0.0),
            itm_strikes=settings.get("option_strike_itm_offset", 1),
        )
        if is_premium else None
    )

    position: Optional[dict] = None
    n = len(underlying_df)

    for i in range(n):
        ts = underlying_df.index[i]
        spot = float(underlying_df["close"].iloc[i])

        # ── Manage an open position ─────────────────────────────────
        if position is not None:
            bar_date = ts.date() if hasattr(ts, "date") else ts
            days_to_expiry = (position["expiry"] - bar_date).days
            if days_to_expiry < 0:
                premium = position["premium_candles"][-1]["close"]  # last known, contract has expired
                _close_position(result, risk_manager, position, premium, ts, "EXPIRED", strategy_name=strategy_name)
                position = None
                continue

            premium = calculate_option_price(
                spot=spot, strike=float(position["strike"]), days_to_expiry=max(days_to_expiry, 0),
                vol=vol, option_type=position["option_type"],
            )
            position["premium_candles"].append(
                {"timestamp": ts, "open": premium, "high": premium, "low": premium, "close": premium, "volume": 0}
            )
            option_df = pd.DataFrame(position["premium_candles"]).set_index("timestamp")
            atr_decision = resolve_option_atr(option_df, premium, settings)

            pos_obj: Position = position["pos_obj"]
            current_time_str = ts.strftime("%H:%M:%S")
            if tiered is not None:
                should_exit, reason, exit_qty = _evaluate_tiered_exit(
                    tiered, pos_obj, premium, underlying_df.iloc[: i + 1],
                    current_time_str, atr_decision.atr_value, exit_engine.eod_exit_time,
                )
            else:
                should_exit, reason, exit_qty = exit_engine.evaluate_exit(
                    pos_obj, premium, current_time_str, atr_decision.atr_value
                )
            if should_exit:
                qty = exit_qty or pos_obj.quantity
                _close_position(result, risk_manager, position, premium, ts, reason, qty=qty, strategy_name=strategy_name)
                if qty >= pos_obj.quantity:
                    position = None
                    if tiered is not None:
                        tiered.close_position()
                else:
                    pos_obj.quantity -= qty
            continue

        # ── Flat: look for an entry ─────────────────────────────────
        if tradeable_dates is not None:
            bar_date_check = ts.date() if hasattr(ts, "date") else ts
            if bar_date_check not in tradeable_dates:
                continue

        if is_premium:
            if len(underlying_df.iloc[: i + 1]) < min_bars_for_premium_engine:
                continue
            sig = premium_engine.evaluate(underlying_df.iloc[: i + 1], 1.0)
            if not sig.is_tradeable or sig.option is None:
                continue
            direction = "CE" if sig.direction == "BUY_CALL" else "PE"
            contract = sig.option
        else:
            raw_signal = signals.iloc[i]
            if raw_signal == 0:
                continue
            result.candidate_signals += 1
            if not _entry_gate_ok(ts, settings):
                result.rejected_market_hours += 1
                continue
            direction = "CE" if raw_signal == 1 else "PE"
            contract = select_option(
                instrument, spot, direction,
                itm_strikes=settings.get("option_strike_itm_offset", 1),
                from_date=(ts.date() if hasattr(ts, "date") else ts),
            )

        bar_date = ts.date() if hasattr(ts, "date") else ts
        entry_dte = max((contract.expiry - bar_date).days, 0)
        entry_premium = calculate_option_price(spot, float(contract.strike), entry_dte, vol, contract.option_type)

        sl_decision = resolve_initial_stop(entry_premium, settings)
        if not sl_decision.is_tradeable:
            result.rejected_untradeable_sl += 1
            continue

        if settings.get("option_risk_based_sizing", True):
            qty_per_unit = risk_manager.calculate_position_size(entry_premium, sl_decision.sl_price, ai_confidence=1.0)
            lots = max(1, qty_per_unit // contract.lot_size)
            quantity = lots * contract.lot_size
        else:
            quantity = contract.lot_size

        risk_amount = (entry_premium - sl_decision.sl_price) * quantity
        is_min_size = quantity <= contract.lot_size
        can_trade, _reason = risk_manager.can_trade(
            symbol=contract.symbol, side="BUY", risk_amount=risk_amount,
            ai_confidence=1.0, is_minimum_tradeable_size=is_min_size,
        )
        if not can_trade:
            result.rejected_risk_gate += 1
            continue

        pos_obj = Position(
            symbol=contract.symbol, side=1, entry_price=entry_premium, quantity=quantity,
            entry_time=ts.isoformat(), highest_price=entry_premium, lowest_price=entry_premium,
            stop_loss=sl_decision.sl_price, target=0.0, lot_size=contract.lot_size,
        )
        position = {
            "pos_obj": pos_obj, "strike": contract.strike, "option_type": contract.option_type,
            "expiry": contract.expiry, "symbol": contract.symbol, "direction": direction,
            "sl_method": sl_decision.method, "sl_band_label": sl_decision.band_label,
            "premium_candles": [
                {"timestamp": ts, "open": entry_premium, "high": entry_premium,
                 "low": entry_premium, "close": entry_premium, "volume": 0}
            ],
        }
        if tiered is not None:
            # Mirrors main.py's own `momentum_strategies[s].open_trade(...)`
            # on the entry path, including its passing of the raw QUANTITY
            # as `total_lots` — reproduced deliberately rather than
            # corrected, because the harness's job is to model what
            # production does. It only affects the engine's internal
            # booked/remaining bookkeeping and its log lines; the executed
            # quantity is derived from the position, exactly as in main.py.
            tiered.open_position(
                entry_price=entry_premium,
                stop_loss=sl_decision.sl_price,
                total_lots=quantity,
                direction=(1 if direction == "CE" else -1),
            )

    # Force-close anything still open at the end of the data.
    if position is not None:
        last_premium = position["premium_candles"][-1]["close"]
        _close_position(result, risk_manager, position, last_premium, underlying_df.index[-1], "END_OF_DATA", strategy_name=strategy_name)

    result.final_equity = risk_manager.current_equity
    return result


def _evaluate_tiered_exit(
    tiered: TieredExitManager,
    pos_obj: Position,
    premium: float,
    underlying_so_far: pd.DataFrame,
    current_time_str: str,
    current_atr: float,
    eod_exit_time: str,
) -> tuple[bool, str, Optional[int]]:
    """Mirror of `main.py`'s `institutional_momentum` exit branch.

    Reproduces main.py's ordering exactly, because order decides outcomes:

      1. hard profit target  (inert — option entries are written
         `target=0.0`, "no fixed target", and main.py guards `> 0`)
      2. hard stop-loss interceptor — full exit, and it runs BEFORE the
         strategy engine is consulted
      3. EOD square-off at `eod_exit_time`
      4. `TieredExitManager.evaluate` — exhaustion lock, its own SL check,
         Phase 1 partial booking at the configured R:R, Phase 2/3 runner
         trail on the underlying's runner EMA

    Deliberately NOT modelled, matching this module's existing scope
    (see the module docstring): the sentiment circuit breaker, and the AI
    early-exit — `ai_confidence=None` disables that branch rather than
    inventing a confidence series the harness has no source for. Both can
    only ADD exits, so every exit measured here is one production would
    also take.

    The candle window is `underlying_so_far`, i.e. bars up to and including
    the current one. In a backtest every bar is closed, so this is the
    "last COMPLETED candle" semantics main.py now feeds the engine after
    dropping its still-forming bar.
    """
    if pos_obj.target and pos_obj.target > 0 and premium >= pos_obj.target:
        return True, f"Hard TP Reached ({premium:.2f} >= {pos_obj.target:.2f})", None

    if pos_obj.stop_loss and pos_obj.stop_loss > 0 and premium <= pos_obj.stop_loss:
        return True, f"Hard SL Hit ({premium:.2f} <= {pos_obj.stop_loss:.2f})", None

    time_only = current_time_str.split(" ")[-1] if " " in current_time_str else current_time_str
    if time_only >= eod_exit_time:
        return True, "Time-based EOD Exit", None

    decision = tiered.evaluate(
        premium, underlying_so_far, ai_confidence=None, current_atr=current_atr
    )
    if not decision.should_exit:
        return False, "", None

    qty_pct = decision.quantity_pct
    if qty_pct < 1.0:
        # main.py's own lot rounding for a partial book.
        raw_qty = int(pos_obj.quantity * qty_pct)
        lots = max(1, raw_qty // pos_obj.lot_size)
        exit_qty = min(lots * pos_obj.lot_size, pos_obj.quantity)
    else:
        exit_qty = pos_obj.quantity
    return True, decision.reason, exit_qty


def _close_position(
    result: BacktestResult, risk_manager: RiskManager, position: dict,
    exit_premium: float, exit_time: Any, reason: str, qty: Optional[int] = None,
    strategy_name: str = "",
) -> None:
    pos_obj: Position = position["pos_obj"]
    quantity = qty if qty is not None else pos_obj.quantity
    pnl = (exit_premium - pos_obj.entry_price) * quantity  # option buying: always this direction, see exit_engine.py's effective_side convention
    entry_time = pos_obj.entry_time
    holding_minutes = (
        (pd.Timestamp(exit_time) - pd.Timestamp(entry_time)).total_seconds() / 60.0
        if entry_time else 0.0
    )
    risk_manager.record_trade(TradeRecord(
        position["symbol"], "SELL", pos_obj.entry_price, exit_premium, pnl,
        pd.Timestamp(exit_time).isoformat(),
    ))

    # MARL_Ultra-specific: main.py calls this on every real position close
    # (two call sites, main.py:836 and :1272) to feed the MARL model's
    # module-level adaptive risk-agent singleton — without it, "MARL_Ultra"
    # would behave identically to the plain "marl_strategy" registration
    # in this harness despite being a genuinely different, feedback-driven
    # strategy live. See the registration comment near this module's top.
    if strategy_name == "MARL_Ultra":
        try:
            from trading_bot.strategies.marl_strategy import record_trade_outcome
            record_trade_outcome(pnl)
        except Exception:
            pass

    result.trades.append(SimTrade(
        symbol=position["symbol"], direction=position["direction"],
        entry_time=entry_time, entry_premium=pos_obj.entry_price,
        exit_time=exit_time, exit_premium=exit_premium,
        quantity=quantity, lot_size=pos_obj.lot_size, pnl=pnl, exit_reason=reason,
        holding_minutes=holding_minutes, sl_method=position["sl_method"],
        sl_band_label=position["sl_band_label"],
    ))
