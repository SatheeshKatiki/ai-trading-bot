"""Premium-banded initial stop-loss for option buying.

Root cause this exists for
--------------------------
The entry path priced every stop as a flat percentage of premium
(``stoploss_pct``), which does not survive contact with an option book. The
live setting was 0.45%: on a ₹120 premium that is a **₹0.54** stop — inside
the bid/ask spread of most NIFTY strikes, so the position was effectively
guaranteed to be stopped out by noise rather than by being wrong. The same
single percentage is simultaneously far too wide for a ₹5 lottery strike
(0.45% = ₹0.02, meaningless) and far too tight for a ₹300 deep-ITM contract.

Option premium is not a linear instrument: the *rupee* volatility of a
contract scales with its own price, but the *percentage* volatility falls as
the contract goes deeper ITM. A single percentage cannot express that; a band
table can. Cheap OTM strikes need a wide percentage (a ₹5 option routinely
moves 40%), expensive ITM strikes need a narrow one (a ₹300 option moving 40%
is a market event, not noise).

Design
------
One resolver, one table, driven entirely from settings. Bands and the rule
for picking a value inside a band are configuration, not code, so tuning them
never requires touching the entry path.

Within a band the stop is **linearly interpolated** rather than fixed at a
midpoint. That gives a stop that rises continuously with premium instead of
stepping at each boundary — and it makes the ₹150-250 band hand over to the
percentage band exactly: interpolation lands on ₹30 at ₹250, and 12% of ₹250
is also ₹30.

This module is pure: no I/O, no broker calls, no logging side effects. It is
called once per entry, and everything after that handoff (trailing stop,
SmartExitEngine, partial booking) owns the position unchanged.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Optional, Sequence

__all__ = [
    "StopLossBand",
    "StopLossDecision",
    "DEFAULT_BANDS",
    "DEFAULT_DYNAMIC_BAND",
    "resolve_initial_stop",
    "resolve_stop_points",
]


@dataclass(frozen=True)
class StopLossBand:
    """One premium band and the rupee stop range that applies inside it.

    ``upper`` is exclusive, ``lower`` inclusive, so the bands tile the number
    line without overlap or gaps.
    """

    lower: float
    upper: float
    min_points: float
    max_points: float

    @property
    def label(self) -> str:
        if self.upper == float("inf"):
            return f">₹{self.lower:g}"
        return f"₹{self.lower:g}-{self.upper:g}"


@dataclass(frozen=True)
class StopLossDecision:
    """The resolved stop for one entry, with everything needed to log it."""

    sl_price: float          # absolute premium level the stop sits at
    sl_points: float         # rupees of premium risked per unit
    sl_pct: float            # sl_points as a % of entry premium
    band_label: str          # which band produced it, for logs/journal
    method: str              # "banded" | "dynamic_pct" | "clamped"
    clamped: bool            # True if the premium floor capped the stop
    is_tradeable: bool = True
    """False when the premium is too small to carry a real stop.

    A contract priced at one or two ticks cannot have a stop placed below it
    that is both positive and distinguishable from the entry — the stop would
    sit at or within a tick of entry, which is not risk management, it is an
    instant stop-out. The caller must skip the entry rather than trade it;
    silently returning a degenerate stop would look like it worked.
    """


#: Fixed rupee bands. Each entry is (lower, upper, min_points, max_points).
#: Interpolated across the band: at ``lower`` the stop is ``min_points``, at
#: ``upper`` it is ``max_points``.
DEFAULT_BANDS: tuple[StopLossBand, ...] = (
    StopLossBand(0.0, 10.0, 2.0, 3.0),
    StopLossBand(10.0, 20.0, 3.0, 5.0),
    StopLossBand(20.0, 50.0, 5.0, 8.0),
    StopLossBand(50.0, 100.0, 10.0, 15.0),
    StopLossBand(100.0, 150.0, 15.0, 20.0),
    StopLossBand(150.0, 250.0, 20.0, 30.0),
)

#: Above the last fixed band the stop becomes a percentage of premium,
#: tapering from ``start_pct`` at the band's lower edge to ``end_pct`` at
#: ``taper_to``. Starting at 12% makes it continuous with the ₹150-250 band
#: (12% of ₹250 = ₹30 = that band's max_points).
DEFAULT_DYNAMIC_BAND: dict[str, float] = {
    "lower": 250.0,
    "start_pct": 12.0,
    "end_pct": 10.0,
    "taper_to": 500.0,
}

#: A stop can never risk more than this share of the premium. Guards the
#: cheap end of the table: a ₹2.5 option with a ₹2 band stop would otherwise
#: resolve to a stop price of ₹0.50, i.e. risking 80% of the position on one
#: tick of a near-worthless contract.
DEFAULT_MAX_SL_PCT_OF_PREMIUM = 60.0

#: Exchange tick size for NSE option premiums. Stops are rounded to this so
#: the price is actually placeable as an SL-M trigger.
DEFAULT_TICK_SIZE = 0.05


def _coerce_bands(raw: Optional[Sequence[Any]]) -> tuple[StopLossBand, ...]:
    """Build the band table from settings, falling back to the defaults.

    Accepts the JSON-friendly shape settings files use::

        [{"lower": 0, "upper": 10, "min_points": 2, "max_points": 3}, ...]

    A malformed table falls back to :data:`DEFAULT_BANDS` rather than raising:
    this runs inside the live entry path, and a typo in a config file must not
    be able to stop the engine from trading. The caller logs the fallback.
    """
    if not raw:
        return DEFAULT_BANDS

    bands: list[StopLossBand] = []
    try:
        for item in raw:
            if isinstance(item, Mapping):
                bands.append(
                    StopLossBand(
                        lower=float(item["lower"]),
                        upper=float(item.get("upper", float("inf"))),
                        min_points=float(item["min_points"]),
                        max_points=float(item.get("max_points", item["min_points"])),
                    )
                )
            else:  # (lower, upper, min_points, max_points) tuple form
                lower, upper, min_points, max_points = item
                bands.append(
                    StopLossBand(float(lower), float(upper), float(min_points), float(max_points))
                )
    except (KeyError, TypeError, ValueError, IndexError):
        return DEFAULT_BANDS

    if not bands:
        return DEFAULT_BANDS
    return tuple(sorted(bands, key=lambda b: b.lower))


def _interpolate(band: StopLossBand, premium: float, mode: str) -> float:
    """Pick the stop distance inside ``band`` for ``premium``."""
    if mode == "min":
        return band.min_points
    if mode == "max":
        return band.max_points
    if mode == "mid":
        return (band.min_points + band.max_points) / 2.0

    # "interpolate" (default): continuous across the band.
    span = band.upper - band.lower
    if span <= 0 or band.upper == float("inf"):
        return band.max_points
    position = (premium - band.lower) / span
    position = min(1.0, max(0.0, position))
    return band.min_points + position * (band.max_points - band.min_points)


def _dynamic_points(premium: float, cfg: Mapping[str, Any]) -> float:
    """Percentage-based stop for premiums above the last fixed band.

    Tapers from ``start_pct`` to ``end_pct`` as premium rises: an expensive
    contract is proportionally less volatile, so it needs proportionally less
    room. Held flat at ``end_pct`` beyond ``taper_to``.
    """
    start_pct = float(cfg.get("start_pct", DEFAULT_DYNAMIC_BAND["start_pct"]))
    end_pct = float(cfg.get("end_pct", DEFAULT_DYNAMIC_BAND["end_pct"]))
    lower = float(cfg.get("lower", DEFAULT_DYNAMIC_BAND["lower"]))
    taper_to = float(cfg.get("taper_to", DEFAULT_DYNAMIC_BAND["taper_to"]))

    if taper_to <= lower:
        pct = end_pct
    else:
        position = min(1.0, max(0.0, (premium - lower) / (taper_to - lower)))
        pct = start_pct + position * (end_pct - start_pct)

    return premium * (pct / 100.0)


def _round_to_tick(value: float, tick: float) -> float:
    if tick <= 0:
        return value
    return round(round(value / tick) * tick, 2)


def resolve_stop_points(premium: float, settings: Optional[Mapping[str, Any]] = None) -> float:
    """Rupees of premium risked per unit for ``premium``. See
    :func:`resolve_initial_stop` for the full decision."""
    return resolve_initial_stop(premium, settings).sl_points


def resolve_initial_stop(
    premium: float,
    settings: Optional[Mapping[str, Any]] = None,
) -> StopLossDecision:
    """Resolve the initial stop-loss for an option entry at ``premium``.

    Parameters
    ----------
    premium
        The option's entry premium. Must be > 0 — the caller already refuses
        to trade without a real live premium (see main.py's entry path), so a
        non-positive value here is a programming error and raises.
    settings
        The live settings mapping. Recognised keys, all optional:

        ``option_sl_bands``
            Band table (see :func:`_coerce_bands`).
        ``option_sl_band_mode``
            ``"interpolate"`` (default) | ``"min"`` | ``"mid"`` | ``"max"``.
        ``option_sl_dynamic``
            Percentage band config for premiums above the table.
        ``option_sl_max_pct_of_premium``
            Hard ceiling on how much of the premium a stop may risk.
        ``option_sl_tick_size``
            Tick to round the resulting stop price to.

    Returns
    -------
    StopLossDecision
        Both the absolute stop price and the rupee distance, plus the band
        label and method for logging and the trade journal.
    """
    if premium <= 0:
        raise ValueError(f"premium must be positive, got {premium!r}")

    settings = settings or {}
    bands = _coerce_bands(settings.get("option_sl_bands"))
    mode = str(settings.get("option_sl_band_mode", "interpolate")).lower()
    dynamic_cfg = settings.get("option_sl_dynamic") or DEFAULT_DYNAMIC_BAND
    max_pct = float(
        settings.get("option_sl_max_pct_of_premium", DEFAULT_MAX_SL_PCT_OF_PREMIUM)
    )
    tick = float(settings.get("option_sl_tick_size", DEFAULT_TICK_SIZE))

    band = next((b for b in bands if b.lower <= premium < b.upper), None)

    if band is not None:
        sl_points = _interpolate(band, premium, mode)
        band_label = band.label
        method = "banded"
    else:
        # Above the fixed table — percentage-based, tapering.
        sl_points = _dynamic_points(premium, dynamic_cfg)
        band_label = f">₹{float(dynamic_cfg.get('lower', DEFAULT_DYNAMIC_BAND['lower'])):g}"
        method = "dynamic_pct"

    # Premium floor: never risk more than max_pct of the contract's value.
    clamped = False
    ceiling = premium * (max_pct / 100.0)
    if sl_points > ceiling:
        sl_points = ceiling
        clamped = True
        method = "clamped"

    sl_price = _round_to_tick(premium - sl_points, tick)

    # Rounding must never push the stop to or through zero, which would make
    # it unplaceable and (worse) read as "no stop" to the exit checks, all of
    # which guard on `stop_loss > 0`.
    if sl_price < tick:
        sl_price = tick
        clamped = True

    sl_points = round(premium - sl_price, 2)

    # A stop must be at least one tick below entry to mean anything. Below
    # ~2 ticks of premium that is arithmetically impossible, so the contract
    # is reported as untradeable instead of being given a stop at its own
    # entry price.
    is_tradeable = sl_points >= tick and sl_price > 0

    return StopLossDecision(
        sl_price=sl_price,
        sl_points=sl_points,
        sl_pct=round(sl_points / premium * 100.0, 2),
        band_label=band_label,
        method=method,
        clamped=clamped,
        is_tradeable=is_tradeable,
    )
