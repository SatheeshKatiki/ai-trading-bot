"""shared/instruments.py — canonical instrument-key normalization.

This is the single source of truth that replaced two independently-drifting
inline copies in trading_bot/main.py. One of those copies had already gone
stale: the "premium" strategy branch never stripped a "BSE:" prefix, so a
SENSEX signal through that path built the key "BSE:SENSEX" instead of
"SENSEX", silently failing to match options_selector.py's INSTRUMENT_CONFIG.
These tests pin the correct behavior for all four tradeable instruments plus
that specific regression.
"""
import _bootstrap  # noqa: F401  (side-effect: puts trading-system/ on sys.path)

import pytest

from shared.instruments import INDEX_INSTRUMENTS, normalize_instrument


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("NSE:NIFTY50-INDEX", "NIFTY"),
        ("NSE:NIFTYBANK-INDEX", "BANKNIFTY"),
        ("NSE:FINNIFTY-INDEX", "FINNIFTY"),
        ("BSE:SENSEX-INDEX", "SENSEX"),
        ("NSE:RELIANCE-EQ", "RELIANCE"),
    ],
)
def test_normalizes_real_broker_symbols(raw, expected):
    assert normalize_instrument(raw) == expected


def test_sensex_strips_bse_prefix():
    """The exact regression this module was extracted to fix: the
    premium-strategy branch used to skip the BSE: strip entirely."""
    assert normalize_instrument("BSE:SENSEX-INDEX") == "SENSEX"
    assert "BSE" not in normalize_instrument("BSE:SENSEX-INDEX")


def test_is_idempotent_on_already_canonical_keys():
    for instrument in INDEX_INSTRUMENTS:
        assert normalize_instrument(instrument) == instrument


def test_is_case_insensitive():
    assert normalize_instrument("nse:nifty50-index") == "NIFTY"
    assert normalize_instrument("bse:sensex-index") == "SENSEX"


def test_all_four_focus_instruments_are_covered():
    for instrument in ("NIFTY", "BANKNIFTY", "FINNIFTY", "SENSEX"):
        assert instrument in INDEX_INSTRUMENTS
