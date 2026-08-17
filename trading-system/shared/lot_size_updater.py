import asyncio
import datetime
import logging
import json
import os
import tempfile
import aiohttp

logger = logging.getLogger(__name__)

NSE_MASTER_URL = "https://public.fyers.in/sym_details/NSE_FO.csv"
BSE_MASTER_URL = "https://public.fyers.in/sym_details/BSE_FO.csv"

# Column indices in the Fyers symbol master CSV (public.fyers.in/sym_details/*.csv).
# Verified against a live sample: col 3 is lot size, col 8 is the contract's
# expiry as a Unix timestamp (seconds). e.g. for
# "...,NIFTY 25 Aug 26 FUT,11,65,0.1,,...,2026-07-31,1787652000,NSE:NIFTY26AUGFUT,...":
# col 3 = 65 (lot size), col 8 = 1787652000 (2026-08-25, the FUT's expiry).
_COL_LOT_SIZE = 3
_COL_EXPIRY_TS = 8


def _target_prefixes() -> dict[str, list[str]]:
    """Build the year-prefixed symbol list fresh on every call.

    Root-cause fix: this used to be a module-level constant computed once
    at import time from CURRENT_YEAR. In a long-running process (e.g.
    api_bridge.py, which only calls update_lot_sizes_in_settings() once at
    startup today, but could reasonably be changed to run periodically),
    a year frozen at import time goes stale the moment the calendar rolls
    over to a new year — every prefix would then search for a year prefix
    (e.g. "NIFTY26") that no longer matches any current contract in the
    symbol master (which would by then use "NIFTY27"), silently returning
    zero results every single call until the process is restarted.
    """
    current_year = str(datetime.datetime.now().year)[-2:]
    return {
        "NSE": [f"NSE:NIFTY{current_year}", f"NSE:BANKNIFTY{current_year}", f"NSE:FINNIFTY{current_year}", f"NSE:MIDCPNIFTY{current_year}"],
        "BSE": [f"BSE:SENSEX{current_year}", f"BSE:BANKEX{current_year}"],
    }


async def fetch_lot_sizes_from_url(session: aiohttp.ClientSession, url: str, prefixes: list[str]) -> dict[str, int]:
    results: dict[str, int] = {}
    best_expiry: dict[str, float] = {}
    try:
        async with session.get(url, timeout=15) as resp:
            if resp.status == 200:
                content = await resp.text()
                for line in content.splitlines():
                    for p in prefixes:
                        # Extract the base index name (e.g. NIFTY, BANKNIFTY) without the prefix year
                        base_name = p.split(':')[1][:-2]
                        if p in line and "-INDEX" not in line:
                            parts = line.split(',')
                            if len(parts) > _COL_EXPIRY_TS:
                                try:
                                    expiry_ts = float(parts[_COL_EXPIRY_TS])
                                    lot_size = int(parts[_COL_LOT_SIZE])
                                except ValueError:
                                    continue
                                # Root-cause fix: previously took whichever
                                # matching line appeared first in the file
                                # (arbitrary — the file isn't guaranteed
                                # sorted by expiry) and locked it in via a
                                # `base_name not in results` guard. Now
                                # keeps scanning and only replaces the
                                # result when a line with a NEARER expiry
                                # is found, so the lot size reflects the
                                # currently-active/soonest-expiring
                                # contract rather than an arbitrary one —
                                # relevant during a lot-size revision
                                # window where different expiries can
                                # (briefly) carry different lot sizes.
                                if base_name not in best_expiry or expiry_ts < best_expiry[base_name]:
                                    best_expiry[base_name] = expiry_ts
                                    results[base_name] = lot_size
    except Exception as e:
        logger.error(f"Error fetching lot sizes from {url}: {e}")
    return results

async def update_lot_sizes_in_settings():
    """
    Downloads symbol master from Fyers, extracts the latest lot sizes for major indices,
    and updates settings.json safely.
    """
    logger.info("Fetching dynamic lot sizes from Fyers Symbol Master...")
    lot_sizes = {}
    try:
        target_prefixes = _target_prefixes()
        async with aiohttp.ClientSession() as session:
            nse_lots = await fetch_lot_sizes_from_url(session, NSE_MASTER_URL, target_prefixes["NSE"])
            bse_lots = await fetch_lot_sizes_from_url(session, BSE_MASTER_URL, target_prefixes["BSE"])
            
            lot_sizes.update(nse_lots)
            lot_sizes.update(bse_lots)
            
            if not lot_sizes:
                logger.warning("No lot sizes found from Fyers symbol master.")
                return

            logger.info(f"Successfully fetched lot sizes: {lot_sizes}")
            
            # Read existing settings.
            # Root-cause fix (Medium audit finding): three separate
            # settings.json files exist in this repo with no documented
            # source of truth. This used to read+write
            # trading-system/settings.json (a legacy file), while the live
            # engine, broker_factory, and api_bridge all read
            # trading-system/config/settings.json — meaning lot sizes
            # persisted here never reached the dashboard/live engine's view
            # of settings. Standardized on config/settings.json, the file
            # every other real consumer already treats as canonical; the
            # existing read-merge-write logic below already preserves every
            # other key already in that file (active_strategy,
            # stoploss_pct, etc.) — only "lot_sizes" is touched.
            settings_path = os.path.join(os.path.dirname(__file__), "..", "config", "settings.json")
            settings = {}
            if os.path.exists(settings_path):
                try:
                    with open(settings_path, 'r') as f:
                        settings = json.load(f)
                except Exception:
                    pass
            
            # Update settings
            existing_lots = settings.get("lot_sizes", {})
            
            # Keep any existing ones if we failed to fetch a specific one
            merged_lots = {**existing_lots, **lot_sizes}

            if existing_lots != merged_lots:
                settings["lot_sizes"] = merged_lots
                # Atomic write (temp file + rename) — the live engine reads
                # this same file concurrently on an mtime check
                # (trading_bot/main.py's _load_settings()); a direct
                # open(..., 'w') here could hand it a truncated/invalid file
                # if a crash or concurrent read landed mid-write.
                settings_dir = os.path.dirname(settings_path) or "."
                fd, tmp_path = tempfile.mkstemp(dir=settings_dir, prefix="settings_tmp_", suffix=".json")
                try:
                    with os.fdopen(fd, "w") as f:
                        json.dump(settings, f, indent=4)
                    os.replace(tmp_path, settings_path)
                except Exception:
                    if os.path.exists(tmp_path):
                        os.unlink(tmp_path)
                    raise
                logger.info("Updated settings.json with new lot sizes.")
            else:
                logger.info("Lot sizes in settings.json are already up to date.")
    except Exception as e:
        logger.error(f"Failed to update lot sizes: {e}")

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(update_lot_sizes_in_settings())


# ---------------------------------------------------------------------------
# Fix 6 helpers: runtime lot size lookup without global CONFIG dependency
# ---------------------------------------------------------------------------

_SETTINGS_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "config", "settings.json"
)

# Known safe defaults — used when settings.json doesn't have a value yet.
_DEFAULT_LOT_SIZES: dict[str, int] = {
    "NSE:NIFTY50-INDEX":   75,
    "NSE:NIFTY-I":         75,
    "NSE:BANKNIFTY-INDEX": 35,
    "NSE:BANKNIFTY-I":     35,
    "NSE:FINNIFTY-INDEX":  40,
    "BSE:SENSEX-INDEX":    10,
}


def _read_settings() -> dict:
    """Read config/settings.json and return it as a dict (empty dict on failure)."""
    try:
        if os.path.exists(_SETTINGS_PATH):
            with open(_SETTINGS_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception as e:
        logger.warning(f"[get_lot_size] Could not read settings.json: {e}")
    return {}


def get_lot_size(symbol: str, default: int = 1) -> int:
    """Return the current lot size for the given symbol.

    Lookup order:
      1. config/settings.json → lot_sizes → {symbol}
      2. Hard-coded _DEFAULT_LOT_SIZES dict
      3. `default` argument (1 — ultra-safe fallback)

    This function is intentionally cheap and synchronous: it reads from a
    local JSON file that is already cached by the OS page cache and is
    never more than a few KB.  Call it freely from strategies without
    worrying about latency.
    """
    settings = _read_settings()
    lot_sizes = settings.get("lot_sizes", {})

    # Exact match first
    if symbol in lot_sizes:
        try:
            return int(lot_sizes[symbol])
        except (ValueError, TypeError):
            pass

    # Prefix/fuzzy match (e.g. "NSE:NIFTY50-INDEX" → "NIFTY" prefix in stored keys)
    symbol_upper = symbol.upper()
    for stored_sym, size in lot_sizes.items():
        if symbol_upper in stored_sym.upper() or stored_sym.upper() in symbol_upper:
            try:
                return int(size)
            except (ValueError, TypeError):
                pass

    # Known defaults
    if symbol in _DEFAULT_LOT_SIZES:
        return _DEFAULT_LOT_SIZES[symbol]

    logger.warning(f"[get_lot_size] Unknown symbol {symbol!r} — using default {default}")
    return max(1, default)
