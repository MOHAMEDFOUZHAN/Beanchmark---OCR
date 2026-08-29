import sqlite3
import os

FACTORY_NAME = "BeanchMark-MMS"
PROGRAM_DATA_DIR = os.path.join(os.environ["PROGRAMDATA"], FACTORY_NAME)
DATABASE = os.path.join(PROGRAM_DATA_DIR, "inventory - BeanchMark-MMS.db")

conn = sqlite3.connect(DATABASE)
cur = conn.cursor()

test_code = '1000'

print(f"Deleting test code '{test_code}' from database...")

# Delete from Materials
cur.execute("DELETE FROM materials WHERE material_code = ?", (test_code,))
print(f"Deleted from materials: {cur.rowcount} rows")

# Delete from Invoice Items
cur.execute("DELETE FROM invoice_items WHERE material = ?", (test_code,))
print(f"Deleted from invoice_items: {cur.rowcount} rows")

# Delete from Batches (just in case, though 0 were found)
cur.execute("DELETE FROM batches WHERE material_code = ?", (test_code,))
print(f"Deleted from batches: {cur.rowcount} rows")

# Delete from Transfers
cur.execute("DELETE FROM transfers WHERE code = ?", (test_code,))
print(f"Deleted from transfers: {cur.rowcount} rows")

# Delete from Dispatches
cur.execute("DELETE FROM dispatches WHERE material_code = ?", (test_code,))
print(f"Deleted from dispatches: {cur.rowcount} rows")

conn.commit()
conn.close()
print("Test code '1000' has been completely removed.")
