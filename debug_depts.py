import sqlite3
import os

db_path = os.path.join(os.environ['PROGRAMDATA'], 'BeanchMark-MMS', 'inventory - BeanchMark-MMS.db')
if not os.path.exists(db_path):
    print(f"Database not found at {db_path}")
else:
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("SELECT department, COUNT(*) FROM transfers GROUP BY department ORDER BY department")
    rows = cur.fetchall()
    
    print("Listing unique departments and their lengths:")
    print("-" * 50)
    for row in rows:
        dept = row[0] if row[0] is not None else "NULL"
        count = row[1]
        length = len(dept)
        # Represent spaces with dots to make them visible
        visible_dept = dept.replace(" ", ".")
        print(f"Name: [{visible_dept}] | Length: {length} | Rows: {count}")
    conn.close()
