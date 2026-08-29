import sqlite3
import os

factory_name = "BeanchMark-MMS"
db_path = os.path.join(os.environ['PROGRAMDATA'], factory_name, 'inventory.db')

conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row
cur = conn.cursor()

cur.execute("SELECT material_code, description FROM materials WHERE description LIKE '%coco%'")
rows = cur.fetchall()

print(f"Found {len(rows)} rows for 'coco'")
for row in rows:
    print(f"Code: '{row['material_code']}', Description: '{row['description']}'")

conn.close()
