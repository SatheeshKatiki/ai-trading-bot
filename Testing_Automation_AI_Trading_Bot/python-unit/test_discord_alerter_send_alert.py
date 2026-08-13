"""Regression test for shared/alerts/discord_alerter.py's Alerter.send_alert.

Root cause (found live, 2026-08-13): trading_bot/main.py already called
`alerter.send_alert(...)` in 3 places (a preload-failure notice, two
sentiment-blocked-trade notices), but the `Alerter` class in this module
only ever defined `send_trade_alert`/`send_exit_alert` -- `send_alert`
didn't exist at all, only on the sibling `shared/alerts/telegram.py`
Alerter. Every one of those 3 call sites would have raised AttributeError
the instant any of them actually fired. None had, so nothing caught it --
the existing test_preload_failure_alert.py only ever tested the message
string builder, never the actual dispatch call, which is exactly why this
went unnoticed. Found while wiring api_bridge.py's main_process_watchdog
to use this same method for freeze/duplicate-launch alerts.

These tests mock urllib.request.urlopen (no real network calls) and
assert on the dispatched payload, following this module's existing
threading-based fire-and-forget design (send_alert must return
immediately; the actual POST happens on a background thread).
"""
import json
import threading
import time
from unittest.mock import MagicMock, patch

import _bootstrap  # noqa: F401  (side-effect: puts trading-system/ on sys.path)

from shared.alerts.discord_alerter import Alerter, alerter


def test_alerter_singleton_has_a_working_send_alert_method():
    """The actual regression: this must not raise AttributeError."""
    assert hasattr(alerter, "send_alert")
    assert callable(alerter.send_alert)


def test_send_alert_returns_immediately_and_posts_on_a_background_thread():
    posted = threading.Event()
    captured = {}

    def _fake_urlopen(req, timeout=None):
        captured["url"] = req.full_url
        captured["body"] = json.loads(req.data.decode("utf-8"))
        posted.set()
        return MagicMock(getcode=lambda: 204, __enter__=lambda s: s, __exit__=lambda *a: None)

    with patch("urllib.request.urlopen", side_effect=_fake_urlopen):
        a = Alerter()
        start = time.monotonic()
        a.send_alert("MAIN.PY FROZEN -- attempting automatic restart")
        elapsed = time.monotonic() - start

        assert posted.wait(timeout=2.0), "background thread never posted"

    assert elapsed < 0.5, "send_alert must return immediately, not block on the network call"
    assert captured["body"]["content"] == "MAIN.PY FROZEN -- attempting automatic restart"


def test_send_alert_is_a_noop_when_no_webhook_configured():
    with patch("shared.alerts.discord_alerter.DISCORD_WEBHOOK_URL", ""):
        with patch("threading.Thread") as mock_thread:
            Alerter().send_alert("should not be sent")
            mock_thread.assert_not_called()


def test_send_alert_swallows_a_network_failure_without_raising():
    """A failed webhook POST must never propagate back to the caller --
    the caller (e.g. the watchdog mid-freeze-recovery) must not itself
    crash because Discord was unreachable."""
    def _raise(*args, **kwargs):
        raise OSError("network unreachable")

    with patch("urllib.request.urlopen", side_effect=_raise):
        a = Alerter()
        a.send_alert("test message")
        # Give the background thread a moment to run and swallow the
        # exception; the test passes as long as this doesn't raise here.
        time.sleep(0.2)
