#!/usr/bin/env python3
"""
EMA9/RSI Momentum -- execution-variant paper book.

Runs the owner's ema9_rsi_momentum rules exactly -- ``generate_signals`` on
CLOSED spot candles; stop 15%, target 33%, stop to breakeven at +15%, the
EMA/RSI reversal exit, square-off at 15:15 -- under an execution *variant*
(which chart the rules read, which strike a signal buys), as its own paper
book.

Why not paper_observer.py: that observer enters on /api/signals' bias and
confidence, not on this strategy's closed-candle cross, so its results cannot
validate a change that was measured against the strategy's own rules. This
book enters on the same bars the backtest did.

Isolated from the main paper book:
  * no state.db writes, no config/active_positions.json -- the dashboard,
    equity curve and EOD report stay the main book's alone
  * logs in paper_obs_logs/variants/<variant>/ -- a subdirectory, so the
    orchestrator's EOD report (which globs paper_obs_logs/*<date>*.json)
    never mixes the two books
  * Telegram messages are prefixed "SHADOW TEST"

Evidence for the one variant defined, 15m_itm (578 NIFTY sessions,
2024-01..2026-09, owner's exits, costs included): +1.99% of premium per
trade, n=170, positive in both halves of the data and still positive at a 3%
round-trip cost -- against -3.20% for today's 5-minute / ATM. NOT proven:
10- and 20-minute charts lose, 2024 alone was flat, and SENSEX loses under
the same rules. This book exists to find out on live quotes before any
default changes.

Usage:  python ema9_variant_observer.py --variant 15m_itm
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

# HTTP, auth and option-chain helpers are paper_observer's, so both books read
# the market the same way. (Importing it also runs its startup maintenance.)
import paper_observer as po  # noqa: E402
from shared.closed_bars import (  # noqa: E402
    candles_to_frame,
    closed_candles,
    regular_session,
    resample_closed,
)
from trading_bot.strategies.ema9_rsi_momentum import (  # noqa: E402
    evaluate_protective_exit,
    generate_signals,
)
from trading_bot.strategies.ema9_rsi_momentum.config import Ema9RsiMomentumConfig  # noqa: E402
from trading_bot.strategies.ema9_rsi_momentum.strike_selection import select_strike  # noqa: E402

VARIANTS = {
    "15m_itm": {
        "label": "EMA9/RSI 15-min ITM",
        "config": {"timeframe_minutes": 15, "strike_selection": "ITM"},
        # NIFTY only: the one index the result was measured on with enough
        # history. SENSEX lost under the same rules; BANKNIFTY had 2.5 months
        # of data -- too little to judge either way.
        "symbols": ["NIFTY"],
    },
}

#: What the backtest measured, so every scorecard carries its own yardstick.
BACKTEST_REFERENCE = {
    "15m_itm": {"trades": 170, "avg_net_return_pct": 1.99, "win_rate_pct": 39.4,
                "basis": "578 NIFTY sessions 2024-01..2026-09, owner's exits, 1.6% round-trip cost"},
}

STOP_PCT = 15.0
TARGET_PCT = 33.0
TRAIL_TRIGGER_PCT = 15.0         # at +15% the stop moves to breakeven
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

VARIANTS_DIR = po.LOG_DIR / "variants"
running = True


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
# Rules -- pure functions, so the book can be tested without a market
# ---------------------------------------------------------------------------

def build_config(variant: str) -> Ema9RsiMomentumConfig:
    """Strategy defaults plus the variant's execution overrides.

    Deliberately NOT read from settings.json: the book must run exactly the
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


def new_position(variant, symbol, side, leg, spot, bar_start, now) -> dict:
    """A position filled at the leg's ASK -- a buyer lifts the offer."""
    entry = round(leg["ask"], 2)
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
        "sl_premium": round(entry * (1 - STOP_PCT / 100.0), 2),
        "tgt_premium": round(entry * (1 + TARGET_PCT / 100.0), 2),
        "trailed": False,
        "quantity": po.LOT_SIZE.get(symbol, 65),
        "entry_time": now.strftime("%H:%M:%S"),
        "entry_time_epoch": now.timestamp(),
    }


def check_price_exits(pos: dict, mark: float):
    """Stop, target, then the breakeven trail -- the observer's order.

    Returns an exit reason or None. Moves the stop to breakeven (mutating
    ``pos``) the first time the mark reaches +15%.
    """
    if mark <= pos["sl_premium"]:
        return "BREAKEVEN STOP" if pos.get("trailed") else "STOP LOSS"
    if mark >= pos["tgt_premium"]:
        return "TARGET"
    if not pos.get("trailed") and mark >= pos["entry_premium"] * (1 + TRAIL_TRIGGER_PCT / 100.0):
        pos["sl_premium"] = pos["entry_premium"]
        pos["trailed"] = True
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
    """Every session this variant has run, against the backtest's yardstick."""
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
    if len(sess["trades"]) + len(sess["open_positions"]) >= MAX_TRADES_PER_DAY:
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
        print(f"  [{now:%H:%M:%S}] {symbol} {record['side']} signal on the {bar_start:%H:%M} bar "
              f"-- {record['action']}")
        return True

    pos = new_position(variant, symbol, side, leg, spot, bar_start, now)
    sess["open_positions"][symbol] = pos
    record["action"] = f"entered {pos['contract']} @ {pos['entry_premium']:.2f}"
    msg = (f"ENTRY {pos['contract']} @ Rs.{pos['entry_premium']:.2f} (ask) | delta {pos['opt_delta']} | "
           f"spot {pos['entry_spot']} | {cfg.timeframe_minutes}-min bar {bar_start:%H:%M} | "
           f"SL Rs.{pos['sl_premium']:.2f} | Tgt Rs.{pos['tgt_premium']:.2f}")
    print(f"  [{now:%H:%M:%S}] 🔵 {msg}")
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
        was_trailed = pos.get("trailed")
        reason = check_price_exits(pos, mark)
        if pos.get("trailed") and not was_trailed:
            print(f"  [{now:%H:%M:%S}] 🛡️ {pos['contract']} +{TRAIL_TRIGGER_PCT:.0f}% -- stop moved to "
                  f"breakeven Rs.{pos['entry_premium']:.2f}")
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
    print(f"  [{now:%H:%M:%S}] {'💰' if closed['net_pnl'] > 0 else '🛑'} {msg}")
    notify(sess["variant"], msg)
    return True


#: The timeframe history is fetched at; coarser bars are built from it.
BASE_TIMEFRAME_MINUTES = 5


def closed_frame(symbol: str, timeframe_minutes: int, now):
    """Closed, regular-session ``timeframe_minutes`` bars, built from 5-minute history.

    Never read from the broker's own 15-minute series: its local cache held
    3 of 2026-09-10's 25 bars while the 5-minute cache held all 75, and
    indicators computed across that hole are not the ones the backtest
    measured. The backtest built its 15-minute bars from 5-minute ones; so
    does this.
    """
    base = po.fetch_candles(symbol, f"{BASE_TIMEFRAME_MINUTES} Min", limit=5000, days=HISTORY_DAYS)
    df = regular_session(candles_to_frame(closed_candles(base or [], BASE_TIMEFRAME_MINUTES, now)))
    if timeframe_minutes == BASE_TIMEFRAME_MINUTES:
        return df
    return resample_closed(df, timeframe_minutes, now)


def step(sess: dict, symbol: str, cfg: Ema9RsiMomentumConfig, now, path: pathlib.Path) -> None:
    df = closed_frame(symbol, cfg.timeframe_minutes, now)
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
# Session
# ---------------------------------------------------------------------------

def run_session(variant: str) -> dict:
    spec = VARIANTS[variant]
    cfg = build_config(variant)
    date_str = po.now_ist().strftime("%Y-%m-%d")
    path = session_file(variant, date_str)
    sess = load_session(path, variant, date_str)
    sess["session_start"] = sess["session_start"] or po.now_ist().isoformat()

    print(f"\n{'=' * 70}")
    print(f"  SHADOW BOOK: {spec['label']}  ({variant})  {date_str}")
    print(f"  Rules : ema9_rsi_momentum on CLOSED {cfg.timeframe_minutes}-min spot bars")
    print(f"  Strike: {cfg.strike_selection} (target |delta| {cfg.itm_target_delta}), "
          f"spread cap {cfg.max_entry_spread_pct}%")
    print(f"  Exits : SL {STOP_PCT:.0f}% | target {TARGET_PCT:.0f}% | breakeven at +{TRAIL_TRIGGER_PCT:.0f}% "
          f"| reversal | EOD 15:15")
    print(f"  Symbols: {', '.join(spec['symbols'])} | resumed trades: {len(sess['trades'])}, "
          f"open: {len(sess['open_positions'])}")
    print(f"{'=' * 70}")
    po.save_session_atomic(sess, path)

    while running and po.is_market_open():
        now = po.now_ist()
        for symbol in spec["symbols"]:
            try:
                step(sess, symbol, cfg, now, path)
            except Exception as exc:
                print(f"  [{now:%H:%M:%S}] {symbol}: cycle error: {exc}")
        for _ in range(POLL_INTERVAL_S):
            if not running:
                break
            time.sleep(1)

    market_closed = not po.is_market_open()
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
    po.save_session_atomic(sess, path)
    card = write_scorecard(variant)

    s = sess["summary"]
    print(f"\n  SESSION {date_str}: {s['trades']} trades, {s['wins']} wins, net Rs.{s['net_pnl']:+.2f}")
    print(f"  BOOK: {card['sessions']} sessions, {card['trades']} trades, net Rs.{card['net_pnl']:+.2f}, "
          f"avg {card['avg_net_return_pct']}%/trade -- {card['verdict']}")
    if market_closed:
        notify(variant, f"Session {date_str}: {s['trades']} trades, net Rs.{s['net_pnl']:+.2f}\n"
                        f"Book: {card['sessions']} sessions, {card['trades']} trades, "
                        f"net Rs.{card['net_pnl']:+.2f}\n{card['verdict']}")
    return sess


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--variant", default="15m_itm", choices=sorted(VARIANTS))
    args = ap.parse_args(argv)
    _install_signal_handlers()

    from shared.singleton_lock import acquire_singleton_lock
    acquire_singleton_lock(f"ema9_variant_{args.variant}", "ema9_variant_observer.py")

    now = po.now_ist()
    if now.weekday() >= 5 or now.time() >= po.MARKET_CLOSE:
        print(f"  [VARIANT] Market closed ({now:%a %H:%M} IST) -- nothing to do.")
        write_scorecard(args.variant)
        return 0
    while running and po.ist_time() < po.MARKET_OPEN:
        time.sleep(5)
    if running:
        run_session(args.variant)
    return 0


if __name__ == "__main__":
    sys.exit(main())
