import sqlite3

conn = sqlite3.connect('trading-system/state.db')
cursor = conn.cursor()

# Update trades
cursor.execute("UPDATE trades SET time='2026-08-31T14:40:00+05:30' WHERE id=59")
cursor.execute("UPDATE trades SET time='2026-08-31T14:40:00+05:30' WHERE id=58")

# Update trade_journal
cursor.execute("UPDATE trade_journal SET trade_date='2026-08-31 14:40:00' WHERE symbol='NSE:NIFTY26AUG24100CE'")
conn.commit()

print("UPDATED TRADES:")
for r in cursor.execute("SELECT id, symbol, side, price, time FROM trades WHERE id >= 55").fetchall():
    print(r)

print("\nUPDATED JOURNAL:")
for r in cursor.execute("SELECT id, trade_date, symbol, pnl FROM trade_journal").fetchall():
    print(r)

conn.close()
