"""api_bridge.py — upstream Fyers feed staleness tracking and the
`time`-shadowing bug found while adding it.

Two live incidents, both 2026-08-12, both in `start_fyers_socket()`:

1. The upstream Fyers WebSocket (fyers_apiv3's `data_ws.FyersDataSocket`,
   `reconnect=True`) went silently zombie for 46 minutes during real market
   hours. Root cause: its keepalive ping is fire-and-forget (see
   `data_ws.py`'s `__ping`) with no pong check, so it never noticed. Fixed
   by tracking `_last_fyers_message_at` in `on_message` and polling
   `shared.risk.tick_staleness.should_rebuild_stale_feed` from a new
   watchdog task (see `test_tick_staleness.py` for that pure-function
   coverage).

2. Deploying fix #1 immediately broke on the very first real message:
   `NameError: cannot access free variable 'time'`. A stray `import time`
   inside this same function's dead yfinance-fallback branch (only reached
   when there's no cached Fyers token) made `time` a local name of the
   WHOLE enclosing `start_fyers_socket()` -- Python decides a name is
   local to a function from any assignment/import anywhere in its body,
   regardless of which branch runs. Every nested closure defined below
   that branch (`on_message`, `on_error`, ...) inherited `time` as an
   unbound free variable the instant any of them tried to use the
   module-level `time`, only raised at call time -- invisible until a real
   message arrived and `on_message` actually ran, exactly like the
   original bug it was fixing.

This test exercises the REAL `on_message` closure (not a reimplementation)
via a stub `FyersDataSocket`, so a regression of either bug fails it.
"""
import time

import _bootstrap  # noqa: F401  (side-effect: puts trading-system/ on sys.path)

import api_bridge


class _StubFyersDataSocket:
    """Captures the callbacks api_bridge wires up, without any real I/O."""

    def __init__(self, **kwargs):
        self.on_message = kwargs["on_message"]
        self.on_error = kwargs["on_error"]
        self.closed = False

    def connect(self):
        pass  # real library would open the socket and eventually call on_connect

    def close_connection(self):
        self.closed = True


def test_on_message_updates_last_message_at_with_no_time_shadowing(monkeypatch):
    monkeypatch.setattr("brokers.token_cache.load_token", lambda name: "fake-token")
    monkeypatch.setattr(api_bridge, "_get_fyers_client_id", lambda: "FAKE-CLIENT-ID")
    monkeypatch.setattr(api_bridge.data_ws, "FyersDataSocket", _StubFyersDataSocket)
    api_bridge._last_fyers_message_at = 0.0

    api_bridge.start_fyers_socket()
    assert isinstance(api_bridge.fyers_socket_instance, _StubFyersDataSocket)

    errors = []
    # Route the real on_error callback's exceptions here instead of just
    # logging them, so a shadowing regression fails loudly instead of
    # silently vanishing into a logger.error() call like it did live.
    real_on_error = api_bridge.fyers_socket_instance.on_error
    api_bridge.fyers_socket_instance.on_error = lambda msg: errors.append(msg) or real_on_error(msg)

    before = time.time()
    api_bridge.fyers_socket_instance.on_message({"symbol": "NSE:NIFTY50-INDEX", "ltp": 100.0})
    after = time.time()

    assert errors == []
    assert before <= api_bridge._last_fyers_message_at <= after
    assert api_bridge.current_market_data["NSE:NIFTY50-INDEX"]["lp"] == 100.0


def test_on_message_updates_the_timestamp_even_for_a_message_with_no_symbol(monkeypatch):
    """Any message proves the socket is alive -- the timestamp must not be
    gated on the tick actually carrying a priced symbol."""
    monkeypatch.setattr("brokers.token_cache.load_token", lambda name: "fake-token")
    monkeypatch.setattr(api_bridge, "_get_fyers_client_id", lambda: "FAKE-CLIENT-ID")
    monkeypatch.setattr(api_bridge.data_ws, "FyersDataSocket", _StubFyersDataSocket)
    api_bridge._last_fyers_message_at = 0.0

    api_bridge.start_fyers_socket()
    api_bridge.fyers_socket_instance.on_message({"type": "auth_ack"})

    assert api_bridge._last_fyers_message_at > 0.0
