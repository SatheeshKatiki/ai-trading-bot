"""Recovering a missed session start (2026-09-17).

The 08:45 scheduled trigger fell while the laptop was in Modern Standby on
battery -- wake timers are disabled on battery -- so the task logged a missed
run and no session started all day: no books, no Telegram. Meanwhile a
main.py started by hand the night before was still running, and would have
shared config/active_positions.json with the next day's paper observer.

Recovery needs extra catch-up triggers, which are only safe if the
orchestrator:

* cannot run twice at once          -> singleton lock in main()
* cannot re-run a finished session  -> session-done marker
* cannot start a book beside a stray -> clear_stray_books(), which refuses
                                       (and alerts) while positions are open
"""

from __future__ import annotations

import datetime
import inspect

import psutil
import pytest

import auto_daily_session as ads


class _Proc:
    def __init__(self, pid, cmdline):
        self.pid = pid
        self.info = {"pid": pid, "cmdline": cmdline}
        self.terminated = False
        self.killed = False

    def terminate(self):
        self.terminated = True

    def kill(self):
        self.killed = True


@pytest.fixture
def root(tmp_path, monkeypatch):
    monkeypatch.setattr(ads, "ROOT_DIR", tmp_path)
    (tmp_path / "config").mkdir()
    return tmp_path


@pytest.fixture
def procs(monkeypatch):
    """A fake process table; wait_procs reports everything as exited."""
    table = []
    monkeypatch.setattr(psutil, "process_iter", lambda attrs=None: list(table))
    monkeypatch.setattr(psutil, "wait_procs", lambda ps, timeout=None: (list(ps), []))
    return table


@pytest.fixture
def telegram(monkeypatch):
    sent = []
    monkeypatch.setattr(ads, "send_telegram_notification", lambda m: sent.append(m))
    return sent


# ---------------------------------------------------------------------------
# Session-done marker
# ---------------------------------------------------------------------------

def test_the_marker_records_a_finished_day(root):
    day = datetime.date(2026, 9, 17)
    assert ads.session_already_ran(day) is False
    ads.mark_session_done(day)
    assert ads.session_already_ran(day) is True
    assert ads.session_already_ran(datetime.date(2026, 9, 18)) is False


def test_a_catch_up_trigger_after_a_finished_session_does_nothing(root, monkeypatch):
    monkeypatch.setattr(ads, "assert_holiday_calendar_current", lambda d: True)
    monkeypatch.setattr(ads, "is_trading_day", lambda d: True)

    def _must_not_start():
        raise AssertionError("a finished day must not start a second session")

    monkeypatch.setattr(ads, "run_auto_auth", _must_not_start)
    ads.mark_session_done(ads.now_ist().date())

    ads.run_session_flow(force_now=False)      # returns quietly


def test_force_now_ignores_the_marker(root, monkeypatch):
    """--now is for testing a full run on demand."""
    monkeypatch.setattr(ads, "assert_holiday_calendar_current", lambda d: True)

    class _Reached(Exception):
        pass

    def _reached():
        raise _Reached

    monkeypatch.setattr(ads, "run_auto_auth", _reached)
    ads.mark_session_done(ads.now_ist().date())

    with pytest.raises(_Reached):
        ads.run_session_flow(force_now=True)


def test_only_a_session_that_reached_its_end_is_marked():
    """An early setup failure must stay retryable."""
    src = inspect.getsource(ads.run_session_flow)
    marked = src.index("mark_session_done(today_date)")
    assert src.index("stop_all_subprocesses()") < marked
    assert src.index('logger.error("Failed to start backend service. Aborting session.")') < marked


# ---------------------------------------------------------------------------
# Stray books
# ---------------------------------------------------------------------------

def test_find_stray_books_matches_only_the_books(procs):
    procs.extend([
        _Proc(1, [r".\venv\Scripts\python.exe", r"trading_bot\main.py"]),
        _Proc(2, ["python", "-u", "D:/x/trading-system/trading_bot/main.py"]),
        _Proc(3, ["python", "-u", r"D:\x\trading-system\paper_observer.py"]),
        _Proc(4, ["python", "-u", "ema9_variant_observer.py", "--variants", "5m_atm"]),
        _Proc(5, ["python", "api_bridge.py"]),
        _Proc(6, ["python", "-m", "pytest", "test_paper_observer_entry_guards.py"]),
        _Proc(7, ["python", "auto_daily_session.py"]),
    ])

    assert sorted(p.pid for p in ads.find_stray_books()) == [1, 2, 3]


def test_no_strays_means_clear(procs, root):
    assert ads.clear_stray_books() is True


def test_a_stray_with_no_positions_is_stopped(procs, root, telegram):
    (root / "config" / "active_positions.json").write_text("{}", encoding="utf-8")
    stray = _Proc(4864, [r".\venv\Scripts\python.exe", r"trading_bot\main.py"])
    procs.append(stray)

    assert ads.clear_stray_books() is True
    assert stray.terminated


def test_a_stray_holding_positions_is_never_stopped(procs, root, telegram):
    """An engine with open positions is managing risk -- refuse and alert."""
    (root / "config" / "active_positions.json").write_text(
        '{"NSE:NIFTY50-INDEX": {"symbol": "NSE:NIFTY2681824400PE"}}', encoding="utf-8")
    stray = _Proc(4864, [r".\venv\Scripts\python.exe", r"trading_bot\main.py"])
    procs.append(stray)

    assert ads.clear_stray_books() is False
    assert not stray.terminated
    assert telegram and "NOT started" in telegram[0]


def test_unreadable_positions_are_treated_as_unsafe(procs, root, telegram):
    (root / "config" / "active_positions.json").write_text("{not json", encoding="utf-8")
    stray = _Proc(4864, ["python", "trading_bot/main.py"])
    procs.append(stray)

    assert ads.clear_stray_books() is False
    assert not stray.terminated


def test_a_refused_clear_starts_no_book_but_the_research_books_still_run(monkeypatch):
    started = []
    monkeypatch.setattr(ads, "clear_stray_books", lambda: False)
    monkeypatch.setattr(ads, "start_paper_observer", lambda: started.append("observer"))
    monkeypatch.setattr(ads, "start_live_engine", lambda: started.append("engine"))
    monkeypatch.setattr(ads, "start_variant_book", lambda: started.append("variants"))

    ads.start_session_books(live=False)
    ads.start_session_books(live=True)

    assert started == ["variants", "variants"]


# ---------------------------------------------------------------------------
# Single instance
# ---------------------------------------------------------------------------

def test_the_manual_launcher_refuses_while_a_session_is_running():
    """Start_AI_Bot.bat force-kills ports 8000/3000 before starting.

    Run while the orchestrator owns the session (2026-09-18) that killed its
    healthy API bridge, every supervised restart was refused by the new
    instance's singleton lock, and the day carried on orphaned on stale code
    -- with main.py adopting the paper observer's open position. The guard
    must come BEFORE the taskkill, or it has already done the damage.
    """
    import pathlib

    # ads.ROOT_DIR is trading-system/; the launcher sits beside it at the root.
    bat = pathlib.Path(ads.ROOT_DIR).resolve().parent / "Start_AI_Bot.bat"
    src = bat.read_text(encoding="utf-8", errors="ignore")

    assert "auto_daily_session.py" in src and "paper_observer.py" in src
    assert "exit /b 1" in src
    assert src.index("auto_daily_session.py") < src.index("taskkill"), \
        "the guard must run before the port cleanup"


def test_both_run_modes_take_the_singleton_lock():
    src = inspect.getsource(ads.main)
    assert src.count("_guard_single_instance()") == 2
    guard = inspect.getsource(ads._guard_single_instance)
    assert 'acquire_singleton_lock("daily_orchestrator", script_hint="auto_daily_session.py")' in guard
