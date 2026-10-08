#!/usr/bin/env python3
"""
=============================================================================
  MANA AI — INSTITUTIONAL PAPER TRADING OBSERVER (3-Session Engine v3.0)
  Perspective : 20+ Years Options Floor and Systematic Trader
  Features    : Multi-Day Persistence, Mid-Session Crash Recovery, 
                Auto-Maintenance, Real-Time Option Pricing & Greeks
  Assets      : NIFTY (Lot: 65) and BANKNIFTY (Lot: 15) Options
  Capital     : Rs. 1,00,000 (Virtual)
=============================================================================
"""

import os
import sys
import io
import json
import time
import datetime
import statistics
import signal as sig_mod
import pathlib
import urllib.request
import urllib.error
import urllib.parse
import pytz

# Enforce UTF-8 on Windows
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')

# Root & Path setup
ROOT_DIR = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT_DIR))

# Run automated system maintenance on startup (cleans old logs & purges stale sessions)
try:
    from shared.maintenance import run_system_maintenance
    m_res = run_system_maintenance()
except Exception:
    m_res = None

# Telegram Alerts Integration
try:
    from shared.alerts.telegram import alerter
except Exception:
    alerter = None

# Real-time state.db & active positions integration for UI dashboard
try:
    from shared.state import record_trade, update_equity
except Exception:
    record_trade = None
    update_equity = None

from shared.closed_bars import candles_to_frame, closed_candles, regular_session
from shared.instruments import DEFAULT_PAPER_TEST_INSTRUMENTS, resolve_paper_test_instruments
from trading_bot.strategies.premium_selection.options_selector import INSTRUMENT_CONFIG
from trading_bot.strategies.ema9_rsi_momentum.config import Ema9RsiMomentumConfig
from trading_bot.strategies.ema9_rsi_momentum.exit_ladder import initial_stop, ratchet_stop, stop_reason
from shared.exits.exit_analyzer import ExitAnalyzerAgent

_EXIT_ANALYZER = ExitAnalyzerAgent()
from trading_bot.strategies.ema9_rsi_momentum.signal_engine import (
    classify_momentum_strength,
    entry_timing_gate,
)
from shared.indicators.htf_confluence import detect_htf_trend, get_trade_holding_mode

from shared.market_hours import latest_bar_is_fresh
from shared.entry_gate import decide as entry_decision
from shared.timeframes import settings_timeframe, timeframe_label
from shared.risk.portfolio_guard import entry_block_reason

_TF_CACHE: dict = {"mtime": None, "minutes": 5}


def active_timeframe_minutes() -> int:
    """The chart timeframe the user selected in the UI, in minutes.

    Re-read when settings.json changes rather than captured at import: the
    user can switch timeframe while this book is running and the next scan
    should already be on the new one. Two call sites used to hardcode
    "5 Min", so a user on the 15-minute chart was watched on 5-minute bars.

    Falls back to 5 on any read problem -- a malformed settings file must not
    stop the book, it should keep trading what it has always traded.
    """
    try:
        path = ROOT_DIR / "config" / "settings.json"
        mtime = path.stat().st_mtime
        if _TF_CACHE["mtime"] != mtime:
            with open(path, "r", encoding="utf-8") as fh:
                _TF_CACHE["minutes"] = settings_timeframe(json.load(fh), 5)
            _TF_CACHE["mtime"] = mtime
        return _TF_CACHE["minutes"]
    except Exception:
        return _TF_CACHE.get("minutes", 5) or 5


#: Last stale bar reported per symbol, so a closed market logs once, not every poll.
_STALE_DATA_LOGGED: dict = {}
#: Last bias a symbol's entry was held back on, so "waiting for bar close" is
#: printed once per signal rather than on every poll of the same one.
_TIMING_LOGGED: dict = {}

#: The owner's exit ladder (SL 15%, stop steps up rung by rung, no fixed target).
_EMA9_CFG = Ema9RsiMomentumConfig()
from trading_bot.strategies.ema9_rsi_momentum.config import (
    TIME_END as _EMA9_TIME_END,
    TIME_START as _EMA9_TIME_START,
)

IST = pytz.timezone("Asia/Kolkata")
MARKET_OPEN  = datetime.time(9, 15)
MARKET_CLOSE = datetime.time(15, 30)
EOD_CUTOFF   = datetime.time(15, 15)
POLL_INTERVAL = 15  # 15s poll for high-precision live observation

# Lot sizes from the one exchange-verified table the live strike selector
# uses. This was a local copy with BANKNIFTY at 15 -- half the real 30 -- so
# every BANKNIFTY paper P&L was recorded at half size, and SENSEX had none.
LOT_SIZE = {name: cfg["lot_size"] for name, cfg in INSTRUMENT_CONFIG.items()}
MAX_TRADES_PER_DAY = 4
CAPITAL = 100000.0

BASE_URL = "http://127.0.0.1:8000"
LOG_DIR = ROOT_DIR / "paper_obs_logs"
LOG_DIR.mkdir(exist_ok=True)

#: The paper-test indices; re-read from settings at each session start (see
#: run_session). Paper books test on these; LIVE trading uses only the indices
#: selected in the UI -- see shared.instruments.resolve_trading_symbols.
SYMBOLS = list(DEFAULT_PAPER_TEST_INSTRUMENTS)
running = True

def _stop(s, f):
    global running
    running = False
    print("\n[OBSERVER] Graceful shutdown triggered...")
sig_mod.signal(sig_mod.SIGINT, _stop)

def now_ist():
    return datetime.datetime.now(IST)

def ist_time():
    return now_ist().time().replace(tzinfo=None)

def is_market_open():
    return MARKET_OPEN <= ist_time() < MARKET_CLOSE

def can_enter():
    return ist_time() < EOD_CUTOFF


#: ema9_rsi_momentum's trading window (09:20-15:15 normal, up to 15:25 for VERY_STRONG momentum).
_EMA9_WINDOW = tuple(datetime.time(*map(int, s.split(":"))) for s in (_EMA9_TIME_START, _EMA9_TIME_END))
_EMA9_LATE_ENTRY_END = datetime.time(15, 25)


def entry_window_open(active_strategy, t=None):
    """Whether a NEW position may be opened now.

    Always shut from the EOD cutoff. For ema9_rsi_momentum, allows from 09:20
    up to 15:25 (signal engine enforces VERY_STRONG momentum requirement after 15:15).
    """
    t = t or ist_time()
    if t >= EOD_CUTOFF:
        return False
    if active_strategy == "ema9_rsi_momentum":
        return _EMA9_WINDOW[0] <= t <= _EMA9_LATE_ENTRY_END
    return True


def signal_observation(sig_res):
    """This poll's {"bias", "confidence"}, or None if it carries no real bias.

    On a cold cache /api/signals answers with a CALCULATING placeholder that
    has no "bias" at all. Counting that as an observation would make the next
    poll's real bias look like a fresh change.
    """
    if not sig_res or sig_res.get("bias") is None:
        return None
    return {"bias": sig_res["bias"], "confidence": sig_res.get("confidence", 0)}


def is_new_entry_trigger(prev, obs):
    """Whether `obs` is a NEW trigger rather than a bias that was already standing.

    `prev` is the symbol's last real observation, or None if there has not
    been one. The first observation only seeds state. Before this, `prev` was
    empty at startup, so ANY standing bias >= 65 counted as "new" and was
    bought on the very first poll: 6 of the first 20 paper trades were entered
    at 09:15:1x, before a single 5-minute candle had closed, and together with
    one more pre-09:25 entry they account for -Rs 4,017 of the -Rs 5,983
    recorded. A restart mid-session did the same.
    """
    if prev is None or obs is None:
        return False
    return (obs["bias"] != prev.get("bias")) or (obs["confidence"] - prev.get("confidence", 0) >= 15)

def get_auth_token():
    """Obtain or generate a valid session token."""
    try:
        sf = ROOT_DIR / "config" / "sessions.json"
        if sf.exists():
            with open(sf, "r", encoding="utf-8") as f:
                sessions = json.load(f)
            now_sec = time.time()
            valid = {t: s for t, s in sessions.items() if s.get("expires_at", 0) > now_sec}
            if valid:
                tok = next((t for t, s in valid.items() if "trading_engine" in s.get("user_id", "")), list(valid.keys())[0])
                return tok
    except Exception:
        pass
    try:
        from shared.security.sessions import create_session
        return create_session("trading_engine_internal", "AI Paper Observer", "bot@internal.local")
    except Exception:
        return ""

AUTH_TOKEN = get_auth_token()

def fetch_json(endpoint, timeout=8):
    global AUTH_TOKEN
    url = f"{BASE_URL}{endpoint}"
    req = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {AUTH_TOKEN}",
        "User-Agent": "AIPaperObserver/3.0"
    })
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as he:
        if he.code == 401:
            AUTH_TOKEN = get_auth_token()
        return None
    except Exception:
        return None

def fetch_signals(symbol):
    return fetch_json(f"/api/signals?symbol={symbol}")

def fetch_candles(symbol, timeframe="5 Min", limit=40, days=4):
    today = now_ist().strftime("%Y-%m-%d")
    start = (now_ist() - datetime.timedelta(days=days)).strftime("%Y-%m-%d")
    tf_encoded = urllib.parse.quote(timeframe)
    endpoint = f"/api/history?symbol={symbol}&start_date={start}&end_date={today}&timeframe={tf_encoded}"
    res = fetch_json(endpoint)
    if res and isinstance(res, dict) and "data" in res:
        candles = res["data"]
        if len(candles) > limit:
            return candles[-limit:]
        return candles
    return None

def check_reversal_exit(symbol, opt_type, entry_premium, current_premium):
    """The strategy's own EMA9/EMA20 + RSI reversal exit.

    Per the strategy spec: "even if target or SL has not been hit, if the spot
    chart reverses and an opposite EMA 9/20 cross appears, exit immediately
    regardless of profit or loss."

    `ema9_rsi_momentum.evaluate_protective_exit()` implements exactly that and
    has since v3.13, but nothing ever called it -- neither this module nor
    main.py -- so the only exits that could actually fire were the 15% stop,
    the 33% target and the EOD square-off. Over the six recorded sessions that
    showed up as 5 of 18 trades ending at the EOD cutoff with no management in
    between.

    Signals are read from the SPOT chart, never the option's own candles, as
    the strategy requires. Returns a ProtectiveExitResult, or None when there
    is not enough history to judge.
    """
    # CLOSED bars only. The rule reads the frame's LAST bar, and the last bar
    # /api/history returns is still forming -- a cross that appears mid-bar
    # and is gone by its close would otherwise exit the position.
    tf = active_timeframe_minutes()
    candles = closed_candles(
        fetch_candles(symbol, timeframe_label(tf), 61) or [], tf, now_ist())
    if len(candles) < 40:
        return None
    try:
        from trading_bot.strategies.ema9_rsi_momentum import evaluate_protective_exit

        df = regular_session(candles_to_frame(candles))    # no pre-open bars
        if len(df) < 40:
            return None

        side = 1 if str(opt_type).upper() == "CE" else -1
        return evaluate_protective_exit(df, side, entry_premium, current_premium)
    except Exception as exc:
        print(f"  [WARN] reversal-exit check failed for {symbol}: {exc}")
        return None


#: Short-lived option-chain cache, keyed by symbol -> (fetched_at, payload).
#: The observer polls every POLL_INTERVAL seconds and now reads the chain
#: twice per cycle per symbol (once to screen for an entry, once to mark an
#: open position). Both want the same snapshot, and each miss is a real broker
#: REST call, so collapse them into one.
_CHAIN_CACHE: dict = {}
_CHAIN_TTL_S = 10.0


def fetch_option_chain(symbol, max_age_s: float = _CHAIN_TTL_S):
    """Fetch the option chain for `symbol`, reusing a very recent snapshot."""
    now = time.time()
    cached = _CHAIN_CACHE.get(symbol)
    if cached and (now - cached[0]) <= max_age_s:
        return cached[1]

    data = fetch_json(f"/api/option-chain?symbol={symbol}")
    if data:
        _CHAIN_CACHE[symbol] = (now, data)
    return data


def fetch_live_premium(symbol, strike, opt_type):
    """The contract's own live quote, or None.

    Returns the real two-sided quote for exactly the strike being held, so an
    open position can be marked against what the market is actually paying
    rather than extrapolated from its entry price.
    """
    chain_data = fetch_option_chain(symbol)
    if not chain_data or "chain" not in chain_data:
        return None

    leg_key = "ce" if str(opt_type).upper() == "CE" else "pe"
    for row in chain_data.get("chain", []):
        try:
            if abs(float(row.get("strike", 0)) - float(strike)) > 0.01:
                continue
        except (TypeError, ValueError):
            continue
        leg = row.get(leg_key) or {}
        ltp = float(leg.get("ltp") or 0)
        if ltp <= 0:
            return None
        return {
            "ltp": ltp,
            "bid": float(leg.get("bid") or 0),
            "ask": float(leg.get("ask") or 0),
            "delta": leg.get("delta"),
            "theta": leg.get("theta"),
            "iv": leg.get("iv"),
        }
    return None

def ema(vals, p):
    if len(vals) < p: return None
    k = 2 / (p + 1)
    e = sum(vals[:p]) / p
    for v in vals[p:]: e = v * k + e * (1 - k)
    return e

def atr(candles, p=14):
    if len(candles) < p + 1: return None
    trs = [max(c["high"] - c["low"], abs(c["high"] - candles[i-1]["close"]), abs(c["low"] - candles[i-1]["close"])) 
           for i, c in enumerate(candles) if i > 0]
    if len(trs) < p: return None
    return sum(trs[-p:]) / p

def rsi(closes, p=14):
    if len(closes) < p + 1: return 50.0
    gs = [max(closes[i] - closes[i-1], 0) for i in range(1, len(closes))]
    ls = [max(closes[i-1] - closes[i], 0) for i in range(1, len(closes))]
    ag = sum(gs[-p:]) / p
    al = sum(ls[-p:]) / p
    if al == 0: return 100.0
    rs = ag / al
    return 100.0 - (100.0 / (1.0 + rs))

def select_best_option(symbol, direction, spot_price):
    """Select optimal strike (ATM or 1 strike OTM) and retrieve real-time premium and Greeks."""
    chain_data = fetch_option_chain(symbol)
    # No real chain, no trade. This used to invent a contract -- premium at
    # 0.75% of spot, delta 0.50, theta -12.5 -- and the caller filled it,
    # recording a price no market ever quoted. A synthetic chain is refused
    # for the same reason.
    if not chain_data or not chain_data.get("chain") or chain_data.get("synthetic"):
        return None
    
    chain = chain_data.get("chain", [])
    pcr = chain_data.get("pcr", 1.0)
    
    sorted_strikes = sorted(chain, key=lambda x: abs(x["strike"] - spot_price))
    if not sorted_strikes:
        return None
    
    selected_row = sorted_strikes[0]
    # The chain publishes legs under "ce"/"pe" (NSE terminology, and what the
    # Options Desk reads). This looked them up as "call"/"put", so opt_details
    # was ALWAYS {} and every field below silently fell back to its default --
    # entry premium a flat 100.0, delta 0.50, theta -10.0, on every paper trade
    # ever recorded. Real ATM premium when this was found was 138.50.
    opt_key = "ce" if direction == "BUY" else "pe"
    opt_type = "CE" if direction == "BUY" else "PE"
    opt_details = selected_row.get(opt_key) or {}
    ltp = opt_details.get("ltp") or 0.0
    bid = opt_details.get("bid") or 0.0
    ask = opt_details.get("ask") or 0.0

    if ltp <= 0:
        return None    # no tradeable quote: do not invent one
    
    return {
        "contract": f"{symbol} {selected_row['strike']} {opt_type}",
        "strike": selected_row["strike"],
        "type": opt_type,
        "ltp": float(ltp),
        # Real two-sided quote. An option BUYER lifts the offer on entry and
        # hits the bid on exit; both legs cost real money and neither was
        # modelled before.
        "bid": float(bid),
        "ask": float(ask),
        "spread_pct": opt_details.get("spread_pct"),
        "vwap": opt_details.get("vwap") or opt_details.get("atp"),
        "atp": opt_details.get("atp") or opt_details.get("vwap"),
        "volume": opt_details.get("volume", 0),
        "delta": opt_details.get("delta", 0.50 if direction == "BUY" else -0.50),
        # Theta from the chain is per DAY (Black-Scholes convention).
        "theta": opt_details.get("theta", -10.0),
        "iv": opt_details.get("iv"),
        "pcr": pcr,
        # India VIX from the same chain snapshot: recorded at entry, and read
        # by the optional VIX gate (shared/risk/portfolio_guard.py).
        "vix": (chain_data.get("indiaVix") or {}).get("value"),
    }

def analyze_market_state(symbol, direction):
    """Analyze multi-layer technical setup like an institutional trader."""
    # 80 bars, not 35: the shared entry gate asks the selected strategy to
    # grade the setup, and that grading needs enough history for EMA20 and
    # the RSI's own 20-bar average to have converged.
    candles = fetch_candles(symbol, timeframe_label(active_timeframe_minutes()), 80)
    if not candles or len(candles) < 20:
        return None
    
    closes = [c["close"] for c in candles]
    
    spot = closes[-1]
    e9   = ema(closes, 9)
    e21  = ema(closes, 21)
    at   = atr(candles, 14) or (spot * 0.002)
    rs   = rsi(closes, 14)
    
    # ── Institutional Exhaustion Filter (RSI Guard) ──
    # Option buyers must never buy CE into extreme overbought exhaustion (RSI > 75)
    # or PE into extreme oversold exhaustion (RSI < 25)
    if direction == "BUY" and rs > 75.0:
        return None
    if direction == "SELL" and rs < 25.0:
        return None

    bullish_trend = e9 and e21 and (e9 > e21) and (rs >= 48)
    bearish_trend = e9 and e21 and (e9 < e21) and (rs <= 52)
    
    aligned = (direction == "BUY" and bullish_trend) or (direction == "SELL" and bearish_trend)
    quality = "STRONG" if aligned else "MODERATE"
    
    return {
        "spot": round(spot, 2),
        "bar_time": candles[-1].get("datetime"),     # for the data-freshness gate
        # The frame the shared entry gate grades the setup on.
        "frame": candles_to_frame(candles),
        "ema9": round(e9, 2) if e9 else spot,
        "ema21": round(e21, 2) if e21 else spot,
        "atr": round(at, 2),
        "rsi": round(rs, 1),
        "quality": quality,
        "aligned": aligned
    }

def compute_trade_pnl(trade, current_opt_price, reason=""):
    entry_p = trade["entry_premium"]
    qty     = trade["quantity"]
    
    gross_pnl = round((current_opt_price - entry_p) * qty, 2)
    brokerage = round(20.0 + (qty * 0.05), 2)
    net_pnl   = round(gross_pnl - brokerage, 2)
    pts       = round(current_opt_price - entry_p, 2)
    
    outcome = "WIN" if net_pnl > 0 else "LOSS" if net_pnl < 0 else "SCRATCH"
    return {
        "exit_premium": current_opt_price,
        "gross_pnl": gross_pnl,
        "net_pnl": net_pnl,
        "points": pts,
        "outcome": outcome,
        "exit_reason": reason
    }

def save_session_atomic(session_log, out_file):
    """Save session state atomically to prevent partial-write file corruption."""
    try:
        tmp_file = out_file.with_suffix(".tmp")
        with open(tmp_file, "w", encoding="utf-8") as f:
            json.dump(session_log, f, indent=2, ensure_ascii=False)
        tmp_file.replace(out_file)
    except Exception as e:
        print(f"  [WARN] Failed to write session file: {e}")

def portfolio_block(symbol, direction, opt, session_log, active_positions, settings, stopped_info=None):
    """The portfolio rule every engine shares (shared/risk/portfolio_guard.py):
    daily loss stop, one position per direction across the correlated
    indices, and no trade risking more than the day's whole loss limit.
    Returns the reason to skip, or None."""
    entry = round(opt.get("ask") or opt["ltp"], 2)
    qty = LOT_SIZE.get(symbol, 65)
    realized = sum(t.get("net_pnl", 0.0) for t in session_log.get("trades", []))
    unrealized = sum((p.get("current_ltp", p["entry_premium"]) - p["entry_premium"]) * p["quantity"]
                     for p in active_positions.values())
    st_dir = 1 if (stopped_info and stopped_info.get("direction") == "BUY") else (-1 if (stopped_info and stopped_info.get("direction") == "SELL") else None)
    return entry_block_reason(
        direction=1 if direction == "BUY" else -1,
        open_directions=[1 if p["direction"] == "BUY" else -1 for p in active_positions.values()],
        day_pnl=realized + unrealized,
        capital=CAPITAL,
        trade_risk=(entry - initial_stop(entry, _EMA9_CFG.initial_sl_pct)) * qty,
        settings=settings,
        vix=opt.get("vix"),
        stopped_out_dir=st_dir,
        stopped_out_time=stopped_info.get("time") if stopped_info else None,
        now_time=time.time(),
    )


def _replace_with_retry(src, dst, attempts=5, delay_s=0.05):
    """``src.replace(dst)``, retried briefly on PermissionError.

    On Windows the swap fails with WinError 5 while another process holds
    ``dst`` open -- api_bridge reads active_positions.json on every broadcast
    -- and the observer logged 28 such failures, each leaving the dashboard
    a poll behind. The reader's handle lasts milliseconds.
    """
    for attempt in range(attempts):
        try:
            src.replace(dst)
            return
        except PermissionError:
            if attempt == attempts - 1:
                raise
            time.sleep(delay_s * (attempt + 1))


def sync_active_positions(active_positions):
    """Atomically sync paper observer positions to config/active_positions.json for live UI M2M tracking."""
    pos_file = ROOT_DIR / "config" / "active_positions.json"
    try:
        disk_data = {}
        if pos_file.exists():
            try:
                with open(pos_file, "r", encoding="utf-8") as f:
                    disk_data = json.load(f)
            except Exception:
                disk_data = {}

        # Remove observer symbols that exited
        for s in SYMBOLS:
            if s in disk_data and s not in active_positions:
                del disk_data[s]

        # Write current active positions
        for sym, pos in active_positions.items():
            disk_data[sym] = {
                "symbol": pos.get("contract", sym),
                "underlying": sym,
                "side": 1,  # Option buying (CE / PE)
                "quantity": int(pos.get("quantity", 65)),
                "entry_price": float(pos.get("entry_premium", 0.0)),
                "current_price": float(pos.get("current_ltp", pos.get("entry_premium", 0.0))),
                "ltp": float(pos.get("current_ltp", pos.get("entry_premium", 0.0))),
                "entry_time": pos.get("entry_time", ""),
                "highest_price": float(pos.get("highest_premium", pos.get("entry_premium", 0.0))),
                "lowest_price": float(pos.get("lowest_premium", pos.get("entry_premium", 0.0))),
                "stop_loss": float(pos.get("sl_premium", 0.0)),
                "target": float(pos.get("tgt_premium") or 0.0),   # None once the ladder's top rung is passed
                "strategy": pos.get("strategy_name", "EMA 9 / RSI Momentum")
            }

        tmp = pos_file.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(disk_data, f, indent=2)
        _replace_with_retry(tmp, pos_file)
    except Exception as e:
        print(f"  [WARN] Failed to sync active positions: {e}")

# --- Existing Session & Multi-Day Audit Detection ---
def detect_existing_sessions():
    """Scan paper_obs_logs directory and return all valid completed/in-progress sessions."""
    sessions = []
    for f in sorted(LOG_DIR.glob("session_Day_*.json")):
        try:
            with open(f, "r", encoding="utf-8") as fp:
                data = json.load(fp)
                sessions.append((f, data))
        except Exception:
            pass
    return sessions

# --- Live Session Handler with Incremental Crash Recovery ---
def run_session(day_num, date_str, day_name):
    session_label = f"Day_{day_num}_{date_str}_{day_name}"
    safe_name = session_label.replace(' ', '_').replace(':', '-')
    out_file = LOG_DIR / f"session_{safe_name}.json"
    
    print(f"\n{'='*65}")
    print(f"  ACTIVE OBSERVER SESSION: {session_label}")
    print(f"  Time: {now_ist().strftime('%Y-%m-%d %H:%M:%S IST')}")
    print(f"{'='*65}")
    
    active_settings = fetch_json("/api/settings") or {}
    active_strategy = active_settings.get("active_strategy", "ema9_rsi_momentum")
    SYMBOLS[:] = resolve_paper_test_instruments(active_settings)   # in place: sync reads it too
    strat_label = "EMA 9 / RSI Momentum" if active_strategy == "ema9_rsi_momentum" else active_strategy.replace("_", " ").title()

    # Check if resuming an existing session for today
    session_log = {
        "date": session_label,
        "strategy": active_strategy,
        "strategy_name": strat_label,
        "session_start": now_ist().isoformat(),
        "session_end": None,
        "trades": [],
        "observations": [],
        "total_signals_scanned": 0
    }
    
    if out_file.exists():
        try:
            with open(out_file, "r", encoding="utf-8") as fp:
                existing = json.load(fp)
                session_log["trades"] = existing.get("trades", [])
                session_log["total_signals_scanned"] = existing.get("total_signals_scanned", 0)
                print(f"  [RESUME] Found existing session log for today with {len(session_log['trades'])} prior trade(s). Resuming seamlessly...")
        except Exception:
            pass
    
    active_positions = {}
    prev_signals = {}
    stopped_out_dir = {}  # Tracks symbol -> "BUY" or "SELL" when stopped out
    _sl_lock_logged = {}
    daily_trades_count = len(session_log["trades"])

    # Resume post-SL guard state if last trade today was stopped out
    if session_log["trades"]:
        last_t = session_log["trades"][-1]
        if last_t.get("outcome") == "LOSS" and ("SL" in last_t.get("exit_reason", "") or "STOP" in last_t.get("exit_reason", "")):
            stopped_out_dir[last_t.get("symbol", "NIFTY")] = {
                "direction": last_t.get("direction"),
                "time": time.time(),
                "ts": last_t.get("exit_time", "")
            }
            print(f"  [RESUME] 🛡️ Post-SL Guard Active for {last_t.get('symbol', 'NIFTY')}: last trade {last_t.get('direction')} hit SL.")

    #: Sent once, when the EOD cutoff has closed the last open position.
    eod_confirmed = False
    
    print(f"  [SYS] Active Strategy Engine: {strat_label} ({active_strategy})")
    print(f"  [SYS] Monitoring live candles, momentum strength, and Greeks...")
    save_session_atomic(session_log, out_file)
    
    while running and is_market_open():
        ts = now_ist().strftime("%H:%M:%S")

        # Confirm the square-off explicitly: past the cutoff with nothing left
        # open. Sent once, and only when the day actually had positions, so
        # silence never has to be read as "probably fine".
        if (not eod_confirmed and ist_time() >= EOD_CUTOFF
                and not active_positions and session_log["trades"]):
            eod_confirmed = True
            _closed = len(session_log["trades"])
            _net = sum(t.get("net_pnl", 0.0) for t in session_log["trades"])
            print(f"  [{ts}] ✅ EOD square-off complete — {_closed} trade(s) closed, "
                  f"net Rs.{_net:+.2f}")
            if alerter:
                try:
                    alerter.send_alert(
                        "✅ **All opened positions are closed**\n\n"
                        f"🕒 EOD square-off at {ts} IST\n"
                        f"📊 Trades closed today: {_closed}\n"
                        f"💰 Net P&L: ₹{_net:+,.2f}\n\n"
                        "No position is carried overnight."
                    )
                except Exception as _alert_exc:
                    print(f"  [{ts}] ⚠️  EOD confirmation alert failed: {_alert_exc}")
        
        for symbol in SYMBOLS:
            try:
                sig_res = fetch_signals(symbol)
                if not sig_res:
                    continue
                
                bias = sig_res.get("bias", "NEUTRAL")
                conf = sig_res.get("confidence", 0)
                session_log["total_signals_scanned"] += 1
                
                # 1. Active Position Management (Exit & Trailing Stop Checks)
                if symbol in active_positions:
                    pos = active_positions[symbol]
                    cur_state = analyze_market_state(symbol, pos["direction"])
                    if cur_state:
                        cur_spot = cur_state["spot"]
                        spot_change = cur_spot - pos["entry_spot"]
                        delta = pos["opt_delta"]
                        
                        # ── Mark to the contract's OWN live quote ──────────
                        # Preferred over any estimate: this is the price the
                        # market is actually paying for the exact strike held.
                        # Exit at the BID -- closing a long option means hitting
                        # the bid, never the mid.
                        #
                        # The estimate below is a first-order delta
                        # extrapolation anchored to the ENTRY price. It ignores
                        # gamma (delta itself moves), ignores IV changes
                        # entirely, and compounds its own error the longer a
                        # position is held. It is a fallback for a missing
                        # quote, not a pricing model.
                        live = fetch_live_premium(symbol, pos["strike"], pos["opt_type"])
                        if live:
                            est_opt_ltp = round(live["bid"] or live["ltp"], 2)
                            pos["mark_source"] = "broker"
                            pos["mark_bid"] = live["bid"]
                            pos["mark_ask"] = live["ask"]
                            if live.get("delta") is not None:
                                pos["opt_delta"] = live["delta"]   # keep delta current
                            if live.get("theta") is not None:
                                pos["opt_theta"] = live["theta"]
                            if live.get("iv") is not None:
                                pos["mark_iv"] = live["iv"]
                        else:
                            # Theta from the chain is per DAY; scale it to the
                            # hours actually held. This was a flat 0.05/hour
                            # (~1.2/day) for every contract, against a real ATM
                            # theta near -13.9/day -- a ~12x understatement that
                            # made every held position look better than it was.
                            hours_held = (time.time() - pos["entry_time_epoch"]) / 3600.0
                            theta_per_day = abs(float(pos.get("opt_theta") or 10.0))
                            time_decay = theta_per_day * (hours_held / 24.0)
                            premium_change = (spot_change * delta) - time_decay
                            mid_est = max(0.5, round(pos["entry_premium"] + premium_change, 2))

                            # Apply half the entry spread to this side, mirroring
                            # what the entry already paid on the other.
                            half_spread_pct = float(pos.get("entry_spread_pct") or 0.0) / 2.0
                            est_opt_ltp = max(0.5, round(mid_est * (1.0 - half_spread_pct / 100.0), 2))
                            pos["mark_source"] = "model"
                        pos["current_ltp"] = est_opt_ltp
                        pos["highest_premium"] = max(pos.get("highest_premium", pos["entry_premium"]), est_opt_ltp)
                        pos["lowest_premium"] = min(pos.get("lowest_premium", pos["entry_premium"]), est_opt_ltp)
                        if pos.get("mark_iv"):
                            try:
                                pos["highest_iv"] = max(float(pos.get("highest_iv", pos["mark_iv"])), float(pos["mark_iv"]))
                            except Exception:
                                pass
                        
                        exit_now = False
                        exit_reason = ""
                        
                        # The owner's ladder (ema9_rsi_momentum/exit_ladder.py):
                        # the stop first, then ratchet it up. There is no target
                        # exit -- the old fixed 33% target is now just a rung.
                        if est_opt_ltp <= pos["sl_premium"]:
                            exit_now = True
                            exit_reason = f"{stop_reason(pos['entry_premium'], pos['sl_premium'])} (premium Rs.{est_opt_ltp:.2f})"
                        else:
                            old_sl = pos["sl_premium"]
                            pos_ladder = pos.get("profit_ladder_pct", _EMA9_CFG.profit_ladder_pct)
                            pos_init_sl = pos.get("initial_sl_pct", _EMA9_CFG.initial_sl_pct)
                            pos["sl_premium"], pos["tgt_premium"] = ratchet_stop(
                                pos["entry_premium"], old_sl, pos["highest_premium"],
                                pos_ladder, pos_init_sl,
                            )
                            if pos["sl_premium"] > old_sl:
                                nxt = f"Rs.{pos['tgt_premium']:.2f}" if pos["tgt_premium"] else "none (top rung passed)"
                                mode_tag = f"[{pos.get('trade_mode_label', 'LADDER')}]"
                                print(f"  [{ts}] 🛡️ {mode_tag} Stop ratcheted Rs.{old_sl:.2f} -> Rs.{pos['sl_premium']:.2f} for {pos['contract']} | next rung {nxt}")
                                if alerter:
                                    alerter.send_trailing_sl_alert(
                                        symbol=pos["contract"],
                                        new_sl=pos["sl_premium"],
                                        reason=f"{pos.get('trade_mode_label', 'Stop Ratchet')} from ₹{old_sl:.2f} -> ₹{pos['sl_premium']:.2f} (Next rung: {nxt})",
                                        execution_time=ts,
                                    )
                                save_session_atomic(session_log, out_file)

                            # AI Exit Analyzer (4 Pillars: Plan D Adaptive Tightening, S&R, OI/IV, Midday Regime)
                            if not exit_now and _EMA9_CFG.enable_exit_analyzer and pos.get("highest_premium", 0) > pos["entry_premium"]:
                                iv_delta = None
                                if pos.get("mark_iv") and pos.get("highest_iv"):
                                    try:
                                        iv_delta = float(pos["mark_iv"]) - float(pos["highest_iv"])
                                    except Exception:
                                        pass

                                analysis = _EXIT_ANALYZER.evaluate(
                                    entry_price=pos["entry_premium"],
                                    current_price=est_opt_ltp,
                                    highest_price=pos["highest_premium"],
                                    lowest_price=pos["lowest_premium"],
                                    direction=1,
                                    is_option_premium=True,
                                    current_time=ts,
                                    underlying_price=pos.get("entry_spot"),
                                    iv_change_from_peak=iv_delta,
                                )

                                # Ratchet stop-loss if Plan D calculated a tighter trailing lock
                                if analysis.suggested_sl and analysis.suggested_sl > pos["sl_premium"]:
                                    old_sl = pos["sl_premium"]
                                    pos["sl_premium"] = round(analysis.suggested_sl, 2)
                                    print(f"  [{ts}] 🧠 [AI EXIT ANALYZER] Plan D tightened SL: Rs.{old_sl:.2f} -> Rs.{pos['sl_premium']:.2f}")
                                    if alerter:
                                        alerter.send_trailing_sl_alert(
                                            symbol=pos["contract"],
                                            new_sl=pos["sl_premium"],
                                            reason=f"AI Exit Analyzer ({analysis.mode}) tightened SL to ₹{pos['sl_premium']:.2f}",
                                            execution_time=ts,
                                        )
                                    save_session_atomic(session_log, out_file)

                                if analysis.should_exit:
                                    exit_now = True
                                    exit_reason = f"AI Exit Analyzer ({analysis.mode}): {analysis.reason}"
                                    print(f"  [{ts}] 🎯 [AI EXIT ANALYZER TRIGGER] {exit_reason}")
                        
                        # Reversal exit -- the strategy's own protective rule.
                        # Ranks below SL and target (both are hard limits) but
                        # above the EOD cutoff, so a broken thesis closes when it
                        # breaks rather than being carried to 15:15.
                        if not exit_now:
                            rev = check_reversal_exit(
                                symbol, pos.get("opt_type", "CE"),
                                pos["entry_premium"], est_opt_ltp,
                            )
                            if rev is not None and rev.should_exit:
                                exit_now = True
                                exit_reason = f"REVERSAL EXIT ({rev.reason.split(':')[0]})"
                                print(f"  [{ts}] 🔄 {rev.reason}")
                            elif rev is not None and rev.warning and rev.premium_health:
                                print(f"  [{ts}] ⚠️  Premium decay {rev.premium_health.decay_level} "
                                      f"({rev.premium_health.pct_change:+.1f}%) on {pos['contract']} "
                                      f"— momentum {rev.momentum_strength}, holding.")

                        # EOD square-off
                        if not exit_now and ist_time() >= EOD_CUTOFF:
                            exit_now = True
                            exit_reason = "EOD CUTOFF 15:15 PM AUTO SQUARE-OFF"
                        
                        if exit_now:
                            pos["exit_time"] = ts
                            pos.update(compute_trade_pnl(pos, est_opt_ltp, exit_reason))
                            dur_min = round((time.time() - pos["entry_time_epoch"]) / 60.0, 1)
                            pos["duration_min"] = dur_min
                            
                            session_log["trades"].append(dict(pos))
                            del active_positions[symbol]
                            sync_active_positions(active_positions)

                            # User Rule (2026-10-05): Smart Post-StopLoss Re-entry Guard
                            if pos.get("outcome") == "LOSS" or "STOP LOSS" in exit_reason or "SL" in exit_reason:
                                stopped_out_dir[symbol] = {
                                    "direction": pos["direction"],
                                    "time": time.time(),
                                    "ts": ts
                                }
                                print(f"  [{ts}] 🛡️ Post-SL Guard ACTIVATED for {symbol} ({pos['direction']} hit SL).")
                                print(f"       Reversals allowed immediately; same-direction requires 5m cool-off & fresh confirmation.")
                            else:
                                stopped_out_dir.pop(symbol, None)
                            
                            # Incremental state save immediately on trade exit!
                            save_session_atomic(session_log, out_file)
                            
                            # Record exit in state.db and update realized PnL
                            if record_trade:
                                try:
                                    record_trade(
                                        symbol=pos["contract"],
                                        side="SELL",
                                        price=est_opt_ltp,
                                        timestamp=now_ist().isoformat(),
                                        qty=pos["quantity"]
                                    )
                                except Exception:
                                    pass
                            if update_equity:
                                realized_today = sum(t.get("net_pnl", 0.0) for t in session_log.get("trades", []))
                                running_unrealized = sum((p.get("current_ltp", p["entry_premium"]) - p["entry_premium"]) * p["quantity"] for p in active_positions.values())
                                tot_pnl = round(realized_today + running_unrealized, 2)
                                update_equity(round(CAPITAL + tot_pnl, 2), tot_pnl)
                            
                            # Dispatch real-time Telegram Exit / SL / Target Alert
                            if alerter:
                                alerter.send_exit_alert(
                                    symbol=pos["contract"],
                                    side=pos["direction"],
                                    qty=pos["quantity"],
                                    price=est_opt_ltp,
                                    pnl=pos["net_pnl"],
                                    reason=exit_reason,
                                    execution_time=ts,
                                )
                            
                            icon = "💰 WIN [PROFIT]" if pos["outcome"] == "WIN" else "🛑 LOSS [SL]"
                            print(f"\n  [{ts}] {icon} EXIT {pos['contract']} | {exit_reason}")
                            print(f"       Fill: Rs.{est_opt_ltp:.2f} | Net P&L: Rs.{pos['net_pnl']:+.2f} ({pos['points']:+.2f} pts) | Time: {dur_min}m\n")
                            continue
                        else:
                            # Position still active: sync live mark-to-market PnL to UI
                            sync_active_positions(active_positions)
                            if update_equity:
                                realized_today = sum(t.get("net_pnl", 0.0) for t in session_log.get("trades", []))
                                running_unrealized = sum((p.get("current_ltp", p["entry_premium"]) - p["entry_premium"]) * p["quantity"] for p in active_positions.values())
                                tot_pnl = round(realized_today + running_unrealized, 2)
                                update_equity(round(CAPITAL + tot_pnl, 2), tot_pnl)
                
                # 2. Check New High-Probability Signal Trigger
                obs = signal_observation(sig_res)

                # Single Source of Truth: require verified strategy trigger ("BUY" or "SELL")
                trigger = sig_res.get("trigger")
                strat_sig = sig_res.get("strategy_signal")
                if trigger in ("BUY", "SELL"):
                    direction = trigger
                elif strat_sig == 1:
                    direction = "BUY"
                elif strat_sig == -1:
                    direction = "SELL"
                elif ("BUY" in bias and "BULLISH" not in bias) and conf >= 80:
                    direction = "BUY"
                elif ("SELL" in bias and "BEARISH" not in bias) and conf >= 80:
                    direction = "SELL"
                else:
                    direction = None

                is_high_prob = conf >= 70 and direction is not None
                is_new_trigger = is_new_entry_trigger(prev_signals.get(symbol), obs)
                can_take_trade = (symbol not in active_positions) and (daily_trades_count < MAX_TRADES_PER_DAY) and entry_window_open(active_strategy)

                # ── Post-SL Smart Re-entry Guard (User Rule 2026-10-05) ──
                if is_high_prob and can_take_trade and direction is not None:
                    locked_sl = stopped_out_dir.get(symbol)
                    if locked_sl is not None:
                        locked_dir = locked_sl["direction"]
                        if direction == locked_dir:
                            cooldown_sec = 300.0  # 5 minutes
                            elapsed = time.time() - locked_sl.get("time", 0.0)
                            if elapsed < cooldown_sec:
                                rem = int(cooldown_sec - elapsed)
                                if _sl_lock_logged.get(symbol) != (ts[:5], direction, rem // 30):
                                    _sl_lock_logged[symbol] = (ts[:5], direction, rem // 30)
                                    print(f"  [{ts}] ⏳ {symbol} {direction} in Post-SL Cool-off ({rem}s remaining). "
                                          f"Awaiting cool-off or opposite signal.")
                                continue
                            else:
                                print(f"  [{ts}] 🔄 Post-SL Cool-off elapsed for {symbol}. Evaluating fresh confirmations for {direction}.")
                        else:
                            print(f"  [{ts}] 🎯 Confirmed OPPOSITE strategy signal received after SL for {symbol} ({locked_dir} -> {direction})! SL lock cleared.")
                            stopped_out_dir.pop(symbol, None)
                            _sl_lock_logged.pop(symbol, None)

                if is_high_prob and is_new_trigger and can_take_trade:
                    state = analyze_market_state(symbol, direction)
                    # No fresh data, no entry. On 2026-09-14 (Ganesh Chaturthi,
                    # missing from the holiday list) this book scanned 4,357
                    # times against Friday's last bars.
                    if state and not latest_bar_is_fresh(state.get("bar_time")):
                        if _STALE_DATA_LOGGED.get(symbol) != state.get("bar_time"):
                            _STALE_DATA_LOGGED[symbol] = state.get("bar_time")
                            print(f"  [{ts}] ⛔ {symbol}: last bar {state.get('bar_time')} is not fresh "
                                  f"-- market closed or feed down; not trading.")
                        state = None
                    # The owner's entry-timing rule (2026-09-22): a crossover is
                    # not final until its candle closes, so take the entry in
                    # the last few seconds of the bar -- earlier only when
                    # momentum is already strong enough not to need the wait.
                    if state:
                        strength = classify_momentum_strength(
                            float(state.get("rsi") or 0.0),
                            1 if direction == "BUY" else -1, _EMA9_CFG)
                        # Graded and timed by whichever strategy is selected
                        # in the UI, on whichever timeframe -- see
                        # shared/entry_gate.py.
                        verdict = entry_decision(
                            active_strategy, state.get("frame"),
                            1 if direction == "BUY" else -1, strength,
                            active_settings, datetime.datetime.now(IST))
                        timing_ok, timing_why = verdict.take, str(verdict)
                        if not timing_ok:
                            if _TIMING_LOGGED.get(symbol) != bias:
                                _TIMING_LOGGED[symbol] = bias
                                print(f"  [{ts}] ⏳ {symbol} {direction} held -- {timing_why}")
                            state = None
                        else:
                            _TIMING_LOGGED.pop(symbol, None)

                    if state:
                        opt = select_best_option(symbol, direction, state["spot"])
                        block = (portfolio_block(symbol, direction, opt, session_log, active_positions, active_settings, stopped_out_dir.get(symbol))
                                 if opt and opt["ltp"] > 0 else None)
                        if block:
                            print(f"  [{ts}] ⛔ {symbol} {direction} signal skipped -- {block}")
                        if opt and opt["ltp"] > 0 and not block:
                            # ── Universal Option Chart Confluence Gate ──
                            try:
                                from shared.option_gate import validate_option_entry
                                opt_verdict = validate_option_entry(
                                    symbol=symbol,
                                    direction=direction,
                                    opt_info=opt,
                                    strategy_name=active_strategy,
                                    settings=active_settings,
                                )
                                if not opt_verdict.passed:
                                    print(f"  [{ts}] ⛔ {symbol} {direction} skipped by Option Gate: {opt_verdict.reason}")
                                    continue
                            except Exception as _gate_err:
                                print(f"  [{ts}] ⚠️ Option Gate check warning: {_gate_err}")

                            qty = LOT_SIZE.get(symbol, 65)
                            # Fill at the ASK. A buyer does not get the mid --
                            # they pay the offer. Using ltp (or worse, the old
                            # hardcoded 100.0) silently credited the account with
                            # half the spread on entry, and again on exit. ATM
                            # NIFTY weeklies quoted a 0.42-0.70% spread when this
                            # was measured, so a round trip is roughly 1% of
                            # premium -- material against a 15% stop and a 33%
                            # target.
                            entry_p = round(opt.get("ask") or opt["ltp"], 2)
                            
                            # Multi-Timeframe (15m/1h) Trend Confluence (Ride vs Scalp Mode)
                            htf_info = detect_htf_trend(state.get("frame"))
                            holding_mode = get_trade_holding_mode(direction, htf_info)
                            pos_sl_pct = holding_mode["initial_sl_pct"]
                            pos_ladder = holding_mode["profit_ladder_pct"]

                            sl_p = initial_stop(entry_p, pos_sl_pct)
                            # Not an exit: the ladder's next rung, shown as the target.
                            tgt_p = ratchet_stop(entry_p, 0.0, entry_p, pos_ladder, pos_sl_pct)[1]
                            
                            trade_obj = {
                                "symbol": symbol,
                                "strategy": active_strategy,
                                "strategy_name": strat_label,
                                "contract": opt["contract"],
                                "direction": direction,
                                "opt_type": opt["type"],
                                "strike": opt["strike"],
                                "opt_delta": opt["delta"],
                                "opt_theta": opt.get("theta", -10.0),
                                "entry_spot": state["spot"],
                                "entry_premium": entry_p,
                                "trade_mode": holding_mode["mode"],
                                "trade_mode_label": holding_mode["label"],
                                "profit_ladder_pct": pos_ladder,
                                "initial_sl_pct": pos_sl_pct,
                                "htf_trend_15m": htf_info.get("trend_15m"),
                                "htf_trend_1h": htf_info.get("trend_1h"),
                                "entry_ltp": opt["ltp"],
                                "entry_bid": opt.get("bid", 0.0),
                                "entry_ask": opt.get("ask", 0.0),
                                "entry_spread_pct": opt.get("spread_pct"),
                                "entry_iv": opt.get("iv"),
                                "entry_vix": opt.get("vix"),
                                "option_vwap": opt_verdict.vwap if opt_verdict else None,
                                "option_gate_status": opt_verdict.status if opt_verdict else None,
                                "current_ltp": entry_p,
                                "highest_premium": entry_p,
                                "lowest_premium": entry_p,
                                "sl_premium": sl_p,
                                "tgt_premium": tgt_p,
                                "quantity": qty,
                                "confidence": conf,
                                "rsi": state["rsi"],
                                "ema_quality": state["quality"],
                                "entry_time": ts,
                                "entry_time_epoch": time.time()
                            }
                            
                            active_positions[symbol] = trade_obj
                            stopped_out_dir.pop(symbol, None)
                            _sl_lock_logged.pop(symbol, None)
                            daily_trades_count += 1
                            sync_active_positions(active_positions)
                            
                            # Incremental state save immediately on new trade entry!
                            save_session_atomic(session_log, out_file)

                            # Record trade entry in state.db for UI reflection
                            if record_trade:
                                try:
                                    record_trade(
                                        symbol=opt["contract"],
                                        side="BUY",
                                        price=entry_p,
                                        timestamp=now_ist().isoformat(),
                                        qty=qty
                                    )
                                except Exception:
                                    pass
                            
                            # Dispatch real-time Telegram Entry Alert
                            gate_vwap_str = f" | Option VWAP: Rs.{opt_verdict.vwap:.2f}" if (opt_verdict and opt_verdict.vwap) else ""
                            if alerter:
                                entry_reason = f"{strat_label} Signal Confirmation ({holding_mode['label']}){gate_vwap_str} | RSI: {state.get('rsi', 'N/A')}"
                                alerter.send_trade_alert(
                                    symbol=opt["contract"],
                                    side=direction,
                                    qty=qty,
                                    price=entry_p,
                                    confidence=(conf / 100.0) if conf > 1 else conf,
                                    reason=entry_reason,
                                    execution_time=ts,
                                )
                            
                            print(f"  [{ts}] 🔵 ENTRY {opt['contract']} (Qty: {qty}) @ Rs.{entry_p:.2f} | Mode: {holding_mode['label']}{gate_vwap_str} | Spot: {state['spot']} | Conf: {conf}% | SL: Rs.{sl_p:.2f} | Tgt: Rs.{tgt_p:.2f}")
                
                if obs is not None:
                    prev_signals[symbol] = obs
                
            except Exception as e:
                print(f"  [{ts}] Error in cycle: {e}")
        
        for _ in range(POLL_INTERVAL):
            if not running:
                break
            time.sleep(1)
    
    # Square off any remaining positions at market close
    for symbol, pos in list(active_positions.items()):
        ts = now_ist().strftime("%H:%M:%S")
        pos["exit_time"] = ts
        pos.update(compute_trade_pnl(pos, pos["entry_premium"], "MARKET CLOSE FORCED SQUARE-OFF"))
        pos["duration_min"] = round((time.time() - pos["entry_time_epoch"]) / 60.0, 1)
        session_log["trades"].append(dict(pos))
        print(f"  [{ts}] 🕐 CLOSE {pos['contract']} @ Rs.{pos['entry_premium']:.2f} | P&L: Rs.{pos['net_pnl']:+.2f}")
    
    session_log["session_end"] = now_ist().isoformat()
    trades = session_log["trades"]
    wins = [t for t in trades if t.get("outcome") == "WIN"]
    losses = [t for t in trades if t.get("outcome") == "LOSS"]
    net_pnl = sum(t.get("net_pnl", 0) for t in trades)
    
    session_log["summary"] = {
        "total_trades": len(trades),
        "wins": len(wins),
        "losses": len(losses),
        "win_rate_pct": round(len(wins) / len(trades) * 100.0, 1) if trades else 0.0,
        "total_net_pnl": round(net_pnl, 2),
        "avg_win": round(statistics.mean([t["net_pnl"] for t in wins]), 2) if wins else 0.0,
        "avg_loss": round(statistics.mean([t["net_pnl"] for t in losses]), 2) if losses else 0.0
    }
    
    print(f"\n{'='*65}")
    print(f"  📊 SESSION COMPLETED: {session_label}")
    print(f"     Total Trades : {len(trades)}")
    print(f"     Wins / Losses: {len(wins)} / {len(losses)}")
    print(f"     Win Rate     : {session_log['summary']['win_rate_pct']}%")
    print(f"     Net P&L      : Rs. {net_pnl:+.2f}")
    print(f"{'='*65}")
    
    save_session_atomic(session_log, out_file)
    print(f"  💾 Session log permanently saved: {out_file}\n")
    return session_log

def generate_final_report(all_sessions):
    """Generate comprehensive institutional 3-day audit report."""
    all_trades = [t for s in all_sessions for t in s.get("trades", [])]
    wins = [t for t in all_trades if t.get("outcome") == "WIN"]
    losses = [t for t in all_trades if t.get("outcome") == "LOSS"]
    net_pnl = sum(t.get("net_pnl", 0) for t in all_trades)
    
    win_rate = round(len(wins) / len(all_trades) * 100.0, 1) if all_trades else 0.0
    profit_factor = round(sum(t["net_pnl"] for t in wins) / abs(sum(t["net_pnl"] for t in losses)), 2) if losses and sum(t["net_pnl"] for t in losses) != 0 else 99.0
    
    report = {
        "generated_at": now_ist().isoformat(),
        "total_sessions": len(all_sessions),
        "total_trades": len(all_trades),
        "wins": len(wins),
        "losses": len(losses),
        "win_rate_pct": win_rate,
        "profit_factor": profit_factor,
        "total_net_pnl": round(net_pnl, 2),
        "return_on_capital_pct": round((net_pnl / CAPITAL) * 100.0, 2),
        "sessions": all_sessions
    }
    
    final_file = LOG_DIR / f"3day_expert_report_{now_ist().strftime('%Y%m%d_%H%M')}.json"
    with open(final_file, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    
    print(f"\n{'='*70}")
    print(f"  🎯 3-DAY INSTITUTIONAL AUDIT SCORECARD")
    print(f"     Total Completed Sessions : {len(all_sessions)} / 3")
    print(f"     Total Executed Trades    : {len(all_trades)}")
    print(f"     Overall Win Rate         : {win_rate}%")
    print(f"     Profit Factor            : {profit_factor}")
    print(f"     Total Net P&L            : Rs. {net_pnl:+.2f} ({report['return_on_capital_pct']:+.2f}%)")
    print(f"     Audit Report File        : {final_file}")
    print(f"{'='*70}\n")
    return report

def main():
    print("""
+===================================================================+
|   MANA AI — INSTITUTIONAL PAPER TRADING OBSERVER (v3.0 Engine)   |
|   Strategy  : Premium Trend & Momentum Confirmation               |
|   Symbols   : NIFTY 50 (Lot: 65), BANKNIFTY (Lot: 15) Options     |
|   Features  : Multi-Day Persistence, Incremental Crash Recovery   |
+===================================================================+
""")
    
    while running:
        existing_sessions = detect_existing_sessions()
        all_sessions = [sess_data for _, sess_data in existing_sessions]
        completed_days_count = len(existing_sessions)
        
        # Check today's status
        today_str = now_ist().strftime("%Y-%m-%d")
        today_session = next((s for s in all_sessions if today_str in s.get("date", "")), None)
        
        # Determine current day index
        if today_session and is_market_open():
            # Resume today's active session
            day_idx = completed_days_count
        elif today_session and ist_time() >= MARKET_CLOSE:
            # Today's session is already done, stand by for next day
            day_idx = completed_days_count + 1
        else:
            # Next trading session
            day_idx = completed_days_count + 1
            
        print(f"  [SESSION STATUS] Completed Days: {completed_days_count} | Target Session: Day {day_idx}")
        
        # Check market hours
        if not is_market_open():
            t = ist_time()
            nw = now_ist()
            if t >= MARKET_CLOSE or (today_session and ist_time() >= MARKET_CLOSE):
                tomorrow = nw + datetime.timedelta(days=1)
                while tomorrow.weekday() >= 5:
                    tomorrow += datetime.timedelta(days=1)
                next_open = IST.localize(datetime.datetime.combine(tomorrow.date(), MARKET_OPEN))
                wait_sec = (next_open - nw).total_seconds()
                print(f"\n  Market closed. Next session: {tomorrow.strftime('%A, %b %d')} 09:15 AM (Day {day_idx})")
                print(f"  Observer resting for {int(wait_sec//3600)}h {int((wait_sec%3600)//60)}m...")
                slept = 0
                while running and slept < wait_sec - 60:
                    time.sleep(60)
                    slept += 60
                continue
            elif t < MARKET_OPEN:
                wait_sec = (datetime.datetime.combine(datetime.date.today(), MARKET_OPEN) - datetime.datetime.combine(datetime.date.today(), t)).total_seconds()
                print(f"\n  Market opens in {int(wait_sec//60)} min. Standing by for Day {day_idx}...")
                time.sleep(max(1, wait_sec - 10))
                continue
        
        if now_ist().weekday() >= 5:
            print("  Weekend detected. Standing by for Monday market open...")
            time.sleep(3600)
            continue
        
        # Run today's session
        date_str = now_ist().strftime("%Y-%m-%d")
        day_name = now_ist().strftime("%A")
        run_session(day_idx, date_str, day_name)
        
        # Refresh session list and update audit report
        existing_sessions = detect_existing_sessions()
        all_sessions = [sess_data for _, sess_data in existing_sessions]
        generate_final_report(all_sessions)
        
        # If running as a subprocess under auto_daily_session, complete today's run
        if ist_time() >= MARKET_CLOSE:
            print("  [SESSION COMPLETE] Intraday session closed. Returning to daily orchestrator.")
            break

if __name__ == "__main__":
    main()
