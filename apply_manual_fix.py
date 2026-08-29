import sqlite3
import os

FACTORY_NAME = "BeanchMark-MMS"
PROGRAM_DATA_DIR = os.path.join(os.environ["PROGRAMDATA"], FACTORY_NAME)
DATABASE = os.path.join(PROGRAM_DATA_DIR, "inventory - BeanchMark-MMS.db")

conn = sqlite3.connect(DATABASE)
cur = conn.cursor()

# Format: (code, new_qty)
updates = [
    ('308', 58.700),
    ('309', 48.0),
    ('310', 17.0),
    ('311', 7.0),
    ('312', 16.0),
    ('313', 11.0)
]

print("Applying manual quantity updates...")

for code, qty in updates:
    # 1. Set all lots for this code to 0 first (clean slate for this code)
    cur.execute("UPDATE materials SET quantity = 0, opening_stock = 0 WHERE material_code = ?", (code,))
    
    # 2. Update the 'BATCH-344' lot (or the first lot found) to the target quantity
    # We check if BATCH-344 exists for this code, if not, we take any lot.
    cur.execute("SELECT id FROM materials WHERE material_code = ? AND lot_no = 'BATCH-344'", (code,))
    row = cur.fetchone()
    
    if row:
        target_id = row[0]
    else:
        # Fallback to any lot for this code
        cur.execute("SELECT id FROM materials WHERE material_code = ? LIMIT 1", (code,))
        target_id = cur.fetchone()[0]
    
    cur.execute("UPDATE materials SET quantity = ?, opening_stock = ? WHERE id = ?", (qty, qty, target_id))
    print(f"Updated Code {code} to {qty}")

conn.commit()
conn.close()
print("All updates applied successfully.")
