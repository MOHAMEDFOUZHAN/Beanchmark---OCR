import sqlite3
import os

db_path = r"C:\ProgramData\BeanchMark-MMS\inventory - BeanchMark-MMS.db"
print(f"Checking DB: {db_path}")

if not os.path.exists(db_path):
    print("Database not found.")
    exit()

conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row
cur = conn.cursor()

print("\n--- Material '428' Master Info ---")
cur.execute("SELECT * FROM materials WHERE material_code = '428'")
row = cur.fetchone()
if row:
    print(dict(row))
else:
    print("Not found in materials table.")

print("\n--- Batches for '428' (Live Material) ---")
cur.execute("SELECT * FROM batches WHERE material_code = '428'")
rows = cur.fetchall()
if rows:
    for r in rows:
        print(dict(r))
else:
    print("No batches found for 428.")

print("\n--- Recent Invoices ---")
cur.execute("SELECT id, invoice_no, no_of_items, date FROM invoices ORDER BY id DESC LIMIT 10")
invoices = cur.fetchall()
for inv in invoices:
    print(dict(inv))
    # For each invoice, see if 428 is in it
    cur.execute("SELECT * FROM invoice_items WHERE invoice_id = ? AND material = '428'", (inv['id'],))
    item = cur.fetchone()
    if item:
        print(f"  --> FOUND 428 in this invoice! Item ID: {item['id']}, Qty: {item['quantity']}")
    else:
        # Check total items in this invoice
        cur.execute("SELECT count(*) FROM invoice_items WHERE invoice_id = ?", (inv['id'],))
        actual_count = cur.fetchone()[0]
        if actual_count != inv['no_of_items']:
            print(f"  !!! MISMATCH: Header says {inv['no_of_items']} but table has {actual_count} items.")

conn.close()
