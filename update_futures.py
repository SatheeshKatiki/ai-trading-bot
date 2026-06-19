import urllib.request
import csv
import json
import re

req = urllib.request.Request('https://archives.nseindia.com/content/fo/fo_mktlots.csv', headers={'User-Agent': 'Mozilla/5.0'})
try:
    content = urllib.request.urlopen(req).read().decode('iso-8859-1')
except Exception as e:
    print("Error:", e)
    exit(1)

lines = content.splitlines()
reader = csv.reader(lines)
lot_sizes = {}
assets = []

indices = ['NIFTY', 'BANKNIFTY', 'FINNIFTY', 'MIDCPNIFTY', 'SENSEX']

for row in reader:
    if len(row) > 2:
        symbol = row[1].strip()
        if symbol == 'SYMBOL' or not symbol:
            continue
        try:
            lot = int(row[2].strip())
        except:
            continue
        lot_sizes[symbol] = lot
        if symbol in indices:
            assets.append({'symbol': symbol, 'name': symbol + " Index", 'type': 'Index'})
        else:
            assets.append({'symbol': symbol, 'name': symbol, 'type': 'Stock'})

print(f"Found {len(lot_sizes)} symbols.")

# Generate tsx strings
lot_sizes_str = "const LOT_SIZES: Record<string, number> = {\n"
for sym, lot in lot_sizes.items():
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

print("Successfully updated live/page.tsx and header.tsx with all F&O stocks.")
