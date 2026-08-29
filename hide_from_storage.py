import sqlite3
import os

FACTORY_NAME = "BeanchMark-MMS"
PROGRAM_DATA_DIR = os.path.join(os.environ["PROGRAMDATA"], FACTORY_NAME)
DATABASE = os.path.join(PROGRAM_DATA_DIR, "inventory - BeanchMark-MMS.db")

conn = sqlite3.connect(DATABASE)
cur = conn.cursor()

codes = ['308', '309', '310', '311', '312', '313']

print("Removing specific materials from Storage list (setting available_quantity to 0 in batches)...")

for code in codes:
    cur.execute("UPDATE batches SET available_quantity = 0 WHERE material_code = ?", (code,))
    print(f"Removed Code {code} from Storage.")

conn.commit()
conn.close()
print("Cleanup completed. These items will no longer appear on the Storage page.")
