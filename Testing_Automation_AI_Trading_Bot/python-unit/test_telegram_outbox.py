"""A Telegram alert must survive a network outage (2026-09-16 / 09-18).

Every send was fire-and-forget: one HTML attempt, one plain-text fallback, and
on failure the message was gone. When the Wi-Fi dropped ~60 times and DNS was
failing, "Market is OPEN", the stand-down warning and the entire EOD report
were generated, logged as "queued", and never arrived — the owner learned the
session had died only by asking.

Alerts about money must not evaporate because a laptop's Wi-Fi blinked. A
failed send is now spooled to disk and retried ahead of the next message, and
again on the next process start.
"""

from __future__ import annotations

import json
import time

import pytest

import _bootstrap  # noqa: F401  (side-effect: puts trading-system/ on sys.path)

import shared.alerts.telegram as tg


@pytest.fixture
def alerter(tmp_path, monkeypatch):
    """A configured alerter whose outbox lives in tmp, with sending stubbed."""
    monkeypatch.setattr(tg, "_OUTBOX_PATH", tmp_path / "telegram_outbox.jsonl")
    a = tg.TelegramAlerter(bot_token="test-token", chat_id="test-chat")
    assert a.is_enabled
    return a


def _outbox(path):
    if not path.is_file():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def test_a_failed_send_is_kept_not_lost(alerter, tmp_path, monkeypatch):
    monkeypatch.setattr(alerter, "_deliver", lambda text, parse_mode="HTML": False)

    alerter._do_send_fast("EOD report: net -3,631.50")

    spooled = _outbox(tmp_path / "telegram_outbox.jsonl")
    assert len(spooled) == 1
    assert "EOD report" in spooled[0]["text"]


def test_a_successful_send_leaves_nothing_behind(alerter, tmp_path, monkeypatch):
    monkeypatch.setattr(alerter, "_deliver", lambda text, parse_mode="HTML": True)

    alerter._do_send_fast("Market is OPEN")

    assert _outbox(tmp_path / "telegram_outbox.jsonl") == []


def test_the_spooled_message_goes_out_when_the_network_returns(alerter, tmp_path, monkeypatch):
    """The whole point: nothing is lost, it is delivered late."""
    monkeypatch.setattr(alerter, "_deliver", lambda text, parse_mode="HTML": False)
    alerter._do_send_fast("Stand-down warning")
    assert len(_outbox(tmp_path / "telegram_outbox.jsonl")) == 1

    sent = []

    def _works(text, parse_mode="HTML"):
        sent.append(text)
        return True

    monkeypatch.setattr(alerter, "_deliver", _works)
    delivered = alerter.flush_outbox()

    assert delivered == 1
    assert any("Stand-down warning" in s for s in sent)
    assert _outbox(tmp_path / "telegram_outbox.jsonl") == [], "delivered messages are dropped from the spool"


def test_a_late_message_says_it_is_late(alerter, tmp_path, monkeypatch):
    path = tmp_path / "telegram_outbox.jsonl"
    path.write_text(json.dumps({"ts": time.time() - 1800, "text": "EOD report", "parse_mode": "HTML"}) + "\n",
                    encoding="utf-8")
    sent = []
    monkeypatch.setattr(alerter, "_deliver", lambda text, parse_mode="HTML": (sent.append(text), True)[1])

    alerter.flush_outbox()

    assert sent and "delayed" in sent[0], "a 30-minute-old alert must not read as current"


def test_a_stale_message_is_dropped_rather_than_sent(alerter, tmp_path, monkeypatch):
    """Yesterday's "Market is OPEN" helps nobody."""
    path = tmp_path / "telegram_outbox.jsonl"
    path.write_text(json.dumps({"ts": time.time() - (13 * 3600), "text": "Market is OPEN",
                                "parse_mode": "HTML"}) + "\n", encoding="utf-8")
    sent = []
    monkeypatch.setattr(alerter, "_deliver", lambda text, parse_mode="HTML": (sent.append(text), True)[1])

    alerter.flush_outbox()

    assert sent == []
    assert _outbox(path) == []


def test_pending_messages_are_retried_before_the_next_one(alerter, tmp_path, monkeypatch):
    """Order matters: the backlog goes first, so alerts arrive in sequence."""
    monkeypatch.setattr(alerter, "_deliver", lambda text, parse_mode="HTML": False)
    alerter._do_send_fast("first")

    sent = []
    monkeypatch.setattr(alerter, "_deliver", lambda text, parse_mode="HTML": (sent.append(text), True)[1])
    alerter._do_send_fast("second")

    assert len(sent) == 2
    assert "first" in sent[0] and sent[1] == "second"


def test_a_still_broken_network_stops_after_the_first_failure(alerter, tmp_path, monkeypatch):
    """Do not hammer a dead link with the whole backlog."""
    path = tmp_path / "telegram_outbox.jsonl"
    now = time.time()
    path.write_text("\n".join(
        json.dumps({"ts": now, "text": f"msg{i}", "parse_mode": "HTML"}) for i in range(3)
    ) + "\n", encoding="utf-8")

    attempts = []
    monkeypatch.setattr(alerter, "_deliver",
                        lambda text, parse_mode="HTML": (attempts.append(text), False)[1])

    assert alerter.flush_outbox() == 0
    assert len(attempts) == 1, "one probe, not three"
    assert len(_outbox(path)) == 3, "nothing is lost while the link is down"


def test_the_spool_cannot_grow_without_bound(alerter, tmp_path, monkeypatch):
    monkeypatch.setattr(tg, "_OUTBOX_MAX", 5)
    monkeypatch.setattr(alerter, "_deliver", lambda text, parse_mode="HTML": False)

    for i in range(9):
        alerter._do_send_fast(f"msg{i}")

    spooled = _outbox(tmp_path / "telegram_outbox.jsonl")
    assert len(spooled) == 5
    assert spooled[-1]["text"] == "msg8", "the newest alerts are the ones kept"


def test_an_unconfigured_alerter_spools_nothing(tmp_path, monkeypatch):
    monkeypatch.setattr(tg, "_OUTBOX_PATH", tmp_path / "telegram_outbox.jsonl")
    off = tg.TelegramAlerter(bot_token="", chat_id="")

    off._do_send_fast("anything")

    assert not (tmp_path / "telegram_outbox.jsonl").exists()
    assert off.flush_outbox() == 0
