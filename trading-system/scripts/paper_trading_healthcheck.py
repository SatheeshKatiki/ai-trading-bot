"""
Paper-trading validation-window health check (see docs/GO_NO_GO_CHECKLIST.md
Sections 2 and 3). Run on demand during market hours to get a compact status
snapshot instead of manually re-deriving it from raw logs each time.

Usage: venv/Scripts/python.exe scripts/paper_trading_healthcheck.py
"""
from __future__ import annotations

import json
import re
import sqlite3
import sys
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENGINE_LOG = ROOT / "logs" / "engine.log"
FYERS_LOG = ROOT / "fyersApi.log"
STATE_DB = ROOT / "state.db"
POSITIONS_FILE = ROOT / "config" / "active_positions.json"

TODAY = date.today().isoformat()


def _today_lines(path: Path) -> list[str]:
    if not path.exists():
        return []
    out = []
    with path.open("r", encoding="utf-8", errors="replace") as f:
        for line in f:
            if line.startswith(f"[{TODAY}"):
                out.append(line)
    return out


def check_processes() -> dict:
    import subprocess
    try:
        out = subprocess.run(
            ["powershell", "-Command",
             "Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | "
             "Select-Object ProcessId,CommandLine | ConvertTo-Json"],
            capture_output=True, text=True, timeout=15,
        ).stdout
        procs = json.loads(out) if out.strip() else []
        if isinstance(procs, dict):
            procs = [procs]
    except Exception as exc:
        return {"error": str(exc)}

    api_bridge = [p for p in procs if "api_bridge.py" in (p.get("CommandLine") or "")]
    engine = [p for p in procs if "trading_bot.main" in (p.get("CommandLine") or "")]
    return {
        "api_bridge_process_count": len(api_bridge),
        "engine_process_count": len(engine),
        "duplicate_engine_warning": len(engine) > 2,  # shim+child == 2 is normal
        "duplicate_api_bridge_warning": len(api_bridge) > 2,
    }


def check_health_endpoint() -> dict:
    try:
        import urllib.request
        with urllib.request.urlopen("http://127.0.0.1:8000/health", timeout=5) as r:
            return {"reachable": True, "status_code": r.status}
    except Exception as exc:
        return {"reachable": False, "error": str(exc)}


def check_logs() -> dict:
    lines = _today_lines(ENGINE_LOG)
    crashes = [l for l in lines if "Traceback" in l or " CRITICAL " in l]
    save_failures = [l for l in lines if "Failed to save active positions" in l]
    mismatches = [l for l in lines if "STATE MISMATCH" in l or "RECONCILIATION" in l]
    reconnects = [l for l in lines if "Connected to API Bridge WebSocket" in l]
    entries = [l for l in lines if re.search(r"\bENTRY\b", l)]
    return {
        "lines_today": len(lines),
        "crash_lines": len(crashes),
        "save_failure_lines": len(save_failures),
        "reconciliation_lines": len(mismatches),
        "reconnect_events_today": len(reconnects),
        "entry_lines_today": len(entries),
        "sample_crash": crashes[0].strip() if crashes else None,
    }


def check_trades() -> dict:
    if not STATE_DB.exists():
        return {"error": "state.db not found"}
    conn = sqlite3.connect(str(STATE_DB))
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM trades")
    total = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM trades WHERE qty = 0")
    phantom = c.fetchone()[0]
    c.execute("SELECT symbol, side, price, timestamp, qty FROM trades ORDER BY id DESC LIMIT 5")
    recent = c.fetchall()
    c.execute("SELECT equity, pnl, last_update FROM state ORDER BY id DESC LIMIT 1")
    state_row = c.fetchone()
    conn.close()

    # Crude mispricing sanity check: option premium shouldn't be within two
    # orders of magnitude of a plausible index level (see checklist §2.3).
    suspicious = [r for r in recent if r[2] > 3000]

    return {
        "total_trades": total,
        "phantom_zero_qty_trades": phantom,
        "recent_trades": recent,
        "suspicious_premium_trades": suspicious,
        "state": state_row,
    }


def check_positions() -> dict:
    if not POSITIONS_FILE.exists():
        return {"error": "active_positions.json not found"}
    try:
        data = json.loads(POSITIONS_FILE.read_text(encoding="utf-8"))
        return {"open_positions": len(data), "symbols": list(data.keys())}
    except Exception as exc:
        return {"error": str(exc)}


def check_disk() -> dict:
    import shutil
    usage = {}
    for sub in ("logs", "audit", "backups"):
        p = ROOT / sub
        if p.exists():
            total = sum(f.stat().st_size for f in p.rglob("*") if f.is_file())
            usage[sub] = round(total / (1024 * 1024), 1)
    return usage


def main() -> None:
    report = {
        "checked_at": datetime.now().isoformat(timespec="seconds"),
        "processes": check_processes(),
        "health_endpoint": check_health_endpoint(),
        "engine_logs_today": check_logs(),
        "trades": check_trades(),
        "positions": check_positions(),
        "disk_usage_mb": check_disk(),
    }
    print(json.dumps(report, indent=2, default=str))


if __name__ == "__main__":
    main()
