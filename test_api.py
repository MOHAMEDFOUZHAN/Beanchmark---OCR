import sqlite3
import os

db_path = r"C:\ProgramData\BeanchMark-MMS\inventory - BeanchMark-MMS.db"
conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row
cur = conn.cursor()

print("\n--- Material 428 ---")
cur.execute("SELECT * FROM materials WHERE material_code = '428'")
print(dict(cur.fetchone()))

print("\n--- Invoice Items for Invoice 9 ---")
cur.execute("SELECT * FROM invoice_items WHERE invoice_id = 9")
for r in cur.fetchall():
    print(dict(r))

print("\n--- Batches for Invoice 9 ---")
cur.execute("SELECT * FROM batches WHERE invoice_id = 9")
for r in cur.fetchall():
    print(dict(r))

conn.close()
