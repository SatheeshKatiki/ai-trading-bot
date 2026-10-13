"""Order-side safety of the live engine, driven by a scripted fake broker.

Every scenario here is one the 2026-10-13 review found could leave a real
position oversold, double-booked or without an exchange stop. The fake broker
(tests/fake_broker.py) keeps a real order book with scripted fills and
failures, so the assertions are about what would have happened at the
exchange, not about which functions were called.
"""
from __future__ import annotations

from brokers.models import OrderStatus


def test_main_imports_order_status():
    """main.py's fill polling and hard-stop checks compare against
    OrderStatus. Without the import every live exit raised NameError inside
    the stop interceptor, which the broad except swallowed, so the market
    exit went out with the exchange stop still live."""
    from trading_bot import main as bot_main

    assert bot_main.OrderStatus is OrderStatus
