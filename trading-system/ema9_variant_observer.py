#!/usr/bin/env python3
"""
EMA9/RSI Momentum -- execution-variant paper books.

Runs the owner's ema9_rsi_momentum rules exactly -- ``generate_signals`` on
CLOSED spot candles; stop 15%, then a stop that ratchets up a ladder of rungs
with no fixed target (exit_ladder.py), the EMA/RSI reversal exit, square-off
at 15:15 -- under one or more execution
*variants* (which chart the rules read, which strike a signal buys), each as
its own paper book:

  5m_atm   5-minute chart, ATM strike -- today's defaults: the CONTROL
  15m_itm  15-minute chart, ITM strike (real delta ~0.70) -- the CANDIDATE

Why not paper_observer.py: that observer enters when /api/signals' "bias"
flips. The bias is a trend STATE -- EMA9 above EMA20 and RSI above its
average, scored on the still-forming candle -- in which ADX and the EMA-touch
rule only add or withhold points; they never block. So it takes trades the
strategy refuses: on 2026-09-11 both of its afternoon entries came on crosses
the strategy blocked (ADX 14.5 and 16.4 < 18). Its results cannot measure the
strategy. These books enter on the strategy's own signals, so 5m_atm vs
15m_itm is a like-for-like comparison.

Both books run in one process and share each poll's data: one 5-minute
history fetch per index, from which the 15-minute bars are built exactly as
the backtest built them.

Indices: the paper-test set (``paper_test_instruments`` setting; default
NIFTY, BANKNIFTY, SENSEX). Live trading, later, uses only the indices chosen
in the UI -- see ``shared.instruments.resolve_trading_symbols``.

Isolated from the main paper book:
  * no state.db writes, no config/active_positions.json
  * logs in paper_obs_logs/variants/<variant>/ -- a subdirectory, so the
    orchestrator's EOD report (which globs paper_obs_logs/*<date>*.json)
    never mixes them in
  * Telegram messages are prefixed "SHADOW TEST"

Backtest yardsticks (578 NIFTY sessions, owner's exits, costs included):
5m_atm -3.20% of premium per trade (n=656); 15m_itm +1.99% (n=170), not
proven -- 10/20-minute lose, 2024 flat, SENSEX loses. BANKNIFTY and SENSEX
have no comparable backtest here; their live numbers are new information.

Usage:  python ema9_variant_observer.py --variants 5m_atm,15m_itm
"""

from __future__ import annotations

import argparse
import datetime
import json
import pathlib
import signal as sig_mod
import statistics
import sys
import time
from collections import Counter

ROOT_DIR = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT_DIR))

# HTTP, auth and option-chain helpers are paper_observer's, so every book
# reads the market the same way. (Importing it also runs its startup
# maintenance.)
import paper_observer as po  # noqa: E402
from shared.closed_bars import (  # noqa: E402
    candles_to_frame,
    closed_candles,
    regular_session,
    resample_closed,
)
from shared.instruments import resolve_paper_test_instruments  # noqa: E402
from shared.risk.portfolio_guard import entry_block_reason  # noqa: E402
from trading_bot.strategies.ema9_rsi_momentum import (  # noqa: E402
    evaluate_protective_exit,
    generate_signals,
)
from trading_bot.strategies.ema9_rsi_momentum.config import Ema9RsiMomentumConfig  # noqa: E402
from trading_bot.strategies.ema9_rsi_momentum.exit_ladder import (  # noqa: E402
    initial_stop,
    ratchet_stop,
    stop_reason,
)
from trading_bot.strategies.ema9_rsi_momentum.strike_selection import select_strike  # noqa: E402

VARIANTS = {
    "5m_atm": {
        "label": "EMA9/RSI 5-min ATM (control)",
        "config": {"timeframe_minutes": 5, "strike_selection": "ATM"},
    },
    "15m_itm": {
        "label": "EMA9/RSI 15-min ITM",
        "config": {"timeframe_minutes": 15, "strike_selection": "ITM"},
    },
}
DEFAULT_VARIANTS = ("5m_atm", "15m_itm")

#: What the backtest measured, so every scorecard carries its own yardstick.
#: NIFTY only -- the one index with enough history to measure.
BACKTEST_REFERENCE = {
    "5m_atm": {"symbol": "NIFTY", "trades": 656, "avg_net_return_pct": -3.20, "win_rate_pct": 26.7,
               "basis": "578 NIFTY sessions 2024-01..2026-09, owner's exits, 3.0% round-trip cost"},
    "15m_itm": {"symbol": "NIFTY", "trades": 170, "avg_net_return_pct": 1.99, "win_rate_pct": 39.4,
                "basis": "578 NIFTY sessions 2024-01..2026-09, owner's exits, 1.6% round-trip cost"},
}

# Exits: the owner's ladder -- SL 15%, then the stop steps up rung by rung with
# no fixed target (Ema9RsiMomentumConfig.initial_sl_pct / profit_ladder_pct;
# see trading_bot/strategies/ema9_rsi_momentum/exit_ladder.py).
#: Per index, per book, per day.
MAX_TRADES_PER_DAY = 3
POLL_INTERVAL_S = 15
#: A signal bar is acted on only if it closed within this many seconds, so a
#: restart at 13:00 cannot buy a 10:45 cross.
FRESH_BAR_S = 180
#: Calendar days of history per poll: ~275 closed 15-min bars in a normal
#: fortnight, and still above MIN_BARS across a long holiday stretch.
HISTORY_DAYS = 15
#: Fewer closed bars than this and no signal is taken. Measured by replaying
#: all 578 sessions through latest_closed_signal with only a trailing window:
#: at 175 bars it fired on exactly the backtest's 170 bars (0 missed, 0
#: extra); at 100 bars it added 6 signals the backtest never took -- EMA/RSI/
#: ADX warm-up drift. Better to sit out a session than trade on that.
MIN_BARS = 150
#: A verdict needs this many sessions AND this many trades.
MIN_SESSIONS_FOR_VERDICT = 20
MIN_TRADES_FOR_VERDICT = 20
#: The timeframe history is fetched at; coarser bars are built from it.
BASE_TIMEFRAME_MINUTES = 5

VARIANTS_DIR = po.LOG_DIR / "variants"
running = True
#: The dashboard's settings, read at session start: the portfolio guard uses
#: the same max_daily_loss_pct / max_same_direction_positions as live.
RISK_SETTINGS: dict = {}
#: Last stale bar reported per (book, index), so a closed market logs once.
_STALE_DATA_LOGGED: dict = {}


def _stop(_signum, _frame):
    global running
    running = False
    print("\n[VARIANT] Graceful shutdown requested...")


def _install_signal_handlers() -> None:
    for name in ("SIGINT", "SIGTERM", "SIGBREAK"):
        if hasattr(sig_mod, name):
            try:
                sig_mod.signal(getattr(sig_mod, name), _stop)
            except (ValueError, OSError):
                pass


# ---------------------------------------------------------------------------
# Rules -- pure functions, so the books can be tested without a market
# ---------------------------------------------------------------------------

def build_config(variant: str) -> Ema9RsiMomentumConfig:
    """Strategy defaults plus the variant's execution overrides.

    Deliberately NOT read from settings.json: the books must run exactly the
    rules that were measured, whatever the dashboard is set to.
    """
    return Ema9RsiMomentumConfig(**VARIANTS[variant]["config"])


def latest_closed_signal(df_closed, cfg: Ema9RsiMomentumConfig) -> int:
    """1 (CE), -1 (PE) or 0 for the newest bar of a CLOSED-bar frame."""
    if df_closed is None or len(df_closed) < MIN_BARS:
        return 0
    kwargs = {name: getattr(cfg, name) for name in cfg.__dataclass_fields__}
    sig = generate_signals(df_closed, **kwargs)
    return int(sig.iloc[-1]) if len(sig) else 0


def is_fresh(bar_close: datetime.datetime, now_naive: datetime.datetime,
             max_age_s: float = FRESH_BAR_S) -> bool:
    age = (now_naive - bar_close).total_seconds()
    return 0 <= age <= max_age_s


def expiry_info(expiry, now):
    """(ISO expiry date, whether it expires today) from the chain's dd-mm-YYYY.

    Expiry-day trades are the owner's deliberate 0DTE setups; the scorecard
    reports them separately so their edge is measured, not assumed.
    """
    if not expiry:
        return None, None
    try:
        day = datetime.datetime.strptime(str(expiry), "%d-%m-%Y").date()
    except ValueError:
        return str(expiry), None
    return day.isoformat(), day == now.date()


def new_position(variant, symbol, side, leg, spot, bar_start, now, expiry=None) -> dict:
    """A position filled at the leg's ASK -- a buyer lifts the offer."""
    entry = round(leg["ask"], 2)
    cfg = build_config(variant)
    expiry_iso, expiry_today = expiry_info(expiry, now)
    return {
        "variant": variant,
        "symbol": symbol,
        "strategy": "ema9_rsi_momentum",
        "contract": f"{symbol} {leg['strike']:g} {leg['opt_type']}",
        "direction": "BUY" if side == 1 else "SELL",
        "side": side,
        "opt_type": leg["opt_type"],
        "strike": leg["strike"],
        "strike_mode": leg["mode"],
        "opt_delta": leg["delta"],
        "opt_theta": leg["theta"],
        "entry_iv": leg["iv"],
        "entry_spot": round(float(spot), 2),
        "signal_bar": bar_start.isoformat(),
        "entry_premium": entry,
        "entry_ltp": leg["ltp"],
        "entry_bid": leg["bid"],
        "entry_ask": leg["ask"],
        "entry_spread_pct": leg["spread_pct"],
        "current_ltp": entry,
        "highest_premium": entry,
        "lowest_premium": entry,
        "sl_premium": initial_stop(entry, cfg.initial_sl_pct),
        # Not an exit: the next rung of the ladder, shown as the "target".
        "tgt_premium": ratchet_stop(entry, 0.0, entry, cfg.profit_ladder_pct, cfg.initial_sl_pct)[1],
        "trailed": False,
        "expiry": expiry_iso,
        "expiry_day": expiry_today,
        "quantity": po.LOT_SIZE.get(symbol, 65),
        "entry_time": now.strftime("%H:%M:%S"),
        "entry_time_epoch": now.timestamp(),
    }


def check_price_exits(pos: dict, mark: float, cfg: Ema9RsiMomentumConfig | None = None):
    """The stop, then the ladder. There is no target exit.

    Returns an exit reason if the stop is hit. Otherwise ratchets the stop up
    the owner's ladder from the best premium seen (mutating ``pos``) and sets
    ``tgt_premium`` to the next rung -- None once the top rung is passed.
    """
    if mark <= pos["sl_premium"]:
        return stop_reason(pos["entry_premium"], pos["sl_premium"])
    cfg = cfg or Ema9RsiMomentumConfig()
    best = max(pos.get("highest_premium", mark), mark)
    new_stop, next_rung = ratchet_stop(pos["entry_premium"], pos["sl_premium"], best,
                                       cfg.profit_ladder_pct, cfg.initial_sl_pct)
    if new_stop > pos["sl_premium"]:
        pos["sl_premium"] = new_stop
        pos["trailed"] = True
    pos["tgt_premium"] = next_rung
    return None


def close_position(pos: dict, price: float, reason: str, now, price_source: str) -> dict:
    closed = dict(pos)
    closed.update(po.compute_trade_pnl(closed, price, reason))
    closed["exit_time"] = now.strftime("%H:%M:%S")
    closed["exit_price_source"] = price_source
    closed["return_pct"] = round((price - pos["entry_premium"]) / pos["entry_premium"] * 100.0, 2)
    closed["net_return_pct"] = round(closed["net_pnl"] / (pos["entry_premium"] * pos["quantity"]) * 100.0, 2)
    closed["duration_min"] = round((now.timestamp() - pos["entry_time_epoch"]) / 60.0, 1)
    return closed


#: India VIX bands the scorecard reports results by (audit P4: measure before gating).
VIX_BANDS = ("<12", "12-15", "15-18", "18+", "unknown")


def vix_band(vix) -> str:
    if vix is None:
        return "unknown"
    v = float(vix)
    return "<12" if v < 12 else "12-15" if v < 15 else "15-18" if v < 18 else "18+"


def book_day_pnl(sess: dict) -> float:
    """This book's P&L today: closed trades plus open positions at their mark."""
    realized = sum(t.get("net_pnl", 0.0) for t in sess["trades"])
    unrealized = sum((p.get("current_ltp", p["entry_premium"]) - p["entry_premium"]) * p["quantity"]
                     for p in sess["open_positions"].values())
    return realized + unrealized


def trades_taken(sess: dict, symbol: str) -> int:
    """Trades this book has opened on ``symbol`` today, closed or open."""
    return (sum(1 for t in sess["trades"] if t.get("symbol") == symbol)
            + (1 if symbol in sess["open_positions"] else 0))


# ---------------------------------------------------------------------------
# Market data
# ---------------------------------------------------------------------------

def base_frame(symbol: str, now):
    """Closed, regular-session 5-minute bars for ``symbol`` -- one fetch per
    index per poll, shared by every book."""
    base = po.fetch_candles(symbol, f"{BASE_TIMEFRAME_MINUTES} Min", limit=5000, days=HISTORY_DAYS)
    return regular_session(candles_to_frame(closed_candles(base or [], BASE_TIMEFRAME_MINUTES, now)))


def frame_for(df5, timeframe_minutes: int, now):
    """The book's own timeframe, built from 5-minute bars.

    Never read from the broker's 15-minute series: its local cache once held
    3 of a session's 25 bars while the 5-minute cache held all 75. The
    backtest built its 15-minute bars from 5-minute ones; so does this.
    """
    if timeframe_minutes == BASE_TIMEFRAME_MINUTES:
        return df5
    return resample_closed(df5, timeframe_minutes, now)


def closed_frame(symbol: str, timeframe_minutes: int, now):
    """Fetch and build in one call -- for a single book or a one-off check."""
    return frame_for(base_frame(symbol, now), timeframe_minutes, now)


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------

def variant_dir(variant: str) -> pathlib.Path:
    d = VARIANTS_DIR / variant
    d.mkdir(parents=True, exist_ok=True)
    return d


def session_file(variant: str, date_str: str) -> pathlib.Path:
    return variant_dir(variant) / f"session_{date_str}.json"


def load_session(path: pathlib.Path, variant: str, date_str: str) -> dict:
    """Today's session, resumed from disk if the book restarted mid-day.

    Open positions are persisted too, so a crash-and-restart keeps managing
    them instead of forgetting them.
    """
    sess = {
        "variant": variant,
        "label": VARIANTS[variant]["label"],
        "date": date_str,
        "config": VARIANTS[variant]["config"],
        "symbols": [],
        "session_start": None,
        "session_end": None,
        "trades": [],
        "open_positions": {},
        "last_bar": {},
        "signals": [],
    }
    if path.exists():
        try:
            with open(path, "r", encoding="utf-8") as f:
                on_disk = json.load(f)
            for key in ("session_start", "trades", "open_positions", "last_bar", "signals"):
                if key in on_disk:
                    sess[key] = on_disk[key]
        except (OSError, ValueError) as exc:
            print(f"  [WARN] could not resume {path.name}: {exc}")
    return sess


def summarise(trades: list) -> dict:
    wins = [t for t in trades if t.get("net_pnl", 0) > 0]
    returns = [t["net_return_pct"] for t in trades if "net_return_pct" in t]
    return {
        "trades": len(trades),
        "wins": len(wins),
        "losses": len(trades) - len(wins),
        "win_rate_pct": round(len(wins) / len(trades) * 100.0, 1) if trades else 0.0,
        "net_pnl": round(sum(t.get("net_pnl", 0.0) for t in trades), 2),
        "avg_net_return_pct": round(statistics.mean(returns), 2) if returns else None,
        "exit_mix": dict(Counter(t.get("exit_reason", "?") for t in trades)),
    }


def build_scorecard(variant: str) -> dict:
    """Every session this book has run, overall and per index, against the
    backtest's yardstick."""
    trades, sessions = [], 0
    for f in sorted(variant_dir(variant).glob("session_*.json")):
        try:
            with open(f, "r", encoding="utf-8") as fp:
                trades.extend(json.load(fp).get("trades", []))
            sessions += 1
        except (OSError, ValueError):
            continue
    card = {"variant": variant, "label": VARIANTS[variant]["label"], "sessions": sessions}
    card.update(summarise(trades))
    card["by_symbol"] = {sym: summarise([t for t in trades if t.get("symbol") == sym])
                         for sym in sorted({t.get("symbol") for t in trades if t.get("symbol")})}
    card["by_expiry_day"] = {
        "expiry_day": summarise([t for t in trades if t.get("expiry_day") is True]),
        "other_days": summarise([t for t in trades if t.get("expiry_day") is False]),
    }
    card["by_entry_vix"] = {band: summarise([t for t in trades if vix_band(t.get("entry_vix")) == band])
                            for band in VIX_BANDS}
    card["backtest_reference"] = BACKTEST_REFERENCE.get(variant)

    if sessions < MIN_SESSIONS_FOR_VERDICT or card["trades"] < MIN_TRADES_FOR_VERDICT:
        card["verdict"] = (f"COLLECTING DATA -- {sessions}/{MIN_SESSIONS_FOR_VERDICT} sessions, "
                           f"{card['trades']}/{MIN_TRADES_FOR_VERDICT} trades. Too early to judge.")
    elif (card["avg_net_return_pct"] or 0) > 0:
        card["verdict"] = "HOLDING UP -- positive net return per trade on live quotes."
    else:
        card["verdict"] = "NOT CONFIRMED -- live net return per trade is not positive."
    card["updated_at"] = po.now_ist().isoformat()
    return card


def write_scorecard(variant: str) -> dict:
    card = build_scorecard(variant)
    po.save_session_atomic(card, variant_dir(variant) / "scorecard.json")
    return card


def notify(variant: str, text: str) -> None:
    if po.alerter is None:
        return
    try:
        po.alerter.send_alert(f"SHADOW TEST | {VARIANTS[variant]['label']}\n{text}")
    except Exception as exc:
        print(f"  [WARN] Telegram notify failed: {exc}")


# ---------------------------------------------------------------------------
# One poll
# ---------------------------------------------------------------------------

def consider_entry(sess: dict, symbol: str, cfg: Ema9RsiMomentumConfig, df, now) -> bool:
    """Open a position if the bar that JUST closed carries a signal. Returns
    True if the session changed."""
    if len(df) == 0:
        return False
    bar_start = df.index[-1].to_pydatetime()
    bar_close = bar_start + datetime.timedelta(minutes=cfg.timeframe_minutes)
    if bar_start.date() != now.date():
        # Market closed or the feed is down -- say so once, then sit out.
        if _STALE_DATA_LOGGED.get((sess["variant"], symbol)) != bar_start:
            _STALE_DATA_LOGGED[(sess["variant"], symbol)] = bar_start
            print(f"  [{now:%H:%M:%S}] {sess['variant']} {symbol}: last closed bar is "
                  f"{bar_start:%Y-%m-%d %H:%M} -- no data for today; not trading.")
        return False
    if not is_fresh(bar_close, now.replace(tzinfo=None)):
        return False
    side = latest_closed_signal(df, cfg)
    if side == 0:
        return False

    record = {"symbol": symbol, "bar": bar_start.isoformat(), "side": "CE" if side == 1 else "PE",
              "seen_at": now.strftime("%H:%M:%S")}
    sess["signals"].append(record)
    variant = sess["variant"]

    if now.time() >= po.EOD_CUTOFF:
        record["action"] = "skipped: after the EOD cutoff"
        return True
    if trades_taken(sess, symbol) >= MAX_TRADES_PER_DAY:
        record["action"] = "skipped: daily trade cap"
        return True

    chain = po.fetch_option_chain(symbol)
    if not chain or not chain.get("chain"):
        record["action"] = "skipped: no option chain"
        return True
    if chain.get("synthetic"):
        record["action"] = "skipped: synthetic chain -- will not fill against invented prices"
        return True
    spot = float(chain.get("underlying_price") or df["close"].iloc[-1])
    leg = select_strike(chain["chain"], spot, side, cfg.strike_selection,
                        cfg.itm_target_delta, cfg.max_entry_spread_pct)
    if leg is None:
        record["action"] = f"skipped: no tradeable {cfg.strike_selection} strike"
        print(f"  [{now:%H:%M:%S}] {variant} {symbol} {record['side']} signal on the {bar_start:%H:%M} bar "
              f"-- {record['action']}")
        return True

    entry = round(leg["ask"], 2)
    vix = (chain.get("indiaVix") or {}).get("value")
    block = entry_block_reason(
        vix=vix,
        direction=side,
        open_directions=[p["side"] for p in sess["open_positions"].values()],
        day_pnl=book_day_pnl(sess),
        capital=po.CAPITAL,
        trade_risk=(entry - initial_stop(entry, cfg.initial_sl_pct)) * po.LOT_SIZE.get(symbol, 65),
        settings=RISK_SETTINGS,
    )
    if block:
        record["action"] = f"skipped: {block}"
        print(f"  [{now:%H:%M:%S}] {variant} {symbol} {record['side']} signal on the {bar_start:%H:%M} bar "
              f"-- {record['action']}")
        return True

    pos = new_position(variant, symbol, side, leg, spot, bar_start, now, expiry=chain.get("expiry"))
    pos["entry_vix"] = vix            # with entry_iv, so the VIX gate's threshold can come from data
    sess["open_positions"][symbol] = pos
    record["action"] = f"entered {pos['contract']} @ {pos['entry_premium']:.2f}"
    msg = (f"ENTRY {pos['contract']} @ Rs.{pos['entry_premium']:.2f} (ask) | delta {pos['opt_delta']} | "
           f"spot {pos['entry_spot']} | {cfg.timeframe_minutes}-min bar {bar_start:%H:%M} | "
           f"SL Rs.{pos['sl_premium']:.2f} | Tgt Rs.{pos['tgt_premium']:.2f}")
    print(f"  [{now:%H:%M:%S}] {variant} 🔵 {msg}")
    notify(variant, msg)
    return True


def manage_position(sess: dict, symbol: str, pos: dict, df, is_new_bar: bool, now) -> bool:
    """Mark to the contract's live BID and run the exit ladder: stop, target,
    trail, reversal (on a newly closed bar), EOD. Returns True if the session
    changed."""
    live = po.fetch_live_premium(symbol, pos["strike"], pos["opt_type"])
    mark = round(live["bid"], 2) if live and live.get("bid") else None
    reason, detail = None, ""

    if mark is not None:
        pos["current_ltp"] = mark
        pos["highest_premium"] = max(pos["highest_premium"], mark)
        pos["lowest_premium"] = min(pos["lowest_premium"], mark)
        pos["mark_time"] = now.strftime("%H:%M:%S")
        old_stop = pos["sl_premium"]
        reason = check_price_exits(pos, mark, build_config(sess["variant"]))
        if pos["sl_premium"] > old_stop:
            nxt = f"Rs.{pos['tgt_premium']:.2f}" if pos.get("tgt_premium") else "none (top rung passed)"
            print(f"  [{now:%H:%M:%S}] {sess['variant']} 🛡️ {pos['contract']} stop ratcheted "
                  f"Rs.{old_stop:.2f} -> Rs.{pos['sl_premium']:.2f} | next rung {nxt}")
        if reason is None and is_new_bar and len(df) >= 2:
            rev = evaluate_protective_exit(df, pos["side"], pos["entry_premium"], mark)
            if rev.should_exit:
                reason, detail = "REVERSAL EXIT", rev.reason

    if reason is None and now.time() >= po.EOD_CUTOFF:
        reason = "EOD 15:15"

    if reason is None:
        return mark is not None

    price = mark if mark is not None else pos.get("current_ltp", pos["entry_premium"])
    source = "broker_bid" if mark is not None else "last_mark"
    closed = close_position(pos, price, reason, now, source)
    if detail:
        closed["exit_detail"] = detail
    sess["trades"].append(closed)
    del sess["open_positions"][symbol]
    card = write_scorecard(sess["variant"])

    msg = (f"EXIT {closed['contract']} | {reason} | Rs.{price:.2f} ({source}) | "
           f"net Rs.{closed['net_pnl']:+.2f} ({closed['net_return_pct']:+.2f}%) | {closed['duration_min']}m\n"
           f"Book so far: {card['trades']} trades, net Rs.{card['net_pnl']:+.2f}")
    print(f"  [{now:%H:%M:%S}] {sess['variant']} {'💰' if closed['net_pnl'] > 0 else '🛑'} {msg}")
    notify(sess["variant"], msg)
    return True


def step(sess: dict, symbol: str, cfg: Ema9RsiMomentumConfig, df, now, path: pathlib.Path) -> None:
    """One book, one index, one poll, on an already-built frame."""
    newest = df.index[-1].isoformat() if len(df) else None
    is_new_bar = newest is not None and newest != sess["last_bar"].get(symbol)

    pos = sess["open_positions"].get(symbol)
    if pos is not None:
        changed = manage_position(sess, symbol, pos, df, is_new_bar, now)
    else:
        changed = is_new_bar and consider_entry(sess, symbol, cfg, df, now)

    if is_new_bar:
        sess["last_bar"][symbol] = newest
        changed = True
    if changed:
        po.save_session_atomic(sess, path)


# ---------------------------------------------------------------------------
# Sessions
# ---------------------------------------------------------------------------

def finish_book(variant: str, sess: dict, path: pathlib.Path, market_closed: bool) -> None:
    if market_closed:
        # EOD normally closed everything at 15:15; this only fires if every
        # quote was missing through the close.
        for symbol, pos in list(sess["open_positions"].items()):
            price = pos.get("current_ltp", pos["entry_premium"])
            sess["trades"].append(close_position(pos, price, "MARKET CLOSE (no quote at EOD)",
                                                 po.now_ist(), "last_mark"))
            del sess["open_positions"][symbol]
        sess["session_end"] = po.now_ist().isoformat()
    sess["summary"] = summarise(sess["trades"])
    sess["summary"]["by_symbol"] = {sym: summarise([t for t in sess["trades"] if t.get("symbol") == sym])
                                    for sym in sess["symbols"]}
    po.save_session_atomic(sess, path)
    card = write_scorecard(variant)

    s = sess["summary"]
    print(f"\n  [{variant}] SESSION {sess['date']}: {s['trades']} trades, {s['wins']} wins, net Rs.{s['net_pnl']:+.2f}")
    print(f"  [{variant}] BOOK: {card['sessions']} sessions, {card['trades']} trades, "
          f"net Rs.{card['net_pnl']:+.2f}, avg {card['avg_net_return_pct']}%/trade -- {card['verdict']}")
    if market_closed:
        per_index = ", ".join(f"{k} {v['trades']}t Rs.{v['net_pnl']:+.0f}" for k, v in s["by_symbol"].items())
        notify(variant, f"Session {sess['date']}: {s['trades']} trades, net Rs.{s['net_pnl']:+.2f} ({per_index})\n"
                        f"Book: {card['sessions']} sessions, {card['trades']} trades, "
                        f"net Rs.{card['net_pnl']:+.2f}\n{card['verdict']}")


def run_books(variants) -> dict:
    """Run every book in ``variants`` for today's session, sharing each poll's
    data between them."""
    cfgs = {v: build_config(v) for v in variants}
    settings = po.fetch_json("/api/settings") or {}
    RISK_SETTINGS.clear()
    RISK_SETTINGS.update(settings)
    symbols = resolve_paper_test_instruments(settings)
    date_str = po.now_ist().strftime("%Y-%m-%d")
    books = {}
    for v in variants:
        path = session_file(v, date_str)
        sess = load_session(path, v, date_str)
        sess["symbols"] = symbols
        sess["session_start"] = sess["session_start"] or po.now_ist().isoformat()
        po.save_session_atomic(sess, path)
        books[v] = (sess, path)

    print(f"\n{'=' * 72}")
    print(f"  SHADOW BOOKS  {date_str}  -- ema9_rsi_momentum rules on CLOSED spot bars")
    for v in variants:
        c, sess = cfgs[v], books[v][0]
        print(f"  {v:8s} {VARIANTS[v]['label']:32s} {c.timeframe_minutes:>2}-min {c.strike_selection:3s} | "
              f"resumed trades {len(sess['trades'])}, open {len(sess['open_positions'])}")
    ladder_cfg = cfgs[variants[0]]
    print(f"  Exits : SL {ladder_cfg.initial_sl_pct:g}%, then ladder "
          f"{'/'.join(f'{r:g}' for r in ladder_cfg.profit_ladder_pct)} -- no fixed target | reversal | EOD 15:15")
    print(f"  Indices (paper test): {', '.join(symbols)} | max {MAX_TRADES_PER_DAY}/index/book/day")
    print(f"{'=' * 72}")

    while running and po.is_market_open():
        now = po.now_ist()
        for symbol in symbols:
            try:
                df5 = base_frame(symbol, now)
            except Exception as exc:
                print(f"  [{now:%H:%M:%S}] {symbol}: history fetch failed: {exc}")
                continue
            for v in variants:
                sess, path = books[v]
                try:
                    step(sess, symbol, cfgs[v], frame_for(df5, cfgs[v].timeframe_minutes, now), now, path)
                except Exception as exc:
                    print(f"  [{now:%H:%M:%S}] {v} {symbol}: cycle error: {exc}")
        for _ in range(POLL_INTERVAL_S):
            if not running:
                break
            time.sleep(1)

    market_closed = not po.is_market_open()
    for v in variants:
        finish_book(v, *books[v], market_closed)
    return {v: books[v][0] for v in variants}


def run_session(variant: str) -> dict:
    """A single book -- kept for callers that run one variant."""
    return run_books([variant])[variant]


def parse_variants(text: str) -> list:
    names = [v.strip() for v in (text or "").split(",") if v.strip()]
    unknown = [v for v in names if v not in VARIANTS]
    if unknown or not names:
        raise SystemExit(f"unknown or empty --variants {text!r}; choose from {sorted(VARIANTS)}")
    return list(dict.fromkeys(names))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--variants", default=",".join(DEFAULT_VARIANTS),
                    help=f"comma-separated, from {sorted(VARIANTS)}")
    ap.add_argument("--variant", default=None, help="a single variant (older spelling of --variants)")
    args = ap.parse_args(argv)
    variants = parse_variants(args.variant or args.variants)
    _install_signal_handlers()

    from shared.singleton_lock import acquire_singleton_lock
    acquire_singleton_lock("ema9_variant_books", "ema9_variant_observer.py")

    now = po.now_ist()
    if now.weekday() >= 5 or now.time() >= po.MARKET_CLOSE:
        print(f"  [VARIANT] Market closed ({now:%a %H:%M} IST) -- nothing to do.")
        for v in variants:
            write_scorecard(v)
        return 0
    while running and po.ist_time() < po.MARKET_OPEN:
        time.sleep(5)
    if running:
        run_books(variants)
    return 0


if __name__ == "__main__":
    sys.exit(main())
