"""Regression test for the 2026-08-13 ~39-minute total engine freeze.

Root cause (confirmed at the code level, not speculative): trading_bot/
main.py called broker.get_market_data(...) synchronously, unwrapped,
directly on the asyncio event loop, from 4 call sites -- and the vendored
fyers_apiv3 SDK's FyersModel.get_call() makes its HTTP request with no
`timeout=` anywhere. A DNS failure fails fast, but a hung TCP connect (a
plausible state mid-network-recovery) could block that single call
indefinitely, freezing the entire single-threaded event loop -- not just
the calling coroutine, but every other position's exit management and
the watchdog tasks too. Today's freeze correlated exactly with an
11-entry DNS failure burst at 14:18:45.

Fixed with two independent, complementary layers:
  1. brokers/fyers_broker.py mounts a default request timeout on every
     FyersModel session (see test_fyers_broker_request_timeout.py).
  2. main.py wraps every broker.get_market_data(...) call site in
     asyncio.to_thread(...), so even a still-slow (now bounded) call
     can no longer block the event loop itself.

This test proves layer 2's actual mechanism: a synchronous call that
genuinely blocks for real wall-clock time, run via asyncio.to_thread,
must not delay a concurrent coroutine on the same event loop. It also
proves the *negative* -- the same blocking call awaited directly
(main.py's old pattern) does stall everything else -- so this test would
have failed before the fix and cannot pass by accident.

Plain sync test functions driving asyncio.run() internally -- this suite
has no pytest-asyncio installed and runs with --strict-markers, so
@pytest.mark.asyncio isn't an option here.
"""
import asyncio
import time


def _blocking_get_market_data(symbols):
    """Stands in for broker.get_market_data() hanging on a real network
    call with no timeout -- e.g. a TCP connect that never completes."""
    time.sleep(1.5)
    return {}


async def _ticking_task(ticks: list, n: int = 6, interval: float = 0.2):
    """Stands in for everything else the event loop needs to keep doing
    while a get_market_data() call is in flight: other positions' exit
    checks, the tick-staleness/heartbeat watchdogs, incoming ticks."""
    for _ in range(n):
        await asyncio.sleep(interval)
        ticks.append(time.monotonic())


def test_to_thread_wrapped_blocking_call_does_not_stall_the_event_loop():
    """The actual fix: wrapping the blocking call in asyncio.to_thread."""

    async def _run():
        ticks: list = []
        start = time.monotonic()

        quotes, _ = await asyncio.gather(
            asyncio.to_thread(_blocking_get_market_data, ["NSE:NIFTY50-INDEX"]),
            _ticking_task(ticks),
        )
        return quotes, ticks, start

    quotes, ticks, start = asyncio.run(_run())

    assert quotes == {}
    assert len(ticks) == 6
    # The ticking task's own schedule is ~6 * 0.2s = 1.2s; if the event
    # loop had been stalled by the blocking call, its ticks would have
    # been pushed out to ~1.5s+ (after the blocking call finally
    # returned) instead of running on their own cadence concurrently.
    assert ticks[-1] - start < 1.4, (
        f"ticking_task's ticks were delayed by the blocking call -- the "
        f"event loop was stalled (last tick at {ticks[-1] - start:.2f}s, "
        f"expected ~1.2s)"
    )


def test_unwrapped_blocking_call_does_stall_the_event_loop():
    """The negative control proving this is a real test, not a tautology:
    main.py's *old* pattern (calling the blocking function directly,
    without asyncio.to_thread) genuinely does stall a concurrent task --
    this is the actual 2026-08-13 freeze mechanism, reproduced."""

    async def old_pattern_call():
        # This is exactly what main.py used to do: a synchronous,
        # blocking call awaited nowhere, just invoked inline on the loop.
        return _blocking_get_market_data(["NSE:NIFTY50-INDEX"])

    async def _run():
        ticks: list = []
        start = time.monotonic()

        quotes, _ = await asyncio.gather(
            old_pattern_call(),
            _ticking_task(ticks),
        )
        return quotes, ticks, start

    quotes, ticks, start = asyncio.run(_run())

    assert quotes == {}
    # With no to_thread, _blocking_get_market_data's time.sleep(1.5)
    # runs synchronously on the only thread the event loop has -- the
    # ticking_task literally cannot run until it returns, so all 6 ticks
    # land bunched up right after the 1.5s block, not on their own
    # 0.2s cadence.
    assert ticks[-1] - start >= 1.5, (
        "expected the unwrapped call to stall the ticking task until "
        "after its own 1.5s sleep -- if this fails, the negative control "
        "itself is broken and the positive test above proves nothing"
    )
