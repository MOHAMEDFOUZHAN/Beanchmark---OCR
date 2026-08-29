import sqlite3
import os

DATABASE = os.path.join(os.environ["PROGRAMDATA"], "BeanchMark-MMS", "inventory - BeanchMark-MMS.db")

def recover():
    if not os.path.exists(DATABASE):
        print("DB not found")
        return
    
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    
    # Missing codes from diagnostic
    codes = ['900', '802', '901', '902', '903', '904', '905', '906', '907', '908']
    
    print("--- Searching for descriptions of orphaned codes ---")
    for code in codes:
        desc = None
        # Try transfers
        cur.execute("SELECT description FROM transfers WHERE code = ? LIMIT 1", (code,))
        res = cur.fetchone()
        if res:
            desc = res['description']
        else:
            # Try invoice_items (Wait, invoice_items doesn't have description)
            # Try batches (using material_code)
            cur.execute("SELECT description FROM batches WHERE material_code = ? LIMIT 1", (code,))
            res = cur.fetchone()
            if res:
                desc = res['description']
        
        if desc:
            print(f"Code {code}: Found Description '{desc}'")
            # Propose to restore?
        else:
            print(f"Code {code}: Not found anywhere")
            
    conn.close()

recover()
