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


def _dashboard() -> str:
    root = pathlib.Path(_bootstrap.TRADING_SYSTEM_ROOT).parent
    return (root / "frontend" / "app" / "page.tsx").read_text(
        encoding="utf-8", errors="ignore")


def _store() -> str:
    root = pathlib.Path(_bootstrap.TRADING_SYSTEM_ROOT).parent
    return (root / "frontend" / "store" / "useLiveMarketStore.ts").read_text(
        encoding="utf-8", errors="ignore")


def test_a_stale_window_is_defined_and_sane():
    src = _store()
    match = re.search(r"export const WS_STALE_MS\s*=\s*(\d+)", src)
    assert match, "the staleness window must be one named constant in the store"
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


def test_there_is_one_definition_of_live_shared_by_both_pages():
    """Two copies of this rule would drift, and one page would freeze again."""
    assert "export function wsIsDelivering" in _store()
    assert "wsIsDelivering" in _live_page()
    assert "wsIsDelivering" in _dashboard()
    assert "const WS_STALE_MS" not in _live_page(), "no local copy of the window"


def test_the_dashboard_home_uses_it_for_its_ws_or_rest_choice():
    """It picked WS values on the flag alone, so it froze the same way."""
    src = _dashboard()
    assert "wsIsDelivering({ isWsConnected: wsIsUp, lastPingTime: wsLastPing })" in src
    assert "const wsConnected = useLiveMarketStore(state => state.isWsConnected);" not in src


def test_the_risk_card_has_a_real_source():
    """It read ACTIVE forever: the store initialised it and nothing wrote it."""
    api = pathlib.Path(_bootstrap.TRADING_SYSTEM_ROOT, "api_bridge.py").read_text(
        encoding="utf-8", errors="ignore")
    assert '"risk_status"' in api
    for state in ("HALTED", "IDLE", "ACTIVE", "UNKNOWN"):
        assert state in api
    assert "data.risk_status" in _store(), "and the store must read it"


def test_an_unreadable_risk_state_is_not_reported_as_fine():
    api = pathlib.Path(_bootstrap.TRADING_SYSTEM_ROOT, "api_bridge.py").read_text(
        encoding="utf-8", errors="ignore")
    start = api.index('websocket_data["risk_status"] = "HALTED"')
    block = api[max(0, start - 600):start + 900]
    assert 'websocket_data["risk_status"] = "UNKNOWN"' in block
    assert "except Exception" in block


def test_an_emergency_stop_is_what_makes_it_halt():
    api = pathlib.Path(_bootstrap.TRADING_SYSTEM_ROOT, "api_bridge.py").read_text(
        encoding="utf-8", errors="ignore")
    start = api.index('websocket_data["risk_status"] = "HALTED"')
    assert 'emergency_stop' in api[max(0, start - 300):start]
