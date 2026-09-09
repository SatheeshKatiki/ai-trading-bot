"""Telegram Alerts integration for trade notifications.

Sends instant notifications for order execution, risk-off events,
and daily summaries to a configured Telegram chat.

Performance & Security:
  - All HTTP requests are dispatched asynchronously on dedicated background
    daemon worker threads via ThreadPoolExecutor.
  - JSON POST payload over HTTPS for maximum throughput and reliability.
  - Zero token exposure in logs (masked security).
  - Multi-language I18N support (Telugu, English, Hindi).
  - Automatic resilient fallback to clean plain text if formatting fails.
"""

from __future__ import annotations

import atexit
import json
import logging
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from typing import Optional, Union, Dict, Any

from shared.config import CONFIG

logger = logging.getLogger(__name__)



class TelegramAlerter:
    """Handles sending trade, exit, trailing SL, and risk alerts via Telegram.

    Dispatches HTTP calls concurrently on a background daemon worker pool so
    the async trading event loop is NEVER blocked.
    """

    def __init__(self, bot_token: Optional[str] = None, chat_id: Optional[str] = None):
        # 1. Resolve credentials (Priority: explicit arg -> CONFIG -> Vault -> os.environ)
        token = bot_token or getattr(CONFIG, "TELEGRAM_BOT_TOKEN", "") or os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
        cid = chat_id or getattr(CONFIG, "TELEGRAM_CHAT_ID", "") or os.getenv("TELEGRAM_CHAT_ID", "").strip()

        if not (token and cid):
            try:
                from brokers.credentials import load_credentials
                creds = load_credentials("telegram")
                token = token or creds.get("bot_token", "")
                cid = cid or creds.get("chat_id", "")
            except Exception:
                pass

        self.bot_token: str = str(token).strip() if token else ""
        self.chat_id: str = str(cid).strip() if cid else ""
        self.is_enabled: bool = bool(self.bot_token and self.chat_id)

        # 2. Concurrency & Fast Multi-Worker Dispatch Engine
        self._executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="TelegramFastWorker")
        atexit.register(self._shutdown_pool)

        if self.is_enabled:
            # Masked token for security (e.g., 881666****Uk)
            masked_token = f"{self.bot_token[:6]}****{self.bot_token[-4:]}" if len(self.bot_token) > 10 else "****"
            logger.info("TelegramAlerter active for chat_id=%s (token=%s)", self.chat_id, masked_token)

    def _shutdown_pool(self) -> None:
        """Clean shutdown of background worker pool on process exit."""
        try:
            self._executor.shutdown(wait=False, cancel_futures=True)
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Ultra-Fast Dispatch Mechanism (Multi-threaded JSON POST)
    # ------------------------------------------------------------------

    #: Characters that legacy MarkdownV2 call sites may have escaped with a
    #: backslash. Kept as an explicit class so the pattern below stays readable.
    _MD_ESCAPABLE = r"_*\[\]()~`>#+=|{}.!\\-"

    @staticmethod
    def format_to_html(text: str) -> str:
        """Convert light markdown into native Telegram HTML.

        Bold ``*text*`` -> ``<b>``, code `` `text` `` -> ``<code>``, italic
        ``_text_`` -> ``<i>``, and ``> quote`` -> ``<blockquote>``.

        Two bugs fixed here on 2026-09-09:

        1. The backslash-stripping step was a **no-op**. Its character class
           was over-escaped (``[_*\\[\\]()...]``), so the class terminated early
           and the pattern matched none of the intended characters. Verified:
           ``\\_underscore\\_`` came back as ``\\<i>underscore\\</i>`` -- the
           backslashes survived AND the italic tags were applied around them,
           producing exactly the "broken backslash artifacts" the docstring
           claimed to prevent.

        2. ``&``, ``<`` and ``>`` were never HTML-escaped. Telegram's HTML
           parser rejects raw ones, so a single ``&`` or ``<`` anywhere in a
           dynamic field (a symbol, an exit reason, a P&L string) returned
           HTTP 400 and the whole message silently fell back to plain text --
           losing all formatting, with only a debug-level log line.

        Order matters: escape the payload FIRST, then insert our own tags, so
        the tags we add are never themselves escaped.
        """
        raw = str(text)

        # 1. Strip backslashes that legacy MarkdownV2 call sites added.
        clean = re.sub(r"\\([" + TelegramAlerter._MD_ESCAPABLE + r"])", r"\1", raw)

        # 2. HTML-escape the payload before any tag is introduced. Telegram
        #    only recognises these three entities.
        clean = (clean.replace("&", "&amp;")
                      .replace("<", "&lt;")
                      .replace(">", "&gt;"))

        # 2. Process blockquotes (lines starting with '> ' or '>')
        lines = clean.split("\n")
        new_lines = []
        in_quote = False
        quote_buf = []

        for line in lines:
            stripped = line.strip()
            # '>' is '&gt;' by this point, having been escaped above.
            if stripped.startswith("&gt;"):
                in_quote = True
                quote_buf.append(stripped[4:].strip())
            else:
                if in_quote:
                    new_lines.append(f"<blockquote>{chr(10).join(quote_buf)}</blockquote>")
                    quote_buf = []
                    in_quote = False
                new_lines.append(line)
        if in_quote:
            new_lines.append(f"<blockquote>{chr(10).join(quote_buf)}</blockquote>")

        formatted = "\n".join(new_lines)

        # 3. Bold: *text* -> <b>text</b> (only if not already html tag)
        formatted = re.sub(r"\*([^*\n]+)\*", r"<b>\1</b>", formatted)
        # 4. Code: `text` -> <code>text</code>
        formatted = re.sub(r"`([^`\n]+)`", r"<code>\1</code>", formatted)
        # 5. Italic: _text_ -> <i>text</i>
        formatted = re.sub(r"_([^_\n]+)_", r"<i>\1</i>", formatted)

        return formatted

    def _do_send_fast(self, text: str, parse_mode: str = "HTML") -> None:
        """Execute high-speed HTTP POST dispatch with robust HTML payload."""
        if not self.is_enabled:
            return

        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"

        # Format message into clean Telegram HTML
        html_payload_text = self.format_to_html(text) if parse_mode == "HTML" else text

        payload: Dict[str, Any] = {
            "chat_id": self.chat_id,
            "text": html_payload_text,
            "parse_mode": parse_mode,
            "disable_web_page_preview": True,
        }
        json_data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=json_data,
            headers={
                "Content-Type": "application/json",
                "User-Agent": "MANA-AI-UltraFastAlerter/3.0"
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=6) as resp:
                if resp.status == 200:
                    return
        except urllib.error.HTTPError as he:
            logger.debug("Telegram HTML parse failed (%s), retrying as clean plain text...", he.code)
        except Exception as exc:
            logger.debug("Telegram fast send notice: %s", exc)

        # Resilient Plain Text Fallback (strips all tags and slashes)
        try:
            plain_text = re.sub(r"<[^>]+>", "", text).replace("\\", "")
            payload_fallback: Dict[str, Any] = {
                "chat_id": self.chat_id,
                "text": plain_text,
                "disable_web_page_preview": True,
            }
            json_fallback = json.dumps(payload_fallback).encode("utf-8")
            req_fb = urllib.request.Request(
                url,
                data=json_fallback,
                headers={
                    "Content-Type": "application/json",
                    "User-Agent": "MANA-AI-UltraFastAlerter/3.0"
                },
                method="POST",
            )
            with urllib.request.urlopen(req_fb, timeout=6) as resp:
                if resp.status != 200:
                    logger.error("Telegram fallback HTTP error: %s", resp.status)
        except Exception as exc:
            logger.error("Telegram fallback dispatch failed: %s", exc)

    def _enqueue(self, text: str, parse_mode: str = "HTML") -> None:
        """Immediately dispatch message to concurrent thread pool without blocking."""
        if not self.is_enabled or not text:
            return
        try:
            self._executor.submit(self._do_send_fast, text, parse_mode)
        except Exception as e:
            logger.warning("Telegram worker submit error: %s", e)

    # ------------------------------------------------------------------
    # Language & I18N Helper
    # ------------------------------------------------------------------

    def _get_lang(self, override_lang: Optional[str] = None) -> str:
        if override_lang:
            return override_lang.lower()
        try:
            from shared.config import CONFIG
            cfg_lang = getattr(CONFIG, "ALERT_LANGUAGE", "te")
            if cfg_lang:
                return cfg_lang.lower()
        except Exception:
            pass
        return os.getenv("ALERT_LANGUAGE", "te").lower()

    @staticmethod
    def escape_markdown(text: str) -> str:
        """Sanitize text for dispatch (legacy backwards-compatible helper)."""
        return str(text).replace("\\", "")

    # ------------------------------------------------------------------
    # Public Alert Methods (All Non-Blocking — Instant Async Return)
    # ------------------------------------------------------------------

    def send_alert(self, msg: str) -> None:
        """Enqueue a generic text alert (returns instantly)."""
        self._enqueue(msg)

    def send_trade_alert(
        self,
        symbol: str,
        side: str,
        qty: int,
        price: float,
        confidence: float = 1.0,
        reason: Optional[str] = None,
        language: Optional[str] = None,
    ) -> None:
        """Enqueue a trade execution alert with detailed technical reason in user's selected language."""
        lang = self._get_lang(language)
        emoji = "🟢" if "BUY" in side.upper() or "CALL" in side.upper() else "🔴"
        conf_pct = round(confidence * 100, 1) if confidence <= 1.0 else round(confidence, 1)
        side_str = side.upper()
        reason_str = reason or "Multi-Timeframe Momentum & Indicator Confirmation"
        if lang == "te":
            action_label = "కొనుగోలు (BUY)" if "BUY" in side_str else "అమ్మకం (SELL)"
            msg = (
                f"{emoji} *MANA AI | కొత్త ట్రేడ్ ఎంట్రీ (NEW TRADE)*\n\n"
                f"📌 *సింబల్ (Symbol)*: `{symbol}`\n"
                f"⚡ *యాక్షన్ (Action)*: *{action_label}*\n"
                f"📦 *పరిమాణం (Qty)*: `{qty}`\n"
                f"💰 *ఎంట్రీ ధర (Price)*: ₹`{price:,.2f}`\n"
                f"🎯 *AI కాన్ఫిడెన్స్*: `{conf_pct}%`\n\n"
                f"🧠 *ట్రేడ్ ఎంట్రీ కారణం (Reason)*:\n"
                f"> 👉 _{reason_str}_\n"
                f"────────────────────────────\n"
                f"🛡️ _AI Greeks & Dynamic Risk Guard Active_\n"
            )
        elif lang == "hi":
            action_label = "खरीदें (BUY)" if "BUY" in side_str else "बेचें (SELL)"
            msg = (
                f"{emoji} *MANA AI | नया ट्रेड निष्पादन (NEW TRADE)*\n\n"
                f"📌 *प्रतीक (Symbol)*: `{symbol}`\n"
                f"⚡ *क्रिया (Action)*: *{action_label}*\n"
                f"📦 *मात्रा (Qty)*: `{qty}`\n"
                f"💰 *प्रवेश मूल्य (Price)*: ₹`{price:,.2f}`\n"
                f"🎯 *AI विश्वास*: `{conf_pct}%`\n\n"
                f"🧠 *ट्रेड लेने का कारण (Reason)*:\n"
                f"> 👉 _{reason_str}_\n"
                f"────────────────────────────\n"
                f"🛡️ _AI Greeks & Dynamic Risk Guard Active_\n"
            )
        else:  # English default
            msg = (
                f"{emoji} *MANA AI | NEW TRADE ENTRY*\n\n"
                f"📌 *Symbol*: `{symbol}`\n"
                f"⚡ *Action*: *{side_str}*\n"
                f"📦 *Quantity (Qty)*: `{qty}`\n"
                f"💰 *Entry Price*: ₹`{price:,.2f}`\n"
                f"🎯 *AI Confidence*: `{conf_pct}%`\n\n"
                f"🧠 *Entry Reason*:\n"
                f"> 👉 _{reason_str}_\n"
                f"────────────────────────────\n"
                f"🛡️ _AI Greeks & Dynamic Risk Guard Active_\n"
            )
        self._enqueue(msg)

    def send_exit_alert(
        self,
        symbol: str,
        side: Union[int, str],
        qty: int,
        price: float,
        pnl: float,
        reason: str,
        language: Optional[str] = None,
    ) -> None:
        """Enqueue a position-closed alert with full exit reason in user's selected language."""
        lang = self._get_lang(language)
        emoji = "🎯" if pnl >= 0 else "🛑"
        side_label = "LONG" if side in (1, "BUY", "LONG") else "SHORT"
        pnl_sign = "+" if pnl >= 0 else ""
        pnl_formatted = f"{pnl_sign}₹{pnl:,.2f}"

        if lang == "te":
            status_emoji = "🟢" if pnl >= 0 else "🔴"
            status_text = "లాభంతో ముగిసింది (PROFIT)" if pnl >= 0 else "నష్టంతో ముగిసింది (LOSS)"
            msg = (
                f"{emoji} *MANA AI | పొజిషన్ క్లోజ్ చేయబడింది (TRADE CLOSED)*\n\n"
                f"📌 *సింబల్ (Symbol)*: `{symbol}` ({side_label})\n"
                f"🚪 *ఎగ్జిట్ ధర (Exit Price)*: ₹`{price:,.2f}`\n"
                f"📦 *పరిమాణం (Quantity)*: `{qty}`\n"
                f"💵 *నికర లాభం/నష్టం (P&L)*: {status_emoji} *{pnl_formatted}* ({status_text})\n\n"
                f"📌 *ఎగ్జిట్ కారణం (Exit Reason)*:\n"
                f"> 👉 _{reason}_\n"
                f"────────────────────────────\n"
                f"🌙 _Capital Preserved & Position Locked_\n"
            )
        elif lang == "hi":
            status_emoji = "🟢" if pnl >= 0 else "🔴"
            status_text = "लाभ (PROFIT)" if pnl >= 0 else "नुकसान (LOSS)"
            msg = (
                f"{emoji} *MANA AI | स्थिति बंद कर दी गई (TRADE CLOSED)*\n\n"
                f"📌 *प्रतीक (Symbol)*: `{symbol}` ({side_label})\n"
                f"🚪 *निकास मूल्य (Exit Price)*: ₹`{price:,.2f}`\n"
                f"📦 *मात्रा (Quantity)*: `{qty}`\n"
                f"💵 *प्राप्त लाभ/हानि (P&L)*: {status_emoji} *{pnl_formatted}* ({status_text})\n\n"
                f"📌 *निकास कारण (Exit Reason)*:\n"
                f"> 👉 _{reason}_\n"
                f"────────────────────────────\n"
                f"🌙 _Capital Preserved & Position Locked_\n"
            )
        else:  # English default
            status_emoji = "🟢" if pnl >= 0 else "🔴"
            msg = (
                f"{emoji} *MANA AI | TRADE CLOSED*\n\n"
                f"📌 *Symbol*: `{symbol}` ({side_label})\n"
                f"🚪 *Exit Price*: ₹`{price:,.2f}`\n"
                f"📦 *Quantity*: `{qty}`\n"
                f"💵 *Realized P&L*: {status_emoji} *{pnl_formatted}*\n\n"
                f"📌 *Exit Reason*:\n"
                f"> 👉 _{reason}_\n"
                f"────────────────────────────\n"
                f"🌙 _Capital Preserved & Position Locked_\n"
            )
        self._enqueue(msg)

    def send_trailing_sl_alert(
        self,
        symbol: str,
        new_sl: float,
        reason: Optional[str] = None,
        language: Optional[str] = None,
    ) -> None:
        """Enqueue trailing stop loss adjustment alert."""
        lang = self._get_lang(language)
        reason_str = reason or "Profit reached threshold, locked in Breakeven"
        if lang == "te":
            msg = (
                f"🛡️ *MANA AI | స్టాప్‌లాస్ ట్రైలింగ్ అప్‌డేట్ (TRAILING SL)*\n\n"
                f"📌 *కాంట్రాక్ట్ (Contract)*: `{symbol}`\n"
                f"🛡️ *కొత్త స్టాప్‌లాస్ (New SL)*: ₹`{new_sl:,.2f}`\n\n"
                f"💡 *కారణం (Reason)*:\n"
                f"> 👉 _{reason_str}_\n"
                f"────────────────────────────\n"
                f"🔒 _Profit Locked & Risk Mitigated_\n"
            )
        elif lang == "hi":
            msg = (
                f"🛡️ *MANA AI | ट्रेलिंग स्टॉप लॉस अपडेट (TRAILING SL)*\n\n"
                f"📌 *अनुबंध (Contract)*: `{symbol}`\n"
                f"🛡️ *नया स्टॉप लॉस (New SL)*: ₹`{new_sl:,.2f}`\n\n"
                f"💡 *कारण (Reason)*:\n"
                f"> 👉 _{reason_str}_\n"
                f"────────────────────────────\n"
                f"🔒 _Profit Locked & Risk Mitigated_\n"
            )
        else:
            msg = (
                f"🛡️ *MANA AI | TRAILING SL UPDATED*\n\n"
                f"📌 *Contract*: `{symbol}`\n"
                f"🛡️ *New Stop Loss*: ₹`{new_sl:,.2f}`\n\n"
                f"💡 *Reason*:\n"
                f"> 👉 _{reason_str}_\n"
                f"────────────────────────────\n"
                f"🔒 _Profit Locked & Risk Mitigated_\n"
            )
        self._enqueue(msg)

    def send_risk_off_alert(self, reason: str, language: Optional[str] = None) -> None:
        """Enqueue a critical risk-off alert (returns instantly)."""
        lang = self._get_lang(language)
        if lang == "te":
            msg = (
                f"⚠️ *MANA AI | అత్యవసర హెచ్చరిక: రిస్క్-ఆఫ్ ట్రిగ్గర్ అయింది (CRITICAL RISK-OFF)* ⚠️\n\n"
                f"ట్రేడింగ్ తాత్కాలికంగా నిలిపివేయబడింది (Trading Halted).\n\n"
                f"📌 *కారణం (Reason)*:\n"
                f"> 👉 _{reason}_\n"
                f"────────────────────────────\n"
                f"🛡️ _Emergency Capital Shield Deployed_\n"
            )
        elif lang == "hi":
            msg = (
                f"⚠️ *MANA AI | महत्वपूर्ण सूचना: रिस्क-ऑफ सक्रिय (CRITICAL RISK-OFF)* ⚠️\n\n"
                f"ट्रेडिंग स्वचालित रूप से रोक दी गई है (Trading Halted).\n\n"
                f"📌 *कारण (Reason)*:\n"
                f"> 👉 _{reason}_\n"
                f"────────────────────────────\n"
                f"🛡️ _Emergency Capital Shield Deployed_\n"
            )
        else:
            msg = (
                f"⚠️ *MANA AI | CRITICAL: RISK-OFF ACTIVATED* ⚠️\n\n"
                f"Trading has been automatically halted.\n\n"
                f"📌 *Reason*:\n"
                f"> 👉 _{reason}_\n"
                f"────────────────────────────\n"
                f"🛡️ _Emergency Capital Shield Deployed_\n"
            )
        self._enqueue(msg)


# Global alerter instance
alerter = TelegramAlerter()
