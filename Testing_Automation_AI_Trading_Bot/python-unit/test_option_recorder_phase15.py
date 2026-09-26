"""Phase 15 -- collection-cycle operations tests.

The incident log, the end-of-day close-out and the COMPLETE-session counter.
These exist so a twenty-session cycle cannot quietly lose the record of what
went wrong, and so the session count cannot drift from the QA rules.

RESEARCH INFRASTRUCTURE ONLY.
"""

from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2] / "trading-system"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from research.option_recorder import audit as AU  # noqa: E402
from research.option_recorder import collect as C  # noqa: E402
from research.option_recorder import eod as EOD  # noqa: E402
from research.option_recorder import incidents as INC  # noqa: E402
from research.option_recorder import schema as SC  # noqa: E402
from research.option_recorder.store import ResearchStore  # noqa: E402

IST = C.IST
TODAY = dt.datetime.now(IST).date()


def _weekdays_before(today, n):
    out, d = [], today - dt.timedelta(days=1)
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d)
        d -= dt.timedelta(days=1)
    return list(reversed(out))


_D2, _D1 = _weekdays_before(TODAY, 2)
SESSION = _D1.isoformat()
PREV = _D2.isoformat()


def make_chain(spot=24000.0, *, strikes=21, step=50.0, bid=100.0, ask=100.8,
               ltp=100.4, vix=13.5, synthetic=False):
    atm = round(spot / step) * step
    rows = []
    for k in range(-(strikes // 2), strikes // 2 + 1):
        K = atm + k * step
        leg = lambda t: {"bid": bid, "ask": ask, "ltp": ltp, "oi": 1000,   # noqa: E731
                         "oichg": 5, "volume": 500,
                         "symbol": f"NSE:X{int(K)}{t}"}
        rows.append({"strike": K, "ce": leg("CE"), "pe": leg("PE")})
    return {"underlying_price": spot, "expiry": "2026-10-06",
            "synthetic": synthetic, "priceSource": "test", "chain": rows,
            "indiaVix": {"value": vix, "chp": -1.0} if vix else None}


def make_history(days=4, bars=75, end_date=None):
    rng = np.random.default_rng(3)
    end = end_date or _D1
    daylist, d = [], end
    while len(daylist) < days:
        if d.weekday() < 5:
            daylist.append(d)
        d -= dt.timedelta(days=1)
    idx = []
    for day in sorted(daylist):
        base = pd.Timestamp(day.isoformat() + " 09:15")
        idx.extend(base + pd.Timedelta(minutes=5 * i) for i in range(bars))
    walk = 24000 + np.cumsum(rng.normal(0, 10, len(idx)))
    return pd.DataFrame({"open": walk, "high": walk + 15, "low": walk - 15,
                         "close": walk, "volume": 1000},
                        index=pd.DatetimeIndex(idx))


@pytest.fixture
def store(tmp_path):
    return ResearchStore(tmp_path / "research_data")


def run_session(store, monkeypatch, date, n=76, **kw):
    hist = make_history(end_date=dt.date.fromisoformat(date))
    clock = {"t": dt.datetime.fromisoformat(date + "T09:15:00+05:30")}
    chain = {"c": make_chain(**kw)}
    monkeypatch.setattr(C, "_now", lambda: clock["t"])
    monkeypatch.setattr(C, "fetch_chain", lambda inst: chain["c"])
    monkeypatch.setattr(
        C, "fetch_history",
        lambda *a, **k: hist[hist.index <= pd.Timestamp(
            clock["t"].replace(tzinfo=None))])
    st = C.InstrumentState("NIFTY", date)
    for i in range(n):
        clock["t"] += dt.timedelta(minutes=5)
        chain["c"] = make_chain(bid=100.0 + i, ask=100.8 + i, ltp=100.4 + i, **kw)
        C.snapshot(store, "NIFTY", state=st)
    return st


# =====================================================================
# sec11 -- the incident log
# =====================================================================

class TestIncidentLog:

    def _log(self, store, **kw):
        base = dict(session_date=SESSION, instrument="NIFTY",
                    incident_type="API_OUTAGE", cause="bridge restarted",
                    action="recorder restarted", outcome="INCOMPLETE")
        base.update(kw)
        return INC.log(store, **base)

    def test_entry_round_trips_with_every_required_field(self, store):
        self._log(store, detected_at="11:20", last_valid_snapshot="11:15",
                  affected_data="3 snapshots")
        rows = INC.read(store)
        assert len(rows) == 1
        for f in ("session_date", "instrument", "incident_type", "detected_at",
                  "last_valid_snapshot", "suspected_cause", "affected_data",
                  "recovery_action", "outcome", "recorder_version"):
            assert rows[0][f] != "" or f in ("affected_data",)

    def test_unknown_type_is_rejected(self, store):
        with pytest.raises(ValueError, match="unknown incident type"):
            self._log(store, incident_type="SOMETHING_ELSE")

    def test_unknown_outcome_is_rejected(self, store):
        with pytest.raises(ValueError, match="unknown outcome"):
            self._log(store, outcome="FINE")

    def test_log_is_append_only(self, store):
        self._log(store)
        self._log(store, incident_type="RECORDER_CRASH")
        assert len(INC.read(store)) == 2
        names = [n for n in dir(INC) if not n.startswith("_")]
        assert not [n for n in names
                    if any(v in n for v in ("delete", "update", "edit",
                                            "remove"))]

    def test_entries_are_checksummed(self, store):
        e = self._log(store)
        assert e["_checksum"]
        body = {k: v for k, v in e.items() if k != "_checksum"}
        assert SC.record_checksum(body) == e["_checksum"]

    def test_data_modification_requires_cause_and_action(self, store):
        with pytest.raises(ValueError, match="cause and the action"):
            self._log(store, data_modified=True, cause="", action="")

    def test_filtering_by_session_and_instrument(self, store):
        self._log(store, session_date=SESSION, instrument="NIFTY")
        self._log(store, session_date=PREV, instrument="BANKNIFTY")
        assert len(INC.read(store, session_date=SESSION)) == 1
        assert len(INC.read(store, instrument="BANKNIFTY")) == 1

    def test_summary_counts_by_type_and_outcome(self, store):
        self._log(store)
        self._log(store, incident_type="RESTART_DRILL", outcome="COMPLETE")
        s = INC.summary(store)
        assert s["total"] == 2
        assert s["by_type"]["API_OUTAGE"] == 1
        assert s["restart_drills"]

    def test_not_collected_sessions_are_tracked(self, store):
        self._log(store, incident_type="NOT_COLLECTED", outcome="NOT_COLLECTED",
                  cause="preflight NO-GO", action="none")
        assert INC.summary(store)["sessions_not_collected"] == [SESSION]

    def test_render_survives_an_empty_log(self, store):
        assert "no incidents" in INC.render(INC.read(store))


# =====================================================================
# sec14, sec15 -- audit aggregates and the counter
# =====================================================================

class TestAuditAggregates:

    def test_quote_quality_totals_are_reported(self, store, monkeypatch):
        run_session(store, monkeypatch, SESSION)
        store.write_manifest("NIFTY", SESSION)
        qt = AU.audit(store, target=20)["quote_quality_totals"]
        for f in ("total_observations", "valid", "invalid", "synthetic",
                  "stale", "zero_bid_or_ask", "crossed_quotes",
                  "malformed_rows", "duplicate_observations"):
            assert f in qt
        assert qt["total_observations"] > 0

    def test_vix_availability_is_reported(self, store, monkeypatch):
        run_session(store, monkeypatch, SESSION)
        store.write_manifest("NIFTY", SESSION)
        v = AU.audit(store, target=20)["india_vix_availability"]
        assert v["sessions_with_vix"] == 1 and v["observations"] > 0

    def test_missing_vix_is_visible_in_the_audit(self, store, monkeypatch):
        run_session(store, monkeypatch, SESSION, vix=None)
        store.write_manifest("NIFTY", SESSION)
        v = AU.audit(store, target=20)["india_vix_availability"]
        assert v["sessions_with_vix"] == 0 and v["pct"] == 0.0

    def test_chain_coverage_reports_the_minimum_not_only_the_mean(self, store,
                                                                  monkeypatch):
        """A mean hides the one session that degraded to three strikes."""
        run_session(store, monkeypatch, SESSION)
        run_session(store, monkeypatch, PREV, strikes=3)
        for d in (SESSION, PREV):
            store.write_manifest("NIFTY", d)
        c = AU.audit(store, target=20)["chain_coverage"]
        assert c["min_strikes"] < c["avg_strikes"]

    def test_not_collected_days_count_as_attempted(self, store, monkeypatch):
        run_session(store, monkeypatch, SESSION)
        store.write_manifest("NIFTY", SESSION)
        INC.log(store, session_date=PREV, instrument="ALL",
                incident_type="NOT_COLLECTED", cause="preflight NO-GO",
                action="none", outcome="NOT_COLLECTED")
        a = AU.audit(store, target=20)
        assert a["sessions_with_stored_data"] == 1
        assert a["sessions_not_collected"] == 1
        assert a["calendar_sessions_attempted"] == 2

    def test_restart_drill_status_is_surfaced(self, store, monkeypatch):
        run_session(store, monkeypatch, SESSION)
        store.write_manifest("NIFTY", SESSION)
        assert AU.audit(store, target=20)["incidents"]["restart_drill_performed"] is False
        INC.log(store, session_date=SESSION, instrument="NIFTY",
                incident_type="RESTART_DRILL", cause="planned drill",
                action="restarted, resumed from checkpoint", outcome="COMPLETE")
        assert AU.audit(store, target=20)["incidents"]["restart_drill_performed"] is True

    def test_recorded_data_modification_blocks_a_pass(self, store, monkeypatch):
        """Lineage damage is blocking however healthy the counts look."""
        run_session(store, monkeypatch, SESSION)
        store.write_manifest("NIFTY", SESSION)
        assert AU.audit(store, target=1)["decision"] == "DATA QUALITY PASS"
        INC.log(store, session_date=SESSION, instrument="NIFTY",
                incident_type="OTHER", cause="fixed a bad row by hand",
                action="edited quotes.jsonl", outcome="COMPLETE",
                data_modified=True)
        a = AU.audit(store, target=1)
        assert a["decision"] == "DATA QUALITY CONDITIONAL"
        assert any("modified" in u for u in a["unresolved_data_quality_issues"])

    def test_checkpoint_ladder_starts_at_five(self):
        assert AU.CHECKPOINTS[:3] == (5, 10, 20)

    def test_audit_still_reports_no_strategy_performance(self, store, monkeypatch):
        run_session(store, monkeypatch, SESSION)
        store.write_manifest("NIFTY", SESSION)
        blob = json.dumps(AU.audit(store, target=20)).lower()
        for banned in ("pnl", "win_rate", "sharpe", "profit", "best_strike",
                       "return_pct", "mfe", "mae"):
            assert banned not in blob


# =====================================================================
# sec9, sec15 -- end of day
# =====================================================================

class TestEndOfDay:

    def test_close_writes_manifest_report_and_verifies(self, store, monkeypatch):
        run_session(store, monkeypatch, SESSION)
        res = EOD.close_session(store, SESSION)
        r = res["instruments"][0]
        assert r["integrity_ok"]
        assert r["manifest_files"] > 0
        assert Path(r["report_path"]).exists()
        assert r["checkpoint_present"]

    def test_close_is_rerunnable(self, store, monkeypatch):
        run_session(store, monkeypatch, SESSION)
        a = EOD.close_session(store, SESSION)
        b = EOD.close_session(store, SESSION)
        assert a["instruments"][0]["status"] == b["instruments"][0]["status"]
        assert b["instruments"][0]["integrity_ok"]

    def test_close_exposes_no_manual_override(self):
        """sec9 forbids overriding the classification, so no flag exists."""
        import inspect
        sig = inspect.signature(EOD.close_session)
        assert set(sig.parameters) == {"store", "session_date", "instruments"}
        src = inspect.getsource(EOD)
        for flag in ("--status", "--force-complete", "--override",
                     "--mark-complete"):
            assert flag not in src

    def test_counter_only_counts_complete(self, store, monkeypatch):
        run_session(store, monkeypatch, SESSION, n=76)      # COMPLETE
        run_session(store, monkeypatch, PREV, n=10)         # too sparse
        EOD.close_session(store, SESSION)
        EOD.close_session(store, PREV)
        c = EOD.counter(store)
        assert c["COMPLETE_SESSIONS"] == 1
        assert c["unusable"] == 1

    def test_counter_agrees_with_the_audit(self, store, monkeypatch):
        run_session(store, monkeypatch, SESSION)
        EOD.close_session(store, SESSION)
        assert (EOD.counter(store)["COMPLETE_SESSIONS"]
                == AU.audit(store, target=20)["complete"])

    def test_counter_reports_the_next_rung(self, store, monkeypatch):
        run_session(store, monkeypatch, SESSION)
        EOD.close_session(store, SESSION)
        c = EOD.counter(store)
        assert c["next_checkpoint"] == 5 and c["checkpoints_reached"] == []

    def test_close_on_a_session_with_no_data_is_survivable(self, store):
        res = EOD.close_session(store, SESSION)
        assert res["instruments"] == [] and res["complete_added"] == 0
        assert "no stored data" in EOD.render(res, EOD.counter(store))

    def test_render_states_trading_is_no_go(self, store, monkeypatch):
        run_session(store, monkeypatch, SESSION)
        res = EOD.close_session(store, SESSION)
        assert "NO-GO" in EOD.render(res, EOD.counter(store))

    def test_synthetic_session_adds_nothing(self, store, monkeypatch):
        run_session(store, monkeypatch, SESSION, synthetic=True)
        res = EOD.close_session(store, SESSION)
        assert res["complete_added"] == 0
        assert res["instruments"][0]["status"] == SC.SessionStatus.UNUSABLE.value


# =====================================================================
# sec25 -- production isolation, re-asserted
# =====================================================================

class TestProductionIsolation:

    RECORDER = ROOT / "research" / "option_recorder"

    def test_no_execution_surface(self):
        import ast
        banned = ("place_order", "fyers_broker", "risk.manager", "exit_engine",
                  "active_positions", "order_manager", "paper_observer",
                  "modify_order", "cancel_order")
        for f in self.RECORDER.glob("*.py"):
            tree = ast.parse(f.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, (ast.Module, ast.FunctionDef,
                                     ast.AsyncFunctionDef, ast.ClassDef)):
                    if (node.body and isinstance(node.body[0], ast.Expr)
                            and isinstance(node.body[0].value, ast.Constant)
                            and isinstance(node.body[0].value.value, str)):
                        node.body[0].value.value = ""
            code = ast.unparse(tree)
            for b in banned:
                assert b not in code, f"{f.name} references {b}"

    def test_active_strategy_and_config_unchanged(self):
        cfg = json.loads((ROOT / "config" / "settings.json").read_text(
            encoding="utf-8"))
        assert cfg["active_strategy"] == "ema9_rsi_momentum"
        assert not [k for k in cfg if "rsi_smc" in k]

    def test_no_production_module_imports_the_recorder(self):
        import ast
        for f in list((ROOT / "trading_bot").rglob("*.py")) + \
                 list((ROOT / "brokers").rglob("*.py")):
            try:
                tree = ast.parse(f.read_text(encoding="utf-8"))
            except (SyntaxError, UnicodeDecodeError):
                continue
            for node in ast.walk(tree):
                mod = None
                if isinstance(node, ast.ImportFrom):
                    mod = node.module or ""
                elif isinstance(node, ast.Import):
                    mod = node.names[0].name
                assert not (mod and "option_recorder" in mod), \
                    f"{f} imports the recorder"

    def test_signal_definition_still_frozen(self):
        assert C.BAND_ATR == 0.25 and C.ATR_WINDOW == 14

    def test_finnifty_absent_from_every_default(self):
        for name in ("collect.py", "preflight.py", "audit.py", "eod.py"):
            src = (self.RECORDER / name).read_text(encoding="utf-8")
            if name == "collect.py":
                assert 'default=["NIFTY", "BANKNIFTY", "SENSEX"]' in src
            else:
                assert "FINNIFTY" not in src
