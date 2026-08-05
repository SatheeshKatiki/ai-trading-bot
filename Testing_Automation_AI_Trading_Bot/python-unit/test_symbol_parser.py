"""Regression tests for shared/security/symbol_parser.py's parse_option_symbol().

Completes the options-chain feature's test coverage — this parser
determines whether /api/history routes a request through the real
broker/equity path or the Black-Scholes option-derivation path, so a
false negative/positive here silently changes what data a user sees.
"""
import sys
from pathlib import Path

import _bootstrap  # noqa: F401  (side-effect: puts trading-system/ on sys.path)

from shared.security.symbol_parser import parse_option_symbol


def test_human_readable_format_with_spaces():
    r = parse_option_symbol("NIFTY 24350 CE")
    assert r == {"is_option": True, "underlying": "NIFTY", "strike": 24350.0, "opt_type": "CE", "raw": "NIFTY 24350 CE"}


def test_human_readable_put_with_call_put_words():
    r = parse_option_symbol("BANKNIFTY 52000 PUT")
    assert r["is_option"] is True
    assert r["underlying"] == "BANKNIFTY"
    assert r["strike"] == 52000.0
    assert r["opt_type"] == "PE"

    r2 = parse_option_symbol("NIFTY 24350 CALL")
    assert r2["opt_type"] == "CE"


def test_compact_format_no_spaces():
    r = parse_option_symbol("NIFTY24350CE")
    assert r["is_option"] is True
    assert r["underlying"] == "NIFTY"
    assert r["strike"] == 24350.0
    assert r["opt_type"] == "CE"


def test_broker_exchange_format_with_expiry_embedded():
    r = parse_option_symbol("NSE:NIFTY26AUG24350CE")
    assert r["is_option"] is True
    assert r["underlying"] == "NIFTY"
    assert r["strike"] == 24350.0
    assert r["opt_type"] == "CE"


def test_lowercase_input_is_normalized():
    r = parse_option_symbol("nifty 24350 ce")
    assert r["is_option"] is True
    assert r["underlying"] == "NIFTY"


def test_plain_equity_symbol_is_not_an_option():
    r = parse_option_symbol("RELIANCE")
    assert r["is_option"] is False

    r2 = parse_option_symbol("NSE:NIFTY50-INDEX")
    assert r2["is_option"] is False


def test_empty_and_none_input_handled_safely():
    assert parse_option_symbol("")["is_option"] is False
    assert parse_option_symbol(None)["is_option"] is False


def test_unrecognized_underlying_is_not_an_option():
    # Not in the recognized underlying whitelist -- must not be
    # misparsed as an option just because it ends in digits+CE/PE-like text.
    r = parse_option_symbol("SOMERANDOMSTOCK 100 CE")
    assert r["is_option"] is False
