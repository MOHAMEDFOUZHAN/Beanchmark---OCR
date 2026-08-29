import sqlite3
import os

DATABASE = r"C:\ProgramData\BeanchMark-MMS\inventory - BeanchMark-MMS.db"

def analyze_duplicates():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    print("--- Analyzing Duplicate Material Codes ---")
    
    # Find codes that appear more than once in the Master List logic
    cur.execute("""
        SELECT material_code, COUNT(*) as master_count
        FROM (
            SELECT DISTINCT material_code, description, category, unit, reorder_level 
            FROM materials
        )
        GROUP BY material_code
        HAVING master_count > 1
    """)
    
    duplicates = cur.fetchall()
    
    if not duplicates:
        print("No duplicates found using the DISTINCT logic.")
    else:
        for dup in duplicates:
            code = dup['material_code']
            print(f"\nCode: {code} (Found {dup['master_count']} variations in master list)")
            
            cur.execute("""
                SELECT DISTINCT material_code, description, category, unit, reorder_level 
                FROM materials 
                WHERE material_code = ?
            """, (code,))
            
            variations = cur.fetchall()
            for i, var in enumerate(variations):
                print(f"  Variation {i+1}: Desc='{var['description']}', Cat='{var['category']}', Unit='{var['unit']}', Reorder={var['reorder_level']}")

    print("\n--- Raw Rows in materials table for 803 ---")
    cur.execute("SELECT id, material_code, description, lot_no, quantity FROM materials WHERE material_code = '803'")
    for row in cur.fetchall():
        print(dict(row))

    conn.close()

if __name__ == "__main__":
    analyze_duplicates()
