import sqlite3
import os

FACTORY_NAME = "BeanchMark-MMS"
PROGRAM_DATA_DIR = os.path.join(os.environ["PROGRAMDATA"], FACTORY_NAME)
DATABASE = os.path.join(PROGRAM_DATA_DIR, "inventory - BeanchMark-MMS.db")

conn = sqlite3.connect(DATABASE)
conn.row_factory = sqlite3.Row
cur = conn.cursor()

codes = ['308', '309', '310', '311', '312', '313']

for code in codes:
    cur.execute("SELECT material_code, lot_no, quantity, opening_stock FROM materials WHERE material_code = ?", (code,))
    rows = cur.fetchall()
    for row in rows:
        print(f"[{row['material_code']}] Lot: {row['lot_no']} Qty: {row['quantity']} Open: {row['opening_stock']}")

conn.close()
