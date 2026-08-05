"""Regression test for the live engine's historical-preload failure alert
(trading_bot/main.py's _build_preload_failure_alert).

Root-cause fix (Low audit finding): the historical-data preload loop in
run_live_bot() used to be wrapped in one broad `try/except Exception`
around the entire per-symbol loop -- any single symbol's failure
silently aborted preload for every symbol still left in the list, with
only a `logger.warning()` call and no operator-facing alert. The engine
now isolates each symbol's preload in its own try/except and, if any
symbols end up with an empty candle buffer, builds an operator alert
via this pure function (pulled out specifically so it's testable
without a live broker connection) and sends it through the existing
`alerter`/`audit` channels.
"""
import sys
from pathlib import Path

import _bootstrap  # noqa: F401  (side-effect: puts trading-system/ on sys.path)

from trading_bot.main import _build_preload_failure_alert


def test_alert_lists_all_failed_symbols():
    msg = _build_preload_failure_alert(["NIFTY", "BANKNIFTY"])
    assert "NIFTY" in msg
    assert "BANKNIFTY" in msg


def test_alert_mentions_empty_buffer_and_warmup():
    msg = _build_preload_failure_alert(["NIFTY"])
    assert "empty candle buffer" in msg
    assert "warmup" in msg


def test_alert_single_symbol_no_trailing_comma():
    msg = _build_preload_failure_alert(["NIFTY"])
    assert "NIFTY," not in msg


if __name__ == "__main__":
    test_alert_lists_all_failed_symbols()
    test_alert_mentions_empty_buffer_and_warmup()
    test_alert_single_symbol_no_trailing_comma()
    print("All preload-failure-alert tests passed.")
