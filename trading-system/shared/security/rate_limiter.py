"""Token-bucket rate limiter for broker API calls.

Prevents hammering the broker API during fast tick loops or error-retry
storms. Thread-safe and usable from both sync and async code.

Usage::

    from shared.security import RateLimiter

    # Allow 10 order placements per minute per broker
    order_limiter = RateLimiter(rate=10, per_seconds=60, burst=3)

    if order_limiter.allow("fyers"):
        broker.place_order(...)
    else:
        logger.warning("Order rate limit reached — skipping.")

Global singleton for common operations::

    from shared.security.rate_limiter import ORDER_LIMITER, DATA_LIMITER

    if ORDER_LIMITER.allow("fyers"):
        ...
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict
from typing import Dict


class _Bucket:
    """Single token-bucket for one key."""
    __slots__ = ("tokens", "last_refill", "lock")

    def __init__(self, capacity: float) -> None:
        self.tokens     = capacity
        self.last_refill = time.monotonic()
        self.lock        = threading.Lock()


class RateLimiter:
    """Thread-safe token-bucket rate limiter.

    Parameters
    ----------
    rate : float
        Maximum number of calls allowed within ``per_seconds``.
    per_seconds : float
        The time window (in seconds) for ``rate`` calls.
    burst : float
        Maximum burst capacity (tokens that can accumulate when idle).
        Defaults to ``rate``.
    """

    def __init__(self, rate: float, per_seconds: float = 1.0, burst: float | None = None) -> None:
        self.rate        = rate
        self.per_seconds = per_seconds
        self.capacity    = burst if burst is not None else rate
        self.refill_rate = rate / per_seconds   # tokens per second
        self._buckets: Dict[str, _Bucket] = defaultdict(lambda: _Bucket(self.capacity))
        self._global_lock = threading.Lock()

    def allow(self, key: str = "default") -> bool:
        """Return True if the call is allowed; False if rate-limited.

        Consumes one token from the bucket for ``key``.
        """
        with self._global_lock:
            bucket = self._buckets[key]

        with bucket.lock:
            now     = time.monotonic()
            elapsed = now - bucket.last_refill
            # Refill tokens based on elapsed time
            bucket.tokens = min(
                self.capacity,
                bucket.tokens + elapsed * self.refill_rate,
            )
            bucket.last_refill = now

            if bucket.tokens >= 1.0:
                bucket.tokens -= 1.0
                return True
            return False

    def wait_and_allow(self, key: str = "default", timeout: float = 5.0) -> bool:
        """Block until a token is available or ``timeout`` seconds elapse.

        Returns True if a token was acquired, False if timed out.
        Useful for non-critical paths where waiting is acceptable.
        """
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self.allow(key):
                return True
            time.sleep(0.05)
        return False

    def reset(self, key: str = "default") -> None:
        """Refill the bucket for ``key`` to full capacity."""
        with self._global_lock:
            self._buckets[key] = _Bucket(self.capacity)

    def status(self, key: str = "default") -> dict:
        """Return current token count and refill rate for monitoring."""
        with self._global_lock:
            bucket = self._buckets.get(key)
        if bucket is None:
            return {"tokens": self.capacity, "capacity": self.capacity}
        return {
            "tokens":      round(bucket.tokens, 2),
            "capacity":    self.capacity,
            "refill_rate": self.refill_rate,
        }


# ---------------------------------------------------------------------------
# Application-level singleton limiters
# ---------------------------------------------------------------------------

# Max 5 real orders per minute across all symbols (intraday typical)
ORDER_LIMITER = RateLimiter(rate=5, per_seconds=60, burst=2)

# Max 30 market-data requests per minute (Fyers allows 100/min)
DATA_LIMITER  = RateLimiter(rate=30, per_seconds=60, burst=10)

# Max 3 authentication attempts per 5 minutes (prevent lockout)
AUTH_LIMITER  = RateLimiter(rate=3, per_seconds=300, burst=1)
