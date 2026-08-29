import sqlite3
import os

PATHS = [
    r"d:\Beanchmark\inventory - BeanchMark-MMS.db",
    os.path.join(os.environ["PROGRAMDATA"], "BeanchMark-MMS", "inventory - BeanchMark-MMS.db")
]

with open("diag_output.txt", "w") as f:
    for DATABASE in PATHS:
        f.write(f"\n{'='*20}\nChecking: {DATABASE}\n{'='*20}\n")
        if not os.path.exists(DATABASE):
            f.write(f"DB not found at this path.\n")
            continue
            
        try:
            conn = sqlite3.connect(DATABASE)
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            
            cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")
            tables = [row['name'] for row in cur.fetchall()]
            f.write(f"Tables found: {', '.join(tables)}\n")
            
            for table in tables:
                cur.execute(f"SELECT COUNT(*) FROM {table}")
                count = cur.fetchone()[0]
                f.write(f"Table {table}: {count} rows\n")
                
            # Missing material codes check
            f.write("\nChecking for missing material codes in materials table:\n")
            checks = [
                ('invoice_items', 'material'),
                ('batches', 'material_code'),
                ('dispatches', 'material_code'),
                ('transfers', 'code')
            ]
            
            for table, col in checks:
                if table in tables:
                    cur.execute(f"""
                        SELECT DISTINCT {col} FROM {table} 
                        WHERE {col} NOT IN (SELECT material_code FROM materials) 
                        AND {col} IS NOT NULL AND {col} != ''
                    """)
                    missing = [row[0] for row in cur.fetchall()]
                    if missing:
                        f.write(f"Table {table} field {col} has codes not in materials: {missing[:10]}\n")
                    else:
                        f.write(f"Table {table} field {col}: All good.\n")
                else:
                    f.write(f"Table {table} does not exist.\n")
                    
            # Check for '0' or empty in critical columns
            f.write("\nChecking for '0' or empty critical values:\n")
            checks_0 = [
                ('materials', 'material_code'),
                ('invoices', 'invoice_no'),
                ('batches', 'batch_no')
            ]
            for table, col in checks_0:
                if table in tables:
                    cur.execute(f"SELECT COUNT(*) FROM {table} WHERE {col} IN ('0', '00', '0.0', '') OR {col} IS NULL")
                    count = cur.fetchone()[0]
                    if count > 0:
                        f.write(f"WARNING: {table}.{col} has {count} zeros/empty values.\n")
                    else:
                        f.write(f"{table}.{col}: All good.\n")

            conn.close()
        except Exception as e:
            f.write(f"Error: {e}\n")
    f.write("\nFinished.\n")
