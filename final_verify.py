import sqlite3
import os

db_path = os.path.join(os.environ['PROGRAMDATA'], 'BeanchMark-MMS', 'inventory - BeanchMark-MMS.db')
conn = sqlite3.connect(db_path)
cur = conn.cursor()

result = {}

cur.execute("SELECT COUNT(*) FROM materials WHERE material_code = '1000'")
result['materials_left'] = cur.fetchone()[0]

cur.execute("SELECT COUNT(*) FROM transfers WHERE code = '1000'")
result['transfers'] = cur.fetchone()[0]

cur.execute("SELECT COUNT(*) FROM dispatches WHERE material_code = '1000'")
result['dispatches'] = cur.fetchone()[0]

conn.close()

with open("final_verify.txt", "w") as f:
    for k, v in result.items():
        f.write(f"{k}: {v}\n")
