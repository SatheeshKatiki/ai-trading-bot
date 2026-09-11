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


#: Broker (Fyers) data symbol for each index instrument.
INDEX_BROKER_SYMBOLS: dict[str, str] = {
    "NIFTY": "NSE:NIFTY50-INDEX",
    "BANKNIFTY": "NSE:NIFTYBANK-INDEX",
    "FINNIFTY": "NSE:FINNIFTY-INDEX",
    "SENSEX": "BSE:SENSEX-INDEX",
}

#: Indices the PAPER books trade while a strategy is being validated. The
#: owner asked on 2026-09-11 for SENSEX alongside NIFTY and BANKNIFTY "for
#: testing"; override with the ``paper_test_instruments`` setting.
DEFAULT_PAPER_TEST_INSTRUMENTS: tuple[str, ...] = ("NIFTY", "BANKNIFTY", "SENSEX")


def resolve_paper_test_instruments(settings: dict | None) -> list[str]:
    """Canonical instrument keys the paper books trade.

    ``settings["paper_test_instruments"]`` when present (short or broker
    names, unknown ones dropped), else :data:`DEFAULT_PAPER_TEST_INSTRUMENTS`.
    """
    raw = (settings or {}).get("paper_test_instruments")
    if not isinstance(raw, (list, tuple)):
        return list(DEFAULT_PAPER_TEST_INSTRUMENTS)
    out: list[str] = []
    for name in raw:
        key = normalize_instrument(str(name))
        if key in INDEX_BROKER_SYMBOLS and key not in out:
            out.append(key)
    return out


def resolve_trading_symbols(settings: dict | None) -> list[str]:
    """Broker symbols the LIVE engine may trade: exactly what the owner
    selected in the UI (``settings["symbols"]``), and nothing else.

    There is deliberately no default. The engine used to fall back to all
    four indices whenever ``symbols`` was missing; the owner's rule
    (2026-09-11) is that only the indices chosen in the UI are ever traded.
    Index names are accepted short or broker-form and mapped to the broker
    symbol; any other exchange-prefixed symbol passes through unchanged.
    """
    raw = (settings or {}).get("symbols")
    if not isinstance(raw, (list, tuple)):
        return []
    out: list[str] = []
    for name in raw:
        text = str(name).strip()
        if not text:
            continue
        key = normalize_instrument(text)
        symbol = INDEX_BROKER_SYMBOLS.get(key, text if ":" in text else None)
        if symbol and symbol not in out:
            out.append(symbol)
    return out
