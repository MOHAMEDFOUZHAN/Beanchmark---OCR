import sqlite3
import os

db_path = os.path.join(os.environ['PROGRAMDATA'], 'MMS', 'inventory.db')
conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row
cur = conn.cursor()

cur.execute("SELECT * FROM materials WHERE description LIKE '%coco%'")
rows = cur.fetchall()

print(f"Found {len(rows)} rows for 'coco'")
for row in rows:
    print(dict(row))

conn.close()
