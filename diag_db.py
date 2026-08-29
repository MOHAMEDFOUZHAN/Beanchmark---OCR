import sqlite3
import os
import sys

print("Python diagnostic starting...")
sys.stdout.flush()

DATABASE = r"d:\Beanchmark\inventory - BeanchMark-MMS.db"

def check_db(path):
    print(f"Checking path: {path}")
    if not os.path.exists(path):
        print(f"DB not found at: {path}")
        return
    
    print(f"\n--- Checking DB: {path} ---")
    try:
        conn = sqlite3.connect(path)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        
        # Get all tables
        cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [row['name'] for row in cur.fetchall()]
        
        for table in tables:
            cur.execute(f"SELECT COUNT(*) as count FROM {table}")
            count = cur.fetchone()['count']
            print(f"Table: {table:20} | Rows: {count}")
            sys.stdout.flush()
            
        # Check for '0' or empty in critical columns
        checks = [
            ('materials', 'material_code'),
            ('invoices', 'invoice_no'),
            ('invoice_items', 'material'),
            ('batches', 'batch_no'),
            ('batches', 'material_code'),
            ('dispatches', 'material_code'),
            ('transfers', 'code')
        ]
        
        print("\n--- Checking for '0', '00', or empty values ---")
        for table, col in checks:
            try:
                cur.execute(f"SELECT COUNT(*) as count FROM {table} WHERE {col} IN ('0', '00', '0.0', '') OR {col} IS NULL")
                count = cur.fetchone()['count']
                if count > 0:
                    print(f"WARNING: {table}.{col} has {count} rows with '0' or empty values.")
                    sys.stdout.flush()
            except Exception as e:
                print(f"Error checking {table}.{col}: {e}")

        # Check for orphaned records
        print("\n--- Checking for orphaned records ---")
        
        # invoice_items without invoices
        cur.execute("SELECT COUNT(*) as count FROM invoice_items WHERE invoice_id NOT IN (SELECT id FROM invoices)")
        count = cur.fetchone()['count']
        if count > 0:
            print(f"WARNING: invoice_items has {count} rows referencing non-existent invoices.")

        # material_code not in materials table
        for table, col in [('invoice_items', 'material'), ('batches', 'material_code'), ('dispatches', 'material_code'), ('transfers', 'code')]:
            try:
                cur.execute(f"SELECT COUNT(*) as count FROM {table} WHERE {col} NOT IN (SELECT material_code FROM materials) AND {col} IS NOT NULL AND {col} != ''")
                count = cur.fetchone()['count']
                if count > 0:
                    print(f"WARNING: {table}.{col} has {count} rows with material codes NOT in materials table.")
                    # Show some examples
                    cur.execute(f"SELECT DISTINCT {col} FROM {table} WHERE {col} NOT IN (SELECT material_code FROM materials) AND {col} IS NOT NULL AND {col} != '' LIMIT 5")
                    examples = [row[0] for row in cur.fetchall()]
                    print(f"   Examples: {examples}")
                    sys.stdout.flush()
            except Exception as e:
                print(f"Error checking orphaned material codes in {table}: {e}")

        conn.close()
    except Exception as e:
        print(f"Connection error: {e}")

check_db(DATABASE)
print("\nDone.")
sys.stdout.flush()
