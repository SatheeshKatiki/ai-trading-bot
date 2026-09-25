"""Tier 1 -- causality. The tests that matter most for rsi_smc_options_buyer.

Every other test in this suite assumes the strategy only ever sees what was
knowable at the time. These are the tests that establish it. A failure here
invalidates every measurement taken from the strategy, so they are separated
from the rule tests deliberately.

Every availability point asserted below was MEASURED on real NIFTY 5-minute
data -- recompute on `df[:k]`, find the first `k` at which the object appears
-- and then compared against the value the implementation DERIVES:

    smc_bos / smc_choch / FVG series   prefix-stable
    FVG objects                        confirmation == bar_index (lag 0)
    Order Blocks                       confirmation == first same-direction
                                       structure event after the origin bar
    liquidity pools                    confirmation == last defining pivot
                                       + effective_internal_len

No SMC object is deleted for depending on future candles. Each one carries
its own confirmation bar, and the strategy may not read it before that bar;
the full retrospective picture stays available on the analytical surface for
charts and research.
"""
from __future__ import annotations

import pathlib

import numpy as np
import pandas as pd
import pytest

import _bootstrap  # noqa: F401

from shared.indicators.smart_money_concepts import LuxAlgoSMCConfig, calculate_smc
from trading_bot.strategies.rsi_smc_options_buyer import signal_engine, smc_lifecycle, structure
from trading_bot.strategies.rsi_smc_options_buyer.config import RsiSmcConfig

#: 1,200 real NIFTY 5-minute bars, committed so these tests never depend on
#: `trading-system/data/` (which is gitignored) or on a broker session.
FIXTURE = (pathlib.Path(__file__).resolve().parent / "fixtures" / "data"
           / "rsi_smc_NIFTY_5Min.csv")


@pytest.fixture(scope="module")
def nifty() -> pd.DataFrame:
    df = pd.read_csv(FIXTURE, parse_dates=["datetime"]).set_index("datetime")
    return df


@pytest.fixture(autouse=True)
def _clear_cache():
    structure.clear_cache()
    yield
    structure.clear_cache()


def _smc_config(cfg: RsiSmcConfig) -> LuxAlgoSMCConfig:
    return LuxAlgoSMCConfig(
        swing_points_length=cfg.swing_points_length,
        internal_length=cfg.internal_length,
        mode="Historical",
        color_candles=False,
    )


# ---------------------------------------------------------------------
# 1. Prefix stability of the per-bar series
# ---------------------------------------------------------------------

@pytest.mark.parametrize("k", [300, 500, 700, 850])
def test_per_bar_series_are_prefix_stable(nifty, k):
    """Truncating the frame must not change any earlier bar's value.

    This is what makes ONE full-frame `calculate_smc` call a valid per-bar
    signal source: the engine defers pivot consumption by
    `conf_idx = i - effective_swing_len`, so bar i never reflects bar i+1.
    """
    cfg = RsiSmcConfig()
    full, _ = calculate_smc(nifty, config=_smc_config(cfg))
    part, _ = calculate_smc(nifty.iloc[:k], config=_smc_config(cfg))

    for column in ("smc_bos", "smc_choch", "smc_bullish_fvg", "smc_bearish_fvg"):
        np.testing.assert_array_equal(
            full[column].to_numpy()[:k], part[column].to_numpy(),
            err_msg=f"{column} is not prefix-stable at k={k}: the adapter's "
                    f"whole causality argument rests on this",
        )


# ---------------------------------------------------------------------
# 2 & 3. Measured availability lags
# ---------------------------------------------------------------------

def _first_visible(df, obj_id, start_index, getter, cfg, span=30):
    """Smallest frame length at which `obj_id` first appears."""
    for k in range(start_index + 1, start_index + span):
        _, partial = calculate_smc(df.iloc[:k], config=_smc_config(cfg))
        if obj_id in {o.id for o in getter(partial)}:
            return k
    return None


def test_liquidity_pool_lag_equals_effective_internal_length(nifty):
    """Pools are knowable `effective_internal_len` bars after their last
    defining pivot -- and the adapter applies exactly that delay.

    `LiquidityPool` carries no availability index. The EQH/EQL builder
    iterates fractal pivots from `detect_pivots`, which needs `length` future
    bars, and applies none of the confirmation delay the BOS/CHoCH loop
    applies. Without the delay the strategy would read levels before they
    could have been known -- on a 5-minute chart, enough hindsight to
    manufacture an edge that does not exist.
    """
    cfg = RsiSmcConfig()
    _, analysis = calculate_smc(nifty, config=_smc_config(cfg))
    _, expected_lag = structure.effective_lengths(len(nifty), cfg)

    pools = [p for p in analysis.active_liquidity_pools
             if 300 < max(p.bar_indices) < 500]
    assert pools, "fixture should contain liquidity pools in the sampled range"

    measured = set()
    for pool in pools[:4]:
        last_pivot = max(pool.bar_indices)
        first = _first_visible(nifty, pool.id, last_pivot,
                               lambda a: a.active_liquidity_pools, cfg)
        assert first is not None, f"{pool.id} never appeared"
        measured.add(first - (last_pivot + 1))

    assert measured == {expected_lag}, (
        f"pool availability lag measured {measured}, adapter applies "
        f"{expected_lag}. If the engine's pivot handling changed, the "
        f"adapter's delay must change with it."
    )

    view = structure.build(nifty, cfg)
    assert view.pool_availability_delay == expected_lag


def test_fvg_lag_is_zero(nifty):
    """An FVG is knowable on its own `bar_index` -- it is printed by the
    third of the three candles that form it, so no delay is needed."""
    cfg = RsiSmcConfig()
    _, analysis = calculate_smc(nifty, config=_smc_config(cfg))
    gaps = [g for g in analysis.active_bullish_fvgs + analysis.active_bearish_fvgs
            if 400 < g.bar_index < 500]
    assert gaps, "fixture should contain FVGs in the sampled range"

    for gap in gaps[:4]:
        first = _first_visible(
            nifty, gap.id, gap.bar_index,
            lambda a: a.active_bullish_fvgs + a.active_bearish_fvgs, cfg, span=10)
        assert first == gap.bar_index + 1, (
            f"{gap.id} first visible at frame length {first}, expected "
            f"{gap.bar_index + 1} (lag 0)"
        )


def test_order_block_confirmation_is_derived_correctly(nifty):
    """An Order Block's confirmation bar is recoverable, and is recovered.

    The engine creates a block inside the same loop iteration as the
    structure break that produced it, scanning backwards for the source
    candle. So the confirmation bar is the first structure event, in the same
    direction, strictly after the block's origin bar. This asserts the
    DERIVED value equals the MEASURED one -- the frame length at which the
    block first appears.
    """
    cfg = RsiSmcConfig()
    analytical = structure.build_analytical(nifty, cfg)
    blocks = [o for o in analytical.objects
              if o.kind == smc_lifecycle.KIND_ORDER_BLOCK
              and 300 < o.origin_index < 600]
    assert blocks, "fixture should contain order blocks in the sampled range"

    for block in blocks[:5]:
        first = _first_visible(
            nifty, block.object_id, block.origin_index,
            lambda a: a.active_bullish_obs + a.active_bearish_obs, cfg, span=40)
        assert first is not None, f"{block.object_id} never appeared"
        assert block.confirmation_index == first - 1, (
            f"{block.object_id}: derived confirmation "
            f"{block.confirmation_index}, measured {first - 1}"
        )


def test_order_blocks_are_never_used_before_confirmation(nifty):
    """The causal mask must be False on every bar before confirmation."""
    cfg = RsiSmcConfig()
    view = structure.build(nifty, cfg)
    analytical = structure.build_analytical(nifty, cfg)
    blocks = [o for o in analytical.objects if o.kind == smc_lifecycle.KIND_ORDER_BLOCK]
    assert blocks

    earliest_confirmation = min(b.confirmation_index for b in blocks)
    assert not view.in_bull_ob[:earliest_confirmation].any()
    assert not view.in_bear_ob[:earliest_confirmation].any()

    for block in blocks[:20]:
        mask = block.active_mask(view.n)
        assert not mask[: block.confirmation_index].any(), (
            f"{block.object_id} usable before its confirmation bar")


def test_order_block_lifecycle_states_are_ordered(nifty):
    """CANDIDATE -> CONFIRMED -> MITIGATED / INVALIDATED, never backwards."""
    cfg = RsiSmcConfig()
    analytical = structure.build_analytical(nifty, cfg)
    blocks = [o for o in analytical.objects if o.kind == smc_lifecycle.KIND_ORDER_BLOCK]

    for block in blocks[:30]:
        assert block.state_at(max(0, block.origin_index - 1)) is smc_lifecycle.SmcState.CANDIDATE
        if block.confirmation_index < len(nifty):
            state = block.state_at(block.confirmation_index)
            assert state in (smc_lifecycle.SmcState.CONFIRMED,
                             smc_lifecycle.SmcState.MITIGATED,
                             smc_lifecycle.SmcState.INVALIDATED)
        if block.confirmation_index > block.origin_index:
            assert block.state_at(block.confirmation_index - 1) is smc_lifecycle.SmcState.CANDIDATE


# ---------------------------------------------------------------------
# 4. Forbidden-field protection
# ---------------------------------------------------------------------

@pytest.mark.parametrize("field", structure.FORBIDDEN_PER_BAR_FIELDS)
def test_forbidden_fields_raise(nifty, field):
    """Every end-of-frame scalar must fail loudly, not return a value.

    `calculate_smc` broadcasts `smc_trend` and `smc_equilibrium` -- the
    frame's FINAL values -- into DataFrame columns, which makes them look
    per-bar. Reading one per-bar injects the end-of-frame answer into every
    historical row.
    """
    view = structure.build(nifty, RsiSmcConfig())
    with pytest.raises(structure.LookAheadError):
        getattr(view, field)


def test_forbidden_columns_detected_in_a_frame(nifty):
    cfg = RsiSmcConfig()
    res_df, _ = calculate_smc(nifty, config=_smc_config(cfg))
    with pytest.raises(structure.LookAheadError):
        structure.assert_no_forbidden_columns(res_df)
    # A plain OHLCV frame is fine.
    structure.assert_no_forbidden_columns(nifty)


def test_unknown_attribute_still_raises_attribute_error(nifty):
    """The guard must not swallow ordinary typos into a LookAheadError."""
    view = structure.build(nifty, RsiSmcConfig())
    with pytest.raises(AttributeError):
        getattr(view, "definitely_not_a_field")


# ---------------------------------------------------------------------
# 5. Minimum-bars gate
# ---------------------------------------------------------------------

def test_below_minimum_bars_returns_all_zero_view(nifty):
    """No partial SMC inference below `6 * swing_points_length`.

    Under that, `calculate_smc` silently substitutes a shorter lookback
    (`effective_swing_len = min(swing, max(3, n // 6))`), so the structure
    reported is not the structure configured.
    """
    cfg = RsiSmcConfig()
    short = nifty.iloc[: cfg.min_bars - 1]
    view = structure.build(short, cfg)

    assert view.n == len(short)
    assert not view.bos.any() and not view.choch.any()
    assert not view.in_bull_fvg.any() and not view.in_bear_fvg.any()
    assert np.isnan(view.pool_high).all() and np.isnan(view.pool_low).all()


def test_below_minimum_bars_emits_no_signals(nifty):
    import trading_bot.strategies.rsi_smc_options_buyer as strategy
    cfg = RsiSmcConfig()
    signals = strategy.generate_signals(nifty.iloc[: cfg.min_bars - 1])
    assert (signals == 0).all()


# ---------------------------------------------------------------------
# 6. The direct no-look-ahead assertion
# ---------------------------------------------------------------------

@pytest.mark.parametrize("cut", [600, 700, 800])
def test_signals_do_not_change_when_future_bars_arrive(nifty, cut):
    """THE decisive test.

    A signal decided at bar i must be identical whether or not bars after i
    exist. Anything that fails this is look-ahead bias regardless of how the
    value was obtained.
    """
    import trading_bot.strategies.rsi_smc_options_buyer as strategy
    cfg = RsiSmcConfig()
    if cut < cfg.min_bars:
        pytest.skip("cut below the minimum-bars gate")

    structure.clear_cache()
    truncated = strategy.generate_signals(nifty.iloc[:cut]).to_numpy()
    structure.clear_cache()
    full = strategy.generate_signals(nifty).to_numpy()[:cut]

    mismatches = np.flatnonzero(truncated != full)
    assert mismatches.size == 0, (
        f"{mismatches.size} bar(s) changed once future bars arrived, first at "
        f"index {mismatches[:5].tolist()} -- this is look-ahead bias"
    )


# ---------------------------------------------------------------------
# 7. Cache behaviour (bounded, per-series, explicit eviction)
# ---------------------------------------------------------------------

def test_cache_recomputes_only_when_a_bar_closes(nifty):
    cfg = RsiSmcConfig()
    structure.clear_cache()

    structure.build(nifty, cfg, symbol="NIFTY")
    assert structure.cache_stats()["misses"] == 1

    for _ in range(5):
        structure.build(nifty, cfg, symbol="NIFTY")
    stats = structure.cache_stats()
    assert stats["misses"] == 1, "an unchanged frame must not recompute"
    assert stats["hits"] == 5

    structure.build(nifty.iloc[:-1], cfg, symbol="NIFTY")
    assert structure.cache_stats()["misses"] == 2, "a new bar must recompute"


def test_cache_is_bounded_and_evicts(nifty):
    cfg = RsiSmcConfig()
    structure.clear_cache()
    for i in range(structure._MAX_CACHE_ENTRIES + 4):
        structure.build(nifty, cfg, symbol=f"SYM{i}")
    stats = structure.cache_stats()
    assert stats["size"] <= structure._MAX_CACHE_ENTRIES
    assert stats["evictions"] >= 4


# ---------------------------------------------------------------------
# 8. Duplicate / non-monotonic timestamps
# ---------------------------------------------------------------------

def test_duplicate_timestamps_do_not_raise_and_stay_positional(nifty):
    """The live 5-minute cache can accumulate duplicate labels -- the defect
    behind the 2026-08-28 CPU livelock. Nothing here may index by label."""
    import trading_bot.strategies.rsi_smc_options_buyer as strategy
    duped = nifty.copy()
    index = duped.index.to_list()
    index[10] = index[9]
    index[200] = index[199]
    duped.index = pd.DatetimeIndex(index)

    signals = strategy.generate_signals(duped)
    assert len(signals) == len(duped)
    assert set(np.unique(signals.to_numpy())) <= {-1, 0, 1}
