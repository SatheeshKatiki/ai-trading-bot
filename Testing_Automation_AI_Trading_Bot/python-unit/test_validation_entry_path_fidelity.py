"""Regression tests: the validation harness must model the entry path the
live bot actually takes.

The defect (found 2026-08-08 during the `ema_rsi` entry-quality audit):

* `registry.run_strategy()` applies four institutional filters gated on
  `enable_*_filter` settings keys. `config/settings.json` has all four
  ENABLED. The harness called it with `settings={}`, so all four were OFF
  in every validation number ever produced.
* `main.py` copies `max_trades_per_day` from the same file into
  `risk_manager.config.max_trades_per_day` on the live entry path. The
  harness built `RiskManager` with no config, leaving the cap at 0
  (unlimited).

Measured on `ema_rsi` over the same 123-day window, same code, changing
only these settings: 522 legs / Rs 211,316 / 19.01% drawdown on the path
that was validated, versus 194 legs / Rs 81,922 / 15.24% on the path
production runs. A harness that measures a different entry path than
production is not measuring production.

Two properties must hold forever:

  1. The daily trade cap is honoured, using main.py's exact key
     precedence -- `config/settings.json` currently carries BOTH
     `max_trades_per_day` and `max_daily_trades`, so reading the wrong key
     silently models a cap production does not enforce.
  2. Passing no settings still behaves exactly as before, so every report
     written before this change stays reproducible via `--entry-path
     legacy`.
"""
import json

import _bootstrap  # noqa: F401  (side-effect: puts trading-system/ on sys.path)

import pandas as pd

from validation_harness.production_settings import (
    SETTINGS_PATH,
    load_production_settings,
    resolve_max_trades_per_day,
)


# ---------------------------------------------------------------------------
# Daily-trade-cap key precedence
# ---------------------------------------------------------------------------

def test_cap_prefers_max_trades_per_day_over_the_other_spellings():
    """main.py checks max_trades_per_day first. Both keys exist in the real
    settings file, so precedence is load-bearing, not cosmetic."""
    settings = {"max_trades_per_day": 3, "maxDailyTrades": 9, "max_daily_trades": 7}
    assert resolve_max_trades_per_day(settings) == 3


def test_cap_falls_back_through_main_pys_exact_order():
    assert resolve_max_trades_per_day({"maxDailyTrades": 9, "max_daily_trades": 7}) == 9
    assert resolve_max_trades_per_day({"max_daily_trades": 7}) == 7


def test_cap_absent_means_unlimited():
    """0 is RiskConfig's own "unlimited" sentinel — the harness must not
    invent a cap where production has none."""
    assert resolve_max_trades_per_day({}) == 0


def test_cap_ignores_unparseable_values_rather_than_crashing():
    assert resolve_max_trades_per_day({"max_trades_per_day": "not a number"}) == 0


# ---------------------------------------------------------------------------
# Production settings loading
# ---------------------------------------------------------------------------

def test_production_settings_load_from_the_same_file_main_py_reads():
    """Pinned against main.py's own _SETTINGS_PATH: config/settings.json,
    one level above the package."""
    assert SETTINGS_PATH.name == "settings.json"
    assert SETTINGS_PATH.parent.name == "config"


def test_production_settings_missing_file_degrades_to_empty():
    """A validation run must not abort because a settings file is absent;
    it must fall back to the documented legacy path."""
    assert load_production_settings(SETTINGS_PATH.parent / "no_such_settings.json") == {}


def test_production_settings_expose_the_entry_filters():
    """The four filter keys are the whole reason this module exists — if
    they ever stop being present, the harness is silently back to
    measuring an unfiltered path."""
    settings = load_production_settings()
    if not settings:                       # settings.json absent in this checkout
        return
    for key in ("enable_squeeze_filter", "enable_extension_filter",
                "enable_cpr_filter", "enable_aggression_filter"):
        assert key in settings, f"{key} missing from config/settings.json"


# ---------------------------------------------------------------------------
# The harness honours the cap, and no-settings stays unchanged
# ---------------------------------------------------------------------------

def _flat_market(bars=40):
    """A frame that generates no signals — these tests exercise the
    RiskManager wiring, not the strategy."""
    idx = pd.date_range("2026-03-02 09:15", periods=bars, freq="5min")
    return pd.DataFrame(
        {"open": 100.0, "high": 100.0, "low": 100.0, "close": 100.0, "volume": 0.0},
        index=idx,
    )


def test_harness_applies_the_cap_to_the_risk_manager():
    from validation_harness import harness as H

    captured = {}
    real_init = H.RiskManager.__init__

    def spy(self, *a, **kw):
        real_init(self, *a, **kw)
        captured["rm"] = self

    H.RiskManager.__init__ = spy
    try:
        H.run_strategy_backtest("ema_rsi", _flat_market(), settings={"max_trades_per_day": 3})
        assert captured["rm"].config.max_trades_per_day == 3
    finally:
        H.RiskManager.__init__ = real_init


def test_harness_without_settings_leaves_the_cap_unlimited():
    """The legacy path must stay bit-identical, so every pre-existing
    report remains reproducible."""
    from validation_harness import harness as H

    captured = {}
    real_init = H.RiskManager.__init__

    def spy(self, *a, **kw):
        real_init(self, *a, **kw)
        captured["rm"] = self

    H.RiskManager.__init__ = spy
    try:
        H.run_strategy_backtest("ema_rsi", _flat_market())
        assert captured["rm"].config.max_trades_per_day == 0
    finally:
        H.RiskManager.__init__ = real_init


# ---------------------------------------------------------------------------
# Reports must say which entry path produced them
# ---------------------------------------------------------------------------

def test_report_stamps_the_entry_path():
    """Two runs of the same strategy over the same window are not
    comparable across entry paths, and the path is not recoverable from
    the numbers — so it has to be recorded."""
    from validation_harness.run_validation import _describe_entry_path

    stamp = _describe_entry_path({
        "enable_squeeze_filter": True, "enable_cpr_filter": True,
        "max_trades_per_day": 3,
    })
    assert stamp["filters"]["enable_squeeze_filter"] is True
    assert stamp["filters"]["enable_cpr_filter"] is True
    assert stamp["filters"]["enable_extension_filter"] is False
    assert stamp["max_trades_per_day"] == 3

    legacy = _describe_entry_path({})
    assert not any(legacy["filters"].values())
    assert legacy["max_trades_per_day"] == 0
