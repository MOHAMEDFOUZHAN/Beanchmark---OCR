import sqlite3
import os

db_path = os.path.join(os.environ['PROGRAMDATA'], 'BeanchMark-MMS', 'inventory - BeanchMark-MMS.db')
if not os.path.exists(db_path):
    print(f"Database not found at {db_path}")
else:
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    
    # We want to keep ONLY these 5 specific batches shown in the image.
    # We will use a combination of batch_no, description, and received_quantity to identify them uniquely.
    
    keep_list = [
        ('32', 'cardamom', 632),
        ('26', 'ginger', 1034),
        ('26', 'ctc dust tea', 2000),
        ('26', 'cardamom', 77),
        ('26', 'masala', 400)
    ]
    
    # Get all IDs first
    cur.execute("SELECT id, batch_no, description, received_quantity FROM batches")
    all_rows = cur.fetchall()
    
    ids_to_keep = []
    for row in all_rows:
        rid, rb_no, rdesc, rqty = row
        # Check if this row is in our keep list
        for kb_no, kdesc, kqty in keep_list:
            if str(rb_no) == kb_no and rdesc.lower() == kdesc.lower() and abs(float(rqty) - kqty) < 0.01:
                ids_to_keep.append(rid)
                break
    
    print(f"Found {len(ids_to_keep)} batches to keep: {ids_to_keep}")
    
    if len(ids_to_keep) > 0:
        # Delete everything else
        placeholders = ','.join(['?'] * len(ids_to_keep))
        cur.execute(f"DELETE FROM batches WHERE id NOT IN ({placeholders})", ids_to_keep)
        conn.commit()
        print(f"Deleted {cur.rowcount} unwanted batches.")
    else:
        print("Warning: No matching batches found to keep! Aborting deletion to prevent total data loss.")
    
    conn.close()
