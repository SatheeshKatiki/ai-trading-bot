"""Regression tests: fabricated prices must never reach the trading engine.

Background (root-caused 2026-09-09). `api_bridge.py` published bare
``{"lp", "chp"}`` dicts with no record of where the number came from, and
four separate paths were allowed to invent one:

  1. ``current_market_data``'s own literal seed (NIFTY 23820.35, ...),
     served as real from process start until the first genuine tick;
  2. ``websocket_broadcaster()``'s ``if not current_market_data:`` re-seed,
     with a *different* invented set (23971.88);
  3. ``get_sim_tick()``, a sine-ish wiggle used whenever the market was closed;
  4. v3.13.0's yfinance fallback, which manufactured five interpolated
     "micro-ticks" per second between real polls and wrote them into the live
     cache during market hours -- falling back to hardcoded 23840 / 57080 /
     76260 if yfinance itself failed.

This was not cosmetic. ``websocket_broadcaster`` published the snapshot as
``raw_ticks``; ``FyersBroker.stream_quotes()`` forwards every ``raw_ticks``
entry directly into ``trading_bot/main.py``'s ``on_tick()``, which has no
market-hours or data-quality gate of its own. Invented prices therefore
reached the candle aggregator, the strategies, entry/exit decisions and the
mark-to-market unrealised P&L.

`select_tradeable_ticks()` is the gate that now stands between a displayable
price and a tradeable one.
"""

from __future__ import annotations

import time

import pytest

import api_bridge as ab


NOW = 1_000_000.0


def _tick(lp, src, age_s=0.0, chp=0.0):
    return ab.make_tick(lp, chp, src, ts=NOW - age_s)


# ---------------------------------------------------------------------------
# No fabrication at rest
# ---------------------------------------------------------------------------

def test_cache_starts_empty():
    """An empty feed is an honest feed.

    The module used to boot with three hardcoded index prices already in the
    cache, so /api/quote, /ws/live and the option-Greeks spot fallback all
    served a fake NIFTY print before a single real tick arrived.
    """
    assert isinstance(ab.current_market_data, dict)
    # Nothing in the module may seed a price at import time. (Tests that run
    # earlier in the session may legitimately have written real entries, so
    # assert on provenance rather than emptiness.)
    for sym, tick in ab.current_market_data.items():
        assert "src" in tick, f"{sym} has no provenance -- fabricated?"


def test_make_tick_always_records_provenance_and_time():
    t = ab.make_tick(24_100.5, -0.4, ab.SRC_FYERS)
    assert t["lp"] == 24_100.5
    assert t["src"] == ab.SRC_FYERS
    assert abs(t["ts"] - time.time()) < 5


def test_no_simulated_tick_generator_remains():
    """`get_sim_tick` fabricated a price whenever the market was closed."""
    assert not hasattr(ab, "get_sim_tick")


# ---------------------------------------------------------------------------
# The engine gate
# ---------------------------------------------------------------------------

def test_authoritative_fresh_tick_is_tradeable():
    snap = {"NSE:NIFTY50-INDEX": _tick(24_100.0, ab.SRC_FYERS)}
    assert ab.select_tradeable_ticks(snap, NOW) == snap


def test_broker_rest_quote_is_tradeable():
    snap = {"NSE:NIFTY50-INDEX": _tick(24_100.0, ab.SRC_BROKER_REST)}
    assert "NSE:NIFTY50-INDEX" in ab.select_tradeable_ticks(snap, NOW)


def test_yfinance_quote_is_never_tradeable():
    """Delayed public quotes are display-only; they must not drive entries."""
    snap = {"NSE:NIFTY50-INDEX": _tick(24_100.0, ab.SRC_YFINANCE)}
    assert ab.select_tradeable_ticks(snap, NOW) == {}


def test_subscription_placeholder_is_never_tradeable():
    """A 0.0 'price' reaching on_tick() is worse than receiving no tick."""
    snap = {"NSE:NIFTY24500CE": _tick(0.0, ab.SRC_PENDING)}
    assert ab.select_tradeable_ticks(snap, NOW) == {}


def test_zero_price_from_an_authoritative_source_is_rejected():
    snap = {"NSE:NIFTY50-INDEX": _tick(0.0, ab.SRC_FYERS)}
    assert ab.select_tradeable_ticks(snap, NOW) == {}


def test_stale_tick_is_rejected():
    """A frozen upstream feed must not read as a flat market.

    This is the 2026-08-12 zombie-socket failure mode: the Fyers WebSocket
    reported itself connected for 46 minutes while delivering nothing.
    """
    snap = {"NSE:NIFTY50-INDEX": _tick(24_100.0, ab.SRC_FYERS, age_s=ab.MAX_TICK_AGE_S + 1)}
    assert ab.select_tradeable_ticks(snap, NOW) == {}


def test_tick_just_inside_the_freshness_window_is_kept():
    snap = {"NSE:NIFTY50-INDEX": _tick(24_100.0, ab.SRC_FYERS, age_s=ab.MAX_TICK_AGE_S - 0.5)}
    assert "NSE:NIFTY50-INDEX" in ab.select_tradeable_ticks(snap, NOW)


def test_legacy_untagged_tick_is_rejected():
    """Defence in depth: any dict without provenance is not tradeable.

    Guarantees that if some future code path reintroduces a bare
    {"lp", "chp"} literal, it fails closed instead of silently trading.
    """
    snap = {"NSE:NIFTY50-INDEX": {"lp": 23_820.35, "chp": -1.49}}
    assert ab.select_tradeable_ticks(snap, NOW) == {}


def test_malformed_entries_do_not_crash_the_gate():
    snap = {
        "A": None,
        "B": "not-a-dict",
        "C": {"lp": "abc", "chp": 0.0, "src": ab.SRC_FYERS, "ts": NOW},
        "D": {"lp": 24_100.0, "chp": 0.0, "src": ab.SRC_FYERS, "ts": "nope"},
        "E": _tick(24_100.0, ab.SRC_FYERS),
    }
    assert set(ab.select_tradeable_ticks(snap, NOW)) == {"E"}


def test_mixed_snapshot_passes_only_the_real_ones():
    """The realistic case: one live index, one delayed, one unsubscribed."""
    snap = {
        "NSE:NIFTY50-INDEX": _tick(24_100.0, ab.SRC_FYERS),
        "NSE:NIFTYBANK-INDEX": _tick(52_300.0, ab.SRC_YFINANCE),
        "NSE:NIFTY24500CE": _tick(0.0, ab.SRC_PENDING),
        "BSE:SENSEX-INDEX": _tick(79_000.0, ab.SRC_FYERS, age_s=120),
    }
    assert set(ab.select_tradeable_ticks(snap, NOW)) == {"NSE:NIFTY50-INDEX"}


@pytest.mark.parametrize("src", sorted(ab.TRADEABLE_SOURCES))
def test_tradeable_sources_are_exactly_the_authoritative_ones(src):
    assert src in (ab.SRC_FYERS, ab.SRC_BROKER_REST)


def test_yfinance_and_pending_are_excluded_from_tradeable_sources():
    assert ab.SRC_YFINANCE not in ab.TRADEABLE_SOURCES
    assert ab.SRC_PENDING not in ab.TRADEABLE_SOURCES
