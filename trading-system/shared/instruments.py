"""Canonical index-instrument identification.

Single source of truth for turning a broker/data underlying symbol (e.g.
``"NSE:NIFTY50-INDEX"``, ``"NSE:NIFTYBANK-INDEX"``, ``"BSE:SENSEX-INDEX"``)
into the canonical instrument key used everywhere else in the system —
``INSTRUMENT_CONFIG`` in
``trading_bot/strategies/premium_selection/options_selector.py``,
per-instrument confidence gating (``shared/risk/instrument_focus.py``), logs,
and the trade journal.

Root cause this exists for: the remap was previously re-derived inline, ad
hoc, at each call site in ``trading_bot/main.py`` — once for the "premium"
strategy branch and once for the index-to-option auto-map branch. The two
copies had already drifted apart: the premium-strategy one never stripped a
``"BSE:"`` prefix, so a SENSEX signal through that path built the instrument
key ``"BSE:SENSEX"`` instead of ``"SENSEX"``, silently failing to match
``INSTRUMENT_CONFIG``. One function, used everywhere, makes that class of
drift structurally impossible.
"""
from __future__ import annotations

#: Underlying data-symbol names that don't match their tradeable option
#: series 1:1 — the index feed is "NIFTY50" but the option series is
#: "NIFTY"; the feed is "NIFTYBANK" but the option series is "BANKNIFTY".
_INSTRUMENT_REMAP = {
    "NIFTY50": "NIFTY",
    "NIFTYBANK": "BANKNIFTY",
}

#: The four index instruments this system trades options on.
INDEX_INSTRUMENTS: tuple[str, ...] = ("NIFTY", "BANKNIFTY", "FINNIFTY", "SENSEX")


def normalize_instrument(symbol: str) -> str:
    """``"NSE:NIFTY50-INDEX"`` -> ``"NIFTY"``, ``"BSE:SENSEX-INDEX"`` ->
    ``"SENSEX"``, ``"NSE:FINNIFTY-INDEX"`` -> ``"FINNIFTY"``, etc.

    Idempotent — normalizing an already-canonical key (``"NIFTY"``) returns
    it unchanged, so callers never need to know whether they already have a
    clean instrument key or a raw broker symbol.
    """
    # Upper-case first, then strip — the prefix/suffix patterns below are
    # literal uppercase strings, so stripping first would silently leave a
    # lowercase input (e.g. "nse:nifty50-index") untouched.
    raw = (
        symbol.upper()
        .replace("NSE:", "")
        .replace("BSE:", "")
        .replace("-INDEX", "")
        .replace("-EQ", "")
    )
    return _INSTRUMENT_REMAP.get(raw, raw)
