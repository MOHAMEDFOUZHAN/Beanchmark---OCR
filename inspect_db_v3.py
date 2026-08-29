import sqlite3
import os

db_path = os.path.join(os.environ['PROGRAMDATA'], 'BeanchMark-MMS', 'inventory - BeanchMark-MMS.db')
with open('db_inspect_out.txt', 'w') as f:
    if not os.path.exists(db_path):
        f.write(f"Database not found at {db_path}\n")
    else:
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        
        f.write("Schema of materials:\n")
        cur.execute("PRAGMA table_info(materials)")
        for col in cur.fetchall():
            f.write(str(col) + "\n")
            
        f.write("\nData in materials (first 20 rows):\n")
        cur.execute("SELECT id, material_code, description, lot_no, quantity, expiry_date FROM materials LIMIT 20")
        for row in cur.fetchall():
            f.write(str(row) + "\n")
            
        conn.close()
