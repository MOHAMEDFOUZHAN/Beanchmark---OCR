import sqlite3
import os

FACTORY_NAME = "BeanchMark-MMS"
PROGRAM_DATA_DIR = os.path.join(os.environ["PROGRAMDATA"], FACTORY_NAME)
DATABASE = os.path.join(PROGRAM_DATA_DIR, "inventory - BeanchMark-MMS.db")

conn = sqlite3.connect(DATABASE)
cur = conn.cursor()

cur.execute("SELECT name, sql FROM sqlite_master WHERE name IN ('materials', 'batches')")
schema = cur.fetchall()
for s in schema:
    print(f"Table: {s[0]}\nSQL: {s[1]}\n")

conn.close()
