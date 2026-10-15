"""Service console logs stay bounded and readable (2026-10-15: api_bridge_stdout.log
had reached 373 MB, with no timestamps, mostly one line per dashboard poll)."""
from __future__ import annotations

import re
import socket
import subprocess
import sys
import textwrap
import time
import urllib.error
import urllib.request
from pathlib import Path

from auto_daily_session import rotate_stdout_log

_ROOT = Path(__file__).resolve().parents[1]


# ── rotation at launch ──────────────────────────────────────────────────────

def _write_lines(path: Path, n: int) -> None:
    path.write_bytes(b"".join(b"line %07d\n" % i for i in range(n)))


def test_a_log_over_the_cap_keeps_only_its_newest_part(tmp_path):
    log = tmp_path / "api_bridge_stdout.log"
    _write_lines(log, 20000)                       # 260 KB
    assert rotate_stdout_log(log, max_bytes=100_000, keep_bytes=10_000) is True

    assert log.stat().st_size == 0
    kept = (tmp_path / "api_bridge_stdout.log.1").read_bytes()
    assert len(kept) <= 10_000
    assert kept.endswith(b"line 0019999\n")
    assert kept.startswith(b"line ")               # cut at a line start


def test_a_log_under_the_cap_is_left_alone(tmp_path):
    log = tmp_path / "x_stdout.log"
    _write_lines(log, 100)
    before = log.read_bytes()
    assert rotate_stdout_log(log, max_bytes=100_000, keep_bytes=10_000) is False
    assert log.read_bytes() == before
    assert not (tmp_path / "x_stdout.log.1").exists()


def test_a_missing_log_is_not_an_error(tmp_path):
    assert rotate_stdout_log(tmp_path / "never_written.log") is False


def test_rotation_replaces_the_previous_backup(tmp_path):
    log = tmp_path / "x_stdout.log"
    backup = tmp_path / "x_stdout.log.1"
    backup.write_bytes(b"old backup\n")
    _write_lines(log, 20000)
    rotate_stdout_log(log, max_bytes=100_000, keep_bytes=10_000)
    assert b"old backup" not in backup.read_bytes()


def test_rotation_works_while_another_handle_has_the_log_open(tmp_path):
    """A stray child may still hold its console log; a rename would fail on Windows."""
    log = tmp_path / "x_stdout.log"
    _write_lines(log, 20000)
    with open(log, "a", encoding="utf-8"):
        assert rotate_stdout_log(log, max_bytes=100_000, keep_bytes=10_000) is True
    assert log.stat().st_size == 0


# ── the bridge's uvicorn logging ────────────────────────────────────────────

def test_bridge_log_lines_are_timestamped_and_polling_is_quiet():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    server = textwrap.dedent(f"""
        import sys
        sys.path.insert(0, {str(_ROOT)!r})
        import uvicorn
        from fastapi import FastAPI, HTTPException
        from shared.bridge_logging import uvicorn_log_config

        app = FastAPI()

        @app.get("/api/state")
        def state():
            return {{"ok": True}}

        @app.get("/api/quote")
        def quote():
            raise HTTPException(status_code=500)

        @app.get("/api/journal")
        def journal():
            return {{"ok": True}}

        uvicorn.run(app, host="127.0.0.1", port={port}, log_config=uvicorn_log_config())
    """)
    proc = subprocess.Popen([sys.executable, "-c", server], stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, text=True)
    try:
        deadline = time.monotonic() + 20
        while True:
            try:
                urllib.request.urlopen(f"http://127.0.0.1:{port}/api/journal", timeout=1).read()
                break
            except (urllib.error.URLError, ConnectionError):
                if time.monotonic() > deadline:
                    raise
                time.sleep(0.2)
        for path in ("/api/state?symbol=NIFTY", "/api/state", "/api/quote?symbol=NIFTY"):
            try:
                urllib.request.urlopen(f"http://127.0.0.1:{port}{path}", timeout=5).read()
            except urllib.error.HTTPError:
                pass
        time.sleep(0.5)
    finally:
        proc.terminate()
        out, _ = proc.communicate(timeout=10)

    lines = [line for line in out.splitlines() if line.strip()]
    stamp = re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} ")
    server_lines = [line for line in lines if "INFO" in line or "ERROR" in line or "WARNING" in line]
    assert server_lines and all(stamp.match(line) for line in server_lines), server_lines
    assert not any('"GET /api/state' in line for line in lines)              # successful poll: quiet
    assert any('"GET /api/quote?symbol=NIFTY' in line and " 500" in line for line in lines)  # error: kept
    assert any('"GET /api/journal' in line for line in lines)                # not a polled path: kept


# ── session-start Telegram ──────────────────────────────────────────────────

from auto_daily_session import _format_inr, paper_session_message


def test_the_engine_message_lists_what_paper_actually_trades():
    """2026-10-14 said "NIFTY & BANKNIFTY"; the engine traded NIFTY only."""
    msg = paper_session_message({"active_strategy": "ema9_fibo_smc_momentum",
                                 "symbols": ["NSE:NIFTY50-INDEX"]})
    assert "• Assets: NIFTY, BANKNIFTY & SENSEX Options" in msg
    assert "EMA 9 + Fibonacci OTE + SMC Momentum" in msg
    assert "• Capital: ₹1,00,000 (Virtual)" in msg


def test_the_engine_message_follows_the_paper_override_and_capital():
    msg = paper_session_message({"paper_test_instruments": ["NIFTY"], "initial_capital": 250000})
    assert "• Assets: NIFTY Options" in msg
    assert "• Capital: ₹2,50,000 (Virtual)" in msg


def test_the_observer_message_lists_its_indices():
    msg = paper_session_message({"active_strategy": "ema9_rsi_momentum"}, book="observer")
    assert "Paper Trading Observer" in msg
    assert "• Assets: NIFTY, BANKNIFTY & SENSEX Options" in msg
    assert "EMA 9 / RSI Momentum" in msg


def test_indian_digit_grouping():
    assert [_format_inr(v) for v in (950, 100000, 1250000, 12345678)] == \
        ["950", "1,00,000", "12,50,000", "1,23,45,678"]
