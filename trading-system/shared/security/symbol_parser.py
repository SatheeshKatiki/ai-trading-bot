import re
from typing import Dict, Any

def parse_option_symbol(symbol: str) -> Dict[str, Any]:
    """
    Parses any option ticker format (human or broker syntax) into standardized parts.
    
    Supported formats:
      - "NIFTY 24350 CE", "NIFTY 25950 PE"
      - "BANKNIFTY 52000 CE", "FINNIFTY 23500 PE"
      - "SENSEX 80000 CE"
      - "NSE:NIFTY26DEC2424000CE", "NSE:NIFTY26AUG24350CE"
      - "NIFTY24350CE", "BANKNIFTY52000PE"
    """
    if not symbol or not isinstance(symbol, str):
        return {"is_option": False, "underlying": "", "strike": 0.0, "opt_type": "", "raw": symbol or ""}

    clean = symbol.strip().upper()
    
    # 1. Human Readable Pattern: "NIFTY 24350 CE" or "BANKNIFTY 52000 PE" or "NIFTY 24350 CALL"
    pattern_human = r'^(NIFTY|BANKNIFTY|FINNIFTY|MIDCPNIFTY|SENSEX|BANKEX|RELIANCE|TCS|INFY)[\s_-]*(\d+[\.]?\d*)[\s_-]*(CE|PE|CALL|PUT)$'
    match_human = re.match(pattern_human, clean)
    if match_human:
        underlying = match_human.group(1)
        strike = float(match_human.group(2))
        opt_raw = match_human.group(3)
        opt_type = "CE" if opt_raw in ("CE", "CALL") else "PE"
        return {
            "is_option": True,
            "underlying": underlying,
            "strike": strike,
            "opt_type": opt_type,
            "raw": clean
        }

    # 2. Broker / Compact Exchange Pattern: e.g. "NSE:NIFTY26DEC2424000CE" or "NIFTY26AUG24350CE" or "NIFTY24350CE"
    # Matches any string ending with strike number + CE/PE
    pattern_end = r'^(?:[A-Z]+:)?(NIFTY|BANKNIFTY|FINNIFTY|MIDCPNIFTY|SENSEX|BANKEX).*?(\d{4,6})\s*(CE|PE)$'
    match_end = re.match(pattern_end, clean)
    if match_end:
        underlying = match_end.group(1)
        strike = float(match_end.group(2))
        opt_type = match_end.group(3)
        return {
            "is_option": True,
            "underlying": underlying,
            "strike": strike,
            "opt_type": opt_type,
            "raw": clean
        }

    return {"is_option": False, "underlying": clean, "strike": 0.0, "opt_type": "", "raw": clean}
