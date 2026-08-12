"""brokers/fyers_broker.py — recovering from a stale Fyers session.

Root cause (found live, 2026-08-12): `FyersBroker._fyers_model` is built
once in `authenticate()` and never touched again for the rest of the
process's life. If anything else re-authenticates Fyers afterward -- in
practice, api_bridge.py's own auto-login running again on its own restart,
a completely separate process -- Fyers invalidates the old session token
server-side. The vendored fyers_apiv3 SDK's `get_call()` never raises on
this; it always returns a dict, just shaped `{"s": "error", ...}` instead
of the usual `{"d": [...]}`. `get_market_data()` used to read that as "no
quotes for these symbols" and silently return `{}`, forever, with no way
to recover short of a full process restart.

Live impact: a real PE entry signal held for 54 minutes straight
(2026-08-12, 12:05-13:00 IST) with `get_market_data` returning an empty
dict on every tick, blocking the trade the entire time behind nothing
more informative than a generic "skipping this entry" warning. Confirmed
by hand that the *current* cached token worked fine when used fresh --
the problem was the long-lived model object's own staleness, not a real
outage.
"""
import _bootstrap  # noqa: F401  (side-effect: puts trading-system/ on sys.path)

from brokers.fyers_broker import FyersBroker


class _StubFyersModel:
    """Mimics fyers_apiv3's actual behavior on a stale session: `quotes()`
    returns an error-shaped dict, never raises."""

    def __init__(self, token: str):
        self.token = token
        self.calls = 0

    def quotes(self, params):
        self.calls += 1
        if self.token == "STALE":
            return {"s": "error", "code": -15, "message": "Please provide valid token"}
        return {
            "s": "ok", "code": 200, "message": "",
            "d": [{"n": "NSE:NIFTY50-INDEX", "v": {"lp": 24280.1}}],
        }


def _make_broker(monkeypatch, initial_token: str, cached_token: str):
    broker = FyersBroker(credentials={"client_id": "FAKE-100"}, paper_mode=False)
    broker._fyers_model = _StubFyersModel(initial_token)
    monkeypatch.setattr(broker, "_load_cached_token", lambda: cached_token)

    def _fake_refresh():
        token = broker._load_cached_token()
        if not token:
            return False
        broker._fyers_model = _StubFyersModel(token)
        return True

    monkeypatch.setattr(broker, "_refresh_fyers_model", _fake_refresh)
    return broker


def test_a_stale_session_is_refreshed_and_retried_transparently(monkeypatch):
    """The exact live scenario: the in-memory model's token was
    invalidated elsewhere, but a fresh, valid token is available on disk
    -- the call should self-heal instead of returning an empty result."""
    broker = _make_broker(monkeypatch, initial_token="STALE", cached_token="FRESH")

    result = broker.get_market_data(["NSE:NIFTY50-INDEX"])

    assert "NSE:NIFTY50-INDEX" in result
    assert result["NSE:NIFTY50-INDEX"].ltp == 24280.1
    assert broker._fyers_model.token == "FRESH"


def test_a_healthy_session_is_not_refreshed_or_retried(monkeypatch):
    """No error, no reason to touch the model or make a second call."""
    broker = _make_broker(monkeypatch, initial_token="FRESH", cached_token="FRESH")

    result = broker.get_market_data(["NSE:NIFTY50-INDEX"])

    assert "NSE:NIFTY50-INDEX" in result
    assert broker._fyers_model.calls == 1


def test_still_stale_after_refresh_returns_empty_not_a_crash(monkeypatch):
    """No fresh token available anywhere (e.g. a genuine outage, not a
    rotation) -- must degrade to the pre-fix "no quotes" behavior, not
    raise, since callers already treat an empty dict as "skip this
    entry"."""
    broker = _make_broker(monkeypatch, initial_token="STALE", cached_token="STALE")

    result = broker.get_market_data(["NSE:NIFTY50-INDEX"])

    assert result == {}


def test_no_cached_token_at_all_does_not_crash(monkeypatch):
    broker = _make_broker(monkeypatch, initial_token="STALE", cached_token="")

    result = broker.get_market_data(["NSE:NIFTY50-INDEX"])

    assert result == {}


def test_refresh_fyers_model_builds_a_fresh_client_from_the_cached_token(monkeypatch):
    """Unlike the tests above (which stub _refresh_fyers_model itself),
    this exercises the real implementation end to end."""
    broker = FyersBroker(credentials={"client_id": "FAKE-100"}, paper_mode=False)
    monkeypatch.setattr(broker, "_load_cached_token", lambda: "A-REAL-LOOKING-TOKEN")

    class _FakeFyersModel:
        def __init__(self, client_id, token, log_path):
            self.client_id = client_id
            self.token = token

    monkeypatch.setattr("fyers_apiv3.fyersModel.FyersModel", _FakeFyersModel)

    refreshed = broker._refresh_fyers_model()

    assert refreshed is True
    assert broker._fyers_model.client_id == "FAKE-100"
    assert broker._fyers_model.token == "A-REAL-LOOKING-TOKEN"


def test_refresh_fyers_model_is_a_noop_with_nothing_cached(monkeypatch):
    broker = FyersBroker(credentials={"client_id": "FAKE-100"}, paper_mode=False)
    original_model = broker._fyers_model
    monkeypatch.setattr(broker, "_load_cached_token", lambda: "")

    refreshed = broker._refresh_fyers_model()

    assert refreshed is False
    assert broker._fyers_model is original_model
