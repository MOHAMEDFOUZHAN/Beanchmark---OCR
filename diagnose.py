import sqlite3
import os
import sys

db_path = r"C:\ProgramData\BeanchMark-MMS\inventory - BeanchMark-MMS.db"
print(f"Checking: {db_path}")
sys.stdout.flush()

if not os.path.exists(db_path):
    print("NOT FOUND")
    sys.stdout.flush()
    exit()

try:
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    
    cur.execute("SELECT material_code, description, quantity FROM materials WHERE material_code = '428'")
    res = cur.fetchone()
    print(f"Material 428: {res}")
    sys.stdout.flush()

    cur.execute("SELECT id, invoice_no FROM invoices ORDER BY id DESC LIMIT 5")
    invs = cur.fetchall()
    print(f"Recent Invoices: {invs}")
    sys.stdout.flush()
    
    if invs:
        last_id = invs[0][0]
        cur.execute(f"SELECT material, quantity FROM invoice_items WHERE invoice_id = {last_id}")
        items = cur.fetchall()
        print(f"Items in Invoice {last_id}: {items}")
        sys.stdout.flush()

    conn.close()
except Exception as e:
    print(f"ERROR: {e}")
    sys.stdout.flush()
