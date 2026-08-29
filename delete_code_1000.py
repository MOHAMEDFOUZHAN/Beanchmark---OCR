import sqlite3
import os

db_path = os.path.join(os.environ['PROGRAMDATA'], 'BeanchMark-MMS', 'inventory - BeanchMark-MMS.db')
conn = sqlite3.connect(db_path)
cur = conn.cursor()

# 1. Check if it exists
cur.execute("SELECT COUNT(*) FROM materials WHERE material_code = '1000'")
count_before = cur.fetchone()[0]

# 2. Delete it
cur.execute("DELETE FROM materials WHERE material_code = '1000'")
rows_deleted = cur.rowcount

conn.commit()
conn.close()

with open("delete_result.txt", "w") as f:
    f.write(f"Count before: {count_before}\nRows deleted: {rows_deleted}")
