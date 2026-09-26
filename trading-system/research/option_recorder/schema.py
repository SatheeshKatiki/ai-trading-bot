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
SCHEMA_VERSION = "1.0.0"

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

    # --- lineage (sec15) ----------------------------------------------
    source: str = "fyers:options-chain-v3"
    source_endpoint: str = "/api/option-chain"
    retrieved_at: str = ""
    original_symbol: str = ""
    schema_version: str = SCHEMA_VERSION

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

    def to_dict(self) -> Dict[str, Any]:
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
    schema_version: str = SCHEMA_VERSION

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------
# Validation (sec5, sec9)
# ---------------------------------------------------------------------

def classify_quote(bid: float, ask: float, last_price: float,
                   age_seconds: Optional[float],
                   is_synthetic: bool,
                   stale_seconds: float = DEFAULT_STALE_SECONDS):
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

    return Quality.VALID, ()


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
    "SCHEMA_VERSION", "REQUIRE_OBSERVED_OPTION_DATA", "DEFAULT_STALE_SECONDS",
    "Quality", "Provenance", "FIELD_PROVENANCE",
    "OptionQuote", "SignalEvent", "UnderlyingSnapshot",
    "classify_quote", "record_checksum",
]
