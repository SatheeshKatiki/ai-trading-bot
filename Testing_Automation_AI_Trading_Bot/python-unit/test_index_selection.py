"""Which indices get traded, and at what size (2026-09-11).

The owner's rules: paper-test on NIFTY, BANKNIFTY and SENSEX; once a strategy
is proven, trade ONLY the strategy and indices selected in the UI -- never
every index.

What was there before:

* the live engine (trading_bot/main.py) fell back to **all four indices**
  whenever settings had no "symbols";
* the UI had no way to choose indices at all;
* paper_observer hardcoded NIFTY + BANKNIFTY and kept its own lot table with
  BANKNIFTY at 15 -- the exchange lot is 30, so every BANKNIFTY paper P&L was
  recorded at half size -- and no SENSEX;
* with no option chain, paper_observer invented a contract (premium 0.75% of
  spot, delta 0.50) and filled it;
* the positions-file swap failed with WinError 5 whenever api_bridge was
  reading the file (28 times in the observer log).
"""

from __future__ import annotations

import inspect

import pytest

import _bootstrap
import paper_observer as po
from shared.instruments import (
    DEFAULT_PAPER_TEST_INSTRUMENTS,
    INDEX_BROKER_SYMBOLS,
    resolve_paper_test_instruments,
    resolve_trading_symbols,
)
from trading_bot.strategies.premium_selection.options_selector import INSTRUMENT_CONFIG


# ---------------------------------------------------------------------------
# Paper test universe
# ---------------------------------------------------------------------------

def test_paper_testing_adds_sensex_by_default():
    assert resolve_paper_test_instruments({}) == ["NIFTY", "BANKNIFTY", "SENSEX"]
    assert resolve_paper_test_instruments(None) == list(DEFAULT_PAPER_TEST_INSTRUMENTS)


def test_paper_setting_overrides_and_is_normalised():
    s = {"paper_test_instruments": ["BSE:SENSEX-INDEX", "nifty", "NIFTY", "RELIANCE"]}
    assert resolve_paper_test_instruments(s) == ["SENSEX", "NIFTY"]


# ---------------------------------------------------------------------------
# Live trading: exactly the UI selection
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("settings", [{}, None, {"symbols": []}, {"symbols": "NIFTY"}])
def test_live_trading_has_no_default(settings):
    assert resolve_trading_symbols(settings) == []


def test_live_trading_is_exactly_the_selection():
    assert resolve_trading_symbols({"symbols": ["NSE:NIFTY50-INDEX"]}) == ["NSE:NIFTY50-INDEX"]
    assert resolve_trading_symbols({"symbols": ["SENSEX", "nifty", "BSE:SENSEX-INDEX"]}) == \
        ["BSE:SENSEX-INDEX", "NSE:NIFTY50-INDEX"]


def test_other_exchange_symbols_pass_through_and_junk_is_dropped():
    assert resolve_trading_symbols({"symbols": ["NSE:RELIANCE-EQ", "garbage", ""]}) == ["NSE:RELIANCE-EQ"]


def test_main_has_no_every_index_fallback():
    src = (_bootstrap.TRADING_SYSTEM_ROOT / "trading_bot" / "main.py").read_text(encoding="utf-8")
    boot = src[src.index("_boot_settings = {}"):]
    assert "resolve_trading_symbols(_boot_settings)" in boot
    assert '_boot_settings.get(\n        "symbols"' not in boot
    assert "raise SystemExit(0)" in boot


def test_the_ui_offers_every_tradable_index():
    page = (_bootstrap.REPO_ROOT / "frontend" / "app" / "strategy" / "page.tsx").read_text(encoding="utf-8")
    for symbol in INDEX_BROKER_SYMBOLS.values():
        assert symbol in page
    assert "symbols: toggleSymbol(prev.symbols" in page


# ---------------------------------------------------------------------------
# paper_observer
# ---------------------------------------------------------------------------

def test_lot_sizes_come_from_the_exchange_table():
    for name in ("NIFTY", "BANKNIFTY", "SENSEX"):
        assert po.LOT_SIZE[name] == INSTRUMENT_CONFIG[name]["lot_size"]
    assert po.LOT_SIZE["BANKNIFTY"] == 30          # was 15: half-size P&L
    assert po.LOT_SIZE["SENSEX"] == 20             # was missing


def test_observer_trades_the_paper_test_set():
    assert "SENSEX" in po.SYMBOLS
    src = inspect.getsource(po.run_session)
    assert "SYMBOLS[:] = resolve_paper_test_instruments(active_settings)" in src


@pytest.mark.parametrize("chain", [
    None, {}, {"chain": []}, {"chain": [{"strike": 81300.0}], "synthetic": True},
])
def test_no_real_chain_means_no_trade(monkeypatch, chain):
    monkeypatch.setattr(po, "fetch_option_chain", lambda *a, **k: chain)
    assert po.select_best_option("SENSEX", "BUY", 81_250.0) is None


def test_positions_swap_retries_a_locked_file(monkeypatch, tmp_path):
    src, dst = tmp_path / "a.tmp", tmp_path / "a.json"
    src.write_text("{}")
    real = type(src).replace
    calls = {"n": 0}

    def flaky(self, target):
        calls["n"] += 1
        if calls["n"] < 3:
            raise PermissionError(5, "Access is denied")
        return real(self, target)

    monkeypatch.setattr(type(src), "replace", flaky)
    monkeypatch.setattr(po.time, "sleep", lambda _s: None)
    po._replace_with_retry(src, dst)
    assert calls["n"] == 3 and dst.read_text() == "{}"


def test_positions_swap_still_reports_a_persistent_lock(monkeypatch, tmp_path):
    src = tmp_path / "a.tmp"
    src.write_text("{}")

    def locked(self, target):
        raise PermissionError(5, "Access is denied")

    monkeypatch.setattr(type(src), "replace", locked)
    monkeypatch.setattr(po.time, "sleep", lambda _s: None)
    with pytest.raises(PermissionError):
        po._replace_with_retry(src, tmp_path / "a.json", attempts=3)
