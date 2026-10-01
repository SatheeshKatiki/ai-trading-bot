"""smc1 configuration: the JSON file is the source, loading is strict."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

import _bootstrap  # noqa: F401

from trading_bot.strategies.smc_rsi_frvp_options_v1.config import (
    DEFAULT_CONFIG_PATH,
    ConfigError,
    Smc1Config,
    load_config,
)


def _raw() -> dict:
    return json.loads(DEFAULT_CONFIG_PATH.read_text(encoding="utf-8"))


def _write(tmp_path: Path, data: dict) -> Path:
    p = tmp_path / "cfg.json"
    p.write_text(json.dumps(data), encoding="utf-8")
    return p


def test_the_shipped_file_equals_the_typed_defaults():
    assert load_config() == Smc1Config()


def test_spec_defaults_are_the_shipped_values():
    c = load_config()
    assert (c.pivots.m5.left, c.pivots.m15.left, c.pivots.h1.left) == (3, 3, 2)
    assert c.displacement.atr_mult == 1.5 and c.displacement.body_ratio == 0.6
    assert c.fvg.min_atr_mult == 0.25
    assert c.order_blocks.max_age_bars_15m == 40 and c.order_blocks.max_age_bars_5m == 75
    assert c.liquidity.eq_tol_pct == 0.03 and c.liquidity.sweep_reclaim_bars == 2
    assert c.frvp.value_area_pct == 0.70 and c.frvp.hvn_mult == 1.3 and c.frvp.lvn_mult == 0.5
    assert c.rsi.length == 14 and c.rsi.div_max_bars == 30
    assert c.regime.adx_min == 18.0 and c.regime.chop_lookback_bars_15m == 12
    assert c.structure.bias_max_age_bars_15m == 32


def test_comment_keys_are_ignored(tmp_path):
    data = _raw()
    data["fvg"]["_note"] = "anything"
    assert load_config(_write(tmp_path, data)) == Smc1Config()


@pytest.mark.parametrize("mutate, message", [
    (lambda d: d["fvg"].update(min_atr_mul=0.3), "unknown key"),
    (lambda d: d["rsi"].pop("length"), "missing"),
    (lambda d: d["rsi"].update(length="14"), "expected int"),
    (lambda d: d["structure"].update(use_1h_filter=1), "expected bool"),
    (lambda d: d.update(underlying="BANKNIFTY"), "not enabled in v1"),
    (lambda d: d["pivots"]["m5"].update(right=4), "symmetric"),
    (lambda d: d["order_blocks"].update(zone_mode="wick"), "zone_mode"),
    (lambda d: d["frvp"].update(smooth_bins=2), "odd"),
    (lambda d: d["frvp"].update(lvn_mult=1.5), "below"),
    (lambda d: d["session"].update(opening_range_end="09:10"), "open < opening_range_end"),
    (lambda d: d["session"].update(open="9am"), "HH:MM"),
    (lambda d: d["displacement"].update(body_ratio=1.5), "body_ratio"),
    (lambda d: d["liquidity"].update(sweep_min_atr_mult=-0.1), ">= 0"),
    (lambda d: d["rsi"].update(div_max_bars=0), ">= 1"),
    (lambda d: d.update(fvg=[1]), "expected an object"),
    (lambda d: d.update(timezone="UTC"), "Asia/Kolkata"),
    (lambda d: d["dealing_range"].update(ote_low=0.8), "OTE"),
    (lambda d: d["frvp"].update(bin_points=0.0), "bin_points"),
    (lambda d: d["frvp"].update(value_area_pct=1.0), "value_area_pct"),
    (lambda d: d["liquidity"].update(sweep_reclaim_bars=-1), "sweep_reclaim_bars"),
    (lambda d: d["pivots"]["h1"].update(left=0, right=0), "length must be"),
    (lambda d: d["session"].update(close="25:00"), "time of day"),
])
def test_bad_files_are_refused(tmp_path, mutate, message):
    data = copy.deepcopy(_raw())
    mutate(data)
    with pytest.raises(ConfigError, match=message):
        load_config(_write(tmp_path, data))


def test_an_int_is_accepted_where_a_float_is_expected(tmp_path):
    data = _raw()
    data["regime"]["adx_min"] = 18
    assert load_config(_write(tmp_path, data)).regime.adx_min == 18.0


def test_missing_and_malformed_files(tmp_path):
    with pytest.raises(ConfigError, match="not found"):
        load_config(tmp_path / "nope.json")
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    with pytest.raises(ConfigError, match="invalid JSON"):
        load_config(bad)


def test_the_package_registers_no_strategy_yet():
    """Phase B ships detectors only: auto-discovery must not register smc1."""
    from trading_bot.strategies.registry import registry
    assert "smc_rsi_frvp_options_v1" not in registry.registered_strategies
