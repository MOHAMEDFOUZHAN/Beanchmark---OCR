import sqlite3
import os

DB_PATH = "inventory - BeanchMark-MMS.db"

conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()

# Check first
cursor.execute("SELECT * FROM materials WHERE material_id IN (913, 914)")
rows = cursor.fetchall()

if rows:
    print("Rows found, deleting...")
    cursor.execute("DELETE FROM materials WHERE material_id IN (913, 914)")
    conn.commit()
else:
    print("No matching rows found")

conn.close()
