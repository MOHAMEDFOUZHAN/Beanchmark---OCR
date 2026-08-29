import sqlite3
import os

db_path = r"C:\ProgramData\BeanchMark-MMS\inventory - BeanchMark-MMS.db"
conn = sqlite3.connect(db_path)
cur = conn.cursor()

# Rows to delete based on the user's images
rows_to_delete = [
    {"desc": "B", "code": "10000"}
]

print("--- Deleting Requested Rows ---")

for row in rows_to_delete:
    desc = row["desc"]
    code = row["code"]
    
    # 1. Check if exists
    if code:
        cur.execute("SELECT id FROM materials WHERE description = ? AND material_code = ?", (desc, code))
    else:
        # For 'c' which has no code
        cur.execute("SELECT id FROM materials WHERE description = ? AND (material_code IS NULL OR material_code = '')", (desc,))
    
    found = cur.fetchone()
    if found:
        # 2. Delete
        if code:
            cur.execute("DELETE FROM materials WHERE id = ?", (found[0],))
            print(f"Deleted: [{desc}] with code [{code}]")
        else:
            cur.execute("DELETE FROM materials WHERE id = ?", (found[0],))
            print(f"Deleted: [{desc}] (no code)")
    else:
        print(f"Not found: [{desc}]")

conn.commit()
conn.close()
print("\nSuccess: Live Material list updated.")
