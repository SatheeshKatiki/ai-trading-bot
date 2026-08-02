import sqlite3
import os

def init_journal_db():
    db_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'state.db')
    print(f"Connecting to {db_path}...")
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS trade_journal (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            trade_date TEXT NOT NULL,
            symbol TEXT NOT NULL,
            strategy_name TEXT NOT NULL,
            direction TEXT NOT NULL,
            entry_price REAL NOT NULL,
            exit_price REAL NOT NULL,
            qty INTEGER NOT NULL,
            pnl REAL NOT NULL,
            ai_feedback TEXT,
            tags TEXT
        )
    ''')
    
    # Check if table is empty, insert some mock data for UI testing if so
    cursor.execute("SELECT COUNT(*) FROM trade_journal")
    count = cursor.fetchone()[0]
    
    if count == 0:
        print("Inserting mock journal data for testing...")
        mock_data = [
            ("2026-07-10 10:15:00", "NSE:NIFTY50-INDEX", "ema_rsi", "BUY", 24100.5, 24150.0, 50, 2475.0, "Great entry based on RSI divergence. Hold could have been longer but hit target.", "perfect_entry,early_exit"),
            ("2026-07-11 11:30:00", "NSE:BANKNIFTY-INDEX", "institutional_momentum", "SELL", 52400.0, 52500.0, 15, -1500.0, "Stoploss hit. Market reversed unexpectedly due to sudden macro news. Next time, tighten SL during news hours.", "sl_hit,macro_reversal"),
            ("2026-07-14 09:45:00", "NSE:RELIANCE-EQ", "buy_the_dip", "BUY", 3100.0, 3140.0, 100, 4000.0, "Perfect dip buy at VWAP support. AI accurately predicted the bounce.", "vwap_support,perfect_execution")
        ]
        
        cursor.executemany('''
            INSERT INTO trade_journal (trade_date, symbol, strategy_name, direction, entry_price, exit_price, qty, pnl, ai_feedback, tags)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', mock_data)
        
    conn.commit()
    conn.close()
    print("trade_journal table initialized successfully!")

if __name__ == "__main__":
    init_journal_db()
