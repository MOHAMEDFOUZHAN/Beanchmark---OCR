import sqlite3, os
db_path = os.path.join(os.environ['PROGRAMDATA'], 'BeanchMark-MMS', 'inventory - BeanchMark-MMS.db')
conn = sqlite3.connect(db_path)
cur = conn.cursor()
cur.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='materials'")
sql = cur.fetchone()[0]
with open('schema_check.txt', 'w') as f:
    f.write(sql)
conn.close()
