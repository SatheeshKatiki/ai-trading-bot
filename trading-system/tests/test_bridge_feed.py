"""The engine's /ws/live reader must keep up with api_bridge's 20 Hz snapshots.

2026-10-14: 116 disconnects, one every ~97s. The reader processed every frame
before reading the next; when processing was slower than the frame rate the
bridge's sends blocked and the keepalive ping failed. The server below is the
bridge's own stack (FastAPI + uvicorn, send_json at 20 Hz).
"""
from __future__ import annotations

import asyncio
import json
import socket
import threading
import time

import pytest
import uvicorn
import websockets
from fastapi import FastAPI, WebSocket

from brokers.fyers_broker import consume_bridge_frames

SYMBOLS = ("NSE:NIFTY50-INDEX", "NSE:NIFTYBANK-INDEX", "BSE:SENSEX-INDEX")
PING = dict(ping_interval=0.5, ping_timeout=1.5)
RUN_S = 12.0
WORK_PER_TICK_S = 0.06          # 180 ms of blocking work per 50 ms frame


def _payload(seq: int) -> dict:
    # ~130 KB, like a full bridge snapshot with signals and trend data.
    return {"seq": seq,
            "raw_ticks": {s: {"lp": 100.0 + seq, "ts": time.time()} for s in SYMBOLS},
            "signalsData": {"trend": list(range(20000))}}


@pytest.fixture(scope="module")
def bridge_url():
    app = FastAPI()

    @app.websocket("/ws/live")
    async def live(ws: WebSocket):
        await ws.accept()
        seq = 0
        try:
            while True:
                seq += 1
                await ws.send_json(_payload(seq))
                await asyncio.sleep(0.05)
        except Exception:
            pass

    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="critical"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 10
    while not server.started and time.monotonic() < deadline:
        time.sleep(0.05)
    yield f"ws://127.0.0.1:{port}/ws/live"
    server.should_exit = True
    thread.join(timeout=5)


async def _slow_tick(tick):
    time.sleep(WORK_PER_TICK_S)          # the strategy stack is synchronous


async def _old_reader(ws, on_tick):
    """The loop this replaced: process each frame before reading the next."""
    while True:
        msg = json.loads(await ws.recv())
        for sym, val in msg["raw_ticks"].items():
            await on_tick({"symbol": sym, "ltp": val["lp"]})


async def _run(url, consumer, on_tick=_slow_tick) -> str:
    try:
        async with websockets.connect(url, **PING) as ws:
            await asyncio.wait_for(consumer(ws, on_tick), timeout=RUN_S)
    except asyncio.TimeoutError:
        return "survived"
    except Exception as exc:
        return f"dropped: {type(exc).__name__}"
    return "ended"


def test_the_old_reader_is_dropped_by_a_slow_handler(bridge_url):
    """Control: proves this setup reproduces the failure."""
    assert asyncio.run(_run(bridge_url, _old_reader)).startswith("dropped")


def test_the_engine_reader_keeps_the_connection_under_a_slow_handler(bridge_url):
    assert asyncio.run(_run(bridge_url, consume_bridge_frames)) == "survived"


class _ScriptedWS:
    """recv() hands out queued frames, then raises like a closed socket."""

    def __init__(self, frames, close_after: bool = True):
        self._frames = list(frames)
        self._close_after = close_after

    async def recv(self):
        await asyncio.sleep(0)
        if self._frames:
            return self._frames.pop(0)
        if self._close_after:
            raise websockets.ConnectionClosedOK(None, None)
        await asyncio.sleep(3600)


def _frame(seq: int) -> str:
    return json.dumps({"raw_ticks": {"NSE:NIFTY50-INDEX": {"lp": 100.0 + seq, "ts": 0}}})


def test_frames_superseded_while_processing_are_skipped():
    seen = []

    async def slow(tick):
        seen.append(tick["ltp"])
        await asyncio.sleep(0.05)          # all ten frames arrive meanwhile

    async def run():
        ws = _ScriptedWS([_frame(i) for i in range(10)], close_after=False)
        try:
            await asyncio.wait_for(consume_bridge_frames(ws, slow), timeout=0.5)
        except asyncio.TimeoutError:
            pass

    asyncio.run(run())
    assert seen[0] == 100.0 and seen[-1] == 109.0
    assert len(seen) < 10


def test_a_closed_connection_raises_after_the_last_frame():
    """The last frame is still acted on, and the consumer returns control to
    the reconnect loop instead of waiting forever."""
    seen = []

    async def tick(t):
        seen.append(t["ltp"])

    async def run():
        await asyncio.wait_for(consume_bridge_frames(_ScriptedWS([_frame(1)]), tick), timeout=2)

    with pytest.raises(websockets.ConnectionClosed):
        asyncio.run(run())
    assert seen == [101.0]
