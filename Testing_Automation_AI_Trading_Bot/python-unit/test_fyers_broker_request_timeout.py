"""brokers/fyers_broker.py -- default request timeout on the Fyers session.

Root cause (found live, 2026-08-13): the vendored fyers_apiv3 SDK's
FyersModel.get_call() makes `self.session.get(...)` with no `timeout=`
anywhere. A DNS resolution failure fails fast, but a hung TCP connect --
a plausible state mid-network-recovery -- could block that call
indefinitely. trading_bot/main.py calls broker.get_market_data()
synchronously and unwrapped directly on its asyncio event loop; a single
hung call there is the confirmed root cause of a ~39-minute total engine
freeze (14:18-14:57 IST), correlated with an 11-entry DNS failure burst
in the same window.

_TimeoutHTTPAdapter/_mount_default_timeout close this at the network
boundary, without editing the vendored SDK. These tests exercise the
adapter and the mount helper directly -- no real network calls.
"""
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
import requests

import _bootstrap  # noqa: F401  (side-effect: puts trading-system/ on sys.path)

from brokers.fyers_broker import (
    FyersBroker,
    _DEFAULT_REQUEST_TIMEOUT_S,
    _TimeoutHTTPAdapter,
    _mount_default_timeout,
)


def test_adapter_injects_default_timeout_when_caller_specifies_none(monkeypatch):
    adapter = _TimeoutHTTPAdapter(timeout=7)
    captured = {}

    def _fake_super_send(self, request, **kwargs):
        captured.update(kwargs)
        return "response"

    monkeypatch.setattr(requests.adapters.HTTPAdapter, "send", _fake_super_send)

    result = adapter.send(MagicMock())

    assert result == "response"
    assert captured["timeout"] == 7


def test_adapter_does_not_override_an_explicit_timeout(monkeypatch):
    adapter = _TimeoutHTTPAdapter(timeout=7)
    captured = {}

    def _fake_super_send(self, request, **kwargs):
        captured.update(kwargs)
        return "response"

    monkeypatch.setattr(requests.adapters.HTTPAdapter, "send", _fake_super_send)

    adapter.send(MagicMock(), timeout=2)

    assert captured["timeout"] == 2


def test_adapter_treats_explicit_zero_timeout_as_caller_intent(monkeypatch):
    """timeout=0 is falsy but not None -- must not be silently replaced."""
    adapter = _TimeoutHTTPAdapter(timeout=7)
    captured = {}

    def _fake_super_send(self, request, **kwargs):
        captured.update(kwargs)
        return "response"

    monkeypatch.setattr(requests.adapters.HTTPAdapter, "send", _fake_super_send)

    adapter.send(MagicMock(), timeout=0)

    assert captured["timeout"] == 0


def test_mount_default_timeout_installs_adapter_on_both_schemes():
    session = requests.Session()

    _mount_default_timeout(SimpleNamespace(session=session))

    assert isinstance(session.adapters["https://"], _TimeoutHTTPAdapter)
    assert isinstance(session.adapters["http://"], _TimeoutHTTPAdapter)
    assert session.adapters["https://"]._timeout == _DEFAULT_REQUEST_TIMEOUT_S


def test_mount_default_timeout_is_a_noop_without_a_real_session():
    """A stub/mock model with no requests.Session must not raise."""
    class _NoSessionModel:
        pass

    _mount_default_timeout(_NoSessionModel())  # must not raise


def test_authenticate_paper_mode_mounts_the_timeout_adapter(monkeypatch):
    """End-to-end: authenticate() in paper mode with a cached token builds
    a real FyersModel and must come out with the timeout adapter mounted."""
    broker = FyersBroker(credentials={"client_id": "FAKE-100"}, paper_mode=True)
    monkeypatch.setattr(broker, "_load_cached_token", lambda: "A-TOKEN")

    class _FakeFyersModel:
        def __init__(self, client_id, token, log_path):
            self.session = requests.Session()

    monkeypatch.setattr("fyers_apiv3.fyersModel.FyersModel", _FakeFyersModel)

    assert broker.authenticate() is True
    assert isinstance(broker._fyers_model.session.adapters["https://"], _TimeoutHTTPAdapter)


def test_refresh_fyers_model_mounts_the_timeout_adapter(monkeypatch):
    broker = FyersBroker(credentials={"client_id": "FAKE-100"}, paper_mode=False)
    monkeypatch.setattr(broker, "_load_cached_token", lambda: "A-TOKEN")

    class _FakeFyersModel:
        def __init__(self, client_id, token, log_path):
            self.session = requests.Session()

    monkeypatch.setattr("fyers_apiv3.fyersModel.FyersModel", _FakeFyersModel)

    assert broker._refresh_fyers_model() is True
    assert isinstance(broker._fyers_model.session.adapters["https://"], _TimeoutHTTPAdapter)
