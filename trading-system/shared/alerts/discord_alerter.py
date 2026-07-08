"""
Discord / Webhook Alert Engine for Algorithmic Trading.

Sends real-time execution alerts with rich embed formatting.
Operates asynchronously (via threading) to prevent blocking the main trading loop.
"""

import os
import json
import logging
import threading
import urllib.request
from typing import Optional

logger = logging.getLogger(__name__)

# User can configure this in settings or env vars later
DISCORD_WEBHOOK_URL = "https://discord.com/api/webhooks/1524480803386560675/J8Ectem4ATqJ8r81618l8Wj4bAglp6EiTFmS5M5YJe_JS3T541C_H1gO0pGpar3jjQNS"

class Alerter:
    def send_trade_alert(
        self,
        symbol: str, 
        message: str, 
        quantity: int, 
        price: float, 
        side: float = 1.0
    ) -> None:
        """
        Dispatch an alert in the background.
        """
        if not DISCORD_WEBHOOK_URL:
            return
            
        threading.Thread(
            target=_post_discord_alert,
            args=(symbol, side, quantity, price, "Meta-Agent", message),
            daemon=True
        ).start()

alerter = Alerter()

def _post_discord_alert(
    symbol: str, 
    side: int, 
    quantity: int, 
    price: float, 
    strategy_name: str,
    message: str
) -> None:
    """Synchronous POST request to Discord Webhook."""
    try:
        side_str = "BUY" if side == 1 else "SELL"
        color = 3066993 if side == 1 else 15158332  # Green for BUY, Red for SELL
        
        import datetime
        import pytz
        ist = pytz.timezone("Asia/Kolkata")
        trigger_time = datetime.datetime.now(ist).strftime("%Y-%m-%d %I:%M:%S %p")
        total_premium = quantity * price

        # Build Discord Rich Embed
        embed = {
            "title": f"🚨 TRADE ALERT: {side_str} {symbol}",
            "color": color,
            "fields": [
                {"name": "Action", "value": side_str, "inline": True},
                {"name": "Symbol", "value": symbol, "inline": True},
                {"name": "Execution Price", "value": f"₹{price:.2f}", "inline": True},
                {"name": "Quantity (Lots)", "value": str(quantity), "inline": True},
                {"name": "Capital Deployed", "value": f"₹{total_premium:,.2f}", "inline": True},
                {"name": "Strategy Engine", "value": strategy_name, "inline": True},
                {"name": "Triggered Time (IST)", "value": trigger_time, "inline": False},
            ],
            "footer": {"text": "QuantAI Execution Terminal"}
        }
        
        if message:
            embed["description"] = message
            
        payload = {
            "username": "QuantAI Swarm Bot",
            "embeds": [embed]
        }
        
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            DISCORD_WEBHOOK_URL, 
            data=data, 
            headers={'Content-Type': 'application/json', 'User-Agent': 'QuantAI/1.0'}
        )
        
        with urllib.request.urlopen(req, timeout=5) as response:
            if response.getcode() not in [200, 204]:
                logger.warning(f"[Alerts] Discord webhook returned {response.getcode()}")
                
    except Exception as e:
        logger.error(f"[Alerts] Failed to send Discord alert: {e}")
