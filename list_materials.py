import sqlite3
import os

db_path = os.path.join(os.environ['PROGRAMDATA'], 'MMS', 'inventory.db')
conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row
cur = conn.cursor()

cur.execute("SELECT material_code, description FROM materials")
rows = cur.fetchall()

print(f"Total materials: {len(rows)}")
for row in rows:
    print(f"Code: '{row['material_code']}', Description: '{row['description']}'")

conn.close()
