import sqlite3
import os

db_path = os.path.join(os.environ['PROGRAMDATA'], 'BeanchMark-MMS', 'inventory - BeanchMark-MMS.db')
if not os.path.exists(db_path):
    print(f"Database not found at {db_path}")
else:
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    
    print("Schema of materials:")
    cur.execute("PRAGMA table_info(materials)")
    for col in cur.fetchall():
        print(col)
        
    print("\nData in materials (first 10 rows):")
    # Fetch some rows focusing on code, description, lot_no, and unique constraints
    cur.execute("SELECT id, material_code, description, lot_no, quantity, expiry_date FROM materials LIMIT 10")
    for row in cur.fetchall():
        print(row)
        
    conn.close()
