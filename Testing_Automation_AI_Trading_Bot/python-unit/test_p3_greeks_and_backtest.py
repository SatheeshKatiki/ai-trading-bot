"""Audit P3 (2026-09-12): the UI's Greeks panel and backtest must show the real thing.

* ``/api/option-greeks`` priced every contract off an IV invented from
  moneyness, assumed a Thursday expiry for every index (NIFTY/BANKNIFTY are
  Tuesday) and used stale lots (NIFTY 75, SENSEX 10); its Next.js proxy
  answered a backend failure with Greeks it made up (spot 24250) at HTTP 200.
  Both now serve the broker chain's own values or an honest error.
* ``/api/backtest`` ran ema9_rsi_momentum through the generic engine's
  underlying-% stop/target (0.6% / 2.5%). It now uses the strategy's own
  premium exits: SL 15%, the ratcheting ladder, the reversal, 15:15.
"""

from __future__ import annotations

import datetime
import types

import numpy as np
import pandas as pd
import pytest
import pytz
from fastapi.testclient import TestClient

import _bootstrap
import api_bridge
from api_bridge import app
from backtesting_engine import premium_ladder as pl
from shared.security.sessions import create_session, revoke_session

IST = pytz.timezone("Asia/Kolkata")

# ---------------------------------------------------------------------------
# /api/option-greeks
# ---------------------------------------------------------------------------

CHAIN = {
    "symbol": "SENSEX", "underlying_price": 74_781.76, "strike_step": 100.0, "expiry": "17-09-2026",
    "synthetic": False, "priceSource": "broker_option_chain",
    "chain": [{"strike": 74_800.0,
               "ce": {"ltp": 568.65, "bid": 568.0, "ask": 569.5, "iv": 13.2, "delta": 0.5204,
                      "gamma": 0.00011, "theta": -35.1, "vega": 22.4},
               "pe": {"ltp": 364.9, "bid": 364.0, "ask": 365.5, "iv": 13.8, "delta": -0.4742,
                      "gamma": 0.00011, "theta": -33.0, "vega": 22.1}}],
}


@pytest.fixture
def client(monkeypatch):
    api_bridge._GREEKS_CHAIN_CACHE.clear()
    token = create_session("greeks-test-user")
    c = TestClient(app, client=("127.0.0.1", 50001))
    c.headers.update({"Authorization": f"Bearer {token}"})
    yield c
    revoke_session(token)
    api_bridge._GREEKS_CHAIN_CACHE.clear()


def _serve(monkeypatch, chain):
    async def fake(symbol):
        return chain
    monkeypatch.setattr(api_bridge, "_fetch_real_option_chain", fake)


def test_greeks_come_from_the_real_chain(client, monkeypatch):
    _serve(monkeypatch, CHAIN)
    r = client.get("/api/option-greeks", params={"symbol": "SENSEX", "strike": 74800, "opt_type": "CE"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["premium"] == 568.65 and body["iv"] == 13.2
    assert body["greeks"]["delta"] == 0.5204 and body["greeks"]["theta"] == -35.1
    assert body["lot_size"] == 20                                   # was 10
    assert body["expiry"] == "17-09-2026" and body["expiry_days"] >= 0
    assert body["status"] == "ATM" and body["spot_source"] == "broker_option_chain"
    assert body["greeks"]["theta_per_lot"] == round(35.1 * 20, 2)


@pytest.mark.parametrize("chain,code", [
    (None, 503),
    (dict(CHAIN, synthetic=True), 503),
    (dict(CHAIN, chain=[{"strike": 74_800.0, "ce": {"ltp": 0}, "pe": {}}]), 503),
])
def test_no_real_data_means_no_greeks(client, monkeypatch, chain, code):
    _serve(monkeypatch, chain)
    assert client.get("/api/option-greeks", params={"symbol": "SENSEX", "strike": 74800}).status_code == code


def test_a_strike_outside_the_chain_is_404(client, monkeypatch):
    _serve(monkeypatch, CHAIN)
    assert client.get("/api/option-greeks", params={"symbol": "SENSEX", "strike": 90000}).status_code == 404


def test_expiry_days_from_the_real_expiry():
    now = IST.localize(datetime.datetime(2026, 9, 15, 9, 30))
    assert api_bridge._expiry_days_from_chain("15-09-2026", now) == pytest.approx(0.25)
    assert api_bridge._expiry_days_from_chain("junk", now) is None


def test_the_invented_model_is_gone():
    import inspect
    src = inspect.getsource(api_bridge.get_option_greeks)
    for gone in ("Estimate IV from moneyness", "days_until_thursday", '"SENSEX": 10'):
        assert gone not in src


def test_the_proxy_forwards_failure_instead_of_inventing_greeks():
    route = (_bootstrap.REPO_ROOT / "frontend" / "app" / "api" / "option-greeks" / "route.ts").read_text(encoding="utf-8")
    # Code only: the route's comment documents the fallback it replaced.
    code = "\n".join(line for line in route.splitlines()
                     if not line.strip().startswith(("*", "/*", "//")))
    assert "moneyness" not in code and "24250" not in code
    assert "status: response.status" in code and "503" in code


# ---------------------------------------------------------------------------
# Premium-ladder backtest
# ---------------------------------------------------------------------------

def _bars(path, start="2026-09-14 09:15"):
    idx = pd.date_range(start, periods=len(path), freq="5min")
    close = np.asarray(path, dtype=float)
    return pd.DataFrame({"datetime": idx.strftime("%Y-%m-%d %H:%M:%S"), "open": close,
                         "high": close + 1, "low": close - 1, "close": close, "volume": 0.0})


@pytest.fixture(autouse=True)
def _no_reversals(monkeypatch):
    """Tests below control reversals explicitly."""
    def none(frame, cfg):
        z = np.zeros(len(frame), dtype=bool)
        return types.SimpleNamespace(bullish=z.copy(), bearish=z.copy())
    monkeypatch.setattr(pl, "compute_reversal_signals", none)


def _run(path, entry_bar=0, side=1, **kw):
    df = _bars(path)
    sig = np.zeros(len(df), dtype=int)
    sig[entry_bar] = side
    return pl.run_premium_ladder_backtest(df, pd.Series(sig), symbol="NIFTY", quantity=65, **kw)


def test_a_runner_climbs_the_ladder_and_is_trailed_out():
    # NIFTY 23,000: premium 0.40% = Rs 92, delta 0.5 -> +1% premium per 1.84 pts.
    up = [23_000 + 8 * k for k in range(15)] + [23_112 - 12 * k for k in range(1, 10)]
    res = _run(up)
    t = res["trades"][0]
    assert t["type"] == "BUY" and t["exit_reason"].startswith("TRAILING STOP")
    assert t["best_pct"] > 50 and t["pnl"] > 0
    assert res["stats"]["exitModel"] == "premium_ladder" and res["stats"]["targetPct"] is None


def test_a_loser_hits_the_15pct_stop():
    res = _run([23_000 - 6 * k for k in range(12)])
    assert res["trades"][0]["exit_reason"] == "STOP LOSS"
    assert res["trades"][0]["return_pct"] < -14


def test_a_put_profits_from_a_fall():
    res = _run([23_000 - 8 * k for k in range(15)] + [22_888 + 12 * k for k in range(1, 10)], side=-1)
    assert res["trades"][0]["type"] == "SELL" and res["trades"][0]["pnl"] > 0


def test_reversal_exit(monkeypatch):
    def rev(frame, cfg):
        bear = np.zeros(len(frame), dtype=bool)
        bear[4] = True
        return types.SimpleNamespace(bullish=np.zeros(len(frame), dtype=bool), bearish=bear)
    monkeypatch.setattr(pl, "compute_reversal_signals", rev)
    res = _run([23_000 + k for k in range(10)])
    assert res["trades"][0]["exit_reason"] == "REVERSAL EXIT"
    assert res["trades"][0]["exit_time"].endswith("09:35:00")


def test_eod_square_off_and_no_late_entries():
    res = _run([23_000.0] * 75, entry_bar=70)                      # 15:05 bar
    assert res["trades"][0]["exit_reason"] == "EOD 15:15"
    assert _run([23_000.0] * 75, entry_bar=72)["trades"] == []     # 15:15: too late


def test_costs_are_charged():
    res = _run([23_000.0] * 20)
    t = res["trades"][0]
    assert t["pnl"] < 0                                            # flat spot: spread + theta + brokerage
    assert res["stats"]["totalSpreadCost"] > 0 and res["stats"]["totalThetaCost"] > 0


def test_backtest_routes_ema9_to_its_own_exits():
    src = (_bootstrap.TRADING_SYSTEM_ROOT / "api_bridge.py").read_text(encoding="utf-8")
    handler = src[src.index("async def get_backtest("):]
    route = handler.index('if strategy == "ema9_rsi_momentum":')
    assert handler.index("run_premium_ladder_backtest", route) < handler.index("run_intraday_backtest,", route)
