import sqlite3
import os

FACTORY_NAME = "BeanchMark-MMS"
PROGRAM_DATA_DIR = os.path.join(os.environ["PROGRAMDATA"], FACTORY_NAME)
DATABASE = os.path.join(PROGRAM_DATA_DIR, "inventory - BeanchMark-MMS.db")

conn = sqlite3.connect(DATABASE)
conn.row_factory = sqlite3.Row
cur = conn.cursor()

target_lots = ['BATCH-344', 'BATCH-050']

with open('transfer_investigation.txt', 'w', encoding='utf-8') as f:
    for lot in target_lots:
        f.write(f"\n=== Transfers for Lot: {lot} ===\n")
        cur.execute("SELECT * FROM transfers WHERE lot_no = ?", (lot,))
        rows = cur.fetchall()
        for row in rows:
            f.write(f"ID: {row['id']}, Date: {row['date']}, Code: {row['code']}, Out: {row['outward']}, Ret: {row['return_units']}, Avail: {row['availability']}\n")

    f.write("\n=== Invoice Items for these Lots ===\n")
    for lot in target_lots:
        cur.execute("SELECT * FROM invoice_items WHERE batch_no = ?", (lot,))
        rows = cur.fetchall()
        for row in rows:
            f.write(f"InvcID: {row['invoice_id']}, Material: {row['material']}, Qty: {row['quantity']}, Batch: {row['batch_no']}\n")

conn.close()
