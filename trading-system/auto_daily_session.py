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

# ---------------------------------------------------------------------------
# NSE trading holidays, keyed by year (YYYY-MM-DD)
# ---------------------------------------------------------------------------
# This was a single flat `NSE_HOLIDAYS_2026` set, consulted unconditionally.
# From 2027-01-01 every lookup would have missed, so `is_trading_day()` would
# have returned True on every NSE holiday and the orchestrator would have run
# a full session -- auto-auth, backend, observer -- into a closed exchange,
# every holiday, silently. Keying by year makes the gap detectable instead of
# invisible; `assert_holiday_calendar_current()` then makes it loud.
#
# NSE publishes the next year's list late in the preceding year. Add the new
# year here when it does. Do NOT guess: several of these are lunar and move.
NSE_HOLIDAYS: Dict[int, set] = {
    2026: {
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
    },
}

#: Backwards-compatible alias for anything still referring to the flat set.
NSE_HOLIDAYS_2026 = NSE_HOLIDAYS[2026]

#: Years already reported as uncovered, so the alert fires once per run.
_holiday_gap_reported: set = set()


def holiday_calendar_covers(year: int) -> bool:
    """Is there a published NSE holiday list loaded for `year`?"""
    return year in NSE_HOLIDAYS


def assert_holiday_calendar_current(today: Optional[datetime.date] = None) -> bool:
    """Warn loudly, once per year per run, if the calendar has run out.

    Returns True when the year is covered. The session is still allowed to
    proceed -- refusing to trade for a whole year because a data file is stale
    would be worse than trading one holiday into a closed exchange, and the
    broker rejects orders on a holiday anyway. But it must never be silent.
    """
    day = today or now_ist().date()
    if holiday_calendar_covers(day.year):
        return True
    if day.year not in _holiday_gap_reported:
        _holiday_gap_reported.add(day.year)
        logger.error(
            "NSE holiday calendar has no entry for %d (loaded years: %s). Every "
            "holiday this year will be treated as a normal trading day. Add %d "
            "to NSE_HOLIDAYS in auto_daily_session.py.",
            day.year, sorted(NSE_HOLIDAYS), day.year,
        )
        send_telegram_notification(
            f"\u26a0\ufe0f [QuantAI] NSE holiday calendar has no entry for {day.year}. "
            f"The orchestrator will run sessions on exchange holidays until it is added."
        )
    return False

# Subprocess references
backend_proc: Optional[subprocess.Popen] = None
observer_proc: Optional[subprocess.Popen] = None
is_running = True

# ---------------------------------------------------------------------------
# Process supervision policy
# ---------------------------------------------------------------------------
# Root-caused 2026-09-09 from logs/daily_orchestrator.log: on 2026-09-07 the
# Paper Observer was relaunched 370 times between 09:14 and 11:17 IST -- one
# restart every 20s for the first two hours of the trading session, during
# which no paper trading happened at all. The observer was NOT crashing: it
# was the pre-v3.13.0 3-day-capped build, so it printed
# "[AUDIT COMPLETE] All 3 live trading sessions completed!" and exited
# cleanly (returncode 0) within about two seconds, every single time. The old
# watchdog only asked `proc.poll() is not None` -- it could not tell a
# deliberate, successful exit from a crash, so it fought the child's own
# decision to stop, forever.
#
# The policy below encodes what a supervisor actually needs to know:
#
#   * returncode == 0 -> the child chose to stop and had a reason. Relaunching
#     an identical process cannot change that reason, so we do NOT restart.
#     We escalate once and leave it down. This alone would have turned the
#     2026-09-07 incident into a single Telegram alert at 09:14.
#   * returncode != 0 -> a genuine fault. Restart, but with a backoff ladder
#     and a hard ceiling, so a permanently-broken child costs a handful of
#     alerts instead of thrashing the machine until the closing bell.
#   * A child that stayed up long enough to be considered healthy starts a
#     fresh burst -- a crash at 14:00 after five clean hours is a new
#     incident, not the continuation of a 09:15 one.

# Seconds to wait before the Nth restart of the current burst. The final
# value repeats once the ladder is exhausted.
_RESTART_BACKOFF_S = (0, 5, 15, 30, 60, 120, 300)

# A child that stayed up at least this long is treated as having started
# successfully; its later exit begins a new burst with a fresh budget.
_MIN_HEALTHY_UPTIME_S = 120

# Hard ceiling on restarts inside one burst before the supervisor gives up.
_MAX_RESTARTS_PER_BURST = 5

# The same idea one level up, for whole-session retries in --daemon mode.
_MAX_SESSION_ATTEMPTS_PER_DAY = 3
_SESSION_RETRY_COOLDOWN_S = 300
_session_attempts: Dict[datetime.date, int] = {}


class ServiceSupervisor:
    """Supervises one long-running child process for a trading session.

    Owns the child's stdout file handle (the previous watchdog opened a new
    one on every restart and never closed any of them -- 372 leaked handles
    on 2026-09-07), its restart budget, and the decision of whether an exit
    is even worth restarting.
    """

    def __init__(self, name: str, launcher, log_filename: str, restart_on_clean_exit: bool = False):
        self.name = name
        self._launcher = launcher            # () -> list[str] argv
        self._log_filename = log_filename
        self._restart_on_clean_exit = restart_on_clean_exit

        self.proc: Optional[subprocess.Popen] = None
        self._log_handle = None
        self._started_at: float = 0.0
        self._restarts_in_burst: int = 0
        self._next_restart_allowed_at: float = 0.0
        self.launches: int = 0               # total, across all bursts
        self.given_up: bool = False          # ceiling hit, or clean exit honoured

    # -- lifecycle ---------------------------------------------------------

    def _close_log(self) -> None:
        if self._log_handle is not None:
            try:
                self._log_handle.close()
            except Exception:
                pass
            self._log_handle = None

    def start(self) -> bool:
        """Launch the child. Returns True if the process object was created."""
        self._close_log()
        try:
            self._log_handle = open(LOG_DIR / self._log_filename, "a", encoding="utf-8")
            self.proc = subprocess.Popen(
                self._launcher(),
                cwd=str(ROOT_DIR),
                stdout=self._log_handle,
                stderr=subprocess.STDOUT,
            )
        except Exception as exc:
            logger.error("Failed to launch %s: %s", self.name, exc, exc_info=True)
            self._close_log()
            self.proc = None
            return False

        self._started_at = time.time()
        self.launches += 1
        logger.info("%s started with PID: %s (launch #%d)", self.name, self.proc.pid, self.launches)
        return True

    def is_alive(self) -> bool:
        return self.proc is not None and self.proc.poll() is None

    def reset(self) -> None:
        """Clear the restart budget and the give-up latch for a new session.

        The supervisors are module singletons, so in --daemon mode they
        outlive any one trading day. Without this, a `given_up` latch set on
        Monday would silently leave the service unsupervised for the rest of
        the week.
        """
        self._restarts_in_burst = 0
        self._next_restart_allowed_at = 0.0
        self.given_up = False

    def stop(self, timeout: float = 5.0) -> None:
        """Terminate the child, escalating to kill, then release its log handle."""
        if self.proc is not None and self.proc.poll() is None:
            try:
                self.proc.terminate()
                self.proc.wait(timeout=timeout)
                logger.info("%s terminated.", self.name)
            except Exception:
                try:
                    self.proc.kill()
                    logger.info("%s force-killed.", self.name)
                except Exception:
                    pass
        self._close_log()

    # -- supervision -------------------------------------------------------

    def supervise(self) -> None:
        """Called on every watchdog tick. Restarts the child only when that
        can plausibly help, and never faster than the backoff ladder allows."""
        if self.proc is None or self.given_up or self.is_alive():
            return

        rc = self.proc.returncode
        uptime = time.time() - self._started_at

        # A child that ran long enough to be healthy starts a fresh burst.
        if uptime >= _MIN_HEALTHY_UPTIME_S:
            self._restarts_in_burst = 0
            self._next_restart_allowed_at = 0.0

        # Case 1: deliberate, successful exit. Restarting cannot change the
        # decision the child just made -- honour it and escalate once.
        if rc == 0 and not self._restart_on_clean_exit:
            self.given_up = True
            self._close_log()
            logger.warning(
                "%s exited cleanly (code 0) after %.0fs. A clean exit is the child's own "
                "decision, not a fault -- NOT restarting. See %s for its final output.",
                self.name, uptime, self._log_filename,
            )
            send_telegram_notification(
                f"ℹ️ [QuantAI] {self.name} finished on its own (exit code 0) after "
                f"{uptime / 60:.0f} min and will not be relaunched this session.\n"
                f"Check logs/{self._log_filename} for why it stopped."
            )
            return

        # Case 2: crash budget exhausted.
        if self._restarts_in_burst >= _MAX_RESTARTS_PER_BURST:
            self.given_up = True
            self._close_log()
            logger.error(
                "%s crashed %d times in a row (last exit code %s). Restart ceiling reached "
                "-- giving up for this session rather than thrashing.",
                self.name, self._restarts_in_burst, rc,
            )
            send_telegram_notification(
                f"🛑 [QuantAI Alert] {self.name} crashed {self._restarts_in_burst} times "
                f"consecutively (exit code {rc}). Supervisor has STOPPED restarting it.\n"
                f"Manual intervention needed — see logs/{self._log_filename}."
            )
            return

        # Case 3: genuine fault, budget remaining -- restart behind the ladder.
        now = time.time()
        if self._next_restart_allowed_at:
            # A restart is already scheduled; wait for it to come due.
            if now < self._next_restart_allowed_at:
                return
        else:
            delay = _RESTART_BACKOFF_S[min(self._restarts_in_burst, len(_RESTART_BACKOFF_S) - 1)]
            if delay:
                self._next_restart_allowed_at = now + delay
                logger.warning(
                    "%s exited with code %s after %.0fs. Restart %d/%d scheduled in %ds (backoff).",
                    self.name, rc, uptime, self._restarts_in_burst + 1, _MAX_RESTARTS_PER_BURST, delay,
                )
                return

        self._restarts_in_burst += 1
        self._next_restart_allowed_at = 0.0
        logger.warning(
            "%s exited with code %s after %.0fs. Restarting (%d/%d)...",
            self.name, rc, uptime, self._restarts_in_burst, _MAX_RESTARTS_PER_BURST,
        )
        self.start()


def now_ist() -> datetime.datetime:
    return datetime.datetime.now(IST)


def is_trading_day(dt: Optional[datetime.date] = None) -> bool:
    """Is `dt` a weekday the NSE is actually open on?

    Looks the date up in that year's calendar rather than a single hardcoded
    year's set -- see NSE_HOLIDAYS. When the year is not covered the holiday
    check cannot be performed, so the day is treated as a trading day and
    `assert_holiday_calendar_current()` reports the gap.
    """
    check_date = dt or now_ist().date()
    # 5 = Saturday, 6 = Sunday
    if check_date.weekday() in (5, 6):
        return False
    holidays = NSE_HOLIDAYS.get(check_date.year)
    if holidays and check_date.strftime("%Y-%m-%d") in holidays:
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
    """Kill whatever is LISTENING on each given port. Exact, not approximate.

    This used to shell out to::

        for /f "tokens=5" %a in ('netstat -aon ^| findstr :8000') do taskkill /PID %a /F /T

    ``findstr`` does a plain substring match, so ``:3000`` also matched
    ``:30000``-``:30009`` and any *foreign* address ending in those digits --
    then ``taskkill /F /T`` killed that PID and its whole process tree. On a
    machine running anything else in the 30000-32767 range (Docker, Kubernetes
    node ports, dev servers) this could take out unrelated software, and the
    Linux branch had the same shape via ``fuser -k``.

    psutil is already a dependency (it backs the singleton-instance guard), so
    match the port exactly, require the socket to be LISTENING, and never kill
    this process or its own parent.
    """
    try:
        import psutil
    except Exception as exc:      # pragma: no cover - psutil is a hard dep
        logger.warning("psutil unavailable, skipping port cleanup: %s", exc)
        return

    wanted = set(ports)
    self_pid = os.getpid()
    protected = {self_pid, os.getppid()}
    victims: dict = {}

    try:
        for conn in psutil.net_connections(kind="inet"):
            if conn.status != psutil.CONN_LISTEN or not conn.laddr:
                continue
            if conn.laddr.port not in wanted or not conn.pid:
                continue
            if conn.pid in protected:
                logger.debug("Not killing PID %s on port %s (self/parent)",
                             conn.pid, conn.laddr.port)
                continue
            victims.setdefault(conn.pid, set()).add(conn.laddr.port)
    except psutil.AccessDenied:
        logger.warning("Insufficient privileges to enumerate listening sockets; "
                       "skipping port cleanup.")
        return
    except Exception as exc:
        logger.warning("Could not enumerate listening sockets: %s", exc)
        return

    for pid, occupied in victims.items():
        try:
            proc = psutil.Process(pid)
            name = proc.name()
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except psutil.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=3)
            logger.info("Freed port(s) %s (killed PID %s, %s)",
                        sorted(occupied), pid, name)
        except psutil.NoSuchProcess:
            pass
        except Exception as exc:
            logger.warning("Could not stop PID %s holding port(s) %s: %s",
                           pid, sorted(occupied), exc)

    for port in sorted(wanted - {p for pl in victims.values() for p in pl}):
        logger.debug("Port %d already free.", port)


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


backend_sv = ServiceSupervisor(
    "API Bridge",
    lambda: [sys.executable, str(ROOT_DIR / "api_bridge.py")],
    "api_bridge_stdout.log",
    # The API bridge is a server: it is never "done", so even a code-0 exit
    # is an abnormal condition worth retrying.
    restart_on_clean_exit=True,
)
observer_sv = ServiceSupervisor(
    "Paper Observer",
    lambda: [sys.executable, "-u", str(ROOT_DIR / "paper_observer.py")],
    "paper_observer_stdout.log",
    # The observer legitimately ends its own session (EOD square-off, audit
    # complete, nothing to trade). Honour that -- see the incident note above.
    restart_on_clean_exit=False,
)


def start_backend_service() -> bool:
    """Launch FastAPI backend (api_bridge.py) and verify health."""
    global backend_proc
    logger.info("==========================================")
    logger.info("STEP 3: Launching FastAPI API Bridge (Port 8000)")
    logger.info("==========================================")

    if not backend_sv.start():
        return False
    backend_proc = backend_sv.proc

    # Wait for API Bridge to respond on /docs
    max_wait = 30
    start_wait = time.time()
    while time.time() - start_wait < max_wait:
        if backend_sv.proc.poll() is not None:
            logger.error("API Bridge process exited unexpectedly with code %s", backend_sv.proc.returncode)
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
    """Launch the Paper Trading Observer (paper_observer.py)."""
    global observer_proc
    logger.info("==========================================")
    logger.info("STEP 4: Launching Paper Trading Observer Engine")
    logger.info("==========================================")

    if not observer_sv.start():
        return False
    observer_proc = observer_sv.proc

    # Announce once per session only. This notification used to live on every
    # launch, so the 2026-09-07 restart loop also fired 370 identical
    # "Market is OPEN" Telegram messages -- enough noise to bury the one
    # alert that actually mattered.
    if observer_sv.launches == 1:
        strat_display = "EMA 9 / RSI Momentum"
        try:
            settings_path = ROOT_DIR / "config" / "settings.json"
            if settings_path.exists():
                with open(settings_path, "r", encoding="utf-8") as f:
                    s_data = json.load(f)
                    act = s_data.get("active_strategy", "ema9_rsi_momentum")
                    strat_display = "EMA 9 / RSI Momentum" if act == "ema9_rsi_momentum" else act.replace("_", " ").title()
        except Exception:
            pass

        send_telegram_notification(
            "🚀 [QuantAI Live] Market is OPEN (09:15 IST).\n"
            "Institutional Paper Trading Observer is Active.\n"
            "• Assets: NIFTY & BANKNIFTY Options\n"
            f"• Strategy: {strat_display}\n"
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
    
    # Read active strategy from settings
    strat_display = "EMA 9 / RSI Momentum"
    try:
        settings_path = ROOT_DIR / "config" / "settings.json"
        if settings_path.exists():
            with open(settings_path, "r", encoding="utf-8") as f:
                s_data = json.load(f)
                act = s_data.get("active_strategy", "ema9_rsi_momentum")
                strat_display = "EMA 9 / RSI Momentum" if act == "ema9_rsi_momentum" else act.replace("_", " ").title()
    except Exception:
        pass

    # Try finding today's observer logs
    if obs_log_dir.exists():
        for f in sorted(obs_log_dir.glob(f"*{today_str}*.json")):
            try:
                with open(f, "r", encoding="utf-8") as jf:
                    data = json.load(jf)
                    if isinstance(data, dict):
                        if data.get("strategy_name"):
                            strat_display = data["strategy_name"]
                        if "trades" in data and isinstance(data["trades"], list):
                            for t in data["trades"]:
                                pnl = float(t.get("net_pnl", t.get("pnl", 0.0)))
                                total_pnl += pnl
                                total_trades += 1
                                if pnl > 0:
                                    wins += 1
                                else:
                                    losses += 1
                                t_copy = dict(t)
                                t_copy["pnl"] = pnl
                                t_copy["net_pnl"] = pnl
                                trades_detail.append(t_copy)
                        if "summary" in data and isinstance(data["summary"], dict):
                            if "total_net_pnl" in data["summary"]:
                                total_pnl = float(data["summary"]["total_net_pnl"])
                            if "wins" in data["summary"]:
                                wins = int(data["summary"]["wins"])
                            if "losses" in data["summary"]:
                                losses = int(data["summary"]["losses"])
                            if "total_trades" in data["summary"]:
                                total_trades = int(data["summary"]["total_trades"])
            except Exception as e:
                logger.warning("Error reading observer log %s: %s", f.name, e)
                
    total_pnl = round(total_pnl, 2)
    win_rate = (wins / total_trades * 100.0) if total_trades > 0 else 0.0
    pnl_formatted = f"+₹{total_pnl:,.2f}" if total_pnl >= 0 else f"-₹{abs(total_pnl):,.2f}"
    
    # Dual dynamic ROI calculations (Option 1: Margin Deployed, Option 2: Account Capital)
    capital = 100000.0
    total_deployed = sum(float(t.get("entry_premium", t.get("entry_price", 0.0))) * int(t.get("quantity", t.get("qty", 1))) for t in trades_detail) if trades_detail else 0.0
    margin_roi = (total_pnl / total_deployed * 100.0) if total_deployed > 0 else ((total_pnl / capital * 100.0) if capital > 0 else 0.0)
    account_roi = (total_pnl / capital * 100.0) if capital > 0 else 0.0

    margin_roi_str = f"+{margin_roi:.2f}%" if margin_roi >= 0 else f"{margin_roi:.2f}%"
    account_roi_str = f"+{account_roi:.2f}%" if account_roi >= 0 else f"{account_roi:.2f}%"
    roi_indicator = "🟢" if total_pnl >= 0 else "🔴"

    # Read configured language
    try:
        from shared.config import CONFIG
        lang = getattr(CONFIG, "ALERT_LANGUAGE", "te").lower()
    except Exception:
        lang = os.getenv("ALERT_LANGUAGE", "te").lower()
        
    if lang == "te":
        status_emoji = "🟢 లాభదాయకమైన ముగింపు (PROFIT)" if total_pnl >= 0 else "🔴 నష్టంతో ముగిసింది (CONTROLLED LOSS)"
        report_lines = [
            f"📊 *MANA AI — ఇన్‌స్టిట్యూషనల్ డైలీ EOD రిపోర్ట్*",
            f"🗓️ *తేదీ*: {today_str} | సెషన్: Phase 1 (Observer)",
            f"🎯 *వ్యూహం (Strategy)*: `{strat_display}`",
            f"────────────────────────────",
            f"💰 *మొత్తం వర్చువల్ లాభం/నష్టం*: *{pnl_formatted}* ({status_emoji})",
            f"📈 *మార్జిన్ ROI (Margin ROI)*: *{margin_roi_str}* {roi_indicator} (పెట్టుబడి పై రాబడి)",
            f"💼 *ఖాతా ఇంపాక్ట్ (Account ROI)*: *{account_roi_str}* {roi_indicator} (మొత్తం క్యాపిటల్ పై)",
            f"💵 *వినియోగించిన మార్జిన్ (Margin Deployed)*: `₹{total_deployed:,.2f}`",
            f"🎯 *మొత్తం ట్రేడ్స్*: `{total_trades}` (గెలిచినవి: `{wins}` | ఓడినవి: `{losses}`)",
            f"📈 *విన్ రేట్ (Win Rate)*: `{win_rate:.1f}%`",
            f"────────────────────────────",
        ]
        if trades_detail:
            report_lines.append("📋 *ట్రేడ్స్ వివరాలు & కారణాలు (Trade Breakdown & Reasons):*")
            for i, t in enumerate(trades_detail, 1):
                contract = t.get("contract", t.get("symbol", "N/A"))
                p = float(t.get("net_pnl", t.get("pnl", 0.0)))
                p_item = f"+₹{p:,.2f}" if p >= 0 else f"-₹{abs(p):,.2f}"
                t_inv = float(t.get("entry_premium", t.get("entry_price", 0.0))) * int(t.get("quantity", t.get("qty", 1)))
                t_roi = (p / t_inv * 100.0) if t_inv > 0 else 0.0
                t_roi_str = f"+{t_roi:.1f}%" if t_roi >= 0 else f"{t_roi:.1f}%"
                t_dot = "🟢" if p >= 0 else "🔴"
                report_lines.append(f"> {i}. `{contract}`: *{p_item}* ({t_roi_str} ROI) {t_dot}\n>    👉 కారణం: _{t.get('exit_reason', 'Closed')}_")
        else:
            report_lines.append("ℹ️ *మార్కెట్ సారాంశం (Market Summary):*\n> ఈరోజు మార్కెట్ చాపీగా ఉన్నందున AI ఫిల్టర్ ఫాల్స్ సిగ్నల్స్‌ను నివారించి మూలధనాన్ని సురక్షితంగా ఉంచింది.")
        report_lines.extend([
            f"────────────────────────────",
            f"✅ రోజువారీ సెషన్ విజయవంతంగా ముగిసింది. అన్ని పొజిషన్లు స్క్వేర్-ఆఫ్ అయ్యాయి.",
            f"🌙 సిస్టమ్ స్లీప్ మోడ్‌లోకి ప్రవేశించింది (తదుపరి సెషన్: రేపు ఉదయం 08:45 AM IST)."
        ])
    elif lang == "hi":
        status_emoji = "🟢 लाभदायक (PROFITABLE)" if total_pnl >= 0 else "🔴 नुकसान (CONTROLLED LOSS)"
        report_lines = [
            f"📊 *MANA AI — दैनिक प्रदर्शन ईओडी रिपोर्ट*",
            f"🗓️ *तारीख (Date)*: {today_str} | सत्र: Phase 1 (Observer)",
            f"🎯 *रणनीति (Strategy)*: `{strat_display}`",
            f"────────────────────────────",
            f"💰 *कुल लाभ/हानि (Net P&L)*: *{pnl_formatted}* ({status_emoji})",
            f"📈 *मार्जिन ROI (Margin ROI)*: *{margin_roi_str}* {roi_indicator} (निवेश पर रिटर्न)",
            f"💼 *खाता प्रभाव (Account ROI)*: *{account_roi_str}* {roi_indicator} (पूंजी पर रिटर्न)",
            f"💵 *उपयोग किया गया मार्जिन*: `₹{total_deployed:,.2f}`",
            f"🎯 *कुल ट्रेड्स (Total Trades)*: `{total_trades}` (जीत: `{wins}` | हार: `{losses}`)",
            f"📈 *जीत दर (Win Rate)*: `{win_rate:.1f}%`",
            f"────────────────────────────",
        ]
        if trades_detail:
            report_lines.append("📋 *ट्रेड विवरण और कारण:*")
            for i, t in enumerate(trades_detail, 1):
                contract = t.get("contract", t.get("symbol", "N/A"))
                p = float(t.get("net_pnl", t.get("pnl", 0.0)))
                p_item = f"+₹{p:,.2f}" if p >= 0 else f"-₹{abs(p):,.2f}"
                t_inv = float(t.get("entry_premium", t.get("entry_price", 0.0))) * int(t.get("quantity", t.get("qty", 1)))
                t_roi = (p / t_inv * 100.0) if t_inv > 0 else 0.0
                t_roi_str = f"+{t_roi:.1f}%" if t_roi >= 0 else f"{t_roi:.1f}%"
                t_dot = "🟢" if p >= 0 else "🔴"
                report_lines.append(f"> {i}. `{contract}`: *{p_item}* ({t_roi_str} ROI) {t_dot}\n>    👉 कारण: _{t.get('exit_reason', 'Closed')}_")
        else:
            report_lines.append("ℹ️ *मार्केट सारांश (Market Summary):*\n> आज कोई ट्रेड नहीं लिया गया (AI ने चॉपी मार्केट में खराब सिग्नलों को फ़िल्टर किया).")
        report_lines.extend([
            f"────────────────────────────",
            f"✅ दैनिक सत्र पूरा हुआ। सभी पोजीशन स्क्वायर-ऑफ कर दी गई हैं.",
            f"🌙 सिस्टम स्लीप मोड में चला गया है (अगला सत्र: कल सुबह 08:45 AM IST)."
        ])
    else:  # English
        status_emoji = "🟢 PROFITABLE" if total_pnl >= 0 else "🔴 CONTROLLED DRAWDOWN"
        report_lines = [
            f"📊 *MANA AI — INSTITUTIONAL EOD REPORT*",
            f"🗓️ *Date*: {today_str} | Session: Phase 1 (Observer)",
            f"🎯 *Strategy*: `{strat_display}`",
            f"────────────────────────────",
            f"💰 *Total Virtual P&L*: *{pnl_formatted}* ({status_emoji})",
            f"📈 *Margin ROI (Deployed Capital)*: *{margin_roi_str}* {roi_indicator}",
            f"💼 *Account ROI (Total Capital)*: *{account_roi_str}* {roi_indicator}",
            f"💵 *Margin Deployed*: `₹{total_deployed:,.2f}`",
            f"🎯 *Total Trades*: `{total_trades}` (Wins: `{wins}` | Losses: `{losses}`)",
            f"📈 *Win Rate*: `{win_rate:.1f}%`",
            f"────────────────────────────",
        ]
        if trades_detail:
            report_lines.append("📋 *Trade Breakdown & Reasons:*")
            for i, t in enumerate(trades_detail, 1):
                contract = t.get("contract", t.get("symbol", "N/A"))
                p = float(t.get("net_pnl", t.get("pnl", 0.0)))
                p_item = f"+₹{p:,.2f}" if p >= 0 else f"-₹{abs(p):,.2f}"
                t_inv = float(t.get("entry_premium", t.get("entry_price", 0.0))) * int(t.get("quantity", t.get("qty", 1)))
                t_roi = (p / t_inv * 100.0) if t_inv > 0 else 0.0
                t_roi_str = f"+{t_roi:.1f}%" if t_roi >= 0 else f"{t_roi:.1f}%"
                t_dot = "🟢" if p >= 0 else "🔴"
                report_lines.append(f"  {i}. `{contract}`: *{p_item}* ({t_roi_str} ROI) {t_dot}\n     👉 Reason: _{t.get('exit_reason', 'Closed')}_")
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
            session_title=f"Phase 1 Paper Session   ·   {strat_display}",
            capital=100000.0,
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

    # Supervisor.stop() terminates (then kills) the child AND closes its
    # stdout handle, which the previous implementation never did.
    observer_sv.stop()
    backend_sv.stop()
    observer_proc = observer_sv.proc
    backend_proc = backend_sv.proc

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

    # Surfaces a stale holiday calendar before anything else happens today.
    assert_holiday_calendar_current(today_date)

    if not force_now and not is_trading_day(today_date):
        logger.info("Today (%s) is a Weekend or NSE Holiday. Skipping session.", today_date)
        return

    # Fresh restart budgets for this trading day (the supervisors are module
    # singletons and outlive a single session in --daemon mode).
    backend_sv.reset()
    observer_sv.reset()

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
            
        # Watchdog: the supervisors decide whether an exit is even worth
        # restarting, and pace any restart behind the backoff ladder. They
        # are safe to call on every tick.
        backend_sv.supervise()

        # Only keep the observer up while it can still open new positions.
        if curr_t < EOD_SQUAREOFF_TIME:
            observer_sv.supervise()

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
                # Same thrash defect as the per-process watchdog, one level up:
                # run_session_flow() returns early on any setup failure (e.g.
                # "Failed to start backend service. Aborting session."), and the
                # daemon used to re-enter it on the very next iteration with no
                # pause -- re-running auto-auth, re-killing ports and re-spawning
                # the backend in a tight loop for the rest of the trading day.
                # Cap it: a handful of attempts per day, spaced out, then stand
                # down until tomorrow rather than hammering the broker's auth
                # endpoint for six hours.
                attempts = _session_attempts.get(today, 0)
                if attempts >= _MAX_SESSION_ATTEMPTS_PER_DAY:
                    logger.error(
                        "Session for %s aborted %d times already. Standing down until tomorrow.",
                        today, attempts,
                    )
                    time.sleep(1800)
                    continue

                if attempts:
                    cool_off = _SESSION_RETRY_COOLDOWN_S
                    logger.warning(
                        "Previous session attempt for %s ended early (attempt %d/%d). "
                        "Cooling off %ds before retrying.",
                        today, attempts, _MAX_SESSION_ATTEMPTS_PER_DAY, cool_off,
                    )
                    if attempts == 1:
                        send_telegram_notification(
                            f"⚠️ [QuantAI] Today's session ended before market close and will be "
                            f"retried in {cool_off // 60} min "
                            f"(attempt {attempts + 1}/{_MAX_SESSION_ATTEMPTS_PER_DAY})."
                        )
                    time.sleep(cool_off)

                _session_attempts[today] = attempts + 1
                logger.info("Trading window active. Launching session for %s", today)
                run_session_flow()
            elif current_time < PRE_MARKET_TIME:
                # IST.localize(), not `tzinfo=IST`. pytz timezone objects carry
                # their pre-1942 LMT offset (+05:53 for Asia/Kolkata) until
                # localize() picks the correct one, so the tzinfo= form
                # produced a datetime 23 minutes off and this sleep was
                # consistently short by that much.
                target_dt = IST.localize(
                    datetime.datetime.combine(today, PRE_MARKET_TIME)
                )
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
