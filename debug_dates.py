import sqlite3
import os

DATABASE = os.path.join(os.environ["PROGRAMDATA"], "BeanchMark-MMS", "inventory - BeanchMark-MMS.db")

if not os.path.exists(DATABASE):
    print(f"File not found: {DATABASE}")
    exit(1)

conn = sqlite3.connect(DATABASE)
conn.row_factory = sqlite3.Row
cur = conn.cursor()

print("--- Invoices ---")
cur.execute("SELECT date FROM invoices LIMIT 5")
for row in cur.fetchall():
    print(row['date'])

print("\n--- Transfers ---")
cur.execute("SELECT date FROM transfers LIMIT 5")
for row in cur.fetchall():
    print(row['date'])

print("\n--- Dispatches ---")
cur.execute("SELECT date FROM dispatches LIMIT 5")
for row in cur.fetchall():
    print(row['date'])

conn.close()
