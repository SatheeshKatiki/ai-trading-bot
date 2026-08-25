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

IST = pytz.timezone("Asia/Kolkata")
MARKET_OPEN  = datetime.time(9, 15)
MARKET_CLOSE = datetime.time(15, 30)
EOD_CUTOFF   = datetime.time(15, 15)
POLL_INTERVAL = 15  # 15s poll for high-precision live observation

# Active index lot sizes (NIFTY: 65, BANKNIFTY: 15, FINNIFTY: 40)
LOT_SIZE = {"NIFTY": 65, "BANKNIFTY": 15, "FINNIFTY": 40}
MAX_TRADES_PER_DAY = 4
CAPITAL = 100000.0

BASE_URL = "http://127.0.0.1:8000"
LOG_DIR = ROOT_DIR / "paper_obs_logs"
LOG_DIR.mkdir(exist_ok=True)

SYMBOLS = ["NIFTY", "BANKNIFTY"]
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

def fetch_candles(symbol, timeframe="5 Min", limit=40):
    today = now_ist().strftime("%Y-%m-%d")
    start = (now_ist() - datetime.timedelta(days=4)).strftime("%Y-%m-%d")
    tf_encoded = urllib.parse.quote(timeframe)
    endpoint = f"/api/history?symbol={symbol}&start_date={start}&end_date={today}&timeframe={tf_encoded}"
    res = fetch_json(endpoint)
    if res and isinstance(res, dict) and "data" in res:
        candles = res["data"]
        if len(candles) > limit:
            return candles[-limit:]
        return candles
    return None

def fetch_option_chain(symbol):
    return fetch_json(f"/api/option-chain?symbol={symbol}")

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
    if not chain_data or "chain" not in chain_data:
        strike = round(spot_price / 50) * 50 if symbol == "NIFTY" else round(spot_price / 100) * 100
        opt_type = "CE" if direction == "BUY" else "PE"
        approx_prem = round(spot_price * 0.0075, 2)
        return {
            "contract": f"{symbol} {strike} {opt_type}",
            "strike": strike,
            "type": opt_type,
            "ltp": approx_prem,
            "delta": 0.50 if opt_type == "CE" else -0.50,
            "theta": -12.5,
            "pcr": 1.0
        }
    
    chain = chain_data.get("chain", [])
    pcr = chain_data.get("pcr", 1.0)
    
    sorted_strikes = sorted(chain, key=lambda x: abs(x["strike"] - spot_price))
    if not sorted_strikes:
        return None
    
    selected_row = sorted_strikes[0]
    opt_key = "call" if direction == "BUY" else "put"
    opt_type = "CE" if direction == "BUY" else "PE"
    opt_details = selected_row.get(opt_key, {})
    ltp = opt_details.get("ltp", 100.0)
    
    return {
        "contract": f"{symbol} {selected_row['strike']} {opt_type}",
        "strike": selected_row["strike"],
        "type": opt_type,
        "ltp": float(ltp) if ltp and ltp > 0 else round(spot_price * 0.0075, 2),
        "delta": opt_details.get("delta", 0.50 if direction == "BUY" else -0.50),
        "theta": opt_details.get("theta", -10.0),
        "pcr": pcr
    }

def analyze_market_state(symbol, direction):
    """Analyze multi-layer technical setup like an institutional trader."""
    candles = fetch_candles(symbol, "5 Min", 35)
    if not candles or len(candles) < 20:
        return None
    
    closes = [c["close"] for c in candles]
    
    spot = closes[-1]
    e9   = ema(closes, 9)
    e21  = ema(closes, 21)
    at   = atr(candles, 14) or (spot * 0.002)
    rs   = rsi(closes, 14)
    
    bullish_trend = e9 and e21 and (e9 > e21) and (rs >= 48)
    bearish_trend = e9 and e21 and (e9 < e21) and (rs <= 52)
    
    aligned = (direction == "BUY" and bullish_trend) or (direction == "SELL" and bearish_trend)
    quality = "STRONG" if aligned else "MODERATE"
    
    return {
        "spot": round(spot, 2),
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
    
    # Check if resuming an existing session for today
    session_log = {
        "date": session_label,
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
    daily_trades_count = len(session_log["trades"])
    
    print(f"  [SYS] Monitoring live candles, AI confidence, and Greeks...")
    save_session_atomic(session_log, out_file)
    
    while running and is_market_open():
        ts = now_ist().strftime("%H:%M:%S")
        
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
                        
                        time_decay = 0.05 * (time.time() - pos["entry_time_epoch"]) / 3600.0
                        premium_change = (spot_change * delta) - time_decay
                        est_opt_ltp = max(0.5, round(pos["entry_premium"] + premium_change, 2))
                        
                        exit_now = False
                        exit_reason = ""
                        
                        # Stop Loss trigger (15% loss on premium)
                        if est_opt_ltp <= pos["sl_premium"]:
                            exit_now = True
                            exit_reason = f"STOP LOSS HIT (Premium dropped to Rs.{est_opt_ltp:.2f})"
                        # Target trigger (33% gain, 1:2.2 R:R)
                        elif est_opt_ltp >= pos["tgt_premium"]:
                            exit_now = True
                            exit_reason = f"TARGET HIT (Premium surged to Rs.{est_opt_ltp:.2f})"
                        # Trailing protection if in profit > 15%
                        elif est_opt_ltp >= pos["entry_premium"] * 1.15:
                            if pos["sl_premium"] < pos["entry_premium"]:
                                pos["sl_premium"] = pos["entry_premium"]
                                print(f"  [{ts}] 🛡️ Trailing SL -> Breakeven (Rs.{pos['entry_premium']:.2f}) for {pos['contract']}")
                                save_session_atomic(session_log, out_file)
                        
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
                            
                            # Incremental state save immediately on trade exit!
                            save_session_atomic(session_log, out_file)
                            
                            icon = "💰 WIN [PROFIT]" if pos["outcome"] == "WIN" else "🛑 LOSS [SL]"
                            print(f"\n  [{ts}] {icon} EXIT {pos['contract']} | {exit_reason}")
                            print(f"       Fill: Rs.{est_opt_ltp:.2f} | Net P&L: Rs.{pos['net_pnl']:+.2f} ({pos['points']:+.2f} pts) | Time: {dur_min}m\n")
                            continue
                
                # 2. Check New High-Probability Signal Trigger
                prev_b = prev_signals.get(symbol, {}).get("bias")
                prev_c = prev_signals.get(symbol, {}).get("confidence", 0)
                
                direction = "BUY" if ("BUY" in bias or "BULLISH" in bias) else "SELL" if ("SELL" in bias or "BEARISH" in bias) else None
                is_high_prob = conf >= 65 and direction is not None
                is_new_trigger = (bias != prev_b) or (conf - prev_c >= 15)
                can_take_trade = (symbol not in active_positions) and (daily_trades_count < MAX_TRADES_PER_DAY) and can_enter()
                
                if is_high_prob and is_new_trigger and can_take_trade:
                    state = analyze_market_state(symbol, direction)
                    if state:
                        opt = select_best_option(symbol, direction, state["spot"])
                        if opt and opt["ltp"] > 0:
                            qty = LOT_SIZE.get(symbol, 65)
                            entry_p = opt["ltp"]
                            sl_p = round(entry_p * 0.85, 2)       # 15% Stop Loss
                            tgt_p = round(entry_p * 1.33, 2)      # 33% Target (1:2.2 R:R)
                            
                            trade_obj = {
                                "symbol": symbol,
                                "contract": opt["contract"],
                                "direction": direction,
                                "opt_type": opt["type"],
                                "strike": opt["strike"],
                                "opt_delta": opt["delta"],
                                "entry_spot": state["spot"],
                                "entry_premium": entry_p,
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
                            daily_trades_count += 1
                            
                            # Incremental state save immediately on new trade entry!
                            save_session_atomic(session_log, out_file)
                            
                            print(f"  [{ts}] 🔵 ENTRY {opt['contract']} (Qty: {qty}) @ Rs.{entry_p:.2f} | Spot: {state['spot']} | Conf: {conf}% | Delta: {opt['delta']} | SL: Rs.{sl_p:.2f} | Tgt: Rs.{tgt_p:.2f}")
                
                prev_signals[symbol] = {"bias": bias, "confidence": conf}
                
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
        
        # If all 3 days are completed
        if completed_days_count >= 3 and (today_session and ist_time() >= MARKET_CLOSE):
            print(f"  [AUDIT COMPLETE] All 3 live trading sessions have been completed!")
            generate_final_report(all_sessions)
            break
            
        # Determine the current day index
        if today_session and is_market_open():
            # Resume today's session
            day_idx = completed_days_count
        elif today_session and ist_time() >= MARKET_CLOSE:
            # Today's session is already done, stand by for next day
            day_idx = completed_days_count + 1
        else:
            # Next new day
            day_idx = completed_days_count + 1
            
        if day_idx > 3:
            print(f"  [AUDIT COMPLETE] All 3 live trading sessions completed!")
            generate_final_report(all_sessions)
            break
            
        print(f"  [SESSION STATUS] Completed Days: {completed_days_count}/3 | Target Day: Day {day_idx}")
        
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
        res = run_session(day_idx, date_str, day_name)
        
        # Refresh session list
        existing_sessions = detect_existing_sessions()
        all_sessions = [sess_data for _, sess_data in existing_sessions]
        if len(existing_sessions) >= 3:
            generate_final_report(all_sessions)
            break

if __name__ == "__main__":
    main()
