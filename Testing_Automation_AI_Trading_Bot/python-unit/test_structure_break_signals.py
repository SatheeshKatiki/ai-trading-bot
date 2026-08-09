"""Unit tests for the `structure_break` strategy's design properties.

These are not "does it make money" tests. Each one pins a property the
strategy's philosophy depends on, chosen because the corresponding
failure has actually happened in this repository before:

* churn / duplicate re-entry (measured as the dominant drawdown driver in
  `ema_rsi` and `advanced_ai`),
* look-ahead and forming-bar semantics (the `TieredExitManager` Phase 3
  divergence, and the classic self-referencing Donchian defect),
* silent zero-signal conditions (five separate occurrences in the audit
  record),
* the signal contract the registry and `main.py` depend on.
"""
import _bootstrap  # noqa: F401  (side-effect: puts trading-system/ on sys.path)

import numpy as np
import pandas as pd
import pytest

from trading_bot.strategies.structure_break import (
    OPENING_RANGE_MINUTES,
    STRATEGY_NAME,
    generate_signals,
)

BAR = "5min"
RANGE_BARS = OPENING_RANGE_MINUTES // 5  # 6 bars of 5 minutes


def _day(closes, date="2026-03-02", freq=BAR, start="09:15", spread=2.0):
    idx = pd.date_range(f"{date} {start}", periods=len(closes), freq=freq)
    close = np.asarray(closes, dtype=float)
    return pd.DataFrame(
        {"open": close, "high": close + spread, "low": close - spread,
         "close": close, "volume": np.full(len(close), 1e5)},
        index=idx,
    )


def _flat_then(after, base=24_000.0, n_range=RANGE_BARS):
    """A perfectly flat opening range followed by `after`."""
    return list(np.full(n_range, base)) + list(after)


# ─────────────────────────────────────────────────────────────────────
# Core event behaviour
# ─────────────────────────────────────────────────────────────────────

def test_breakout_above_the_opening_range_emits_a_long_event():
    df = _day(_flat_then([24_050, 24_060, 24_070]))
    sig = generate_signals(df)
    assert (sig == 1).sum() == 1
    assert (sig == -1).sum() == 0


def test_breakdown_below_the_opening_range_emits_a_short_event():
    df = _day(_flat_then([23_950, 23_940, 23_930]))
    sig = generate_signals(df)
    assert (sig == -1).sum() == 1
    assert (sig == 1).sum() == 0


def test_no_event_while_price_stays_inside_the_range():
    """The strategy's philosophy is that nothing has happened yet."""
    df = _day(_flat_then([24_001, 23_999, 24_000, 24_001] * 4))
    assert (generate_signals(df) != 0).sum() == 0


def test_range_bars_themselves_never_signal():
    """A bar that helps DEFINE the range cannot also break it — that is
    the self-referencing defect that plagues naive Donchian code."""
    df = _day([24_000, 24_100, 23_900, 24_050, 24_000, 24_000, 24_000, 24_000])
    sig = generate_signals(df)
    assert (sig.iloc[:RANGE_BARS] == 0).all()


# ─────────────────────────────────────────────────────────────────────
# Churn / duplicate prevention — by construction, not by patch
# ─────────────────────────────────────────────────────────────────────

def test_sustained_breakout_emits_exactly_one_event_not_one_per_bar():
    """The failure this design exists to avoid: a level-triggered
    strategy re-enters the same setup on every bar it stays true."""
    df = _day(_flat_then([24_050 + 10 * i for i in range(30)]))
    sig = generate_signals(df)
    assert (sig == 1).sum() == 1, "a sustained break is ONE event"


def test_price_re_crossing_the_level_does_not_re_trigger():
    """Whipsaw around the level must not produce a second long event."""
    df = _day(_flat_then([24_050, 23_990, 24_055, 23_995, 24_060]))
    sig = generate_signals(df)
    assert (sig == 1).sum() == 1


def test_a_genuine_opposite_break_is_still_allowed():
    """Churn suppression must not swallow a real direction change — that
    is a different event, not a repeat of the same one."""
    df = _day(_flat_then([24_050, 24_060, 23_940, 23_930, 23_920]))
    sig = generate_signals(df)
    assert (sig == 1).sum() == 1
    assert (sig == -1).sum() == 1
    assert sig[sig == 1].index[0] < sig[sig == -1].index[0]


def test_each_session_gets_its_own_range_and_its_own_events():
    d1 = _day(_flat_then([24_050, 24_060, 24_070]), date="2026-03-02")
    d2 = _day(_flat_then([24_050, 24_060, 24_070], base=24_000.0), date="2026-03-03")
    sig = generate_signals(pd.concat([d1, d2]))
    per_day = sig[sig != 0].groupby(sig[sig != 0].index.normalize()).count()
    assert list(per_day) == [1, 1], "one event per session, not carried across"


# ─────────────────────────────────────────────────────────────────────
# Live/backtest semantic identity — no forming-bar, no look-ahead
# ─────────────────────────────────────────────────────────────────────

def test_signal_is_emitted_on_the_bar_after_the_confirming_close():
    """Live, `main.py` reads `signals.iloc[-1]` on the bar still forming.
    A rule keyed to the CURRENT bar's close therefore means something
    different live than in a backtest. The signal must sit on the bar
    AFTER the bar that closed beyond the level."""
    closes = _flat_then([24_050, 24_060, 24_070])
    df = _day(closes)
    sig = generate_signals(df)

    breaking_bar = RANGE_BARS          # first bar closing above the range
    assert sig.iloc[breaking_bar] == 0, "must not act on the bar still forming"
    assert sig.iloc[breaking_bar + 1] == 1, "acts on the next bar"


def test_signals_do_not_depend_on_future_bars():
    """Truncating the future must not change any already-emitted signal —
    the definition of no look-ahead."""
    df = _day(_flat_then([24_050, 23_980, 24_100, 23_900, 24_200, 23_800]))
    full = generate_signals(df)
    for cut in range(RANGE_BARS + 2, len(df)):
        prefix = generate_signals(df.iloc[:cut])
        pd.testing.assert_series_equal(
            prefix, full.iloc[:cut], check_names=False,
            obj=f"signals changed when truncated at bar {cut}",
        )


# ─────────────────────────────────────────────────────────────────────
# Contract, robustness, and the silent-zero-signal class of failure
# ─────────────────────────────────────────────────────────────────────

def test_signal_contract_matches_what_the_registry_and_main_expect():
    df = _day(_flat_then([24_050, 24_060]))
    sig = generate_signals(df)
    assert isinstance(sig, pd.Series)
    assert sig.dtype == int
    assert set(sig.unique()) <= {-1, 0, 1}
    assert sig.index.equals(df.index)


def test_strategy_is_autodiscovered_by_the_registry():
    """If the registry cannot see it, `main.py` cannot run it."""
    from trading_bot.strategies.registry import registry

    assert STRATEGY_NAME in registry.registered_strategies
    result = registry.run_strategy(STRATEGY_NAME, _day(_flat_then([24_050, 24_060])))
    signals = result[0] if isinstance(result, tuple) else result
    assert isinstance(signals, pd.Series)


def test_opening_range_is_defined_in_minutes_not_bars():
    """The same 30-minute idea on a 15-minute feed must use 2 bars, not 6
    — otherwise the strategy silently becomes a different one per feed."""
    closes_5m = _flat_then([24_050, 24_060, 24_070])
    sig_5m = generate_signals(_day(closes_5m, freq="5min"))

    closes_15m = list(np.full(2, 24_000.0)) + [24_050, 24_060, 24_070]
    sig_15m = generate_signals(_day(closes_15m, freq="15min"))

    assert (sig_5m == 1).sum() == 1
    assert (sig_15m == 1).sum() == 1


@pytest.mark.parametrize("n_bars", [0, 1, RANGE_BARS, RANGE_BARS + 1])
def test_degenerate_inputs_return_a_valid_empty_signal_series(n_bars):
    """Too little data must yield no signal — never an exception, and
    never a signal built from an incomplete range."""
    df = _day(list(np.full(n_bars, 24_000.0))) if n_bars else _day([])
    sig = generate_signals(df)
    assert len(sig) == n_bars
    assert (sig == 0).all()


def test_missing_ohlc_columns_raise_rather_than_silently_emitting_nothing():
    """A silent zero-signal condition is this project's most repeated
    production failure. A malformed frame must fail loudly."""
    df = _day(_flat_then([24_050, 24_060])).drop(columns=["high"])
    with pytest.raises(KeyError):
        generate_signals(df)


def test_research_risk_tier_does_not_leak_into_production_defaults():
    """The 1% research tier must be opt-in. A harness that silently
    re-tiered every strategy would invalidate every published result."""
    import inspect

    from shared.risk import RiskConfig
    from validation_harness import harness
    from validation_harness.research_config import BASE_RISK_TIER

    default = inspect.signature(harness.run_strategy_backtest).parameters["risk_config"].default
    assert default is None, "risk_config must default to None (RiskManager's own defaults)"

    stock = RiskConfig()
    assert stock.risk_per_trade == 0.01
    assert stock.high_confidence_risk_per_trade == 0.035, (
        "production default tier changed — every prior result assumed 3.5%"
    )
    # The research tier pins BOTH, so the confidence override cannot fire.
    assert BASE_RISK_TIER.risk_per_trade == 0.01
    assert BASE_RISK_TIER.high_confidence_risk_per_trade == 0.01


def test_research_split_does_not_overlap_and_oos_is_the_established_window():
    """The whole programme's honesty rests on these two ranges being
    disjoint, and on OOS being the window every prior result used."""
    from validation_harness.research_config import DEV_END, DEV_START, OOS_END, OOS_START

    assert DEV_START < DEV_END < OOS_START < OOS_END
    assert (OOS_START, OOS_END) == ("2026-02-01", "2026-07-31")


def test_research_config_is_not_imported_by_production_code():
    """`research_config` may be read by research runners only. If
    `trading_bot/` ever imports it, experimental settings have entered the
    live path."""
    import pathlib

    root = pathlib.Path(_bootstrap.TRADING_SYSTEM_ROOT)
    offenders = [
        p.relative_to(root).as_posix()
        for p in (root / "trading_bot").rglob("*.py")
        if "research_config" in p.read_text(encoding="utf-8", errors="ignore")
    ]
    assert not offenders, f"production code imports research_config: {offenders}"


def test_strategy_declares_no_institutional_filter_ownership():
    """It consumes no `enable_*_filter` key, so the registry's global
    filters must apply to it normally. Declaring ownership by accident
    would silently disable a control the operator enabled."""
    from trading_bot.strategies import structure_break

    assert not hasattr(structure_break, "OWNS_INSTITUTIONAL_FILTERS")
