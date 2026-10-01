"""Typed configuration for smc1, loaded from a dedicated JSON file.

Owner decision D8 (DESIGN.md §12): one JSON file,
``trading-system/config/strategies/smc_rsi_frvp_options_v1.json``, rather
than ``smc1_*`` keys in the shared ``settings.json``. This module holds the
typed defaults; the JSON file holds the same values with explanations
(``_comment`` keys, ignored by the loader). A test asserts the two never
drift apart.

Loading is strict: an unknown key, a missing section or a wrongly typed value
raises :class:`ConfigError`. A typo in a threshold must stop the strategy,
not silently fall back to a default.

Phase B carries only the detector parameters (spec §3). Later phases add
their own sections.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, fields, is_dataclass
from pathlib import Path
from typing import Any, Mapping, TypeVar

#: The one instrument v1 may run on (owner decision Q3).
SUPPORTED_UNDERLYINGS: tuple[str, ...] = ("NIFTY",)

DEFAULT_CONFIG_PATH = (
    Path(__file__).resolve().parents[3] / "config" / "strategies" / "smc_rsi_frvp_options_v1.json"
)


class ConfigError(ValueError):
    """The configuration file is missing, malformed or out of range."""


@dataclass(frozen=True)
class PivotConfig:
    """Fractal pivot lengths (spec §3.1). Symmetric only -- see DESIGN.md §13."""

    left: int
    right: int


@dataclass(frozen=True)
class PivotsConfig:
    m5: PivotConfig = field(default_factory=lambda: PivotConfig(3, 3))
    m15: PivotConfig = field(default_factory=lambda: PivotConfig(3, 3))
    h1: PivotConfig = field(default_factory=lambda: PivotConfig(2, 2))


@dataclass(frozen=True)
class SessionConfig:
    open: str = "09:15"
    close: str = "15:30"
    opening_range_end: str = "09:45"


@dataclass(frozen=True)
class StructureConfig:
    """Bias rules (spec §3.3)."""

    require_bos_after_choch: bool = True
    bias_max_age_bars_15m: int = 32
    use_1h_filter: bool = True


@dataclass(frozen=True)
class DealingRangeConfig:
    """Premium / discount and the optional OTE tag (spec §3.4)."""

    use_ote: bool = False
    ote_low: float = 0.62
    ote_high: float = 0.79


@dataclass(frozen=True)
class DisplacementConfig:
    """Spec §3.5."""

    atr_mult: float = 1.5
    body_ratio: float = 0.6


@dataclass(frozen=True)
class FvgConfig:
    """Spec §3.6."""

    min_atr_mult: float = 0.25


@dataclass(frozen=True)
class OrderBlockConfig:
    """Spec §3.7."""

    zone_mode: str = "full"
    max_age_bars_15m: int = 40
    max_age_bars_5m: int = 75
    fresh_only: bool = True
    require_displacement: bool = True


@dataclass(frozen=True)
class LiquidityConfig:
    """Spec §3.8. ``eq_tol_pct`` is in PERCENT (0.03 means 0.03 %).

    ``eq_max_pivots_back`` is not in the spec: without a bound, any pivot from
    any time could pair into an "equal high". Added and documented in
    DESIGN.md §13.
    """

    eq_tol_pct: float = 0.03
    eq_tol_atr_mult: float = 0.1
    eq_max_pivots_back: int = 10
    sweep_min_atr_mult: float = 0.05
    sweep_reclaim_bars: int = 2


@dataclass(frozen=True)
class FrvpConfig:
    """Spec §3.9. ``history_sessions`` bounds the 1m buffer (not in the spec)."""

    bin_points: float = 5.0
    value_area_pct: float = 0.70
    hvn_mult: float = 1.3
    lvn_mult: float = 0.5
    smooth_bins: int = 3
    history_sessions: int = 5


@dataclass(frozen=True)
class RsiConfig:
    """Spec §3.10."""

    length: int = 14
    div_max_bars: int = 30


@dataclass(frozen=True)
class RegimeConfig:
    """Spec §3.11 / §3.12."""

    atr_length: int = 14
    adx_length: int = 14
    adx_min: float = 18.0
    chop_lookback_bars_15m: int = 12


@dataclass(frozen=True)
class Smc1Config:
    underlying: str = "NIFTY"
    timezone: str = "Asia/Kolkata"
    session: SessionConfig = field(default_factory=SessionConfig)
    pivots: PivotsConfig = field(default_factory=PivotsConfig)
    structure: StructureConfig = field(default_factory=StructureConfig)
    dealing_range: DealingRangeConfig = field(default_factory=DealingRangeConfig)
    displacement: DisplacementConfig = field(default_factory=DisplacementConfig)
    fvg: FvgConfig = field(default_factory=FvgConfig)
    order_blocks: OrderBlockConfig = field(default_factory=OrderBlockConfig)
    liquidity: LiquidityConfig = field(default_factory=LiquidityConfig)
    frvp: FrvpConfig = field(default_factory=FrvpConfig)
    rsi: RsiConfig = field(default_factory=RsiConfig)
    regime: RegimeConfig = field(default_factory=RegimeConfig)

    def __post_init__(self) -> None:
        validate(self)


_T = TypeVar("_T")


def _build(cls: type[_T], data: Any, path: str, defaults: _T) -> _T:
    if not isinstance(data, Mapping):
        raise ConfigError(f"{path}: expected an object, got {type(data).__name__}")
    known = [f.name for f in fields(cls)]  # type: ignore[arg-type]
    payload = {k: v for k, v in data.items() if not str(k).startswith("_")}
    unknown = sorted(set(payload) - set(known))
    if unknown:
        raise ConfigError(f"{path}: unknown key(s) {unknown}")
    kwargs: dict[str, Any] = {}
    for name in known:
        if name not in payload:
            raise ConfigError(f"{path}.{name}: missing (every parameter must be set in the file)")
        value = payload[name]
        default = getattr(defaults, name)
        if is_dataclass(default) and not isinstance(default, type):
            kwargs[name] = _build(type(default), value, f"{path}.{name}", default)
            continue
        expected = type(default)
        if expected is float and isinstance(value, int) and not isinstance(value, bool):
            value = float(value)
        if type(value) is not expected:
            raise ConfigError(
                f"{path}.{name}: expected {expected.__name__}, got {type(value).__name__} ({value!r})")
        kwargs[name] = value
    return cls(**kwargs)


def _hhmm(value: str, name: str) -> int:
    try:
        hh, mm = value.split(":")
        minutes = int(hh) * 60 + int(mm)
    except ValueError as exc:
        raise ConfigError(f"{name}: expected HH:MM, got {value!r}") from exc
    if not 0 <= minutes < 24 * 60:
        raise ConfigError(f"{name}: {value!r} is not a time of day")
    return minutes


def validate(cfg: Smc1Config) -> None:
    """Range checks. Raises :class:`ConfigError` on the first problem."""
    if cfg.underlying not in SUPPORTED_UNDERLYINGS:
        raise ConfigError(
            f"underlying {cfg.underlying!r} is not enabled in v1 (supported: {SUPPORTED_UNDERLYINGS})")
    if cfg.timezone != "Asia/Kolkata":
        raise ConfigError("timezone must be Asia/Kolkata")
    s_open = _hhmm(cfg.session.open, "session.open")
    s_close = _hhmm(cfg.session.close, "session.close")
    s_or = _hhmm(cfg.session.opening_range_end, "session.opening_range_end")
    if not s_open < s_or < s_close:
        raise ConfigError("session times must satisfy open < opening_range_end < close")
    for tf in ("m5", "m15", "h1"):
        p: PivotConfig = getattr(cfg.pivots, tf)
        if p.left != p.right:
            raise ConfigError(
                f"pivots.{tf}: left ({p.left}) != right ({p.right}); the reused "
                "detect_pivots is symmetric (DESIGN.md §13)")
        if p.left < 1:
            raise ConfigError(f"pivots.{tf}: length must be >= 1")
    positive_ints = {
        "structure.bias_max_age_bars_15m": cfg.structure.bias_max_age_bars_15m,
        "order_blocks.max_age_bars_15m": cfg.order_blocks.max_age_bars_15m,
        "order_blocks.max_age_bars_5m": cfg.order_blocks.max_age_bars_5m,
        "liquidity.eq_max_pivots_back": cfg.liquidity.eq_max_pivots_back,
        "frvp.history_sessions": cfg.frvp.history_sessions,
        "rsi.length": cfg.rsi.length,
        "rsi.div_max_bars": cfg.rsi.div_max_bars,
        "regime.atr_length": cfg.regime.atr_length,
        "regime.adx_length": cfg.regime.adx_length,
        "regime.chop_lookback_bars_15m": cfg.regime.chop_lookback_bars_15m,
    }
    for name, value in positive_ints.items():
        if value < 1:
            raise ConfigError(f"{name} must be >= 1 (got {value})")
    if cfg.liquidity.sweep_reclaim_bars < 0:
        raise ConfigError("liquidity.sweep_reclaim_bars must be >= 0")
    if cfg.frvp.smooth_bins < 1 or cfg.frvp.smooth_bins % 2 == 0:
        raise ConfigError("frvp.smooth_bins must be a positive odd number")
    non_negative = {
        "displacement.atr_mult": cfg.displacement.atr_mult,
        "fvg.min_atr_mult": cfg.fvg.min_atr_mult,
        "liquidity.eq_tol_pct": cfg.liquidity.eq_tol_pct,
        "liquidity.eq_tol_atr_mult": cfg.liquidity.eq_tol_atr_mult,
        "liquidity.sweep_min_atr_mult": cfg.liquidity.sweep_min_atr_mult,
        "regime.adx_min": cfg.regime.adx_min,
    }
    for name, fvalue in non_negative.items():
        if fvalue < 0:
            raise ConfigError(f"{name} must be >= 0 (got {fvalue})")
    if not 0 < cfg.displacement.body_ratio <= 1:
        raise ConfigError("displacement.body_ratio must be in (0, 1]")
    if cfg.order_blocks.zone_mode not in ("full", "body"):
        raise ConfigError("order_blocks.zone_mode must be 'full' or 'body'")
    if cfg.frvp.bin_points <= 0:
        raise ConfigError("frvp.bin_points must be > 0")
    if not 0 < cfg.frvp.value_area_pct < 1:
        raise ConfigError("frvp.value_area_pct must be in (0, 1)")
    if cfg.frvp.lvn_mult >= cfg.frvp.hvn_mult:
        raise ConfigError("frvp.lvn_mult must be below frvp.hvn_mult")
    if not 0 < cfg.dealing_range.ote_low < cfg.dealing_range.ote_high < 1:
        raise ConfigError("dealing_range OTE bounds must satisfy 0 < ote_low < ote_high < 1")


def load_config(path: Path | str | None = None) -> Smc1Config:
    """Read and validate the JSON file (default: :data:`DEFAULT_CONFIG_PATH`)."""
    p = Path(path) if path is not None else DEFAULT_CONFIG_PATH
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ConfigError(f"config file not found: {p}") from exc
    except json.JSONDecodeError as exc:
        raise ConfigError(f"{p}: invalid JSON ({exc})") from exc
    try:
        return _build(Smc1Config, raw, "config", Smc1Config())
    except TypeError as exc:  # pragma: no cover - guarded by the checks above
        raise ConfigError(f"{p}: {exc}") from exc


__all__ = [
    "ConfigError",
    "DEFAULT_CONFIG_PATH",
    "DealingRangeConfig",
    "DisplacementConfig",
    "FrvpConfig",
    "FvgConfig",
    "LiquidityConfig",
    "OrderBlockConfig",
    "PivotConfig",
    "PivotsConfig",
    "RegimeConfig",
    "RsiConfig",
    "SUPPORTED_UNDERLYINGS",
    "SessionConfig",
    "Smc1Config",
    "StructureConfig",
    "load_config",
    "validate",
]
