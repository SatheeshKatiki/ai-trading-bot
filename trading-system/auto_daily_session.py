#!/usr/bin/env python3
"""
=============================================================================
  QUANT AI — ZERO-TOUCH DAILY SESSION ORCHESTRATOR (Phase 1 Paper Engine)
=============================================================================
Perspective : 20+ Years Options System Architect & Floor Trader
Mission     : 100% Autonomous, zero-manual-intervention execution lifecycle
             from 08:45 AM Pre-Market to 03:35 PM Post-Market EOD Reporting.

Daily Automation Lifecycle:
  1. [08:45 AM] Pre-Market Wakeup & Holiday / Weekend Filter
  2. [08:46 AM] Headless Auto-Authentication (Fyers TOTP / PIN token generation)
  3. [08:50 AM] Port Cleanup (8000, 3000) & System Maintenance / Log Rotation
  4. [09:00 AM] Boot FastAPI Backend (api_bridge.py) & Wait for Health Check
  5. [09:14 AM] Launch Institutional Paper Trading Observer (paper_observer.py)
  6. [09:15 AM - 15:15 PM] Continuous Process Watchdog & Auto-Recovery
  7. [15:15 PM] Trigger Auto EOD Square-off
  8. [15:30 PM] Generate Institutional Performance Report (Win rate, P&L, Trades)
  9. [15:35 PM] Send Instant Telegram Summary & Graceful Teardown / Sleep
=============================================================================
"""

from __future__ import annotations

import argparse
import datetime
import json
import logging
import os
import pathlib
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request
from typing import Dict, List, Optional, Any

import pytz

# Enforce UTF-8 in Windows Terminal
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if sys.stderr and hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

# Setup Paths
ROOT_DIR = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT_DIR))

# Logging Setup
LOG_DIR = ROOT_DIR / "logs"
LOG_DIR.mkdir(exist_ok=True)
SESSION_LOG = LOG_DIR / "daily_orchestrator.log"

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.FileHandler(SESSION_LOG, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger("Orchestrator")

IST = pytz.timezone("Asia/Kolkata")

# Timing Schedule (IST)
PRE_MARKET_TIME = datetime.time(8, 45)
BACKEND_START_TIME = datetime.time(9, 0)
MARKET_OPEN_TIME = datetime.time(9, 15)
EOD_SQUAREOFF_TIME = datetime.time(15, 15)
MARKET_CLOSE_TIME = datetime.time(15, 30)
EOD_REPORT_TIME = datetime.time(15, 31)

# NSE National Holidays 2026 (YYYY-MM-DD)
NSE_HOLIDAYS_2026 = {
    "2026-01-26",  # Republic Day
    "2026-03-03",  # Holi
    "2026-03-20",  # Id-Ul-Fitr
    "2026-03-27",  # Ram Navami
    "2026-04-03",  # Good Friday
    "2026-04-14",  # Dr. Baba Saheb Ambedkar Jayanti
    "2026-05-01",  # Maharashtra Day
    "2026-05-28",  # Bakri Id
    "2026-06-26",  # Muharram
    "2026-08-15",  # Independence Day
    "2026-09-04",  # Milad-un-Nabi
    "2026-10-02",  # Mahatma Gandhi Jayanti
    "2026-10-20",  # Dussehra
    "2026-11-09",  # Diwali Laxmi Pujan
    "2026-11-10",  # Diwali Balipratipada
    "2026-11-24",  # Gurunanak Jayanti
    "2026-12-25",  # Christmas
}

# Subprocess references
backend_proc: Optional[subprocess.Popen] = None
observer_proc: Optional[subprocess.Popen] = None
is_running = True


def now_ist() -> datetime.datetime:
    return datetime.datetime.now(IST)


def is_trading_day(dt: Optional[datetime.date] = None) -> bool:
    """Check if given date is a weekday and not an NSE holiday."""
    check_date = dt or now_ist().date()
    # 5 = Saturday, 6 = Sunday
    if check_date.weekday() in (5, 6):
        return False
    date_str = check_date.strftime("%Y-%m-%d")
    if date_str in NSE_HOLIDAYS_2026:
        return False
    return True


def send_telegram_notification(message: str) -> None:
    """Send an instant Telegram message via shared.alerts if configured."""
    try:
        from shared.alerts.telegram import alerter
        if alerter and alerter.is_enabled:
            alerter.send_alert(message)
            logger.info("Telegram notification queued: %s", message.splitlines()[0])
        else:
            logger.info("[Telegram Not Configured] Notification: %s", message.splitlines()[0])
    except Exception as e:
        logger.warning("Could not dispatch Telegram alert: %s", e)


def kill_process_on_ports(ports: List[int]) -> None:
    """Kill any zombie processes listening on given ports (Windows/Linux compatible)."""
    for port in ports:
        try:
            if os.name == "nt":
                cmd = f'for /f "tokens=5" %a in (\'netstat -aon ^| findstr :{port}\') do taskkill /PID %a /F /T 2>nul'
                subprocess.run(cmd, shell=True, capture_output=True)
            else:
                subprocess.run(f"fuser -k {port}/tcp 2>/dev/null", shell=True)
            logger.info("Cleaned up port %d", port)
        except Exception as e:
            logger.debug("Port cleanup notice for %d: %s", port, e)


def run_auto_auth() -> bool:
    """Execute automated broker authentication without human intervention."""
    logger.info("==========================================")
    logger.info("STEP 1: Starting Broker Auto-Authentication")
    logger.info("==========================================")
    try:
        from scripts.auth.auto_login_fyers import main as fyers_login
        # Run Fyers auto login
        fyers_login()
        logger.info("Broker auto-authentication routine completed.")
        send_telegram_notification("🟢 [QuantAI] Pre-Market Auto-Auth completed successfully. Access token cached.")
        return True
    except Exception as e:
        err_msg = f"Auto-Authentication failed: {e}"
        logger.error(err_msg, exc_info=True)
        send_telegram_notification(f"⚠️ [QuantAI Alert] Pre-Market Auto-Auth encountered an issue: {e}")
        return False


def run_system_cleanup() -> None:
    """Run log rotation, stale session cleanup, and database maintenance."""
    logger.info("==========================================")
    logger.info("STEP 2: Running System Maintenance & Cleanup")
    logger.info("==========================================")
    kill_process_on_ports([8000, 3000])
    try:
        from shared.maintenance import run_system_maintenance
        res = run_system_maintenance()
        logger.info("System maintenance result: %s", res)
    except Exception as e:
        logger.warning("System maintenance notice: %s", e)


def start_backend_service() -> bool:
    """Launch FastAPI backend (api_bridge.py) and verify health."""
    global backend_proc
    logger.info("==========================================")
    logger.info("STEP 3: Launching FastAPI API Bridge (Port 8000)")
    logger.info("==========================================")
    
    python_exe = sys.executable
    backend_script = ROOT_DIR / "api_bridge.py"
    backend_log = open(LOG_DIR / "api_bridge_stdout.log", "a", encoding="utf-8")
    
    backend_proc = subprocess.Popen(
        [python_exe, str(backend_script)],
        cwd=str(ROOT_DIR),
        stdout=backend_log,
        stderr=subprocess.STDOUT,
    )
    logger.info("API Bridge started with PID: %s", backend_proc.pid)
    
    # Wait for API Bridge to respond on /docs
    max_wait = 30
    start_wait = time.time()
    while time.time() - start_wait < max_wait:
        if backend_proc.poll() is not None:
            logger.error("API Bridge process exited unexpectedly with code %s", backend_proc.returncode)
            return False
        try:
            req = urllib.request.Request("http://127.0.0.1:8000/docs", headers={"User-Agent": "QuantAI-Orchestrator"})
            with urllib.request.urlopen(req, timeout=2) as resp:
                if resp.status == 200:
                    logger.info("✅ API Bridge is UP and responding cleanly!")
                    return True
        except Exception:
            time.sleep(1.5)
            
    logger.warning("API Bridge did not return 200 within %ds, proceeding with watchdog.", max_wait)
    return True


def start_paper_observer() -> bool:
    """Launch the 3-Session Paper Trading Observer (paper_observer.py)."""
    global observer_proc
    logger.info("==========================================")
    logger.info("STEP 4: Launching Paper Trading Observer Engine")
    logger.info("==========================================")
    
    python_exe = sys.executable
    observer_script = ROOT_DIR / "paper_observer.py"
    observer_log = open(LOG_DIR / "paper_observer_stdout.log", "a", encoding="utf-8")
    
    observer_proc = subprocess.Popen(
        [python_exe, str(observer_script)],
        cwd=str(ROOT_DIR),
        stdout=observer_log,
        stderr=subprocess.STDOUT,
    )
    logger.info("Paper Observer started with PID: %s", observer_proc.pid)
    send_telegram_notification(
        "🚀 [QuantAI Live] Market is OPEN (09:15 IST).\n"
        "Institutional Paper Trading Observer is Active.\n"
        "• Assets: NIFTY & BANKNIFTY Options\n"
        "• Strategy: Multi-Timeframe AI Momentum & Strike Selection\n"
        "• Capital: ₹1,00,000 (Virtual)"
    )
    return True


def generate_and_send_eod_report() -> None:
    """Parse today's paper trading logs and send institutional EOD summary."""
    logger.info("==========================================")
    logger.info("STEP 5: Generating Institutional EOD Performance Report")
    logger.info("==========================================")
    
    today_str = now_ist().strftime("%Y-%m-%d")
    obs_log_dir = ROOT_DIR / "paper_obs_logs"
    
    total_trades = 0
    wins = 0
    losses = 0
    total_pnl = 0.0
    trades_detail: List[Dict[str, Any]] = []
    
    # Try finding today's observer logs
    if obs_log_dir.exists():
        for f in obs_log_dir.glob(f"*{today_str}*.json"):
            try:
                with open(f, "r", encoding="utf-8") as jf:
                    data = json.load(jf)
                    if isinstance(data, dict) and "trades" in data:
                        for t in data["trades"]:
                            pnl = float(t.get("pnl", 0.0))
                            total_pnl += pnl
                            total_trades += 1
                            if pnl > 0:
                                wins += 1
                            else:
                                losses += 1
                            trades_detail.append(t)
            except Exception as e:
                logger.warning("Error reading observer log %s: %s", f.name, e)
                
    win_rate = (wins / total_trades * 100.0) if total_trades > 0 else 0.0
    pnl_sign = "+" if total_pnl >= 0 else ""
    
    # Read configured language
    try:
        from shared.config import CONFIG
        lang = getattr(CONFIG, "ALERT_LANGUAGE", "te").lower()
    except Exception:
        lang = os.getenv("ALERT_LANGUAGE", "te").lower()
        
    if lang == "te":
        status_emoji = "🟢 లాభదాయకమైన ముగింపు (PROFIT)" if total_pnl >= 0 else "🔴 నష్టంతో ముగిసింది (LOSS)"
        report_lines = [
            f"📊 *MANA AI — ఇన్‌స్టిట్యూషనల్ డైలీ EOD రిపోర్ట్*",
            f"🗓️ *తేదీ*: {today_str} | సెషన్: Phase 1 (Observer)",
            f"",
            f"💰 *మొత్తం వర్చువల్ లాభం/నష్టం*: *{pnl_sign}₹{total_pnl:,.2f}* ({status_emoji})",
            f"🎯 *మొత్తం ట్రేడ్స్*: `{total_trades}` (గెలిచినవి: `{wins}` | ఓడినవి: `{losses}`)",
            f"📈 *విన్ రేట్ (Win Rate)*: `{win_rate:.1f}%`",
            f"────────────────────────────",
        ]
        if trades_detail:
            report_lines.append("📋 *ట్రేడ్స్ వివరాలు & కారణాలు (Trade Breakdown & Reasons):*")
            for i, t in enumerate(trades_detail[-5:], 1):
                contract = t.get("contract", t.get("symbol", "N/A"))
                p = float(t.get("pnl", 0.0))
                sgn = "+" if p >= 0 else ""
                report_lines.append(f"> {i}. `{contract}`: *{sgn}₹{p:,.2f}*\n>    👉 కారణం: _{t.get('exit_reason', 'Closed')}_")
        else:
            report_lines.append("ℹ️ *మార్కెట్ సారాంశం (Market Summary):*\n> ఈరోజు మార్కెట్ చాపీగా ఉన్నందున AI ఫిల్టర్ ఫాల్స్ సిగ్నల్స్‌ను నివారించి మూలధనాన్ని సురక్షితంగా ఉంచింది.")
        report_lines.extend([
            f"────────────────────────────",
            f"✅ రోజువారీ సెషన్ విజయవంతంగా ముగిసింది. అన్ని పొజిషన్లు స్క్వేర్-ఆఫ్ అయ్యాయి.",
            f"🌙 సిస్టమ్ స్లీప్ మోడ్‌లోకి ప్రవేశించింది (తదుపరి సెషన్: రేపు ఉదయం 08:45 AM IST)."
        ])
    elif lang == "hi":
        status_emoji = "🟢 लाभदायक (PROFITABLE)" if total_pnl >= 0 else "🔴 नुकसान (LOSS)"
        report_lines = [
            f"📊 *MANA AI — दैनिक प्रदर्शन ईओडी रिपोर्ट*",
            f"🗓️ *तारीख (Date)*: {today_str} | सत्र: Phase 1 (Observer)",
            f"────────────────────────────",
            f"💰 *कुल लाभ/हानि (Net P&L)*: *{pnl_sign}₹{total_pnl:,.2f}* ({status_emoji})",
            f"🎯 *कुल ट्रेड्स (Total Trades)*: `{total_trades}` (जीत: `{wins}` | हार: `{losses}`)",
            f"📈 *जीत दर (Win Rate)*: `{win_rate:.1f}%`",
            f"────────────────────────────",
        ]
        if trades_detail:
            report_lines.append("📋 *ट्रेड विवरण और कारण:*")
            for i, t in enumerate(trades_detail[-5:], 1):
                contract = t.get("contract", t.get("symbol", "N/A"))
                p = float(t.get("pnl", 0.0))
                sgn = "+" if p >= 0 else ""
                report_lines.append(f"> {i}. `{contract}`: *{sgn}₹{p:,.2f}*\n>    👉 कारण: _{t.get('exit_reason', 'Closed')}_")
        else:
            report_lines.append("ℹ️ *मार्केट सारांश (Market Summary):*\n> आज कोई ट्रेड नहीं लिया गया (AI ने चॉपी मार्केट में खराब सिग्नलों को फ़िल्टर किया).")
        report_lines.extend([
            f"────────────────────────────",
            f"✅ दैनिक सत्र पूरा हुआ। सभी पोजीशन स्क्वायर-ऑफ कर दी गई हैं.",
            f"🌙 सिस्टम स्लीप मोड में चला गया है (अगला सत्र: कल सुबह 08:45 AM IST)."
        ])
    else:  # English
        status_emoji = "🟢 PROFITABLE" if total_pnl >= 0 else "🔴 LOSS"
        report_lines = [
            f"📊 *MANA AI — INSTITUTIONAL EOD REPORT*",
            f"🗓️ *Date*: {today_str} | Session: Phase 1 (Observer)",
            f"────────────────────────────",
            f"💰 *Total Virtual P&L*: *{pnl_sign}₹{total_pnl:,.2f}* ({status_emoji})",
            f"🎯 *Total Trades*: `{total_trades}` (Wins: `{wins}` | Losses: `{losses}`)",
            f"📈 *Win Rate*: `{win_rate:.1f}%`",
            f"────────────────────────────",
        ]
        if trades_detail:
            report_lines.append("📋 *Trade Breakdown & Reasons:*")
            for i, t in enumerate(trades_detail[-5:], 1):
                contract = t.get("contract", t.get("symbol", "N/A"))
                p = float(t.get("pnl", 0.0))
                sgn = "+" if p >= 0 else ""
                report_lines.append(f"  {i}. `{contract}`: *{sgn}₹{p:,.2f}*\n     👉 Reason: _{t.get('exit_reason', 'Closed')}_")
        else:
            report_lines.append("ℹ️ No trades triggered today (Strict AI Filter avoided chop).")
        report_lines.extend([
            f"────────────────────────────",
            f"✅ Daily session complete. All intraday positions squared off.",
            f"🌙 System entering sleep mode until next trading day 08:45 AM IST."
        ])
        
    eod_report_text = "\n".join(report_lines)
    logger.info("\n%s\n", eod_report_text)

    # ── Generate & dispatch cinematic visual card ──────────────────────────────
    try:
        from shared.alerts.image_generator import generate_eod_card
        from shared.alerts.telegram import alerter
        import json as _json, urllib.request as _req, time as _time

        photo_bytes = generate_eod_card(
            date_str=today_str,
            total_pnl=total_pnl,
            total_trades=total_trades,
            wins=wins,
            losses=losses,
            win_rate=win_rate,
            trades_detail=trades_detail if trades_detail else None,
            session_title="Phase 1 Paper Session",
        )

        if alerter and alerter.is_enabled and photo_bytes:
            url = f"https://api.telegram.org/bot{alerter.bot_token}/sendPhoto"
            boundary = f"----MANAAIBoundary{int(_time.time()*1000)}"
            body = bytearray()

            def _field(name, value):
                body.extend(f"--{boundary}\r\n".encode())
                body.extend(f'Content-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode())

            _field("chat_id", alerter.chat_id)
            _field("caption", "📊 MANA AI ⚡ — Institutional EOD Performance Card")
            # photo binary
            body.extend(f"--{boundary}\r\n".encode())
            body.extend(b'Content-Disposition: form-data; name="photo"; filename="mana_eod.png"\r\n')
            body.extend(b"Content-Type: image/png\r\n\r\n")
            body.extend(photo_bytes)
            body.extend(b"\r\n")
            body.extend(f"--{boundary}--\r\n".encode())

            req = _req.Request(
                url, data=bytes(body),
                headers={"Content-Type": f"multipart/form-data; boundary={boundary}",
                         "User-Agent": "MANA-AI-Alerter/5.0"},
                method="POST"
            )
            with _req.urlopen(req, timeout=35) as resp:
                if resp.status == 200:
                    logger.info("EOD Visual Card & HTML summary queued for dispatch.")
                else:
                    raise RuntimeError(f"sendPhoto status {resp.status}")
    except Exception as img_err:
        logger.warning("Image card generation/dispatch failed (%s); sending text-only...", img_err)
        send_telegram_notification(eod_report_text)
        return

    # Also send rich text summary after the photo
    send_telegram_notification(eod_report_text)
    logger.info("EOD Visual Card & Summary dispatched to Telegram.")


def stop_all_subprocesses() -> None:
    """Gracefully terminate backend and paper observer subprocesses."""
    global backend_proc, observer_proc
    logger.info("Stopping all background services...")
    
    if observer_proc and observer_proc.poll() is None:
        try:
            observer_proc.terminate()
            observer_proc.wait(timeout=5)
            logger.info("Paper Observer terminated.")
        except Exception:
            observer_proc.kill()
            logger.info("Paper Observer force-killed.")
            
    if backend_proc and backend_proc.poll() is None:
        try:
            backend_proc.terminate()
            backend_proc.wait(timeout=5)
            logger.info("API Bridge terminated.")
        except Exception:
            backend_proc.kill()
            logger.info("API Bridge force-killed.")
            
    kill_process_on_ports([8000])


def handle_shutdown(signum, frame):
    global is_running
    logger.info("Shutdown signal received. Cleaning up...")
    is_running = False
    stop_all_subprocesses()
    sys.exit(0)


signal.signal(signal.SIGINT, handle_shutdown)
signal.signal(signal.SIGTERM, handle_shutdown)


def run_session_flow(force_now: bool = False) -> None:
    """Run one single daily market session lifecycle."""
    current_ist = now_ist()
    today_date = current_ist.date()
    current_time = current_ist.time()
    
    if not force_now and not is_trading_day(today_date):
        logger.info("Today (%s) is a Weekend or NSE Holiday. Skipping session.", today_date)
        return
        
    logger.info("=====================================================")
    logger.info("🚀 STARTING AUTOMATED DAILY TRADING SESSION: %s", today_date)
    logger.info("=====================================================")
    
    # 1. Auto Auth
    run_auto_auth()
    
    # 2. Port & System Cleanup
    run_system_cleanup()
    
    # 3. Boot Backend
    if not start_backend_service():
        logger.error("Failed to start backend service. Aborting session.")
        return
        
    # If before 09:14 AM and not forced, wait until market open
    if not force_now:
        while now_ist().time() < datetime.time(9, 14):
            time_left = (datetime.datetime.combine(today_date, datetime.time(9, 14)) - datetime.datetime.combine(today_date, now_ist().time())).total_seconds()
            logger.info("Pre-market initialized. Waiting %d seconds for market open (09:14 AM)...", max(int(time_left), 5))
            time.sleep(min(max(int(time_left), 5), 60))
            
    # 4. Start Paper Observer
    start_paper_observer()
    
    # 5. Market Hours Watchdog Loop
    logger.info("Entering Market Watchdog Loop (09:15 - 15:30 IST)...")
    while is_running:
        curr_t = now_ist().time()
        
        # Check if market has closed
        if not force_now and curr_t >= MARKET_CLOSE_TIME:
            logger.info("Market close reached at %s. Initiating EOD procedures.", curr_t.strftime("%H:%M:%S"))
            break
            
        # Watchdog: Ensure backend is alive
        if backend_proc and backend_proc.poll() is not None:
            logger.warning("API Bridge died! Auto-restarting...")
            start_backend_service()
            
        # Watchdog: Ensure observer is alive during market hours
        if curr_t < EOD_SQUAREOFF_TIME:
            if observer_proc and observer_proc.poll() is not None:
                logger.warning("Paper Observer process stopped unexpectedly! Auto-restarting...")
                start_paper_observer()
                
        time.sleep(20)
        
    # 6. Generate EOD Report & Teardown
    time.sleep(5)  # allow logs to flush
    generate_and_send_eod_report()
    stop_all_subprocesses()
    logger.info("Daily session completed successfully.")


def run_daemon_loop() -> None:
    """Run continuous 24/7 background loop that wakes up at 08:45 AM on trading days."""
    logger.info("QuantAI Zero-Touch Daemon Mode Activated. Running 24/7 scheduler...")
    send_telegram_notification("🤖 [QuantAI] Zero-Touch Daemon Activated on host. Ready to manage trading sessions.")
    
    while is_running:
        current_ist = now_ist()
        today = current_ist.date()
        current_time = current_ist.time()
        
        # If today is trading day and time is between 08:45 AM and 15:30 PM, run session
        if is_trading_day(today):
            if current_time >= PRE_MARKET_TIME and current_time < MARKET_CLOSE_TIME:
                logger.info("Trading window active. Launching session for %s", today)
                run_session_flow()
            elif current_time < PRE_MARKET_TIME:
                target_dt = datetime.datetime.combine(today, PRE_MARKET_TIME, tzinfo=IST)
                sleep_secs = (target_dt - current_ist).total_seconds()
                logger.info("Waiting until 08:45 AM IST (in %d minutes)...", int(sleep_secs / 60))
                time.sleep(min(sleep_secs, 300))
                continue
            else:
                # Market closed for today, sleep until next morning
                logger.info("Market is closed for today. Sleeping until tomorrow morning...")
                time.sleep(1800)
                continue
        else:
            logger.info("Today (%s) is a Non-Trading Day (Weekend/Holiday). Sleeping...", today)
            time.sleep(3600)


def main():
    parser = argparse.ArgumentParser(description="QuantAI Zero-Touch Daily Session Orchestrator")
    parser.add_argument("--daemon", action="store_true", help="Run 24/7 persistent scheduler loop")
    parser.add_argument("--now", action="store_true", help="Force immediate execution of full session for testing")
    parser.add_argument("--test-login", action="store_true", help="Test Fyers auto-login routine and exit")
    parser.add_argument("--test-eod", action="store_true", help="Test EOD report generation and Telegram dispatch")
    args = parser.parse_args()
    
    if args.test_login:
        run_auto_auth()
    elif args.test_eod:
        generate_and_send_eod_report()
    elif args.daemon:
        run_daemon_loop()
    else:
        run_session_flow(force_now=args.now)


if __name__ == "__main__":
    main()
