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
from typing import Dict, List

import pandas as pd
import pytz

_IST = pytz.timezone("Asia/Kolkata")

# Add parent directory to sys.path to find 'shared' module
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shared.config import CONFIG
from shared.state import update_equity, record_trade
# Broker layer — broker-agnostic: trading logic never imports vendor SDKs directly
from brokers import BrokerFactory, OrderRequest, OrderSide
from trading_bot.strategies.registry import registry
from trading_bot.strategies.premium_selection import (
    PremiumSignalEngine, PremiumSignal, generate_signals as premium_signals
)
from trading_bot.strategies.momentum_strategy import MomentumStrategy

# Import AI / Risk / Exit / Alert Modules
from shared.ai import TradeFilterModel, compute_features
from shared.risk import RiskManager, RiskConfig, TradeRecord
from shared.exits import SmartExitEngine, Position, PyramidSizer
from shared.alerts import alerter
from trading_bot.portfolio_risk import PortfolioRiskEngine

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

# Path to the shared settings file written by the Streamlit dashboard
_SETTINGS_PATH = Path(__file__).resolve().parents[1] / "config" / "settings.json"

# ------------------------------------------------------------------
# Settings cache: avoids disk I/O on every tick (checks mtime instead)
# ------------------------------------------------------------------
_settings_cache: dict = {}
_settings_last_mtime: float = 0.0


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
        "target_pct": 1.0,
        "stoploss_pct": 0.5,
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
    """Aggregate raw tick dictionaries into OHLCV DataFrames."""

    def __init__(self, symbols: List[str]):
        self.symbols = symbols
        self._buffer: Dict[str, List[Dict]] = defaultdict(list)
        self._current_minute: datetime | None = None
        self.candles: Dict[str, pd.DataFrame] = {}

    def _minute_floor(self, ts: datetime) -> datetime:
        return ts.replace(second=0, microsecond=0)

    def add_tick(self, tick: Dict) -> None:
        ts = datetime.fromtimestamp(tick["timestamp"], tz=timezone.utc)
        minute = self._minute_floor(ts)
        if self._current_minute is None:
            self._current_minute = minute
        elif minute > self._current_minute:
            self._finalize_minute()
            self._current_minute = minute
        symbol = tick["symbol"]
        self._buffer[symbol].append(tick)

    def _finalize_minute(self) -> None:
        for symbol, ticks in self._buffer.items():
            if not ticks:
                continue
            df = pd.DataFrame(ticks)
            candle = {
                "open": df["ltp"].iloc[0],
                "high": df["ltp"].max(),
                "low": df["ltp"].min(),
                "close": df["ltp"].iloc[-1],
                "volume": df["volume"].sum(),
                "timestamp": pd.to_datetime(self._current_minute),
            }
            if symbol not in self.candles:
                self.candles[symbol] = pd.DataFrame([candle]).set_index("timestamp")
            else:
                self.candles[symbol] = pd.concat([
                    self.candles[symbol],
                    pd.DataFrame([candle]).set_index("timestamp"),
                ])
        self._buffer = defaultdict(list)

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

    aggregator = CandleAggregator(symbols)

    # Read initial capital from settings — not hardcoded
    _init_settings = _load_settings()
    _initial_capital = float(_init_settings.get("initial_capital", 100_000.0))

    # Initialize Core Engines
    risk_manager = RiskManager(initial_capital=_initial_capital)
    ai_filter = TradeFilterModel()
    exit_engine = SmartExitEngine(atr_multiplier=1.5, partial_booking_pct=50.0)
    pyramid_sizer = PyramidSizer(pct_trigger=0.2, max_scales=2)
    portfolio_risk = PortfolioRiskEngine(max_daily_dd_pct=5.0, max_weekly_dd_pct=10.0, max_consecutive_losses=3)

    active_positions: Dict[str, Position] = {}
    momentum_strategies: Dict[str, MomentumStrategy] = {}

    async def on_tick(tick: Dict) -> None:
        sym = tick["symbol"]
        ltp = tick["ltp"]
        # Use IST time for all intraday comparisons (EOD exit at 15:15 IST)
        current_time = datetime.now(_IST).strftime("%H:%M:%S")

        # Load settings once per tick — the TTL cache (10 s) makes this free
        # (no disk I/O) on the vast majority of ticks.
        settings = _load_settings()

        # ----------------------------------------------------------------
        # Lazy Strategy Initialization
        # ----------------------------------------------------------------
        strategy_name = settings.get("active_strategy", "institutional_momentum")
        if strategy_name == "institutional_momentum" and sym not in momentum_strategies:
            momentum_strategies[sym] = MomentumStrategy(
                capital=_initial_capital,
                target_pct=settings.get("target_pct", 1.0),
                stoploss_pct=settings.get("stoploss_pct", 0.5),
                default_lots=settings.get("quantity", 1)
            )

        # ----------------------------------------------------------------
        # 1. Intra-candle Exit Evaluation for existing positions
        # ----------------------------------------------------------------
        if sym in active_positions:
            pos = active_positions[sym]
            df = aggregator.get_latest_dataframe(sym)
            current_atr = (df["high"].iloc[-1] - df["low"].iloc[-1]) if not df.empty else (ltp * 0.005)

            from shared.sentiment import get_current_sentiment
            sentiment_data = get_current_sentiment()
            sentiment_score = sentiment_data.get("score", 0.0)

            should_exit, reason, exit_qty = False, "", None

            if sentiment_score < -0.8 and pos.direction == "LONG":
                should_exit = True
                reason = "Macro Panic (Sentiment Circuit Breaker)"
                exit_qty = pos.quantity
            else:
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
                
                decision = m_strategy.manage_active_trades(ltp, df_5min, ai_confidence=confidence * 100)
                if decision and decision.get("exit"):
                    should_exit = True
                    reason = decision.get("reason", "Institutional Smart Exit")
                    # Support partial booking
                    qty_pct = decision.get("quantity_pct", 1.0)
                    exit_qty = max(1, int(pos.quantity * qty_pct)) if qty_pct < 1.0 else pos.quantity
            else:
                should_exit, reason, exit_qty = exit_engine.evaluate_exit(
                    pos, ltp, current_time, current_atr
                )
            
            # Close the else block for the sentiment check
            pass

            if should_exit:
                qty_to_close = exit_qty if exit_qty else pos.quantity
                is_live = settings.get("live_trading_mode", False)   # use the cached settings

                if is_live:
                    logger.info("EXIT %s %s for %s (%s) [LIVE]", pos.side, qty_to_close, sym, reason)
                    if not ORDER_LIMITER.allow(broker.BROKER_ID):
                        logger.warning("EXIT order rate-limited for %s — skipping.", sym)
                    else:
                        exit_req = OrderRequest(
                            symbol=sym,
                            quantity=qty_to_close,
                            side=OrderSide.SELL if pos.side == 1 else OrderSide.BUY,
                        )
                        try:
                            exit_req = validator.validate(exit_req)
                            await broker.place_order_async(exit_req)
                            audit.trade(AuditEvent.TRADE_EXIT, sym,
                                        "SELL" if pos.side == 1 else "BUY",
                                        qty_to_close, pos.entry_price,
                                        broker=broker.BROKER_ID, pnl=0)
                        except ValidationError as ve:
                            logger.error("EXIT order validation failed for %s: %s", sym, ve)
                            audit.log(AuditEvent.VALIDATION_ERROR,
                                      {"symbol": sym, "reason": str(ve)}, severity="WARNING")
                else:
                    logger.info("EXIT %s %s for %s (%s) [PAPER]", pos.side, qty_to_close, sym, reason)

                # Record PnL & update dashboard state
                pnl = (ltp - pos.entry_price) * qty_to_close * pos.side
                
                # Phase 7: Update Portfolio Risk
                portfolio_risk.update_pnl(pnl, risk_manager.current_equity)
                
                trade_side = "LONG" if pos.side == 1 else "SHORT"
                risk_manager.record_trade(TradeRecord(
                    sym, trade_side,
                    pos.entry_price, ltp, pnl, datetime.utcnow().isoformat()
                ))
                # Also persist to shared state for dashboard display
                record_trade(sym, "SELL" if pos.side == 1 else "BUY", ltp, datetime.utcnow().isoformat())
                update_equity(risk_manager.current_equity, risk_manager.daily_pnl)
                alerter.send_exit_alert(sym, pos.side, qty_to_close, ltp, pnl, reason)

                if exit_qty is None or exit_qty >= pos.quantity:
                    del active_positions[sym]
                else:
                    pos.quantity -= exit_qty

            # ----------------------------------------------------------------
            # 1.5. Pyramiding (Scaling In) for remaining positions
            # ----------------------------------------------------------------
            if sym in active_positions:
                pos = active_positions[sym]
                
                should_scale, scale_reason = pyramid_sizer.evaluate_scale(pos, ltp)
                
                if should_scale:
                    scale_qty = int(settings.get("quantity", 2)) // 2  # Scale in with half of base qty or 1 lot
                    if scale_qty < 1: scale_qty = 1
                    
                    is_live = settings.get("live_trading_mode", False)
                    side_str = "BUY" if pos.side == 1 else "SELL"
                    
                    if is_live:
                        logger.info("PYRAMID SCALE %d: %s %d %s @ %.2f (%s) [LIVE]", 
                                    pos.scales_done + 1, side_str, scale_qty, sym, ltp, scale_reason)
                        
                        if not ORDER_LIMITER.allow(broker.BROKER_ID):
                            logger.warning("SCALE order rate-limited for %s — skipping.", sym)
                        else:
                            scale_req = OrderRequest(
                                symbol=pos.symbol,
                                quantity=scale_qty,
                                side=OrderSide.BUY if pos.side == 1 else OrderSide.SELL,
                            )
                            try:
                                scale_req = validator.validate(scale_req)
                                await broker.place_order_async(scale_req)
                                audit.trade(AuditEvent.TRADE_ENTRY, pos.symbol,
                                            scale_req.side.value, scale_req.quantity,
                                            ltp, broker=broker.BROKER_ID)
                                
                                # Update position
                                pos.quantity += scale_qty
                                pos.scales_done += 1
                                alerter.send_trade_alert(pos.symbol, f"PYRAMID SCALE IN {side_str}", scale_qty, ltp, 1.0)
                                
                            except ValidationError as ve:
                                logger.error("Scale order validation failed for %s: %s", sym, ve)
                    else:
                        logger.info("PYRAMID SCALE %d: %s %d %s @ %.2f (%s) [PAPER]", 
                                    pos.scales_done + 1, side_str, scale_qty, sym, ltp, scale_reason)
                        pos.quantity += scale_qty
                        pos.scales_done += 1

        # ----------------------------------------------------------------
        # 2. Aggregate tick → check for new candle bar
        # ----------------------------------------------------------------
        try:
            aggregator.add_tick(tick)
            if aggregator._current_minute and \
               datetime.now(timezone.utc).replace(second=0, microsecond=0) > aggregator._current_minute:

                # Settings already loaded at top of on_tick (cached, no disk I/O)
                strategy_name = settings.get("active_strategy", "institutional_momentum")
                is_live = settings.get("live_trading_mode", False)
                target_pct = settings.get("target_pct", 1.0) / 100.0
                sl_pct = settings.get("stoploss_pct", 0.5) / 100.0

                # AI confidence threshold: stricter for enhanced_ai strategy
                min_confidence = 0.85 if strategy_name == "enhanced_ai" else 0.60

                for s in symbols:
                    if s in active_positions:
                        continue  # Only one open position per symbol

                    df = aggregator.get_latest_dataframe(s)
                    if len(df) < 50:  # Need enough warmup bars
                        continue

                    # ── AI Confidence Gate (computed first, needed by premium engine) ──
                    # Only compute on the last 60 rows — enough for all indicator warmups.
                    # This avoids reprocessing the full 200-500 bar history each tick.
                    df_tail = df.tail(60)
                    features = compute_features(df_tail).tail(1)
                    
                    if ai_filter.is_trained:
                        confidence = ai_filter.predict(features)["confidence"].iloc[-1] if not features.empty else 1.0
                    else:
                        # Fallback to pure rules-based trading if model is not trained
                        confidence = 1.0

                    if confidence < min_confidence:
                        logger.info(
                            "AI rejected signal for %s — confidence %.2f < threshold %.2f",
                            s, confidence, min_confidence
                        )
                        continue

                    # ── Run selected strategy ──────────────────────────
                    logger.info("Running strategy: [%s] for %s", strategy_name, s)

                    # ── Premium Strategy: uses engine directly for option selection ──
                    if strategy_name == "premium":
                        instrument = s.replace("NSE:", "").replace("-INDEX", "").replace("-EQ", "")
                        premium_engine = PremiumSignalEngine(
                            instrument=instrument,
                            capital=risk_manager.current_equity,
                            min_ai_confidence=min_confidence,
                        )
                        sig: PremiumSignal = premium_engine.evaluate(df, ai_confidence=confidence)

                        if not sig.is_tradeable:
                            logger.info("Premium filter rejected %s: %s", s, sig.reject_reason)
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
                        signals_data = registry.run_strategy(strategy_name, df, **settings)
                        if isinstance(signals_data, tuple):
                            signals, _ = signals_data
                        else:
                            signals = signals_data
                        latest_signal = signals.iloc[-1]
                        entry_symbol  = s
                        lot_size      = 1
                        
                        if strategy_name == "institutional_ema" and 'custom_sl_pct' in df.columns:
                            sl_pct = df['custom_sl_pct'].iloc[-1] / 100.0
                            logger.info(f"Using custom SL%% from strategy: {sl_pct*100:.2f}%%")

                    if latest_signal == 0:
                        continue

                    # ── Macro Sentiment Blocks ─────────────────────────
                    from shared.sentiment import get_current_sentiment
                    sentiment_data = get_current_sentiment()
                    sentiment_score = sentiment_data.get("score", 0.0)

                    if latest_signal == 1 and sentiment_score < -0.5:
                        logger.warning("Macro Filter Blocked BUY for %s: Highly Bearish Sentiment (%.2f)", s, sentiment_score)
                        alerter.send_telegram_alert(f"🛑 **Trade Blocked**\n\nSymbol: {s}\nReason: Highly Bearish Sentiment ({sentiment_score})")
                        continue
                        
                    if latest_signal == -1 and sentiment_score > 0.5:
                        logger.warning("Macro Filter Blocked SELL for %s: Highly Bullish Sentiment (%.2f)", s, sentiment_score)
                        alerter.send_telegram_alert(f"🛑 **Trade Blocked**\n\nSymbol: {s}\nReason: Highly Bullish Sentiment ({sentiment_score})")
                        continue

                    # ── Risk Manager Gate ──────────────────────────────
                    current_volatility = df["close"].pct_change().std() * 100
                    
                    # Phase 7: Portfolio Circuit Breaker
                    is_trading_allowed, halt_reason = portfolio_risk.is_trading_allowed(risk_manager.current_equity)
                    if not is_trading_allowed:
                        logger.warning("Portfolio Risk Halt for %s: %s", s, halt_reason)
                        continue
                        
                    allowed, reject_reason = risk_manager.can_trade(
                        symbol=s,
                        risk_amount=100,
                        ai_confidence=confidence,
                        current_volatility=current_volatility,
                    )
                    if not allowed:
                        logger.info("Trade BLOCKED for %s: %s", s, reject_reason)
                        continue

                    # ── Compute Entry / SL / Target ────────────────────
                    entry_price = df["close"].iloc[-1]
                    side_str = "BUY CALL" if latest_signal == 1 else "BUY PUT"
                    sl_price = entry_price * (1 - sl_pct) if latest_signal == 1 else entry_price * (1 + sl_pct)
                    tgt_price = entry_price * (1 + target_pct) if latest_signal == 1 else entry_price * (1 - target_pct)
                    
                    if "quantity" in settings:
                        qty = int(settings["quantity"])
                    else:
                        qty = risk_manager.calculate_position_size(entry_price, sl_price) or 1

                    # ── Execute (Live or Paper) ────────────────────────
                    if is_live:
                        logger.info(
                            "ENTRY %s %s qty=%d @ %.2f | SL=%.2f | TGT=%.2f | AI=%.0f%% [LIVE]",
                            side_str, entry_symbol, qty, entry_price, sl_price, tgt_price, confidence * 100
                        )
                        # Rate-limit guard
                        if not ORDER_LIMITER.allow(broker.BROKER_ID):
                            logger.warning(
                                "Order rate limit reached for broker %s — skipping entry on %s.",
                                broker.BROKER_ID, s,
                            )
                            continue
                        # Input validation gate
                        entry_req = OrderRequest(
                            symbol=entry_symbol,
                            quantity=qty * lot_size,
                            side=OrderSide.BUY if latest_signal == 1 else OrderSide.SELL,
                        )
                        try:
                            entry_req = validator.validate(entry_req)
                            await broker.place_order_async(entry_req)
                            audit.trade(AuditEvent.TRADE_ENTRY, entry_symbol,
                                        entry_req.side.value, entry_req.quantity,
                                        entry_price, broker=broker.BROKER_ID)
                        except ValidationError as ve:
                            logger.error("Entry order validation failed for %s: %s", s, ve)
                            audit.log(AuditEvent.VALIDATION_ERROR,
                                      {"symbol": s, "reason": str(ve)}, severity="WARNING")
                            continue
                    else:
                        logger.info(
                            "ENTRY %s %s qty=%d @ %.2f | SL=%.2f | TGT=%.2f | AI=%.0f%% [PAPER]",
                            side_str, entry_symbol, qty, entry_price, sl_price, tgt_price, confidence * 100
                        )

                    # ── Send Telegram Alert ────────────────────────────
                    alerter.send_trade_alert(entry_symbol, side_str, qty, entry_price, confidence)

                    # ── Track position ─────────────────────────────────
                    active_positions[s] = Position(
                        symbol=entry_symbol,
                        side=latest_signal,
                        entry_price=entry_price,
                        quantity=qty * lot_size,
                        entry_time=current_time,
                        highest_price=entry_price,
                        lowest_price=entry_price,
                        stop_loss=sl_price,
                        target=tgt_price,
                    )
                    
                    if strategy_name == "institutional_momentum" and s in momentum_strategies:
                        momentum_strategies[s].open_trade(
                            entry_price=entry_price, 
                            stop_loss=sl_price, 
                            total_lots=qty * lot_size, 
                            direction=latest_signal
                        )
                        
                    update_equity(risk_manager.current_equity, risk_manager.daily_pnl)

        except Exception as exc:
            logger.exception("Error processing tick: %s", exc)

    logger.info("Starting live stream for symbols: %s", ", ".join(symbols))
    await broker.stream_quotes(symbols, on_tick)


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
    try:
        asyncio.run(run_live_bot(SYMBOLS))
    except KeyboardInterrupt:
        logger.info("Live bot terminated by user")
