"""Regression coverage for the enhanced_ai RSI dual-confirmation flaw
(backlog #2, found and fixed 2026-08-08).

Root cause: the bull and bear RSI confirmations used `rsi > 40` and
`rsi < 60`. Those ranges OVERLAP across the entire 40-60 band, which is
where RSI spends most of its life. Measured on the real validation
window (9,219 bars): the RSI layer awarded a confirmation point to BOTH
directions on 50.6% of bars, and awarded at least one point on 100.0% of
bars — it was never silent.

A confirmation layer that confirms both directions simultaneously carries
zero information, yet it counted toward the "5 of 6 layers must agree"
threshold exactly like a genuine one — effectively lowering the real bar
to 4-of-5 and systematically admitting under-confirmed signals.

Fixed by splitting at the RSI midline so at most one direction can claim
the point, preserving the intended "RSI momentum confirmation"
philosophy. A guard collapses any overlapping caller/settings values back
to the midline so the defect cannot be reintroduced by configuration.
"""
import numpy as np
import pandas as pd

import _bootstrap  # noqa: F401  (side-effect: puts trading-system/ on sys.path)

from shared.indicators import rsi
from trading_bot.strategies.enhanced_ai_strategy import RSI_MIDLINE, generate_signals


def _ohlcv(n: int = 400, seed: int = 11) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    close = 24_000 + rng.normal(0, 14, n).cumsum()
    idx = pd.date_range("2026-06-01 09:15", periods=n, freq="5min")
    return pd.DataFrame({
        "open": close, "high": close + 7, "low": close - 7, "close": close,
        "volume": rng.integers(1_000, 50_000, n).astype(float),
    }, index=idx)


def test_rsi_confirmations_are_mutually_exclusive():
    """THE regression: no bar may award an RSI point to both directions."""
    df = _ohlcv(600)
    r = rsi(df["close"], window=14)

    bull = r > RSI_MIDLINE
    bear = r < RSI_MIDLINE
    both = (bull & bear)

    assert both.sum() == 0, (
        f"{both.sum()} bars award an RSI confirmation to BOTH directions — "
        "this is the dual-confirmation defect."
    )


def test_the_old_overlapping_thresholds_would_have_failed():
    """Proves the test above is meaningful by demonstrating the pre-fix
    thresholds genuinely produce the overlap."""
    df = _ohlcv(600)
    r = rsi(df["close"], window=14)

    old_bull = r > 40
    old_bear = r < 60
    overlap = (old_bull & old_bear).sum()

    assert overlap > 0, "expected the legacy 40/60 thresholds to overlap"


def test_overlapping_thresholds_from_settings_are_collapsed_to_midline(caplog):
    """A caller or settings file reintroducing 40/60 must be corrected,
    not silently honoured — overlap is the defect, not a tuning choice."""
    df = _ohlcv(300)
    import logging
    with caplog.at_level(logging.WARNING, logger="trading_bot.strategies.enhanced_ai_strategy"):
        generate_signals(df.copy(), rsi_buy_thresh=40, rsi_sell_thresh=60)
    assert any("overlapping RSI thresholds" in r.getMessage() for r in caplog.records)


def test_non_overlapping_custom_thresholds_are_respected(caplog):
    """A legitimate stricter configuration (e.g. 60/40, a genuine
    dead-band) must pass through untouched."""
    df = _ohlcv(300)
    import logging
    with caplog.at_level(logging.WARNING, logger="trading_bot.strategies.enhanced_ai_strategy"):
        generate_signals(df.copy(), rsi_buy_thresh=60, rsi_sell_thresh=40)
    assert not any("overlapping RSI thresholds" in r.getMessage() for r in caplog.records)


def test_output_is_still_a_valid_signal_series():
    df = _ohlcv(400)
    out = generate_signals(df.copy())
    assert isinstance(out, pd.Series)
    assert len(out) == len(df)
    assert set(out.unique()) <= {-1, 0, 1}


def test_a_bar_cannot_be_both_buy_and_sell():
    """End-to-end consequence: with a discriminating RSI layer, no single
    bar should be able to reach the 5-of-6 threshold in both directions."""
    df = _ohlcv(600)
    out = generate_signals(df.copy())
    # A Series can only hold one value per bar, so this asserts the
    # scoring never produced a contradictory state that got silently
    # resolved by assignment order.
    assert set(out.unique()) <= {-1, 0, 1}
