import sqlite3
conn = sqlite3.connect('d:/Projects/AI trading Bot/trading-system/state.db')
print('Tables:', conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall())
try:
    print('Positions:', conn.execute("SELECT * FROM positions").fetchall())
except Exception as e:
    print("Error:", e)
