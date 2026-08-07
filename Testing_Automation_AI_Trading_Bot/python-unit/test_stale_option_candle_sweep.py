"""Unit tests for trading_bot.main._stale_option_candle_symbols -- prevents
the option-premium candle aggregator from growing unboundedly over a
long-running process (2026-08-07 audit §2.1 fix, option-premium ATR
architecture).
"""
import _bootstrap  # noqa: F401  (side-effect: puts trading-system/ on sys.path)

from trading_bot.main import _stale_option_candle_symbols


def test_option_symbol_with_no_open_position_is_evicted():
    tracked = ["NSE:NIFTY2681126950PE"]
    open_syms = []
    assert _stale_option_candle_symbols(tracked, open_syms) == ["NSE:NIFTY2681126950PE"]


def test_option_symbol_with_an_open_position_is_kept():
    tracked = ["NSE:NIFTY2681126950PE"]
    open_syms = ["NSE:NIFTY2681126950PE"]
    assert _stale_option_candle_symbols(tracked, open_syms) == []


def test_index_symbols_are_never_evicted_even_when_flat():
    """The underlying index symbols must keep accumulating candles for
    strategy signal generation regardless of whether any position is
    open -- only option contracts are position-scoped."""
    tracked = ["NSE:NIFTY50-INDEX", "NSE:NIFTYBANK-INDEX", "BSE:SENSEX-INDEX"]
    assert _stale_option_candle_symbols(tracked, []) == []


def test_mixed_tracked_symbols_only_evicts_orphaned_options():
    tracked = [
        "NSE:NIFTY50-INDEX",
        "NSE:NIFTY2681126950PE",   # open position -- keep
        "NSE:NIFTY2681124500CE",   # closed, orphaned -- evict
    ]
    open_syms = ["NSE:NIFTY2681126950PE"]
    result = _stale_option_candle_symbols(tracked, open_syms)
    assert result == ["NSE:NIFTY2681124500CE"]


def test_empty_tracked_symbols_returns_empty():
    assert _stale_option_candle_symbols([], ["NSE:NIFTY2681126950PE"]) == []


def test_multiple_closed_contracts_all_evicted():
    tracked = ["NSE:NIFTY2681126950PE", "NSE:NIFTY2681124500CE", "NSE:NIFTY2681158100PE"]
    result = _stale_option_candle_symbols(tracked, [])
    assert set(result) == set(tracked)
