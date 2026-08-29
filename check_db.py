import sqlite3
import os

db_path = os.path.join(os.environ['PROGRAMDATA'], 'BeanchMark-MMS', 'inventory - BeanchMark-MMS.db')
if not os.path.exists(db_path):
    print(f"Database not found at {db_path}")
else:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("SELECT id, batch_no, description, received_date, received_quantity, available_quantity, uom FROM batches")
    rows = cur.fetchall()
    for row in rows:
        print(dict(row))
    conn.close()
