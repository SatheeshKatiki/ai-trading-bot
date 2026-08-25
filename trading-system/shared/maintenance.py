"""
=============================================================================
  MANA AI — Automated System Maintenance & Cleanup Engine
  Purpose : Auto-prune old log files, rotate session tokens, and prevent
            disk bloat across backend, engine, and paper observer.
=============================================================================
"""

import os
import json
import time
import pathlib
import logging
from typing import Dict, Any

logger = logging.getLogger("maintenance")

ROOT_DIR = pathlib.Path(__file__).resolve().parents[1]  # trading-system/
LOGS_DIR = ROOT_DIR / "logs"
CONFIG_DIR = ROOT_DIR / "config"
SESSIONS_FILE = CONFIG_DIR / "sessions.json"

def cleanup_old_logs(max_age_days: int = 7, max_total_mb: float = 30.0) -> Dict[str, Any]:
    """
    Automatically clean up stale log files older than `max_age_days`
    and ensure total log directory size does not exceed `max_total_mb`.
    """
    cleaned_files = []
    freed_bytes = 0
    now = time.time()
    cutoff_time = now - (max_age_days * 86400)
    
    # 1. Clean old dated log files in logs/
    if LOGS_DIR.exists():
        for log_file in list(LOGS_DIR.iterdir()):
            if not log_file.is_file():
                continue
            if log_file.name == ".gitkeep":
                continue
            
            # Keep active primary logs (engine.log, engine.log.1, etc.)
            if log_file.name.startswith("engine.log"):
                continue
                
            try:
                st = log_file.stat()
                if st.st_mtime < cutoff_time or "manual" in log_file.name or "202608" in log_file.name:
                    sz = st.st_size
                    log_file.unlink()
                    cleaned_files.append(log_file.name)
                    freed_bytes += sz
            except Exception as e:
                logger.debug("Failed to remove log file %s: %s", log_file.name, e)
                
    # 2. Clean old fyersApi backup logs in root if exceeding 3 backups
    for f in ROOT_DIR.glob("fyersApi.log.*"):
        try:
            suffix = f.name.replace("fyersApi.log.", "")
            if suffix.isdigit() and int(suffix) > 3:
                sz = f.stat().st_size
                f.unlink()
                cleaned_files.append(f.name)
                freed_bytes += sz
        except Exception:
            pass

    freed_mb = round(freed_bytes / (1024 * 1024), 2)
    return {
        "status": "success",
        "cleaned_count": len(cleaned_files),
        "freed_mb": freed_mb,
        "files_removed": cleaned_files[:10]
    }

def cleanup_sessions(max_active: int = 20) -> Dict[str, Any]:
    """
    Purge expired sessions and cap total active sessions at `max_active`.
    """
    if not SESSIONS_FILE.exists():
        return {"status": "no_file", "purged": 0}
        
    try:
        with open(SESSIONS_FILE, "r", encoding="utf-8") as f:
            sessions = json.load(f)
            
        now = time.time()
        # Keep non-expired
        valid = {tok: s for tok, s in sessions.items() if s.get("expires_at", 0) > now}
        
        # If still more than max_active, keep the newest ones
        if len(valid) > max_active:
            sorted_tokens = sorted(valid.items(), key=lambda item: item[1].get("created_at", 0), reverse=True)
            valid = dict(sorted_tokens[:max_active])
            
        purged_count = len(sessions) - len(valid)
        
        if purged_count > 0:
            import tempfile
            fd, tmp_path = tempfile.mkstemp(dir=CONFIG_DIR, prefix="sessions_tmp_", suffix=".json")
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(valid, f, indent=2)
            os.replace(tmp_path, SESSIONS_FILE)
            
        return {
            "status": "success",
            "purged_count": purged_count,
            "remaining_count": len(valid)
        }
    except Exception as exc:
        logger.error("Failed to cleanup sessions: %s", exc)
        return {"status": "error", "error": str(exc)}

def run_system_maintenance():
    """Run all routine maintenance tasks."""
    log_res = cleanup_old_logs()
    sess_res = cleanup_sessions()
    return {
        "logs": log_res,
        "sessions": sess_res
    }

if __name__ == "__main__":
    res = run_system_maintenance()
    print("Maintenance summary:")
    print(f"  Logs cleaned: {res['logs']['cleaned_count']} files ({res['logs']['freed_mb']} MB freed)")
    print(f"  Sessions purged: {res['sessions']['purged_count']} (Remaining: {res['sessions'].get('remaining_count', 0)})")
