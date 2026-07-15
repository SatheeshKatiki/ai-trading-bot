"""Iceberg Execution Manager — Anti-Slippage Engine for High Quantities.

This module slices large option/equity orders into smaller chunks (e.g., 500 qty max)
and executes them asynchronously with random time delays (TWAP-style) to hide 
institutional footprint and minimize slippage.
"""
import asyncio
import logging
import random
from typing import List, Callable, Optional

from brokers import OrderRequest, OrderSide, BaseBroker
from shared.security.rate_limiter import ORDER_LIMITER

logger = logging.getLogger(__name__)

class IcebergManager:
    def __init__(self, max_slice_qty: int = 500, min_delay_sec: float = 0.5, max_delay_sec: float = 2.0):
        self.max_slice_qty = max_slice_qty
        self.min_delay = min_delay_sec
        self.max_delay = max_delay_sec

    async def execute_iceberg(self, broker: BaseBroker, order: OrderRequest, halt_check: Optional[Callable[[], bool]] = None) -> List[OrderRequest]:
        """
        Slices a large order into chunks and executes them sequentially.
        Respects system halt flags during TWAP sleeps.
        """
        total_qty = order.quantity
        if total_qty <= self.max_slice_qty:
            # Standard execution, no slicing needed
            if ORDER_LIMITER.allow(broker.BROKER_ID):
                try:
                    await broker.place_order_async(order)
                    return [order]
                except Exception as e:
                    logger.error("Standard Order failed: %s", e)
                    return []
            else:
                logger.warning("Order rate limit reached for %s", order.symbol)
                return []

        # Iceberg Slicing logic
        slices = []
        remaining = total_qty
        while remaining > 0:
            chunk = min(remaining, self.max_slice_qty)
            slices.append(chunk)
            remaining -= chunk

        logger.info("ICEBERG TRIGGERED: %s %d qty split into %d slices %s", 
                    order.side.name, total_qty, len(slices), slices)

        executed_orders = []
        for i, chunk_qty in enumerate(slices):
            slice_order = OrderRequest(
                symbol=order.symbol,
                quantity=chunk_qty,
                side=order.side,
                order_type=order.order_type,
                product_type=order.product_type,
                price=order.price,
                trigger_price=order.trigger_price
            )
            
            if ORDER_LIMITER.allow(broker.BROKER_ID):
                try:
                    await broker.place_order_async(slice_order)
                    executed_orders.append(slice_order)
                    logger.info("Iceberg Slice %d/%d: Executed %d qty for %s", 
                                i+1, len(slices), chunk_qty, order.symbol)
                except Exception as e:
                    logger.error("Iceberg Slice %d failed: %s", i+1, e)
            else:
                logger.warning("Iceberg Slice %d delayed due to rate limit.", i+1)
            
            # TWAP Random Delay between slices (unless it's the last one)
            if i < len(slices) - 1:
                delay = random.uniform(self.min_delay, self.max_delay)
                await asyncio.sleep(delay)
                
                # Halt Execution if system panic exited or reached max drawdown during the sleep!
                if halt_check and halt_check():
                    logger.warning("ICEBERG ABORTED: System Halt or Panic Exit triggered mid-flight for %s!", order.symbol)
                    break
                    
        return executed_orders
