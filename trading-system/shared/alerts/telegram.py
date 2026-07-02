"""Telegram Alerts integration for trade notifications.

Sends instant notifications for order execution, risk-off events,
and daily summaries to a configured Telegram chat.

Performance:  All HTTP requests are dispatched on a dedicated background
              daemon thread via a queue so the async trading event loop is
              NEVER blocked, even when the Telegram API is slow or unreachable.
"""

from __future__ import annotations

import logging
import re
import queue
import threading
import time
import urllib.parse
import urllib.request
from typing import Optional

from shared.config import CONFIG

logger = logging.getLogger(__name__)

# Pre-compiled regex for Telegram MarkdownV2 escaping (much faster than per-char loop)
_MD_ESCAPE_RE = re.compile(r"([_*\[\]()~`>#+\-=|{}.!])")

# Max messages queued before older ones are dropped (prevents memory growth)
_QUEUE_MAXSIZE = 50


class TelegramAlerter:
    """Handles sending trade and risk alerts via Telegram.

    HTTP calls are offloaded to a background daemon thread so they never
    block the async trading event loop.
    """

    def __init__(self, bot_token: Optional[str] = None, chat_id: Optional[str] = None):
        self.bot_token = bot_token or getattr(CONFIG, "TELEGRAM_BOT_TOKEN", "")
        self.chat_id   = chat_id   or getattr(CONFIG, "TELEGRAM_CHAT_ID", "")
        self.is_enabled = bool(self.bot_token and self.chat_id)

        # Background sender thread + queue
        self._queue: queue.Queue[Optional[str]] = queue.Queue(maxsize=_QUEUE_MAXSIZE)
        self._last_send_time: float = 0.0
        self._MIN_INTERVAL = 0.04   # ~25 messages / second (Telegram limit: 30/s)

        if self.is_enabled:
            t = threading.Thread(target=self._sender_loop, daemon=True, name="TelegramSender")
            t.start()
            logger.info("TelegramAlerter: background sender thread started.")

    # ------------------------------------------------------------------
    # Background sender thread
    # ------------------------------------------------------------------

    def _sender_loop(self) -> None:
        """Daemon thread: drain the queue and fire HTTP requests."""
        while True:
            try:
                text = self._queue.get(timeout=60)
                if text is None:          # shutdown signal
                    break
                self._do_send(text)
                self._queue.task_done()
            except queue.Empty:
                continue
            except Exception as exc:
                logger.error("TelegramSender loop error: %s", exc)

    def _do_send(self, text: str) -> None:
        """Execute the actual HTTP request (runs in background thread only)."""
        # Respect Telegram rate limit
        now = time.monotonic()
        gap = self._MIN_INTERVAL - (now - self._last_send_time)
        if gap > 0:
            time.sleep(gap)
        self._last_send_time = time.monotonic()

        try:
            encoded = urllib.parse.quote_plus(text)
            url = (
                f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
                f"?chat_id={self.chat_id}"
                f"&text={encoded}"
                f"&parse_mode=MarkdownV2"
            )
            req = urllib.request.Request(url, method="GET")
            with urllib.request.urlopen(req, timeout=8) as resp:
                if resp.status != 200:
                    logger.error("Telegram HTTP %s", resp.status)
        except Exception as exc:
            logger.warning("Telegram send failed (non-blocking): %s", exc)

    def _enqueue(self, text: str) -> None:
        """Push a message onto the queue; drop silently if full."""
        if not self.is_enabled:
            return
        try:
            self._queue.put_nowait(text)
        except queue.Full:
            logger.warning("Telegram queue full – alert dropped.")

    # ------------------------------------------------------------------
    # Markdown helpers
    # ------------------------------------------------------------------

    @staticmethod
    def escape_markdown(text: str) -> str:
        """Escape special characters for Telegram MarkdownV2 (regex-based, fast)."""
        return _MD_ESCAPE_RE.sub(r"\\\1", str(text))

    # ------------------------------------------------------------------
    # Public alert methods (all non-blocking — return immediately)
    # ------------------------------------------------------------------

    def send_alert(self, msg: str) -> None:
        """Enqueue a generic text alert (returns instantly)."""
        self._enqueue(msg)

    def send_trade_alert(
        self, symbol: str, side: str, qty: int, price: float, confidence: float = 1.0
    ) -> None:
        """Enqueue a trade execution alert (returns instantly)."""
        emoji = "🟢" if "BUY" in side.upper() or "CALL" in side.upper() else "🔴"
        conf_pct = round(confidence * 100, 1)
        msg = (
            f"{emoji} *NEW TRADE EXECUTION*\n\n"
            f"Symbol: {self.escape_markdown(symbol)}\n"
            f"Action: *{self.escape_markdown(side.upper())}*\n"
            f"Quantity: {qty}\n"
            f"Entry Price: ₹{self.escape_markdown(str(price))}\n"
            f"AI Confidence: {conf_pct}%\n"
        )
        self._enqueue(msg)

    def send_exit_alert(
        self, symbol: str, side: int | str, qty: int, price: float, pnl: float, reason: str
    ) -> None:
        """Enqueue a position-closed alert (returns instantly)."""
        emoji = "🎯" if pnl > 0 else "🛑"
        side_label = "LONG" if side == 1 else "SHORT"
        msg = (
            f"{emoji} *POSITION CLOSED*\n\n"
            f"Symbol: {self.escape_markdown(symbol)} \\({side_label}\\)\n"
            f"Exit Price: ₹{self.escape_markdown(str(price))}\n"
            f"Quantity: {qty}\n"
            f"Realized PnL: *₹{self.escape_markdown(str(round(pnl, 2)))}*\n"
            f"Reason: {self.escape_markdown(reason)}\n"
        )
        self._enqueue(msg)

    def send_risk_off_alert(self, reason: str) -> None:
        """Enqueue a critical risk-off alert (returns instantly)."""
        msg = (
            f"⚠️ *CRITICAL: RISK\\-OFF ACTIVATED* ⚠️\n\n"
            f"Trading has been automatically halted\\.\n"
            f"Reason: {self.escape_markdown(reason)}\n"
        )
        self._enqueue(msg)


# Global alerter instance
alerter = TelegramAlerter()
