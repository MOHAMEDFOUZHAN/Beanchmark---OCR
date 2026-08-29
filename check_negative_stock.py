import sqlite3
import os

FACTORY_NAME = "BeanchMark-MMS"
PROGRAM_DATA_DIR = os.path.join(os.environ["PROGRAMDATA"], FACTORY_NAME)
DATABASE = os.path.join(PROGRAM_DATA_DIR, "inventory - BeanchMark-MMS.db")

print(f"Connecting to: {DATABASE}")

if not os.path.exists(DATABASE):
    print("FATAL ERROR: Database file not found!")
    exit(1)

conn = sqlite3.connect(DATABASE)
conn.row_factory = sqlite3.Row
cur = conn.cursor()

# Check if tables exist
cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = [row[0] for row in cur.fetchall()]
print(f"Tables found: {tables}")

if 'materials' not in tables:
    print("ERROR: 'materials' table not found!")
    conn.close()
    exit(1)

print("\n--- Materials with Negative Stock ---")
cur.execute("SELECT material_code, description, lot_no, quantity, opening_stock FROM materials WHERE quantity < 0")
rows = cur.fetchall()

if not rows:
    print("No negative stock found in materials table.")
else:
    for row in rows:
        print(f"Code: {row['material_code']}, Desc: {row['description']}, Lot: {row['lot_no']}, Qty: {row['quantity']}, Opening: {row['opening_stock']}")

print("\n--- Batches with Negative Stock ---")
cur.execute("SELECT material_code, description, batch_no, available_quantity FROM batches WHERE available_quantity < 0")
rows = cur.fetchall()

if not rows:
    print("No negative stock found in batches table.")
else:
    for row in rows:
        print(f"Code: {row['material_code']}, Desc: {row['description']}, Batch: {row['batch_no']}, Avail: {row['available_quantity']}")

conn.close()
