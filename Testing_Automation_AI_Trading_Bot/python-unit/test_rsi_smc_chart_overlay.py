"""The chart overlay endpoint for RSI_SMC_OPTIONS_BUYER_V1.

The point of this endpoint is that the chart and the engine cannot disagree,
because there is only one implementation. These tests hold that line: the
payload must come from the strategy's own modules, must say plainly that it
is the analytical view, and must not activate anything.
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2] / "trading-system"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd  # noqa: E402

FIXTURE = (Path(__file__).resolve().parent / "fixtures" / "data"
           / "rsi_smc_NIFTY_5Min.csv")


@pytest.fixture(scope="module")
def rows():
    df = pd.read_csv(FIXTURE)
    tcol = next(c for c in df.columns if c.lower() in ("datetime", "time", "date"))
    return [{"datetime": str(r[tcol]), "open": float(r["open"]),
             "high": float(r["high"]), "low": float(r["low"]),
             "close": float(r["close"]), "volume": float(r.get("volume", 0) or 0)}
            for _, r in df.iterrows()]


@pytest.fixture
def call(monkeypatch, rows):
    import api_bridge as A

    def _call(data=None, **kw):
        payload = rows if data is None else data

        async def fake_history(**_):
            return {"data": payload}

        monkeypatch.setattr(A, "get_history", fake_history)
        # Calling the coroutine directly bypasses FastAPI, so its Query()
        # defaults are never injected -- they have to be supplied here the
        # way the framework would over HTTP.
        params = dict(symbol="NSE:NIFTY50-INDEX", start_date="2026-09-01",
                      end_date="2026-09-25", timeframe="5 Min",
                      max_bars=1500)
        params.update(kw)
        return asyncio.run(A.get_rsi_smc_overlay(**params))

    return _call


# ---------------------------------------------------------------------
# shape
# ---------------------------------------------------------------------

def test_payload_has_every_selected_object_type(call):
    out = call()
    for key in ("structure", "fvg", "sweeps", "levels", "pd_band"):
        assert key in out, f"missing {key}"
    assert out["bars"] > 0
    assert out["structure"] and out["fvg"] and out["sweeps"]


def test_structure_separates_bos_from_choch(call):
    types = {e["type"].upper() for e in call()["structure"]}
    assert any(t.startswith("BOS") for t in types)
    assert any("CH" in t and not t.startswith("BOS") for t in types)


def test_every_object_carries_a_drawable_time_and_price(call):
    out = call()
    for e in out["structure"]:
        assert isinstance(e["epoch"], int) and e["price"] is not None
    for g in out["fvg"]:
        assert g["top"] is not None and g["bottom"] is not None
        assert g["top"] >= g["bottom"]
    for s in out["sweeps"]:
        assert s["extreme"] is not None


def test_pd_band_carries_the_frozen_rule_tolerance(call):
    out = call()
    assert out["params"]["pd_band_atr"] == 0.25
    banded = [b for b in out["pd_band"] if b["pdh"] is not None and b["tol"] is not None]
    assert banded, "no prior-day levels resolved"
    assert all(b["tol"] > 0 for b in banded)


# ---------------------------------------------------------------------
# honesty about what is being drawn
# ---------------------------------------------------------------------

def test_payload_declares_itself_analytical(call):
    """The owner chose the analytical view. The payload has to say so, or a
    reader six months from now assumes the engine saw this."""
    out = call()
    assert out["view"] == "analytical"
    assert out["causal"] is False
    assert "not what the engine saw" in out["notice"].lower()


def test_payload_declares_the_strategy_inactive(call):
    out = call()
    assert out["active"] is False
    assert out["strategy_id"] == "RSI_SMC_OPTIONS_BUYER_V1"


def test_fvg_reports_its_confirmation_lag(call):
    """The gap between the bar drawn and the bar the engine could use it."""
    assert all("confirmation_lag" in g for g in call()["fvg"])


# ---------------------------------------------------------------------
# what must NOT be there
# ---------------------------------------------------------------------

def test_order_blocks_are_not_returned(call):
    """Phase 7 blocked Order Blocks for this strategy. Drawing them beside
    the objects it does use would imply otherwise."""
    out = call()
    assert "order_blocks" not in out
    assert "order_block" not in json.dumps(out).lower()


def test_no_trade_or_signal_field_leaks_into_the_overlay(call):
    blob = json.dumps(call()).lower()
    for banned in ("buy ce", "buy pe", "entry", "stoploss", "target",
                   "order_id", "quantity", "premium"):
        assert banned not in blob, f"overlay leaked {banned}"


def test_sweeps_are_deduplicated(call):
    """reference_sweeps holds its flag for sweep_recent_bars after the event.
    Undeduplicated, one sweep becomes five markers."""
    import numpy as np
    from trading_bot.strategies.rsi_smc_options_buyer import liquidity as L
    from trading_bot.strategies.rsi_smc_options_buyer.config import RsiSmcConfig

    out = call()
    df = pd.DataFrame(out["levels"])  # one row per bar
    raw_df = pd.read_csv(FIXTURE)
    tcol = next(c for c in raw_df.columns if c.lower() in ("datetime", "time", "date"))
    raw_df[tcol] = pd.to_datetime(raw_df[tcol])
    raw_df = raw_df.set_index(tcol).sort_index()
    cfg = RsiSmcConfig()
    res = L.reference_sweeps(raw_df, cfg.sweep_lookback, cfg.sweep_recent_bars)
    raw_flags = int(np.count_nonzero(res.bullish) + np.count_nonzero(res.bearish))

    assert len(out["sweeps"]) < raw_flags, (
        f"{len(out['sweeps'])} markers vs {raw_flags} raw flags -- not deduped")
    assert len(df) == out["bars"]


def test_one_sweep_never_becomes_two_markers(call):
    """Within the flag's own hold window, the same swept extreme must appear
    once. Beyond it, the market genuinely re-swept that price and two
    markers are correct -- collapsing those would hide a real re-test."""
    from trading_bot.strategies.rsi_smc_options_buyer.config import RsiSmcConfig
    out = call()
    tf_s = RsiSmcConfig().timeframe_minutes * 60
    window = RsiSmcConfig().sweep_recent_bars * tf_s
    last: dict = {}
    for s in out["sweeps"]:
        key = (s["side"], s["extreme"])
        prev = last.get(key)
        if prev is not None:
            gap = s["epoch"] - prev
            assert gap > window, (
                f"sweep {key} re-emitted after {gap}s, inside the "
                f"{window}s hold window -- that is one event drawn twice")
        last[key] = s["epoch"]


# ---------------------------------------------------------------------
# degradation
# ---------------------------------------------------------------------

def test_no_history_returns_empty_not_an_error(call):
    out = call(data=[])
    assert out["bars"] == 0 and out["structure"] == [] and out["sweeps"] == []


def test_too_few_bars_says_so(call, rows):
    out = call(data=rows[:20])
    assert out["bars"] == 20
    assert "need" in (out.get("message") or "")
    assert out["structure"] == []


def test_max_bars_is_honoured(call):
    out = call(max_bars=200)
    assert out["bars"] == 200
    assert len(out["levels"]) == 200


# ---------------------------------------------------------------------
# one implementation
# ---------------------------------------------------------------------

def test_endpoint_uses_the_strategys_own_modules(call):
    """If this ever stops importing the strategy package, the chart has
    silently grown a second implementation again."""
    src = (ROOT / "api_bridge.py").read_text(encoding="utf-8")
    body = src.split("async def get_rsi_smc_overlay")[1].split("\n@app.")[0]
    for mod in ("rsi_smc_options_buyer import levels",
                "rsi_smc_options_buyer import liquidity",
                "rsi_smc_options_buyer import structure"):
        assert mod in body, f"overlay no longer uses {mod}"
    assert "build_analytical" in body


def test_overlay_matches_the_strategys_own_structure_count(call):
    """The endpoint must report exactly what the strategy's module produces,
    with nothing added or filtered."""
    from trading_bot.strategies.rsi_smc_options_buyer import structure as S
    from trading_bot.strategies.rsi_smc_options_buyer.config import RsiSmcConfig

    raw = pd.read_csv(FIXTURE)
    tcol = next(c for c in raw.columns if c.lower() in ("datetime", "time", "date"))
    raw[tcol] = pd.to_datetime(raw[tcol])
    df = raw.set_index(tcol).sort_index()[["open", "high", "low", "close", "volume"]]

    view = S.build_analytical(df, RsiSmcConfig(), symbol="test:cmp")
    expected = sum(1 for o in view.objects if o.kind == "structure_event")
    assert len(call()["structure"]) == expected


def test_settings_json_gained_no_rsi_smc_key():
    cfg = json.loads((ROOT / "config" / "settings.json").read_text(encoding="utf-8"))
    assert cfg["active_strategy"] == "ema9_rsi_momentum"
    assert not [k for k in cfg if "rsi_smc" in k]
