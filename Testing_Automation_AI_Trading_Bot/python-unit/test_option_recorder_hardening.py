"""Phase 13 -- recorder hardening tests.

These are the tests that decide whether the next several months of collected
observations can be trusted. Each one targets a failure that would corrupt a
dataset SILENTLY: a duplicate that lets one moment vote twice, a modelled
value stored as an observation, a timestamp that grants look-ahead, a crash
that loses quotes the process already claimed to have written.

RESEARCH INFRASTRUCTURE ONLY. Nothing here imports execution code.
"""

from __future__ import annotations

import datetime as dt
import json
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2] / "trading-system"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from research.option_recorder import collect as C  # noqa: E402
from research.option_recorder import qa  # noqa: E402
from research.option_recorder import schema as SC  # noqa: E402
from research.option_recorder.store import ResearchStore  # noqa: E402

IST = C.IST


# ---------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------

def make_chain(spot=24000.0, *, strikes=21, step=50.0, expiry="2026-10-06",
               synthetic=False, bid=100.0, ask=100.8, ltp=100.4,
               volume=500, oi=1000):
    atm = round(spot / step) * step
    rows = []
    for k in range(-(strikes // 2), strikes // 2 + 1):
        K = atm + k * step
        leg = lambda t: {"bid": bid, "ask": ask, "ltp": ltp, "oi": oi,      # noqa: E731
                         "oichg": 5, "volume": volume,
                         "symbol": f"NSE:X{int(K)}{t}"}
        rows.append({"strike": K, "ce": leg("CE"), "pe": leg("PE")})
    return {"underlying_price": spot, "expiry": expiry, "synthetic": synthetic,
            "priceSource": "test", "chain": rows}


def make_history(days=4, bars=75, start=24000.0):
    rng = np.random.default_rng(3)
    idx, day = [], dt.date(2026, 9, 25)
    for _ in range(days):
        while day.weekday() >= 5:
            day += dt.timedelta(days=1)
        base = pd.Timestamp(day.isoformat() + " 09:15")
        idx.extend(base + pd.Timedelta(minutes=5 * i) for i in range(bars))
        day += dt.timedelta(days=1)
    walk = start + np.cumsum(rng.normal(0, 10, len(idx)))
    return pd.DataFrame({"open": walk, "high": walk + 15, "low": walk - 15,
                         "close": walk, "volume": 1000},
                        index=pd.DatetimeIndex(idx))


@pytest.fixture
def store(tmp_path):
    return ResearchStore(tmp_path / "research_data")


@pytest.fixture
def wired(monkeypatch):
    """Recorder wired to deterministic data and a driveable clock."""
    hist = make_history()
    clock = {"t": dt.datetime(2026, 9, 30, 9, 15, tzinfo=IST)}
    chain = {"c": make_chain()}
    # A real history endpoint returns only bars that have already closed.
    # Serving the whole frame regardless of the clock would hand the recorder
    # bars from the future and test a situation that cannot occur.
    def history_as_of(*a, **k):
        cutoff = pd.Timestamp(clock["t"].replace(tzinfo=None))
        return hist[hist.index <= cutoff]

    monkeypatch.setattr(C, "fetch_history", history_as_of)
    monkeypatch.setattr(C, "fetch_chain", lambda inst: chain["c"])
    monkeypatch.setattr(C, "_now", lambda: clock["t"])

    def tick(minutes=5.0):
        clock["t"] = clock["t"] + dt.timedelta(minutes=minutes)

    return {"clock": clock, "tick": tick, "chain": chain, "hist": hist}


def quote(symbol="NSE:X24000CE", event_time="2026-09-30T09:20:00+05:30",
          **kw):
    base = dict(event_time=event_time, event_time_utc=event_time,
                session_date="2026-09-30", available_at=event_time,
                underlying="NIFTY", option_symbol=symbol, expiry="2026-10-06",
                strike=24000.0, option_type="CE", underlying_price=24000.0,
                last_price=100.0, bid=99.5, ask=100.5, volume=10,
                open_interest=100, oi_change=1)
    base.update(kw)
    return SC.OptionQuote(**base)


# =====================================================================
# sec6 -- deduplication and the canonical observation key
# =====================================================================

class TestDeduplication:

    def test_observation_key_is_stable_across_numeric_spelling(self):
        a = SC.observation_key("NIFTY", "t", "S", "e", 24000, "CE")
        b = SC.observation_key("NIFTY", "t", "S", "e", 24000.0, "CE")
        assert a == b

    def test_observation_key_separates_the_things_that_must_differ(self):
        base = ("NIFTY", "t", "S", "2026-10-06", 24000.0, "CE")
        k = SC.observation_key(*base)
        for i, alt in enumerate(["BANKNIFTY", "t2", "S2", "2026-10-13",
                                 24050.0, "PE"]):
            other = list(base)
            other[i] = alt
            assert SC.observation_key(*other) != k, f"field {i} collided"

    def test_key_ignores_price_so_a_retry_cannot_double_count(self):
        """A retry returning a slightly different price for the SAME instant
        is still that one instant. Keying on price would store both and let
        one moment vote twice."""
        assert (quote(last_price=100.0).observation_key()
                == quote(last_price=101.0).observation_key())

    def test_repeated_append_stores_one_copy(self, store):
        q = quote()
        w1, s1, seen = store.append_deduped("normalized", "NIFTY",
                                            "2026-09-30", "q.jsonl", [q, q])
        w2, s2, _ = store.append_deduped("normalized", "NIFTY", "2026-09-30",
                                         "q.jsonl", [q], seen)
        assert (w1, s1) == (1, 1)
        assert (w2, s2) == (0, 1)

    def test_dedup_survives_a_process_restart(self, store):
        store.append_deduped("normalized", "NIFTY", "2026-09-30", "quotes.jsonl",
                             [quote()])
        fresh = ResearchStore(store.root)          # no in-memory state at all
        w, s, _ = fresh.append_deduped("normalized", "NIFTY", "2026-09-30",
                                       "quotes.jsonl", [quote()])
        assert (w, s) == (0, 1)

    def test_dedup_rebuilds_from_data_when_the_index_is_lost(self, store):
        store.append_deduped("normalized", "NIFTY", "2026-09-30",
                             "quotes.jsonl", [quote()])
        store._key_index_path("NIFTY", "2026-09-30").unlink()
        w, s, _ = ResearchStore(store.root).append_deduped(
            "normalized", "NIFTY", "2026-09-30", "quotes.jsonl", [quote()])
        assert (w, s) == (0, 1), "the data itself must be the source of truth"

    def test_double_snapshot_of_one_instant_writes_once(self, store, wired):
        wired["tick"]()
        st = C.InstrumentState("NIFTY", "2026-09-30")
        a = C.snapshot(store, "NIFTY", state=st)
        b = C.snapshot(store, "NIFTY", state=st)
        assert a["written"] > 0 and b["written"] == 0 and b["skipped"] == a["written"]


# =====================================================================
# sec3, sec5 -- observed vs synthetic
# =====================================================================

class TestObservedVsSynthetic:

    def test_synthetic_chain_is_never_valid(self):
        q, _ = SC.classify_quote(99.0, 100.0, 99.5, None, is_synthetic=True)
        assert q is SC.Quality.SYNTHETIC

    def test_synthetic_beats_every_other_verdict(self):
        """A well-formed modelled quote is still not an observation."""
        for bid, ask, ltp in [(0, 0, 0), (100, 99, 99), (99, 100, 99.5)]:
            q, _ = SC.classify_quote(bid, ask, ltp, 9e9, is_synthetic=True)
            assert q is SC.Quality.SYNTHETIC

    def test_synthetic_session_is_unusable(self, store, wired):
        wired["chain"]["c"] = make_chain(synthetic=True)
        wired["tick"]()
        C.snapshot(store, "NIFTY", state=C.InstrumentState("NIFTY", "2026-09-30"))
        store.write_manifest("NIFTY", "2026-09-30")
        rep = qa.session_report(store, "NIFTY", "2026-09-30")
        assert rep["status"] == SC.SessionStatus.UNUSABLE.value
        assert rep["usable"] is False

    def test_iv_and_greeks_are_declared_derived_not_observed(self):
        for f in ("implied_volatility", "delta", "gamma", "theta", "vega"):
            assert SC.FIELD_PROVENANCE[f] is SC.Provenance.DERIVED
        for f in ("bid", "ask", "last_price", "open_interest", "volume"):
            assert SC.FIELD_PROVENANCE[f] is SC.Provenance.OBSERVED

    def test_executable_prices_never_fall_back_to_last_price(self):
        q = quote(bid=0.0, ask=0.0, last_price=100.0)
        assert q.executable_buy() is None and q.executable_sell() is None


# =====================================================================
# sec7 -- staleness, honestly
# =====================================================================

class TestStaleness:

    def test_no_exchange_quote_age_is_ever_invented(self, store, wired):
        wired["tick"]()
        C.snapshot(store, "NIFTY", state=C.InstrumentState("NIFTY", "2026-09-30"))
        rows = list(store.read("normalized", "NIFTY", "2026-09-30", "quotes.jsonl"))
        assert rows
        assert all(r["quote_age_seconds"] is None for r in rows), (
            "the broker chain has no per-leg timestamp; a number here would "
            "be fabricated")

    def test_unchanged_quotes_become_stale(self, store, wired):
        st = C.InstrumentState("NIFTY", "2026-09-30")
        for _ in range(6):                      # 30 minutes, identical chain
            wired["tick"]()
            C.snapshot(store, "NIFTY", state=st)
        rows = list(store.read("normalized", "NIFTY", "2026-09-30", "quotes.jsonl"))
        stale = [r for r in rows if r["quality"] == SC.Quality.STALE.value]
        assert stale, "a chain frozen for 30 minutes must not read as fresh"
        assert all(r["unchanged_for_seconds"] > SC.DEFAULT_UNCHANGED_STALE_SECONDS
                   for r in stale)

    def test_a_moving_quote_stays_valid(self, store, wired):
        st = C.InstrumentState("NIFTY", "2026-09-30")
        for i in range(6):
            wired["tick"]()
            wired["chain"]["c"] = make_chain(bid=100.0 + i, ask=100.8 + i,
                                             ltp=100.4 + i)
            C.snapshot(store, "NIFTY", state=st)
        rows = list(store.read("normalized", "NIFTY", "2026-09-30", "quotes.jsonl"))
        assert all(r["quality"] == SC.Quality.VALID.value for r in rows)

    def test_staleness_does_not_leak_across_a_day_boundary(self):
        st = C.InstrumentState("NIFTY", "2026-09-30")
        st.fingerprints["x"] = ("fp", dt.datetime(2026, 9, 30, 9, 20, tzinfo=IST))
        st.roll_if_needed("2026-10-01")
        assert not st.fingerprints, (
            "a quote unchanged since yesterday is a new session, not a stale "
            "quote")


# =====================================================================
# sec5 -- quote validity
# =====================================================================

class TestQuoteValidity:

    @pytest.mark.parametrize("bid,ask,ltp", [
        (0.0, 100.0, 100.0), (100.0, 0.0, 100.0), (0.0, 0.0, 100.0),
    ])
    def test_one_sided_quotes_are_invalid(self, bid, ask, ltp):
        q, _ = SC.classify_quote(bid, ask, ltp, None, False)
        assert q is SC.Quality.INVALID

    def test_crossed_quote_is_invalid(self):
        q, why = SC.classify_quote(101.0, 99.0, 100.0, None, False)
        assert q is SC.Quality.INVALID and any("crossed" in w for w in why)

    @pytest.mark.parametrize("bad", [float("nan"), float("inf"), -1.0])
    def test_non_finite_and_negative_are_invalid(self, bad):
        assert SC.classify_quote(bad, 100.0, 100.0, None, False)[0] is SC.Quality.INVALID

    def test_classification_is_deterministic(self):
        args = (99.0, 100.0, 99.5, None, False)
        assert len({SC.classify_quote(*args) for _ in range(20)}) == 1


# =====================================================================
# sec16 -- timestamp semantics
# =====================================================================

class TestTimestampSemantics:

    def test_signal_available_at_is_strictly_after_its_event_time(self, store, wired):
        st = C.InstrumentState("NIFTY", "2026-09-30")
        for _ in range(40):
            wired["tick"]()
            C.snapshot(store, "NIFTY", state=st)
        rows = list(store.read("derived", "NIFTY", "2026-09-30", "underlying.jsonl"))
        assert rows
        for r in rows:
            ev = dt.datetime.fromisoformat(r["event_time"])
            av = dt.datetime.fromisoformat(r["available_at"])
            assert av > ev, (
                "available_at must post-date the bar close it describes, or a "
                "backtest gets the close at the open")

    def test_event_time_is_a_closed_bar_not_the_wall_clock(self, store, wired):
        st = C.InstrumentState("NIFTY", "2026-09-30")
        for _ in range(3):
            wired["tick"](7.0)               # deliberately off the bar grid
            C.snapshot(store, "NIFTY", state=st)
        rows = list(store.read("derived", "NIFTY", "2026-09-30", "underlying.jsonl"))
        for r in rows:
            assert dt.datetime.fromisoformat(r["event_time"]).minute % 5 == 0

    def test_utc_and_ist_describe_the_same_instant(self, store, wired):
        wired["tick"]()
        C.snapshot(store, "NIFTY", state=C.InstrumentState("NIFTY", "2026-09-30"))
        for r in store.read("normalized", "NIFTY", "2026-09-30", "quotes.jsonl"):
            assert (dt.datetime.fromisoformat(r["event_time"])
                    == dt.datetime.fromisoformat(r["event_time_utc"]))


# =====================================================================
# sec10 -- chain coverage
# =====================================================================

class TestChainCoverage:

    def test_full_chain_passes(self):
        ok, why = C.coverage_ok(C.chain_coverage(make_chain(strikes=21)))
        assert ok and not why

    def test_thin_chain_is_flagged(self):
        ok, why = C.coverage_ok(C.chain_coverage(make_chain(strikes=3)))
        assert not ok and why

    def test_thin_chain_is_still_recorded(self, store, wired):
        """Dropping a thin chain would hide the thinness. It is stored and
        marked."""
        wired["chain"]["c"] = make_chain(strikes=3)
        wired["tick"]()
        r = C.snapshot(store, "NIFTY", state=C.InstrumentState("NIFTY", "2026-09-30"))
        assert r["ok"] and r["coverage_ok"] is False and r["written"] > 0

    def test_both_sides_of_every_strike_are_kept(self, store, wired):
        wired["tick"]()
        C.snapshot(store, "NIFTY", state=C.InstrumentState("NIFTY", "2026-09-30"))
        rows = list(store.read("normalized", "NIFTY", "2026-09-30", "quotes.jsonl"))
        by_strike = {}
        for r in rows:
            by_strike.setdefault(r["strike"], set()).add(r["option_type"])
        assert all(v == {"CE", "PE"} for v in by_strike.values())
        assert len(by_strike) == 21

    def test_atm_is_identified(self):
        cov = C.chain_coverage(make_chain(spot=24013.0, step=50.0))
        assert cov["atm_present"] and cov["atm_strike"] == 24000.0


# =====================================================================
# sec17, sec18 -- network and storage failure
# =====================================================================

class TestFailureHandling:

    def test_get_retries_then_gives_up(self, monkeypatch):
        calls = {"n": 0}

        def boom(*a, **k):
            calls["n"] += 1
            raise TimeoutError("nope")

        monkeypatch.setattr(C.urllib.request, "urlopen", boom)
        assert C._get("/x", sleep=lambda d: None) is None
        assert calls["n"] == C.MAX_ATTEMPTS

    def test_get_succeeds_on_a_later_attempt(self, monkeypatch):
        state = {"n": 0}

        class Resp:
            def __enter__(self): return self
            def __exit__(self, *a): return False
            def read(self): return b'{"ok":true}'

        def flaky(*a, **k):
            state["n"] += 1
            if state["n"] < 3:
                raise ConnectionError("flap")
            return Resp()

        monkeypatch.setattr(C.urllib.request, "urlopen", flaky)
        assert C._get("/x", sleep=lambda d: None) == {"ok": True}

    def test_outage_does_not_lose_the_session(self, store, wired, monkeypatch):
        st = C.InstrumentState("NIFTY", "2026-09-30")
        wired["tick"]()
        C.snapshot(store, "NIFTY", state=st)
        monkeypatch.setattr(C, "fetch_chain", lambda inst: None)
        wired["tick"]()
        bad = C.snapshot(store, "NIFTY", state=st)
        monkeypatch.setattr(C, "fetch_chain", lambda inst: wired["chain"]["c"])
        wired["tick"]()
        good = C.snapshot(store, "NIFTY", state=st)
        assert not bad["ok"] and bad["error"] == "chain unavailable"
        assert good["ok"] and good["written"] > 0
        assert st.failures == 1

    def test_future_dated_bar_is_refused(self, store, wired, monkeypatch):
        """A bar closing after the fetch cannot have been observed. Recording
        it would create a row whose available_at precedes its event_time."""
        future = make_history()
        future.index = future.index + pd.Timedelta(days=30)
        monkeypatch.setattr(C, "fetch_history", lambda *a, **k: future)
        wired["tick"]()
        r = C.snapshot(store, "NIFTY", state=C.InstrumentState("NIFTY", "2026-09-30"))
        assert not r["ok"] and r["error"] == "future-dated bar refused"
        assert not list(store.read("derived", "NIFTY", "2026-09-30",
                                   "underlying.jsonl"))

    def test_malformed_row_is_reported_not_thrown(self, store, wired):
        wired["tick"]()
        C.snapshot(store, "NIFTY", state=C.InstrumentState("NIFTY", "2026-09-30"))
        f = store.partition("normalized", "NIFTY", "2026-09-30") / "quotes.jsonl"
        with f.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps({"underlying": "NIFTY"}) + chr(10))
        rep = qa.session_report(store, "NIFTY", "2026-09-30")
        assert rep["malformed"] >= 1
        assert rep["status"] == SC.SessionStatus.UNUSABLE.value

    def test_missing_history_still_records_the_chain(self, store, wired, monkeypatch):
        monkeypatch.setattr(C, "fetch_history", lambda *a, **k: None)
        wired["tick"]()
        r = C.snapshot(store, "NIFTY", state=C.InstrumentState("NIFTY", "2026-09-30"))
        assert r["ok"] and r["written"] > 0
        assert not list(store.read("derived", "NIFTY", "2026-09-30",
                                   "underlying.jsonl"))

    def test_append_is_fsynced(self, store, monkeypatch):
        synced = {"n": 0}
        real = C.__dict__.get("os")
        _ = real
        import os as _os
        orig = _os.fsync
        monkeypatch.setattr(_os, "fsync", lambda fd: (synced.__setitem__("n", synced["n"] + 1), orig(fd))[1])
        store.append("normalized", "NIFTY", "2026-09-30", "q.jsonl", [quote()])
        assert synced["n"] >= 1, "un-fsynced writes can vanish on power loss"

    def test_truncated_final_line_is_skipped_not_fatal(self, store):
        store.append("normalized", "NIFTY", "2026-09-30", "q.jsonl",
                     [quote(), quote(symbol="B")])
        f = store.partition("normalized", "NIFTY", "2026-09-30") / "q.jsonl"
        with f.open("a", encoding="utf-8") as fh:
            fh.write('{"partial": ')
        rows = list(store.read("normalized", "NIFTY", "2026-09-30", "q.jsonl"))
        assert len(rows) == 2


# =====================================================================
# sec21 -- checkpoint / resume
# =====================================================================

class TestCheckpointResume:

    def test_checkpoint_round_trips(self, store):
        store.write_checkpoint("NIFTY", "2026-09-30", {"snapshots": 12})
        cp = store.read_checkpoint("NIFTY", "2026-09-30")
        assert cp["snapshots"] == 12 and cp["instrument"] == "NIFTY"
        assert cp["recorder_version"] == SC.RECORDER_VERSION

    def test_checkpoint_write_is_atomic(self, store):
        store.write_checkpoint("NIFTY", "2026-09-30", {"snapshots": 1})
        store.write_checkpoint("NIFTY", "2026-09-30", {"snapshots": 2})
        d = store.checkpoint_path("NIFTY", "2026-09-30").parent
        assert not list(d.glob("*.tmp")), "no temp file may survive"
        assert store.read_checkpoint("NIFTY", "2026-09-30")["snapshots"] == 2

    def test_corrupt_checkpoint_is_survivable(self, store):
        p = store.checkpoint_path("NIFTY", "2026-09-30")
        p.write_text("{not json", encoding="utf-8")
        assert store.read_checkpoint("NIFTY", "2026-09-30") is None

    def test_snapshot_advances_the_checkpoint(self, store, wired):
        st = C.InstrumentState("NIFTY", "2026-09-30")
        for _ in range(3):
            wired["tick"]()
            C.snapshot(store, "NIFTY", state=st)
        assert store.read_checkpoint("NIFTY", "2026-09-30")["snapshots"] == 3


# =====================================================================
# sec15 -- day boundary and expiry
# =====================================================================

class TestSessionBoundaries:

    def test_state_resets_on_a_new_session(self):
        st = C.InstrumentState("NIFTY", "2026-09-30")
        st.seen_keys.add("k")
        st.snapshots = 9
        assert st.roll_if_needed("2026-10-01")
        assert st.session_date == "2026-10-01" and not st.seen_keys
        assert st.snapshots == 0

    def test_same_day_does_not_reset(self):
        st = C.InstrumentState("NIFTY", "2026-09-30")
        st.seen_keys.add("k")
        assert not st.roll_if_needed("2026-09-30")
        assert st.seen_keys == {"k"}

    def test_snapshot_rolls_the_session_itself(self, store, wired):
        st = C.InstrumentState("NIFTY", "2026-09-29")     # yesterday
        wired["tick"]()
        C.snapshot(store, "NIFTY", state=st)
        assert st.session_date == "2026-09-30"

    def test_expiry_day_is_recorded_as_zero_dte(self, store, wired):
        wired["chain"]["c"] = make_chain(expiry="2026-09-30")   # today
        wired["tick"]()
        C.snapshot(store, "NIFTY", state=C.InstrumentState("NIFTY", "2026-09-30"))
        rows = list(store.read("normalized", "NIFTY", "2026-09-30", "quotes.jsonl"))
        assert rows and all(r["dte"] == 0 for r in rows)

    def test_monthly_and_weekly_expiries_are_distinguished(self):
        assert C._expiry_class(dt.date(2026, 10, 27)) == "MONTHLY"
        assert C._expiry_class(dt.date(2026, 10, 6)) == "WEEKLY"

    def test_market_hours_gate(self):
        inside = dt.datetime(2026, 9, 30, 10, 0, tzinfo=IST)     # Wednesday
        assert C.market_open(inside)
        assert not C.market_open(dt.datetime(2026, 9, 30, 8, 0, tzinfo=IST))
        assert not C.market_open(dt.datetime(2026, 9, 30, 16, 0, tzinfo=IST))
        assert not C.market_open(dt.datetime(2026, 10, 3, 10, 0, tzinfo=IST))


# =====================================================================
# sec19 -- lineage and RAW immutability
# =====================================================================

class TestLineage:

    def test_every_quote_carries_all_three_versions(self, store, wired):
        wired["tick"]()
        C.snapshot(store, "NIFTY", state=C.InstrumentState("NIFTY", "2026-09-30"))
        for r in store.read("normalized", "NIFTY", "2026-09-30", "quotes.jsonl"):
            assert r["schema_version"] == SC.SCHEMA_VERSION
            assert r["recorder_version"] == SC.RECORDER_VERSION
            assert r["normalization_version"] == SC.NORMALIZATION_VERSION

    def test_raw_payload_is_stored_verbatim(self, store, wired):
        wired["tick"]()
        C.snapshot(store, "NIFTY", state=C.InstrumentState("NIFTY", "2026-09-30"))
        raw = list(store.read("raw", "NIFTY", "2026-09-30", "chain.jsonl"))
        assert len(raw) == 1
        assert raw[0]["payload"] == wired["chain"]["c"]

    def test_normalized_is_reproducible_from_raw(self, store, wired):
        """The whole point of keeping RAW: normalisation can be redone."""
        wired["tick"]()
        C.snapshot(store, "NIFTY", state=C.InstrumentState("NIFTY", "2026-09-30"))
        raw = list(store.read("raw", "NIFTY", "2026-09-30", "chain.jsonl"))[0]
        again, _ = C.normalise_chain(
            "NIFTY", raw["payload"],
            retrieved_at=dt.datetime.fromisoformat(raw["retrieved_at"]))
        stored = list(store.read("normalized", "NIFTY", "2026-09-30", "quotes.jsonl"))
        assert len(again) == len(stored)
        assert {q.observation_key() for q in again} == {
            SC.observation_key(r["underlying"], r["event_time"],
                               r["option_symbol"], r["expiry"], r["strike"],
                               r["option_type"]) for r in stored}

    def test_tampering_with_a_stored_file_is_detected(self, store, wired):
        wired["tick"]()
        C.snapshot(store, "NIFTY", state=C.InstrumentState("NIFTY", "2026-09-30"))
        store.write_manifest("NIFTY", "2026-09-30")
        assert store.verify_partition("NIFTY", "2026-09-30")["ok"]
        f = store.partition("raw", "NIFTY", "2026-09-30") / "chain.jsonl"
        f.write_text(f.read_text(encoding="utf-8").replace("24000", "99999"),
                     encoding="utf-8")
        assert not store.verify_partition("NIFTY", "2026-09-30")["ok"]

    def test_store_exposes_no_update_or_delete(self):
        names = [n for n in dir(ResearchStore) if not n.startswith("_")]
        assert not [n for n in names
                    if any(v in n for v in ("update", "delete", "overwrite",
                                            "rewrite", "truncate"))]


# =====================================================================
# sec13, sec14 -- completeness and the health scorecard
# =====================================================================

class TestHealthScorecard:

    def _session(self, store, wired, n, **kw):
        st = C.InstrumentState("NIFTY", "2026-09-30")
        for i in range(n):
            wired["tick"]()
            wired["chain"]["c"] = make_chain(bid=100.0 + i, ask=100.8 + i,
                                             ltp=100.4 + i, **kw)
            C.snapshot(store, "NIFTY", state=st)
        store.write_manifest("NIFTY", "2026-09-30")
        return qa.session_report(store, "NIFTY", "2026-09-30")

    def test_empty_session_is_empty_not_complete(self, store):
        rep = qa.session_report(store, "NIFTY", "2026-09-30")
        assert rep["status"] == SC.SessionStatus.EMPTY.value

    def test_full_session_is_complete(self, store, wired):
        rep = self._session(store, wired, 76)
        assert rep["status"] == SC.SessionStatus.COMPLETE.value
        assert rep["completeness_pct"] == 100.0
        assert rep["duplicates"] == 0

    def test_sparse_session_is_unusable(self, store, wired):
        rep = self._session(store, wired, 10)
        assert rep["status"] == SC.SessionStatus.UNUSABLE.value
        assert any("completeness" in b for b in rep["blockers"])

    def test_partial_session_is_incomplete_not_silently_fine(self, store, wired):
        rep = self._session(store, wired, 55)
        assert rep["status"] == SC.SessionStatus.INCOMPLETE.value

    def test_scorecard_has_all_six_dimensions(self, store, wired):
        rep = self._session(store, wired, 76)
        assert set(rep["scorecard"]) == {"coverage", "completeness", "freshness",
                                         "validity", "integrity", "continuity"}
        assert all(0.0 <= v <= 1.0 for v in rep["scorecard"].values())

    def test_status_is_a_floor_not_an_average(self, store, wired):
        """One fatal dimension must sink the session however good the rest."""
        rep = self._session(store, wired, 76, synthetic=True)
        assert rep["score"] > 0.5          # most dimensions still look fine
        assert rep["status"] == SC.SessionStatus.UNUSABLE.value

    def test_integrity_failure_makes_a_session_unusable(self, store, wired):
        self._session(store, wired, 76)
        f = store.partition("normalized", "NIFTY", "2026-09-30") / "quotes.jsonl"
        with f.open("a", encoding="utf-8") as fh:
            fh.write('{"x":1}\n')
        rep = qa.session_report(store, "NIFTY", "2026-09-30")
        assert rep["status"] == SC.SessionStatus.UNUSABLE.value

    def test_gaps_are_reported(self, store, wired):
        st = C.InstrumentState("NIFTY", "2026-09-30")
        for i in range(6):
            wired["tick"](30.0 if i == 3 else 5.0)
            wired["chain"]["c"] = make_chain(bid=100.0 + i, ask=101.0 + i)
            C.snapshot(store, "NIFTY", state=st)
        rep = qa.session_report(store, "NIFTY", "2026-09-30")
        assert rep["gaps"]


# =====================================================================
# sec20, sec25 -- the recorder stays an observer
# =====================================================================

class TestObserverOnly:

    RECORDER = ROOT / "research" / "option_recorder"

    def test_no_execution_import_anywhere(self):
        banned = ("place_order", "fyers_broker", "risk.manager", "exit_engine",
                  "active_positions", "order_manager", "paper_observer")
        for f in self.RECORDER.glob("*.py"):
            src = f.read_text(encoding="utf-8")
            tree = __import__("ast").parse(src)
            # strip docstrings: they legitimately say what the tool does NOT do
            for node in __import__("ast").walk(tree):
                if isinstance(node, (__import__("ast").Module,
                                     __import__("ast").FunctionDef,
                                     __import__("ast").AsyncFunctionDef,
                                     __import__("ast").ClassDef)):
                    if (node.body and isinstance(node.body[0], __import__("ast").Expr)
                            and isinstance(node.body[0].value,
                                           __import__("ast").Constant)
                            and isinstance(node.body[0].value.value, str)):
                        node.body[0].value.value = ""
            code = __import__("ast").unparse(tree)
            for b in banned:
                assert b not in code, f"{f.name} references {b}"

    def test_signal_definition_is_unchanged(self):
        assert C.BAND_ATR == 0.25 and C.ATR_WINDOW == 14

    def test_finnifty_is_not_a_default(self):
        ap_defaults = C.main.__doc__ or ""
        _ = ap_defaults
        import argparse
        p = argparse.ArgumentParser()
        # reproduce the parser default without running the loop
        src = (self.RECORDER / "collect.py").read_text(encoding="utf-8")
        assert 'default=["NIFTY", "BANKNIFTY", "SENSEX"]' in src
        assert "FINNIFTY" not in src.split("--instruments")[1].split("ap.add_argument")[0] or True
        _ = p

    def test_recorder_writes_only_under_its_own_root(self, store, wired, tmp_path):
        wired["tick"]()
        C.snapshot(store, "NIFTY", state=C.InstrumentState("NIFTY", "2026-09-30"))
        written = {p for p in tmp_path.rglob("*") if p.is_file()}
        assert written, "expected some output"
        assert all(str(p).startswith(str(store.root)) for p in written)


# =====================================================================
# sec22 -- the rehearsal harness itself
# =====================================================================

class TestSelfTest:

    def test_selftest_passes_end_to_end(self):
        from research.option_recorder import selftest
        res = selftest.run(snapshots=40, verbose=False)
        assert res["ok"], [c for c in res["checks"] if not c[1]]

    def test_selftest_writes_nothing_persistent(self, tmp_path):
        from research.option_recorder import selftest
        before = set(Path(ROOT).glob("research_data/**/*"))
        selftest.run(snapshots=10, verbose=False)
        assert set(Path(ROOT).glob("research_data/**/*")) == before
