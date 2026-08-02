import sqlite3
import time
import json
import random

db_path = r"d:\Projects\AI trading Bot\trading-system\state.db"

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
    inject_mock_trade()
