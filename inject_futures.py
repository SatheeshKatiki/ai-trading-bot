import re

# Comprehensive list of NSE F&O stocks and approximate lot sizes (as of 2024/2025)
fo_stocks = {
    "NIFTY": 25, "BANKNIFTY": 15, "FINNIFTY": 40, "MIDCPNIFTY": 50, "SENSEX": 20,
    "AARTIIND": 1000, "ABB": 250, "ABBOTINDIA": 40, "ABCAPITAL": 5400, "ABFRL": 2600,
    "ACC": 300, "ADANIENT": 300, "ADANIPORTS": 400, "ALKEM": 200, "AMBUJACEM": 1800,
    "APOLLOHOSP": 125, "APOLLOTYRE": 1700, "ASHOKLEY": 5000, "ASIANPAINT": 200, "ASTRAL": 348,
    "ATUL": 75, "AUBANK": 1000, "AUROPHARMA": 1050, "AXISBANK": 625, "BAJAJ-AUTO": 125,
    "BAJAJFINSV": 500, "BAJFINANCE": 125, "BALKRISIND": 300, "BALRAMCHIN": 1600, "BANDHANBNK": 2500,
    "BANKBARODA": 5850, "BATAINDIA": 375, "BEL": 5700, "BERGEPAINT": 1100, "BHARATFORG": 500,
    "BHARTIARTL": 950, "BHEL": 5250, "BIOCON": 2500, "BOSCHLTD": 50, "BPCL": 1800,
    "BRITANNIA": 200, "BSOFT": 1000, "CANBK": 2700, "CANFINHOME": 975, "CHAMBLFERT": 1900,
    "CHOLAFIN": 1250, "CIPLA": 650, "COALINDIA": 2100, "COFORGE": 150, "COLPAL": 350,
    "CONCOR": 1000, "COROMANDEL": 700, "CROMPTON": 1800, "CUB": 5000, "CUMMINSIND": 300,
    "DABUR": 1250, "DALBHARAT": 250, "DEEPAKNTR": 300, "DIVISLAB": 200, "DIXON": 100,
    "DLF": 1650, "DRREDDY": 125, "EICHERMOT": 175, "ESCORTS": 275, "EXIDEIND": 3600,
    "FEDERALBNK": 5000, "GAIL": 4050, "GLENMARK": 700, "GMRINFRA": 11250, "GNFC": 1300,
    "GODREJCP": 500, "GODREJPROP": 175, "GRANULES": 2000, "GRASIM": 250, "GUJGASLTD": 1250,
    "HAL": 300, "HAVELLS": 500, "HCLTECH": 700, "HDFCAMC": 150, "HDFCBANK": 550,
    "HDFCLIFE": 1100, "HEROMOTOCO": 300, "HINDALCO": 1400, "HINDCOPPER": 4300, "HINDPETRO": 2700,
    "HINDUNILVR": 300, "ICICIBANK": 700, "ICICIGI": 500, "ICICIPRULI": 1500, "IDEA": 80000,
    "IDFC": 10000, "IDFCFIRSTB": 15000, "IEX": 3750, "IGL": 1375, "INDHOTEL": 2000,
    "INDIACEM": 2900, "INDIAMART": 150, "INDIGO": 300, "INDUSINDBK": 500, "INDUSTOWER": 3400,
    "INFY": 400, "IOC": 9750, "IPCALAB": 650, "IRCTC": 875, "ITC": 1600,
    "JINDALSTEL": 1250, "JKCEMENT": 250, "JSWSTEEL": 675, "JUBLFOOD": 1250, "KOTAKBANK": 400,
    "L&TFH": 4462, "LALPATHLAB": 250, "LAURUSLABS": 1700, "LICHSGFIN": 2000, "LT": 300,
    "LTIM": 150, "LTTS": 200, "LUPIN": 850, "M&M": 350, "M&MFIN": 2000,
    "MANAPPURAM": 3000, "MARICO": 1200, "MARUTI": 50, "MCDOWELL-N": 700, "MCX": 200,
    "METROPOLIS": 400, "MFSL": 800, "MGL": 800, "MOTHERSON": 7100, "MPHASIS": 275,
    "MRF": 10, "MUTHOOTFIN": 550, "NATIONALUM": 7500, "NAUKRI": 150, "NAVINFLUOR": 150,
    "NESTLEIND": 400, "NMDC": 4500, "NTPC": 3000, "OBEROIRLTY": 700, "OFSS": 100,
    "ONGC": 3850, "PAGEIND": 15, "PEL": 750, "PERSISTENT": 200, "PETRONET": 3000,
    "PFC": 3875, "PIDILITIND": 250, "PIIND": 250, "PNB": 8000, "POLYCAB": 100,
    "POWERGRID": 3600, "PVRINOX": 407, "RAMCOCEM": 850, "RBLBANK": 2500, "RECLTD": 2000,
    "RELIANCE": 250, "SAIL": 8000, "SBICARD": 800, "SBILIFE": 750, "SBIN": 750,
    "SHREECEM": 25, "SHRIRAMFIN": 300, "SIEMENS": 125, "SRF": 375, "SUNTV": 1500,
    "SUNPHARMA": 700, "SYNGENE": 1000, "TATACHEM": 550, "TATACOMM": 500, "TATACONSUM": 900,
    "TATAMOTORS": 1425, "TATAPOWER": 3375, "TATASTEEL": 5500, "TCS": 175, "TECHM": 600,
    "TITAN": 175, "TORNTPHARM": 500, "TRENT": 400, "TVSMOTOR": 700, "UBL": 400,
    "ULTRACEMCO": 100, "UPL": 1300, "VEDL": 3150, "VOLTAS": 600, "WIPRO": 1500,
    "ZEEL": 3000, "ZYDUSLIFE": 900
}

indices = ['NIFTY', 'BANKNIFTY', 'FINNIFTY', 'MIDCPNIFTY', 'SENSEX']
assets = []
for sym, lot in fo_stocks.items():
    if sym in indices:
        assets.append({'symbol': sym, 'name': sym + " Index", 'type': 'Index'})
    else:
        assets.append({'symbol': sym, 'name': sym, 'type': 'Stock'})

lot_sizes_str = "const LOT_SIZES: Record<string, number> = {\n"
for sym, lot in fo_stocks.items():
    lot_sizes_str += f'  "{sym}": {lot},\n'
lot_sizes_str += "};"

assets_str = "const INDIAN_MARKET_ASSETS = [\n"
for asset in assets:
    assets_str += f'  {{ symbol: "{asset["symbol"]}", name: "{asset["name"]}", type: "{asset["type"]}" }},\n'
assets_str += "];"

# Update frontend/app/live/page.tsx
with open("frontend/app/live/page.tsx", "r", encoding="utf-8") as f:
    page_content = f.read()

page_content = re.sub(r'const LOT_SIZES: Record<string, number> = \{.*?\};', lot_sizes_str, page_content, flags=re.DOTALL)

with open("frontend/app/live/page.tsx", "w", encoding="utf-8") as f:
    f.write(page_content)

# Update frontend/components/header.tsx
with open("frontend/components/header.tsx", "r", encoding="utf-8") as f:
    header_content = f.read()

header_content = re.sub(r'const INDIAN_MARKET_ASSETS = \[.*?\];', assets_str, header_content, flags=re.DOTALL)

with open("frontend/components/header.tsx", "w", encoding="utf-8") as f:
    f.write(header_content)

print(f"Successfully added {len(fo_stocks)} symbols to UI.")
