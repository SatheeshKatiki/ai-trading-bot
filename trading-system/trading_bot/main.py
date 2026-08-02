"""Live trading entry point.

This script boots the active broker (selected from the dashboard settings),
streams candles for a set of symbols, runs multi-strategy evaluations, and
issues market orders based on the generated signals — filtered by AI and
managed by institutional risk controls.

The trading engine is BROKER-AGNOSTIC.  Broker selection, credentials, and
switching are handled entirely by the brokers.BrokerFactory layer.

Strategies available:
  - ema_rsi                : Classic EMA crossover + RSI + Volume
  - enhanced_ai            : Full multi-layer confirmation (EMA + RSI + MACD + Volume + SMC + Option Chain + AI)
  - premium                : 8-Layer institutional-grade filter with option selection
  - institutional_momentum : Donchian breakout + VWAP + ADX + AI stoploss + 3-phase tiered exits
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
import threading

# Force UTF-8 for terminal logging on Windows
if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if sys.stderr and hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')

# Disable any local system proxy to prevent connection failures to Fyers
os.environ["HTTP_PROXY"] = ""
os.environ["HTTPS_PROXY"] = ""
os.environ["ALL_PROXY"] = ""
os.environ["no_proxy"] = "*"
os.environ["NO_PROXY"] = "*"

from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Any, Optional, Literal

import pandas as pd
import pytz

_IST = pytz.timezone("Asia/Kolkata")

# Add parent directory to sys.path to find 'shared' module
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shared.config import CONFIG
from shared.state import update_equity, record_trade

# ---------------------------------------------------------------------------
# Module-level mutable state lifecycle note (Low audit finding):
#
# The outer `if __name__ == "__main__":` loop below catches any exception
# from run_live_bot() and retries WITHOUT restarting the Python process
# (see _compute_retry_delay()/_should_reset_failure_count()) — so every
# module-level global declared in this file (this one, _m2m_last_update,
# _settings_cache/_settings_last_mtime, etc.) SURVIVES a crash-retry
# unchanged, unlike what a real process restart would give you.
#
# Each one currently declared here is safe under that model:
#   - _evaluating_symbols: mutated only inside a try/finally in the tick
#     loop (the `finally: _evaluating_symbols.discard(s)` a few hundred
#     lines below) — cleared even if that symbol's evaluation raises, so
#     nothing can wedge a symbol into "permanently blocked" state.
#   - _m2m_last_update / the settings cache below: intentionally MEANT to
#     persist across a crash-retry (they're a rate-limit timestamp and a
#     file-mtime cache respectively) — resetting them would just force
#     one extra harmless recompute/read on the next tick, not a
#     correctness issue either way.
#
# If you add new module-level mutable state here, make sure it's either
# safe to leave stale across a crash-retry (like the two above), or is
# explicitly guarded with the same try/finally pattern as
# _evaluating_symbols — don't assume a "restart" clears it.
# ---------------------------------------------------------------------------
_evaluating_symbols: set[str] = set()

# Broker layer — broker-agnostic: trading logic never imports vendor SDKs directly
from brokers import BrokerFactory, OrderRequest, OrderSide, OrderType, OrderStatus
from trading_bot.strategies.registry import registry
from trading_bot.strategies.premium_selection import (
    PremiumSignalEngine, PremiumSignal, generate_signals as premium_signals
)
from trading_bot.strategies.momentum_strategy import MomentumStrategy
from trading_bot.strategies.drl_strategy import generate_signals as drl_signals
from trading_bot.strategies.marl_strategy import generate_signals as marl_signals

_m2m_last_update: float = 0.0

# Import AI / Risk / Exit / Alert Modules
from shared.ai import TradeFilterModel, compute_features
from shared.risk import RiskManager, RiskConfig, TradeRecord
from shared.exits import SmartExitEngine, Position, PyramidSizer
from shared.alerts import alerter
from trading_bot.portfolio_risk import PortfolioRiskEngine
from trading_bot.iceberg_manager import IcebergManager

# Security layer
from shared.security import install_log_sanitizer, audit, validator
from shared.security.audit_log import AuditEvent
from shared.security.rate_limiter import ORDER_LIMITER
from shared.security.validator import ValidationError

# Install log sanitizer first — ensures API keys never appear in any log output
install_log_sanitizer()

logging.basicConfig(
    level=CONFIG.LOG_LEVEL,
    format="[%(asctime)s] %(levelname)s %(name)s: %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)

# Register strategies that are not auto-discovered (e.g., from subpackages)
registry.register("premium", premium_signals)
registry.register("drl_strategy", drl_signals)
registry.register("MARL_Ultra", marl_signals)

# Path to the shared settings file written by the Streamlit dashboard
_SETTINGS_PATH = Path(__file__).resolve().parents[1] / "config" / "settings.json"
_POSITIONS_PATH = Path(__file__).resolve().parents[1] / "config" / "active_positions.json"

# ------------------------------------------------------------------
# Settings cache: avoids disk I/O on every tick (checks mtime instead)
# ------------------------------------------------------------------
_settings_cache: dict = {}
_settings_last_mtime: float = 0.0


def _save_positions(positions: Dict[str, Position]) -> None:
    import tempfile
    import os
    try:
        # Create a shallow copy to prevent RuntimeError if a background task mutates active_positions
        positions_copy = dict(positions)
        data = {
            sym: {
                "symbol": p.symbol,
                "side": p.side,
                "quantity": p.quantity,
                "entry_price": p.entry_price,
                "entry_time": getattr(p, "entry_time", ""),
                "highest_price": getattr(p, "highest_price", p.entry_price),
                "lowest_price": getattr(p, "lowest_price", p.entry_price),
                "stop_loss": getattr(p, "stop_loss", 0.0),
                "target": getattr(p, "target", 0.0),
                "is_partially_booked": getattr(p, "is_partially_booked", False),
                "scales_done": getattr(p, "scales_done", 0),
                "sl_order_id": getattr(p, "sl_order_id", None)
            } for sym, p in positions_copy.items()
        }
        
        # Phase 7: Atomic Write prevents torn/corrupted state files on crash
        _POSITIONS_PATH.parent.mkdir(parents=True, exist_ok=True)
        temp_fd, temp_path = tempfile.mkstemp(dir=_POSITIONS_PATH.parent, prefix="active_positions_tmp_", suffix=".json")
        try:
            with os.fdopen(temp_fd, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=4)
            os.replace(temp_path, _POSITIONS_PATH)
        except Exception as e:
            if os.path.exists(temp_path):
                os.unlink(temp_path)
            raise e
            
    except Exception as e:
        logger.error("Failed to save active positions: %s", e)

def _load_positions() -> Dict[str, Position]:
    if _POSITIONS_PATH.exists():
        try:
            with open(_POSITIONS_PATH, "r") as f:
                data = json.load(f)
                loaded = {}
                for sym, p in data.items():
                    pos = Position(
                        symbol=p["symbol"], 
                        side=p["side"], 
                        entry_price=p["entry_price"],
                        quantity=p["quantity"], 
                        entry_time=p.get("entry_time", p.get("timestamp", "")),
                        highest_price=p.get("highest_price", p["entry_price"]),
                        lowest_price=p.get("lowest_price", p["entry_price"]),
                        stop_loss=p.get("stop_loss", 0.0),
                        target=p.get("target", 0.0)
                    )
                    pos.is_partially_booked = p.get("is_partially_booked", False)
                    pos.scales_done = p.get("scales_done", 0)
                    pos.sl_order_id = p.get("sl_order_id", None)
                    pos.is_exiting = False  # Always reset on load — no in-flight tasks survive restart
                    loaded[sym] = pos
                return loaded
        except Exception as e:
            logger.error("Failed to load active positions: %s", e)
    return {}


def _load_settings() -> dict:
    """Read settings from disk, using an in-memory cache that checks for file modifications."""
    import os
    global _settings_cache, _settings_last_mtime
    
    
    defaults = {
        "active_strategy": "institutional_momentum",
        "live_trading_mode": False,
        "ema_fast": 9,
        "ema_slow": 20,
        "rsi_window": 14,
        "rsi_buy": 60,
        "rsi_sell": 40,
        "target_pct": 500.0,
        "stoploss_pct": 15.0,
        "auto_trade_enabled": True,
    }
    
    if _SETTINGS_PATH.is_file():
        try:
            current_mtime = os.path.getmtime(_SETTINGS_PATH)
            # If file changed or we haven't loaded it yet
            if current_mtime > _settings_last_mtime or not _settings_cache:
                with open(_SETTINGS_PATH, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                    defaults.update(loaded)
                _settings_cache = defaults
                _settings_last_mtime = current_mtime
                logger.info("Settings reloaded instantly from disk.")
        except Exception as e:
            logger.error(f"Failed to check/load settings: {e}")
            
    # If file doesn't exist or error occurred, use defaults/previous cache
    if not _settings_cache:
        _settings_cache = defaults
        
    return _settings_cache


class CandleAggregator:
    """Aggregate raw tick dictionaries into OHLCV DataFrames (Per-Symbol Isolated)."""

    def __init__(self, symbols: List[str], timeframe_str: str = "5 Min"):
        self.symbols = symbols
        self._buffer: Dict[str, List[Dict]] = defaultdict(list)
        self._current_interval: Dict[str, datetime | None] = defaultdict(lambda: None)
        self.candles: Dict[str, pd.DataFrame] = {}
        
        # Parse timeframe to minutes
        try:
            if "Min" in timeframe_str:
                self.interval_mins = int(timeframe_str.split(" ")[0])
            elif "Hour" in timeframe_str:
                self.interval_mins = int(timeframe_str.split(" ")[0]) * 60
            else:
                self.interval_mins = 1
        except Exception:
            self.interval_mins = 1

    def _interval_floor(self, ts: datetime) -> datetime:
        # Floor to the nearest interval_mins boundary. Previously computed
        # (ts.minute // interval_mins) * interval_mins directly on
        # ts.minute (always 0-59), which is always 0 for any
        # interval_mins > 60 -- a tick at 11:45 and one at 10:15 would
        # both floor to "minute=0, hour unchanged", landing in two
        # different (wrong-sized) 1-hour buckets instead of the same
        # correct multi-hour bucket. Flooring on total minutes since
        # midnight instead handles hour-spanning intervals correctly,
        # while being identical to the old behavior for interval_mins
        # <= 60 (verified: for interval_mins=60 both formulas floor to
        # the top of the current hour).
        total_minutes = ts.hour * 60 + ts.minute
        floored_total = (total_minutes // self.interval_mins) * self.interval_mins
        floor_hour, floor_minute = divmod(floored_total, 60)
        return ts.replace(hour=floor_hour, minute=floor_minute, second=0, microsecond=0)

    def add_tick(self, tick: Dict) -> None:
        ts = datetime.fromtimestamp(tick["timestamp"], tz=timezone.utc)
        minute = self._interval_floor(ts)
        symbol = tick["symbol"]
        
        current = self._current_interval[symbol]
        if current is None:
            self._current_interval[symbol] = minute
        elif minute > current:
            self._finalize_symbol_interval(symbol, current)
            self._current_interval[symbol] = minute
            
        self._buffer[symbol].append(tick)

    def _finalize_symbol_interval(self, symbol: str, interval: datetime) -> None:
        ticks = self._buffer.get(symbol, [])
        if not ticks:
            return
            
        df = pd.DataFrame(ticks)
        candle = {
            "open": df["ltp"].iloc[0],
            "high": df["ltp"].max(),
            "low": df["ltp"].min(),
            "close": df["ltp"].iloc[-1],
            "volume": df["volume"].sum(),
            "timestamp": pd.to_datetime(interval),
        }
        
        candle_df = pd.DataFrame([candle]).set_index("timestamp")
        
        if symbol not in self.candles:
            self.candles[symbol] = candle_df
        else:
            self.candles[symbol] = pd.concat([self.candles[symbol], candle_df]).tail(2000)
            
        # Clear only this symbol's buffer
        self._buffer[symbol] = []

    def get_latest_dataframe(self, symbol: str) -> pd.DataFrame:
        if symbol not in self.candles:
            return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
        return self.candles[symbol]


async def run_live_bot(symbols: List[str]) -> None:
    # Get the single active broker — selected from dashboard settings.
    # BrokerFactory handles credentials, authentication, and paper-mode fallback.
    broker = BrokerFactory.get_active_broker()
    logger.info(
        "Live bot starting with broker: %s (paper=%s)",
        broker.DISPLAY_NAME, broker.paper_mode,
    )
    audit.log(AuditEvent.BOT_START, {
        "broker":     broker.BROKER_ID,
        "paper_mode": broker.paper_mode,
        "symbols":    symbols,
    })

    # Read settings
    _init_settings = _load_settings()
    _initial_capital = float(_init_settings.get("initial_capital", 100_000.0))
    _tf_str = _init_settings.get("timeframe", "5 Min")
    
    # Load previous PNL if from today
    from shared.state import load_state
    saved_state = load_state()
    saved_pnl = saved_state.get("pnl", 0.0)
    last_update_str = saved_state.get("last_update", "")
    
    # Check if last_update is from today
    today_str = datetime.now(_IST).strftime("%Y-%m-%d")
    if last_update_str and not last_update_str.startswith(today_str):
        # Reset if it's a new day
        saved_pnl = 0.0
        logger.info("New trading day detected. Resetting session PNL to 0.0")
    else:
        logger.info(f"Resuming session with previous PNL: {saved_pnl}")
        
    aggregator = CandleAggregator(symbols, _tf_str)

    # Initialize Core Engines
    risk_manager = RiskManager(initial_capital=_initial_capital, daily_pnl=saved_pnl)
    ai_filter = TradeFilterModel()
    exit_engine = SmartExitEngine(atr_multiplier=1.5, partial_booking_pct=50.0)
    pyramid_sizer = PyramidSizer(pct_trigger=0.2, max_scales=2)
    portfolio_risk = PortfolioRiskEngine(max_daily_dd_pct=5.0, max_weekly_dd_pct=10.0, max_consecutive_losses=3, initial_capital=_initial_capital)
    iceberg_manager = IcebergManager(max_slice_qty=500)

    active_positions: Dict[str, Position] = _load_positions()
    if active_positions:
        logger.info("Loaded %d active positions from disk state recovery.", len(active_positions))
        
    momentum_strategies: Dict[str, MomentumStrategy] = {}

    # Preload historical data using the broker directly (eliminating HTTP hop and localhost dependency)
    from datetime import timedelta

    def _format_sym(s: str) -> str:
        if ":" in s and "-" in s: return s
        idx = {"NIFTY": "NSE:NIFTY50-INDEX", "BANKNIFTY": "NSE:NIFTYBANK-INDEX", "SENSEX": "BSE:SENSEX-INDEX"}
        if s in idx: return idx[s]
        exch, t = s.split(":") if ":" in s else ("NSE", s)
        return f"{exch}:{t}-EQ"

    _preload_failed_symbols: List[str] = []
    try:
        end_date = datetime.now().strftime("%Y-%m-%d")
        start_date = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")

        if not broker.is_authenticated:
            broker.authenticate()

        # Each symbol is preloaded in its own try/except so one bad symbol
        # (broker error, malformed response) can't silently abort preload
        # for every symbol still left in the list.
        for sym in symbols:
            try:
                broker_sym = _format_sym(sym)
                data = broker.get_historical_data(broker_sym, start_date, end_date, _tf_str)
                if data:
                    df = pd.DataFrame(data)
                    df["timestamp"] = pd.to_datetime(df["datetime"] if "datetime" in df.columns else df.get("Datetime"))
                    df.set_index("timestamp", inplace=True)
                    # Lowercase columns mapping
                    col_map = {c: c.lower() for c in df.columns}
                    df.rename(columns=col_map, inplace=True)
                    for col in ["open", "high", "low", "close", "volume"]:
                        if col in df.columns:
                            df[col] = pd.to_numeric(df[col], errors='coerce')
                    aggregator.candles[sym] = df
                    logger.info("Preloaded %d historical candles for %s natively via Broker", len(df), sym)
                else:
                    _preload_failed_symbols.append(sym)
                    logger.warning("Historical preload for %s returned no data; starting with an empty candle buffer.", sym)
            except Exception as sym_e:
                _preload_failed_symbols.append(sym)
                logger.warning("Could not preload history for %s: %s", sym, sym_e)
    except Exception as e:
        # Auth (or other setup) failure affects every symbol at once.
        _preload_failed_symbols = list(symbols)
        logger.error("Could not preload history natively from broker: %s", e)

    if _preload_failed_symbols:
        # A silent empty candle buffer means the affected symbol(s) won't
        # clear strategy warmup checks (e.g. `len(df) < 50`) until enough
        # live ticks accumulate naturally -- effectively "not trading" for
        # a while with no visible signal beyond a log line. Surface it the
        # same way other operator-facing conditions in this file do.
        try:
            alerter.send_alert(_build_preload_failure_alert(_preload_failed_symbols))
        except Exception as alert_e:
            logger.warning("Failed to send historical-preload alert: %s", alert_e)
        audit.log(AuditEvent.VALIDATION_ERROR,
                  {"reason": "historical_preload_incomplete", "symbols": _preload_failed_symbols},
                  severity="WARNING")

    last_eval_time = 0.0
    _iceberg_semaphore = asyncio.Semaphore(3)

    async def background_iceberg_entry(broker, entry_req: OrderRequest, pos_obj: Position, s: str, is_option_trade: bool):
        try:
            async with _iceberg_semaphore:
                executed_slices = await iceberg_manager.execute_iceberg(
                    broker, 
                    entry_req,
                    halt_check=lambda: portfolio_risk.trading_halted
                )
                actual_qty = sum(resp.quantity for resp in executed_slices)
            if actual_qty == 0:
                logger.error("Entry order completely failed to execute for %s. Removing ghost position.", s)
                if s in active_positions:
                    del active_positions[s]
                    _save_positions(active_positions)
            else:
                pos_obj.quantity = actual_qty
                
                # Fetch actual filled price to track Slippage
                await asyncio.sleep(1.0) # Give broker time to update order book
                total_cost = 0.0
                valid_slices = 0
                for resp in executed_slices:
                    if resp.order_id:
                        status = broker.get_order_status(resp.order_id)
                        if status and status.traded_price > 0:
                            total_cost += status.traded_price * resp.quantity
                            valid_slices += resp.quantity
                
                if valid_slices > 0:
                    pos_obj.entry_price = total_cost / valid_slices
                    logger.info("Actual Entry Price for %s resolved to %.2f (Slippage adjusted)", s, pos_obj.entry_price)

                # Place Hard Stop-Loss at Exchange
                sl_req = OrderRequest(
                    symbol=s,
                    quantity=actual_qty,
                    side=OrderSide.SELL if pos_obj.side == 1 else OrderSide.BUY,
                    order_type=OrderType.SL_M,
                    trigger_price=pos_obj.stop_loss,
                    price=0.0, # Market price execution upon trigger
                )
                try:
                    sl_resp = await broker.place_order_async(sl_req)
                    if sl_resp and sl_resp.order_id:
                        pos_obj.sl_order_id = sl_resp.order_id
                        logger.info("Hard SL placed at Exchange for %s at %.2f (ID: %s)", s, pos_obj.stop_loss, sl_resp.order_id)
                except Exception as sl_e:
                    logger.error("Failed to place Hard SL for %s: %s", s, sl_e)
                
                _save_positions(active_positions)
                
                # Persist Entry to state.db ONLY after broker confirms execution
                state_action = "BUY" if is_option_trade else ("BUY" if pos_obj.side == 1 else "SELL")
                record_trade(pos_obj.symbol, state_action, pos_obj.entry_price, datetime.now(_IST).isoformat(), qty=actual_qty)
                update_equity(risk_manager.current_equity, risk_manager.daily_pnl)

                audit.trade(AuditEvent.TRADE_ENTRY, pos_obj.symbol,
                            entry_req.side.value, actual_qty,
                            pos_obj.entry_price, broker=broker.BROKER_ID)
        except Exception as e:
            logger.error("Background Iceberg Entry Failed for %s: %s", s, e)
            if s in active_positions:
                del active_positions[s]
                _save_positions(active_positions)

    async def update_exchange_sl(broker, pos: Position):
        """Cancels old Hard SL and places a new one at the updated Trailing SL price."""
        if not getattr(pos, 'sl_order_id', None):
            return
        
        old_id = pos.sl_order_id
        try:
            broker.cancel_order(old_id)
            logger.info("Cancelled old Trailing SL (ID: %s) for %s", old_id, pos.symbol)
        except Exception as e:
            logger.error("Failed to cancel old SL for %s: %s", pos.symbol, e)
            return  # Safety: Don't place a new one if the old one couldn't be cancelled (avoids multiple SLs)

        # Give broker a split second to register the cancellation
        await asyncio.sleep(0.5)

        new_sl_req = OrderRequest(
            symbol=pos.symbol,
            quantity=pos.quantity,
            side=OrderSide.SELL if pos.side == 1 else OrderSide.BUY,
            order_type=OrderType.SL_M,
            trigger_price=pos.stop_loss,
            price=0.0,
        )
        try:
            sl_resp = await broker.place_order_async(new_sl_req)
            if sl_resp and sl_resp.order_id:
                pos.sl_order_id = sl_resp.order_id
                logger.info("New Trailing SL placed at Exchange for %s at %.2f (ID: %s)", pos.symbol, pos.stop_loss, pos.sl_order_id)
                _save_positions(active_positions)
        except Exception as e:
            logger.error("Failed to place new Trailing SL for %s: %s", pos.symbol, e)

    async def background_iceberg_exit(
        broker, exit_req: OrderRequest, sym: str, side: int, entry_price: float,
        exit_price: float, qty_to_close: int, full_exit: bool
    ):
        # Assigned before the try block so the except handler's `if pos:`
        # check below can never raise UnboundLocalError if an exception
        # fires before `pos = active_positions.get(sym)` executes (e.g. the
        # semaphore acquisition itself failing) — previously that would mask
        # the real error and leave is_exiting stuck True on this position
        # forever, since the intended unlock-on-failure code never ran.
        pos = active_positions.get(sym)
        try:
            actual_exit_qty = qty_to_close
            ltp_actual = exit_price
            broker_sl_hit = False

            async with _iceberg_semaphore:
                # Re-fetch: active_positions may have changed while this
                # coroutine was waiting on the semaphore above.
                pos = active_positions.get(sym)
                if pos and getattr(pos, 'sl_order_id', None):
                    try:
                        # Interceptor: Check if the Broker SL already executed natively
                        status = broker.get_order_status(pos.sl_order_id)
                        if status and status.status in ["COMPLETE", "FILLED", "TRADED"]:
                            logger.warning("Broker Hard SL already executed for %s! Skipping local Market order.", sym)
                            broker_sl_hit = True
                            actual_exit_qty = pos.quantity
                            ltp_actual = status.traded_price if status.traded_price > 0 else exit_price
                        else:
                            broker.cancel_order(pos.sl_order_id)
                            logger.info("Cancelled Hard SL order (ID: %s) for %s before exit", pos.sl_order_id, sym)
                        pos.sl_order_id = None
                    except Exception as e:
                        logger.error("Failed to check/cancel Hard SL for %s: %s", sym, e)
                
                if not broker_sl_hit:
                    executed_slices = await iceberg_manager.execute_iceberg(
                        broker, 
                        exit_req,
                        halt_check=lambda: portfolio_risk.trading_halted
                    )
                    actual_exit_qty = sum(resp.quantity for resp in executed_slices)
            
            if not broker_sl_hit:
                if actual_exit_qty == 0:
                    logger.error("EXIT order completely failed to execute for %s. Resetting is_exiting — will retry next tick.", sym)
                    # Unlock the position so it's managed again on the next tick
                    if pos:
                        pos.is_exiting = False
                    return
                
                # Fetch actual filled price to track Slippage
                await asyncio.sleep(1.0)
                total_value = 0.0
                valid_slices = 0
                for resp in executed_slices:
                    if resp.order_id:
                        status = broker.get_order_status(resp.order_id)
                        if status and status.traded_price > 0:
                            total_value += status.traded_price * resp.quantity
                            valid_slices += resp.quantity
                
                ltp_actual = total_value / valid_slices if valid_slices > 0 else exit_price
                logger.info("Actual Exit Price for %s resolved to %.2f (Slippage adjusted)", sym, ltp_actual)
            
            # ── Confirmed execution: now record PNL and clean up position ──
            pnl = (ltp_actual - entry_price) * actual_exit_qty * side

            if _load_settings().get("active_strategy") == "MARL_Ultra":
                try:
                    from trading_bot.strategies.marl_strategy import record_trade_outcome
                    record_trade_outcome(pnl)
                except Exception as mrl_exc:
                    logger.error("Failed to record MARL trade outcome: %s", mrl_exc)

            portfolio_risk.update_pnl(pnl, risk_manager.current_equity)
            trade_side = "LONG" if side == 1 else "SHORT"
            risk_manager.record_trade(TradeRecord(
                sym, trade_side,
                entry_price, ltp_actual, pnl, datetime.now(_IST).isoformat()
            ))
            is_opt = "CE" in sym or "PE" in sym
            state_action = "SELL" if is_opt else ("SELL" if side == 1 else "BUY")
            record_trade(sym, state_action, ltp_actual, datetime.now(_IST).isoformat(), qty=actual_exit_qty)
            update_equity(risk_manager.current_equity, risk_manager.daily_pnl)
            alerter.send_exit_alert(sym, side, actual_exit_qty, ltp_actual, pnl, "Live Exit Confirmed")
                
            audit.trade(AuditEvent.TRADE_EXIT, sym,
                        "SELL" if side == 1 else "BUY",
                        actual_exit_qty, entry_price,
                        broker=broker.BROKER_ID, pnl=pnl)

            # ── Remove or reduce position in shared state ──
            if sym in active_positions:
                pos = active_positions[sym]
                if full_exit or actual_exit_qty >= pos.quantity:
                    del active_positions[sym]
                else:
                    pos.quantity -= actual_exit_qty
                    pos.is_exiting = False  # Partial exit: allow further management
                _save_positions(active_positions)

        except Exception as e:
            logger.error("Background Iceberg Exit Failed for %s: %s", sym, e)
            # Unlock the position so it's re-evaluated on the next tick
            if pos:
                pos.is_exiting = False


    async def background_iceberg_scale(broker, scale_req: OrderRequest, pos: Position, side_str: str, ltp: float):
        try:
            async with _iceberg_semaphore:
                executed_slices = await iceberg_manager.execute_iceberg(
                    broker,
                    scale_req,
                    halt_check=lambda: portfolio_risk.trading_halted
                )
                actual_scale_qty = sum(req.quantity for req in executed_slices)

            if actual_scale_qty == 0:
                logger.error("SCALE order completely failed to execute for %s.", pos.symbol)
            else:
                audit.trade(AuditEvent.TRADE_ENTRY, pos.symbol,
                            scale_req.side.value, actual_scale_qty,
                            ltp, broker=broker.BROKER_ID)

                # Update position
                if pos.symbol in active_positions:
                    pos.quantity += actual_scale_qty
                    pos.scales_done += 1
                    alerter.send_trade_alert(pos.symbol, f"PYRAMID SCALE IN {side_str}", actual_scale_qty, ltp, 1.0)
                    _save_positions(active_positions)
        except Exception as e:
            logger.error("Background Iceberg Scale Failed for %s: %s", pos.symbol, e)
        finally:
            # Unlock regardless of outcome so the position is eligible for the
            # next legitimate scale-in trigger on a later tick.
            pos.is_scaling = False
    async def on_tick(tick: Dict) -> None:
        nonlocal last_eval_time
        sym = tick["symbol"]
        ltp = tick["ltp"]
        # Use IST time for all intraday comparisons (EOD exit at 15:15 IST)
        current_time = datetime.now(_IST).strftime("%Y-%m-%d %H:%M:%S")

        # Load settings once per tick. _load_settings() caches by file
        # mtime (not a time-based TTL, despite what this comment used to
        # claim) — a cheap os.path.getmtime() stat check on every call,
        # only re-parsing the file when it has actually changed, so this
        # is free (no meaningful disk I/O) on the vast majority of ticks
        # regardless of how long it's been since the last real change.
        settings = _load_settings()
        
        # ----------------------------------------------------------------
        # 🚨 Emergency Halt Check (Advanced Wiring)
        # ----------------------------------------------------------------
        if not settings.get("is_active", True):
            # Engine is halted. Do not process ticks or place new trades.
            return

        # ----------------------------------------------------------------
        # Lazy Strategy Initialization
        # ----------------------------------------------------------------
        strategy_name = settings.get("active_strategy", "institutional_momentum")
        if strategy_name == "institutional_momentum" and sym not in momentum_strategies:
            momentum_strategies[sym] = MomentumStrategy(
                capital=_initial_capital,
                target_pct=settings.get("target_pct", 500.0),
                stoploss_pct=settings.get("stoploss_pct", 15.0),
                default_lots=settings.get("quantity", 1)
            )

        # ----------------------------------------------------------------
        # 1. Evaluate Exit Conditions for Open Positions
        # ----------------------------------------------------------------
        open_position = None
        base_symbol_key = None
        
        # We must match the incoming market tick with the correct open position.
        for base_sym, position in active_positions.items():
            if position.symbol == sym:
                # The incoming tick matches the option or stock we are holding
                open_position = position
                base_symbol_key = base_sym
                break
            
            # Fallback for plain index/equity positions
            is_option = "CE" in position.symbol or "PE" in position.symbol
            if base_sym == sym and not is_option:
                open_position = position
                base_symbol_key = base_sym
                break

        if open_position:
            # ── Safety gate: skip if a background exit is already in flight ──
            if open_position.is_exiting:
                return

            df = aggregator.get_latest_dataframe(sym)
            # Proper 14-bar rolling ATR (not single-candle range which is too noisy)
            if not df.empty and len(df) >= 2:
                tr_series = (df["high"] - df["low"]).abs()
                current_atr = tr_series.rolling(min(14, len(df))).mean().iloc[-1]
                if pd.isna(current_atr) or current_atr <= 0:
                    current_atr = ltp * 0.005
            else:
                current_atr = ltp * 0.005

            from shared.sentiment import get_current_sentiment
            sentiment_data = get_current_sentiment()
            sentiment_score = sentiment_data.get("score", 0.0)

            should_exit, reason, exit_qty = False, "", None

            # ── Sentiment Panic: full-position exit with highest priority ──────
            # Symmetric both ways: a long position is at risk from a bearish
            # panic (score < -0.8), and a short position is equally at risk
            # from a bullish squeeze (score > 0.8) — the circuit breaker
            # previously only protected longs, leaving shorts fully exposed
            # to the mirror-image blowup scenario.
            if sentiment_score < -0.8 and open_position.side == 1:
                should_exit = True
                reason = "Macro Panic (Sentiment Circuit Breaker)"
                exit_qty = open_position.quantity
            elif sentiment_score > 0.8 and open_position.side == -1:
                should_exit = True
                reason = "Bullish Squeeze (Sentiment Circuit Breaker)"
                exit_qty = open_position.quantity
            
            # ── Strategy exit check: only runs if sentiment hasn't already fired ──
            if not should_exit:
                # --- Hard Target % Interceptor ---
                if open_position.target and open_position.target > 0:
                    is_opt_pos = "CE" in open_position.symbol or "PE" in open_position.symbol
                    if is_opt_pos:
                        if ltp >= open_position.target:
                            should_exit = True
                            reason = f"Hard TP Reached (LTP {ltp:.2f} >= TGT {open_position.target:.2f})"
                            exit_qty = open_position.quantity
                    else:
                        if open_position.side == 1 and ltp >= open_position.target:
                            should_exit = True
                            reason = f"Hard TP Reached (LTP {ltp:.2f} >= TGT {open_position.target:.2f})"
                            exit_qty = open_position.quantity
                        elif open_position.side == -1 and ltp <= open_position.target:
                            should_exit = True
                            reason = f"Hard TP Reached (LTP {ltp:.2f} <= TGT {open_position.target:.2f})"
                            exit_qty = open_position.quantity

                # --- Hard Stop Loss Interceptor ---
                if not should_exit and open_position.stop_loss and open_position.stop_loss > 0:
                    if is_opt_pos:
                        if ltp <= open_position.stop_loss:
                            should_exit = True
                            reason = f"Hard SL Hit (LTP {ltp:.2f} <= SL {open_position.stop_loss:.2f})"
                            exit_qty = open_position.quantity
                    else:
                        if open_position.side == 1 and ltp <= open_position.stop_loss:
                            should_exit = True
                            reason = f"Hard SL Hit (LTP {ltp:.2f} <= SL {open_position.stop_loss:.2f})"
                            exit_qty = open_position.quantity
                        elif open_position.side == -1 and ltp >= open_position.stop_loss:
                            should_exit = True
                            reason = f"Hard SL Hit (LTP {ltp:.2f} >= SL {open_position.stop_loss:.2f})"
                            exit_qty = open_position.quantity

            if not should_exit:
                strategy_name = settings.get("active_strategy", "institutional_momentum")
            
                if strategy_name == "institutional_momentum" and sym in momentum_strategies:
                    m_strategy = momentum_strategies[sym]
                    # Requires 5min dataframe for TieredExitManager
                    df_5min = df.resample('5min', label='right', closed='right').agg({
                        'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last', 'volume': 'sum'
                    }).dropna() if not df.empty else df
                    
                    # Fetch AI Confidence for early exit
                    features = compute_features(df.tail(60)).tail(1)
                    confidence = ai_filter.predict(features)["confidence"].iloc[-1] if (ai_filter.is_trained and not features.empty) else 1.0
                    
                    decision = m_strategy.manage_active_trades(
                        ltp, 
                        df_5min, 
                        ai_confidence=confidence * 100,
                        current_atr=current_atr
                    )
                    if decision and decision.get("exit"):
                        should_exit = True
                        reason = decision.get("reason", "Institutional Smart Exit")
                        qty_pct = decision.get("quantity_pct", 1.0)
                        if qty_pct < 1.0:
                            raw_qty = int(open_position.quantity * qty_pct)
                            lots = max(1, raw_qty // open_position.lot_size)
                            exit_qty = min(lots * open_position.lot_size, open_position.quantity)
                        else:
                            exit_qty = open_position.quantity
                        
                        if open_position.is_partially_booked and qty_pct < 1.0:
                            pass
                else:
                    # Dynamically apply Trailing SL settings
                    if settings.get("trailing_sl", False) or settings.get("trailingSl", False):
                        # AUDIT FIX: Default 0.5% (not 1.0%) — proven optimal in backtesting
                        exit_engine.trailing_activation_pct = settings.get("trail_trigger", settings.get("trailTrigger", 0.5))
                        exit_engine.trailing_offset_pct     = settings.get("trail_offset",  settings.get("trailOffset",  0.35))
                    else:
                        # If turned off, set activation pct to an unreachable high number
                        exit_engine.trailing_activation_pct = 9999.0

                    old_stop_loss = open_position.stop_loss
                    should_exit, reason, exit_qty = exit_engine.evaluate_exit(
                        open_position, ltp, current_time, current_atr
                    )
                    # Phase 5: Persist Trailing SL to disk immediately to prevent amnesia on reboot
                    if open_position.stop_loss != old_stop_loss:
                        logger.info("TRAILING SL MOVED for %s: %.2f -> %.2f. Saving to disk.", sym, old_stop_loss, open_position.stop_loss)
                        _save_positions(active_positions)
                        if not broker.paper_mode:
                            asyncio.create_task(update_exchange_sl(broker, open_position))

            if should_exit:
                qty_to_close = exit_qty if exit_qty else open_position.quantity
                is_live = not broker.paper_mode   # accurately reflect the broker's operating mode

                if is_live:
                    logger.info("EXIT %s %s for %s (%s) [LIVE]", open_position.side, qty_to_close, sym, reason)
                    if not ORDER_LIMITER.allow(broker.BROKER_ID):
                        logger.warning("EXIT order rate-limited for %s — will retry on next tick.", sym)
                        return  # Return immediately so position isn't removed; it will retry on next tick
                    else:
                        is_opt = "CE" in open_position.symbol or "PE" in open_position.symbol
                        exit_side = OrderSide.SELL if is_opt else (OrderSide.SELL if open_position.side == 1 else OrderSide.BUY)
                        
                        # Marketable Limit Order (MLO) Bypass for Exit
                        if is_opt:
                            if exit_side == OrderSide.SELL:
                                mlo_price = round(ltp * 0.95, 2) # Sell 5% below LTP to guarantee fill
                            else:
                                mlo_price = round(ltp * 1.05, 2) # Buy 5% above LTP
                            order_type = OrderType.LIMIT
                        else:
                            mlo_price = 0.0
                            order_type = OrderType.MARKET
                            
                        exit_req = OrderRequest(
                            symbol=open_position.symbol,
                            quantity=qty_to_close,
                            side=exit_side,
                            order_type=order_type,
                            price=mlo_price
                        )
                        try:
                            exit_req = validator.validator.validate(exit_req)
                            # Lock the position: prevents duplicate exit signals while iceberg executes
                            open_position.is_exiting = True
                            full_exit = (exit_qty is None or exit_qty >= open_position.quantity)
                            asyncio.create_task(background_iceberg_exit(
                                broker, exit_req, base_symbol_key, open_position.side, open_position.entry_price,
                                exit_price=ltp, qty_to_close=qty_to_close, full_exit=full_exit
                            ))
                        except ValidationError as ve:
                            logger.error("EXIT order validation failed for %s: %s", base_symbol_key, ve)
                            audit.log(AuditEvent.VALIDATION_ERROR,
                                      {"symbol": sym, "reason": str(ve)}, severity="WARNING")
                            return # Retry on next tick
                else:
                    # Paper Trading: synchronous execution is safe — guaranteed fill
                    logger.info("EXIT %s %s for %s (%s) [PAPER]", open_position.side, qty_to_close, sym, reason)

                    # Record PnL & update dashboard state (paper mode: immediate, no confirmation needed)
                    pnl = (ltp - open_position.entry_price) * qty_to_close * open_position.side

                    if settings.get("active_strategy") == "MARL_Ultra":
                        try:
                            from trading_bot.strategies.marl_strategy import record_trade_outcome
                            record_trade_outcome(pnl)
                        except Exception as mrl_exc:
                            logger.error("Failed to record MARL trade outcome: %s", mrl_exc)

                    portfolio_risk.update_pnl(pnl, risk_manager.current_equity)
                    trade_side = "LONG" if open_position.side == 1 else "SHORT"
                    risk_manager.record_trade(TradeRecord(
                        open_position.symbol, trade_side,
                        open_position.entry_price, ltp, pnl, datetime.now(_IST).isoformat()
                    ))
                    is_opt = "CE" in open_position.symbol or "PE" in open_position.symbol
                    state_action = "SELL" if is_opt else ("SELL" if open_position.side == 1 else "BUY")
                    record_trade(open_position.symbol, state_action, ltp, datetime.now(_IST).isoformat(), qty=qty_to_close)
                    update_equity(risk_manager.current_equity, risk_manager.daily_pnl)
                    alerter.send_exit_alert(sym, open_position.side, qty_to_close, ltp, pnl, reason)

                    if exit_qty is None or exit_qty >= open_position.quantity:
                        del active_positions[sym]
                    else:
                        open_position.quantity -= exit_qty

                    _save_positions(active_positions)

            # ----------------------------------------------------------------
            # 1.5. Pyramiding (Scaling In) for remaining positions
            # ----------------------------------------------------------------
            if sym in active_positions:
                pos = active_positions[sym]
                
                # Dynamically apply settings
                should_scale = False
                scale_reason = ""
                
                if settings.get("enablePyramiding", False) or settings.get("enable_pyramiding", False):
                    pyramid_sizer.pct_trigger = settings.get("scalePct", settings.get("scale_pct", 0.2))
                    pyramid_sizer.max_scales = settings.get("maxScales", settings.get("max_scales", 2))
                    should_scale, scale_reason = pyramid_sizer.evaluate_scale(pos, ltp)
                
                # Safety gate: skip if a background scale-in is already in flight for
                # this position. scales_done only increments once
                # background_iceberg_scale's broker round-trip completes, so without
                # this lock a burst of ticks within that window can re-satisfy
                # evaluate_scale() and spawn multiple concurrent scale-in orders.
                if should_scale and pos.is_scaling:
                    should_scale = False

                if should_scale:
                    scale_qty = int(settings.get("quantity", 2)) // 2  # Scale in with half of base qty or 1 lot
                    if scale_qty < 1: scale_qty = 1

                    is_live = not broker.paper_mode
                    side_str = "BUY" if pos.side == 1 else "SELL"

                    if is_live:
                        logger.info("PYRAMID SCALE %d: %s %d %s @ %.2f (%s) [LIVE]",
                                    pos.scales_done + 1, side_str, scale_qty, sym, ltp, scale_reason)

                        if not ORDER_LIMITER.allow(broker.BROKER_ID):
                            logger.warning("SCALE order rate-limited for %s — skipping.", sym)
                        else:
                            is_opt = "CE" in pos.symbol or "PE" in pos.symbol
                            scale_req = OrderRequest(
                                symbol=pos.symbol,
                                quantity=scale_qty,
                                side=OrderSide.BUY if is_opt else (OrderSide.BUY if pos.side == 1 else OrderSide.SELL),
                            )
                            try:
                                scale_req = validator.validator.validate(scale_req)
                                # Lock the position: prevents duplicate scale-in signals while iceberg executes
                                pos.is_scaling = True
                                asyncio.create_task(background_iceberg_scale(
                                    broker, scale_req, pos, side_str, ltp
                                ))
                            except ValidationError as ve:
                                logger.error("Scale order validation failed for %s: %s", sym, ve)
                    else:
                        logger.info("PYRAMID SCALE %d: %s %d %s @ %.2f (%s) [PAPER]", 
                                    pos.scales_done + 1, side_str, scale_qty, sym, ltp, scale_reason)
                        pos.quantity += scale_qty
                        pos.scales_done += 1
                    
                    _save_positions(active_positions)

        # ----------------------------------------------------------------
        # 2. Aggregate tick → check for new candle bar
        # ----------------------------------------------------------------
        try:
            aggregator.add_tick(tick)
            
            import time
            current_time_sec = time.time()
            # ZERO-LATENCY HFT TRIGGER: Evaluate every 200ms for ultra-fast execution
            if current_time_sec - last_eval_time >= 0.2:
                last_eval_time = current_time_sec

                # Settings already loaded at top of on_tick (cached, no disk I/O)
                strategy_name = settings.get("active_strategy", "institutional_momentum")
                is_live = not broker.paper_mode
                target_pct = settings.get("target_pct", 500.0) / 100.0
                sl_pct = settings.get("stoploss_pct", 15.0) / 100.0

                # AI confidence threshold: stricter for enhanced_ai strategy
                min_confidence = 0.85 if strategy_name == "enhanced_ai" else 0.60

                for s in aggregator.symbols:
                    if s in active_positions or s in _evaluating_symbols:
                        continue  # Only one open position per symbol, and block concurrent evaluations
                        
                    _evaluating_symbols.add(s)
                    try:
                        df = aggregator.get_latest_dataframe(s)
                        if len(df) < 50:  # Need enough warmup bars
                            continue

                        # ── AI Confidence Gate (computed first, needed by premium engine) ──
                        # Limit to last 100 rows to prevent severe CPU bottleneck and latency spikes
                        features = compute_features(df.tail(100)).tail(1)
                        
                        enable_ai = settings.get("enable_ai_filter", False)
                        if enable_ai and ai_filter.is_trained:
                            pred_df = await asyncio.to_thread(ai_filter.predict, features)
                            confidence = pred_df["confidence"].iloc[-1] if not features.empty else 1.0
                        else:
                            # Fallback to pure rules-based trading if model is not trained or disabled
                            confidence = 1.0

                        # ── Run selected strategy ──────────────────────────
                        # We run the strategy first before applying the AI gate to avoid spamming logs 
                        # on every tick when no actual signal was generated.
                        
                        # ── Premium Strategy: uses engine directly for option selection ──
                        if strategy_name == "premium":
                            instrument = s.replace("NSE:", "").replace("-INDEX", "").replace("-EQ", "")
                            premium_engine = PremiumSignalEngine(
                                instrument=instrument,
                                capital=risk_manager.current_equity,
                                min_ai_confidence=min_confidence,
                            )
                            sig: PremiumSignal = await asyncio.to_thread(
                                premium_engine.evaluate, df, confidence
                            )

                            if not sig.is_tradeable:
                                # premium engine handles its own rejection logs
                                continue

                            latest_signal = 1 if sig.direction == "BUY_CALL" else -1
                            option_symbol = sig.option.symbol if sig.option else s
                            lot_size      = sig.option.lot_size if sig.option else 1
                            entry_symbol  = option_symbol
                            logger.info(
                                "PREMIUM SIGNAL %s | %s | Layers: %s | Composite: %.0f%%",
                                sig.direction, option_symbol, sig.layers_passed, sig.confidence * 100
                            )
                        else:
                            signals_data = await asyncio.to_thread(
                                registry.run_strategy, strategy_name, df, **settings
                            )
                            if isinstance(signals_data, tuple):
                                signals, _ = signals_data
                            else:
                                signals = signals_data
                            latest_signal = signals.iloc[-1]
                            entry_symbol  = s
                            lot_size      = 1
                            
                            if latest_signal != 0:
                                if confidence < min_confidence:
                                    logger.info(
                                        "AI rejected %s signal for %s — confidence %.2f < threshold %.2f",
                                        strategy_name, s, confidence, min_confidence
                                    )
                                    continue

                            # Auto-map to Options if it's an Index trade
                            if latest_signal != 0 and ("INDEX" in s or s.startswith("NSE:NIFTY") or s.startswith("BSE:SENSEX")):
                                try:
                                    from trading_bot.strategies.premium_selection.options_selector import select_option
                                    instrument = s.replace("NSE:", "").replace("BSE:", "").replace("-INDEX", "").replace("-EQ", "")
                                    opt_dir: Literal['CE', 'PE'] = "CE" if latest_signal == 1 else "PE"
                                    opt = select_option(instrument, ltp, opt_dir, itm_strikes=1)
                                    entry_symbol = opt.symbol
                                    lot_size = opt.lot_size
                                    logger.info("Auto-mapped %s %s signal to Option: %s", instrument, opt_dir, entry_symbol)
                                except Exception as e:
                                    logger.error("Failed to auto-map option for %s: %s", s, e)
                            

                        if latest_signal == 0:
                            continue

                        # ── Macro Sentiment Blocks ─────────────────────────
                        from shared.sentiment import get_current_sentiment
                        sentiment_data = get_current_sentiment()
                        sentiment_score = sentiment_data.get("score", 0.0)

                        if latest_signal == 1 and sentiment_score < -0.5:
                            logger.warning("Macro Filter Blocked BUY for %s: Highly Bearish Sentiment (%.2f)", s, sentiment_score)
                            alerter.send_alert(f"🛑 **Trade Blocked**\n\nSymbol: {s}\nReason: Highly Bearish Sentiment ({sentiment_score})")
                            continue
                            
                        if latest_signal == -1 and sentiment_score > 0.5:
                            logger.warning("Macro Filter Blocked SELL for %s: Highly Bullish Sentiment (%.2f)", s, sentiment_score)
                            alerter.send_alert(f"🛑 **Trade Blocked**\n\nSymbol: {s}\nReason: Highly Bullish Sentiment ({sentiment_score})")
                            continue

                        # ── Risk Manager Gate ──────────────────────────────
                        current_volatility = df["close"].pct_change().std() * 100
                        
                        if settings.get("maxDailyLossPct"):
                            portfolio_risk.max_daily_dd_pct = float(settings.get("maxDailyLossPct", 0.05))
                        elif settings.get("max_daily_loss_pct"):
                            portfolio_risk.max_daily_dd_pct = float(settings.get("max_daily_loss_pct", 0.05))

                        if settings.get("max_trades_per_day") is not None:
                            risk_manager.config.max_trades_per_day = int(settings.get("max_trades_per_day", 1))
                        elif settings.get("maxDailyTrades") is not None:
                            risk_manager.config.max_trades_per_day = int(settings.get("maxDailyTrades", 1))
                        elif settings.get("max_daily_trades") is not None:
                            risk_manager.config.max_trades_per_day = int(settings.get("max_daily_trades", 1))
                            
                        is_trading_allowed, halt_reason = portfolio_risk.is_trading_allowed(risk_manager.current_equity)
                        if not is_trading_allowed:
                            logger.warning("Portfolio Risk Halt for %s: %s", s, halt_reason)
                            continue
                            
                        # ── Compute Entry Premium, Stop Loss, and Target ──
                        entry_premium = df["close"].iloc[-1] # Default to index price
                        side_str = "BUY CALL" if latest_signal == 1 else "BUY PUT"
                        
                        is_option_trade = "CE" in entry_symbol or "PE" in entry_symbol
                        
                        if is_option_trade:
                            # Fetch the Live Option Premium to calculate P&L correctly
                            try:
                                live_quotes = broker.get_market_data([entry_symbol])
                                if entry_symbol in live_quotes and live_quotes[entry_symbol].ltp > 0:
                                    entry_premium = live_quotes[entry_symbol].ltp
                                else:
                                    logger.warning("Could not fetch live option premium for %s. Using index price as fallback.", entry_symbol)
                            except Exception as e:
                                logger.error("Error fetching live option premium: %s", e)
                                
                            # Option buying means we buy premium, so target is UP and SL is DOWN
                            sl_price = entry_premium * (1 - sl_pct)
                            tgt_price = entry_premium * (1 + target_pct)
                        else:
                            sl_price = entry_premium * (1 - sl_pct) if latest_signal == 1 else entry_premium * (1 + sl_pct)
                            tgt_price = entry_premium * (1 + target_pct) if latest_signal == 1 else entry_premium * (1 - target_pct)

                        # ── Compute Quantity ──
                        if "quantity" in settings and int(settings["quantity"]) > 0:
                            total_shares = int(settings["quantity"])
                        else:
                            # Calculate position size based on risk amount
                            total_shares = risk_manager.calculate_position_size(entry_premium, sl_price, ai_confidence=confidence) or 1
                            
                        # AUDIT FIX: Apply Capital Protection Position Sizing Multiplier
                        # Automatically reduces size (50% or 25%) during losing streaks
                        cap_protect_multiplier = portfolio_risk.get_position_multiplier()
                        total_shares = int(total_shares * cap_protect_multiplier)
                        
                        # ULTIMATE UPGRADE: Dynamic Capital Compounding Engine
                        # Scales lot size as equity grows — capped at realistic 5x max
                        current_equity = risk_manager.current_equity
                        init_cap = risk_manager.initial_capital
                        if settings.get("enable_compounding", True) and current_equity > init_cap:
                            max_compound_cap = float(settings.get("max_compounding_multiplier", 5.0))
                            compound_factor = min(max_compound_cap, max(1.0, current_equity / init_cap))
                            total_shares = int(total_shares * compound_factor)
                            
                        number_of_lots = max(1, total_shares // lot_size)
                        total_quantity = number_of_lots * lot_size
                        
                        # SECURITY SANITY GUARD: Max order value limit protection
                        # Root-cause fix: options entries are placed as a
                        # Marketable Limit Order at entry_premium * 1.05 (see
                        # mlo_price below) to guarantee execution, but this
                        # check used to compare against the raw entry_premium
                        # — the real worst-case notional the broker could fill
                        # at was up to 5% higher than what this cap validated,
                        # silently allowing up to 5% over the configured
                        # max_order_value. Use the same worst-case fill price
                        # (mlo pad) the actual order will be placed at.
                        max_order_val = settings.get("max_order_value", 500000.0)
                        worst_case_fill_price = entry_premium * 1.05 if is_option_trade else entry_premium
                        if (worst_case_fill_price * total_quantity) > max_order_val:
                            logger.warning(f"SECURITY GUARD: Order value ₹{worst_case_fill_price * total_quantity:,.2f} (worst-case fill) exceeds limit ₹{max_order_val:,.2f}. Capping lots.")
                            total_quantity = (int(max_order_val // worst_case_fill_price) // lot_size) * lot_size
                        
                        if cap_protect_multiplier < 1.0:
                            logger.info(f"CAPITAL PROTECTION ACTIVE: Scaling position size to {cap_protect_multiplier*100}% ({total_quantity} shares)")

                        # ── Risk Manager Gate ─────────────────────────────────────────
                        # Pass actual rupee risk so the per-trade risk limit is enforced
                        actual_risk_amount = abs(entry_premium - sl_price) * total_quantity
                        allowed, reject_reason = risk_manager.can_trade(
                            symbol=s,
                            risk_amount=actual_risk_amount,
                            ai_confidence=confidence,
                            current_volatility=current_volatility,
                        )
                        if not allowed:
                            logger.info("Trade BLOCKED for %s: %s", s, reject_reason)
                            continue

                        if not settings.get("auto_trade_enabled", True):
                            logger.info("Auto trades disabled (Manual Mode) - Skipping execution for %s.", s)
                            continue

                        # ── Execute (Live or Paper) ────────────────────────
                        if is_live:
                            logger.info(
                                "ENTRY %s %s quantity=%d @ %.2f | SL=%.2f | TGT=%.2f | AI=%.0f%% [LIVE]",
                                side_str, entry_symbol, total_quantity, entry_premium, sl_price, tgt_price, confidence * 100
                            )
                            # Rate-limit guard
                            if not ORDER_LIMITER.allow(broker.BROKER_ID):
                                logger.warning(
                                    "Order rate limit reached for broker %s — skipping entry on %s.",
                                    broker.BROKER_ID, s,
                                )
                                continue
                            # Input validation gate
                            is_option = "CE" in entry_symbol or "PE" in entry_symbol
                            
                            # Marketable Limit Order (MLO) Bypass for Options
                            # We send a Limit order 5% worse than LTP to guarantee execution while bypassing Broker Market Blocks
                            mlo_price = round(entry_premium * 1.05, 2) if is_option else 0.0
                            order_type = OrderType.LIMIT if is_option else OrderType.MARKET
                            
                            entry_req = OrderRequest(
                                symbol=entry_symbol,
                                quantity=total_quantity,
                                side=OrderSide.BUY if is_option_trade else (OrderSide.BUY if latest_signal == 1 else OrderSide.SELL),
                                order_type=order_type,
                                price=mlo_price
                            )
                            try:
                                entry_req = validator.validator.validate(entry_req)
                                # Create position object for tracking
                                pos_obj = Position(
                                    symbol=entry_symbol,
                                    side=latest_signal,
                                    entry_price=entry_premium,
                                    quantity=total_quantity,
                                    entry_time=current_time,
                                    highest_price=entry_premium,
                                    lowest_price=entry_premium,
                                    stop_loss=sl_price,
                                    target=tgt_price,
                                    lot_size=lot_size,
                                )
                                active_positions[s] = pos_obj
                                _save_positions(active_positions)
                                
                                asyncio.create_task(background_iceberg_entry(
                                    broker, entry_req, pos_obj, s, is_option_trade
                                ))
                            except ValidationError as ve:
                                logger.error("Entry order validation failed for %s: %s", s, ve)
                                audit.log(AuditEvent.VALIDATION_ERROR,
                                          {"symbol": s, "reason": str(ve)}, severity="WARNING")
                                continue
                        else:
                            logger.info(
                                "ENTRY %s %s qty=%d @ %.2f | SL=%.2f | TGT=%.2f | AI=%.0f%% [PAPER]",
                                side_str, entry_symbol, total_quantity, entry_premium, sl_price, tgt_price, confidence * 100
                            )

                        # ── Send Telegram Alert ────────────────────────────
                        alerter.send_trade_alert(entry_symbol, side_str, total_quantity // lot_size, entry_premium, confidence)

                        # ── Track position ─────────────────────────────────
                        if not is_live:
                            # Paper trades add position synchronously here
                            pos_obj = Position(
                                symbol=entry_symbol,
                                side=latest_signal,
                                entry_price=entry_premium,
                                quantity=total_quantity,
                                entry_time=current_time,
                                highest_price=entry_premium,
                                lowest_price=entry_premium,
                                stop_loss=sl_price,
                                target=tgt_price,
                                lot_size=lot_size,
                            )
                            # We MUST key active_positions by the base symbol (INDEX) so that on_tick hits!
                            active_positions[s] = pos_obj
                            _save_positions(active_positions)
                            
                            # Persist Paper Entry to state.db
                            state_action = "BUY" if is_option_trade else ("BUY" if latest_signal == 1 else "SELL")
                            record_trade(entry_symbol, state_action, entry_premium, datetime.now(_IST).isoformat(), qty=total_quantity)
                            update_equity(risk_manager.current_equity, risk_manager.daily_pnl)

                        if strategy_name == "institutional_momentum" and s in momentum_strategies:
                            momentum_strategies[s].open_trade(
                                entry_price=entry_premium, 
                                stop_loss=sl_price, 
                                total_lots=total_quantity, 
                                direction=latest_signal
                            )
                    finally:
                        _evaluating_symbols.discard(s)

        except Exception as exc:
            logger.exception("Error processing tick: %s", exc)

        # ----------------------------------------------------------------
        # 3. Calculate Unrealized M2M PNL and update dashboard
        # ----------------------------------------------------------------
        import time
        global _m2m_last_update
            
        if time.time() - _m2m_last_update > 0.05:
            total_unrealized_pnl = 0.0
            
            for position in active_positions.values():
                entry_premium = position.entry_price
                total_quantity = position.quantity
                
                # Get the live premium for this specific position
                if position.symbol == sym:
                    current_premium = ltp
                else:
                    # Look up the latest premium from our data aggregator
                    option_data = aggregator.get_latest_dataframe(position.symbol)
                    if not option_data.empty:
                        current_premium = option_data["close"].iloc[-1]
                    else:
                        current_premium = entry_premium
                
                # P&L = (Current Premium - Entry Premium) * Total Quantity
                premium_difference = current_premium - entry_premium
                position_pnl = premium_difference * total_quantity * position.side
                
                total_unrealized_pnl += position_pnl
            
            total_portfolio_pnl = risk_manager.daily_pnl + total_unrealized_pnl
            update_equity(risk_manager.current_equity + total_unrealized_pnl, total_portfolio_pnl)
            _m2m_last_update = time.time()

    async def sync_broker_state():
        if not hasattr(broker, 'get_positions'):
            return
        logger.info("Re-syncing with broker state after WebSocket reconnect...")
        try:
            broker_positions = broker.get_positions()
            broker_pos_dict = {p.symbol: p for p in broker_positions}

            # Fetch the order book once so any position found flat below can be
            # reconciled against what the broker actually filled, instead of
            # guessing. A position that closed while we were disconnected may
            # have hit its target, been closed manually, or gapped through the
            # stop-loss to a worse price — assuming it always hit the SL price
            # can under- or over-state PNL and mis-trigger (or mask) the
            # drawdown circuit breaker.
            try:
                order_book = broker.get_order_book()
            except Exception as ob_exc:
                logger.error("Could not fetch order book during reconciliation: %s", ob_exc)
                order_book = []

            for sym, local_pos in list(active_positions.items()):
                # If local says we have a position, but broker says we don't or it's flat
                if sym not in broker_pos_dict or broker_pos_dict[sym].quantity == 0:
                    logger.warning("STATE MISMATCH: Local position %s exists but broker is flat. Resolving locally.", sym)

                    # Match the same exit-side convention the live exit path uses
                    # (options are always closed with a SELL; index/equity closes
                    # opposite the position side).
                    is_opt = "CE" in sym or "PE" in sym
                    exit_side = OrderSide.SELL if is_opt else (OrderSide.SELL if local_pos.side == 1 else OrderSide.BUY)

                    ltp_actual = None
                    for entry in order_book:
                        if (entry.symbol == sym and entry.side == exit_side
                                and entry.status == OrderStatus.COMPLETE and entry.traded_price > 0):
                            ltp_actual = entry.traded_price
                            break

                    if ltp_actual is not None:
                        logger.info(
                            "RECONCILIATION: resolved actual exit price for %s to %.2f from the broker order book.",
                            sym, ltp_actual,
                        )
                    else:
                        # Last-resort estimate only — the broker order book had
                        # no matching completed fill (e.g. order history already
                        # rolled off, or the position was closed by something
                        # outside this order book). Loudly flag this as an
                        # estimate rather than silently recording it as fact.
                        ltp_actual = local_pos.stop_loss
                        logger.error(
                            "RECONCILIATION: could not find %s's actual closing fill in the broker "
                            "order book — falling back to the stop-loss price (%.2f) as an ESTIMATE. "
                            "Recorded PNL for this trade may be inaccurate; verify manually.",
                            sym, ltp_actual,
                        )

                    pnl = (ltp_actual - local_pos.entry_price) * local_pos.quantity * local_pos.side
                    
                    portfolio_risk.update_pnl(pnl, risk_manager.current_equity)
                    trade_side = "LONG" if local_pos.side == 1 else "SHORT"
                    risk_manager.record_trade(TradeRecord(
                        sym, trade_side,
                        local_pos.entry_price, ltp_actual, pnl, datetime.now(_IST).isoformat()
                    ))
                    
                    is_opt = "CE" in sym or "PE" in sym
                    state_action = "SELL" if is_opt else ("SELL" if local_pos.side == 1 else "BUY")
                    record_trade(sym, state_action, ltp_actual, datetime.now(_IST).isoformat(), qty=local_pos.quantity)
                    
                    del active_positions[sym]
                    _save_positions(active_positions)
        except Exception as e:
            logger.error("Failed to sync broker state: %s", e)

    logger.info("Starting live stream for symbols: %s", ", ".join(symbols))
    await broker.stream_quotes(symbols, on_tick, on_reconnect=sync_broker_state)


# Root-cause fix (Medium audit finding): "the container restart policy
# stacks on top of the engine's own internal auto-restart loop with no
# shared backoff/cooldown" — this loop used to sleep a flat 10s after
# every crash regardless of how many times it had just crashed in a
# row. If something is fundamentally broken (a bad settings.json, a
# permanently-unreachable broker), a flat delay produces a tight
# restart-storm hammering logs and the broker's API, uncoordinated with
# Docker's own outer restart policy if this process ever exits the
# container entirely. These two small, pure helpers compute an
# escalating backoff (doubling from a 10s base up to a 5-minute cap on
# consecutive fast failures) and decide when to reset that escalation
# back to the base delay (once the bot has run successfully for a
# sustained period) — pulled out of the loop below so they're
# unit-testable without needing to actually run the live engine.
_RETRY_BASE_DELAY_S = 10
_RETRY_MAX_DELAY_S = 300
_RETRY_SUSTAINED_UPTIME_RESET_S = 300


def _compute_retry_delay(consecutive_fast_failures: int) -> int:
    """Delay before the next restart attempt, given how many consecutive
    *fast* failures (crashes before a sustained-uptime reset) have
    happened so far, including this one."""
    if consecutive_fast_failures <= 0:
        return _RETRY_BASE_DELAY_S
    return min(_RETRY_MAX_DELAY_S, _RETRY_BASE_DELAY_S * (2 ** (consecutive_fast_failures - 1)))


def _should_reset_failure_count(run_duration_s: float) -> bool:
    """True if the bot ran long enough before this crash that it should be
    treated as a fresh start rather than another rapid crash-loop cycle."""
    return run_duration_s >= _RETRY_SUSTAINED_UPTIME_RESET_S


def _build_preload_failure_alert(failed_symbols: List[str]) -> str:
    """Operator-facing alert text for symbols that started with an empty
    candle buffer after historical preload — pulled out of the preload
    loop in run_live_bot() so it's unit-testable without needing a live
    broker connection."""
    return (
        f"⚠️ **Historical Preload Incomplete**\n\nSymbols starting with an "
        f"empty candle buffer: {', '.join(failed_symbols)}\n\n"
        f"These symbols will not generate signals until enough live "
        f"ticks accumulate to satisfy strategy warmup requirements."
    )


if __name__ == "__main__":
    # Read symbols from settings — no more hardcoded list
    _boot_settings = {}
    _settings_path = Path(__file__).resolve().parents[1] / "config" / "settings.json"
    if _settings_path.is_file():
        try:
            _boot_settings = json.loads(_settings_path.read_text(encoding="utf-8"))
        except Exception:
            pass

    SYMBOLS: List[str] = _boot_settings.get(
        "symbols",
        ["NSE:NIFTY50-INDEX"],   # sensible default if not set in settings
    )
    logger.info("Starting live bot with symbols: %s", SYMBOLS)
    import time
    _consecutive_fast_failures = 0
    while True:
        _run_started_at = time.monotonic()
        try:
            asyncio.run(run_live_bot(SYMBOLS))
        except KeyboardInterrupt:
            logger.info("Live bot terminated by user")
            audit.log(AuditEvent.BOT_STOP, {"reason": "user_interrupt"})
            break
        except Exception as e:
            _run_duration = time.monotonic() - _run_started_at
            if _should_reset_failure_count(_run_duration):
                _consecutive_fast_failures = 0
            _consecutive_fast_failures += 1
            _delay = _compute_retry_delay(_consecutive_fast_failures)
            logger.error(
                "FATAL CRASH in Live Bot: %s. Ran for %.0fs before crashing "
                "(%d consecutive fast failures). Auto-restarting in %ds...",
                e, _run_duration, _consecutive_fast_failures, _delay,
            )
            time.sleep(_delay)
