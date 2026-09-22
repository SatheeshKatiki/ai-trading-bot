"""The metric cards must not freeze when the socket goes quiet (2026-09-22).

Reported live, with the market open: Current Equity, Today's P&L, AI
Confidence and Today's Trades stopped moving and only changed on a page
reload. The backend was fine -- /api/state showed equity moving (98,013.75 ->
97,982.25 inside twelve seconds) and the WS broadcaster pushes every 500ms
with a 50ms trade-cache TTL.

The fault was in the fallback's condition. REST polling wrote equity, P&L and
the trade count only `if (!store.isWsConnected)`. That flag says whether a
socket object is open, not whether anything is arriving on it. When the
backend restarts, the browser is routinely left holding a HALF-OPEN socket:
no `onclose` fires for a long time, the flag stays true, nothing is
delivered, and the one code path that could have refreshed those numbers was
skipped. The cards then sat frozen until reload -- exactly the symptom.

The fix measures silence instead of trusting the flag: `lastPingTime` is
stamped on every WS message, so past WS_STALE_MS the socket is treated as
dead for data purposes, REST takes over at the fast interval, and a fresh
socket is requested.
"""

from __future__ import annotations

import pathlib
import re

import _bootstrap  # noqa: F401  (side-effect: puts trading-system/ on sys.path)


def _live_page() -> str:
    root = pathlib.Path(_bootstrap.TRADING_SYSTEM_ROOT).parent
    return (root / "frontend" / "app" / "live" / "page.tsx").read_text(
        encoding="utf-8", errors="ignore")


def _store() -> str:
    root = pathlib.Path(_bootstrap.TRADING_SYSTEM_ROOT).parent
    return (root / "frontend" / "store" / "useLiveMarketStore.ts").read_text(
        encoding="utf-8", errors="ignore")


def test_a_stale_window_is_defined_and_sane():
    src = _live_page()
    match = re.search(r"const WS_STALE_MS\s*=\s*(\d+)", src)
    assert match, "the staleness window must be a named constant"
    window = int(match.group(1))
    # The broadcaster pushes every 500ms: long enough not to flap on a slow
    # frame, short enough that a frozen card is never visible for long.
    assert 1000 <= window <= 10000


def test_polling_no_longer_trusts_the_connected_flag_alone():
    src = _live_page()
    assert "if (!store.isWsConnected) {" not in src, \
        "the flag alone was the bug -- a half-open socket kept it true"
    assert "wsDelivering" in src
    assert "lastPingTime" in src


def test_the_fallback_writes_the_metrics_the_cards_read():
    """equity, P&L and trades are what froze; they must be in the fallback."""
    src = _live_page()
    start = src.index("const wsDelivering")
    block = src[start:start + 1200]
    assert "setEquity" in block
    assert "setPnl" in block
    assert "setTrades" in block


def test_the_price_branch_uses_the_same_freshness_test():
    src = _live_page()
    assert "if (!wsDelivering || store.currentPrice === 0)" in src


def test_a_silent_socket_is_replaced_and_polled_fast():
    src = _live_page()
    start = src.index("} finally {")
    block = src[start:start + 900]
    assert "disconnectWs()" in block and "connectWs(" in block, \
        "a socket that has gone quiet must be replaced, not waited on"
    assert "delivering ? 5000 : 1500" in block, \
        "and until it is back, poll at the disconnected rate"


def test_every_ws_message_stamps_the_timestamp_the_fix_relies_on():
    store = _store()
    assert "setLastPingTime(Date.now())" in store
    assert "lastPingTime: number" in store


def test_the_metrics_the_cards_show_are_all_carried_by_the_socket():
    """If the socket carried fewer fields than the cards show, those fields
    would freeze whenever the socket WAS healthy."""
    store = _store()
    for field in ("data.equity", "data.pnl", "data.total_pnl",
                  "data.trades", "data.open_positions_count",
                  "data.signalsData"):
        assert field in store, f"{field} is shown on a card but never sent"


def test_the_broadcaster_refreshes_state_fast_enough_to_matter():
    api = pathlib.Path(_bootstrap.TRADING_SYSTEM_ROOT, "api_bridge.py").read_text(
        encoding="utf-8", errors="ignore")
    match = re.search(r"_WS_TRADE_CACHE_TTL:\s*float\s*=\s*([0-9.]+)", api)
    assert match, "the trade-cache TTL must stay explicit"
    assert float(match.group(1)) <= 0.5
