import sqlite3
import os

db_path = os.path.join(os.environ['PROGRAMDATA'], 'BeanchMark-MMS', 'inventory - BeanchMark-MMS.db')

MAPPING = {
    "chocolae factory": "chocolate factory",
    "chocolate facory": "chocolate factory",
    "chocolate factor": "chocolate factory",
    "chocolate factory": "chocolate factory",
    "chocolate factory.": "chocolate factory",
    "chocolate factory (new)": "chocolate factory",
    "chocolate facttory": "chocolate factory",
    "kitchen and chocolate factory": "chocolate factory",
    "tea": "Tea factory",
    "tea factory": "Tea factory",
    "tea counter": "Tea factory",
    "oil counter": "oil Counter",
    "oil couter": "oil Counter",
    "oil factory": "oil Counter",
    "varkey factory": "Varkey factory",
    "kitchen": "Kitchen"
}

def clean_database():
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    
    tables = ["transfers", "batches", "dispatches"]
    output_log = []
    
    for table in tables:
        cur.execute(f"SELECT name FROM sqlite_master WHERE type='table' AND name='{table}'")
        if not cur.fetchone(): continue
            
        cur.execute(f"SELECT DISTINCT department FROM {table} WHERE department IS NOT NULL")
        depts = cur.fetchall()
        
        for (old_name,) in depts:
            if not old_name: continue
            lookup = old_name.strip().lower()
            if lookup in MAPPING:
                new_name = MAPPING[lookup]
                if old_name != new_name:
                    cur.execute(f"UPDATE {table} SET department = ? WHERE department = ?", (new_name, old_name))
                    output_log.append(f"Fixed {table}: [{old_name}] -> [{new_name}] ({cur.rowcount} rows)")
    
    conn.commit()
    conn.close()
    
    with open("fix_log.txt", "w") as f:
        f.write("\n".join(output_log))
        if not output_log:
            f.write("No corrections were needed (already clean).")

if __name__ == "__main__":
    clean_database()
