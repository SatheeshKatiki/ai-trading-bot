"""Canonical immutable research schema for observed option data.

RESEARCH INFRASTRUCTURE. Nothing here is imported by ``trading_bot/``,
``brokers/`` or ``api_bridge.py``, and nothing here places an order.

Why this module exists
----------------------
Phases 8-11 established that this repository holds no historical option data.
The only real option quotes it can obtain are LIVE, from the broker chain
endpoint, and they are never written down. Everything needed to answer the
options question already flows through the process once a day -- it is simply
discarded. This schema is the shape it has to be kept in.

The one rule that matters
-------------------------
**An observed value is never overwritten by a modelled one.** Every field
carries its own provenance, and a record whose provenance is SYNTHETIC can
never be counted as evidence. :data:`REQUIRE_OBSERVED_OPTION_DATA` makes the
research harness fail closed rather than quietly substitute a model.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Dict, Optional

#: Schema version. Bumped on any field change; stored on every record so a
#: frozen dataset can always be read back with the reader that wrote it.
SCHEMA_VERSION = "1.2.0"   # 1.2.0: India VIX on the underlying (Phase 14)

#: Version of the COLLECTOR that produced a record (Phase 13 sec19). Bumped
#: when collection behaviour changes in a way a researcher must know about.
#: Distinct from SCHEMA_VERSION: the shape can be stable while the way the
#: values were obtained changes.
RECORDER_VERSION = "1.1.0"

#: Version of the normalisation rules (payload -> OptionQuote). Bumped when
#: the mapping or the quality rules change, so a mixed dataset stays readable.
NORMALIZATION_VERSION = "1.1.0"

#: Research-time guard (Phase 12 sec3). Any future options-validation harness
#: must assert this and refuse to run against modelled premiums. It exists so
#: the failure mode is a loud stop, not a silent substitution.
REQUIRE_OBSERVED_OPTION_DATA = True


class Quality(str, Enum):
    """Per-observation verdict. Only VALID may enter economic validation."""

    VALID = "VALID"
    STALE = "STALE"            # quote older than the freshness bound
    INVALID = "INVALID"        # crossed, negative, zero-bid/ask, impossible
    MISSING = "MISSING"        # expected and absent
    SYNTHETIC = "SYNTHETIC"    # modelled, never observed


class Provenance(str, Enum):
    """Where a single field's value came from."""

    OBSERVED = "OBSERVED"      # straight from the exchange/broker payload
    DERIVED = "DERIVED"        # computed from observed inputs (e.g. IV solved
                               # from a real premium) -- reproducible, but not
                               # itself a market observation
    INFERRED = "INFERRED"      # guessed from context; never used for economics
    UNAVAILABLE = "UNAVAILABLE"


#: Provenance of every option-leg field as this repository's broker actually
#: supplies it. Verified against `api_bridge._fetch_real_option_chain` and
#: `_chain_leg`, not from comments.
FIELD_PROVENANCE: Dict[str, Provenance] = {
    "last_price": Provenance.OBSERVED,
    "bid": Provenance.OBSERVED,
    "ask": Provenance.OBSERVED,
    "volume": Provenance.OBSERVED,
    "open_interest": Provenance.OBSERVED,
    "oi_change": Provenance.OBSERVED,
    "strike": Provenance.OBSERVED,
    "expiry": Provenance.OBSERVED,
    "option_type": Provenance.OBSERVED,
    "underlying_price": Provenance.OBSERVED,
    # India VIX is a real broker value (api_bridge serves it from
    # `indiavixData`), not a model output. It is OBSERVED when present and
    # simply absent when the broker does not send it -- never interpolated.
    "india_vix": Provenance.OBSERVED,
    # The broker does NOT publish IV or Greeks. api_bridge solves IV from the
    # real premium and derives Greeks from that. Reproducible from stored
    # inputs, so they are recorded as DERIVED and the raw inputs are kept.
    "implied_volatility": Provenance.DERIVED,
    "delta": Provenance.DERIVED,
    "gamma": Provenance.DERIVED,
    "theta": Provenance.DERIVED,
    "vega": Provenance.DERIVED,
}

#: A quote older than this at capture time is STALE, not VALID.
DEFAULT_STALE_SECONDS = 90.0

#: **The broker chain carries no per-leg quote timestamp.** Verified against
#: ``api_bridge._chain_leg``, which maps ltp/bid/ask/oi/volume and nothing
#: temporal. Exchange-supplied quote age is therefore UNAVAILABLE and this
#: recorder does not invent one -- ``quote_age_seconds`` stays ``None``.
#:
#: What IS observable is whether a contract quote CHANGED between two
#: consecutive snapshots of our own. A leg whose ltp, bid, ask, volume and OI
#: are all identical across several minutes of an open market is not trading.
#: That is derived from stored observations, reproducible from them, and
#: recorded separately as ``unchanged_for_seconds`` so it is never confused
#: with a real exchange timestamp.
DEFAULT_UNCHANGED_STALE_SECONDS = 600.0


class SessionStatus(str, Enum):
    """Verdict for a whole instrument-session (Phase 13 sec13)."""

    COMPLETE = "COMPLETE"        # meets every coverage and quality bound
    INCOMPLETE = "INCOMPLETE"    # real data, but gaps -- usable with care
    UNUSABLE = "UNUSABLE"        # synthetic, corrupt, or too sparse to trust
    EMPTY = "EMPTY"              # nothing collected


@dataclass(frozen=True)
class OptionQuote:
    """One option leg, as observed at one moment.

    ``event_time`` is when the market state existed; ``available_at`` is when
    this process could first have known it. They are distinct on purpose --
    Phase 12 sec16. Any future backtest must filter on ``available_at``.
    """

    # --- identity -----------------------------------------------------
    event_time: str                 # exchange-local ISO-8601 (IST)
    event_time_utc: str             # UTC ISO-8601
    session_date: str               # YYYY-MM-DD, the trading session
    available_at: str               # when THIS process received it (IST ISO)
    underlying: str                 # "NIFTY" | "BANKNIFTY" | "SENSEX" | ...
    option_symbol: str
    expiry: str                     # YYYY-MM-DD
    strike: float
    option_type: str                # "CE" | "PE"

    # --- observed market state ---------------------------------------
    underlying_price: float
    last_price: float
    bid: float
    ask: float
    volume: int
    open_interest: int
    oi_change: int

    # --- derived (reproducible from the above) ------------------------
    implied_volatility: Optional[float] = None
    delta: Optional[float] = None
    gamma: Optional[float] = None
    theta: Optional[float] = None
    vega: Optional[float] = None

    # --- expiry structure (sec27) -------------------------------------
    dte: Optional[int] = None
    expiry_class: Optional[str] = None       # "WEEKLY" | "MONTHLY"

    # --- staleness (sec7) ---------------------------------------------
    #: Exchange-supplied age. Always None here: the chain has no per-leg
    #: timestamp. Kept as a field so a future feed that DOES supply one needs
    #: no schema change.
    quote_age_seconds: Optional[float] = None
    #: Seconds this exact quote (ltp/bid/ask/volume/oi) has been unchanged
    #: across our own consecutive snapshots. DERIVED, not observed.
    unchanged_for_seconds: Optional[float] = None

    # --- lineage (sec15, sec19) ---------------------------------------
    source: str = "fyers:options-chain-v3"
    source_endpoint: str = "/api/option-chain"
    retrieved_at: str = ""
    original_symbol: str = ""
    schema_version: str = SCHEMA_VERSION
    recorder_version: str = RECORDER_VERSION
    normalization_version: str = NORMALIZATION_VERSION

    # --- quality (sec9) -----------------------------------------------
    quality: str = Quality.VALID.value
    quality_reasons: tuple = ()

    @property
    def spread(self) -> Optional[float]:
        if self.bid > 0 and self.ask > 0:
            return self.ask - self.bid
        return None

    @property
    def spread_pct(self) -> Optional[float]:
        s = self.spread
        if s is None or self.last_price <= 0:
            return None
        return s / self.last_price * 100.0

    def executable_buy(self) -> Optional[float]:
        """What a BUY could actually have paid: the ASK (sec24).

        Returns None when there is no two-sided quote. It deliberately does
        NOT fall back to the last traded price -- that substitution is the
        thing sec24 forbids.
        """
        return self.ask if self.ask > 0 else None

    def executable_sell(self) -> Optional[float]:
        """What a SELL could actually have received: the BID (sec24)."""
        return self.bid if self.bid > 0 else None

    def observation_key(self) -> str:
        """Canonical identity of ONE observation (Phase 13 sec6).

        Two records with this key describe the same contract at the same
        instant and are the same observation, however many times the loop
        polled. The key deliberately excludes price and quality: a retry that
        returns slightly different numbers for the same instant is still a
        duplicate of that instant, and keeping both would let one moment vote
        twice in any later statistic.
        """
        return observation_key(self.underlying, self.event_time,
                               self.option_symbol, self.expiry,
                               self.strike, self.option_type)

    def quote_fingerprint(self) -> str:
        """Hash of the tradeable state only, for change detection (sec7)."""
        return record_checksum({
            "ltp": self.last_price, "bid": self.bid, "ask": self.ask,
            "volume": self.volume, "oi": self.open_interest,
        })

    def to_dict(self):
        d = asdict(self)
        d["quality_reasons"] = list(self.quality_reasons)
        return d


@dataclass(frozen=True)
class SignalEvent:
    """A frozen prior-day-extreme candidate. OBSERVATIONAL ONLY -- recording
    one never places, simulates or implies an order (sec10, sec19).

    The signal definition is frozen at the Phase 10 rule and must not be
    changed by this phase (sec20).
    """

    event_time: str
    session_date: str
    available_at: str
    underlying: str
    setup_id: str
    direction: int                  # +1 long/CE, -1 short/PE
    previous_day_high: float
    previous_day_low: float
    level: float                    # the level in play
    distance_to_level: float
    atr: float
    band_atr: float                 # the configured band, for reproducibility
    underlying_price: float
    signal_state: str               # see setup.STATES
    in_band: bool
    schema_version: str = SCHEMA_VERSION

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class UnderlyingSnapshot:
    """The underlying state at the same moment as a chain snapshot (sec8),
    so a future researcher can reconstruct exactly what was knowable."""

    event_time: str
    session_date: str
    available_at: str
    underlying: str
    price: float
    previous_day_high: float
    previous_day_low: float
    atr: float
    bar_open: Optional[float] = None
    bar_high: Optional[float] = None
    bar_low: Optional[float] = None
    bar_close: Optional[float] = None
    #: India VIX at this snapshot, when the broker supplied it. ``None`` means
    #: it was not sent -- it is never carried forward from an earlier snapshot
    #: and never modelled, because a stale volatility reading silently
    #: rewrites the regime a later study would attribute a result to.
    india_vix: Optional[float] = None
    india_vix_change_pct: Optional[float] = None
    schema_version: str = SCHEMA_VERSION
    recorder_version: str = RECORDER_VERSION

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------
# Validation (sec5, sec9)
# ---------------------------------------------------------------------

def classify_quote(bid: float, ask: float, last_price: float,
                   age_seconds: Optional[float],
                   is_synthetic: bool,
                   stale_seconds: float = DEFAULT_STALE_SECONDS,
                   unchanged_for_seconds=None,
                   unchanged_stale_seconds: float = DEFAULT_UNCHANGED_STALE_SECONDS):
    """(Quality, reasons) for one leg. Deterministic and order-independent.

    SYNTHETIC wins over everything: a modelled premium is not an observation
    however well-formed it looks.
    """
    reasons = []
    if is_synthetic:
        return Quality.SYNTHETIC, ("chain reported synthetic=true",)

    if last_price is None or not _finite(last_price) or last_price <= 0:
        reasons.append("last_price <= 0 or not finite")
    if bid is None or not _finite(bid) or bid < 0:
        reasons.append("bid negative or not finite")
    if ask is None or not _finite(ask) or ask < 0:
        reasons.append("ask negative or not finite")
    if _finite(bid) and _finite(ask) and bid > 0 and ask > 0 and ask < bid:
        reasons.append("crossed quote (ask < bid)")
    if reasons:
        return Quality.INVALID, tuple(reasons)

    if bid == 0 or ask == 0:
        # Not corrupt, but not executable either -- sec24 forbids substituting
        # last price, so this cannot support execution analysis.
        return Quality.INVALID, ("no two-sided quote (zero bid or ask)",)

    if age_seconds is not None and age_seconds > stale_seconds:
        return Quality.STALE, (f"quote age {age_seconds:.0f}s > {stale_seconds:.0f}s",)

    if (unchanged_for_seconds is not None
            and unchanged_for_seconds > unchanged_stale_seconds):
        return Quality.STALE, (
            f"quote unchanged for {unchanged_for_seconds:.0f}s > "
            f"{unchanged_stale_seconds:.0f}s (derived, not an exchange age)",)

    return Quality.VALID, ()


def observation_key(underlying: str, event_time: str, option_symbol: str,
                    expiry: str, strike: float, option_type: str) -> str:
    """The canonical duplicate key (Phase 13 sec6).

    Strike is formatted to 2dp so 24000 and 24000.0 collide, as they must.
    ``option_symbol`` is included because it is the exchange contract
    identity; ``expiry`` and ``strike`` are included too because a symbol can
    be absent from a malformed row while the contract is still identified.
    """
    return "|".join((str(underlying), str(event_time), str(option_symbol or ""),
                     str(expiry or ""), f"{float(strike):.2f}",
                     str(option_type)))


def _finite(x) -> bool:
    try:
        return x == x and abs(float(x)) != float("inf")
    except (TypeError, ValueError):
        return False


def record_checksum(payload: Dict[str, Any]) -> str:
    """Stable content hash for lineage and tamper detection (sec32)."""
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"),
                      default=str).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


__all__ = [
    "SCHEMA_VERSION", "RECORDER_VERSION", "NORMALIZATION_VERSION",
    "REQUIRE_OBSERVED_OPTION_DATA", "DEFAULT_STALE_SECONDS",
    "DEFAULT_UNCHANGED_STALE_SECONDS",
    "Quality", "Provenance", "SessionStatus", "FIELD_PROVENANCE",
    "OptionQuote", "SignalEvent", "UnderlyingSnapshot",
    "classify_quote", "observation_key", "record_checksum",
]
