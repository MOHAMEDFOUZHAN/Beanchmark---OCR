import sqlite3
import os

FACTORY_NAME = "BeanchMark-MMS"
PROGRAM_DATA_DIR = os.path.join(os.environ["PROGRAMDATA"], FACTORY_NAME)
DATABASE = os.path.join(PROGRAM_DATA_DIR, "inventory - BeanchMark-MMS.db")

conn = sqlite3.connect(DATABASE)
conn.row_factory = sqlite3.Row
cur = conn.cursor()

with open('negative_report.txt', 'w', encoding='utf-8') as f:
    f.write(f"Connecting to: {DATABASE}\n")
    
    f.write("\n--- Materials with Negative Stock ---\n")
    cur.execute("SELECT material_code, description, lot_no, quantity, opening_stock FROM materials WHERE quantity < 0")
    rows = cur.fetchall()
    for row in rows:
        f.write(f"Code: {row['material_code']}, Desc: {row['description']}, Lot: {row['lot_no']}, Qty: {row['quantity']}, Opening: {row['opening_stock']}\n")

    f.write("\n--- Batches with Negative Stock ---\n")
    cur.execute("SELECT material_code, description, batch_no, available_quantity FROM batches WHERE available_quantity < 0")
    rows = cur.fetchall()
    for row in rows:
        f.write(f"Code: {row['material_code']}, Desc: {row['description']}, Batch: {row['batch_no']}, Avail: {row['available_quantity']}\n")

conn.close()
