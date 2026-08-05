"""Seeds fabricated trades into the LIVE paper-trading journal.

Formerly `trading-system/scripts/e2e_test.py`. Despite the old name this is
not an end-to-end test — it writes rows straight into `state.db`, the same
table the dashboard, `/api/state` and every P&L figure read from. Rows it
writes cannot be told apart from real fills after the fact, and pollution of
this kind is what forced the full `state.db` reset on 2026-08-05.

It is kept for the occasional "does the journal UI render a closed trade
correctly" spot-check, but it now refuses to run unless the caller opts in
explicitly, because nothing about the old invocation (`python e2e_test.py`)
signalled that it mutated live state.

Usage:
    python inject_mock_trade.py --write-to-live-journal

Prefer the Playwright suite's mocked backend (`src/mocks/`) — it renders the
same UI states without touching any database.
"""
import sqlite3
import sys
import time
import json
import random
from pathlib import Path

# Resolved relative to this file rather than the hardcoded absolute path this
# script used to carry, so it follows the repo instead of one machine's D:.
db_path = str(Path(__file__).resolve().parents[2] / "trading-system" / "state.db")

_OPT_IN_FLAG = "--write-to-live-journal"

def inject_mock_trade():
    try:
        conn = sqlite3.connect(db_path)
        c = conn.cursor()
        
        # Table schema: id, symbol, entry_time, exit_time, action, entry_price, exit_price, pnl, pnl_pct, status, ai_confidence, model_version
        
        # Insert into trades (live feed)
        current_time = time.strftime('%Y-%m-%d %H:%M:%S')
        
        c.execute("""
            INSERT INTO trades (symbol, side, price, time, qty) 
            VALUES (?, ?, ?, ?, ?)
        """, ("NIFTY 24000 CE", "BUY", 145.50, current_time, 50))
        
        c.execute("""
            INSERT INTO trades (symbol, side, price, time, qty) 
            VALUES (?, ?, ?, ?, ?)
        """, ("BANKNIFTY 52000 PE", "SELL", 285.50, current_time, 15))
        
        # Insert into trade_journal (history/closed trades)
        c.execute("""
            INSERT INTO trade_journal 
            (trade_date, symbol, strategy_name, direction, entry_price, exit_price, qty, pnl, ai_feedback, tags) 
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            current_time.split(' ')[0], 
            "BANKNIFTY 52000 PE", 
            "AI Momentum Breakout", 
            "LONG", 
            210.00, 
            285.50, 
            15, 
            1132.50, 
            "Excellent exit based on resistance.", 
            "PROFIT, E2E-TEST"
        ))
        
        conn.commit()
        conn.close()
        print("Successfully injected a simulated CLOSED trade!")
        
    except Exception as e:
        print(f"Error injecting mock trade: {e}")

if __name__ == "__main__":
    if _OPT_IN_FLAG not in sys.argv:
        print(__doc__)
        print(f"Refusing to run without {_OPT_IN_FLAG}.")
        print(f"Target database: {db_path}")
        sys.exit(2)
    inject_mock_trade()
