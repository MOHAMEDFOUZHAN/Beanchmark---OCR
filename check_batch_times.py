import sqlite3
import os

FACTORY_NAME = "BeanchMark-MMS"
PROGRAM_DATA_DIR = os.path.join(os.environ["PROGRAMDATA"], FACTORY_NAME)
DATABASE = os.path.join(PROGRAM_DATA_DIR, "inventory - BeanchMark-MMS.db")

conn = sqlite3.connect(DATABASE)
conn.row_factory = sqlite3.Row
cur = conn.cursor()

codes = ['308', '309', '310', '311', '312', '313']

print(f"{'Code':<10} {'Batch':<15} {'Qty':<10} {'Created':<20}")
for code in codes:
    cur.execute("SELECT material_code, batch_no, available_quantity, created_at FROM batches WHERE material_code = ?", (code,))
    rows = cur.fetchall()
    for row in rows:
        print(f"{row['material_code']:<10} {str(row['batch_no']):<15} {row['available_quantity']:<10} {row['created_at']:<20}")

conn.close()
