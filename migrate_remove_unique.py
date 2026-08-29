import sqlite3
import os

db_path = os.path.join(os.environ['PROGRAMDATA'], 'BeanchMark-MMS', 'inventory - BeanchMark-MMS.db')
if not os.path.exists(db_path):
    print(f"Database not found at {db_path}")
    exit(1)

conn = sqlite3.connect(db_path)
cur = conn.cursor()

try:
    # 1. Check current schema
    cur.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='materials'")
    create_sql = cur.fetchone()[0]
    
    if "UNIQUE" in create_sql.upper() and "MATERIAL_CODE" in create_sql.upper():
        print("Found UNIQUE constraint on material_code. Proceeding with migration...")
        
        # 2. PRAGMA to get columns
        cur.execute("PRAGMA table_info(materials)")
        cols = cur.fetchall()
        col_names = [c[1] for c in cols]
        
        # 3. Rename old table
        cur.execute("ALTER TABLE materials RENAME TO materials_old")
        
        # 4. Create new table WITHOUT UNIQUE on material_code
        cur.execute("""
            CREATE TABLE materials (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                material_code TEXT NOT NULL,
                description TEXT,
                category TEXT,
                opening_stock REAL DEFAULT 0,
                quantity REAL DEFAULT 0,
                reorder_level INTEGER DEFAULT 0,
                purchase_date TEXT,
                expiry_date TEXT,
                lot_no TEXT,
                unit_price REAL DEFAULT 0,
                unit TEXT,
                last_updated TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # 5. Copy data
        cols_str = ", ".join(col_names)
        cur.execute(f"INSERT INTO materials ({cols_str}) SELECT {cols_str} FROM materials_old")
        
        # 6. Drop old table
        cur.execute("DROP TABLE materials_old")
        
        conn.commit()
        print("Migration successful: material_code is no longer UNIQUE.")
    else:
        print("material_code is already non-unique or UNIQUE constraint not found in the expected format.")

except Exception as e:
    conn.rollback()
    print(f"Migration failed: {e}")
finally:
    conn.close()
