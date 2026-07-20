import asyncio
import logging
import json
import os
import aiohttp

logger = logging.getLogger(__name__)

NSE_MASTER_URL = "https://public.fyers.in/sym_details/NSE_FO.csv"
BSE_MASTER_URL = "https://public.fyers.in/sym_details/BSE_FO.csv"

# Current active year prefix for options
import datetime
CURRENT_YEAR = str(datetime.datetime.now().year)[-2:]

TARGET_PREFIXES = {
    "NSE": [f"NSE:NIFTY{CURRENT_YEAR}", f"NSE:BANKNIFTY{CURRENT_YEAR}", f"NSE:FINNIFTY{CURRENT_YEAR}", f"NSE:MIDCPNIFTY{CURRENT_YEAR}"],
    "BSE": [f"BSE:SENSEX{CURRENT_YEAR}", f"BSE:BANKEX{CURRENT_YEAR}"]
}

async def fetch_lot_sizes_from_url(session: aiohttp.ClientSession, url: str, prefixes: list[str]) -> dict[str, int]:
    results = {}
    try:
        async with session.get(url, timeout=15) as resp:
            if resp.status == 200:
                content = await resp.text()
                for line in content.splitlines():
                    for p in prefixes:
                        # Extract the base index name (e.g. NIFTY, BANKNIFTY) without the prefix year
                        base_name = p.split(':')[1][:-(len(CURRENT_YEAR))]
                        if base_name not in results and p in line and "-INDEX" not in line:
                            parts = line.split(',')
                            if len(parts) > 3:
                                try:
                                    results[base_name] = int(parts[3])
                                except ValueError:
                                    pass
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
        async with aiohttp.ClientSession() as session:
            nse_lots = await fetch_lot_sizes_from_url(session, NSE_MASTER_URL, TARGET_PREFIXES["NSE"])
            bse_lots = await fetch_lot_sizes_from_url(session, BSE_MASTER_URL, TARGET_PREFIXES["BSE"])
            
            lot_sizes.update(nse_lots)
            lot_sizes.update(bse_lots)
            
            if not lot_sizes:
                logger.warning("No lot sizes found from Fyers symbol master.")
                return

            logger.info(f"Successfully fetched lot sizes: {lot_sizes}")
            
            # Read existing settings
            settings_path = os.path.join(os.path.dirname(__file__), "..", "settings.json")
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
                with open(settings_path, 'w') as f:
                    json.dump(settings, f, indent=4)
                logger.info("Updated settings.json with new lot sizes.")
            else:
                logger.info("Lot sizes in settings.json are already up to date.")
    except Exception as e:
        logger.error(f"Failed to update lot sizes: {e}")

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(update_lot_sizes_in_settings())
