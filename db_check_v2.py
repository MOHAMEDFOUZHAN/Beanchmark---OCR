import sqlite3
import os

path1 = r"d:\Beanchmark\inventory - BeanchMark-MMS.db"
path2 = os.path.join(os.environ.get("PROGRAMDATA", ""), "BeanchMark-MMS", "inventory - BeanchMark-MMS.db")

with open(r"d:\Beanchmark\db_results.txt", "w") as f:
    for p in [path1, path2]:
        if os.path.exists(p):
            f.write(f"Checking {p}...\n")
            try:
                conn = sqlite3.connect(p)
                cur = conn.cursor()
                cur.execute("SELECT COUNT(*) FROM invoices")
                f.write(f"Invoices count: {cur.fetchone()[0]}\n")
                cur.execute("SELECT date FROM invoices LIMIT 5")
                for row in cur.fetchall():
                    f.write(f"Invoice date: {row[0]}\n")
                conn.close()
            except Exception as e:
                f.write(f"Error: {e}\n")
        else:
            f.write(f"Path not found: {p}\n")
