"""Which indices trading_bot/main.py trades, by mode (owner's rule, 2026-09-11):
paper tests NIFTY, BANKNIFTY and SENSEX; live trades only the UI selection."""
from shared.instruments import resolve_engine_symbols

PAPER_SET = ["NSE:NIFTY50-INDEX", "NSE:NIFTYBANK-INDEX", "BSE:SENSEX-INDEX"]


def test_paper_tests_the_three_indices_whatever_the_ui_selection():
    """2026-10-14: settings had symbols=[NIFTY] and live_trading_mode False;
    the paper session ran NIFTY only."""
    settings = {"live_trading_mode": False, "symbols": ["NSE:NIFTY50-INDEX"]}
    assert resolve_engine_symbols(settings) == PAPER_SET


def test_paper_is_the_default_when_the_mode_is_missing():
    assert resolve_engine_symbols({"symbols": ["NSE:NIFTY50-INDEX"]}) == PAPER_SET


def test_paper_honours_the_paper_test_instruments_override():
    settings = {"live_trading_mode": False, "paper_test_instruments": ["NIFTY", "SENSEX"]}
    assert resolve_engine_symbols(settings) == ["NSE:NIFTY50-INDEX", "BSE:SENSEX-INDEX"]


def test_live_trades_only_the_ui_selection():
    settings = {"live_trading_mode": True, "symbols": ["NSE:NIFTY50-INDEX"],
                "paper_test_instruments": ["NIFTY", "BANKNIFTY", "SENSEX"]}
    assert resolve_engine_symbols(settings) == ["NSE:NIFTY50-INDEX"]


def test_live_with_no_selection_trades_nothing():
    assert resolve_engine_symbols({"live_trading_mode": True}) == []
