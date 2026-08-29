import sqlite3
import os

factory_name = "BeanchMark-MMS"
db_path = os.path.join(os.environ['PROGRAMDATA'], factory_name, 'inventory.db')
print(f"Checking database at: {db_path}")

if not os.path.exists(db_path):
    print("Database file does not exist!")
    exit()

conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row
cur = conn.cursor()

cur.execute("SELECT material_code, description FROM materials")
rows = cur.fetchall()

print(f"Total materials: {len(rows)}")
for row in rows:
    print(f"Code: '{row['material_code']}', Description: '{row['description']}'")

conn.close()
