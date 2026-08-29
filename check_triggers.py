import sqlite3
import os

FACTORY_NAME = "BeanchMark-MMS"
PROGRAM_DATA_DIR = os.path.join(os.environ["PROGRAMDATA"], FACTORY_NAME)
DATABASE = os.path.join(PROGRAM_DATA_DIR, "inventory - BeanchMark-MMS.db")

conn = sqlite3.connect(DATABASE)
cur = conn.cursor()

cur.execute("SELECT name, sql FROM sqlite_master WHERE type='trigger'")
triggers = cur.fetchall()
for t in triggers:
    print(f"Trigger: {t[0]}\nSQL: {t[1]}\n")

conn.close()
