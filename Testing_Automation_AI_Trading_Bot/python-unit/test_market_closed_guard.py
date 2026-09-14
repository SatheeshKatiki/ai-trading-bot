"""Do not trade when the exchange is silent (2026-09-14, Ganesh Chaturthi).

NSE and BSE were closed; `2026-09-14` was missing from the orchestrator's
hardcoded NSE_HOLIDAYS, so `is_trading_day()` said yes and a full session
ran into a closed exchange: api_bridge up from 09:00, the main paper book
scanning **4,357** times, every engine polling all day against Friday's last
bars, an EOD report at 15:30.

Nothing traded -- the variant books' bar-freshness rule refused the stale
bars, and the main book's "new trigger" fix meant an unchanging stale bias
never fired -- but nothing REFUSED on the grounds that the data was stale.
That is luck, not a rule.

A hardcoded calendar cannot be the only defence: an unlisted holiday, a feed
outage and a dropped broker session look identical from inside, and the
answer to all three is the same. So every engine now checks bar freshness
before a NEW entry (open positions keep full exit management), and the
orchestrator stands down when the exchange has printed nothing by 10:00.
"""

from __future__ import annotations

import datetime
import inspect

import pandas as pd
import pytest
import pytz

import _bootstrap
import auto_daily_session as ads
import ema9_variant_observer as ev
import paper_observer as po
from shared.instruments import is_option_symbol
from shared.market_hours import latest_bar_is_fresh

IST = pytz.timezone("Asia/Kolkata")
NOW = datetime.datetime(2026, 9, 14, 10, 30)


# ---------------------------------------------------------------------------
# The rule
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("bar,fresh", [
    ("2026-09-14 10:25:00", True),
    ("2026-09-14 10:15:00", True),                       # 15 minutes: the limit
    ("2026-09-14 10:10:00", False),                      # older than the limit
    ("2026-09-11 15:25:00", False),                      # Friday's last bar -- the incident
    ("2026-09-14 10:31:00", True),                       # a minute of clock skew is tolerated
    ("2026-09-14 10:45:00", False),                      # the future is not fresh
    ("not a time", False),
    (None, False),
])
def test_freshness(bar, fresh):
    assert latest_bar_is_fresh(bar, now=NOW) is fresh


def test_accepts_datetimes_and_timestamps():
    assert latest_bar_is_fresh(datetime.datetime(2026, 9, 14, 10, 25), now=NOW)
    assert latest_bar_is_fresh(pd.Timestamp("2026-09-14 10:25"), now=NOW)
    aware = IST.localize(datetime.datetime(2026, 9, 14, 10, 25))
    assert latest_bar_is_fresh(aware, now=IST.localize(NOW))


# ---------------------------------------------------------------------------
# The calendar, and the check that does not depend on it
# ---------------------------------------------------------------------------

def test_ganesh_chaturthi_is_in_the_calendar():
    assert "2026-09-14" in ads.NSE_HOLIDAYS[2026]
    assert ads.is_trading_day(datetime.date(2026, 9, 14)) is False
    assert ads.is_trading_day(datetime.date(2026, 9, 15)) is True


def test_cache_freshness_check(tmp_path, monkeypatch):
    monkeypatch.setattr(ads, "ROOT_DIR", tmp_path)
    data = tmp_path / "data"
    data.mkdir()
    today = ads.now_ist().strftime("%Y-%m-%d")
    path = data / "NSE_NIFTY50-INDEX_5Min.csv"

    path.write_text("datetime,open,high,low,close,volume\n2026-09-11 15:25:00,1,1,1,1,0\n", encoding="utf-8")
    assert ads.cache_has_today_bars() is False
    path.write_text(f"datetime,open,high,low,close,volume\n{today} 09:15:00,1,1,1,1,0\n", encoding="utf-8")
    assert ads.cache_has_today_bars() is True
    path.unlink()
    assert ads.cache_has_today_bars() is None          # cannot tell != closed


def test_orchestrator_stands_down_when_the_exchange_is_silent():
    src = inspect.getsource(ads.run_session_flow)
    assert "cache_has_today_bars() is False" in src
    assert "Standing down for the day" in src
    stand_down = src.index("cache_has_today_bars() is False")
    assert src.index("break", stand_down) < src.index("observer_sv.supervise()", stand_down)


# ---------------------------------------------------------------------------
# The engines
# ---------------------------------------------------------------------------

def test_main_book_refuses_a_stale_bar():
    src = inspect.getsource(po.run_session)
    assert 'latest_bar_is_fresh(state.get("bar_time"))' in src
    assert "not trading" in src
    assert '"bar_time": candles[-1].get("datetime")' in inspect.getsource(po.analyze_market_state)


def test_variant_book_refuses_a_bar_from_another_day(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(po, "alerter", None)
    monkeypatch.setattr(ev, "VARIANTS_DIR", tmp_path / "variants")
    monkeypatch.setattr(ev, "latest_closed_signal", lambda df, cfg: 1)
    ev._STALE_DATA_LOGGED.clear()
    sess = ev.load_session(tmp_path / "none.json", "5m_atm", "2026-09-14")
    stale = pd.DataFrame({"open": [1.0], "high": [1.0], "low": [1.0], "close": [23_400.0], "volume": [0.0]},
                         index=pd.DatetimeIndex(["2026-09-11 15:25"]))       # Friday's last bar
    now = IST.localize(datetime.datetime(2026, 9, 14, 10, 30))

    assert ev.consider_entry(sess, "NIFTY", ev.build_config("5m_atm"), stale, now) is False
    assert sess["open_positions"] == {} and sess["signals"] == []
    assert "no data for today" in capsys.readouterr().out


def test_live_engine_refuses_a_stale_bar():
    src = (_bootstrap.TRADING_SYSTEM_ROOT / "trading_bot" / "main.py").read_text(encoding="utf-8")
    gate = src.index("if not latest_bar_is_fresh(df.index[-1]):")
    assert src.index("compute_features", gate) > gate            # before any entry work
    assert "No fresh data for %s (last bar %s) -- no new entries." in src


# ---------------------------------------------------------------------------
# Option detection by suffix
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("symbol,is_option", [
    ("NSE:NIFTY2691523300CE", True), ("NSE:BANKNIFTY26SEP56200PE", True),
    ("BANKNIFTY 56200.0 CE", True), ("NSE:RELIANCE-EQ", False),
    ("NSE:NIFTY50-INDEX", False), ("BSE:SENSEX-INDEX", False), ("", False),
])
def test_option_symbol_reads_the_suffix(symbol, is_option):
    assert is_option_symbol(symbol) is is_option
