"""The Live/Paper toggle must actually decide what runs (2026-09-16).

The dashboard has had a Live/Paper toggle and an Auto/Manual toggle for a
while, and both persist correctly into settings.json. What was missing was the
other half of the wiring:

* Nothing ever started `trading_bot/main.py`. The orchestrator is a paper-only
  lifecycle, so switching the toggle to LIVE changed the broker object and the
  manual order button, but the autonomous engine -- the only thing that places
  real orders on its own -- was not running at all.
* The dashboard's engine START/STOP button wrote `is_active` into api_bridge's
  in-memory dict, while main.py halts on `settings.get("is_active", True)`
  read from the FILE. Nothing ever wrote that key, so the button was inert and
  the indicator could report "Engine Off" while the engine kept trading.

The owner's rules, which these tests encode:

1. Paper toggle  -> paper trades run automatically.
2. Auto/Manual has NO relation to paper trading; it applies to live only.
3. Live + Auto   -> the bot trades live automatically.
   Live + Manual -> the bot must NOT enter on its own.
"""

from __future__ import annotations

import datetime
import json

import pytest

import auto_daily_session as ads


class FakeSupervisor:
    """Records what the orchestrator asked of it."""

    def __init__(self):
        self.started = 0
        self.supervised = 0
        self.stopped = 0
        self.launches = 0
        # stop_all_subprocesses() copies .proc back into module globals.
        self.proc = None

    def start(self):
        self.started += 1
        self.launches += 1
        return True

    def supervise(self):
        self.supervised += 1

    def stop(self):
        self.stopped += 1

    def reset(self):
        self.launches = 0


@pytest.fixture
def books(monkeypatch):
    """Swap every supervisor for a recorder, and silence Telegram."""
    fakes = {name: FakeSupervisor() for name in
             ("engine_sv", "observer_sv", "variant_sv", "backend_sv")}
    for name, fake in fakes.items():
        monkeypatch.setattr(ads, name, fake)
    monkeypatch.setattr(ads, "send_telegram_notification", lambda _m: None)
    return fakes


# ---------------------------------------------------------------------------
# live_trading_mode() -- fails closed
# ---------------------------------------------------------------------------

def _settings(tmp_path, monkeypatch, payload):
    cfg = tmp_path / "config"
    cfg.mkdir(exist_ok=True)
    (cfg / "settings.json").write_text(json.dumps(payload), encoding="utf-8")
    monkeypatch.setattr(ads, "ROOT_DIR", tmp_path)


def test_live_mode_reads_the_toggle(tmp_path, monkeypatch):
    _settings(tmp_path, monkeypatch, {"live_trading_mode": True})
    assert ads.live_trading_mode() is True


def test_paper_is_the_default(tmp_path, monkeypatch):
    _settings(tmp_path, monkeypatch, {"live_trading_mode": False})
    assert ads.live_trading_mode() is False


def test_a_missing_key_means_paper(tmp_path, monkeypatch):
    _settings(tmp_path, monkeypatch, {"active_strategy": "ema9_rsi_momentum"})
    assert ads.live_trading_mode() is False


def test_a_missing_file_means_paper(tmp_path, monkeypatch):
    monkeypatch.setattr(ads, "ROOT_DIR", tmp_path / "nowhere")
    assert ads.live_trading_mode() is False


def test_corrupt_settings_mean_paper(tmp_path, monkeypatch):
    cfg = tmp_path / "config"
    cfg.mkdir()
    (cfg / "settings.json").write_text("{not json", encoding="utf-8")
    monkeypatch.setattr(ads, "ROOT_DIR", tmp_path)
    assert ads.live_trading_mode() is False, "unreadable settings must never enable live orders"


# ---------------------------------------------------------------------------
# Rule 1 + 3: which book starts
# ---------------------------------------------------------------------------

def test_paper_mode_starts_the_observer_and_not_the_engine(books):
    ads.start_session_books(live=False)
    assert books["observer_sv"].started == 1
    assert books["engine_sv"].started == 0, "paper mode must never start the real-order engine"
    assert books["variant_sv"].started == 1


def test_live_mode_starts_the_engine_and_not_the_observer(books):
    ads.start_session_books(live=True)
    assert books["engine_sv"].started == 1
    assert books["observer_sv"].started == 0, (
        "the observer and the engine both own config/active_positions.json and "
        "both write equity -- they must never run together"
    )
    assert books["variant_sv"].started == 1, "research books run in either mode"


def test_the_two_books_are_never_both_started(books):
    for live in (True, False):
        ads.start_session_books(live=live)
    assert books["engine_sv"].started == 1
    assert books["observer_sv"].started == 1
    # One each across two sessions -- never both within one.


# ---------------------------------------------------------------------------
# The watchdog supervises only the book that was started
# ---------------------------------------------------------------------------

def test_live_supervises_only_the_engine(books):
    ads.supervise_session_books(live=True, curr_t=datetime.time(11, 0))
    assert books["engine_sv"].supervised == 1
    assert books["observer_sv"].supervised == 0


def test_paper_supervises_only_the_observer(books):
    ads.supervise_session_books(live=False, curr_t=datetime.time(11, 0))
    assert books["observer_sv"].supervised == 1
    assert books["engine_sv"].supervised == 0


def test_the_observer_is_left_alone_after_the_squareoff(books):
    """Unchanged behaviour: no restart once it can no longer open positions."""
    after = datetime.time(15, 20)
    assert after >= ads.EOD_SQUAREOFF_TIME
    ads.supervise_session_books(live=False, curr_t=after)
    assert books["observer_sv"].supervised == 0


def test_teardown_stops_the_engine_too(books, monkeypatch):
    # Never let a unit test reach for a real process on port 8000.
    monkeypatch.setattr(ads, "kill_process_on_ports", lambda _ports: None)
    ads.stop_all_subprocesses()
    assert books["engine_sv"].stopped == 1
    assert books["observer_sv"].stopped == 1


# ---------------------------------------------------------------------------
# Rule 3: Auto/Manual gates ENTRIES only, and only in the live engine
# ---------------------------------------------------------------------------

def test_manual_mode_blocks_entries_in_the_live_engine():
    """main.py must skip execution when auto_trade_enabled is off."""
    import pathlib
    src = (pathlib.Path(ads.ROOT_DIR) / "trading_bot" / "main.py").read_text(encoding="utf-8")
    assert 'if not settings.get("auto_trade_enabled", True):' in src
    assert src.count('settings.get("auto_trade_enabled"') == 1, (
        "the flag must gate entries only -- a second site would risk gating exits, "
        "leaving open positions unmanaged in Manual mode"
    )


def test_the_paper_observer_ignores_auto_manual():
    """Rule 2: Auto/Manual has no relation to paper trading."""
    import pathlib
    src = (pathlib.Path(ads.ROOT_DIR) / "paper_observer.py").read_text(encoding="utf-8")
    assert "auto_trade_enabled" not in src
    assert "live_trading_mode" not in src


# ---------------------------------------------------------------------------
# The engine START/STOP button must reach main.py
# ---------------------------------------------------------------------------

@pytest.fixture
def bridge(tmp_path, monkeypatch):
    """api_bridge with a settings.json of its own, in a temp cwd.

    /api/engine/* sits behind api_bridge's HTTP auth middleware (it is not in
    _PUBLIC_PATHS), so the client carries a real session token -- the same way
    test_p3_greeks_and_backtest.py does. Without it every request is a 401 and
    the assertions fail for a reason that has nothing to do with the engine.
    """
    from fastapi.testclient import TestClient

    import api_bridge
    from api_bridge import app
    from shared.security.sessions import create_session, revoke_session

    monkeypatch.chdir(tmp_path)
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "settings.json").write_text(
        json.dumps({"active_strategy": "ema9_rsi_momentum", "live_trading_mode": False}),
        encoding="utf-8",
    )
    # The reader is mtime-cached and module-global; start each test cold.
    monkeypatch.setattr(api_bridge, "_config_cache", {})
    monkeypatch.setattr(api_bridge, "_config_last_mtime", 0.0)

    token = create_session("engine-toggle-test-user")
    client = TestClient(app, client=("127.0.0.1", 50001))
    client.headers.update({"Authorization": f"Bearer {token}"})
    yield api_bridge, client, tmp_path / "config" / "settings.json"
    revoke_session(token)


def _saved(path):
    return json.loads(path.read_text(encoding="utf-8"))


def test_absent_is_active_reads_as_running(bridge):
    """main.py defaults `is_active` to True, so the dashboard must agree.

    Reporting "Engine Off" while main.py happily trades is the exact
    misreport this endpoint used to produce.
    """
    _api, client, path = bridge
    assert "is_active" not in _saved(path)
    assert client.get("/api/engine/status").json()["is_active"] is True


def test_toggle_persists_the_halt_flag_to_disk(bridge):
    _api, client, path = bridge

    body = client.post("/api/engine/toggle").json()

    assert body["is_active"] is False
    assert _saved(path)["is_active"] is False, "main.py reads the FILE, not api_bridge's memory"
    assert client.get("/api/engine/status").json()["is_active"] is False


def test_toggle_round_trips(bridge):
    _api, client, path = bridge

    client.post("/api/engine/toggle")            # -> halted
    body = client.post("/api/engine/toggle").json()   # -> running again

    assert body["is_active"] is True
    assert _saved(path)["is_active"] is True


def test_toggling_preserves_every_other_setting(bridge):
    """A scoped write -- it must not clobber the rest of settings.json."""
    _api, client, path = bridge

    client.post("/api/engine/toggle")

    saved = _saved(path)
    assert saved["active_strategy"] == "ema9_rsi_momentum"
    assert saved["live_trading_mode"] is False


def test_status_follows_a_flag_written_by_someone_else(bridge):
    """The file is the source of truth, not this process's memory."""
    api_bridge, client, path = bridge

    data = _saved(path)
    data["is_active"] = False
    path.write_text(json.dumps(data), encoding="utf-8")
    api_bridge._config_last_mtime = 0.0

    assert client.get("/api/engine/status").json()["is_active"] is False
