"""Regression tests for api_bridge.py's option-history derivation path:
generate_option_history_from_spot() and load_csv_history().

Completes the options-chain feature. The most important property under
test here isn't the exact Black-Scholes numbers (those are a documented
approximation - see generate_option_history_from_spot's own docstring)
but two real bugs found and fixed while completing this feature:

1. load_csv_history's fallback list used to include the NIFTY/SENSEX/
   BANKNIFTY cache files unconditionally, so a broker failure for any
   OTHER symbol would silently return a different index's candles
   mislabeled as the requested symbol's history.
2. Different cached CSVs use different casing for the datetime column
   (lowercase "datetime" vs "Datetime"), which broke the RELIANCE
   fallback specifically until columns were normalized to lowercase.
"""
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from api_bridge import generate_option_history_from_spot, load_csv_history


def _synthetic_spot(n=10, base=24000.0):
    candles = []
    price = base
    for i in range(n):
        o = price
        h = price + 20
        l = price - 20
        c = price + 5
        candles.append({"datetime": f"2026-08-0{i+1} 09:15:00", "open": o, "high": h, "low": l, "close": c, "volume": 100000})
        price = c
    return candles


def test_call_option_ohlc_invariants_hold():
    spot = _synthetic_spot()
    result = generate_option_history_from_spot(spot, strike=24000.0, opt_type="CE")
    assert len(result) == len(spot)
    for candle in result:
        assert candle["high"] >= candle["open"] >= candle["low"]
        assert candle["high"] >= candle["close"] >= candle["low"]
        assert candle["low"] > 0  # option price floor (0.05) must never go non-positive


def test_put_option_ohlc_invariants_hold():
    spot = _synthetic_spot()
    result = generate_option_history_from_spot(spot, strike=24000.0, opt_type="PE")
    assert len(result) == len(spot)
    for candle in result:
        assert candle["high"] >= candle["open"] >= candle["low"]
        assert candle["high"] >= candle["close"] >= candle["low"]


def test_deep_itm_call_worth_more_than_deep_otm_call():
    spot = _synthetic_spot(base=24000.0)
    itm = generate_option_history_from_spot(spot, strike=20000.0, opt_type="CE")  # deep ITM call
    otm = generate_option_history_from_spot(spot, strike=28000.0, opt_type="CE")  # deep OTM call
    assert itm[0]["close"] > otm[0]["close"]


def test_deep_itm_put_worth_more_than_deep_otm_put():
    spot = _synthetic_spot(base=24000.0)
    itm_put = generate_option_history_from_spot(spot, strike=28000.0, opt_type="PE")  # deep ITM put
    otm_put = generate_option_history_from_spot(spot, strike=20000.0, opt_type="PE")  # deep OTM put
    assert itm_put[0]["close"] > otm_put[0]["close"]


def test_empty_spot_data_returns_empty():
    assert generate_option_history_from_spot([], strike=24000.0, opt_type="CE") == []


def test_load_csv_history_reliance_returns_reliance_data_not_nifty():
    result = load_csv_history("RELIANCE", "2026-05-04", "2026-05-05", "5 Min")
    assert len(result) > 0
    # RELIANCE trades in the hundreds/low-thousands; NIFTY trades above 20000 -- if
    # this ever silently falls back to NIFTY's cache again, this assertion catches it.
    assert all(c["close"] < 5000 for c in result[:20])
    assert "open" in result[0] and "close" in result[0]


def test_load_csv_history_nifty_returns_nifty_data():
    result = load_csv_history("NSE:NIFTY50-INDEX", "2026-05-04", "2026-05-05", "5 Min")
    assert len(result) > 0
    assert all(c["close"] > 15000 for c in result[:20])


def test_load_csv_history_unknown_symbol_returns_empty_not_wrong_data():
    result = load_csv_history("SOMESTOCKWITHNOCACHE", "2026-05-04", "2026-05-05", "5 Min")
    assert result == []


def test_load_csv_history_bank_nifty_does_not_match_plain_nifty_branch():
    # "NIFTYBANK"/"BANKNIFTY" must be checked before the generic "NIFTY"
    # substring branch, or bank nifty requests would incorrectly fall
    # into the NIFTY50 cache instead of the bank nifty one.
    result = load_csv_history("NSE:NIFTYBANK-INDEX", "2026-05-04", "2026-05-05", "5 Min")
    assert len(result) > 0
    assert all(c["close"] > 40000 for c in result[:20])  # bank nifty trades much higher than NIFTY50
