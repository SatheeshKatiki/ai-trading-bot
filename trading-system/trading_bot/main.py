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
import logging.handlers
import os
import sys
import threading
import time

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
from shared.state import update_equity, record_trade, record_journal_entry

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
from trading_bot.reconciliation import compute_reconciliation
from trading_bot.strategies.registry import registry
from trading_bot.strategies.premium_selection import (
    PremiumSignalEngine, PremiumSignal, generate_signals as premium_signals
)
from trading_bot.strategies.momentum_strategy import MomentumStrategy
from trading_bot.strategies.drl_strategy import generate_signals as drl_signals
from trading_bot.strategies.marl_strategy import generate_signals as marl_signals
from trading_bot.strategies.ema9_rsi_momentum import STRATEGY_NAME as EMA9_RSI_MOMENTUM_STRATEGY_NAME

_m2m_last_update: float = 0.0

# Import AI / Risk / Exit / Alert Modules
from shared.ai import TradeFilterModel, compute_features
from shared.risk import RiskManager, RiskConfig, TradeRecord, resolve_initial_stop, resolve_min_confidence, find_stale_positions, seconds_since_any_tick, resolve_option_atr
from shared.instruments import normalize_instrument
from shared.market_hours import is_market_open, is_before_eod_cutoff
from shared.exits import SmartExitEngine, Position, PyramidSizer
from shared.alerts import alerter
from trading_bot.portfolio_risk import PortfolioRiskEngine
from trading_bot.iceberg_manager import IcebergManager

# Security layer
from shared.security import install_log_sanitizer, audit, validator
from shared.security.audit_log import AuditEvent
from shared.security.rate_limiter import ORDER_LIMITER, DATA_LIMITER
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

# Same directory shared/singleton_lock.py already uses for process-lifecycle
# artifacts (run/{name}.pid, run/{name}.lock) -- the heartbeat file lives
# alongside them for the same reason: not application config, a fact about
# this running process. Read by api_bridge.py's main_process_watchdog.
_HEARTBEAT_PATH = Path(__file__).resolve().parents[1] / "run" / "main_heartbeat.txt"
_HEARTBEAT_WRITE_INTERVAL_S = 15.0

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
        # Root-cause fix (found running live paper trading): quantity/price
        # fields can arrive here as numpy int64/float64 (position sizing
        # runs through pandas/numpy internally) — json.dump only accepts
        # native Python types and raises on a bare numpy scalar. int()/
        # float() unwrap both numpy scalars and native types identically,
        # so this is a no-op for the already-native case.
        data = {
            sym: {
                "symbol": p.symbol,
                "side": int(p.side),
                "quantity": int(p.quantity),
                "entry_price": float(p.entry_price),
                "entry_time": getattr(p, "entry_time", ""),
                "highest_price": float(getattr(p, "highest_price", p.entry_price)),
                "lowest_price": float(getattr(p, "lowest_price", p.entry_price)),
                "stop_loss": float(getattr(p, "stop_loss", 0.0)),
                "target": float(getattr(p, "target", 0.0)),
                "is_partially_booked": bool(getattr(p, "is_partially_booked", False)),
                "scales_done": int(getattr(p, "scales_done", 0)),
                "sl_order_id": getattr(p, "sl_order_id", None)
            } for sym, p in positions_copy.items()
        }
        
        # Phase 7: Atomic Write prevents torn/corrupted state files on crash
        _POSITIONS_PATH.parent.mkdir(parents=True, exist_ok=True)
        temp_fd, temp_path = tempfile.mkstemp(dir=_POSITIONS_PATH.parent, prefix="active_positions_tmp_", suffix=".json")
        try:
            with os.fdopen(temp_fd, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=4)
            # Root-cause fix (found running live paper trading, 2026-08-03):
            # os.replace() can fail with WinError 5 "Access is denied" when
            # another process (e.g. an api_bridge dashboard request reading
            # this same file) transiently has it open at the exact moment of
            # the rename -- a real occurrence, not hypothetical, and exactly
            # the failure mode docs/GO_NO_GO_CHECKLIST.md's §2.2 has zero
            # tolerance for. This is a transient OS-level lock contention
            # issue, not a real error, so a short bounded retry is
            # appropriate here (unlike most of this codebase's error
            # handling, which deliberately fails fast rather than masking
            # real problems).
            import time as _time_mod
            last_exc = None
            for attempt in range(5):
                try:
                    os.replace(temp_path, _POSITIONS_PATH)
                    last_exc = None
                    break
                except OSError as replace_exc:
                    last_exc = replace_exc
                    _time_mod.sleep(0.05 * (attempt + 1))
            if last_exc is not None:
                raise last_exc
        except Exception as e:
            if os.path.exists(temp_path):
                os.unlink(temp_path)
            raise e

    except Exception as e:
        logger.error("Failed to save active positions: %s", e)


def _write_heartbeat(path: Path) -> None:
    """Atomically write the current `time.time()` to `path`. Pulled out of
    `heartbeat_writer`'s loop (run_live_bot) so the actual write behavior
    is directly testable without spinning up the real event loop -- same
    reasoning as `_compute_retry_delay`/`_should_reset_failure_count`
    below. Same tempfile+os.replace pattern as `_save_positions` above.

    Root-cause fix (found live, 2026-08-26): this used to skip
    `_save_positions`'s bounded retry on the theory that a heartbeat write
    losing a single race against a reader is fine (the next write is <=
    `_HEARTBEAT_WRITE_INTERVAL_S` away) -- true for main_process_watchdog's
    behavior, but it still meant every transient WinError 5 ("Access is
    denied", from api_bridge.py's main_process_watchdog reading this same
    file mid-replace -- identical mechanism to `_save_positions`'s
    documented 2026-08-03 finding) surfaced as a logged ERROR for what is,
    by design, a harmless miss. Applying the same short bounded retry
    _save_positions already uses removes that noise without changing the
    "a miss is tolerable" policy -- it just makes a miss rarer.
    """
    import tempfile
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_fd, temp_path = tempfile.mkstemp(dir=path.parent, prefix="heartbeat_tmp_", suffix=".txt")
    try:
        with os.fdopen(temp_fd, "w", encoding="utf-8") as f:
            f.write(str(time.time()))
        last_exc = None
        for attempt in range(5):
            try:
                os.replace(temp_path, path)
                last_exc = None
                break
            except OSError as replace_exc:
                last_exc = replace_exc
                time.sleep(0.05 * (attempt + 1))
        if last_exc is not None:
            raise last_exc
    except Exception:
        if os.path.exists(temp_path):
            os.unlink(temp_path)
        raise


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


# Handled entirely inside main.py's entry loop via a dedicated branch
# (PremiumSignalEngine) — the only `active_strategy` value that never goes
# through `registry.run_strategy()`, so it doesn't need to be a registered
# strategy name to be valid.
_STRATEGIES_OUTSIDE_REGISTRY = frozenset({"premium"})

# The single current `active_strategy` value we've already warned about, if
# any — not a growing set, since only one value is ever "current" at a time.
# Reset to None whenever the current value is valid, so a bad value that
# reappears later (after being corrected in between) warns again instead of
# staying silenced forever.
_last_bad_active_strategy: Optional[str] = None


def _validate_active_strategy(strategy_name: Optional[str]) -> None:
    """Warn loudly, once per distinct bad value, if `active_strategy` isn't
    a real, tradeable strategy name.

    Root-cause fix (found 2026-08-07 audit, docs/STRATEGY_AUDIT_2026-08-07.md
    §4.7): `registry.run_strategy()` raises `ValueError` for an unregistered
    name, but that's caught by a broad `try/except Exception` deep in the
    entry loop and just logged — a typo, or a strategy that failed to
    auto-register due to an import error, would make the engine raise and
    retry on every single tick, forever, while still reporting healthy at
    the process/health-check level and generating zero real trade signals.
    Called once per actual settings (re)load, not per-tick, so this can't
    itself become a source of per-tick log spam or CPU cost.
    """
    global _last_bad_active_strategy
    if (
        not strategy_name
        or strategy_name in _STRATEGIES_OUTSIDE_REGISTRY
        or strategy_name in registry.registered_strategies
    ):
        _last_bad_active_strategy = None
        return
    if strategy_name == _last_bad_active_strategy:
        return
    _last_bad_active_strategy = strategy_name
    logger.critical(
        "active_strategy=%r is not a registered strategy (known: %s, plus %s). "
        "The engine will raise and silently retry on every tick until this is "
        "corrected — no real trade signals will be generated in the meantime.",
        strategy_name,
        sorted(registry.registered_strategies),
        sorted(_STRATEGIES_OUTSIDE_REGISTRY),
    )


def _should_abort_missing_option_mapping(
    strategy_name: str, option_mapping_required: bool, option_mapping_succeeded: bool
) -> bool:
    """True if this tick's entry must be skipped because it needed an
    option mapped but none was successfully selected.

    Root-cause fix (found 2026-08-07 audit, docs/STRATEGY_AUDIT_2026-08-07.md
    §1.1): a failed `select_option()` call used to fall through with
    `entry_symbol` still equal to the raw underlying index symbol — every
    downstream check (`is_option_trade`, `resolve_initial_stop`, order
    placement) would then treat the INDEX's own price as if it were an
    option premium, a direct violation of the option-buying-only mandate.
    This system only ever buys options; if mapping to one was required for
    this tick and didn't succeed, the entry must be skipped rather than
    falling back to trading the raw index.

    The `"premium"` strategy is excluded: it builds `entry_symbol` via its
    own `PremiumSignalEngine` path (already gated by `sig.is_tradeable`,
    which `continue`s before this check is ever reached), not the
    `option_mapping_required`/`option_mapping_succeeded` pair this
    function checks.
    """
    return strategy_name != "premium" and option_mapping_required and not option_mapping_succeeded


def _has_valid_spot_price_for_option_mapping(ltp: float) -> bool:
    """False for any spot price that must not reach
    `options_selector.select_option()` (and, downstream, `calculate_greeks`'
    `math.log(spot / strike)`).

    Root-cause fix (found live, 2026-08-25): a spot price of `0.0` — a
    malformed/keepalive tick, not a real trade — was passed straight into
    `math.log(spot / strike)`, raising `ValueError: expected a positive
    input, got 0.0`, logged as a generic "Failed to auto-map option"
    error. That's a data-validity problem, not a mapping failure; reject
    it at this boundary so it never reaches the Black-Scholes math at all.
    A negative ltp (never legitimately observed, but not structurally
    impossible from a malformed feed message) is rejected for the same
    reason.
    """
    return ltp > 0


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

        # ── Option stop-loss architecture ──────────────────────────────
        # Premium-banded initial stop for option buying. `stoploss_pct`
        # above still applies to non-option (index/equity) trades; these
        # replace it for anything with CE/PE in the symbol.
        # See shared/risk/option_stop_loss.py.
        "option_sl_bands": [
            {"lower": 0,   "upper": 10,   "min_points": 2,  "max_points": 3},
            {"lower": 10,  "upper": 20,   "min_points": 3,  "max_points": 5},
            {"lower": 20,  "upper": 50,   "min_points": 5,  "max_points": 8},
            {"lower": 50,  "upper": 100,  "min_points": 10, "max_points": 15},
            {"lower": 100, "upper": 150,  "min_points": 15, "max_points": 20},
            {"lower": 150, "upper": 250,  "min_points": 20, "max_points": 30},
        ],
        # How to pick within a band: interpolate | min | mid | max.
        "option_sl_band_mode": "interpolate",
        # Above the table the stop is a percentage of premium, tapering
        # from start_pct to end_pct (12% at ₹250 = ₹30, continuous with
        # the last fixed band's max_points).
        "option_sl_dynamic": {
            "lower": 250.0, "start_pct": 12.0, "end_pct": 10.0, "taper_to": 500.0,
        },
        # A stop may never risk more than this share of the premium.
        "option_sl_max_pct_of_premium": 60.0,
        "option_sl_tick_size": 0.05,
        # Derive option quantity from the stop distance instead of the
        # fixed `quantity` setting, so risk-per-trade stays constant as
        # the banded stop varies with premium.
        "option_risk_based_sizing": True,

        # ── Strike selection: ATM preferred, ITM as a liquidity fallback,
        # never OTM. select_option() hard-clamps this regardless of what's
        # configured here — see MIN/MAX_ITM_STRIKES in options_selector.py.
        "option_strike_itm_offset": 1,

        # ── Multi-instrument focus (shared/risk/instrument_focus.py) ──
        # NIFTY/SENSEX trade at the active strategy's own confidence bar;
        # everything else (BANKNIFTY/FINNIFTY) needs at least this bar.
        "focus_instruments": ["NIFTY", "SENSEX"],
        "secondary_instrument_min_confidence": 0.85,

        # ── Tick-staleness watchdog (observability only) ──────────────
        # Warn when an open position's underlying hasn't ticked in this
        # many seconds — see shared/risk/tick_staleness.py.
        "tick_staleness_warning_s": 90.0,
        # Warn when NO watched symbol has ticked in this many seconds
        # during market hours, regardless of open positions.
        "engine_stall_warning_s": 90.0,
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
                _validate_active_strategy(defaults.get("active_strategy"))
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


async def _reconcile_broker_state(broker, active_positions, risk_manager, portfolio_risk) -> None:
    """Re-syncs locally tracked positions against the broker's own record
    after a WebSocket reconnect. Pulled out of run_live_bot's
    `sync_broker_state` closure (which is now a thin wrapper calling this
    with its own captured `broker`/`active_positions`/`risk_manager`/
    `portfolio_risk`) so it's directly testable without running the real
    live engine -- closing docs/GO_NO_GO_CHECKLIST.md's §2.6, which had
    zero test coverage for the reconnect-while-holding-a-position path
    even after 5 real WebSocket disconnects in a single session
    (2026-08-13) -- none of which happened to coincide with an open
    position, so it stayed live-untested too.

    Root-cause fix (found live, 2026-08-05): in paper mode there is no
    real broker account to reconcile against -- FyersBroker.get_positions()
    unconditionally returns [] in paper mode (it has no persistent state
    of its own across restarts), so this reconciliation would see EVERY
    locally tracked position as "the broker reports it flat" on every
    single WebSocket (re)connect, including the very first connect right
    after a fresh process start. Live result: a real open position was
    force-closed at its stop-loss price as an ESTIMATE within seconds of
    a routine restart, even though nothing had actually happened to it.
    In paper mode active_positions.json IS the authoritative position
    state -- there is nothing to reconcile it against, so skip entirely.
    """
    if not hasattr(broker, 'get_positions'):
        return
    if getattr(broker, 'paper_mode', False):
        logger.info("Skipping broker-state reconciliation — paper mode has no real broker account to reconcile against.")
        return
    logger.info("Re-syncing with broker state after WebSocket reconnect...")
    try:
        broker_positions = broker.get_positions()

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

        # Pure decision logic lives in trading_bot.reconciliation so it's
        # unit-testable without a live broker or this function's state —
        # see test_reconciliation.py.
        for result in compute_reconciliation(active_positions, broker_positions, order_book):
            logger.warning("STATE MISMATCH: Local position %s exists but broker is flat. Resolving locally.", result.symbol)
            if result.is_estimate:
                logger.error(
                    "RECONCILIATION: could not find %s's actual closing fill in the broker "
                    "order book — falling back to the stop-loss price (%.2f) as an ESTIMATE. "
                    "Recorded PNL for this trade may be inaccurate; verify manually.",
                    result.symbol, result.exit_price,
                )
            else:
                logger.info(
                    "RECONCILIATION: resolved actual exit price for %s to %.2f from the broker order book.",
                    result.symbol, result.exit_price,
                )

            portfolio_risk.update_pnl(result.pnl, risk_manager.current_equity)
            risk_manager.record_trade(TradeRecord(
                result.symbol, result.trade_side,
                result.entry_price, result.exit_price, result.pnl, datetime.now(_IST).isoformat()
            ))
            record_trade(result.symbol, result.state_action, result.exit_price, datetime.now(_IST).isoformat(), qty=result.quantity)

            del active_positions[result.local_key]
            _save_positions(active_positions)
    except Exception as e:
        logger.error("Failed to sync broker state: %s", e)


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

    # Root-cause fix (found live, 2026-08-05): equity is NOT a daily
    # counter like pnl -- it's the account's actual cumulative balance and
    # must always carry forward across restarts, regardless of which day
    # it was last updated. Previously only daily_pnl was restored here;
    # RiskManager/PortfolioRiskEngine both silently defaulted their
    # equity tracking back to the static initial_capital on every
    # restart, discarding all real cumulative gains/losses.
    saved_equity = saved_state.get("equity")
    if saved_equity is None:
        saved_equity = _initial_capital

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
    risk_manager = RiskManager(initial_capital=_initial_capital, daily_pnl=saved_pnl, current_equity=saved_equity)

    # Root-cause fix (found live, 2026-08-05): RiskManager.trades_today is a
    # pure in-memory list, always starting empty -- unlike daily_pnl/equity
    # above, it was never seeded from persisted state. Any restart during a
    # trading day (a routine bug-fix redeploy, a crash-retry, anything)
    # silently reset the day's trade count to 0, letting the engine place
    # MORE real trades than the configured daily cap intended. Confirmed
    # live: restarting to deploy the fix above let 3 additional trades
    # through even though today's real 3-trade cap had already been hit
    # hours earlier.
    _today_trades = load_state(reload_trades=True).get("trades", [])
    _executed_today = _count_trades_already_executed_today(_today_trades, datetime.now(_IST).strftime("%Y-%m-%d"))
    if _executed_today:
        risk_manager.trades_today = [
            TradeRecord("restored", "SELL", 0.0, 0.0, 0.0, "") for _ in range(_executed_today)
        ]
        logger.info(
            "Restored %d trade(s) already executed today into the daily trade cap (was about to reset to 0).",
            _executed_today,
        )
    ai_filter = TradeFilterModel()
    exit_engine = SmartExitEngine(atr_multiplier=1.5, partial_booking_pct=50.0)
    pyramid_sizer = PyramidSizer(pct_trigger=0.2, max_scales=2)
    # max_consecutive_losses=7 matches PortfolioRiskEngine's own documented
    # design (get_position_multiplier(): 3-4 losses -> half size, 5-6 ->
    # quarter size, 7+ -> halt). This call site previously passed 3, the
    # pre-gradual-scaling halt threshold -- with that, _evaluate_risk()
    # halted trading completely at exactly the loss count where size
    # reduction was supposed to begin, so the gradual-scaling behavior the
    # class was built for could never actually engage. Found during the
    # 2026-08-03 production-readiness audit.
    portfolio_risk = PortfolioRiskEngine(max_daily_dd_pct=5.0, max_weekly_dd_pct=10.0, max_consecutive_losses=7, initial_capital=_initial_capital, current_capital=saved_equity)
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
    # time.monotonic() of the most recent tick per underlying symbol.
    # Feeds tick_staleness_watchdog() below — see shared/risk/tick_staleness.py
    # for why this exists (on_tick, and everything inside it including exit
    # management, only ever runs when a real tick arrives; nothing else
    # detects a feed that has simply gone quiet).
    _last_tick_at: Dict[str, float] = {}
    # (timestamp, last_known_premium) per option symbol — see the
    # exit-check block in on_tick() for why this exists.
    _option_premium_cache: Dict[str, tuple[float, float]] = {}
    _OPTION_PREMIUM_FETCH_INTERVAL_S = 1.0
    # Separate from _option_premium_cache (which only ever holds a real
    # premium, never None -- the exit-check path above assigns its cached
    # value straight into a price used for SL/target math, so a None
    # sneaking in there would crash it). This one just remembers the last
    # time a given entry candidate's premium fetch FAILED, so repeated
    # candidates for the same symbol within the same throttle window skip
    # the API call entirely instead of retrying every single time -- the
    # gap that mattered most in practice: near/after market close, quotes
    # for many strikes never succeed at all, so a success-only cache never
    # engages and every candidate re-hits the API.
    _entry_premium_failure_cache: Dict[str, float] = {}
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
            # `sym` here is the base/underlying key (e.g. "NSE:NIFTY50-INDEX"),
            # not the traded instrument -- checking it for "CE"/"PE" would
            # always be False for an option position. Use the actual traded
            # symbol from the order request instead.
            is_opt = "CE" in exit_req.symbol or "PE" in exit_req.symbol
            # `side` encodes the directional bet for options (CE=+1/PE=-1),
            # not "long vs short the contract" -- this system only ever BUYS
            # options, so the side-flip below is only correct for a genuine
            # short position in the underlying (see the matching fix and
            # comment on the paper-mode exit path above).
            pnl = (ltp_actual - entry_price) * actual_exit_qty * (1 if is_opt else side)

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
        _last_tick_at[sym] = time.monotonic()
        # Populated by the exit-check block below (section 1) when it fetches
        # an option's live premium, so section 3's M2M calc can reuse it
        # instead of hitting the broker API a second time for the same
        # symbol on the same tick.
        _tick_option_premiums: Dict[str, float] = {}
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
        # 🚨🚨 Emergency Stop (panic-exit) — force-close everything
        # ----------------------------------------------------------------
        # Root-cause fix (found live, 2026-08-05): see
        # emergency_flatten_all_positions()'s own docstring for the full
        # incident. Checked ahead of the plain `is_active` halt below on
        # purpose -- `is_active=False` only freezes processing (existing
        # positions are left completely unmanaged, SL/target included),
        # which is the wrong behavior for a panic exit that needs to
        # actively flatten everything, not just stop touching it.
        if settings.get("emergency_stop", False):
            if active_positions:
                await emergency_flatten_all_positions("panic-exit triggered via dashboard")
            return

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

            # Fallback: an index/underlying tick also carries an open option
            # position keyed by that same base symbol. The live stream only
            # ever subscribes to the underlying, never to option contracts
            # directly, so this is the ONLY path by which an option
            # position's exit conditions get evaluated at all — without it,
            # a filled option entry can never be exited by SL/target/
            # trailing/anything else (root-caused 2026-08-03: a position
            # sat unmanaged for a full session while its premium round-
            # tripped through both target and stop-loss within 5 minutes).
            if base_sym == sym:
                open_position = position
                base_symbol_key = base_sym
                break

        if open_position:
            # ── Safety gate: skip if a background exit is already in flight ──
            if open_position.is_exiting:
                return

            is_opt_pos = "CE" in open_position.symbol or "PE" in open_position.symbol

            # For an option position, `ltp` here is the underlying index's
            # price (that's what the tick is), not the option's own price —
            # comparing an index level against option-premium SL/target
            # values would be meaningless. Fetch the option's real live
            # premium on demand (same call already used at entry) and use
            # THAT for every exit-side decision below.
            #
            # Root-cause fix (found live, 2026-08-05): this used to fetch on
            # EVERY tick unconditionally. Ticks can arrive far faster than
            # Fyers' real rate limit (DATA_LIMITER's own comment: ~100/min),
            # and there's nothing else in this codebase throttling
            # get_market_data calls (DATA_LIMITER exists but was never
            # wired to anything — a gap flagged but deliberately not acted
            # on during the 2026-08-03 audit). Live result: a position sat
            # completely unmanaged for the better part of a session because
            # every single fetch attempt came back empty, almost certainly
            # from self-inflicted rate limiting. Throttling to at most one
            # real fetch per second per symbol, reusing the last known
            # premium in between, fixes the self-inflicted overload while
            # keeping SL/target checks running on effectively every tick
            # (a ~1s-old premium is more than adequate for this purpose,
            # and infinitely better than never fetching successfully at
            # all).
            exit_check_price = ltp
            if is_opt_pos:
                now_mono = time.monotonic()
                cached = _option_premium_cache.get(open_position.symbol)
                if cached and (now_mono - cached[0]) < _OPTION_PREMIUM_FETCH_INTERVAL_S:
                    exit_check_price = cached[1]
                    _tick_option_premiums[open_position.symbol] = exit_check_price
                else:
                    try:
                        # Root-cause fix (found live, 2026-08-13): this call
                        # used to run synchronously, unwrapped, directly on
                        # the event loop -- the vendored SDK makes it with
                        # no request timeout, so a hung connection (not just
                        # a fast-failing DNS error) could block every tick,
                        # every position, and the watchdogs themselves for
                        # as long as it hung. Confirmed root cause of a
                        # ~39-minute total engine freeze correlated with a
                        # DNS failure burst. asyncio.to_thread keeps a still-
                        # slow call (now bounded by fyers_broker.py's
                        # request timeout) from blocking anything else;
                        # DATA_LIMITER.allow() is the throttle flagged but
                        # never wired since the 2026-08-03 audit -- both are
                        # defense in depth on top of this call's own
                        # existing per-symbol cache above.
                        if not DATA_LIMITER.allow("fyers"):
                            opt_quotes = {}
                        else:
                            opt_quotes = await asyncio.to_thread(
                                broker.get_market_data, [open_position.symbol]
                            )
                        opt_quote = opt_quotes.get(open_position.symbol)
                        if opt_quote and opt_quote.ltp > 0:
                            exit_check_price = opt_quote.ltp
                            _option_premium_cache[open_position.symbol] = (now_mono, exit_check_price)
                            _tick_option_premiums[open_position.symbol] = exit_check_price
                            # Feed this fresh premium sample into the same
                            # CandleAggregator already building the index's
                            # own candles, keyed by the option's own
                            # contract symbol -- builds a real premium-scale
                            # candle history for resolve_option_atr() below.
                            # See shared/risk/option_atr.py and
                            # docs/STRATEGY_AUDIT_2026-08-07.md §2.1. Reuses
                            # the exact same aggregation/interval-flooring
                            # logic already live for index symbols rather
                            # than a second, duplicate candle builder.
                            aggregator.add_tick({
                                "timestamp": time.time(),
                                "symbol": open_position.symbol,
                                "ltp": exit_check_price,
                                "volume": 0,
                            })
                        elif cached:
                            # Fresh fetch failed but we have a recent-enough
                            # stale value — better than skipping the check
                            # entirely.
                            exit_check_price = cached[1]
                            _tick_option_premiums[open_position.symbol] = exit_check_price
                        else:
                            logger.warning(
                                "Exit check skipped for %s — could not fetch live option premium this tick.",
                                open_position.symbol,
                            )
                            return
                    except Exception as exc:
                        if cached:
                            exit_check_price = cached[1]
                            _tick_option_premiums[open_position.symbol] = exit_check_price
                        else:
                            logger.warning("Exit check failed to fetch premium for %s: %s", open_position.symbol, exc)
                            return

            # The UNDERLYING index's own candles. Bound on EVERY path, not
            # just the non-option one below.
            #
            # Root-cause fix (found 2026-08-09 institutional_momentum deep
            # audit): this assignment used to live only inside the `else`
            # (non-option) branch, while the institutional_momentum exit
            # branch further down reads `df` unconditionally (to resample
            # 5-min candles for TieredExitManager and to build AI-confidence
            # features). Python makes `df` local to the WHOLE of on_tick the
            # moment it is assigned anywhere in it, so on an OPTION position
            # — which is every position this strategy ever takes — that read
            # hit an unbound local and raised UnboundLocalError. The broad
            # `except Exception` at the end of on_tick logged it and moved
            # on, so the engine looked healthy while TieredExitManager was
            # never once consulted: no partial booking, no runner trail, no
            # exhaustion lock, no AI early exit. Only the hard-SL/target
            # interceptors above (which run BEFORE this point) and the
            # sentiment breaker ever closed a position. Same scoping defect
            # class as the 2026-08-02 `datetime` shadowing bug in this very
            # function. See docs/STRATEGY_IMPROVEMENT_BACKLOG.md #13.
            df = aggregator.get_latest_dataframe(sym)

            if is_opt_pos:
                # Root-cause fix (found 2026-08-07 audit,
                # docs/STRATEGY_AUDIT_2026-08-07.md §2.1): this used to
                # compute current_atr from the UNDERLYING INDEX's own
                # candles (aggregator.get_latest_dataframe(sym), sym being
                # the index symbol the tick carries — the live feed never
                # subscribes to option contracts directly) and feed that
                # index-point-scale value straight into the trailing-stop
                # math against position.highest_price, which for an option
                # is the PREMIUM. Spot is for entry-signal generation only;
                # every option risk/exit decision must be sized in the
                # option's own premium units. option_df is the option
                # contract's OWN candle series, built from the fresh
                # premium samples fed into `aggregator` just above —
                # resolve_option_atr() computes a real ATR(14) from it once
                # enough history exists, bridging with the same
                # premium-banded proxy the initial stop uses during the
                # unavoidable cold-start window right after entry. See
                # shared/risk/option_atr.py.
                option_df = aggregator.get_latest_dataframe(open_position.symbol)
                atr_decision = resolve_option_atr(option_df, exit_check_price, settings)
                current_atr = atr_decision.atr_value
            else:
                # Proper 14-bar rolling ATR (not single-candle range which is too noisy)
                if not df.empty and len(df) >= 2:
                    tr_series = (df["high"] - df["low"]).abs()
                    current_atr = tr_series.rolling(min(14, len(df))).mean().iloc[-1]
                    if pd.isna(current_atr) or current_atr <= 0:
                        current_atr = exit_check_price * 0.005
                else:
                    current_atr = exit_check_price * 0.005

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
                    if is_opt_pos:
                        if exit_check_price >= open_position.target:
                            should_exit = True
                            reason = f"Hard TP Reached (LTP {exit_check_price:.2f} >= TGT {open_position.target:.2f})"
                            exit_qty = open_position.quantity
                    else:
                        if open_position.side == 1 and exit_check_price >= open_position.target:
                            should_exit = True
                            reason = f"Hard TP Reached (LTP {exit_check_price:.2f} >= TGT {open_position.target:.2f})"
                            exit_qty = open_position.quantity
                        elif open_position.side == -1 and exit_check_price <= open_position.target:
                            should_exit = True
                            reason = f"Hard TP Reached (LTP {exit_check_price:.2f} <= TGT {open_position.target:.2f})"
                            exit_qty = open_position.quantity

                # --- Hard Stop Loss Interceptor ---
                if not should_exit and open_position.stop_loss and open_position.stop_loss > 0:
                    if is_opt_pos:
                        if exit_check_price <= open_position.stop_loss:
                            should_exit = True
                            reason = f"Hard SL Hit (LTP {exit_check_price:.2f} <= SL {open_position.stop_loss:.2f})"
                            exit_qty = open_position.quantity
                    else:
                        if open_position.side == 1 and exit_check_price <= open_position.stop_loss:
                            should_exit = True
                            reason = f"Hard SL Hit (LTP {exit_check_price:.2f} <= SL {open_position.stop_loss:.2f})"
                            exit_qty = open_position.quantity
                        elif open_position.side == -1 and exit_check_price >= open_position.stop_loss:
                            should_exit = True
                            reason = f"Hard SL Hit (LTP {exit_check_price:.2f} >= SL {open_position.stop_loss:.2f})"
                            exit_qty = open_position.quantity

            if not should_exit:
                strategy_name = settings.get("active_strategy", "institutional_momentum")
            
                if strategy_name == "institutional_momentum" and sym in momentum_strategies:
                    m_strategy = momentum_strategies[sym]

                    # ── EOD square-off (this branch bypasses SmartExitEngine) ──
                    # Root-cause fix (2026-08-09 deep audit): the 15:15 IST
                    # intraday square-off is implemented inside
                    # SmartExitEngine.evaluate_exit, and this strategy takes
                    # the branch that never calls it. TieredExitManager has
                    # no time-based rule of its own — by design, its Phase 2
                    # runner is explicitly uncapped — so an
                    # institutional_momentum position had nothing at all to
                    # close it at the end of the session. For an intraday
                    # system buying near-expiry options that means carrying
                    # overnight gap risk and a full night of theta on a
                    # contract that may expire the next day. Reuses
                    # `exit_engine.eod_exit_time` rather than re-declaring
                    # the cutoff so both paths keep one definition.
                    _t_only = current_time.split(" ")[-1] if " " in current_time else current_time
                    _eod_reached = _t_only >= exit_engine.eod_exit_time
                    if _eod_reached:
                        should_exit = True
                        reason = "Time-based EOD Exit"
                        exit_qty = open_position.quantity

                    # Requires 5min dataframe for TieredExitManager.
                    #
                    # The final resampled bar is the one still FORMING (with
                    # label='right'/closed='right' a bar stamped 09:20 covers
                    # 09:15-09:20, so at 09:17 it exists but is incomplete).
                    # TieredExitManager's Phase 3 rule is "exit when a candle
                    # CLOSES on the wrong side of the runner EMA" and its own
                    # code comment states it evaluates the last COMPLETED
                    # candle. Passing the forming bar silently degraded that
                    # into "exit the instant price TOUCHES the wrong side",
                    # since ticks arrive ~1/s — turning a close-confirmation
                    # rule into an intrabar-noise trigger and cutting runners
                    # early. Dropping the incomplete bar restores the
                    # documented semantics and makes `iloc[-1]` inside the
                    # engine mean the same thing live as it does on the
                    # complete-bar history a backtest replays.
                    df_5min = df.resample('5min', label='right', closed='right').agg({
                        'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last', 'volume': 'sum'
                    }).dropna() if not df.empty else df
                    if len(df_5min) > 1:
                        df_5min = df_5min.iloc[:-1]

                    # Fetch AI Confidence for early exit
                    features = compute_features(df.tail(60)).tail(1)
                    confidence = ai_filter.predict(features)["confidence"].iloc[-1] if (ai_filter.is_trained and not features.empty) else 1.0

                    decision = None if _eod_reached else m_strategy.manage_active_trades(
                        exit_check_price,
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
                        open_position, exit_check_price, current_time, current_atr
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
                                mlo_price = round(exit_check_price * 0.95, 2) # Sell 5% below LTP to guarantee fill
                            else:
                                mlo_price = round(exit_check_price * 1.05, 2) # Buy 5% above LTP
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
                                exit_price=exit_check_price, qty_to_close=qty_to_close, full_exit=full_exit
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
                    # `side` encodes the directional bet for options (CE=+1/PE=-1),
                    # not "long vs short the contract" -- this system only ever BUYS
                    # options, so a bought PUT's own premium still has to rise for a
                    # profit, exactly like a bought CALL. Applying `* side` inverted
                    # every PUT trade's PnL (root-caused 2026-08-03: a stop-loss hit
                    # was logged as a profit). The side-flip is only correct for a
                    # genuine short position in the underlying (is_opt_pos is False).
                    pnl = (exit_check_price - open_position.entry_price) * qty_to_close * (1 if is_opt_pos else open_position.side)

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
                        open_position.entry_price, exit_check_price, pnl, datetime.now(_IST).isoformat()
                    ))
                    is_opt = "CE" in open_position.symbol or "PE" in open_position.symbol
                    state_action = "SELL" if is_opt else ("SELL" if open_position.side == 1 else "BUY")
                    record_trade(open_position.symbol, state_action, exit_check_price, datetime.now(_IST).isoformat(), qty=qty_to_close)
                    record_journal_entry(
                        symbol=open_position.symbol,
                        strategy_name=strategy_name or "EMA9/RSI Momentum",
                        direction="BUY",
                        entry_price=open_position.entry_price,
                        exit_price=exit_check_price,
                        qty=qty_to_close,
                        pnl=pnl,
                        ai_feedback=f"Exit: {reason}. Smart Trailing Stoploss managed.",
                        tags=f"{'PROFIT' if pnl > 0 else 'LOSS'},{strategy_name or 'EMA9_RSI'},{'CE' if 'CE' in open_position.symbol else 'PE'}",
                        trade_date=datetime.now(_IST).strftime("%Y-%m-%d %H:%M:%S")
                    )
                    update_equity(risk_manager.current_equity, risk_manager.daily_pnl)
                    alerter.send_exit_alert(sym, open_position.side, qty_to_close, exit_check_price, pnl, reason)

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
                    # Same fix as the exit check above: this is an option position,
                    # so it must be evaluated against its own premium, not the
                    # underlying index price the tick carries.
                    should_scale, scale_reason = pyramid_sizer.evaluate_scale(pos, exit_check_price)
                
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
                                    pos.scales_done + 1, side_str, scale_qty, sym, exit_check_price, scale_reason)

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
                                    broker, scale_req, pos, side_str, exit_check_price
                                ))
                            except ValidationError as ve:
                                logger.error("Scale order validation failed for %s: %s", sym, ve)
                    else:
                        logger.info("PYRAMID SCALE %d: %s %d %s @ %.2f (%s) [PAPER]",
                                    pos.scales_done + 1, side_str, scale_qty, sym, exit_check_price, scale_reason)
                        pos.quantity += scale_qty
                        pos.scales_done += 1
                    
                    _save_positions(active_positions)

        # ----------------------------------------------------------------
        # 2. Aggregate tick → check for new candle bar
        # ----------------------------------------------------------------
        try:
            aggregator.add_tick(tick)

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
                base_min_confidence = 0.85 if strategy_name == "enhanced_ai" else 0.60

                for s in aggregator.symbols:
                    if s in active_positions or s in _evaluating_symbols:
                        continue  # Only one open position per symbol, and block concurrent evaluations

                    _evaluating_symbols.add(s)
                    try:
                        # ── Per-instrument confidence gate ──────────────
                        # "Mainly focus NIFTY and SENSEX": those trade at
                        # whatever bar the active strategy already sets;
                        # BANKNIFTY/FINNIFTY need a stricter one (default
                        # 0.85 — the same bar enhanced_ai already uses).
                        # Position sizing and every risk cap stay uniform
                        # across all four instruments — this only changes
                        # which signals are allowed through at all. See
                        # shared/risk/instrument_focus.py.
                        instrument_key = normalize_instrument(s)
                        min_confidence = resolve_min_confidence(
                            instrument_key, base_min_confidence, settings
                        )
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
                            # Root-cause fix: this used to derive `instrument`
                            # inline without stripping a "BSE:" prefix, so a
                            # SENSEX signal through this branch built the key
                            # "BSE:SENSEX" instead of "SENSEX", silently
                            # failing to match INSTRUMENT_CONFIG. Reusing
                            # instrument_key (shared.instruments.normalize_
                            # instrument, already computed above) closes that
                            # gap and keeps this in sync with the auto-map
                            # branch below instead of maintaining a second
                            # copy of the same remap.
                            premium_engine = PremiumSignalEngine(
                                instrument=instrument_key,
                                capital=risk_manager.current_equity,
                                min_ai_confidence=min_confidence,
                                itm_strikes=settings.get("option_strike_itm_offset", 1),
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
                            option_mapping_required = latest_signal != 0 and ("INDEX" in s or s.startswith("NSE:NIFTY") or s.startswith("BSE:SENSEX"))
                            option_mapping_succeeded = False
                            if option_mapping_required:
                                # Root-cause fix (found live, 2026-08-25): a
                                # spot price of 0.0 (a malformed/keepalive
                                # tick, not a real trade) fed straight into
                                # calculate_greeks()'s math.log(spot / strike)
                                # and blew up with "expected a positive
                                # input, got 0.0" -- a data-validity problem
                                # masquerading as a mapping failure. Reject
                                # it at the boundary instead of letting an
                                # invalid spot price reach the Black-Scholes
                                # math at all; option_mapping_succeeded stays
                                # False so the existing
                                # _should_abort_missing_option_mapping guard
                                # below correctly skips this entry, same as
                                # any other mapping failure.
                                if not _has_valid_spot_price_for_option_mapping(ltp):
                                    logger.warning(
                                        "Skipping option auto-map for %s -- invalid spot price from tick (ltp=%.4f)",
                                        s, ltp,
                                    )
                                else:
                                    try:
                                        from trading_bot.strategies.premium_selection.options_selector import select_option
                                        # instrument_key (shared.instruments.
                                        # normalize_instrument) already resolved
                                        # the same NIFTY50->NIFTY / NIFTYBANK->
                                        # BANKNIFTY remap this used to redo inline
                                        # — see instrument_key's computation above
                                        # for why that's now one function instead
                                        # of two independently-maintained copies.
                                        opt_dir: Literal['CE', 'PE'] = "CE" if latest_signal == 1 else "PE"
                                        opt = select_option(
                                            instrument_key, ltp, opt_dir,
                                            itm_strikes=settings.get("option_strike_itm_offset", 1),
                                        )
                                        entry_symbol = opt.symbol
                                        lot_size = opt.lot_size
                                        option_mapping_succeeded = True
                                        logger.info("Auto-mapped %s %s signal to Option: %s", instrument_key, opt_dir, entry_symbol)
                                    except Exception as e:
                                        logger.error("Failed to auto-map option for %s: %s", s, e)


                        if latest_signal == 0:
                            continue

                        # Root-cause fix (found 2026-08-07 audit,
                        # docs/STRATEGY_AUDIT_2026-08-07.md §1.1): a failed
                        # select_option() call used to fall through with
                        # entry_symbol still equal to the raw underlying
                        # index symbol — every downstream check
                        # (is_option_trade, resolve_initial_stop, order
                        # placement) would then treat the INDEX's own price
                        # as if it were an option premium, a direct
                        # violation of the option-buying-only mandate. This
                        # system only ever buys options; if mapping to one
                        # was required for this tick and didn't succeed,
                        # skip the entry outright rather than falling back
                        # to trading the raw index.
                        if _should_abort_missing_option_mapping(strategy_name, option_mapping_required, option_mapping_succeeded):
                            continue

                        # ── Market-hours gate (NEW entries only) ───────────
                        # Root-cause fix (found live 2026-08-06): nothing
                        # previously stopped a new entry from executing
                        # outside real NSE trading hours -- a real broker
                        # enforces this structurally, paper mode did not.
                        # See shared/market_hours.py and the 2026-08-06
                        # anomaly_log.md entry for the live incident this
                        # closes. Deliberately placed only in the entry
                        # path -- already-open positions keep full exit
                        # management (trailing/SL/EOD/partial-book/
                        # pyramiding) regardless of the time of day; this
                        # gate is never consulted there.
                        if not is_market_open(settings=settings):
                            continue

                        # ── EOD entry cutoff (NEW entries only) ────────────
                        # Root-cause fix (found live 2026-08-07): a signal
                        # could still open a brand-new position seconds
                        # before SmartExitEngine's eod_exit_time (15:15
                        # IST), only to be force-closed on the very same or
                        # next tick -- a round-trip under 250ms that was
                        # never real market exposure. Three of these burned
                        # through the entire daily trade cap in one session,
                        # blocking every genuine signal for the rest of the
                        # day. See shared/market_hours.py::
                        # is_before_eod_cutoff and the 2026-08-07
                        # anomaly_log.md entry. Same scope rule as the
                        # market-hours gate above: NEW entries only, exit
                        # management (including this exact EOD exit) is
                        # untouched for already-open positions.
                        if not is_before_eod_cutoff(settings=settings):
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
                        
                        # Fallback defaults are on the same 0-100 percentage
                        # scale _evaluate_risk() compares against (e.g. 5.0 ==
                        # 5%) -- they were previously 0.05, which would have
                        # meant an effective 0.05% drawdown halt if this key
                        # were ever missing from settings.json. Not currently
                        # reachable (the key is always present), but fixed for
                        # consistency during the 2026-08-03 audit.
                        if settings.get("maxDailyLossPct"):
                            portfolio_risk.max_daily_dd_pct = float(settings.get("maxDailyLossPct", 5.0))
                        elif settings.get("max_daily_loss_pct"):
                            portfolio_risk.max_daily_dd_pct = float(settings.get("max_daily_loss_pct", 5.0))

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
                            # Root-cause fix (found running live paper trading):
                            # entry_premium defaults to the INDEX close price
                            # (tens of thousands), not an option premium (tens
                            # to low hundreds). The old fallback silently kept
                            # that index price as if it were the option's
                            # premium whenever a live quote wasn't available,
                            # which fed a ~100x-too-large entry_premium into
                            # every downstream calculation (SL/target, order
                            # value, position sizing) — this alone produced a
                            # nonsensical ₹1.66M order-value that the max-
                            # order-value guard then capped down to qty=0,
                            # and the code placed a phantom zero-quantity
                            # "entry" anyway. Skip the trade entirely instead:
                            # a real trade needs a real premium, and a wrong
                            # premium is worse than no trade.
                            #
                            # Root-cause fix (found live, 2026-08-05): this
                            # fetched unconditionally on every candidate
                            # entry, unlike the exit-check path below which
                            # was already throttled for exactly this reason
                            # (2026-08-04). Near market close, elevated
                            # volatility drives rapid re-evaluation across
                            # many different strikes, each firing its own
                            # unthrottled get_market_data() call -- live
                            # result: a burst of ~250 rate-limit/empty-body
                            # errors from Fyers' /quotes endpoint in a two-
                            # minute window right at close. Reusing the same
                            # per-symbol cache as the exit path closes the
                            # gap consistently instead of patching it twice.
                            live_premium = None
                            now_mono = time.monotonic()
                            cached_entry = _option_premium_cache.get(entry_symbol)
                            last_failure = _entry_premium_failure_cache.get(entry_symbol)
                            throttled_recent_failure = False
                            if cached_entry and (now_mono - cached_entry[0]) < _OPTION_PREMIUM_FETCH_INTERVAL_S:
                                live_premium = cached_entry[1]
                            elif last_failure is not None and (now_mono - last_failure) < _OPTION_PREMIUM_FETCH_INTERVAL_S:
                                live_premium = None  # recently failed for this symbol -- don't re-hit the API yet
                                throttled_recent_failure = True
                            else:
                                try:
                                    # See the exit-check path above (~line
                                    # 1024) for the full 2026-08-13
                                    # root-cause note: to_thread keeps a
                                    # still-slow call from blocking the
                                    # event loop, DATA_LIMITER.allow() is
                                    # the throttle flagged since 2026-08-03
                                    # and never wired until now.
                                    if not DATA_LIMITER.allow("fyers"):
                                        live_quotes = {}
                                    else:
                                        live_quotes = await asyncio.to_thread(
                                            broker.get_market_data, [entry_symbol]
                                        )
                                    if entry_symbol in live_quotes and live_quotes[entry_symbol].ltp > 0:
                                        live_premium = live_quotes[entry_symbol].ltp
                                        _option_premium_cache[entry_symbol] = (now_mono, live_premium)
                                    elif cached_entry:
                                        live_premium = cached_entry[1]
                                    else:
                                        _entry_premium_failure_cache[entry_symbol] = now_mono
                                except Exception as e:
                                    logger.error("Error fetching live option premium: %s", e)
                                    _entry_premium_failure_cache[entry_symbol] = now_mono

                            if live_premium is None:
                                if not throttled_recent_failure:
                                    logger.warning(
                                        "Could not fetch live option premium for %s — skipping this entry "
                                        "rather than pricing it off the index level.", entry_symbol,
                                    )
                                continue

                            entry_premium = live_premium

                            # ── Premium-banded initial stop-loss ──────────
                            # Option buying means we buy premium, so the stop
                            # sits BELOW entry for both CE and PE.
                            #
                            # The flat `stoploss_pct` this replaced could not
                            # express option risk: the live 0.45% setting put
                            # the stop ₹0.54 under a ₹120 premium — inside the
                            # spread, so the position was stopped out by noise
                            # rather than by being wrong. See
                            # shared/risk/option_stop_loss.py for the table and
                            # the reasoning.
                            sl_decision = resolve_initial_stop(entry_premium, settings)
                            if not sl_decision.is_tradeable:
                                # Premium too small to carry a stop that is
                                # both positive and a real distance from
                                # entry — trading it would mean an instant
                                # stop-out dressed up as risk management.
                                logger.warning(
                                    "Skipping %s: premium ₹%.2f is too small to place a "
                                    "meaningful stop (would be ₹%.2f).",
                                    entry_symbol, entry_premium, sl_decision.sl_price,
                                )
                                continue
                            sl_price = sl_decision.sl_price

                            # NO FIXED PROFIT TARGET. 0.0 means "unlimited
                            # upside" to every downstream exit check
                            # (main.py's hard-TP interceptor and
                            # SmartExitEngine both guard on `target > 0`).
                            # Profit management belongs entirely to the
                            # trailing stop and the Smart Exit Engine, which
                            # take over the moment this position is opened.
                            tgt_price = 0.0

                            logger.info(
                                "SL BAND %s | premium ₹%.2f -> SL ₹%.2f (risk ₹%.2f/unit, %.2f%%, %s)%s",
                                sl_decision.band_label, entry_premium, sl_price,
                                sl_decision.sl_points, sl_decision.sl_pct,
                                sl_decision.method,
                                " [CLAMPED by max_pct_of_premium]" if sl_decision.clamped else "",
                            )
                        else:
                            sl_price = entry_premium * (1 - sl_pct) if latest_signal == 1 else entry_premium * (1 + sl_pct)
                            tgt_price = entry_premium * (1 + target_pct) if latest_signal == 1 else entry_premium * (1 - target_pct)

                        # ── Compute Quantity ──
                        # Root cause for the option branch: a fixed `quantity`
                        # setting makes rupee risk a function of the stop
                        # width, which is exactly backwards. With premium-
                        # banded stops the stop distance now varies ~15x
                        # across the table (₹2 to ₹30), so a fixed 65 lots
                        # would risk ₹130 on one trade and ₹1,950 on the next
                        # with no relationship to the account. Risk-based
                        # sizing inverts that: solve for quantity from the
                        # stop distance so risk-per-trade stays roughly
                        # constant no matter which strike is selected.
                        #
                        # Non-option trades keep the previous behaviour
                        # exactly — this change is scoped to option buying.
                        use_risk_sizing = is_option_trade and settings.get(
                            "option_risk_based_sizing", True
                        )
                        if use_risk_sizing:
                            total_shares = risk_manager.calculate_position_size(
                                entry_premium, sl_price, ai_confidence=confidence
                            ) or 1
                        elif "quantity" in settings and int(settings["quantity"]) > 0:
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

                        # Root-cause fix (found running live paper trading):
                        # capping to less than one lot used to fall through
                        # and place a phantom qty=0 "entry" instead of
                        # rejecting the trade — not even one lot fits under
                        # max_order_value at this price, so there's no valid
                        # size to trade at all.
                        if total_quantity <= 0:
                            logger.warning(
                                "SECURITY GUARD: not even one lot (%d) fits under max_order_value "
                                "₹%.2f at worst-case fill ₹%.2f for %s — skipping entry.",
                                lot_size, max_order_val, worst_case_fill_price, entry_symbol,
                            )
                            continue

                        if cap_protect_multiplier < 1.0:
                            logger.info(f"CAPITAL PROTECTION ACTIVE: Scaling position size to {cap_protect_multiplier*100}% ({total_quantity} shares)")

                        # ── Risk Manager Gate ─────────────────────────────────────────
                        # Pass actual rupee risk so the per-trade risk limit is enforced
                        actual_risk_amount = abs(entry_premium - sl_price) * total_quantity

                        # An option lot is indivisible: if this is already a
                        # single lot, sizing has no smaller answer to give.
                        # Tell the risk manager so it can allow it with a loud
                        # RISK-CAP OVERRIDE warning instead of silently
                        # rejecting every high-premium signal — see
                        # RiskManager.can_trade's docstring.
                        is_min_size = total_quantity <= lot_size
                        allowed, reject_reason = risk_manager.can_trade(
                            symbol=s,
                            risk_amount=actual_risk_amount,
                            ai_confidence=confidence,
                            current_volatility=current_volatility,
                            is_minimum_tradeable_size=is_min_size,
                        )
                        if not allowed:
                            logger.info("Trade BLOCKED for %s: %s", s, reject_reason)
                            continue

                        if not settings.get("auto_trade_enabled", True):
                            logger.info("Auto trades disabled (Manual Mode) - Skipping execution for %s.", s)
                            continue

                        # ── Execute (Live or Paper) ────────────────────────
                        if is_live:
                            # TGT is deliberately absent for option entries —
                            # profit management is the trailing stop's and the
                            # Smart Exit Engine's job, with no cap on upside.
                            tgt_display = f"{tgt_price:.2f}" if tgt_price > 0 else "NONE (trailing/smart-exit)"
                            logger.info(
                                "ENTRY %s %s quantity=%d @ %.2f | SL=%.2f | TGT=%s | AI=%.0f%% [LIVE]",
                                side_str, entry_symbol, total_quantity, entry_premium, sl_price, tgt_display, confidence * 100
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
                            tgt_display = f"{tgt_price:.2f}" if tgt_price > 0 else "NONE (trailing/smart-exit)"
                            logger.info(
                                "ENTRY %s %s qty=%d @ %.2f | SL=%.2f | TGT=%s | AI=%.0f%% [PAPER]",
                                side_str, entry_symbol, total_quantity, entry_premium, sl_price, tgt_display, confidence * 100
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
        global _m2m_last_update
            
        if time.time() - _m2m_last_update > 0.05:
            total_unrealized_pnl = 0.0
            
            for position in active_positions.values():
                entry_premium = position.entry_price
                total_quantity = position.quantity
                is_option = "CE" in position.symbol or "PE" in position.symbol

                # Get the live premium for this specific position
                if position.symbol == sym:
                    current_premium = ltp
                elif position.symbol in _tick_option_premiums:
                    # Already fetched this tick by the exit-check block above
                    current_premium = _tick_option_premiums[position.symbol]
                elif is_option:
                    # The data aggregator only ever holds candles for
                    # subscribed symbols (the underlying index) -- an option's
                    # own symbol is never in it, so this used to silently fall
                    # through to `entry_premium`, making unrealized P&L for
                    # every open option position display as flat $0 no matter
                    # how far the real premium had moved. Fetch it directly.
                    try:
                        # See ~line 1024's 2026-08-13 root-cause note:
                        # to_thread + DATA_LIMITER close the engine-freeze
                        # gap for this call site too.
                        if not DATA_LIMITER.allow("fyers"):
                            quotes = {}
                        else:
                            quotes = await asyncio.to_thread(broker.get_market_data, [position.symbol])
                        quote = quotes.get(position.symbol)
                        current_premium = quote.ltp if (quote and quote.ltp > 0) else entry_premium
                    except Exception:
                        current_premium = entry_premium
                else:
                    # Look up the latest premium from our data aggregator
                    option_data = aggregator.get_latest_dataframe(position.symbol)
                    if not option_data.empty:
                        current_premium = option_data["close"].iloc[-1]
                    else:
                        current_premium = entry_premium

                # P&L = (Current Premium - Entry Premium) * Total Quantity.
                # `side` only flips the sign for a genuine short position in
                # the underlying -- this system always BUYS options (CE/PE
                # already encodes the directional bet), so a bought option's
                # unrealized P&L must never be sign-flipped by `side`.
                premium_difference = current_premium - entry_premium
                position_pnl = premium_difference * total_quantity * (1 if is_option else position.side)

                total_unrealized_pnl += position_pnl
            
            total_portfolio_pnl = risk_manager.daily_pnl + total_unrealized_pnl
            update_equity(risk_manager.current_equity + total_unrealized_pnl, total_portfolio_pnl)
            _m2m_last_update = time.time()

    async def sync_broker_state():
        await _reconcile_broker_state(broker, active_positions, risk_manager, portfolio_risk)

    async def emergency_flatten_all_positions(reason: str) -> None:
        """Force-close every open position right now, at a real market
        price where one can be gotten. Wired to the dashboard's panic-exit
        button via the `emergency_stop` flag in config/settings.json.

        Root-cause fix (found live, 2026-08-05, while designing a safe way
        to test the kill switch ahead of the next live session):
        api_bridge.py's `/api/panic-exit` endpoint only ever called
        `broker.get_positions()`/`get_order_book()`/`place_order()` directly
        on the broker -- but `FyersBroker.get_positions()` and
        `get_order_book()` both unconditionally return `[]` in paper mode,
        so the endpoint always reported `closed=0, cancelled=0` and never
        touched anything this engine actually has open. Worse: even with a
        real broker, main.py runs in a SEPARATE process from api_bridge.py
        with no shared state except `config/settings.json` and
        `config/active_positions.json` -- main.py's own in-memory
        `active_positions` dict and `trading_halted`-style state had zero
        awareness a panic exit had even happened, so it could keep managing
        (or worse, entering new) positions completely unaware. The kill
        switch was, in effect, non-functional end-to-end during this entire
        paper-trading validation window.

        This closes the loop from main.py's side: `on_tick()` checks the
        `emergency_stop` flag on every tick (settings.json is already
        reloaded every tick for other settings, so this needs no new
        polling), and calls this function once when the flag is first seen.
        Reuses `compute_reconciliation()` -- the same pure, already
        extensively tested decision logic behind the WebSocket-reconnect
        reconciliation path -- via its `live_prices` parameter (added for
        exactly this reuse) so the exit-price/PnL/state_action logic is
        identical to, not a second hand-rolled copy of, the already-proven
        reconciliation math.
        """
        if not active_positions:
            return
        logger.warning("!!! EMERGENCY STOP: force-closing %d open position(s) — %s !!!", len(active_positions), reason)

        live_prices: Dict[str, float] = {}
        for pos in active_positions.values():
            try:
                # to_thread only (see ~line 1024's 2026-08-13 root-cause
                # note) -- deliberately NOT gated by DATA_LIMITER: this is
                # the kill-switch/emergency-flatten path, and throttling a
                # forced close of real risk would be exactly backwards.
                quotes = await asyncio.to_thread(broker.get_market_data, [pos.symbol])
                quote = quotes.get(pos.symbol)
                if quote and quote.ltp > 0:
                    live_prices[pos.symbol] = quote.ltp
            except Exception as e:
                logger.error("Emergency stop: could not fetch live price for %s: %s", pos.symbol, e)

        for result in compute_reconciliation(active_positions, broker_positions=[], order_book=[], live_prices=live_prices):
            if result.is_estimate:
                logger.error(
                    "EMERGENCY STOP: could not get a live quote for %s — falling back to the "
                    "stop-loss price (%.2f) as an ESTIMATE. Recorded PNL for this trade may be "
                    "inaccurate; verify manually.",
                    result.symbol, result.exit_price,
                )
            else:
                logger.warning("EMERGENCY STOP: closed %s at %.2f (%s).", result.symbol, result.exit_price, reason)

            portfolio_risk.update_pnl(result.pnl, risk_manager.current_equity)
            risk_manager.record_trade(TradeRecord(
                result.symbol, result.trade_side,
                result.entry_price, result.exit_price, result.pnl, datetime.now(_IST).isoformat()
            ))
            record_trade(result.symbol, result.state_action, result.exit_price, datetime.now(_IST).isoformat(), qty=result.quantity)
            update_equity(risk_manager.current_equity, risk_manager.daily_pnl)

            audit.log(AuditEvent.EMERGENCY_STOP, {
                "symbol": result.symbol, "exit_price": result.exit_price,
                "pnl": result.pnl, "is_estimate": result.is_estimate, "reason": reason,
            }, severity="WARNING")

            del active_positions[result.local_key]

        _save_positions(active_positions)

    # ----------------------------------------------------------------
    # Tick-staleness watchdog
    # ----------------------------------------------------------------
    # Root-cause fix (found live, 2026-08-06): on_tick() -- and everything
    # inside it, including all exit management -- only ever runs when a
    # real tick arrives. If the feed goes quiet while a position is open
    # (market closed, or a genuine WS outage during real trading hours),
    # nothing manages that position for as long as the silence lasts, and
    # nothing previously reported that this was happening. Observed live:
    # a position opened at 02:50 IST off one post-restart snapshot tick
    # then went unmonitored for 7h49m. This task is pure observability --
    # it warns and audit-logs, it does not halt trading, block entries, or
    # touch any position. See shared/risk/tick_staleness.py.
    _last_staleness_alert: Dict[str, float] = {}
    # Re-alert cadence deliberately coarser than the check interval, so an
    # ongoing gap logs once every few minutes instead of once every check.
    _STALENESS_CHECK_INTERVAL_S = 30.0
    _STALENESS_REALERT_INTERVAL_S = 300.0
    _last_engine_stall_alert = 0.0

    async def tick_staleness_watchdog() -> None:
        while True:
            await asyncio.sleep(_STALENESS_CHECK_INTERVAL_S)
            try:
                settings = _load_settings()
                now = time.monotonic()

                # ── Engine-wide stall check (runs regardless of open positions) ──
                # Root-cause fix (found live, 2026-08-06): the per-position
                # check below only ever runs when a position is open, by
                # design -- it exists to protect capital at risk. That left
                # a real gap: main.py went CPU-bound for 22+ minutes with
                # zero log output while genuinely flat (confirmed via
                # repeated py-spy dumps -- ongoing computation across
                # different pandas/indicator code paths, not a deadlock;
                # exact trigger not fully pinned down, did not reproduce on
                # a clean restart). Nothing in the system reported it; it
                # was only caught by manually cross-checking process CPU
                # against log timestamps. This check closes that gap --
                # only evaluated during real market hours, since silence
                # outside trading hours is expected, not a fault.
                nonlocal _last_engine_stall_alert
                if is_market_open(settings=settings):
                    stall_threshold = float(settings.get("engine_stall_warning_s", 90.0))
                    stall_age = seconds_since_any_tick(_last_tick_at, now)
                    if stall_age >= stall_threshold and (now - _last_engine_stall_alert) >= _STALENESS_REALERT_INTERVAL_S:
                        _last_engine_stall_alert = now
                        age_display = "never" if stall_age == float("inf") else f"{stall_age:.0f}s"
                        logger.warning(
                            "ENGINE STALL: no tick received for ANY watched symbol in %s "
                            "during market hours -- the engine cannot process exits OR "
                            "new entries until a tick arrives. Check the WS connection "
                            "and process CPU (a stuck process can look alive while doing "
                            "no useful work).",
                            age_display,
                        )
                        audit.log(AuditEvent.ENGINE_STALL, {
                            "seconds_since_any_tick": stall_age,
                            "symbols": list(_last_tick_at.keys()),
                        }, severity="WARNING")

                # ── Stale option-candle buffer sweep ───────────────────────
                # Root-cause fix (2026-08-07, option-premium ATR
                # architecture — docs/STRATEGY_AUDIT_2026-08-07.md §2.1):
                # every open option position feeds its own premium samples
                # into `aggregator`, keyed by its own contract symbol.
                # Nothing else ever removes those entries, and unlike the
                # underlying index symbols (a small, fixed set), option
                # contract symbols are effectively unique per trade —
                # without this sweep the candle buffer would grow
                # unboundedly over a long-running process. Runs every
                # cycle regardless of market hours or whether any position
                # is currently open, so a closed position's buffer is
                # evicted promptly rather than lingering until the next
                # trade. See _stale_option_candle_symbols()'s own
                # docstring for the full reasoning.
                stale_symbols = _stale_option_candle_symbols(
                    list(aggregator.candles.keys()),
                    [pos.symbol for pos in active_positions.values()],
                )
                for stale_symbol in stale_symbols:
                    aggregator.candles.pop(stale_symbol, None)

                # ── Per-position staleness check ──────────────────────────
                open_positions = {key: pos.symbol for key, pos in active_positions.items()}
                if not open_positions:
                    continue
                for stale in find_stale_positions(_last_tick_at, open_positions, now, settings):
                    last_alert = _last_staleness_alert.get(stale.underlying_key, 0.0)
                    if (now - last_alert) < _STALENESS_REALERT_INTERVAL_S:
                        continue
                    _last_staleness_alert[stale.underlying_key] = now
                    age_display = (
                        "never" if stale.seconds_since_tick == float("inf")
                        else f"{stale.seconds_since_tick:.0f}s"
                    )
                    logger.warning(
                        "TICK STALENESS: %s (position: %s) has not ticked in %s -- "
                        "this position is receiving NO risk management (trailing/SL/"
                        "partial-book) until a tick arrives. Feed outage or market closed.",
                        stale.underlying_key, stale.traded_symbol, age_display,
                    )
                    audit.log(AuditEvent.TICK_STALENESS, {
                        "underlying": stale.underlying_key,
                        "symbol": stale.traded_symbol,
                        "seconds_since_tick": stale.seconds_since_tick,
                    }, severity="WARNING")
            except Exception as e:
                logger.error("Tick staleness watchdog error: %s", e)

    asyncio.create_task(tick_staleness_watchdog())

    async def heartbeat_writer() -> None:
        """Writes `time.time()` to `_HEARTBEAT_PATH` on a fixed cadence,
        independent of ticks, broker calls, or anything else that could
        block. This is the "is the event loop itself still scheduling
        tasks at all" signal main.py never had before 2026-08-13 -- see
        `shared.risk.tick_staleness.heartbeat_is_stale`'s docstring for
        the full root-cause history. Deliberately does nothing else: the
        whole point is that this task must keep running even when other
        tasks (entry/exit evaluation, the tick-staleness watchdog itself)
        are slow or wedged, so api_bridge.py's watchdog can tell "no
        ticks are arriving" (feed/market issue) apart from "the process
        itself is unresponsive" (needs a restart).
        """
        while True:
            try:
                # Root-cause fix (found live, 2026-08-14): this used to call
                # _write_heartbeat directly, unwrapped, on the event loop --
                # exactly the same anti-pattern as the 2026-08-13
                # get_market_data() freeze this whole mechanism was built to
                # catch, just freshly reintroduced here. A real ~12-hour
                # total freeze (main.py silent from ~00:37 to 12:34 IST,
                # only main_process_watchdog's forced termination finally
                # surfacing one last "Heartbeat write failed: [WinError 5]
                # Access is denied" as the process was killed) is strong
                # circumstantial evidence this exact write -- a synchronous
                # tempfile+os.replace, unprotected -- hung on a Windows-level
                # file lock and took the whole loop down with it, ironically
                # freezing the freeze-detector itself. No open position and
                # zero trades during the affected window, but confirmed via
                # main_process_watchdog actually firing and recovering it --
                # see docs/paper_trading_validation/anomaly_log.md's
                # 2026-08-14 entry. asyncio.to_thread keeps a still-slow or
                # hung write from blocking anything else on this loop again.
                await asyncio.to_thread(_write_heartbeat, _HEARTBEAT_PATH)
            except Exception as e:
                # Never let a heartbeat-write hiccup take down the engine --
                # log and keep going; a missed write or two just makes the
                # next stale-check slightly more conservative, matching
                # heartbeat_is_stale's own tolerance for jitter.
                logger.error("Heartbeat write failed: %s", e)
            await asyncio.sleep(_HEARTBEAT_WRITE_INTERVAL_S)

    asyncio.create_task(heartbeat_writer())

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


def _stale_option_candle_symbols(tracked_symbols, open_position_symbols) -> List[str]:
    """Option-contract symbols with a premium candle buffer but no
    corresponding open position -- safe to evict.

    Root cause this exists for: the option-premium ATR architecture
    (`shared/risk/option_atr.py`, docs/STRATEGY_AUDIT_2026-08-07.md §2.1)
    feeds each open option position's own live premium samples into the
    shared `CandleAggregator`, keyed by the option's own contract symbol.
    Unlike the underlying index symbols (a small, fixed set for the life
    of the process), option contract symbols are effectively unique per
    trade -- a different symbol every time the strike or expiry changes.
    Nothing else ever removes an entry from `aggregator.candles`, so
    without this sweep, every distinct option contract ever traded across
    a long-running process (potentially many per day, every trading day)
    would accumulate in memory forever. Pulled out as its own pure
    function so it's unit-testable without a live aggregator or broker
    connection, matching this file's existing precedent
    (`_build_preload_failure_alert`, `_count_trades_already_executed_today`).

    Parameters
    ----------
    tracked_symbols
        Every symbol currently present in `aggregator.candles` (mixes
        underlying index symbols and option contract symbols).
    open_position_symbols
        The `.symbol` of every currently-open position.

    Returns
    -------
    List[str]
        The subset of `tracked_symbols` that are option contracts
        (CE/PE) with no matching open position -- never includes an
        underlying index symbol, which must keep accumulating candles
        for strategy signal generation regardless of position state.
    """
    open_set = set(open_position_symbols)
    return [
        sym for sym in tracked_symbols
        if ("CE" in sym or "PE" in sym) and sym not in open_set
    ]


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


def _count_trades_already_executed_today(trades: List[Dict[str, Any]], today_str: str) -> int:
    """How many real trades were already executed today, for restoring
    RiskManager.trades_today across a restart (root-cause fix, found live
    2026-08-05 — see the call site in run_live_bot() for the incident).

    `trades` is state.db's raw per-leg trade rows (one row per BUY or SELL,
    not one per completed round-trip). risk_manager.record_trade() -- the
    call that actually increments the day's cap -- is only ever invoked at
    EXIT time, never at entry (grep every call site in this file to verify:
    entries only ever call the free `record_trade()` that writes to
    state.db, never `risk_manager.record_trade()`). This system only ever
    BUYS options, never shorts the underlying directly, so an exit's
    state.db row is always tagged side="SELL" for an option symbol, and an
    entry never is -- counting today's option-tagged SELL rows is therefore
    an exact count of real risk_manager.record_trade() calls today, not an
    approximation. (A hypothetical direct underlying short would break this
    -- its exit is tagged "BUY" -- but no current strategy in this codebase
    does that.)
    """
    return sum(
        1 for t in trades
        if str(t.get("time", "")).startswith(today_str)
        and t.get("side") == "SELL"
        and ("CE" in str(t.get("symbol", "")) or "PE" in str(t.get("symbol", "")))
    )


if __name__ == "__main__":
    from shared.singleton_lock import acquire_singleton_lock
    acquire_singleton_lock("main", script_hint="main.py")

    # Run automated system maintenance on startup — cleans old logs,
    # truncates unbounded SDK logs, purges __pycache__ and stale .bak files.
    try:
        from shared.maintenance import run_system_maintenance
        _maint = run_system_maintenance()
        if _maint.get("total_freed_mb", 0) > 0:
            logger.info("Startup maintenance freed %.1f MB", _maint["total_freed_mb"])
    except Exception as _maint_exc:
        logger.debug("Startup maintenance skipped: %s", _maint_exc)

    # Durable file log — main.py otherwise only logs to its console window,
    # which is invisible to anything monitoring the process from outside.
    # Deliberately set up here, not at module level: this module is also
    # imported by the test suite and other scripts, and a module-level
    # RotatingFileHandler would attach a second, independent handler to
    # the SAME engine.log path from whatever process does that importing
    # -- root-caused 2026-08-04 when a test run's own handler collided
    # with the live engine's, silently breaking the live process's ability
    # to keep writing to the file (the process itself kept running fine —
    # confirmed via state.db's last_update still advancing — only the log
    # went dark). Only the actual live-engine process should own this file.
    _LOG_DIR = Path(__file__).resolve().parents[1] / "logs"
    _LOG_DIR.mkdir(exist_ok=True)
    _engine_file_handler = logging.handlers.RotatingFileHandler(
        _LOG_DIR / "engine.log", maxBytes=5 * 1024 * 1024, backupCount=5, encoding="utf-8"
    )
    _engine_file_handler.setFormatter(logging.Formatter(
        "[%(asctime)s] %(levelname)s %(name)s: %(message)s"
    ))
    logging.getLogger().addHandler(_engine_file_handler)

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
        # All four tradeable index instruments. NIFTY and SENSEX listed
        # first (evaluated first each tick) and trade at the strategy's
        # normal AI-confidence bar; BANKNIFTY/FINNIFTY trade alongside them
        # but need a stricter bar by default — see
        # shared/risk/instrument_focus.py and the "focus_instruments"/
        # "secondary_instrument_min_confidence" settings.
        [
            "NSE:NIFTY50-INDEX",
            "BSE:SENSEX-INDEX",
            "NSE:NIFTYBANK-INDEX",
            "NSE:FINNIFTY-INDEX",
        ],
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
