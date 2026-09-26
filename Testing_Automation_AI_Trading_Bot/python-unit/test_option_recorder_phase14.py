"""Phase 14 -- observation-phase infrastructure tests.

Covers the pre-flight gate, India VIX capture, the per-session evidence
report, and the multi-session audit. The theme is the same as Phase 13: every
failure here is one that produces no error and would be discovered only
months later, when the sessions are already spent.

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
from research.option_recorder import preflight as PF  # noqa: E402
from research.option_recorder import schema as SC  # noqa: E402
from research.option_recorder import session_report as SR  # noqa: E402
from research.option_recorder.store import ResearchStore  # noqa: E402

IST = C.IST

#: Sessions must never be dated in the future: the report's time-integrity
#: check correctly rejects a stored event_time later than "now", so fixtures
#: are anchored to the real clock rather than to a hardcoded date.
TODAY = dt.datetime.now(IST).date()


def _weekdays_before(today, n):
    """The n most recent weekdays strictly before `today`, oldest first."""
    out, d = [], today - dt.timedelta(days=1)
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d)
        d -= dt.timedelta(days=1)
    return list(reversed(out))


#: A full 76-snapshot session runs 09:15 -> 15:35. Anchoring fixtures to a
#: COMPLETED weekday keeps every stored event_time in the past regardless of
#: what time of day the suite runs -- otherwise the same test passes in the
#: morning and fails after lunch.
_D2, _D1 = _weekdays_before(TODAY, 2)
SESSION = _D1.isoformat()
PREV = _D2.isoformat()


def make_chain(spot=24000.0, *, strikes=21, step=50.0, expiry="2026-10-06",
               synthetic=False, bid=100.0, ask=100.8, ltp=100.4, vix=13.5):
    atm = round(spot / step) * step
    rows = []
    for k in range(-(strikes // 2), strikes // 2 + 1):
        K = atm + k * step
        leg = lambda t: {"bid": bid, "ask": ask, "ltp": ltp, "oi": 1000,   # noqa: E731
                         "oichg": 5, "volume": 500,
                         "symbol": f"NSE:X{int(K)}{t}"}
        rows.append({"strike": K, "ce": leg("CE"), "pe": leg("PE")})
    out = {"underlying_price": spot, "expiry": expiry, "synthetic": synthetic,
           "priceSource": "test", "chain": rows}
    if vix is not None:
        out["indiaVix"] = {"value": vix, "chp": -1.1, "src": "broker",
                           "ts": 1.0}
    else:
        out["indiaVix"] = None
    return out


def make_history(days=4, bars=75, start=24000.0, end_date=None):
    """Bars on the `days` weekdays ending at `end_date` (default: SESSION)."""
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
    walk = start + np.cumsum(rng.normal(0, 10, len(idx)))
    return pd.DataFrame({"open": walk, "high": walk + 15, "low": walk - 15,
                         "close": walk, "volume": 1000},
                        index=pd.DatetimeIndex(idx))


@pytest.fixture
def store(tmp_path):
    return ResearchStore(tmp_path / "research_data")


@pytest.fixture
def wired(monkeypatch):
    hist = make_history()
    clock = {"t": dt.datetime.combine(_D1, dt.time(9, 15), tzinfo=IST)}
    chain = {"c": make_chain()}

    def history_as_of(*a, **k):
        return hist[hist.index <= pd.Timestamp(clock["t"].replace(tzinfo=None))]

    monkeypatch.setattr(C, "fetch_history", history_as_of)
    monkeypatch.setattr(C, "fetch_chain", lambda inst: chain["c"])
    monkeypatch.setattr(C, "_now", lambda: clock["t"])

    def tick(minutes=5.0):
        clock["t"] = clock["t"] + dt.timedelta(minutes=minutes)

    return {"clock": clock, "tick": tick, "chain": chain}


def run_session(store, wired, n=76, **chain_kw):
    st = C.InstrumentState("NIFTY", SESSION)
    for i in range(n):
        wired["tick"]()
        wired["chain"]["c"] = make_chain(bid=100.0 + i, ask=100.8 + i,
                                         ltp=100.4 + i, **chain_kw)
        C.snapshot(store, "NIFTY", state=st)
    store.write_manifest("NIFTY", SESSION)
    return st


# =====================================================================
# sec1 -- the pre-flight must actually check, not merely report
# =====================================================================

class TestPreflight:

    def test_synthetic_chain_is_a_hard_no_go(self, store, wired):
        wired["chain"]["c"] = make_chain(synthetic=True)
        res = PF.run(store, ["NIFTY"], now=dt.datetime.now(IST))
        assert not res["go"]
        assert any("synthetic" in c["name"].lower() or "REAL" in c["name"]
                   for c in res["failed_critical"])

    def test_real_chain_passes(self, store, wired):
        res = PF.run(store, ["NIFTY"], now=dt.datetime.now(IST))
        assert res["go"], res["failed_critical"]

    def test_unreachable_bridge_is_a_no_go(self, store, wired, monkeypatch):
        monkeypatch.setattr(C, "fetch_chain", lambda inst: None)
        res = PF.run(store, ["NIFTY"], now=dt.datetime.now(IST))
        assert not res["go"]

    def test_wrong_timezone_is_a_no_go(self, store, wired):
        utc_now = dt.datetime.now(IST).astimezone(dt.timezone.utc)
        res = PF.run(store, ["NIFTY"], now=utc_now)
        assert not res["go"]
        assert any("IST" in c["name"] for c in res["failed_critical"])

    def test_future_history_bar_is_a_no_go(self, store, wired, monkeypatch):
        future = make_history()
        future.index = future.index + pd.Timedelta(days=60)
        monkeypatch.setattr(C, "fetch_history", lambda *a, **k: future)
        res = PF.run(store, ["NIFTY"], now=dt.datetime.now(IST))
        assert not res["go"]
        assert any("future" in c["name"] for c in res["failed_critical"])

    def test_weekend_and_closed_market_are_advisory_not_blocking(self, store, wired):
        """The operator runs pre-flight before the open; a closed market must
        not read as a broken feed."""
        sunday = dt.datetime(2026, 9, 27, 8, 0, tzinfo=IST)
        res = PF.run(store, ["NIFTY"], now=sunday)
        names = [c["name"] for c in res["advisories"]]
        assert "it is a weekday" in names
        assert all(c["critical"] is False for c in res["advisories"])

    def test_preflight_writes_nothing(self, store, wired, tmp_path):
        before = {p for p in tmp_path.rglob("*") if p.is_file()}
        PF.run(store, ["NIFTY"], now=dt.datetime.now(IST))
        assert {p for p in tmp_path.rglob("*") if p.is_file()} == before

    def test_thin_chain_is_advisory_not_blocking(self, store, wired):
        wired["chain"]["c"] = make_chain(strikes=3)
        res = PF.run(store, ["NIFTY"], now=dt.datetime.now(IST))
        assert res["go"], "a degraded chain is still real data worth recording"
        assert any("coverage" in c["name"] for c in res["advisories"])


# =====================================================================
# sec3 -- India VIX
# =====================================================================

class TestIndiaVix:

    def test_vix_is_extracted_when_present(self):
        assert C.extract_vix(make_chain(vix=14.2)) == (14.2, -1.1)

    def test_absent_vix_stays_absent(self):
        """Never carried forward and never modelled: a stale volatility
        reading silently rewrites the regime a later study reports."""
        assert C.extract_vix(make_chain(vix=None)) == (None, None)
        assert C.extract_vix({}) == (None, None)

    @pytest.mark.parametrize("bad", [0, -1, "x", None])
    def test_unusable_vix_values_are_dropped_not_coerced(self, bad):
        assert C.extract_vix({"indiaVix": {"value": bad}}) == (None, None)

    def test_vix_is_persisted_on_the_underlying_snapshot(self, store, wired):
        wired["tick"]()
        C.snapshot(store, "NIFTY", state=C.InstrumentState("NIFTY", SESSION))
        rows = list(store.read("derived", "NIFTY", SESSION,
                               "underlying.jsonl"))
        assert rows and rows[0]["india_vix"] == 13.5
        assert rows[0]["india_vix_change_pct"] == -1.1

    def test_missing_vix_persists_as_null_not_zero(self, store, wired):
        wired["chain"]["c"] = make_chain(vix=None)
        wired["tick"]()
        C.snapshot(store, "NIFTY", state=C.InstrumentState("NIFTY", SESSION))
        rows = list(store.read("derived", "NIFTY", SESSION,
                               "underlying.jsonl"))
        assert rows and rows[0]["india_vix"] is None

    def test_vix_is_declared_observed(self):
        assert SC.FIELD_PROVENANCE["india_vix"] is SC.Provenance.OBSERVED


# =====================================================================
# sec7 -- the session report
# =====================================================================

class TestSessionReport:

    def test_report_has_every_required_section(self, store, wired):
        run_session(store, wired, 20)
        rep = SR.build(store, "NIFTY", SESSION)
        for section in ("session_metadata", "data_quality", "persistence",
                        "time_integrity", "session_status"):
            assert section in rep

    def test_metadata_carries_versions_and_window(self, store, wired):
        run_session(store, wired, 10)
        m = SR.build(store, "NIFTY", SESSION)["session_metadata"]
        assert m["recorder_version"] == [SC.RECORDER_VERSION]
        assert m["schema_version"] == [SC.SCHEMA_VERSION]
        assert m["start_time"] and m["end_time"]
        assert m["start_time"] < m["end_time"]

    def test_persistence_counters_come_from_the_checkpoint(self, store, wired,
                                                           monkeypatch):
        """Outages leave no trace in the data; a file-only report would show a
        clean session."""
        st = C.InstrumentState("NIFTY", SESSION)
        wired["tick"]()
        C.snapshot(store, "NIFTY", state=st)
        monkeypatch.setattr(C, "fetch_chain", lambda inst: None)
        wired["tick"]()
        C.snapshot(store, "NIFTY", state=st)
        monkeypatch.setattr(C, "fetch_chain", lambda inst: wired["chain"]["c"])
        wired["tick"]()
        C.snapshot(store, "NIFTY", state=st)
        p = SR.build(store, "NIFTY", SESSION)["persistence"]
        assert p["fetch_failures"] == 1
        assert p["reconnects"] == 1
        assert p["checkpoint_present"]

    def test_defect_kinds_are_counted_separately(self, store, wired):
        wired["chain"]["c"] = make_chain(bid=0.0, ask=0.0)
        wired["tick"]()
        C.snapshot(store, "NIFTY", state=C.InstrumentState("NIFTY", SESSION))
        store.write_manifest("NIFTY", SESSION)
        q = SR.build(store, "NIFTY", SESSION)["data_quality"]
        assert q["zero_bid_or_ask"] > 0 and q["crossed_quotes"] == 0

    def test_crossed_quotes_are_counted(self, store, wired):
        wired["chain"]["c"] = make_chain(bid=120.0, ask=100.0)
        wired["tick"]()
        C.snapshot(store, "NIFTY", state=C.InstrumentState("NIFTY", SESSION))
        q = SR.build(store, "NIFTY", SESSION)["data_quality"]
        assert q["crossed_quotes"] > 0

    def test_time_integrity_is_recomputed_from_stored_data(self, store, wired):
        run_session(store, wired, 20)
        t = SR.build(store, "NIFTY", SESSION)["time_integrity"]
        assert t["ok"] and t["timezone_ok"]
        assert t["future_timestamp_violations"] == 0
        assert t["availability_violations"] == 0

    def test_lookahead_row_forces_unusable(self, store, wired):
        """A guarantee only ever asserted by the writer is not a guarantee."""
        run_session(store, wired, 76)
        f = store.partition("derived", "NIFTY", SESSION) / "underlying.jsonl"
        with f.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps({
                "event_time": "2026-09-30T15:00:00+05:30",
                "available_at": "2026-09-30T09:20:00+05:30",   # before event
                "session_date": SESSION, "underlying": "NIFTY",
            }) + chr(10))
        rep = SR.build(store, "NIFTY", SESSION)
        assert rep["time_integrity"]["availability_violations"] == 1
        assert rep["session_status"] == SC.SessionStatus.UNUSABLE.value
        assert any("look-ahead" in b for b in rep["blockers"])

    def test_setup_ids_are_reported_and_deduplicated(self, store, wired):
        run_session(store, wired, 76)
        p = SR.build(store, "NIFTY", SESSION)["persistence"]
        assert p["distinct_setups"] <= p["setup_event_rows"]
        for sid in p["setup_ids"]:
            assert sid.count(":") == 2 and sid.split(":")[-1] in ("LONG", "SHORT")

    def test_report_can_be_persisted_and_reread(self, store, wired):
        run_session(store, wired, 10)
        path = SR.write(store, "NIFTY", SESSION)
        assert path.exists()
        assert json.loads(path.read_text(encoding="utf-8"))["session_status"]

    def test_render_does_not_throw_on_an_empty_session(self, store):
        rep = SR.build(store, "NIFTY", SESSION)
        assert rep["session_status"] == SC.SessionStatus.EMPTY.value
        assert "SESSION REPORT" in SR.render(rep)


# =====================================================================
# sec14 -- the multi-session audit
# =====================================================================

class TestAudit:

    def _session(self, store, monkeypatch, date, n=76, **kw):
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
            chain["c"] = make_chain(bid=100.0 + i, ask=100.8 + i,
                                    ltp=100.4 + i, **kw)
            C.snapshot(store, "NIFTY", state=st)
        store.write_manifest("NIFTY", date)

    def test_only_complete_sessions_count(self, store, monkeypatch):
        self._session(store, monkeypatch, SESSION, n=76)
        self._session(store, monkeypatch, PREV, n=10)     # too sparse
        a = AU.audit(store, target=20)
        assert a["complete"] == 1
        assert a["unusable"] == 1
        assert a["calendar_sessions_attempted"] == 2

    def test_decision_is_in_progress_below_target(self, store, monkeypatch):
        self._session(store, monkeypatch, SESSION)
        assert AU.audit(store, target=20)["decision"] == "IN PROGRESS"

    def test_target_met_with_no_issues_passes(self, store, monkeypatch):
        self._session(store, monkeypatch, SESSION)
        assert AU.audit(store, target=1)["decision"] == "DATA QUALITY PASS"

    def test_target_met_with_issues_is_conditional(self, store, monkeypatch):
        self._session(store, monkeypatch, SESSION)
        self._session(store, monkeypatch, PREV, n=10)
        a = AU.audit(store, target=1)
        assert a["decision"] == "DATA QUALITY CONDITIONAL"
        assert a["unresolved_data_quality_issues"]

    def test_unresolved_issues_name_the_session_and_reason(self, store, monkeypatch):
        self._session(store, monkeypatch, PREV, n=10)
        issues = AU.audit(store, target=20)["unresolved_data_quality_issues"]
        assert issues and PREV in issues[0] and "NIFTY" in issues[0]

    def test_audit_reports_storage_footprint(self, store, monkeypatch):
        self._session(store, monkeypatch, SESSION)
        s = AU.audit(store, target=20)["storage"]
        assert s["total_bytes"] > 0
        assert set(s["layers"]) >= {"raw", "normalized"}

    def test_next_checkpoint_is_the_next_rung(self, store, monkeypatch):
        self._session(store, monkeypatch, SESSION)
        assert AU.audit(store, target=20)["next_checkpoint"] == 20

    def test_audit_never_reports_strategy_performance(self, store, monkeypatch):
        self._session(store, monkeypatch, SESSION)
        blob = json.dumps(AU.audit(store, target=20)).lower()
        for banned in ("pnl", "p&l", "win_rate", "winrate", "sharpe",
                       "profit", "return_pct", "best_strike"):
            assert banned not in blob, f"audit leaked {banned}"

    def test_render_is_explicit_that_trading_stays_no_go(self, store, monkeypatch):
        self._session(store, monkeypatch, SESSION)
        assert "NO-GO" in AU.render(AU.audit(store, target=1))


# =====================================================================
# sec20 -- the recorder is still not a trading engine
# =====================================================================

class TestObservationOnlySafety:

    RECORDER = ROOT / "research" / "option_recorder"

    def test_no_execution_surface_in_any_module(self):
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

    def test_recorder_imports_no_trading_bot_execution_package(self):
        import ast
        allowed_prefixes = ("shared.indicators",
                            "trading_bot.strategies.rsi_smc_options_buyer")
        for f in self.RECORDER.glob("*.py"):
            tree = ast.parse(f.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                mod = None
                if isinstance(node, ast.ImportFrom):
                    mod = node.module or ""
                elif isinstance(node, ast.Import):
                    mod = node.names[0].name
                if mod and mod.startswith(("trading_bot", "brokers", "shared")):
                    assert mod.startswith(allowed_prefixes), \
                        f"{f.name} imports {mod}"

    def test_signal_definition_is_still_frozen(self):
        assert C.BAND_ATR == 0.25 and C.ATR_WINDOW == 14

    def test_finnifty_is_not_a_collector_default(self):
        src = (self.RECORDER / "collect.py").read_text(encoding="utf-8")
        assert 'default=["NIFTY", "BANKNIFTY", "SENSEX"]' in src

    def test_finnifty_is_not_a_preflight_default(self):
        assert "FINNIFTY" not in str(PF.run.__defaults__)
        src = (self.RECORDER / "preflight.py").read_text(encoding="utf-8")
        assert "FINNIFTY" not in src

    def test_production_config_is_untouched(self):
        cfg = json.loads((ROOT / "config" / "settings.json").read_text(
            encoding="utf-8"))
        assert cfg["active_strategy"] == "ema9_rsi_momentum"
        assert not [k for k in cfg if "rsi_smc" in k]
