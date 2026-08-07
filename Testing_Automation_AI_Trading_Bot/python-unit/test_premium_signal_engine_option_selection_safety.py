"""Confirms the "premium" strategy entry path is safe against the same
class of bug fixed in the generic entry path (2026-08-07 audit §1.1,
"no abort on select_option() failure").

`PremiumSignal.option` can be `None` in its dataclass definition, and
`main.py`'s premium-strategy branch reads
`option_symbol = sig.option.symbol if sig.option else s` -- on its face,
the same "fall back to the raw index symbol" shape as the bug fixed in
the generic path. Investigated during the Fix #4 re-verification pass:
`select_option()`'s declared return type is `-> OptionContract` (never
`Optional`) -- it always either returns a real contract or raises.
`PremiumSignalEngine.evaluate()` calls it with NO try/except around it,
so a raise propagates straight out of `evaluate()` -- `sig` never gets
assigned in `main.py`, and `main.py`'s own outer
`except Exception as exc: logger.exception(...)` (wrapping the entire
tick's entry-evaluation block) absorbs it, aborting that tick's entry
attempt entirely. `option_symbol`'s `else s` fallback is therefore
defensive code for a case that cannot occur through this call path today
-- confirmed here directly rather than left as an assumption.
"""
from unittest.mock import patch

import pandas as pd

import _bootstrap  # noqa: F401  (side-effect: puts trading-system/ on sys.path)

from trading_bot.strategies.premium_selection.signal_engine import PremiumSignalEngine


def _passing_ohlcv(n: int = 210) -> pd.DataFrame:
    close = [100.0 + i * 0.1 for i in range(n)]
    return pd.DataFrame({
        "open": close, "high": [c + 0.5 for c in close],
        "low": [c - 0.5 for c in close], "close": close,
        "volume": [1000.0] * n,
    })


def _force_bullish_row(df: pd.DataFrame) -> pd.DataFrame:
    """Stamp every flag evaluate() reads on the last row so it reaches
    the select_option() call deterministically, without depending on
    the real filter math producing a bullish read on synthetic data."""
    df = df.copy()
    for col, val in {
        "no_trade": False, "in_no_trade_window": False, "is_sideways": False,
        "volatility_ok": True, "vol_expanding": True, "vol_ratio": 1.5,
        "trend_bullish": True, "trend_bearish": False,
        "momentum_bullish": True, "momentum_bearish": False,
        "structure_bullish": True, "structure_bearish": False,
    }.items():
        df.loc[df.index[-1], col] = val
    return df


def test_select_option_failure_propagates_rather_than_producing_a_none_option_signal():
    engine = PremiumSignalEngine(instrument="NIFTY", capital=100_000.0, min_ai_confidence=0.5)
    df = _passing_ohlcv()

    with patch(
        "trading_bot.strategies.premium_selection.signal_engine.compute_trend", lambda d: _force_bullish_row(d)
    ), patch(
        "trading_bot.strategies.premium_selection.signal_engine.compute_momentum", lambda d, **kw: d
    ), patch(
        "trading_bot.strategies.premium_selection.signal_engine.compute_volume", lambda d: d
    ), patch(
        "trading_bot.strategies.premium_selection.signal_engine.compute_volatility", lambda d: d
    ), patch(
        "trading_bot.strategies.premium_selection.signal_engine.compute_market_structure", lambda d: d
    ), patch(
        "trading_bot.strategies.premium_selection.signal_engine.compute_no_trade_conditions", lambda d: d
    ), patch(
        "trading_bot.strategies.premium_selection.signal_engine.select_option",
        side_effect=RuntimeError("no liquid contract found"),
    ):
        # The whole point of this test: evaluate() must NOT swallow the
        # error and return a PremiumSignal(option=None) -- it must raise,
        # so main.py's outer exception handler is the one that decides
        # what happens next (skip the tick), never a silent fallback to
        # the raw index symbol.
        try:
            engine.evaluate(df, ai_confidence=1.0)
            assert False, "expected select_option()'s RuntimeError to propagate"
        except RuntimeError as exc:
            assert "no liquid contract found" in str(exc)
