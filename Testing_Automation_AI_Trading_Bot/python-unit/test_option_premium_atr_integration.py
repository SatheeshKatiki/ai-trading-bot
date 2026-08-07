"""Integration tests for the option-premium ATR architecture end-to-end:
CandleAggregator.add_tick() (feeding real premium samples) ->
get_latest_dataframe() (building real option candles) ->
resolve_option_atr() (computing a premium-scale ATR) ->
_stale_option_candle_symbols() (cleanup once a position closes).

2026-08-07 audit §2.1 / docs/ATR_TRAILING_STOP_DESIGN_2026-08-07.md.
Uses the REAL CandleAggregator class from trading_bot.main, not a mock --
this is the actual object main.py's live tick loop uses.
"""
import time

import _bootstrap  # noqa: F401  (side-effect: puts trading-system/ on sys.path)

from trading_bot.main import CandleAggregator, _stale_option_candle_symbols
from shared.risk.option_atr import resolve_option_atr, MIN_CANDLES_FOR_OPTION_ATR


INDEX_SYMBOL = "NSE:NIFTY50-INDEX"
OPTION_SYMBOL = "NSE:NIFTY2681126950PE"


def _feed_option_ticks(aggregator: CandleAggregator, n_minutes: int, base_premium: float = 120.0, ticks_per_minute: int = 3):
    """Feed synthetic premium samples spanning n_minutes distinct 1-minute
    candle intervals, mimicking the ~1/sec throttled real fetch.

    Uses a fixed, minute-boundary-aligned base timestamp rather than live
    time.time() -- otherwise the sub-tick offsets below can spuriously
    cross a minute boundary depending on the real wall-clock seconds at
    test-run time, making candle counts flaky.
    """
    start = 1_754_550_000.0  # arbitrary, exactly on a minute boundary
    assert start % 60 == 0
    premium = base_premium
    for minute in range(n_minutes):
        for sub in range(ticks_per_minute):
            premium += 0.05 * ((-1) ** sub)  # small in-candle wiggle
            aggregator.add_tick({
                "timestamp": start + minute * 60 + sub * 15,
                "symbol": OPTION_SYMBOL,
                "ltp": max(premium, 0.5),
                "volume": 0,
            })


def test_feeding_option_ticks_builds_a_real_candle_series():
    aggregator = CandleAggregator([INDEX_SYMBOL], "1 Min")
    _feed_option_ticks(aggregator, n_minutes=MIN_CANDLES_FOR_OPTION_ATR + 1)

    option_df = aggregator.get_latest_dataframe(OPTION_SYMBOL)
    # The aggregator only finalizes a candle once the NEXT interval's tick
    # arrives, so N+1 minutes of feed produces N finalized candles.
    assert len(option_df) == MIN_CANDLES_FOR_OPTION_ATR
    assert set(["open", "high", "low", "close", "volume"]).issubset(option_df.columns)


def test_option_ticks_never_contaminate_the_index_symbols_candles():
    """Isolation: feeding option premium samples through the shared
    aggregator must never affect the underlying index's own candle
    series used for strategy signal generation."""
    aggregator = CandleAggregator([INDEX_SYMBOL], "1 Min")
    aggregator.add_tick({"timestamp": time.time(), "symbol": INDEX_SYMBOL, "ltp": 26950.0, "volume": 1000})

    _feed_option_ticks(aggregator, n_minutes=MIN_CANDLES_FOR_OPTION_ATR + 1)

    index_df = aggregator.get_latest_dataframe(INDEX_SYMBOL)
    # Only the one index tick was ever fed -- no candle finalized yet
    # (needs a second, later tick to close the first interval), and
    # critically, no option-scale (₹15-2400) values leaked into it.
    assert index_df.empty or (index_df["close"] > 10_000).all()


def test_cold_start_transitions_to_warm_option_atr_as_candles_accumulate():
    """End-to-end: right after entry (no candles yet) the resolver must
    use the premium-banded proxy; once enough of the option's own candle
    history has been fed through the real aggregator, it must switch to
    a genuine option-premium ATR -- and never, at any point, an
    index-point-scale value."""
    aggregator = CandleAggregator([INDEX_SYMBOL], "1 Min")
    premium = 120.0

    # Immediately after entry: no candles yet.
    option_df = aggregator.get_latest_dataframe(OPTION_SYMBOL)
    decision_cold = resolve_option_atr(option_df, premium)
    assert decision_cold.source == "premium_proxy"
    assert decision_cold.atr_value < premium  # sane premium-scale magnitude

    # Feed enough real premium history to warm up.
    _feed_option_ticks(aggregator, n_minutes=MIN_CANDLES_FOR_OPTION_ATR + 1, base_premium=premium)
    option_df = aggregator.get_latest_dataframe(OPTION_SYMBOL)
    decision_warm = resolve_option_atr(option_df, premium)
    assert decision_warm.source == "option_atr"
    assert decision_warm.atr_value > 0
    # Sanity: nowhere near the ~100-375 index-point magnitude seen in
    # real NIFTY data -- this is a ₹120 contract's own ATR.
    assert decision_warm.atr_value < premium


def test_sweep_evicts_the_option_symbol_after_the_aggregator_has_tracked_it():
    aggregator = CandleAggregator([INDEX_SYMBOL], "1 Min")
    _feed_option_ticks(aggregator, n_minutes=5)
    assert OPTION_SYMBOL in aggregator.candles

    # Position still open -- must be kept.
    stale = _stale_option_candle_symbols(list(aggregator.candles.keys()), [OPTION_SYMBOL])
    assert OPTION_SYMBOL not in stale

    # Position closed -- must be evicted, and the index symbol (if
    # present) must never be swept.
    stale = _stale_option_candle_symbols(list(aggregator.candles.keys()), [])
    assert OPTION_SYMBOL in stale
    for sym in stale:
        aggregator.candles.pop(sym, None)
    assert OPTION_SYMBOL not in aggregator.candles


def test_no_duplicate_candle_growth_from_repeated_same_second_ticks():
    """Multiple ticks landing in the same candle interval must merge into
    ONE candle (via high/low/close aggregation), not create duplicate
    rows -- confirms this reuses the aggregator's existing, already-tested
    interval-bucketing rather than any new/duplicate logic."""
    aggregator = CandleAggregator([INDEX_SYMBOL], "1 Min")
    start = time.time()
    for i in range(20):
        aggregator.add_tick({
            "timestamp": start + i,  # all within the same 1-minute bucket
            "symbol": OPTION_SYMBOL,
            "ltp": 100.0 + i * 0.1,
            "volume": 0,
        })
    # Force the bucket to finalize by advancing into the next interval.
    aggregator.add_tick({"timestamp": start + 61, "symbol": OPTION_SYMBOL, "ltp": 102.0, "volume": 0})

    option_df = aggregator.get_latest_dataframe(OPTION_SYMBOL)
    assert len(option_df) == 1  # exactly one finalized candle, not 20
