import sqlite3
import os

FACTORY_NAME = "BeanchMark-MMS"
PROGRAM_DATA_DIR = os.path.join(os.environ["PROGRAMDATA"], FACTORY_NAME)
DATABASE = os.path.join(PROGRAM_DATA_DIR, "inventory - BeanchMark-MMS.db")

conn = sqlite3.connect(DATABASE)
cur = conn.cursor()

test_code = '1000'

print(f"Searching for test code '{test_code}' across all tables...")

tables_and_columns = [
    ('materials', 'material_code'),
    ('batches', 'material_code'),
    ('invoice_items', 'material'),
    ('transfers', 'code'),
    ('dispatches', 'material_code')
]

for table, column in tables_and_columns:
    cur.execute(f"SELECT COUNT(*) FROM {table} WHERE {column} = ?", (test_code,))
    count = cur.fetchone()[0]
    print(f"Table '{table}': {count} records found.")

conn.close()
