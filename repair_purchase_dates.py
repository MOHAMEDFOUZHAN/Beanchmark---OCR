import sqlite3
import os

DATABASE = r"C:\ProgramData\BeanchMark-MMS\inventory - BeanchMark-MMS.db"

def repair_dates():
    if not os.path.exists(DATABASE):
        print(f"Error: Database not found at {DATABASE}")
        return

    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    print("Attempting to repair purchase dates from invoice history...")

    # Find all lots that have an invoice record
    cur.execute("""
        SELECT 
            ii.material, 
            ii.batch_no, 
            MIN(i.date) as real_date
        FROM invoice_items ii
        JOIN invoices i ON ii.invoice_id = i.id
        GROUP BY ii.material, ii.batch_no
    """)
    
    updates = cur.fetchall()
    count = 0
    
    for row in updates:
        mat_code = row['material']
        lot_no = row['batch_no']
        real_date = row['real_date']
        
        # Update the materials table
        cur.execute("""
            UPDATE materials 
            SET purchase_date = ? 
            WHERE material_code = ? AND lot_no = ?
        """, (real_date, mat_code, lot_no))
        
        if cur.rowcount > 0:
            count += 1
            if count % 10 == 0:
                print(f"Repaired {count} records...")

    conn.commit()
    print(f"Finished! Total records repaired: {count}")
    conn.close()

if __name__ == "__main__":
    repair_dates()
