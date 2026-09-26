"""Phase 12 -- the observed-option-data recorder.

Research infrastructure, so these tests are about DATA INTEGRITY rather than
trading behaviour: that an observation is never silently replaced by a model,
that RAW is never rewritten, that `available_at` is distinct from
`event_time`, and that the collector cannot reach production code.
"""
from __future__ import annotations

import datetime as dt
import pathlib

import pytest

import _bootstrap  # noqa: F401

from research.option_recorder import schema as SC
from research.option_recorder.store import ResearchStore

IST = dt.timezone(dt.timedelta(hours=5, minutes=30))


def _leg(bid=100.0, ask=100.5, ltp=100.2, oi=1000, vol=50, sym="X"):
    return {"bid": bid, "ask": ask, "ltp": ltp, "oi": oi, "oichg": 10,
            "volume": vol, "symbol": sym, "iv": 14.2, "delta": 0.5,
            "gamma": 0.001, "theta": -8.0, "vega": 3.0}


def _chain(synthetic=False, expiry="2026-10-06", spot=24000.0, strikes=(23900, 24000, 24100)):
    return {
        "symbol": "NSE:NIFTY50-INDEX", "underlying_price": spot,
        "atm": 24000, "expiry": expiry, "synthetic": synthetic,
        "priceSource": "model_chain" if synthetic else "broker_option_chain",
        "chain": [{"strike": float(s),
                   "ce": _leg(sym=f"NIFTY{s}CE"),
                   "pe": _leg(sym=f"NIFTY{s}PE")} for s in strikes],
    }


@pytest.fixture()
def store(tmp_path) -> ResearchStore:
    return ResearchStore(tmp_path / "research_data")


# ---------------------------------------------------------------------
# Quote validation
# ---------------------------------------------------------------------

def test_valid_two_sided_quote():
    q, reasons = SC.classify_quote(100.0, 100.5, 100.2, 5.0, False)
    assert q is SC.Quality.VALID and reasons == ()


def test_crossed_quote_is_invalid():
    q, reasons = SC.classify_quote(101.0, 100.0, 100.5, 1.0, False)
    assert q is SC.Quality.INVALID
    assert any("crossed" in r for r in reasons)


@pytest.mark.parametrize("bid,ask", [(0.0, 100.0), (100.0, 0.0), (0.0, 0.0)])
def test_one_sided_quote_is_invalid(bid, ask):
    """No two-sided quote means execution cannot be reconstructed, and sec24
    forbids falling back to the last traded price."""
    q, reasons = SC.classify_quote(bid, ask, 100.0, 1.0, False)
    assert q is SC.Quality.INVALID
    assert any("two-sided" in r for r in reasons)


def test_negative_and_nonfinite_are_invalid():
    assert SC.classify_quote(-1.0, 10.0, 5.0, 1.0, False)[0] is SC.Quality.INVALID
    assert SC.classify_quote(10.0, 10.5, 0.0, 1.0, False)[0] is SC.Quality.INVALID
    assert SC.classify_quote(float("nan"), 10.0, 5.0, 1.0, False)[0] is SC.Quality.INVALID


def test_stale_quote_detected():
    q, reasons = SC.classify_quote(100.0, 100.5, 100.2, 500.0, False)
    assert q is SC.Quality.STALE
    assert any("age" in r for r in reasons)


def test_synthetic_beats_every_other_verdict():
    """A modelled premium is not an observation however well-formed it looks."""
    q, _ = SC.classify_quote(100.0, 100.5, 100.2, 1.0, True)
    assert q is SC.Quality.SYNTHETIC
    # even a corrupt synthetic quote stays SYNTHETIC, never INVALID
    q2, _ = SC.classify_quote(101.0, 100.0, 100.2, 9999.0, True)
    assert q2 is SC.Quality.SYNTHETIC


# ---------------------------------------------------------------------
# Normalisation: strike / expiry / CE-PE / timestamps
# ---------------------------------------------------------------------

def test_chain_normalisation_maps_every_leg():
    from research.option_recorder.collect import normalise_chain
    now = dt.datetime(2026, 10, 1, 11, 30, tzinfo=IST)
    quotes, counts = normalise_chain("NIFTY", _chain(), retrieved_at=now)

    assert len(quotes) == 6                      # 3 strikes x CE/PE
    assert {q.option_type for q in quotes} == {"CE", "PE"}
    assert {q.strike for q in quotes} == {23900.0, 24000.0, 24100.0}
    assert all(q.expiry == "2026-10-06" for q in quotes)
    assert all(q.underlying == "NIFTY" for q in quotes)
    assert counts[SC.Quality.VALID.value] == 6


def test_dte_and_expiry_class():
    from research.option_recorder.collect import normalise_chain
    now = dt.datetime(2026, 10, 1, 11, 30, tzinfo=IST)
    q = normalise_chain("NIFTY", _chain(expiry="2026-10-06"), retrieved_at=now)[0][0]
    assert q.dte == 5
    assert q.expiry_class == "WEEKLY"
    q2 = normalise_chain("NIFTY", _chain(expiry="2026-10-27"), retrieved_at=now)[0][0]
    assert q2.expiry_class == "MONTHLY"


def test_timestamps_are_normalised_and_distinct_fields():
    """`event_time` (market state) and `available_at` (when we knew it) are
    separate fields -- sec16. Both must be present and parseable."""
    from research.option_recorder.collect import normalise_chain
    now = dt.datetime(2026, 10, 1, 11, 30, tzinfo=IST)
    q = normalise_chain("NIFTY", _chain(), retrieved_at=now)[0][0]
    assert dt.datetime.fromisoformat(q.event_time).tzinfo is not None
    assert dt.datetime.fromisoformat(q.event_time_utc).tzinfo is not None
    assert q.session_date == "2026-10-01"
    assert hasattr(q, "available_at") and q.available_at


def test_synthetic_chain_marks_every_leg():
    from research.option_recorder.collect import normalise_chain
    now = dt.datetime(2026, 10, 1, 11, 30, tzinfo=IST)
    quotes, counts = normalise_chain("NIFTY", _chain(synthetic=True), retrieved_at=now)
    assert counts[SC.Quality.SYNTHETIC.value] == len(quotes)
    assert counts[SC.Quality.VALID.value] == 0


# ---------------------------------------------------------------------
# Execution reconstruction (sec24)
# ---------------------------------------------------------------------

def test_executable_prices_use_ask_to_buy_and_bid_to_sell():
    from research.option_recorder.collect import normalise_chain
    now = dt.datetime(2026, 10, 1, 11, 30, tzinfo=IST)
    q = normalise_chain("NIFTY", _chain(), retrieved_at=now)[0][0]
    assert q.executable_buy() == pytest.approx(100.5)
    assert q.executable_sell() == pytest.approx(100.0)
    assert q.spread == pytest.approx(0.5)


def test_executable_price_is_none_without_a_two_sided_quote():
    """It must NOT silently substitute the last traded price."""
    q = SC.OptionQuote(
        event_time="t", event_time_utc="t", session_date="2026-10-01",
        available_at="t", underlying="NIFTY", option_symbol="X",
        expiry="2026-10-06", strike=24000.0, option_type="CE",
        underlying_price=24000.0, last_price=100.0, bid=0.0, ask=0.0,
        volume=0, open_interest=0, oi_change=0)
    assert q.executable_buy() is None
    assert q.executable_sell() is None
    assert q.spread is None


# ---------------------------------------------------------------------
# Store: append-only, lineage, integrity
# ---------------------------------------------------------------------

def test_append_and_read_round_trip(store):
    rows = [{"a": 1}, {"a": 2}]
    assert store.append("events", "NIFTY", "2026-10-01", "signals.jsonl", rows) == 2
    back = list(store.read("events", "NIFTY", "2026-10-01", "signals.jsonl"))
    assert [r["a"] for r in back] == [1, 2]
    assert all("_checksum" in r for r in back)


def test_append_never_rewrites_existing_records(store):
    store.append("raw", "NIFTY", "2026-10-01", "chain.jsonl", [{"n": 1}])
    first = (store.partition("raw", "NIFTY", "2026-10-01") / "chain.jsonl").read_text()
    store.append("raw", "NIFTY", "2026-10-01", "chain.jsonl", [{"n": 2}])
    second = (store.partition("raw", "NIFTY", "2026-10-01") / "chain.jsonl").read_text()
    assert second.startswith(first), "existing RAW bytes must be preserved verbatim"


def test_store_exposes_no_update_or_delete():
    """Append-only by construction, not by convention."""
    forbidden = [n for n in dir(ResearchStore)
                 if any(k in n.lower() for k in ("update", "delete", "overwrite", "truncate"))]
    assert not forbidden, f"store must not expose {forbidden}"


def test_truncated_final_line_is_skipped_not_fatal(store):
    store.append("events", "NIFTY", "2026-10-01", "signals.jsonl", [{"a": 1}])
    p = store.partition("events", "NIFTY", "2026-10-01") / "signals.jsonl"
    with p.open("a", encoding="utf-8") as fh:
        fh.write('{"a": 2, "truncat')          # killed mid-write
    rows = list(store.read("events", "NIFTY", "2026-10-01", "signals.jsonl"))
    assert [r["a"] for r in rows] == [1]


def test_manifest_and_integrity_verification(store):
    store.append("normalized", "NIFTY", "2026-10-01", "quotes.jsonl", [{"a": 1}])
    m = store.write_manifest("NIFTY", "2026-10-01")
    assert m["files"], "manifest must list the partition files"
    assert store.verify_partition("NIFTY", "2026-10-01")["ok"]


def test_integrity_check_detects_tampering(store):
    store.append("normalized", "NIFTY", "2026-10-01", "quotes.jsonl", [{"a": 1}])
    store.write_manifest("NIFTY", "2026-10-01")
    p = store.partition("normalized", "NIFTY", "2026-10-01") / "quotes.jsonl"
    p.write_text('{"a": 999}\n', encoding="utf-8")       # rewrite history
    res = store.verify_partition("NIFTY", "2026-10-01")
    assert not res["ok"] and res["mismatches"]


def test_raw_payload_is_stored_verbatim(store):
    payload = _chain()
    store.append_raw("NIFTY", "2026-10-01", payload,
                     endpoint="/api/option-chain", retrieved_at="t")
    rec = next(iter(store.read("raw", "NIFTY", "2026-10-01", "chain.jsonl")))
    assert rec["payload"] == payload
    assert rec["endpoint"] == "/api/option-chain"


def test_unknown_layer_rejected(store):
    with pytest.raises(ValueError):
        store.partition("guesses", "NIFTY", "2026-10-01")


# ---------------------------------------------------------------------
# Provenance and the research guard
# ---------------------------------------------------------------------

def test_observed_fields_are_marked_observed():
    for f in ("bid", "ask", "last_price", "open_interest", "volume", "strike"):
        assert SC.FIELD_PROVENANCE[f] is SC.Provenance.OBSERVED


def test_iv_and_greeks_are_marked_derived_not_observed():
    """The broker publishes no IV or Greeks; api_bridge solves them from the
    real premium. Recording them as OBSERVED would be a false claim."""
    for f in ("implied_volatility", "delta", "gamma", "theta", "vega"):
        assert SC.FIELD_PROVENANCE[f] is SC.Provenance.DERIVED


def test_research_guard_is_on():
    assert SC.REQUIRE_OBSERVED_OPTION_DATA is True


# ---------------------------------------------------------------------
# Isolation from production
# ---------------------------------------------------------------------

def test_recorder_imports_no_execution_code():
    """It must be structurally incapable of trading.

    Checked on the AST with docstrings stripped, so prose describing what the
    module does NOT do cannot trip it -- an earlier version of this test
    failed on its own explanatory docstring.
    """
    import ast

    pkg = pathlib.Path(_bootstrap.TRADING_SYSTEM_ROOT, "research", "option_recorder")
    banned = ("place_order", "OrderRequest", "BrokerFactory", "RiskManager",
              "SmartExitEngine", "active_positions", "record_trade", "update_equity")

    for f in pkg.glob("*.py"):
        tree = ast.parse(f.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef,
                                 ast.AsyncFunctionDef)):
                body = node.body
                if body and isinstance(body[0], ast.Expr) and \
                        isinstance(body[0].value, ast.Constant) and \
                        isinstance(body[0].value.value, str):
                    node.body = body[1:]          # drop the docstring
        code = ast.unparse(tree)
        for token in banned:
            assert token not in code, f"{f.name} executable code references {token}"


def test_recorder_imports_no_broker_or_order_module():
    """No import path into execution, checked on the import statements."""
    import ast

    pkg = pathlib.Path(_bootstrap.TRADING_SYSTEM_ROOT, "research", "option_recorder")
    for f in pkg.glob("*.py"):
        tree = ast.parse(f.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            mods = []
            if isinstance(node, ast.Import):
                mods = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                mods = [node.module or ""]
            for m in mods:
                assert not m.startswith("brokers"), f"{f.name} imports {m}"
                assert "exit_engine" not in m and "risk" not in m, f"{f.name} imports {m}"


def test_production_does_not_import_the_recorder():
    """The dependency must run one way only."""
    root = pathlib.Path(_bootstrap.TRADING_SYSTEM_ROOT)
    for sub in ("trading_bot", "brokers", "shared"):
        for f in (root / sub).rglob("*.py"):
            assert "option_recorder" not in f.read_text(encoding="utf-8"), f
    assert "option_recorder" not in (root / "api_bridge.py").read_text(encoding="utf-8")


def test_finnifty_is_not_a_default_instrument():
    """Its Phase 9 holdout is sealed; collecting it must be a deliberate act."""
    src = pathlib.Path(_bootstrap.TRADING_SYSTEM_ROOT, "research",
                       "option_recorder", "collect.py").read_text(encoding="utf-8")
    assert 'default=["NIFTY", "BANKNIFTY", "SENSEX"]' in src
