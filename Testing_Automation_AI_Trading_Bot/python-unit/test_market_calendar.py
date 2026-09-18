"""The holiday calendar comes from the exchange, not from a hand-edited list.

The orchestrator carried a hardcoded `NSE_HOLIDAYS` table. On 2026-09-14 it
was missing Ganesh Chaturthi and a whole session ran into a closed exchange.
Checked against the exchange's own calendar on 2026-09-18, that table was
wrong SEVEN ways:

* missing three WEEKDAY holidays -- 2026-01-15 (Maharashtra municipal
  election), 2026-03-26 (Ram Navami), 2026-03-31 (Mahavir Jayanti) -- days the
  system would have tried to trade into a shut market;
* claiming four holidays the exchange does not have -- 2026-03-20, 2026-03-27,
  2026-09-04, 2026-11-09 -- real trading days it would have sat out.

So exchange data REPLACES the fallback rather than merging with it: a union
would keep sitting out those four real trading days.

A failed fetch must never read as "no holidays" -- it keeps the last cache,
and only a year never fetched falls back to the table.
"""

from __future__ import annotations

import datetime
import json

import pytest

import _bootstrap  # noqa: F401  (side-effect: puts trading-system/ on sys.path)

from shared import market_calendar as mc

EXCHANGE_PAYLOAD = {
    "CM": [
        {"tradingDate": "15-Jan-2026", "description": "Municipal Corporation Election - Maharashtra"},
        {"tradingDate": "26-Jan-2026", "description": "Republic Day"},
        {"tradingDate": "14-Sep-2026", "description": "Ganesh Chaturthi"},
        {"tradingDate": "02-Oct-2026", "description": "Mahatma Gandhi Jayanti"},
    ]
}


@pytest.fixture
def cache(tmp_path, monkeypatch):
    monkeypatch.setattr(mc, "CACHE_PATH", tmp_path / "market_holidays.json")
    return tmp_path / "market_holidays.json"


def _seed(cache_path, holidays, fetched_at=None):
    payload = {
        "fetched_at": (fetched_at or datetime.datetime.now()).isoformat(),
        "source": "test",
        "holidays": holidays,
    }
    cache_path.write_text(json.dumps(payload), encoding="utf-8")


# ---------------------------------------------------------------------------
# Parsing the exchange feed
# ---------------------------------------------------------------------------

def test_the_exchange_feed_is_parsed_into_iso_dates(monkeypatch):
    monkeypatch.setattr(mc, "_fetch_payload", lambda timeout=20.0: EXCHANGE_PAYLOAD, raising=False)
    monkeypatch.setattr(mc.urllib.request, "urlopen", _fake_urlopen(EXCHANGE_PAYLOAD))

    out = mc.fetch_exchange_holidays()

    assert out["2026-09-14"] == "Ganesh Chaturthi"
    assert out["2026-01-15"].startswith("Municipal")
    assert all(len(k) == 10 and k[4] == "-" for k in out)


def _fake_urlopen(payload):
    class _Resp:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def read(self):
            return json.dumps(payload).encode("utf-8")

    def _open(req, timeout=None):
        return _Resp()

    return _open


def test_an_empty_feed_raises_rather_than_reporting_no_holidays(monkeypatch):
    """"Could not fetch" must never quietly become "nothing is a holiday"."""
    monkeypatch.setattr(mc.urllib.request, "urlopen", _fake_urlopen({"CM": []}))
    with pytest.raises(Exception):
        mc.fetch_exchange_holidays()


# ---------------------------------------------------------------------------
# Which source wins
# ---------------------------------------------------------------------------

def test_exchange_data_replaces_the_fallback(cache):
    """The fallback wrongly lists 2026-11-09; the exchange does not."""
    _seed(cache, {"2026-01-15": "Municipal Corporation Election - Maharashtra"})

    assert "2026-11-09" in mc.FALLBACK_HOLIDAYS[2026], "precondition: the old table has it"
    assert mc.is_trading_day(datetime.date(2026, 11, 9)) is True, "a real trading day must not be skipped"
    assert mc.is_trading_day(datetime.date(2026, 1, 15)) is False, "a weekday holiday the table missed"


def test_a_year_never_fetched_falls_back_to_the_table(cache):
    _seed(cache, {"2027-01-26": "Republic Day"})

    # 2026 is absent from the cache, so the hardcoded table answers for it.
    assert mc.is_trading_day(datetime.date(2026, 1, 26)) is False


def test_a_failed_refresh_keeps_the_previous_cache(cache, monkeypatch):
    _seed(cache, {"2026-10-02": "Mahatma Gandhi Jayanti"},
          fetched_at=datetime.datetime.now() - datetime.timedelta(days=30))

    def _boom(req, timeout=None):
        raise OSError("[Errno 11001] getaddrinfo failed")

    monkeypatch.setattr(mc.urllib.request, "urlopen", _boom)

    refreshed, detail = mc.refresh()

    assert refreshed is False
    assert "keeping 1 cached date" in detail
    assert mc.is_trading_day(datetime.date(2026, 10, 2)) is False, "the known holiday survives the outage"


def test_a_fresh_cache_is_not_refetched(cache, monkeypatch):
    _seed(cache, {"2026-10-02": "Mahatma Gandhi Jayanti"})
    monkeypatch.setattr(mc.urllib.request, "urlopen",
                        lambda *a, **k: pytest.fail("must not hit the network"))

    refreshed, detail = mc.refresh()

    assert refreshed is False and "no refresh needed" in detail


# ---------------------------------------------------------------------------
# The question every trading path asks
# ---------------------------------------------------------------------------

def test_weekends_are_closed(cache):
    _seed(cache, {})
    assert mc.closed_reason(datetime.date(2026, 9, 19)) == "weekend"
    assert mc.closed_reason(datetime.date(2026, 9, 20)) == "weekend"


def test_a_holiday_says_which_one(cache):
    _seed(cache, {"2026-10-02": "Mahatma Gandhi Jayanti"})
    assert mc.closed_reason(datetime.date(2026, 10, 2)) == "holiday: Mahatma Gandhi Jayanti"


def test_an_ordinary_weekday_is_open(cache):
    _seed(cache, {"2026-10-02": "Mahatma Gandhi Jayanti"})
    assert mc.closed_reason(datetime.date(2026, 9, 21)) is None


def test_upcoming_closures_are_listed_in_advance(cache):
    _seed(cache, {"2026-10-02": "Gandhi Jayanti", "2026-10-20": "Dussehra",
                  "2026-01-15": "Election"})

    nxt = mc.next_holidays(after=datetime.date(2026, 9, 18), limit=2)

    assert [d.isoformat() for d, _ in nxt] == ["2026-10-02", "2026-10-20"]
    assert nxt[0][1] == "Gandhi Jayanti"


# ---------------------------------------------------------------------------
# Broker status: today's truth, and "unknown" is not "open"
# ---------------------------------------------------------------------------

class _Model:
    def __init__(self, rows):
        self._rows = rows

    def market_status(self):
        return {"marketStatus": self._rows}


class _Broker:
    paper_mode = False

    def __init__(self, rows):
        self._fyers_model = _Model(rows)


def test_broker_reports_open():
    assert mc.broker_market_open(_Broker([{"market_type": "NORMAL", "status": "OPEN"}])) is True


def test_broker_reports_closed():
    rows = [{"market_type": "NORMAL", "status": "POSTCLOSE_CLOSED"},
            {"market_type": "AUCTION", "status": "CLOSED"}]
    assert mc.broker_market_open(_Broker(rows)) is False


def test_unknown_is_never_reported_as_open():
    """No session, no rows, or a raising broker must all be 'unknown'."""
    assert mc.broker_market_open(_Broker([])) is None

    class _Paper:
        paper_mode = True

    assert mc.broker_market_open(_Paper()) is None

    class _Angry:
        paper_mode = False

        @property
        def _fyers_model(self):
            raise RuntimeError("no session")

    assert mc.broker_market_open(_Angry()) is None


# ---------------------------------------------------------------------------
# Both workflows obey it
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# market_closed_now: holiday OR weekend OR after hours OR broker says shut
# ---------------------------------------------------------------------------

def test_after_hours_is_closed_even_on_a_trading_day(cache, monkeypatch):
    """A 9pm click on a Friday is not a trading moment.

    Found live on 2026-09-18: the calendar said "trading day", the broker was
    in paper mode so its status was unknown, and a manual order at 21:00 was
    accepted.
    """
    _seed(cache, {})
    monkeypatch.setattr(mc, "closed_reason", lambda day=None: None)
    monkeypatch.setattr("shared.market_hours.is_market_open", lambda *a, **k: False)

    assert mc.market_closed_now() == "outside market hours (09:15-15:30 IST)"


def test_within_hours_on_a_trading_day_is_open(cache, monkeypatch):
    _seed(cache, {})
    monkeypatch.setattr(mc, "closed_reason", lambda day=None: None)
    monkeypatch.setattr("shared.market_hours.is_market_open", lambda *a, **k: True)
    monkeypatch.setattr(mc, "broker_market_open", lambda broker=None: None)

    assert mc.market_closed_now() is None


def test_a_holiday_beats_the_clock(cache, monkeypatch):
    """Never reach the hours check on a holiday -- the reason must name it."""
    _seed(cache, {"2026-10-02": "Mahatma Gandhi Jayanti"})
    monkeypatch.setattr(mc, "closed_reason", lambda day=None: "holiday: Mahatma Gandhi Jayanti")
    monkeypatch.setattr("shared.market_hours.is_market_open", lambda *a, **k: True)

    assert mc.market_closed_now() == "holiday: Mahatma Gandhi Jayanti"


def test_the_broker_can_veto_an_otherwise_open_session(cache, monkeypatch):
    """An unscheduled halt no calendar knows about."""
    _seed(cache, {})
    monkeypatch.setattr(mc, "closed_reason", lambda day=None: None)
    monkeypatch.setattr("shared.market_hours.is_market_open", lambda *a, **k: True)
    monkeypatch.setattr(mc, "broker_market_open", lambda broker=None: False)

    assert mc.market_closed_now() == "the broker reports the market is closed right now"


def test_the_manual_order_path_checks_the_calendar():
    import inspect

    import api_bridge

    src = inspect.getsource(api_bridge.execute_order)
    assert "_market_closed_reason()" in src
    assert src.index("_market_closed_reason()") < src.index("BrokerFactory.get_active_broker()"), \
        "the market must be checked before a broker is even fetched"


def test_the_auto_entry_path_checks_the_same_calendar():
    import inspect
    import pathlib

    src = pathlib.Path(_bootstrap.TRADING_SYSTEM_ROOT, "trading_bot", "main.py").read_text(
        encoding="utf-8", errors="ignore")
    assert "_closed = _market_closed_reason()" in src
    gate = src.index("_closed = _market_closed_reason()")
    assert src.index('"Entry for %s skipped -- market is closed', gate) > gate
