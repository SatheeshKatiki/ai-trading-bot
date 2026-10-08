"""Unit tests for Telegram alert timestamp formatting across Entry, Exit, Trailing SL, and Risk-off."""

import pytest
from shared.alerts.telegram import TelegramAlerter, _format_alert_time


def test_format_alert_time():
    # None returns current IST time
    t_none = _format_alert_time(None)
    assert "AM" in t_none or "PM" in t_none

    # Clean HH:MM:SS string
    assert _format_alert_time("09:35:12") == "09:35:12 AM"
    assert _format_alert_time("14:20:05") == "02:20:05 PM"

    # Already formatted with AM/PM
    assert _format_alert_time("09:35:12 AM") == "09:35:12 AM"


def test_telegram_alert_timing_templates():
    alerter = TelegramAlerter()
    captured = []
    alerter._enqueue = lambda msg, parse_mode="HTML": captured.append(msg)

    # 1. Trade Entry Alert
    alerter.send_trade_alert(
        symbol="NIFTY26OCT22600CE",
        side="BUY",
        qty=65,
        price=103.40,
        confidence=0.9,
        reason="EMA 9 / RSI Momentum Signal Confirmation",
        language="te",
        execution_time="09:35:12",
    )
    assert len(captured) == 1
    assert "⏰ *ఎంట్రీ సమయం (Time)*: `09:35:12 AM`" in captured[-1]
    assert "NIFTY26OCT22600CE" in captured[-1]

    # 2. Trade Exit Alert
    alerter.send_exit_alert(
        symbol="NIFTY26OCT22600CE",
        side="BUY",
        qty=65,
        price=82.65,
        pnl=-1372.0,
        reason="Stop Loss Hit",
        language="te",
        execution_time="09:42:05",
    )
    assert len(captured) == 2
    assert "⏰ *ఎగ్జిట్ సమయం (Time)*: `09:42:05 AM`" in captured[-1]
    assert "Stop Loss Hit" in captured[-1]

    # 3. Trailing SL Alert
    alerter.send_trailing_sl_alert(
        symbol="NIFTY26OCT22600CE",
        new_sl=95.0,
        reason="Profit ratcheted",
        language="te",
        execution_time="09:40:15",
    )
    assert len(captured) == 3
    assert "⏰ *సమయం (Time)*: `09:40:15 AM`" in captured[-1]
    assert "₹`95.00`" in captured[-1]

    # 4. Risk Off Alert
    alerter.send_risk_off_alert(
        reason="Daily Drawdown Limit Reached",
        language="te",
        execution_time="10:15:00",
    )
    assert len(captured) == 4
    assert "⏰ *సమయం (Time)*: `10:15:00 AM`" in captured[-1]
