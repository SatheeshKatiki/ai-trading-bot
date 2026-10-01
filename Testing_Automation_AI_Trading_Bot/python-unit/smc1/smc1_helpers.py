"""Bar builders shared by the smc1 detector tests."""

from __future__ import annotations

import random
from datetime import datetime, timedelta
from pathlib import Path
from typing import Iterable, Sequence

import _bootstrap  # noqa: F401  (side-effect: puts trading-system/ on sys.path)

from trading_bot.strategies.smc_rsi_frvp_options_v1.types import Bar

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "data"
T0 = datetime(2026, 6, 1, 9, 15)


def bar(i: int, o: float, h: float, low: float, c: float, v: float = 1000.0,
        minutes: int = 5, start: datetime = T0) -> Bar:
    """Bar ``i`` of a contiguous intraday series starting at ``start``."""
    return Bar(start + timedelta(minutes=minutes * i), o, h, low, c, v, minutes)


def bars(rows: Sequence[tuple[float, float, float, float]], minutes: int = 5,
         start: datetime = T0, volume: float = 1000.0) -> list[Bar]:
    return [bar(i, *r, v=volume, minutes=minutes, start=start) for i, r in enumerate(rows)]


def flat(n: int, price: float = 100.0, half_range: float = 0.5) -> list[tuple[float, float, float, float]]:
    return [(price, price + half_range, price - half_range, price)] * n


def random_walk(n: int, seed: int, minutes: int = 5, start: datetime = T0,
                price: float = 20000.0) -> list[Bar]:
    """Seeded synthetic OHLCV: deterministic, with trends, gaps and chop."""
    rng = random.Random(seed)
    out: list[Bar] = []
    p = price
    drift = 0.0
    for i in range(n):
        if i % 40 == 0:
            drift = rng.uniform(-3.0, 3.0)
        o = p + rng.gauss(0, 2.0)
        c = o + drift + rng.gauss(0, 12.0)
        h = max(o, c) + abs(rng.gauss(0, 6.0))
        low = min(o, c) - abs(rng.gauss(0, 6.0))
        out.append(Bar(start + timedelta(minutes=minutes * i), o, h, low, c,
                       float(rng.randint(500, 5000)), minutes))
        p = c
    return out


def load_fixture_5m() -> list[Bar]:
    import pandas as pd
    df = pd.read_csv(FIXTURES / "smc1_nifty_5m_2026-06.csv")
    df["datetime"] = pd.to_datetime(df["datetime"])
    return [Bar(r.datetime.to_pydatetime(), float(r.open), float(r.high), float(r.low),
                float(r.close), float(r.volume), 5) for r in df.itertuples()]


def feed(tracker: object, items: Iterable[Bar]) -> list[object]:
    return [tracker.update(b) for b in items]  # type: ignore[attr-defined]
