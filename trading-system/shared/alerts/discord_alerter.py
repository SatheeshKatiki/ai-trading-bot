"""
Discord / Webhook Alert Engine for Algorithmic Trading.

Sends real-time execution alerts with rich embed formatting.
Operates asynchronously (via threading) to prevent blocking the main trading loop.
"""

from __future__ import annotations

import json
import logging
import threading
import urllib.request
from datetime import datetime
from typing import Any, Optional, Union

import pytz

logger = logging.getLogger(__name__)

_IST = pytz.timezone("Asia/Kolkata")

# User can configure this in settings or env vars later
DISCORD_WEBHOOK_URL = "https://discord.com/api/webhooks/1524480803386560675/J8Ectem4ATqJ8r81618l8Wj4bAglp6EiTFmS5M5YJe_JS3T541C_H1gO0pGpar3jjQNS"


def _format_alert_time(execution_time: Optional[Any] = None) -> str:
    """Format execution time into IST readable string."""
    if isinstance(execution_time, str) and execution_time.strip():
        return execution_time.strip()
    if isinstance(execution_time, datetime):
        if execution_time.tzinfo is None:
            return _IST.localize(execution_time).strftime("%Y-%m-%d %I:%M:%S %p")
        return execution_time.astimezone(_IST).strftime("%Y-%m-%d %I:%M:%S %p")
    return datetime.now(_IST).strftime("%Y-%m-%d %I:%M:%S %p")


def _send_discord_payload(payload: dict[str, Any]) -> None:
    """Helper to dispatch JSON payload to Discord webhook."""
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        DISCORD_WEBHOOK_URL,
        data=data,
        headers={"Content-Type": "application/json", "User-Agent": "QuantAI/1.0"},
    )
    with urllib.request.urlopen(req, timeout=5) as response:
        if response.getcode() not in (200, 204):
            logger.warning("[Alerts] Discord webhook returned %s", response.getcode())


class Alerter:
    """Institutional-grade Discord Webhook Alerter with non-blocking dispatch."""

    def send_trade_alert(
        self,
        symbol: str,
        message: str = "",
        quantity: int = 0,
        price: float = 0.0,
        side: Union[float, int, str] = 1.0,
        qty: int = 0,
        confidence: float = 1.0,
        reason: Optional[str] = None,
        execution_time: Optional[Any] = None,
        **kwargs: Any,
    ) -> None:
        """Dispatch a trade execution alert in the background."""
        if not DISCORD_WEBHOOK_URL:
            return

        final_qty = qty if qty > 0 else quantity
        final_msg = reason or message or "Trade Executed"
        side_val = 1 if (side == 1 or "BUY" in str(side).upper() or "CALL" in str(side).upper()) else -1
        time_str = _format_alert_time(execution_time)

        threading.Thread(
            target=_post_discord_alert,
            args=(symbol, side_val, final_qty, price, "Meta-Agent", final_msg, time_str, confidence),
            daemon=True,
        ).start()

    def send_exit_alert(
        self,
        symbol: str,
        side: Union[int, str],
        qty: int,
        price: float,
        pnl: float,
        reason: str,
        execution_time: Optional[Any] = None,
        **kwargs: Any,
    ) -> None:
        """Dispatch an exit alert in the background."""
        if not DISCORD_WEBHOOK_URL:
            return

        time_str = _format_alert_time(execution_time)
        threading.Thread(
            target=_post_discord_exit_alert,
            args=(symbol, side, qty, price, pnl, reason, time_str),
            daemon=True,
        ).start()

    def send_trailing_sl_alert(
        self,
        symbol: str,
        new_sl: float,
        reason: Optional[str] = None,
        execution_time: Optional[Any] = None,
        **kwargs: Any,
    ) -> None:
        """Dispatch a trailing stop loss alert in the background."""
        if not DISCORD_WEBHOOK_URL:
            return

        time_str = _format_alert_time(execution_time)
        threading.Thread(
            target=_post_discord_trailing_sl_alert,
            args=(symbol, new_sl, reason or "Risk Mitigation", time_str),
            daemon=True,
        ).start()

    def send_alert(self, message: str) -> None:
        """Dispatch a generic, freeform text alert in the background."""
        if not DISCORD_WEBHOOK_URL:
            return

        threading.Thread(
            target=_post_discord_generic_alert,
            args=(message,),
            daemon=True,
        ).start()


alerter = Alerter()


def _post_discord_alert(
    symbol: str,
    side: int,
    quantity: int,
    price: float,
    strategy_name: str,
    message: str,
    trigger_time: Optional[str] = None,
    confidence: float = 1.0,
) -> None:
    """Synchronous POST request to Discord Webhook."""
    try:
        side_str = "BUY" if side == 1 else "SELL"
        color = 3066993 if side == 1 else 15158332  # Green for BUY, Red for SELL
        time_display = trigger_time or _format_alert_time()
        total_premium = quantity * price
        conf_display = f"{confidence * 100:.0f}%" if confidence <= 1.0 else f"{confidence:.0f}%"

        # Build Discord Rich Embed
        fields = [
            {"name": "Action", "value": side_str, "inline": True},
            {"name": "Symbol", "value": symbol, "inline": True},
            {"name": "Execution Price", "value": f"₹{price:.2f}", "inline": True},
            {"name": "Quantity (Lots)", "value": str(quantity), "inline": True},
            {"name": "Capital Deployed", "value": f"₹{total_premium:,.2f}", "inline": True},
            {"name": "AI Confidence", "value": conf_display, "inline": True},
            {"name": "Strategy Engine", "value": strategy_name, "inline": True},
            {"name": "Triggered Time (IST)", "value": time_display, "inline": False},
        ]

        embed: dict[str, Any] = {
            "title": f"🚨 TRADE ALERT: {side_str} {symbol}",
            "color": color,
            "fields": fields,
            "footer": {"text": "QuantAI Execution Terminal"},
        }

        if message:
            embed["description"] = message

        payload = {
            "username": "QuantAI Swarm Bot",
            "embeds": [embed],
        }

        _send_discord_payload(payload)

    except Exception as e:
        logger.error("[Alerts] Failed to send Discord alert: %s", e)


def _post_discord_exit_alert(
    symbol: str,
    side: Union[int, str],
    qty: int,
    price: float,
    pnl: float,
    reason: str,
    trigger_time: Optional[str] = None,
) -> None:
    """Synchronous POST request to Discord Webhook for exits."""
    try:
        side_label = "LONG" if (side == 1 or str(side).upper() in ("1", "BUY", "LONG")) else "SHORT"
        color = 3066993 if pnl > 0 else 15158332  # Green if profit, Red if loss
        time_display = trigger_time or _format_alert_time()

        # Build Discord Rich Embed
        embed: dict[str, Any] = {
            "title": f"🎯 POSITION CLOSED: {symbol}" if pnl > 0 else f"🛑 POSITION CLOSED: {symbol}",
            "color": color,
            "fields": [
                {"name": "Symbol", "value": f"{symbol} ({side_label})", "inline": True},
                {"name": "Exit Price", "value": f"₹{price:.2f}", "inline": True},
                {"name": "Quantity", "value": str(qty), "inline": True},
                {"name": "Realized PnL", "value": f"₹{pnl:,.2f}", "inline": True},
                {"name": "Reason", "value": reason, "inline": True},
                {"name": "Triggered Time (IST)", "value": time_display, "inline": False},
            ],
            "footer": {"text": "QuantAI Execution Terminal"},
        }

        payload = {
            "username": "QuantAI Swarm Bot",
            "embeds": [embed],
        }

        _send_discord_payload(payload)

    except Exception as e:
        logger.error("[Alerts] Failed to send Discord exit alert: %s", e)


def _post_discord_trailing_sl_alert(
    symbol: str,
    new_sl: float,
    reason: str,
    trigger_time: Optional[str] = None,
) -> None:
    """Synchronous POST request to Discord Webhook for trailing stop loss adjustments."""
    try:
        time_display = trigger_time or _format_alert_time()
        embed: dict[str, Any] = {
            "title": f"🛡️ TRAILING SL ADJUSTED: {symbol}",
            "color": 3447003,  # Blue
            "fields": [
                {"name": "Symbol", "value": symbol, "inline": True},
                {"name": "New Stop Loss", "value": f"₹{new_sl:.2f}", "inline": True},
                {"name": "Adjustment Reason", "value": reason, "inline": True},
                {"name": "Triggered Time (IST)", "value": time_display, "inline": False},
            ],
            "footer": {"text": "QuantAI Risk Mitigation Engine"},
        }
        payload = {
            "username": "QuantAI Swarm Bot",
            "embeds": [embed],
        }
        _send_discord_payload(payload)
    except Exception as e:
        logger.error("[Alerts] Failed to send Discord trailing SL alert: %s", e)


def _post_discord_generic_alert(message: str) -> None:
    """Synchronous POST request to Discord Webhook for a freeform text alert."""
    try:
        payload = {
            "username": "QuantAI Swarm Bot",
            "content": message,
        }
        _send_discord_payload(payload)
    except Exception as e:
        logger.error("[Alerts] Failed to send Discord alert: %s", e)
