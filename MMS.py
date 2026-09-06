import os
os.environ["PYTHONIOENCODING"] = "utf-8"
from backup_manager import MirrorBackup
from flask import Flask, render_template, request, redirect, url_for, session, g, jsonify
import sqlite3
from datetime import datetime, timedelta  # Add timedelta here
import threading
import webview
from waitress import serve


# -------------------
# ⭐ Add normalize_date RIGHT HERE
# -------------------
def normalize_date(raw_date):
    """Convert any date format to clean YYYY-MM-DD (no time). Returns today's date ONLY if input is empty."""
    today = datetime.now().strftime("%Y-%m-%d")
    if not raw_date or not str(raw_date).strip():
        return today

    raw_date = str(raw_date).strip()

    # If date has time → remove time part
    if " " in raw_date:
        raw_date = raw_date.split(" ")[0]

    # Try dd-mm-yyyy or dd/mm/yyyy → yyyy-mm-dd
    for fmt in ["%d-%m-%Y", "%d/%m/%Y"]:
        try:
            dt = datetime.strptime(raw_date, fmt)
            return dt.strftime("%Y-%m-%d")
        except:
            pass

    return today

def should_reset_daily_data():
    """Check if we need to reset daily data (new day)"""
    # Use direct connection instead of get_db()
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    
    today = datetime.now().strftime("%Y-%m-%d")
    
    # Check if any material was updated today
    cur.execute("SELECT COUNT(*) as count FROM materials WHERE date(last_updated) = ?", (today,))
    count = cur.fetchone()["count"]
    
    conn.close()
    return count == 0  # Reset if no updates today

def reset_daily_data():
    """Reset daily data: Yesterday's quantity becomes today's opening_stock."""
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    
    today = datetime.now().strftime("%Y-%m-%d")
    
    print(f"Resetting daily data for {today}...")
    
    # Update: Yesterday's quantity becomes today's opening_stock
    # Removed automatic purchase_date update as it's confusing
    cur.execute("""
        UPDATE materials 
        SET opening_stock = quantity,
            last_updated = ?
    """, (today,))
    
    conn.commit()
    mirror.mirror_backup()
    conn.close()
    print("Daily data reset completed")

# Optional: if you have this module, it will be launched in background
try:
    import smart_report_mailer
except Exception:
    smart_report_mailer = None

try:
    from ocr_invoice_parser import extract_invoice_data_from_bytes
except Exception as e:
    extract_invoice_data_from_bytes = None
    print("OCR Invoice parser load warning:", e)


import sys

if getattr(sys, 'frozen', False):
    base_dir = sys._MEIPASS
    app = Flask(__name__,
                template_folder=os.path.join(base_dir, 'templates'),
                static_folder=os.path.join(base_dir, 'static'))
else:
    app = Flask(__name__)
app.secret_key = "super_secret_key"

@app.template_filter('format_date')
def format_date_filter(date_str):
    if not date_str or str(date_str).strip() == 'N/A' or str(date_str).strip() == '':
        return date_str
    date_str = str(date_str).strip()
    try:
        # Try YYYY-MM-DD
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        return dt.strftime("%d/%m/%Y")
    except:
        try:
            # Try already DD-MM-YYYY or DD/MM/YYYY
            for fmt in ["%d-%m-%Y", "%d/%m/%Y"]:
                try:
                    dt = datetime.strptime(date_str, fmt)
                    return dt.strftime("%d/%m/%Y")
                except: continue
            return date_str
        except:
            return date_str

# ⭐ Standardized Departments List (to prevent spelling mistakes)
DEPARTMENTS = ["chocolate factory", "Tea factory", "Varkey factory", "oil Counter", "Kitchen"]

@app.after_request
def auto_mirror(response):
    try:
        # If the DB was used in this request → update mirror backup
        if 'db' in g:
            mirror.mirror_backup()
    except:
        pass
    return response


import sys
FACTORY_NAME = "BeanchMark-MMS"

# Find ProgramData folder like C:\ProgramData
PROGRAM_DATA_DIR = os.path.join(os.environ["PROGRAMDATA"], FACTORY_NAME)

# Create folder if it does not exist
os.makedirs(PROGRAM_DATA_DIR, exist_ok=True)

# Main DB location (Protected)
DATABASE = os.path.join(PROGRAM_DATA_DIR, "inventory - BeanchMark-MMS.db")

# Mirror backup folder inside ProgramData
MIRROR_BACKUP_FOLDER = os.path.join(PROGRAM_DATA_DIR, "backup")


mirror = MirrorBackup(
    main_db_path=DATABASE,
    backup_folder=MIRROR_BACKUP_FOLDER
)
mirror.mirror_backup()
# -----------------------------
def get_db():
    """Get a connection to inventory.db stored in flask.g"""
    if 'db' not in g:
        g.db = sqlite3.connect(DATABASE)
        g.db.row_factory = sqlite3.Row
    return g.db

@app.teardown_appcontext
def teardown_db(exception):
    db = g.pop('db', None)
    if db is not None:
        db.close()

# -----------------------------
# Initialize / create inventory DB if missing
# -----------------------------
def initialize_database(db_path):
    """Create inventory.db if missing OR use existing one."""
    if not os.path.exists(db_path):
        print("Creating NEW database:", db_path)
    else:
        print("Using EXISTING database:", db_path)

    connection = sqlite3.connect(db_path)
    cursor = connection.cursor()

    # -------------------- MATERIALS --------------------
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS materials (
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
    );
    """)

    # -------------------- VENDORS --------------------
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS vendors (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        contact TEXT,
        place TEXT,
        pincode TEXT,
        gstin TEXT,
        material TEXT,
        info TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    );
    """)

    # -------------------- INVOICES --------------------
    # ⭐ Added total_igst here
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS invoices (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        purchase_id TEXT,
        date TEXT,
        invoice_no TEXT NOT NULL UNIQUE,
        vendor TEXT,
        no_of_items INTEGER DEFAULT 1,
        total_excl_tax REAL DEFAULT 0,
        total_gst REAL DEFAULT 0,
        total_igst REAL DEFAULT 0,        -- ⭐ NEW
        cgst_percent REAL DEFAULT 0,
        sgst_percent REAL DEFAULT 0,
        round_off_value REAL DEFAULT 0,
        final_total REAL DEFAULT 0,
        grand_total REAL DEFAULT 0,
        payment_status TEXT DEFAULT 'Pending',
        remarks TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    );
    """)

    # -------------------- INVOICE ITEMS --------------------
    # ⭐ Added igst_percentage and item_igst_value here
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS invoice_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        invoice_id INTEGER NOT NULL,
        material TEXT NOT NULL,
        quantity REAL,
        unit TEXT,
        unit_price REAL,
        discount_percentage REAL DEFAULT 0,
        gst_percentage REAL,
        igst_percentage REAL DEFAULT 0,   -- ⭐ NEW
        item_subtotal REAL,
        item_gst_value REAL,
        item_igst_value REAL DEFAULT 0,   -- ⭐ NEW
        item_total REAL,
        batch_no TEXT,
        FOREIGN KEY (invoice_id) REFERENCES invoices (id) ON DELETE CASCADE
    );
    """)

    # -------------------- DISPATCHES --------------------
   # Add this to your database initialization
    # -------------------- DISPATCHES --------------------
# -------------------- DISPATCHES --------------------
    cursor.execute("""
CREATE TABLE IF NOT EXISTS dispatches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT,
    material_code TEXT NOT NULL,
    product TEXT,
    quantity REAL,
    units TEXT,
    location TEXT,
    department TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
""")

# -------------------- DISPATCH BATCHES --------------------
    cursor.execute("""
CREATE TABLE IF NOT EXISTS dispatch_batches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    dispatch_id INTEGER,
    batch_no TEXT,
    batch_id INTEGER,  -- ⭐ NEW: Store the specific batch ID
    quantity REAL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(dispatch_id) REFERENCES dispatches(id) ON DELETE CASCADE,
    FOREIGN KEY(batch_id) REFERENCES batches(id) ON DELETE CASCADE
);
""")

    # -------------------- TRANSFERS --------------------
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS transfers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date TEXT,
        code TEXT,
        description TEXT,
        lot_no TEXT,
        outward REAL DEFAULT 0,
        units TEXT,
        department TEXT,
        person TEXT,
        return_units REAL DEFAULT 0,
        availability REAL DEFAULT 0,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    );
    """)

    # -------------------- BATCHES (STORAGE) --------------------
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS batches (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        batch_no TEXT ,
        material_code TEXT,
        description TEXT,
        received_quantity REAL,
        available_quantity REAL,
        uom TEXT,
        received_date TEXT,
        department TEXT,
        invoice_id INTEGER,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    );
    """)

    # -------------------- CATEGORY LOCATIONS --------------------
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS category_locations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        category TEXT NOT NULL UNIQUE,
        location TEXT,
        last_updated TEXT DEFAULT CURRENT_TIMESTAMP
    );
    """)

    connection.commit()
    connection.close()
    print("inventory.db ensured")

# Ensure inventory DB exists
initialize_database(DATABASE)

# Ensure inventory DB exists
initialize_database(DATABASE)

# ⭐ UPDATED: Database schema check (Adds columns if they are missing)
# ⭐ UPDATED: Database schema check (Adds available_quantity to batches)
def update_database_schema():
    """Update existing database with ALL new fields automatically, handling duplicates gracefully."""
    conn = sqlite3.connect(DATABASE)
    cur = conn.cursor()
    
    try:
        # Get existing columns for all tables to check before adding
        # 1. Update INVOICES Table
        cur.execute("PRAGMA table_info(invoices)")
        inv_columns = [col[1] for col in cur.fetchall()]
        
        invoice_updates = [
            ('cgst_percent', "ALTER TABLE invoices ADD COLUMN cgst_percent REAL DEFAULT 0"),
            ('sgst_percent', "ALTER TABLE invoices ADD COLUMN sgst_percent REAL DEFAULT 0"),
            ('round_off_value', "ALTER TABLE invoices ADD COLUMN round_off_value REAL DEFAULT 0"),
            ('final_total', "ALTER TABLE invoices ADD COLUMN final_total REAL DEFAULT 0"),
            ('total_igst', "ALTER TABLE invoices ADD COLUMN total_igst REAL DEFAULT 0")
        ]
        
        for col_name, sql in invoice_updates:
            if col_name not in inv_columns:
                try:
                    cur.execute(sql)
                except sqlite3.OperationalError:
                    pass

        # 2. Update INVOICE_ITEMS Table
        cur.execute("PRAGMA table_info(invoice_items)")
        item_columns = [col[1] for col in cur.fetchall()]
        
        item_updates = [
            ('discount_percentage', "ALTER TABLE invoice_items ADD COLUMN discount_percentage REAL DEFAULT 0"),
            ('igst_percentage', "ALTER TABLE invoice_items ADD COLUMN igst_percentage REAL DEFAULT 0"),
            ('item_igst_value', "ALTER TABLE invoice_items ADD COLUMN item_igst_value REAL DEFAULT 0"),
            ('hsn_sac', "ALTER TABLE invoice_items ADD COLUMN hsn_sac TEXT")
        ]
        
        for col_name, sql in item_updates:
            if col_name not in item_columns:
                try:
                    cur.execute(sql)
                except sqlite3.OperationalError:
                    pass

        # 3. Update MATERIALS Table
        cur.execute("PRAGMA table_info(materials)")
        mat_columns = [col[1] for col in cur.fetchall()]

        if 'purchase_date' not in mat_columns:
            cur.execute("ALTER TABLE materials ADD COLUMN purchase_date TEXT")
        if 'expiry_date' not in mat_columns:
            cur.execute("ALTER TABLE materials ADD COLUMN expiry_date TEXT")
        if 'hsn_sac' not in mat_columns:
            try:
                cur.execute("ALTER TABLE materials ADD COLUMN hsn_sac TEXT")
            except sqlite3.OperationalError:
                pass

        # 4. Update BATCHES Table
        cur.execute("PRAGMA table_info(batches)")
        batch_columns = [col[1] for col in cur.fetchall()]

        if 'available_quantity' not in batch_columns:
            cur.execute("ALTER TABLE batches ADD COLUMN available_quantity REAL")
            cur.execute("UPDATE batches SET available_quantity = received_quantity")
            print("Added available_quantity column to batches")

        if 'received_date' not in batch_columns:
            cur.execute("ALTER TABLE batches ADD COLUMN received_date TEXT")
            cur.execute("UPDATE batches SET received_date = created_at WHERE received_date IS NULL")
            print("Added received_date column to batches")

        if 'department' not in batch_columns:
            try:
                cur.execute("ALTER TABLE batches ADD COLUMN department TEXT")
                print("Added department column to batches")
            except sqlite3.OperationalError:
                pass

        if 'invoice_id' not in batch_columns:
            try:
                cur.execute("ALTER TABLE batches ADD COLUMN invoice_id INTEGER")
                print("Added invoice_id column to batches")
            except sqlite3.OperationalError:
                pass

        # 5. Ensure stock_adjustments table schema is clean & up to date
        cur.execute("PRAGMA table_info(stock_adjustments)")
        sa_cols = [col[1] for col in cur.fetchall()]

        if 'code' in sa_cols:
            print("Migrating legacy stock_adjustments table schema...")
            cur.execute("ALTER TABLE stock_adjustments RENAME TO stock_adjustments_old")
            cur.execute("""
                CREATE TABLE stock_adjustments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    material_code TEXT NOT NULL,
                    operation TEXT NOT NULL,
                    amount REAL NOT NULL,
                    reason TEXT,
                    before_qty REAL,
                    after_qty REAL,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)
            cur.execute("""
                INSERT INTO stock_adjustments (material_code, operation, amount, reason, before_qty, after_qty, created_at)
                SELECT 
                    COALESCE(material_code, code, ''),
                    COALESCE(operation, mode, 'subtract'),
                    COALESCE(amount, qty_change, 0),
                    reason,
                    COALESCE(before_qty, stock_before, 0),
                    COALESCE(after_qty, stock_after, 0),
                    created_at
                FROM stock_adjustments_old
            """)
            cur.execute("DROP TABLE stock_adjustments_old")
            print("stock_adjustments table migrated successfully.")
        else:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS stock_adjustments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    material_code TEXT NOT NULL,
                    operation TEXT NOT NULL,
                    amount REAL NOT NULL,
                    reason TEXT,
                    before_qty REAL,
                    after_qty REAL,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)

        conn.commit()
        print("Database schema verified.")

        
    except Exception as e:
        print(f"Error updating database schema: {e}")
    finally:
        conn.close()
# Run this check immediately
update_database_schema()
# -----------------------------
# ⭐ ONE-TIME FIX: Repair Available Quantity
# -----------------------------
def fix_available_quantity():
    conn = sqlite3.connect(DATABASE)
    cur = conn.cursor()
    try:
        # Check for batches where available_quantity is NULL or 0 but received_quantity > 0
        # We only want to fix rows that look "broken"
        cur.execute("""
            UPDATE batches 
            SET available_quantity = received_quantity 
            WHERE (available_quantity IS NULL OR available_quantity = 0)
            AND received_quantity > 0
        """)
        if cur.rowcount > 0:
            print(f"✅ FIXED: Updated available_quantity for {cur.rowcount} batches.")
        conn.commit()
    except Exception as e:
        print("Fix error:", e)
    finally:
        conn.close()

# Run the fix immediately after schema update
fix_available_quantity()
# ⭐ ADD: Daily reset (transfer stock to opening stock)
if should_reset_daily_data():
    reset_daily_data()
    print("Daily data reset completed.")

# -----------------------------
# Simple auth
# -----------------------------
USER_CREDENTIALS = {"bm": "babaji@108"}

@app.route("/")
def home():
    return redirect(url_for("login"))

@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        if username in USER_CREDENTIALS and USER_CREDENTIALS[username] == password:
            session["user"] = username
            return redirect(url_for("dashboard"))
        else:
            error = "Invalid User ID or Password"
    return render_template("login.html", error=error)

@app.route("/logout")
def logout():
    session.pop("user", None)
    return redirect(url_for("login"))

# -----------------------------
# Dashboard & API
# -----------------------------
@app.route("/dashboard")
def dashboard():
    if "user" not in session:
        return redirect(url_for("login"))
    
    conn = get_db()
    cur = conn.cursor()
    
    # 1. Total Materials
    cur.execute("SELECT COUNT(*) as total FROM materials")
    total_materials = cur.fetchone()["total"]
    
    # 2. Reorder Level
    cur.execute("SELECT COUNT(*) as total FROM materials WHERE quantity <= reorder_level AND quantity > 0")
    reorder_items = cur.fetchone()["total"]
    
    # 3. ⭐ CHANGED: Expiring Soon
    # Counts items where expiry_date is set AND is within the next 30 days (or already expired)
    cur.execute("""
        SELECT COUNT(*) as total FROM materials 
        WHERE expiry_date IS NOT NULL 
        AND expiry_date != '' 
        AND expiry_date <= date('now', '+30 days')
    """)
    expiring_items = cur.fetchone()["total"]
    
    return render_template("dashboard.html", 
                           total_materials=total_materials, 
                           reorder_items=reorder_items, 
                           expiring_items=expiring_items)

@app.route("/api/dashboard_charts")
def get_dashboard_charts():
    if "user" not in session:
        return jsonify({"error": "Not authorized"}), 401
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        SELECT category, SUM(quantity) as total_stock
        FROM materials
        WHERE category IS NOT NULL AND category != ''
        GROUP BY category
    """)
    category_data = [dict(r) for r in cur.fetchall()]
    cur.execute("SELECT description, quantity FROM materials ORDER BY quantity DESC LIMIT 5")
    top_items_data = [dict(r) for r in cur.fetchall()]
    return jsonify(stock_by_category=category_data, top_5_items=top_items_data)

## -----------------------------
# Materials
# -----------------------------
## -----------------------------
# Materials
# -----------------------------
from datetime import datetime

@app.route("/materials")
def material_list():
    if "user" not in session:
        return redirect(url_for("login"))

    # Get today's date in 'YYYY-MM-DD' format
    today_str = datetime.now().strftime("%Y-%m-%d")

    # ⭐ ADD: Check and reset daily data (this will update dates)
    if should_reset_daily_data():
        reset_daily_data()

    conn = get_db()
    cur = conn.cursor()

    # Fetch unique categories for dropdown
    cur.execute("SELECT DISTINCT category FROM materials WHERE category IS NOT NULL AND category != '' ORDER BY category")
    categories = [r["category"] for r in cur.fetchall()]

    # Get filter parameters
    selected_category = request.args.get("category", "")
    search_code = request.args.get("search_code", "").strip()
    from_date = request.args.get("from_date", today_str)
    to_date = request.args.get("to_date", today_str)
    
    # We'll use these for the calculations below
    calc_from = from_date or today_str
    calc_to = to_date or today_str

    # Fetch UNIQUE master materials for the grouped list
    query = "SELECT DISTINCT material_code, description, category, unit, reorder_level FROM materials WHERE 1=1"
    params = []

    if selected_category:
        query += " AND category = ?"
        params.append(selected_category)
    
    if search_code:
        query += " AND material_code LIKE ?"
        params.append(f"%{search_code}%")
    
    query += " ORDER BY material_code"
    
    cur.execute(query, tuple(params))
    master_materials = cur.fetchall()

    # Fetch locations
    cur.execute("SELECT category, location FROM category_locations")
    loc_map = {r['category']: r['location'] for r in cur.fetchall()}

    stock_data = []

    for master in master_materials:
        mat_code = master["material_code"]
        mat_cat = master["category"]
        unit = master["unit"]
        shelf = loc_map.get(mat_cat, 'N/A')

        # Get ALL Lots for this material
        cur.execute("SELECT * FROM materials WHERE material_code = ? ORDER BY expiry_date ASC", (mat_code,))
        lots = cur.fetchall()
        
        # Calculate Aggregates
        total_opening = sum(lot["opening_stock"] or 0 for lot in lots)
        total_closing = sum(lot["quantity"] or 0 for lot in lots)
        
        # 1. TRANSFERRED IN RANGE (Outward)
        cur.execute("""
            SELECT COALESCE(SUM(outward),0) AS total_outward 
            FROM transfers 
            WHERE code = ? AND date(date) BETWEEN ? AND ?
        """, (mat_code, calc_from, calc_to))
        total_outward = cur.fetchone()["total_outward"] or 0

        # 2. RETURNED IN RANGE
        cur.execute("""
            SELECT COALESCE(SUM(return_units),0) AS total_returned 
            FROM transfers 
            WHERE code = ? AND date(date) BETWEEN ? AND ?
        """, (mat_code, calc_from, calc_to))
        total_returned = cur.fetchone()["total_returned"] or 0

        # 3. PURCHASED IN RANGE
        cur.execute("""
            SELECT COALESCE(SUM(ii.quantity), 0) as total_inward
            FROM invoice_items ii
            JOIN invoices i ON ii.invoice_id = i.id
            WHERE ii.material = ? AND date(i.date) BETWEEN ? AND ?
        """, (mat_code, calc_from, calc_to))
        total_inward = cur.fetchone()["total_inward"] or 0

        # Sub-data for each Lot
        lots_display = []
        for lot in lots:
            raw_p_date = lot["purchase_date"]
            raw_e_date = lot["expiry_date"]
            
            # Format dates for lot view
            f_p_date = ""
            if raw_p_date:
                try: f_p_date = datetime.strptime(raw_p_date, "%Y-%m-%d").strftime("%d/%m/%Y")
                except: f_p_date = raw_p_date
            
            f_e_date = ""
            if raw_e_date:
                try: f_e_date = datetime.strptime(raw_e_date, "%Y-%m-%d").strftime("%d/%m/%Y")
                except: f_e_date = raw_e_date

            lots_display.append({
                "lot_no": lot["lot_no"] or "No Lot",
                "opening": round(lot["opening_stock"] or 0, 3),
                "closing": round(lot["quantity"] or 0, 3),
                "purchase_date": f_p_date,
                "expiry_date": f_e_date
            })

        # Append Summary result
        stock_data.append(
            {
                "code": mat_code,
                "name": master["description"], 
                "opening_stock": round(total_opening, 3),
                "purchased_stock": round(total_inward, 3),
                "transferred_stock": round(total_outward, 3),
                "returned_stock": round(total_returned, 3),
                "closing_stock": round(total_closing, 3),
                "reorder_level": master["reorder_level"],
                "unit": unit,
                "location": shelf,
                "lots": lots_display  # <--- LOTS ATTACHED HERE
            }
        )

    return render_template(
        "materials/list.html",
        stock_data=stock_data,
        categories=categories,
        selected_category=selected_category,
        search_code=search_code,
        from_date=calc_from,
        to_date=calc_to
    )

@app.route("/materials/edit/<string:code>", methods=["GET", "POST"])
def material_edit(code):
    if "user" not in session:
        return redirect(url_for("login"))
    conn = get_db()
    cur = conn.cursor()
    if request.method == "POST":
        new_description = request.form.get("description")
        new_category = request.form.get("category")
        new_reorder_level = int(request.form.get("reorder_level") or 0)
        cur.execute("UPDATE materials SET description = ?, category = ?, reorder_level = ? WHERE material_code = ?",
                    (new_description, new_category, new_reorder_level, code))
        conn.commit()
        return redirect(url_for("material_list"))
    cur.execute("SELECT * FROM materials WHERE material_code = ?", (code,))
    material = cur.fetchone()
    if not material:
        return "Material not found", 404
    return render_template("materials/edit_material.html", material=material)

# -----------------------------
# Materials Master (Master Data Management)
# -----------------------------
@app.route("/materials/master")
def materials_master():
    if "user" not in session:
        return redirect(url_for("login"))
    
    conn = get_db()
    cur = conn.cursor()
    
    search_code = request.args.get("search_code", "").strip()
    
    # Get unique materials (one row per code)
    query = "SELECT DISTINCT material_code, description, unit FROM materials WHERE 1=1"
    params = []
    if search_code:
        query += " AND (material_code LIKE ? OR description LIKE ?)"
        params.extend([f"%{search_code}%", f"%{search_code}%"])
    query += " ORDER BY material_code"
    
    cur.execute(query, tuple(params))
    materials = cur.fetchall()
    
    return render_template("materials/materials_master.html", materials=materials, search_code=search_code)

@app.route("/materials/master/update", methods=["POST"])
def update_material_unit():
    if "user" not in session:
        return redirect(url_for("login"))
    
    code = request.form.get("code")
    new_unit = request.form.get("unit")
    
    if not code or not new_unit:
        return "<script>alert('Missing material code or unit');window.history.back();</script>"
    
    conn = get_db()
    cur = conn.cursor()
    
    try:
        # Update 1: materials table
        cur.execute("UPDATE materials SET unit = ? WHERE material_code = ?", (new_unit, code))
        
        # Update 2: batches table (column is 'uom')
        cur.execute("UPDATE batches SET uom = ? WHERE material_code = ?", (new_unit, code))
        
        # Update 3: invoice_items table (column is 'unit', match by 'material' which stores the code)
        cur.execute("UPDATE invoice_items SET unit = ? WHERE material = ?", (new_unit, code))
        
        # Update 4: transfers table (column is 'units', match by 'code')
        cur.execute("UPDATE transfers SET units = ? WHERE code = ?", (new_unit, code))
        
        # Update 5: dispatches table (column is 'units', match by 'material_code')
        cur.execute("UPDATE dispatches SET units = ? WHERE material_code = ?", (new_unit, code))
        
        conn.commit()
        return f"<script>alert('Unit successfully updated to {new_unit} for {code} in all records.');window.location.href='/materials/master';</script>"
    except Exception as e:
        conn.rollback()
        print("Master Data Update Error:", e)
        return f"<script>alert('Error updating unit: {str(e)}');window.history.back();</script>"
    finally:
        conn.close()

# -----------------------------
# New Material Registration
# -----------------------------
@app.route("/materials/new", methods=["GET", "POST"])
def new_material():
    if "user" not in session:
        return redirect(url_for("login"))

    conn = get_db()
    cur = conn.cursor()

    # Get existing categories for datalist
    cur.execute("SELECT DISTINCT category FROM materials WHERE category IS NOT NULL AND category != '' ORDER BY category")
    categories = [r["category"] for r in cur.fetchall()]

    if request.method == "POST":
        code        = request.form.get("material_code", "").strip().upper()
        description = request.form.get("description", "").strip()
        category    = request.form.get("category", "").strip()
        unit        = request.form.get("unit", "").strip()
        reorder_lvl = request.form.get("reorder_level", "0").strip() or "0"

        # Validate required fields
        if not code or not description or not category:
            return render_template("materials/new_material.html",
                                   categories=categories,
                                   error="Code, Description and Category are all required.",
                                   form_data=request.form)

        # Check for duplicate code
        cur.execute("SELECT 1 FROM materials WHERE material_code = ? LIMIT 1", (code,))
        if cur.fetchone():
            return render_template("materials/new_material.html",
                                   categories=categories,
                                   error=f"Material code '{code}' already exists. Please use a different code.",
                                   form_data=request.form)

        today = datetime.now().strftime("%Y-%m-%d")
        try:
            reorder_int = int(float(reorder_lvl))
        except Exception:
            reorder_int = 0

        cur.execute("""
            INSERT INTO materials
              (material_code, description, category, unit, opening_stock, quantity,
               reorder_level, purchase_date, last_updated)
            VALUES (?, ?, ?, ?, 0, 0, ?, ?, ?)
        """, (code, description, category, unit, reorder_int, today, today))
        conn.commit()
        return redirect(url_for("material_list"))

    return render_template("materials/new_material.html", categories=categories, error=None, form_data={})

# -----------------------------
# Storage (Batch Management)
# -----------------------------
@app.route("/storage")

def storage_list():
    """List batches with Date Range and Search filters."""
    if "user" not in session:
        return redirect(url_for("login"))
    
    conn = get_db()
    cur = conn.cursor()
    
    # Get filter parameters
    search = request.args.get("search", "").strip()
    from_date = request.args.get("from_date", "")
    to_date = request.args.get("to_date", "")
    
    # Only show batches with Available Quantity > 0.001 (hide rounding errors)
    query = "SELECT * FROM batches WHERE available_quantity > 0.001"
    params = []
    
    # 1. Apply Date Filter
    if from_date:
        query += " AND date(received_date) >= ?"
        params.append(from_date)
        
    if to_date:
        query += " AND date(received_date) <= ?"
        params.append(to_date)
        
    # 2. Apply Search Filter
    if search:
        query += " AND (batch_no LIKE ? OR material_code LIKE ? OR description LIKE ?)"
        params.extend([f"%{search}%", f"%{search}%", f"%{search}%"])
        
    query += " ORDER BY id DESC"
    
    cur.execute(query, tuple(params))
    batches = cur.fetchall()

    # Format output
    formatted_batches = []
    for batch in batches:
        # Safely handle potential None values
        rec_qty = batch["received_quantity"] or 0
        avail_qty = batch["available_quantity"] or 0
        
        # Format the received quantity for display
        display_received = format_storage_quantity(rec_qty, batch["uom"])
        
        # --- ⭐ THIS IS THE MISSING BLOCK FIXING YOUR ERROR ⭐ ---
        # 1. Date Logic (Robust parsing)
        raw_date = (batch["received_date"] or "").strip() or (batch["created_at"] or "").strip() or "-"
        formatted_date = "-"
        if raw_date and raw_date != "-":
            try:
                # Handle cases with time
                clean_date = raw_date.split(" ")[0] if " " in raw_date else raw_date
                
                # Try standard formats
                dt = None
                for fmt in ["%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y"]:
                    try:
                        dt = datetime.strptime(clean_date, fmt)
                        break
                    except: continue
                
                if dt:
                    formatted_date = dt.strftime("%d/%m/%Y")
                else:
                    formatted_date = raw_date
            except:
                formatted_date = raw_date

        # 2. Time Logic
        raw_created = batch["created_at"] or ""
        formatted_time = "-"
        if raw_created and " " in raw_created:
            try:
                dt_created = datetime.strptime(raw_created, "%Y-%m-%d %H:%M:%S")
                formatted_time = dt_created.strftime("%I:%M %p") 
            except:
                pass 
        # --------------------------------------------------------

        formatted_batches.append({
            "id": batch["id"],
            "date_added": formatted_date,   # Now this variable exists!
            "time_added": formatted_time,   # Now this variable exists!
            "batch_no": batch["batch_no"],
            "department": batch["department"] or "-",
            "material_code": batch["material_code"],
            "description": batch["description"],
            "received_quantity": round(rec_qty, 3),
            "available_quantity": round(avail_qty, 3),
            "display_quantity": display_received,
            "display_available": format_storage_quantity(avail_qty, batch["uom"]),
            "uom": batch["uom"]
        })

    conn.close()
    return render_template("storage/list.html", batches=formatted_batches, from_date=from_date, to_date=to_date)
def format_storage_quantity(quantity, unit):
    """
    Format storage quantity for display.
    Example: 100.5 litre → "100 Litre 500 ml"
    """
    try:
        qty_val = float(quantity)
    except:
        return f"{quantity} {unit}"

    # 1. Handle KG -> Split into Kg and Grams
    if unit == "kg":
        main = int(qty_val) # Get the 100
        sub = round((qty_val - main) * 1000) # Get the 0.5 * 1000 = 500
        
        if sub > 0:
            return f"{main} Kg {sub} g"
        return f"{main} Kg"

    # 2. Handle Litre -> Split into Litre and ML
    elif unit == "litre":
        main = int(qty_val)
        sub = round((qty_val - main) * 1000)
        
        if sub > 0:
            return f"{main} Litre {sub} ml"
        return f"{main} Litre"

    # 3. Handle Other Units (Pcs, Box, etc.)
    else:
        if qty_val.is_integer():
            return f"{int(qty_val)} {unit}"
        else:
            return f"{round(qty_val, 3)} {unit}"

# -----------------------------
# Add Storage Batch Page - FIXED ENDPOINT NAME
# -----------------------------
@app.route("/storage/add", methods=["GET"])
def add_storage():  # ⭐ CHANGED FROM add_storage_data to add_storage
    """Show the Add New Batch form."""
    if "user" not in session:
        return redirect(url_for("login"))
    return render_template("storage/add_storage.html")

# -----------------------------
# Add Storage Batch (POST) - KEEP THIS SEPARATE
# -----------------------------
# -----------------------------
# Add Storage Batch (POST) - UPDATED FOR SINGLE INPUT
# -----------------------------
@app.route("/storage/add", methods=["POST"])
def add_storage_data():
    if "user" not in session: return redirect(url_for("login"))
    conn = get_db()
    cur = conn.cursor()

    batch_no = request.form.get("batch_no")
    received_date = request.form.get("received_date")
    description = request.form.get("description") 
    uom = request.form.get("uom")
    department = request.form.get("department")
    material_code = "STORAGE-ITEM"

    try:
        # ⭐ CHANGED: Just read the single decimal input directly
        quantity = float(request.form.get("quantity") or 0)
    except: 
        quantity = 0

    if not all([batch_no, description, uom]) or quantity <= 0:
        return "<script>alert('Invalid input');window.history.back();</script>"

    try:
        rounded_qty = round(quantity, 3)
        
        cur.execute("""
            INSERT INTO batches (batch_no, material_code, description, received_quantity, available_quantity, uom, received_date, department, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (batch_no, material_code, description, rounded_qty, rounded_qty, uom, received_date, department, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        
        message = f"New batch {batch_no} created for {description} and storage stock updated."
        
        conn.commit()
        return f"<script>alert('{message}');window.location.href='/storage';</script>"

    except Exception as e:
        conn.rollback()
        print("Storage Error:", e)
        return "<script>alert('Error saving batch. Check console for details.');window.history.back();</script>"
    finally:
        conn.close()   
# -----------------------------
# Edit Storage Batch Page - FIXED ENDPOINT NAME
# -----------------------------
@app.route("/storage/edit/<int:batch_id>", methods=["GET"])
def edit_storage(batch_id):  # ⭐ CHANGED FROM edit_storage_page to edit_storage
    """Display form for editing a batch."""
    if "user" not in session:
        return redirect(url_for("login"))

    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM batches WHERE id = ?", (batch_id,))
    batch = cur.fetchone()
    conn.close()

    if not batch:
        return "<script>alert('Batch not found!');window.location.href='/storage';</script>"

    return render_template("storage/edit_storage.html", batch=batch)


# -----------------------------
# Edit Storage Batch (POST) - UPDATED FOR SINGLE INPUT
# -----------------------------
@app.route("/storage/edit/<int:batch_id>", methods=["POST"])
def edit_storage_data(batch_id):
    """Handle the form submission to update an existing batch."""
    if "user" not in session: return redirect(url_for("login"))
    conn = get_db()
    cur = conn.cursor()

    # 1. Get existing batch details
    cur.execute("SELECT * FROM batches WHERE id = ?", (batch_id,))
    batch = cur.fetchone()
    if not batch:
        return "<script>alert('Batch not found!');window.location.href='/storage';</script>"

    # 2. Get Form Data
    received_date = request.form.get("received_date")
    description = request.form.get("description")
    uom = request.form.get("uom")
    department = request.form.get("department")
    
    try:
        # ⭐ CHANGED: Read single input
        new_quantity = float(request.form.get("quantity") or 0)
    except: 
        new_quantity = 0

    if new_quantity <= 0:
        return "<script>alert('Invalid quantity');window.history.back();</script>"

    try:
        new_rounded_qty = round(new_quantity, 3)
        old_received_qty = batch['received_quantity']
        old_available_qty = batch['available_quantity']

        # 3. Calculate Difference
        difference = new_rounded_qty - old_received_qty
        new_available_qty = old_available_qty + difference

        # Validation: Don't allow reducing stock below what has already been used
        if new_available_qty < 0:
             used_qty = old_received_qty - old_available_qty
             return f"<script>alert('Cannot reduce quantity to {new_rounded_qty}. You have already dispatched {used_qty}. Minimum allowed is {used_qty}.');window.history.back();</script>"

        # 4. Update Database (Batch)
        cur.execute("""
            UPDATE batches 
            SET received_date = ?, description = ?, uom = ?, department = ?,
                received_quantity = ?, available_quantity = ?
            WHERE id = ?
        """, (received_date, description, uom, department, new_rounded_qty, new_available_qty, batch_id))
        
        conn.commit()
        return redirect(url_for('storage_list'))

    except Exception as e:
        conn.rollback()
        print("Edit Storage Error:", e)
        return "<script>alert('Error updating batch');window.history.back();</script>"
    finally:
        conn.close()
        
# -----------------------------
# Edit Storage Batch (POST) - KEEP THIS SEPARATE
# -----------------------------
        
# Auto-date refresh removed to prevent unwanted data changes

# -----------------------------
# Inward History (Permanent Record)
# -----------------------------
@app.route("/inward_history")
def inward_history():
    if "user" not in session:
        return redirect(url_for("login"))
    
    conn = get_db()
    cur = conn.cursor()
    
    # Date Filters
    from_date = request.args.get("from_date", "")
    to_date = request.args.get("to_date", "")
    search = request.args.get("search", "").strip()
    
    # ⭐ QUERY: Select EVERYTHING (No check for available_quantity > 0)
    query = "SELECT * FROM batches WHERE 1=1"
    params = []
    
    if from_date:
        query += " AND date(received_date) >= ?"
        params.append(from_date)
    if to_date:
        query += " AND date(received_date) <= ?"
        params.append(to_date)
        
    if search:
        query += " AND (batch_no LIKE ? OR description LIKE ?)"
        params.extend([f"%{search}%", f"%{search}%"])
        
    query += " ORDER BY created_at DESC"
    
    cur.execute(query, tuple(params))
    batches = cur.fetchall()
    
    history_data = []
    
    for batch in batches:
        # Formatting Date & Time
        raw_date = batch["received_date"] or batch["created_at"] or ""
        formatted_date = "-"
        if raw_date:
            try:
                if " " in raw_date: raw_date = raw_date.split(" ")[0]
                dt = datetime.strptime(raw_date, "%Y-%m-%d")
                formatted_date = dt.strftime("%d/%m/%Y")
            except:
                formatted_date = raw_date

        raw_created = batch["created_at"] or ""
        formatted_time = "-"
        if raw_created:
            try:
                dt_created = datetime.strptime(raw_created, "%Y-%m-%d %H:%M:%S")
                formatted_time = dt_created.strftime("%I:%M %p") 
            except:
                pass

        # Format Quantity (Only Received Matters Here)
        rec_qty = batch["received_quantity"] or 0
        display_received = format_storage_quantity(rec_qty, batch["uom"])
        
        history_data.append({
            "date": formatted_date,
            "time": formatted_time,
            "batch_no": batch["batch_no"],
            "description": batch["description"],
            "received_qty": display_received,
            "uom": batch["uom"]
        })
        
    return render_template("storage/inward_history.html", history=history_data, from_date=from_date, to_date=to_date)
# -----------------------------
# Delete Storage Batch
# -----------------------------
@app.route("/storage/delete/<int:batch_id>")
def delete_storage(batch_id):
    """Delete a batch (if not used in dispatch)."""
    if "user" not in session:
        return redirect(url_for("login"))
    
    conn = get_db()
    cur = conn.cursor()
    try:
        # ⭐ FIXED: Check if THIS SPECIFIC BATCH (by ID) is linked to any dispatch_batches
        cur.execute("""
            SELECT COUNT(*) as count 
            FROM dispatch_batches 
            WHERE batch_id = ?
        """, (batch_id,))
        linked = cur.fetchone()["count"]
        
        # Delete the specific batch by ID (not by batch_no)
        cur.execute("DELETE FROM batches WHERE id = ?", (batch_id,))
        conn.commit()
        return redirect(url_for("storage_list"))
    except Exception as e:
        conn.rollback()
        print("Delete Batch Error:", e)
        return "<script>alert('Error deleting batch.');window.history.back();</script>"
    finally:
        conn.close()

# -----------------------------
# Vendors
# -----------------------------
@app.route("/vendors")
def vendor_list():
    if "user" not in session:
        return redirect(url_for("login"))
    search = request.args.get("search", "").strip()
    conn = get_db()
    cur = conn.cursor()
    if search:
        term = f"%{search}%"
        cur.execute("SELECT * FROM vendors WHERE name LIKE ? OR place LIKE ? OR gstin LIKE ?", (term, term, term))
    else:
        cur.execute("SELECT * FROM vendors")
    vendors = cur.fetchall()
    return render_template("vendors/list.html", vendors=vendors)

@app.route("/vendors/add", methods=["GET", "POST"])
def vendor_add():
    if "user" not in session:
        return redirect(url_for("login"))
    if request.method == "POST":
        conn = get_db()
        cur = conn.cursor()
        cur.execute("INSERT INTO vendors(name,contact,place,pincode,gstin,material,info) VALUES(?,?,?,?,?,?,?)",
                    (request.form.get("vendor_name"), request.form.get("contact"), request.form.get("place"),
                     request.form.get("pincode"), request.form.get("gstin"), request.form.get("material"),
                     request.form.get("info")))
        conn.commit()
        return redirect(url_for("vendor_list"))
    return render_template("vendors/add_vendor.html")

@app.route("/vendors/edit/<int:vid>", methods=["GET", "POST"])
def vendor_edit(vid):
    if "user" not in session:
        return redirect(url_for("login"))
    conn = get_db()
    cur = conn.cursor()
    if request.method == "POST":
        cur.execute("UPDATE vendors SET name=?, contact=?, place=?, pincode=?, gstin=?, material=?, info=? WHERE id=?",
                    (request.form.get("vendor_name"), request.form.get("contact"), request.form.get("place"),
                     request.form.get("pincode"), request.form.get("gstin"), request.form.get("material"),
                     request.form.get("info"), vid))
        conn.commit()
        return redirect(url_for("vendor_list"))
    cur.execute("SELECT * FROM vendors WHERE id=?", (vid,))
    vendor = cur.fetchone()
    return render_template("vendors/edit_vendor.html", vendor=vendor)

@app.route("/vendors/delete/<int:vid>")
def vendor_delete(vid):
    if "user" not in session:
        return redirect(url_for("login"))
    conn = get_db()
    cur = conn.cursor()
    cur.execute("DELETE FROM vendors WHERE id=?", (vid,))
    conn.commit()
    return redirect(url_for("vendor_list"))

# -----------------------------
# Invoices (add / edit / view / delete)
# -----------------------------
@app.route("/invoices")
def invoice_list():
    if "user" not in session:
        return redirect(url_for("login"))

    from_date = request.args.get("from_date", "")
    to_date = request.args.get("to_date", "")

    conn = get_db()
    cur = conn.cursor()

    # Base query
    query = "SELECT * FROM invoices WHERE 1=1"
    params = []

    # Date filters - Using a more robust matching strategy
    if from_date:
        query += " AND (date >= ? OR date(date) >= ?)"
        params.extend([from_date, from_date])
    if to_date:
        query += " AND (date <= ? OR date(date) <= ?)"
        params.extend([to_date, to_date])

    query += " ORDER BY id DESC" # Order by ID to ensure newest are always seen

    cur.execute(query, tuple(params))
    invoice_rows = cur.fetchall()

    invoices = []

    from datetime import datetime

    for inv_row in invoice_rows:
        inv = dict(inv_row)

        # ----------------------------
        # ⭐ DATE FORMAT FIX HERE
        # ----------------------------
        raw_date = inv.get("date", "")
        formatted_date = ""

        if raw_date:
            try:
                # Try date + time
                dt = datetime.strptime(raw_date, "%Y-%m-%d %H:%M:%S")
                formatted_date = dt.strftime("%d/%m/%Y %I:%M %p")
            except:
                try:
                    # Try date only
                    dt = datetime.strptime(raw_date, "%Y-%m-%d")
                    formatted_date = dt.strftime("%d/%m/%Y")
                except:
                    formatted_date = raw_date

        inv["date"] = formatted_date

        # Fetch material codes for summary
        cur.execute("SELECT material FROM invoice_items WHERE invoice_id = ?", (inv['id'],))
        items = cur.fetchall()
        codes = [item['material'] for item in items]
        inv['material_codes_summary'] = ", ".join(codes) if codes else '-'
        
        invoices.append(inv)

    # For summary in footer
    grand_total = sum(float(inv.get("grand_total") or 0) for inv in invoices)
    # ⭐ Updated Tax Summary to include IGST if needed, or keep as total tax paid
    total_gst = sum(float(inv.get("total_gst") or 0) for inv in invoices)
    total_igst = sum(float(inv.get("total_igst") or 0) for inv in invoices)
    total_tax_value = total_gst + total_igst

    return render_template(
        "invoices/list.html",
        invoices=invoices,
        grand_total=grand_total,
        total_tax_value=total_tax_value,
        from_date=from_date,
        to_date=to_date
    )

def material_exists_with_different_name(cur, material_code, material_name):
    """Return True if code exists but name is different."""
    cur.execute("SELECT description FROM materials WHERE material_code=?", (material_code,))
    row = cur.fetchone()
    if row:
        return row["description"].strip().lower() != material_name.strip().lower()
    return False
@app.template_filter('format_qty')
def format_qty(value, unit):
    if value is None: return ""
    try:
        val = float(value)
    except ValueError:
        return f"{value} {unit}"

    if unit in ['kg', 'litre', 'kg/g', 'litre/ml']:
        main_unit = "kg" if "kg" in unit.lower() else "L"
        sub_unit = "g" if "kg" in unit.lower() else "ml"

        # ⭐ ROBUST FIX: Round to 3 decimal places FIRST.
        # This turns 100.049999 into 100.050 immediately.
        val = round(val, 3)

        main_qty = int(val) # Gets 100
        
        # Calculate grams: (100.050 - 100) = 0.050
        # 0.050 * 1000 = 50
        remainder = val - main_qty
        sub_qty = int(round(remainder * 1000))

        # Handle any rare edge case where sub_qty hits 1000
        if sub_qty >= 1000: 
            main_qty += 1
            sub_qty = 0

        if sub_qty > 0:
            return f"{main_qty} {main_unit} {sub_qty} {sub_unit}"
        else:
            return f"{main_qty} {main_unit}"

    # Handle standard units
    if val.is_integer():
        return f"{int(val)} {unit}"
    else:
        return f"{val} {unit}"
# 1. Add this helper function at the top of app.py (outside the route)
def round2(x):
    """Rounds to 2 decimal places using standard rounding"""
    return round(x + 1e-10, 2)

@app.route("/api/ocr/scan_invoice", methods=["POST"])
def api_ocr_scan_invoice():
    if "user" not in session:
        return jsonify({"success": False, "error": "Unauthorized"}), 401
    
    if "invoice_file" not in request.files:
        return jsonify({"success": False, "error": "No invoice file uploaded"}), 400
        
    file = request.files["invoice_file"]
    if file.filename == "":
        return jsonify({"success": False, "error": "No selected file"}), 400
        
    try:
        if extract_invoice_data_from_bytes is None:
            return jsonify({"success": False, "error": "OCR engine module is not loaded"}), 500
            
        file_bytes = file.read()
        extracted = extract_invoice_data_from_bytes(file_bytes)
        return jsonify(extracted)
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/invoices/add", methods=["GET", "POST"])
def invoice_add():
    if "user" not in session: return redirect(url_for("login"))
    conn = get_db()
    cur = conn.cursor()

    if request.method == "POST":
        try:
            purchase_id = request.form.get("purchase_id")
            # ⭐ CRITICAL FIX: Normalize the date before saving so it's never "hidden"
            date_str = normalize_date(request.form.get("date"))
            invoice_no = request.form.get("invoice_no")
            vendor = request.form.get("vendor")
            no_of_items = int(request.form.get("no_of_items") or 0)
            
            round_off_value = float(request.form.get("round_off") or 0)
            cgst_percent = float(request.form.get("cgst_percent") or 0)
            sgst_percent = float(request.form.get("sgst_percent") or 0)

            cur.execute("""
                INSERT INTO invoices (purchase_id, date, invoice_no, vendor, no_of_items, 
                total_excl_tax, total_gst, total_igst, cgst_percent, sgst_percent, round_off_value, final_total, grand_total)
                VALUES (?, ?, ?, ?, ?, 0, 0, 0, ?, ?, ?, 0, 0)
            """, (purchase_id, date_str, invoice_no, vendor, no_of_items, cgst_percent, sgst_percent, round_off_value))
            new_invoice_id = cur.lastrowid

            try:
                date_obj = datetime.strptime(date_str, "%Y-%m-%d")
                batch_no = f"BATCH-{date_obj.timetuple().tm_yday:03d}"
            except: batch_no = "BATCH-000"

            calc_subtotal = 0.0
            calc_gst_total = 0.0
            calc_igst_total = 0.0

            for i in range(1, no_of_items + 1):
                material_name = request.form.get(f"material_name_{i}").strip()
                material_code = request.form.get(f"material_code_{i}").strip()
                
                cur.execute("SELECT material_code FROM materials WHERE description = ? COLLATE NOCASE AND material_code != ?", (material_name, material_code))
                if cur.fetchone():
                    conn.rollback()
                    return f"<script>alert('Error: Name {material_name} exists for another code.'); window.history.back();</script>"

                category = request.form.get(f"category_{i}")
                unit = request.form.get(f"unit_{i}")
                hsn_sac = (request.form.get(f"hsn_sac_{i}") or "").strip()
                reorder_level = int(request.form.get(f"reorder_level_{i}") or 0)
                
                # Get Lot No from form, or fallback to auto-generated batch_no
                item_lot_no = request.form.get(f"lot_no_{i}") or batch_no
                
                item_p_date = request.form.get(f"purchase_date_{i}") or date_str
                item_e_date = request.form.get(f"expiry_date_{i}")

                # Simple Quantity (Single Box)
                quantity = float(request.form.get(f"quantity_{i}") or 0)

                unit_price = float(request.form.get(f"unit_price_{i}") or 0)
                discount_percentage = float(request.form.get(f"discount_{i}") or 0)
                gst_percentage = float(request.form.get(f"gst_{i}") or 0)
                igst_percentage = float(request.form.get(f"igst_{i}") or 0)

                # ========= HYBRID LOGIC (Matches Vendor Bill 4120.08) =========
                
                # 1. Gross & Net (Precise - No Rounding)
                gross_amount = quantity * unit_price
                discount_amount = gross_amount * (discount_percentage / 100.0)
                net_amount = gross_amount - discount_amount
                
                # 2. Tax (Rounded PER ROW - Ledger Style)
                # This ensures the sum of taxes matches the vendor's sum of rounded taxes
                item_gst_value = round2(net_amount * (gst_percentage / 100.0))
                item_igst_value = round2(net_amount * (igst_percentage / 100.0))
                
                item_total = net_amount + item_gst_value + item_igst_value

                # 3. Accumulate
                calc_subtotal += net_amount       # Sum precise net
                calc_gst_total += item_gst_value  # Sum rounded tax
                calc_igst_total += item_igst_value # Sum rounded tax

                cur.execute("""
                    INSERT INTO invoice_items (invoice_id, material, quantity, unit, unit_price, 
                    discount_percentage, gst_percentage, igst_percentage, item_subtotal, item_gst_value, item_igst_value, item_total, batch_no, hsn_sac)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (new_invoice_id, material_code, quantity, unit, unit_price, discount_percentage,
                      gst_percentage, igst_percentage, net_amount, item_gst_value, item_igst_value, item_total, item_lot_no, hsn_sac))

                # Update Material Stock (Live Materials) - TARGET BY CODE AND LOT
                cur.execute("SELECT * FROM materials WHERE material_code=? AND lot_no=?", (material_code, item_lot_no))
                if cur.fetchone():
                    cur.execute("""
                        UPDATE materials SET description=?, quantity=quantity+?, opening_stock=opening_stock+?, 
                        category=?, reorder_level=?, unit_price=?, purchase_date=?, expiry_date=?, hsn_sac=? 
                        WHERE material_code=? AND lot_no=?
                    """, (material_name, quantity, quantity, category, reorder_level, unit_price, item_p_date, item_e_date, hsn_sac, material_code, item_lot_no))
                else:
                    cur.execute("""
                        INSERT INTO materials(material_code, description, category, opening_stock, quantity, unit, unit_price, purchase_date, expiry_date, lot_no, reorder_level, hsn_sac)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (material_code, material_name, category, quantity, quantity, unit, unit_price, item_p_date, item_e_date, item_lot_no, reorder_level, hsn_sac))

            # --- UPDATE INVOICE HEADER ---
            # Total = Rounded Subtotal + Rounded Tax Sums
            final_subtotal_display = round2(calc_subtotal)
            final_grand_total = round2(final_subtotal_display + calc_gst_total + calc_igst_total)
            final_bill_amount = final_grand_total + round_off_value
            
            cur.execute("""
                UPDATE invoices SET total_excl_tax=?, total_gst=?, total_igst=?, grand_total=?, final_total=? WHERE id=?
            """, (final_subtotal_display, calc_gst_total, calc_igst_total, final_grand_total, final_bill_amount, new_invoice_id))

            conn.commit()
            return redirect(url_for("invoice_list"))

        except Exception as e:
            conn.rollback()
            print(f"Error: {e}")
            return f"<script>alert('Error: {str(e)}'); window.history.back();</script>"

    cur.execute("SELECT material_code, description FROM materials ORDER BY material_code")
    materials_for_dropdown = cur.fetchall()
    return render_template("invoices/add_invoice.html", materials=materials_for_dropdown)

@app.route("/invoices/edit/<int:iid>", methods=["GET", "POST"])
def invoice_edit(iid):
    if "user" not in session: return redirect(url_for("login"))
    conn = get_db()
    cur = conn.cursor()

    if request.method == "POST":
        try:
            purchase_id = request.form.get("purchase_id")
            date_str = request.form.get("date")
            invoice_no = request.form.get("invoice_no")
            vendor = request.form.get("vendor")
            no_of_items = int(request.form.get("no_of_items") or 0)
            
            round_off_value = float(request.form.get("round_off") or 0)
            cgst_percent = float(request.form.get("cgst_percent") or 0)
            sgst_percent = float(request.form.get("sgst_percent") or 0)

            # 1. REVERT OLD STOCK
            cur.execute("SELECT material, quantity, batch_no FROM invoice_items WHERE invoice_id = ?", (iid,))
            old_items = cur.fetchall()
            for item in old_items:
                cur.execute("""
                    UPDATE materials SET quantity = quantity - ?, opening_stock = opening_stock - ? 
                    WHERE material_code = ? AND lot_no = ?
                """, (item["quantity"], item["quantity"], item["material"], item["batch_no"]))

            cur.execute("DELETE FROM invoice_items WHERE invoice_id = ?", (iid,))

            # 2. UPDATE INVOICE HEADER
            # ⭐ CRITICAL FIX: Normalize date on Edit
            date_str = normalize_date(request.form.get("date"))
            cur.execute("""
                UPDATE invoices SET purchase_id=?, date=?, invoice_no=?, vendor=?, 
                no_of_items=?, cgst_percent=?, sgst_percent=?, round_off_value=? WHERE id=?
            """, (purchase_id, date_str, invoice_no, vendor, no_of_items, cgst_percent, sgst_percent, round_off_value, iid))

            try:
                date_obj = datetime.strptime(date_str, "%Y-%m-%d")
                batch_no = f"BATCH-{date_obj.timetuple().tm_yday:03d}"
            except: batch_no = "BATCH-000"

            # Accumulators
            calc_subtotal = 0.0
            calc_gst_total = 0.0
            calc_igst_total = 0.0

            # 3. ADD NEW ITEMS
            for i in range(1, no_of_items + 1):
                material_name = request.form.get(f"material_name_{i}").strip()
                material_code = request.form.get(f"material_code_{i}").strip()

                cur.execute("SELECT material_code FROM materials WHERE description = ? COLLATE NOCASE AND material_code != ?", (material_name, material_code))
                if cur.fetchone():
                    conn.rollback()
                    return f"<script>alert('Error: Name {material_name} exists for another code.'); window.history.back();</script>"

                category = request.form.get(f"category_{i}")
                unit = request.form.get(f"unit_{i}")
                hsn_sac = (request.form.get(f"hsn_sac_{i}") or "").strip()
                reorder_level = int(request.form.get(f"reorder_level_{i}") or 0)
                
                # Get Lot No from form, or fallback to auto-generated batch_no
                item_lot_no = request.form.get(f"lot_no_{i}") or batch_no
                
                item_p_date = request.form.get(f"purchase_date_{i}") or date_str
                item_e_date = request.form.get(f"expiry_date_{i}")

                # ⭐ SIMPLE QUANTITY FETCH
                quantity = float(request.form.get(f"quantity_{i}") or 0)

                unit_price = float(request.form.get(f"unit_price_{i}") or 0)
                discount_percentage = float(request.form.get(f"discount_{i}") or 0)
                gst_percentage = float(request.form.get(f"gst_{i}") or 0)
                igst_percentage = float(request.form.get(f"igst_{i}") or 0)

                # ⭐ HYBRID LOGIC
                gross_amount = quantity * unit_price
                discount_amount = gross_amount * (discount_percentage / 100.0)
                net_amount = gross_amount - discount_amount
                
                item_gst_value = round2(net_amount * (gst_percentage / 100.0))
                item_igst_value = round2(net_amount * (igst_percentage / 100.0))
                item_total = net_amount + item_gst_value + item_igst_value

                calc_subtotal += net_amount
                calc_gst_total += item_gst_value
                calc_igst_total += item_igst_value

                cur.execute("""
                    INSERT INTO invoice_items (invoice_id, material, quantity, unit, unit_price, 
                    discount_percentage, gst_percentage, igst_percentage, item_subtotal, item_gst_value, item_igst_value, item_total, batch_no, hsn_sac)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (iid, material_code, quantity, unit, unit_price, discount_percentage,
                      gst_percentage, igst_percentage, net_amount, item_gst_value, item_igst_value, item_total, item_lot_no, hsn_sac))

                cur.execute("SELECT * FROM materials WHERE material_code=? AND lot_no=?", (material_code, item_lot_no))
                if cur.fetchone():
                    cur.execute("""
                        UPDATE materials SET description=?, quantity=quantity+?, opening_stock=opening_stock+?, 
                        category=?, reorder_level=?, unit_price=?, purchase_date=?, expiry_date=?, hsn_sac=? 
                        WHERE material_code=? AND lot_no=?
                    """, (material_name, quantity, quantity, category, reorder_level, unit_price, item_p_date, item_e_date, hsn_sac, material_code, item_lot_no))
                else:
                    cur.execute("""
                        INSERT INTO materials(material_code, description, category, opening_stock, quantity, unit, unit_price, purchase_date, expiry_date, lot_no, reorder_level, hsn_sac)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (material_code, material_name, category, quantity, quantity, unit, unit_price, item_p_date, item_e_date, item_lot_no, reorder_level, hsn_sac))

            # Update Header
            final_subtotal_display = round2(calc_subtotal)
            final_grand_total = round2(final_subtotal_display + calc_gst_total + calc_igst_total)
            final_bill_amount = final_grand_total + round_off_value
            
            cur.execute("""
                UPDATE invoices SET total_excl_tax=?, total_gst=?, total_igst=?, grand_total=?, final_total=? WHERE id=?
            """, (final_subtotal_display, calc_gst_total, calc_igst_total, final_grand_total, final_bill_amount, iid))

            conn.commit()
            return redirect(url_for("invoice_list"))

        except Exception as e:
            conn.rollback()
            return f"<script>alert('Error: {str(e)}'); window.history.back();</script>"

    cur.execute("SELECT * FROM invoices WHERE id = ?", (iid,))
    invoice = cur.fetchone()
    if not invoice: return redirect(url_for("invoice_list"))

    cur.execute("""
        SELECT ii.*, m.category, COALESCE(m.description, ii.material) AS description, m.reorder_level, m.purchase_date, m.expiry_date,
               COALESCE(ii.hsn_sac, m.hsn_sac, '') AS hsn_sac
        FROM invoice_items AS ii
        LEFT JOIN materials AS m ON ii.material = m.material_code
        WHERE ii.invoice_id = ?
    """, (iid,))
    items = [dict(row) for row in cur.fetchall()]

    return render_template("invoices/edit_invoice.html", invoice=invoice, items=items)
# -----------------------------
# API: Autocomplete Material Search
# -----------------------------
@app.route('/api/materials/autocomplete')
def autocomplete_materials():
    if "user" not in session:
        return jsonify([]) # Return empty list if not logged in

    term = request.args.get('term', '')
    if not term:
        return jsonify([])

    conn = get_db()
    cur = conn.cursor()
    
    # Search for code OR description
    search_term = f"%{term}%"
    cur.execute("""
        SELECT material_code, description, category, unit, reorder_level 
        FROM materials 
        WHERE material_code LIKE ? OR description LIKE ?
        LIMIT 10
    """, (search_term, search_term))
    
    results = []
    for row in cur.fetchall():
        results.append({
                    'label': f"{row['material_code']} - {row['description']}",  # What user sees in the dropdown
            'value': row['material_code'],       # What fills the input box
            'description': row['description'],   # Data to auto-fill
            'category': row['category'],
            'unit': row['unit'],
            'reorder_level': row['reorder_level']
        })
    
    conn.close()
    return jsonify(results)

# -----------------------------
# API: Lookup Material Code by Description (for OCR & live auto-fill)
# -----------------------------
@app.route('/api/materials/lookup_by_description')
def lookup_material_by_description():
    """Given a product name (from OCR or manual input), find matching material code and category from the factory DB."""
    if "user" not in session:
        return jsonify({"found": False})
    
    name = request.args.get('name', '').strip()
    if not name:
        return jsonify({"found": False})
    
    conn = get_db()
    cur = conn.cursor()
    
    # Check if hsn_sac column exists in materials
    cur.execute("PRAGMA table_info(materials)")
    mat_cols = [c[1] for c in cur.fetchall()]
    hsn_col_sql = "hsn_sac" if "hsn_sac" in mat_cols else "'' AS hsn_sac"
    
    # 1. Exact match (case-insensitive)
    cur.execute(f"""
        SELECT material_code, description, category, unit, reorder_level, {hsn_col_sql}
        FROM materials
        WHERE description = ? COLLATE NOCASE
        GROUP BY material_code
        ORDER BY material_code
        LIMIT 5
    """, (name,))
    rows = cur.fetchall()
    
    # 2. Prefix match
    if not rows:
        cur.execute(f"""
            SELECT material_code, description, category, unit, reorder_level, {hsn_col_sql}
            FROM materials
            WHERE description LIKE ? COLLATE NOCASE OR ? LIKE (description || '%') COLLATE NOCASE
            GROUP BY material_code
            ORDER BY material_code
            LIMIT 5
        """, (f"{name}%", name))
        rows = cur.fetchall()

    # 3. Substring match
    if not rows and len(name) >= 3:
        cur.execute(f"""
            SELECT material_code, description, category, unit, reorder_level, {hsn_col_sql}
            FROM materials
            WHERE description LIKE ? COLLATE NOCASE
            GROUP BY material_code
            ORDER BY material_code
            LIMIT 5
        """, (f"%{name}%",))
        rows = cur.fetchall()

    # 4. Multi-word search
    if not rows:
        import re as py_re
        words = [w for w in py_re.split(r"[\s\-_]+", name) if len(w) >= 3 and not w.isdigit()]
        if words:
            best_word = max(words, key=len)
            cur.execute(f"""
                SELECT material_code, description, category, unit, reorder_level, {hsn_col_sql}
                FROM materials
                WHERE description LIKE ? COLLATE NOCASE
                GROUP BY material_code
                ORDER BY material_code
                LIMIT 5
            """, (f"%{best_word}%",))
            rows = cur.fetchall()
    
    conn.close()
    
    if not rows:
        return jsonify({"found": False, "name": name})
    
    matches = [{
        "code": r["material_code"],
        "description": r["description"],
        "category": r["category"],
        "unit": r["unit"],
        "reorder_level": r["reorder_level"],
        "hsn_sac": r["hsn_sac"] if "hsn_sac" in r.keys() and r["hsn_sac"] else ""
    } for r in rows]
    
    best = matches[0]
    
    return jsonify({
        "found": True,
        "code": best["code"],
        "description": best["description"],
        "category": best["category"],
        "unit": best["unit"],
        "reorder_level": best["reorder_level"],
        "hsn_sac": best["hsn_sac"],
        "all_matches": matches
    })

# -----------------------------
# API: Generate Next Material Code
# -----------------------------
@app.route('/api/materials/generate_next_code')
def generate_next_material_code():
    """Generates the next unique sequential material code for new items."""
    if "user" not in session:
        return jsonify({"success": False, "error": "Unauthorized"}), 401
    
    category = request.args.get('category', '').strip().lower()
    
    conn = get_db()
    cur = conn.cursor()
    
    min_range = 900
    max_range = 999
    
    if "tea bag" in category:
        min_range, max_range = 800, 899
    elif "coffee" in category:
        min_range, max_range = 700, 799
    elif "oil" in category:
        min_range, max_range = 600, 699
    elif "bakery" in category or "vakery" in category:
        min_range, max_range = 500, 599
    elif "choc" in category:
        min_range, max_range = 400, 499
    elif "dry fruit" in category or "nut" in category:
        min_range, max_range = 300, 399
    elif "spice" in category:
        min_range, max_range = 200, 299
    elif "tea" in category:
        min_range, max_range = 100, 199
    else:
        min_range, max_range = 900, 999

    cur.execute("""
        SELECT material_code FROM materials 
        WHERE CAST(material_code AS INTEGER) >= ? AND CAST(material_code AS INTEGER) <= ?
        ORDER BY CAST(material_code AS INTEGER) DESC LIMIT 1
    """, (min_range, max_range))
    row = cur.fetchone()
    
    if row and row['material_code'] and str(row['material_code']).isdigit():
        next_code = str(int(row['material_code']) + 1)
    else:
        next_code = str(min_range)
        
    # Ensure next_code is unique
    while True:
        cur.execute("SELECT 1 FROM materials WHERE material_code = ?", (next_code,))
        if not cur.fetchone():
            break
        next_code = str(int(next_code) + 1)
        
    conn.close()
    return jsonify({
        "success": True,
        "code": next_code,
        "category": category if category else "packing"
    })

# -----------------------------
# API: Get Lots for a Material
# -----------------------------
@app.route('/api/materials/get_lots')
def get_material_lots():
    if "user" not in session: return jsonify([])
    code = request.args.get('code', '')
    if not code: return jsonify([])
    
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT id, lot_no, quantity, unit, expiry_date FROM materials WHERE material_code = ? AND quantity > 0", (code,))
    rows = cur.fetchall()
    
    lots = []
    for r in rows:
        exp = r['expiry_date']
        if exp:
            try: exp = datetime.strptime(exp, "%Y-%m-%d").strftime("%d/%m/%Y")
            except: pass
        lots.append({
            "id": r['id'],
            "lot_no": r['lot_no'] or "No Lot",
            "quantity": r['quantity'],
            "unit": r['unit'],
            "expiry": exp or "-"
        })
    return jsonify(lots)

# [In MMS.py, Find the 'invoice_view' function and REPLACE it with this]
# Reason: We added 'ii.id' to the SELECT statement so we can identify which row to delete.

@app.route("/invoices/view/<int:iid>")  
def invoice_view(iid):
    if "user" not in session: return redirect(url_for("login"))
    
    conn = get_db()
    cur = conn.cursor()
    
    # Fetch Invoice Header
    cur.execute("SELECT * FROM invoices WHERE id = ?", (iid,))
    row = cur.fetchone()
    
    if not row: return redirect(url_for("invoice_list"))
    
    invoice = dict(row)
    
    # Format Date
    if invoice.get("date"):
        try:
            dt = datetime.strptime(invoice["date"], "%Y-%m-%d")
            invoice["date"] = dt.strftime("%d/%m/%Y")
        except ValueError: pass 
    
    # ⭐ UPDATE: Added 'ii.id' to this query so we can delete specific rows
    cur.execute("""
        SELECT 
            ii.id,
            ii.material AS code, 
            COALESCE(m.description, ii.material) AS name, 
            COALESCE(ii.hsn_sac, m.hsn_sac, '') AS hsn,
            ii.quantity, 
            ii.unit, 
            ii.unit_price, 
            ii.discount_percentage,
            ii.gst_percentage AS gst,
            ii.igst_percentage AS igst,
            ii.item_subtotal,  
            ii.item_total,
            ii.batch_no
        FROM invoice_items AS ii 
        LEFT JOIN materials AS m ON ii.material = m.material_code 
        WHERE ii.invoice_id = ?
    """, (iid,))
    
    materials = cur.fetchall()
    
    return render_template("invoices/view_invoice.html", invoice=invoice, materials=materials)

# [In MMS.py, ADD this completely NEW route at the end of the Invoice section]

@app.route("/invoices/delete_item/<int:item_id>")
def delete_invoice_item(item_id):
    if "user" not in session: return redirect(url_for("login"))
    
    conn = get_db()
    cur = conn.cursor()
    
    try:
        # 1. Get item details before deleting (to know stock and invoice_id)
        cur.execute("SELECT invoice_id, material, quantity, batch_no FROM invoice_items WHERE id = ?", (item_id,))
        item = cur.fetchone()
        
        if not item:
            return "<script>alert('Item not found');window.history.back();</script>"
            
        invoice_id = item['invoice_id']
        material_code = item['material']
        qty_to_remove = item['quantity']
        b_no = item['batch_no']
        
        # 2. Reverse Stock (Subtract quantity because we are removing a purchase)
        cur.execute("""
            UPDATE materials 
            SET quantity = quantity - ?, 
                opening_stock = opening_stock - ? 
            WHERE material_code = ? AND lot_no = ?
        """, (qty_to_remove, qty_to_remove, material_code, b_no))
        
        # 3. Delete the Item Row
        cur.execute("DELETE FROM invoice_items WHERE id = ?", (item_id,))
        
        # 4. RECALCULATE INVOICE TOTALS
        # We fetch all remaining items and sum them up again
        cur.execute("""
            SELECT 
                SUM(item_subtotal) as new_subtotal,
                SUM(item_gst_value) as new_gst,
                SUM(item_igst_value) as new_igst
            FROM invoice_items 
            WHERE invoice_id = ?
        """, (invoice_id,))
        
        totals = cur.fetchone()
        new_subtotal = totals['new_subtotal'] or 0
        new_gst = totals['new_gst'] or 0
        new_igst = totals['new_igst'] or 0
        
        # Get existing Round Off value to preserve it
        cur.execute("SELECT round_off_value FROM invoices WHERE id = ?", (invoice_id,))
        round_off = cur.fetchone()['round_off_value'] or 0
        
        # Calculate new Grand Total
        new_grand_total = new_subtotal + new_gst + new_igst
        new_final_total = new_grand_total + round_off
        
        new_cgst = new_gst / 2
        new_sgst = new_gst / 2
        
        # 5. Update Invoice Header (⭐ SYNC: Added no_of_items decrement)
        cur.execute("""
            UPDATE invoices 
            SET total_excl_tax = ?, 
                total_gst = ?, 
                total_igst = ?, 
                cgst_percent = ?, 
                sgst_percent = ?, 
                grand_total = ?, 
                final_total = ?,
                no_of_items = no_of_items - 1
            WHERE id = ?
        """, (new_subtotal, new_gst, new_igst, new_cgst, new_sgst, new_grand_total, new_final_total, invoice_id))
        
        conn.commit()
        return redirect(url_for('invoice_view', iid=invoice_id))
        
    except Exception as e:
        conn.rollback()
        print(f"Error deleting item: {e}")
        return f"<script>alert('Error: {e}');window.history.back();</script>"

# [Add this to the bottom of MMS.py]

@app.route("/invoices/add_item_to_existing", methods=["POST"])
def add_item_to_existing():
    if "user" not in session: return redirect(url_for("login"))
    conn = get_db()
    cur = conn.cursor()

    try:
        invoice_id = request.form.get("invoice_id")
        
        # 1. Get Form Data
        material_code = request.form.get("material_code")
        material_name = request.form.get("material_name")
        category = request.form.get("category")
        unit = request.form.get("unit")
        
        # Get/Calculate Numeric Values
        quantity = float(request.form.get("quantity") or 0)
        unit_price = float(request.form.get("unit_price") or 0)
        discount = float(request.form.get("discount") or 0)
        gst = float(request.form.get("gst") or 0)
        igst = float(request.form.get("igst") or 0)
        
        # Get Lot No from form
        item_lot_no = request.form.get("lot_no")
        
        # Generate Default Batch No if lot_no is empty
        cur.execute("SELECT date FROM invoices WHERE id = ?", (invoice_id,))
        inv_date_row = cur.fetchone()
        
        default_batch = "BATCH-000"
        if inv_date_row and inv_date_row['date']:
             try:
                date_obj = datetime.strptime(inv_date_row['date'], "%Y-%m-%d")
                default_batch = f"BATCH-{date_obj.timetuple().tm_yday:03d}"
             except:
                try:
                     for fmt in ["%d-%m-%Y", "%d/%m/%Y"]:
                         try:
                             date_obj = datetime.strptime(inv_date_row['date'], fmt)
                             default_batch = f"BATCH-{date_obj.timetuple().tm_yday:03d}"
                             break
                         except: continue
                except: pass
        
        if not item_lot_no:
            item_lot_no = default_batch

        # 2. Calculations (Hybrid Logic - Using round2 for consistency)
        gross_amount = quantity * unit_price
        discount_amount = gross_amount * (discount / 100.0)
        net_amount = gross_amount - discount_amount
        
        item_gst_value = round2(net_amount * (gst / 100.0))
        item_igst_value = round2(net_amount * (igst / 100.0))
        item_total = net_amount + item_gst_value + item_igst_value

        # 3. Insert the New Item
        cur.execute("""
            INSERT INTO invoice_items (invoice_id, material, quantity, unit, unit_price, 
            discount_percentage, gst_percentage, igst_percentage, item_subtotal, item_gst_value, item_igst_value, item_total, batch_no)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (invoice_id, material_code, quantity, unit, unit_price, discount,
              gst, igst, net_amount, item_gst_value, item_igst_value, item_total, item_lot_no))

        # 4. Update Stock (Add to stock)
        cur.execute("SELECT * FROM materials WHERE material_code=? AND lot_no=?", (material_code, item_lot_no))
        if cur.fetchone():
            cur.execute("""
                UPDATE materials SET description=?, quantity=quantity+?, opening_stock=opening_stock+?, 
                category=?, unit_price=? WHERE material_code=? AND lot_no=?
            """, (material_name, quantity, quantity, category, unit_price, material_code, item_lot_no))
        else:
             # Handle case where lot doesn't exist
             cur.execute("""
                INSERT INTO materials(material_code, description, category, opening_stock, quantity, unit, unit_price, lot_no, purchase_date)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (material_code, material_name, category, quantity, quantity, unit, unit_price, item_lot_no, inv_date_row['date'] if inv_date_row else None))

        # 5. RECALCULATE INVOICE HEADER (The most important part!)
        cur.execute("""
            SELECT 
                SUM(item_subtotal) as new_subtotal,
                SUM(item_gst_value) as new_gst,
                SUM(item_igst_value) as new_igst
            FROM invoice_items 
            WHERE invoice_id = ?
        """, (invoice_id,))
        
        totals = cur.fetchone()
        new_subtotal = totals['new_subtotal'] or 0
        new_gst = totals['new_gst'] or 0
        new_igst = totals['new_igst'] or 0
        
        cur.execute("SELECT round_off_value FROM invoices WHERE id = ?", (invoice_id,))
        round_off = cur.fetchone()['round_off_value'] or 0
        
        new_grand_total = new_subtotal + new_gst + new_igst
        new_final_total = new_grand_total + round_off
        
        cur.execute("""
            UPDATE invoices 
            SET total_excl_tax = ?, total_gst = ?, total_igst = ?, 
                cgst_percent = ?, sgst_percent = ?, 
                grand_total = ?, final_total = ?,
                no_of_items = no_of_items + 1
            WHERE id = ?
        """, (new_subtotal, new_gst, new_igst, (new_gst/2), (new_gst/2), new_grand_total, new_final_total, invoice_id))

        conn.commit()
        return redirect(url_for('invoice_view', iid=invoice_id))

    except Exception as e:
        conn.rollback()
        print(f"Error adding item: {e}")
        return f"<script>alert('Error: {e}');window.history.back();</script>"
    
@app.route("/invoices/delete/<int:iid>")
def invoice_delete(iid):
    if "user" not in session:
        return redirect(url_for("login"))
    
    conn = get_db()
    cur = conn.cursor()
    try:
        # 1. Get all items associated with this invoice
        cur.execute("SELECT material, quantity, batch_no FROM invoice_items WHERE invoice_id = ?", (iid,))
        items_to_delete = cur.fetchall()
        
        for item in items_to_delete:
            mat_code = item["material"]
            qty_to_remove = item["quantity"]
            b_no = item["batch_no"]

            # 2. Reduce BOTH quantity AND opening_stock (Reverse the addition)
            cur.execute("""
                UPDATE materials 
                SET quantity = quantity - ?, 
                    opening_stock = opening_stock - ? 
                WHERE material_code = ? AND lot_no = ?
            """, (qty_to_remove, qty_to_remove, mat_code, b_no))
            
            # --- ⭐ NEW LOGIC: DELETE ROW IF QUANTITY IS 0 (DISABLED) ⭐ ---
            # Check the new quantity of the material
            # cur.execute("SELECT quantity FROM materials WHERE material_code = ?", (mat_code,))
            # row = cur.fetchone()
            
            # if row:
            #     current_qty = row['quantity']
            #     # If quantity is 0 (or negative due to error), delete the material row entirely
            #     if current_qty <= 0.001: 
            #         cur.execute("DELETE FROM materials WHERE material_code = ?", (mat_code,))
            #         print(f"Material {mat_code} deleted because stock reached 0.")
            # -----------------------------------------------------
            
        # 2b. Also remove synced batches for this invoice
        cur.execute("DELETE FROM batches WHERE invoice_id = ?", (iid,))
            
        # 3. Finally, delete the invoice itself
        cur.execute("DELETE FROM invoices WHERE id = ?", (iid,))
        conn.commit()
        
    except Exception as e:
        conn.rollback()
        print(f"Error during delete: {e}")
        return "<script>alert('Error deleting invoice');window.history.back();</script>"
        
    return redirect(url_for("invoice_list"))


# -----------------------------
# NEW API ROUTES FOR DISPATCH
# -----------------------------
@app.route('/api/storage/search_description')
def api_storage_search_desc():
    """Search for unique product descriptions in batches."""
    if "user" not in session: return jsonify([])
    term = request.args.get('term', '').strip()
    if not term: return jsonify([])
    conn = get_db()
    cur = conn.cursor()
    # Find descriptions that match and have stock
    cur.execute("SELECT DISTINCT description FROM batches WHERE description LIKE ? COLLATE NOCASE AND available_quantity > 0 LIMIT 10", (f"%{term}%",))
    results = [row['description'] for row in cur.fetchall()]
    return jsonify(results)

@app.route('/api/storage/get_oldest_batch')
def api_storage_oldest_batch():
    """Find oldest batch number for a specific description."""
    if "user" not in session: return jsonify({"error": "Unauthorized"}), 401
    desc = request.args.get('description', '').strip()
    conn = get_db()
    cur = conn.cursor()
    # Sort by Batch No (Day of Year) ASC to get the oldest one first
    cur.execute("""
        SELECT batch_no, available_quantity, uom 
        FROM batches 
        WHERE description = ? COLLATE NOCASE AND available_quantity > 0 
        ORDER BY CAST(batch_no AS INTEGER) ASC, id ASC 
        LIMIT 1
    """, (desc,))
    row = cur.fetchone()
    if row: return jsonify({"batch_no": row['batch_no'], "available_quantity": row['available_quantity'], "uom": row['uom']})
    else: return jsonify({"error": "No stock"}), 404
    
# -----------------------------
# Dispatch
# --------------------------



# --- DELETE THIS BLOCK ---
def restore_dispatch_stock(dispatch_id):
    """
    Revert batches used in a dispatch.
    """
    conn = get_db()
    cur = conn.cursor()
    
    # 1. Find out what items were in this dispatch - UPDATED to use batch_id
    cur.execute("SELECT batch_id, quantity FROM dispatch_batches WHERE dispatch_id = ?", (dispatch_id,))
    rows = cur.fetchall()
    
    for r in rows:
        # ⭐ FIXED: Now using batch_id to target the specific batch
        cur.execute("""
            UPDATE batches 
            SET available_quantity = available_quantity + ? 
            WHERE id = ?
        """, (r['quantity'], r['batch_id']))
        
    # 2. Remove the link
    cur.execute("DELETE FROM dispatch_batches WHERE dispatch_id = ?", (dispatch_id,))
    conn.commit()
# --- DELETE END ---
def format_quantity_display(quantity, unit):
    """
    Convert calculated quantity back to main+sub display format
    Example: 40.05 kg → "40 kg 50 g"
    """
    if unit in ["kg", "litre"]:
        main_part = int(quantity)
        sub_part = round((quantity - main_part) * 1000)
        
        if sub_part > 0:
            return f"{main_part} {unit} {sub_part} g"
        else:
            return f"{main_part} {unit}"
    else:
        # For pieces, meters, etc.
        return f"{quantity} {unit}"

@app.route("/dispatch")
def dispatch_list():
    if "user" not in session:
        return redirect(url_for("login"))
    
    conn = get_db()
    cur = conn.cursor()
    
    from_date = request.args.get("from_date", "")
    to_date = request.args.get("to_date", "")
    search = request.args.get("search", "")
    params = []

    # ⭐ UPDATED QUERY: Fetch both the Dispatch Product Name and Material Description
    query = """
        SELECT d.*, 
               m.description as material_desc,
               db.batch_no
        FROM dispatches d
        LEFT JOIN materials m ON d.material_code = m.material_code
        LEFT JOIN dispatch_batches db ON d.id = db.dispatch_id
        WHERE 1=1
    """
    
    if from_date:
        query += " AND date(d.date) >= ?"
        params.append(from_date)
    if to_date:
        query += " AND date(d.date) <= ?"
        params.append(to_date)
    
    if search:
        query += " AND (d.product LIKE ? OR d.material_code LIKE ? OR m.description LIKE ?)"
        params.extend([f"%{search}%", f"%{search}%", f"%{search}%"])
        
    query += " ORDER BY d.id DESC"
    
    cur.execute(query, tuple(params))
    dispatches = cur.fetchall()
    
    formatted_dispatches = []
    for dispatch in dispatches:
        dispatch_dict = dict(dispatch)
        
        # ⭐ FIX LOGIC: Prioritize the name saved in Dispatch ('product')
        # If 'product' is empty, fallback to the Material Description
        if dispatch_dict.get('product'):
            display_name = dispatch_dict['product']
        else:
            display_name = dispatch_dict.get('material_desc') or "Unknown Item"
            
        dispatch_dict['display_name'] = display_name

        # Format Date
        raw_date = dispatch_dict.get("date")
        if raw_date:
            try:
                dt = datetime.strptime(raw_date, "%Y-%m-%d")
                dispatch_dict["date"] = dt.strftime("%d/%m/%Y")
            except ValueError:
                pass 

        # Format Quantity
        display_quantity = format_quantity_display(dispatch_dict['quantity'], dispatch_dict['units'])
        dispatch_dict['display_quantity'] = display_quantity
        
        formatted_dispatches.append(dispatch_dict)
    
    total_quantity = sum(d['quantity'] for d in dispatches if d['quantity'] is not None)
    
    return render_template("dispatch/list.html", 
                           dispatches=formatted_dispatches, 
                           total_quantity=round(total_quantity, 3),
                           from_date=from_date,
                           to_date=to_date)
    
@app.route("/dispatch/add", methods=["GET", "POST"])
def dispatch_add():
    if "user" not in session: return redirect(url_for("login"))
    conn = get_db()
    cur = conn.cursor()

    if request.method == "POST":
        try:
            date_str = request.form.get("date")
            product_name = request.form.get("material_name") 
            batch_no = request.form.get("batch_no")
            unit = request.form.get("units")
            location = request.form.get("location")
            department = request.form.get("department")
            material_code = "STORAGE-ITEM"

            # ⭐ NEW: Read single quantity input
            try:
                quantity = float(request.form.get("quantity") or 0)
            except:
                quantity = 0

            if quantity <= 0: 
                return "<script>alert('Invalid quantity');window.history.back();</script>"

            # 1. Get ALL batches for this product (oldest first)
            cur.execute("""
                SELECT id, batch_no, available_quantity 
                FROM batches 
                WHERE description = ? COLLATE NOCASE AND available_quantity > 0 
                ORDER BY id ASC
            """, (product_name,))
            batch_data = cur.fetchone()
            
            if not batch_data:
                return "<script>alert('Error: No available batches found!');window.history.back();</script>"
            
            # 2. Check limit
            if quantity > batch_data['available_quantity']:
                available_qty = batch_data['available_quantity']
                batch_num = batch_data['batch_no']
                return f"<script>alert('Error: Only {available_qty} {unit} available in batch {batch_num}.');window.history.back();</script>"

            # 3. Insert Dispatch
            cur.execute("INSERT INTO dispatches (date, material_code, product, quantity, units, location, department) VALUES (?, ?, ?, ?, ?, ?, ?)",
                        (date_str, material_code, product_name, quantity, unit, location, department))
            dispatch_id = cur.lastrowid

            # 4. Deduct from the specific batch
            cur.execute("UPDATE batches SET available_quantity = available_quantity - ? WHERE id = ?", 
                        (quantity, batch_data['id']))
            
            # Check if empty and remove
            cur.execute("SELECT available_quantity FROM batches WHERE id = ?", (batch_data['id'],))
            updated_batch = cur.fetchone()
            if updated_batch and updated_batch['available_quantity'] <= 0.001:
                cur.execute("UPDATE batches SET available_quantity = 0 WHERE id = ?", (batch_data['id'],))
            
            # 5. Link
            cur.execute("INSERT INTO dispatch_batches (dispatch_id, batch_no, batch_id, quantity) VALUES (?, ?, ?, ?)", 
                        (dispatch_id, batch_data['batch_no'], batch_data['id'], quantity))
            
            conn.commit()
            return redirect(url_for("dispatch_list"))
            
        except Exception as e:
            conn.rollback()
            print("Dispatch Error:", e)
            return f"<script>alert('Error processing dispatch: {str(e)}');window.history.back();</script>"

    return render_template("dispatch/add_dispatch.html")


@app.route("/dispatch/edit/<int:did>", methods=["GET", "POST"])
def dispatch_edit(did):
    if "user" not in session: return redirect(url_for("login"))
    conn = get_db()
    cur = conn.cursor()
    
    cur.execute("""
        SELECT d.*, db.batch_no 
        FROM dispatches d
        LEFT JOIN dispatch_batches db ON d.id = db.dispatch_id
        WHERE d.id = ?
    """, (did,))
    row = cur.fetchone()
    if not row: return redirect(url_for("dispatch_list"))
    dispatch = dict(row)

    if request.method == "POST":
        try:
            restore_dispatch_stock(did)
            new_date = request.form.get("date")
            new_name = request.form.get("material_name")
            new_batch = request.form.get("batch_no")
            new_unit = request.form.get("units")
            new_loc = request.form.get("location")
            new_dept = request.form.get("department")
            material_code = "STORAGE-ITEM"

            # ⭐ NEW: Read single quantity input
            try:
                new_qty = float(request.form.get("quantity") or 0)
            except:
                new_qty = 0

            cur.execute("SELECT id, available_quantity FROM batches WHERE batch_no = ? AND description = ?", (new_batch, new_name))
            b_data = cur.fetchone()
            if not b_data: return "<script>alert('Batch not found');window.history.back();</script>"
            
            if new_qty > b_data['available_quantity']:
                return "<script>alert('Insufficient stock in selected batch');window.history.back();</script>"

            cur.execute("UPDATE dispatches SET date=?, product=?, quantity=?, units=?, location=?, department=? WHERE id=?",
                        (new_date, new_name, new_qty, new_unit, new_loc, new_dept, did))
            
            cur.execute("UPDATE batches SET available_quantity = available_quantity - ? WHERE id = ?", (new_qty, b_data['id']))
            cur.execute("INSERT INTO dispatch_batches (dispatch_id, batch_no, quantity) VALUES (?, ?, ?)", (did, new_batch, new_qty))
            
            conn.commit()
            return redirect(url_for("dispatch_list"))
        except Exception as e:
            conn.rollback()
            return "<script>alert('Error editing');window.history.back();</script>"
    
    return render_template("dispatch/edit_dispatch.html", dispatch=dispatch)


@app.route("/dispatch/delete/<int:did>")
def dispatch_delete(did):
    if "user" not in session:
        return redirect(url_for("login"))
    conn = get_db()
    cur = conn.cursor()
    try:
        restore_dispatch_stock(did)
        cur.execute("DELETE FROM dispatches WHERE id = ?", (did,))
        conn.commit()
    except Exception as e:
        conn.rollback()
        print("Error deleting dispatch:", e)
    return redirect(url_for("dispatch_list"))


# -----------------------------
# Transfers
# -----------------------------
@app.route("/transfers")
def transfer_list():
    if "user" not in session:
        return redirect(url_for("login"))

    conn = get_db()
    cur = conn.cursor()

    from_date = request.args.get("from_date", "")
    to_date = request.args.get("to_date", "")
    dept_filter = request.args.get("dept", "").strip()

    # Read transfer records
    query = "SELECT * FROM transfers WHERE 1=1"
    params = []

    if from_date:
        query += " AND date(date) >= ?"
        params.append(from_date)
    if to_date:
        query += " AND date(date) <= ?"
        params.append(to_date)
    if dept_filter:
        query += " AND department = ?"
        params.append(dept_filter)

    query += " ORDER BY id DESC"
    cur.execute(query, tuple(params))
    transfers_raw = cur.fetchall()

    transfers = []
    from datetime import datetime

    for row in transfers_raw:
        item = dict(row)

        # ----------------------------
        # ⭐ DATE FORMAT FIX (dd-mm-yyyy)
        # ----------------------------
        raw_date = item.get("date", "")
        formatted_date = ""

        if raw_date:
            try:
                # date + time
                dt = datetime.strptime(raw_date, "%Y-%m-%d %H:%M:%S")
                formatted_date = dt.strftime("%d/%m/%Y %I:%M %p")
            except:
                try:
                    # only date
                    dt = datetime.strptime(raw_date, "%Y-%m-%d")
                    formatted_date = dt.strftime("%d/%m/%Y")
                except:
                    formatted_date = raw_date

        item["date"] = formatted_date

        # ----------------------------
        # ⭐ REMOVE LOT NUMBER FROM BACKEND
        # ----------------------------
        if "lot_no" in item:
            del item["lot_no"]

        transfers.append(item)

    # Fetch all unique departments for the filter dropdown
    cur.execute("SELECT DISTINCT department FROM transfers WHERE department IS NOT NULL AND department != '' ORDER BY department ASC")
    all_departments = [row['department'] for row in cur.fetchall()]

    # Load materials for dropdown (Shows UNIQUE codes only)
    cur.execute("SELECT DISTINCT material_code, description FROM materials ORDER BY material_code")
    materials_for_dropdown = cur.fetchall()

    # Today's date (for default)
    today = datetime.now().strftime("%Y-%m-%d")

    return render_template(
        "transfers/form.html",
        transfers=transfers,
        materials=materials_for_dropdown,
        date=today,
        from_date=from_date,
        to_date=to_date,
        dept_filter=dept_filter,
        all_departments=all_departments,
        standard_depts=DEPARTMENTS
    )
# Duplicate normalize_date removed

@app.route("/transfers/add", methods=["GET", "POST"])
def transfer_add():
    if "user" not in session:
        return redirect(url_for("login"))

    conn = get_db()
    cur = conn.cursor()

    if request.method == "POST":
        material_id = request.form.get("material_id") # Unique ID for the specific Lot
        code = request.form.get("code")
        department = request.form.get("department")
        person = request.form.get("person")
        transfer_date = normalize_date(request.form.get("date"))

        outward = float(request.form.get("outward") or 0)
        return_units = float(request.form.get("return_units") or 0)
        units = request.form.get("units")

        # 1. Fetch SPECIFIC Lot Data
        cur.execute("SELECT id, quantity, description, lot_no, unit FROM materials WHERE id = ?", (material_id,))
        material_data = cur.fetchone()
        
        if not material_data:
            return "Error: Material Lot not found", 400
            
        current_stock = material_data['quantity'] or 0
        description = material_data['description']
        lot_no = material_data['lot_no']
        
        if not units: 
            units = material_data['unit']

        # 2. VALIDATION
        if outward > current_stock:
            return f"""
            <script>
                alert('Insufficient Stock in this Lot!\\nAvailable: {current_stock}\\nTransfer Out: {outward}');
                window.history.back();
            </script>
            """

        # 3. Calculate Net Change
        net_change = return_units - outward
        remaining_balance = current_stock + net_change

        # 4. Update Stock (Specific Lot Only)
        cur.execute("UPDATE materials SET quantity = ROUND(quantity + ?, 3) WHERE id = ?", 
                    (net_change, material_id))

        # 5. Save Transfer Record
        cur.execute("""
            INSERT INTO transfers 
            (date, code, description, lot_no, outward, units, department, person, return_units, availability)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (transfer_date, code, description, lot_no, outward, units, department, person, 
              return_units, remaining_balance))  # <--- Changed current_stock to remaining_balance

        conn.commit()
        return redirect(url_for("transfer_list"))

    # GET Request
    cur.execute("SELECT material_code, description, unit FROM materials ORDER BY material_code")
    materials_for_dropdown = cur.fetchall()

    return render_template("transfers/add_transfer.html",
                           materials=materials_for_dropdown,
                           date=datetime.now().strftime("%Y-%m-%d"),
                           departments=DEPARTMENTS)


@app.route("/transfers/edit/<int:tid>", methods=["GET", "POST"])
def transfer_edit(tid):
    if "user" not in session:
        return redirect(url_for("login"))

    conn = get_db()
    cur = conn.cursor()

    cur.execute("SELECT * FROM transfers WHERE id = ?", (tid,))
    original_transfer = cur.fetchone()

    if request.method == "POST":
        material_code = original_transfer['code']
        department = request.form.get("department")
        person = request.form.get("person")
        units = request.form.get("units")

        if request.form.get("outward") is not None:
            new_outward = float(request.form.get("outward") or 0)
        else:
            main_val = float(request.form.get("outward_main") or 0)
            sub_val = float(request.form.get("outward_sub") or 0)
            if units in ["kg", "litre"]:
                new_outward = main_val + (sub_val / 1000.0)
            else:
                new_outward = main_val

        if request.form.get("return_units") is not None:
            new_return_units = float(request.form.get("return_units") or 0)
        else:
            main_ret = float(request.form.get("return_main") or 0)
            sub_ret = float(request.form.get("return_sub") or 0)
            if units in ["kg", "litre"]:
                new_return_units = main_ret + (sub_ret / 1000.0)
            else:
                new_return_units = main_ret

        # 1. Get Current Stock for THIS LOT
        cur.execute("SELECT quantity FROM materials WHERE material_code = ? AND lot_no = ?", (material_code, original_transfer['lot_no']))
        material_data = cur.fetchone()
        if not material_data:
            return "Error: Material Lot not found", 400
        
        current_real_stock = material_data['quantity'] or 0

        # 2. Calculate "Stock Before This Transfer"
        old_outward = original_transfer['outward']
        old_return = original_transfer['return_units']
        
        stock_if_transfer_undone = current_real_stock + old_outward - old_return

        # 3. Validation
        if new_outward > (stock_if_transfer_undone + 0.001):
             return f"""
            <script>
                alert('Insufficient Stock for update!\\nAvailable Max: {round(stock_if_transfer_undone, 3)}\\nNew Transfer Out: {new_outward}');
                window.history.back();
            </script>
            """

        # 4. Apply Changes
        reversal_change = old_outward - old_return
        cur.execute("UPDATE materials SET quantity = ROUND(quantity + ?, 3) WHERE material_code = ? AND lot_no = ?", 
                    (reversal_change, material_code, original_transfer['lot_no']))
        
        # Apply New
        new_change = new_return_units - new_outward
        cur.execute("UPDATE materials SET quantity = ROUND(quantity + ?, 3) WHERE material_code = ? AND lot_no = ?", 
                    (new_change, material_code, original_transfer['lot_no']))
        
        # ⭐ CALCULATE NEW REMAINING BALANCE
        new_remaining_balance = stock_if_transfer_undone + new_change

        # 5. Update Record (⭐ SAVING NEW REMAINING BALANCE)
        cur.execute("""
            UPDATE transfers 
            SET outward=?, units=?, department=?, person=?, return_units=?, availability=? 
            WHERE id=?
        """, (new_outward, units, department, person, new_return_units, new_remaining_balance, tid))

        conn.commit()
        return redirect(url_for("transfer_list"))

    return render_template("transfers/edit_transfer.html", 
                           transfer=original_transfer,
                           departments=DEPARTMENTS)

@app.route("/transfers/delete/<int:tid>")
def transfer_delete(tid):
    if "user" not in session:
        return redirect(url_for("login"))
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM transfers WHERE id=?", (tid,))
    transfer = cur.fetchone()
    if transfer:
        net_change = transfer['return_units'] - transfer['outward']
        cur.execute("UPDATE materials SET quantity = quantity - ? WHERE material_code = ? AND lot_no = ?", (net_change, transfer['code'], transfer['lot_no']))
        cur.execute("DELETE FROM transfers WHERE id=?", (tid,))
        conn.commit()
    return redirect(url_for("transfer_list"))

@app.route("/help")
def system_help():
    if "user" not in session:
        return redirect(url_for("login"))
    return render_template("help.html")

# -----------------------------
# Material Utilization Report (MUR)
# -----------------------------
@app.route("/reports/utilization")
def report_utilization():
    if "user" not in session:
        return redirect(url_for("login"))
    
    conn = get_db()
    cur = conn.cursor()
    
    # Get filters
    period = request.args.get('period', 'monthly') # weekly, monthly, yearly
    selected_year = request.args.get('year', datetime.now().strftime('%Y'))
    selected_month = request.args.get('month', datetime.now().strftime('%m'))
    selected_category = request.args.get('category', '')

    # Fetch unique categories for dropdown
    cur.execute("SELECT DISTINCT category FROM materials WHERE category IS NOT NULL AND category != '' ORDER BY category")
    categories = [r["category"] for r in cur.fetchall()]
    
    # --- PERIOD LOGIC ---
    # target_month_start: e.g. '2026-01-01'
    # target_month_end: e.g. '2026-01-31'
    
    if period == 'weekly':
        period_start = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')
        period_end = datetime.now().strftime('%Y-%m-%d')
    elif period == 'monthly':
        period_start = f"{selected_year}-{selected_month}-01"
        # Get last day of month
        if selected_month == '12':
            period_end = f"{selected_year}-12-31"
        else:
            next_month = datetime(int(selected_year), int(selected_month) + 1, 1)
            period_end = (next_month - timedelta(days=1)).strftime('%Y-%m-%d')
    else: # yearly
        period_start = f"{selected_year}-01-01"
        period_end = f"{selected_year}-12-31"

    # Fetch materials (Aggregated by Code)
    if selected_category:
        cur.execute("SELECT DISTINCT material_code, description, unit, category FROM materials WHERE category = ? ORDER BY material_code", (selected_category,))
    else:
        cur.execute("SELECT DISTINCT material_code, description, unit, category FROM materials ORDER BY material_code")
    materials = cur.fetchall()
    
    utilization_data = []
    category_summary_map = {} # (category, unit) -> { ... }

    for mat in materials:
        code = mat['material_code']
        desc = mat['description']
        
        # Get total current stock for all lots of this code
        cur.execute("SELECT SUM(quantity) FROM materials WHERE material_code = ?", (code,))
        current_stock = cur.fetchone()[0] or 0
        unit = mat['unit'] or 'Units'
        cat_name = mat['category'] or 'Uncategorized'
        
        # 1. PURCHASED in Period
        cur.execute("""
            SELECT COALESCE(SUM(ii.quantity), 0) 
            FROM invoice_items ii 
            JOIN invoices i ON ii.invoice_id = i.id 
            WHERE ii.material = ? AND date(i.date) BETWEEN ? AND ?
        """, (code, period_start, period_end))
        in_purchased = cur.fetchone()[0] or 0
        
        # 2. USED in Period (Transfers + Dispatches - Returns)
        cur.execute("SELECT COALESCE(SUM(outward), 0) FROM transfers WHERE code = ? AND date(date) BETWEEN ? AND ?", (code, period_start, period_end))
        in_transferred = cur.fetchone()[0] or 0
        cur.execute("SELECT COALESCE(SUM(return_units), 0) FROM transfers WHERE code = ? AND date(date) BETWEEN ? AND ?", (code, period_start, period_end))
        in_returned = cur.fetchone()[0] or 0
        cur.execute("SELECT COALESCE(SUM(quantity), 0) FROM dispatches WHERE material_code = ? AND date(date) BETWEEN ? AND ?", (code, period_start, period_end))
        in_dispatched = cur.fetchone()[0] or 0
        in_used = in_transferred + in_dispatched - in_returned

        # 3. Calculate FLOWS AFTER Period (to backtrack to period closing)
        cur.execute("""
            SELECT COALESCE(SUM(ii.quantity), 0) 
            FROM invoice_items ii JOIN invoices i ON ii.invoice_id = i.id 
            WHERE ii.material = ? AND date(i.date) > ?
        """, (code, period_end))
        after_purchased = cur.fetchone()[0] or 0
        
        cur.execute("SELECT COALESCE(SUM(outward - return_units), 0) FROM transfers WHERE code = ? AND date(date) > ?", (code, period_end))
        after_transferred = cur.fetchone()[0] or 0
        cur.execute("SELECT COALESCE(SUM(quantity), 0) FROM dispatches WHERE material_code = ? AND date(date) > ?", (code, period_end))
        after_dispatched = cur.fetchone()[0] or 0
        after_used = after_transferred + after_dispatched

        # BACKTRACK MATH:
        # Period Closing = Current Stock + Used_After - Purchased_After
        period_closing = current_stock + after_used - after_purchased
        # Period Opening = Period Closing + Used_In - Purchased_In
        period_opening = period_closing + in_used - in_purchased

        u_pct = 0
        total_available = period_opening + in_purchased # Or just period_opening + in_purchased
        if (period_opening + in_purchased) > 0:
            u_pct = round((in_used / (period_opening + in_purchased)) * 100, 1)
            if u_pct > 100: u_pct = 100
            if u_pct < 0: u_pct = 0
            

        # Prepare individual data item
        data_item = {
            'code': code,
            'category': cat_name,
            'unit': unit,
            'opening': period_opening,
            'purchased': in_purchased,
            'used': in_used,
            'closing': period_closing,
            'item_count': 1,
            'materials': [desc], # Just one material name
            'utilization_percent': u_pct
        }
        utilization_data.append(data_item)

    # Merge with location data
    cur.execute("SELECT category, location FROM category_locations")
    loc_map = {r['category']: r['location'] for r in cur.fetchall()}

    # Prepare final list for template
    category_summary = []
    for item in utilization_data:
        item['shelf_location'] = loc_map.get(item['category'], 'Not Assigned')
        category_summary.append(item)

    # Sort by Category and then by Material Name
    category_summary.sort(key=lambda x: (x['category'], x['materials'][0]))
        
    current_date = datetime.now().strftime('%d/%m/%Y %I:%M:%S %p')
    return render_template("reports/utilization.html", 
                           category_summary=category_summary,
                           period=period,
                           period_start=period_start,
                           period_end=period_end,
                           selected_year=selected_year,
                           selected_month=selected_month,
                           categories=categories,
                           selected_category=selected_category,
                           current_date=current_date)

# -----------------------------
# Reports
# -----------------------------
@app.route("/reports")
def reports_index():
    if "user" not in session:
        return redirect(url_for("login"))
    return render_template("reports/index.html")

@app.route("/reports/reorder")
def report_reorder():
    if "user" not in session:
        return redirect(url_for("login"))
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT material_code, description, quantity, reorder_level FROM materials WHERE quantity <= reorder_level AND quantity > 0")
    materials = cur.fetchall()
    current_date = datetime.now().strftime("%d/%m/%Y %H:%M")
    return render_template("reports/reorder.html", materials=materials, current_date=current_date)

@app.route("/reports/outofstock")
def report_outofstock():
    if "user" not in session:
        return redirect(url_for("login"))
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT material_code, description, category FROM materials WHERE quantity = 0")
    materials = cur.fetchall()
    current_date = datetime.now().strftime("%d/%m/%Y %H:%M")
    return render_template("reports/outofstock.html", materials=materials, current_date=current_date)

@app.route("/reports/department")
def report_department():
    if "user" not in session:
        return redirect(url_for("login"))
    dept_filter = request.args.get("department")
    date_filter = request.args.get("date")
    conn = get_db()
    cur = conn.cursor()
    query = "SELECT * FROM transfers"
    params = []
    conditions = []
    if dept_filter:
        conditions.append("department = ?"); params.append(dept_filter)
    if date_filter:
        conditions.append("date(date) = ?"); params.append(date_filter)
    if conditions:
        query += " WHERE " + " AND ".join(conditions)
    cur.execute(query, tuple(params))
    records_raw = cur.fetchall()
    records = []
    for row in records_raw:
        record_item = dict(row)
        if record_item.get('date'):
            try:
                record_item['date'] = datetime.strptime(record_item['date'], '%Y-%m-%d')
            except Exception:
                pass
        if record_item.get('expiry_date'):
            try:
                record_item['expiry_date'] = datetime.strptime(record_item['expiry_date'], '%Y-%m-%d')
            except Exception:
                pass
        records.append(record_item)
    cur.execute("SELECT DISTINCT department FROM transfers")
    departments = cur.fetchall()
    current_date = datetime.now().strftime("%d/%m/%Y %H:%M")
    return render_template("reports/department.html", records=records, departments=departments, current_date=current_date)

#   UPDATED DAILY LEDGER REPORT 
@app.route("/reports/daily_ledger")
def report_daily_ledger():
    if "user" not in session:
        return redirect(url_for("login"))
    conn = get_db()
    cur = conn.cursor()
    
    today = datetime.now().date()
    raw_selected_date = request.args.get('date', today.strftime('%Y-%m-%d'))
    
    try: selected_dt = datetime.strptime(raw_selected_date, '%Y-%m-%d').date()
    except:
        try:
            for fmt in ["%d-%m-%Y", "%d/%m/%Y"]:
                try:
                    selected_dt = datetime.strptime(raw_selected_date, fmt).date()
                    break
                except: continue
            if not selected_dt: selected_dt = today
        except: selected_dt = today
            
    selected_date_str = selected_dt.strftime('%Y-%m-%d')
    is_viewing_today = (selected_dt == today)

    cur.execute("SELECT * FROM materials")
    materials = cur.fetchall()
    
    ledger_data = []
    for material in materials:
        mat_code = material['material_code']
        current_quantity = material['quantity'] or 0
        db_opening = material['opening_stock'] or 0
        
        # ⭐ IMPROVED QUERY: Use LIKE and date() to catch all formats
        cur.execute("""
            SELECT COALESCE(SUM(ii.quantity), 0) AS total 
            FROM invoice_items AS ii 
            JOIN invoices AS i ON ii.invoice_id = i.id 
            WHERE ii.material = ? AND (i.date LIKE ? OR date(i.date) = ?)
        """, (mat_code, f"{selected_date_str}%", selected_date_str))
        invoices_today = cur.fetchone()['total'] or 0
        
        cur.execute("""SELECT COALESCE(SUM(outward),0) AS total_outward FROM transfers WHERE code = ? AND (date LIKE ? OR date(date) = ?)""", (mat_code, f"{selected_date_str}%", selected_date_str))
        transfers_outward_today = cur.fetchone()['total_outward'] or 0
        
        cur.execute("""SELECT COALESCE(SUM(return_units),0) AS total_return FROM transfers WHERE code = ? AND (date LIKE ? OR date(date) = ?)""", (mat_code, f"{selected_date_str}%", selected_date_str))
        transfers_return_today = cur.fetchone()['total_return'] or 0
        
        # ⭐ USE DB OPENING
        calculated_opening = db_opening

        # ⭐ FORCE CLOSING TO MATCH REALITY IF TODAY
        if is_viewing_today:
            closing_stock_display = current_quantity
        else:
            closing_stock_display = calculated_opening + invoices_today - transfers_outward_today + transfers_return_today

        if closing_stock_display > 0 or invoices_today > 0 or transfers_outward_today > 0 or calculated_opening > 0:
            ledger_data.append({
                'code': mat_code,
                'description': material['description'],
                'opening_stock': round(calculated_opening, 3),
                'transfer_out': round(transfers_outward_today, 3),
                'return_in': round(transfers_return_today, 3),
                'closing_stock': round(closing_stock_display, 3),
                'unit': material['unit'],
                'reorder_level': material['reorder_level']  # <--- ⭐ I ADDED THIS LINE
            })
    
    return render_template("reports/daily_ledger.html", 
                           ledger_data=ledger_data, 
                           selected_date=selected_date_str, 
                           current_date=datetime.now().strftime("%d/%m/%Y %H:%M"))
    
# -----------------------------
# Expiring Soon Report Route
# -----------------------------
@app.route("/reports/expiring")
def report_expiring():
    if "user" not in session:
        return redirect(url_for("login"))
    
    conn = get_db()
    cur = conn.cursor()
    
    # Query to fetch items expiring soon (or already expired)
    # We select material_code, description (Name), quantity (Availability),
    # unit, purchase_date, and expiry_date
    cur.execute("""
        SELECT material_code, description, quantity, unit, purchase_date, expiry_date, lot_no
        FROM materials 
        WHERE expiry_date IS NOT NULL 
        AND expiry_date != '' 
        AND expiry_date <= date('now', '+30 days')
        ORDER BY expiry_date ASC
    """)
    
    materials = []
    rows = cur.fetchall()
    
    # Process dates for cleaner display
    for row in rows:
        item = dict(row)
        
        # Format Expiry Date (YYYY-MM-DD -> DD-MM-YYYY)
        if item.get("expiry_date"):
            try:
                exp_dt = datetime.strptime(item["expiry_date"], "%Y-%m-%d")
                item["expiry_date"] = exp_dt.strftime("%d/%m/%Y")
                
                # Calculate Days Left
                days_left = (exp_dt.date() - datetime.now().date()).days
                item["days_left"] = days_left
            except:
                item["days_left"] = 0
        
        # Format Purchase Date (YYYY-MM-DD -> DD-MM-YYYY)
        if item.get("purchase_date"):
            try:
                pur_dt = datetime.strptime(item["purchase_date"], "%Y-%m-%d")
                item["purchase_date"] = pur_dt.strftime("%d/%m/%Y")
            except:
                pass # Keep original if error
        
        materials.append(item)
    
    current_date = datetime.now().strftime("%d/%m/%Y %H:%M")
    return render_template("reports/expiring.html", materials=materials, current_date=current_date)

# -----------------------------
# Material Directory / Wall Reference Chart Report
# -----------------------------
@app.route("/reports/material_directory")
@app.route("/reports/material_catalog")
def report_material_directory():
    if "user" not in session:
        return redirect(url_for("login"))
    
    conn = get_db()
    cur = conn.cursor()
    
    selected_category = request.args.get("category", "").strip()
    search = request.args.get("search", "").strip()
    
    # Get distinct categories for dropdown filter
    cur.execute("SELECT DISTINCT category FROM materials WHERE category IS NOT NULL AND category != '' ORDER BY category ASC")
    categories = [r["category"] for r in cur.fetchall()]
    
    # Fetch category to shelf location mapping
    cur.execute("SELECT category, location FROM category_locations")
    loc_map = {r['category']: r['location'] for r in cur.fetchall()}
    
    # Fetch unique master materials by code
    query = """
        SELECT 
            material_code,
            description,
            category,
            unit,
            COALESCE(hsn_sac, '') as hsn_sac,
            MAX(reorder_level) as reorder_level
        FROM materials
        WHERE 1=1
    """
    params = []
    if selected_category:
        query += " AND category = ?"
        params.append(selected_category)
    if search:
        query += " AND (material_code LIKE ? OR description LIKE ? OR category LIKE ? OR hsn_sac LIKE ?)"
        term = f"%{search}%"
        params.extend([term, term, term, term])
        
    query += " GROUP BY material_code, description, category, unit ORDER BY category ASC, material_code ASC, description ASC"
    
    cur.execute(query, tuple(params))
    rows = cur.fetchall()
    
    # Group materials by Category for clean wall chart printing
    grouped_materials = {}
    total_materials = 0
    
    for r in rows:
        cat = r["category"] or "Uncategorized"
        if cat not in grouped_materials:
            grouped_materials[cat] = {
                "category_name": cat,
                "location": loc_map.get(cat, "Not Assigned"),
                "material_items": []
            }
        grouped_materials[cat]["material_items"].append({
            "code": r["material_code"],
            "description": r["description"],
            "unit": r["unit"] or "-",
            "hsn_sac": r["hsn_sac"] or "-",
            "reorder_level": r["reorder_level"] or 0,
            "location": loc_map.get(cat, "Not Assigned")
        })
        total_materials += 1
        
    current_date = datetime.now().strftime("%d/%m/%Y %I:%M %p")
    
    return render_template(
        "reports/material_directory.html",
        grouped_materials=grouped_materials,
        categories=categories,
        selected_category=selected_category,
        search=search,
        total_materials=total_materials,
        total_categories=len(grouped_materials),
        current_date=current_date
    )

# -----------------------------
# NEW: Storage / Batch Report
# -----------------------------
# MMS.py

@app.route("/reports/storage")
def report_storage():
    if "user" not in session:
        return redirect(url_for("login"))
    
    conn = get_db()
    cur = conn.cursor()
    
    # 1. Defaults to TODAY
    today_str = datetime.now().strftime("%Y-%m-%d")
    
    # Get parameters
    from_date = request.args.get("from_date", today_str)
    to_date = request.args.get("to_date", today_str)
    search_batch = request.args.get("search_batch", "").strip() # <--- NEW PARAMETER
    
    # 2. Daily Dispatches Logic (Resets daily)
    dispatch_query = """
        SELECT db.batch_no, d.product, SUM(db.quantity) as daily_total
        FROM dispatch_batches db
        JOIN dispatches d ON db.dispatch_id = d.id
        WHERE date(d.date) >= ? AND date(d.date) <= ?
        GROUP BY db.batch_no, d.product
    """
    cur.execute(dispatch_query, (from_date, to_date))
    daily_dispatches = {}
    for row in cur.fetchall():
        key = (row['batch_no'], row['product']) # Create a unique key
        daily_dispatches[key] = row['daily_total']

    # 3. Fetch Active Batches
    # Start building the query
    query = """
        SELECT 
            batch_no, 
            description, 
            uom,
            SUM(available_quantity) as total_available
        FROM batches 
        WHERE available_quantity > 0 
    """
    
    params = []
    
    # <--- ADD SEARCH LOGIC HERE
    if search_batch:
        query += " AND batch_no LIKE ?"
        params.append(f"%{search_batch}%")
        
    query += " GROUP BY batch_no, description, uom ORDER BY MAX(created_at) DESC"
    
    cur.execute(query, tuple(params))
    rows = cur.fetchall()
    
    batches = []
    summary_totals = {}
    
    # Current Date for the report header/columns
    current_date_display = datetime.now().strftime("%d/%m/%Y") 
    
    for row in rows:
        batch = dict(row)
        
        # Add the date string to the dictionary passed to HTML
        batch["report_date"] = current_date_display 

        # Get Quantities
        avail_qty = batch["total_available"] or 0
        key = (batch['batch_no'], batch['description'])
        dispatched_today = daily_dispatches.get(key, 0)

        # Format Quantities
        batch["dispatched_display"] = format_storage_quantity(dispatched_today, batch.get('uom',''))
        batch["avail_qty_display"] = format_storage_quantity(avail_qty, batch.get('uom',''))
        
        # Status
        if avail_qty == 0:
            batch["status"] = "EMPTY"
            batch["status_class"] = "status-empty"
        else:
            batch["status"] = "ACTIVE"
            batch["status_class"] = "status-full"
        
        batches.append(batch)

        # Summary Totals
        uom = batch.get('uom') or 'Other'
        if uom not in summary_totals:
            summary_totals[uom] = {'dispatched_today': 0.0, 'available': 0.0}
        
        summary_totals[uom]['dispatched_today'] += float(dispatched_today)
        summary_totals[uom]['available'] += float(avail_qty)

    return render_template("reports/Stock Availability & Dispatch Summary.html", 
                           batches=batches, 
                           summary=summary_totals,
                           current_date=current_date_display,
                           search_batch=search_batch,
                           from_date=from_date,
                           to_date=to_date) # <--- Pass date range back to template
    


# API: lookup material from STORAGE (batches)
# -----------------------------
@app.route('/api/storage/get')
def api_get_storage_material():
    """Fetch material details from storage batches (not materials table)."""
    if "user" not in session:
        return jsonify({"error": "Unauthorized"}), 401

    code = request.args.get('code')
    if not code:
        return jsonify({"error": "Missing material code"}), 400

    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        SELECT material_code, description, uom
        FROM batches
        WHERE material_code = ?
        ORDER BY id DESC
        LIMIT 1
    """, (code,))
    material = cur.fetchone()

    if not material:
        return jsonify({"error": "Material not found"}), 404

    return jsonify({
        "code": material["material_code"],
        "name": material["description"],
        "unit": material["uom"]
    })

@app.route("/reports/send_daily_mail")
def trigger_manual_report():
    if "user" not in session:
        return "Not Authorized", 401
    
    if smart_report_mailer:
        try:
            # Generate the summary and send it immediately
            summary = smart_report_mailer.generate_ai_summary()
            smart_report_mailer.send_report_email(summary)
            return "Success: Report sent."
        except Exception as e:
            return f"Error: {str(e)}", 500
    else:
        return "Error: Mailer module not found.", 500


# -----------------------------
# Warehouse Category Management
# -----------------------------
@app.route("/warehouse/categories", methods=["GET", "POST"])
def warehouse_categories():
    if "user" not in session: return redirect(url_for("login"))
    conn = get_db()
    cur = conn.cursor()

    if request.method == "POST":
        category = request.form.get("category")
        location = request.form.get("location")
        cur.execute("""
            INSERT INTO category_locations (category, location, last_updated)
            VALUES (?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(category) DO UPDATE SET location=excluded.location, last_updated=CURRENT_TIMESTAMP
        """, (category, location))
        conn.commit()
        return redirect(url_for("warehouse_categories"))

    # Fetch all unique categories from materials
    cur.execute("SELECT DISTINCT category FROM materials WHERE category IS NOT NULL AND category != ''")
    all_categories = [r['category'] for r in cur.fetchall()]

    # Fetch existing locations
    cur.execute("SELECT category, location FROM category_locations")
    location_map = {r['category']: r['location'] for r in cur.fetchall()}

    return render_template("warehouse/category_locations.html", 
                           categories=all_categories, 
                           location_map=location_map)


# --- REPLACE THE BOTTOM OF MMS.py WITH THIS ---

# -----------------------------
# Stock Adjustment
# -----------------------------
@app.route("/stock/adjustment")
def stock_adjustment():
    if "user" not in session:
        return redirect(url_for("login"))
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT DISTINCT category FROM materials WHERE category IS NOT NULL AND category != '' ORDER BY category")
    categories = [r["category"] for r in cur.fetchall()]

    # Simple fetch — no JOIN to avoid issues if stock_adjustments schema differs
    try:
        cur.execute("SELECT * FROM stock_adjustments ORDER BY created_at DESC LIMIT 30")
        rows = cur.fetchall()
    except Exception:
        rows = []

    # Enrich each row with description + unit from materials (Python-side lookup)
    history = []
    for row in rows:
        row_dict = dict(row)
        mat_code = row_dict.get("material_code", "")
        if mat_code:
            cur.execute("""SELECT description, unit FROM materials
                           WHERE material_code = ? ORDER BY id DESC LIMIT 1""", (mat_code,))
            mat = cur.fetchone()
            row_dict["description"] = mat["description"] if mat else ""
            row_dict["unit"]        = mat["unit"] if mat else ""
        else:
            row_dict["description"] = ""
            row_dict["unit"]        = ""
        row_dict["amount"]     = float(row_dict.get("amount") or 0)
        row_dict["before_qty"] = float(row_dict.get("before_qty") or 0)
        row_dict["after_qty"]  = float(row_dict.get("after_qty") or 0)
        history.append(row_dict)

    return render_template("materials/stock_adjustment.html", categories=categories, history=history)

@app.route("/api/stock/search")
def api_stock_search():
    if "user" not in session:
        return jsonify([])
    term = request.args.get("q", "").strip()
    category = request.args.get("category", "").strip()

    conn = get_db()
    cur = conn.cursor()

    conditions = ["1=1"]
    params = []

    if term:
        conditions.append("(material_code LIKE ? OR description LIKE ?)")
        params.extend([f"%{term}%", f"%{term}%"])

    if category:
        conditions.append("category = ?")
        params.append(category)

    where = " AND ".join(conditions)
    cur.execute(f"""
        SELECT material_code, description, category, unit,
               SUM(quantity) as total_quantity, reorder_level
        FROM materials
        WHERE {where}
        GROUP BY material_code
        ORDER BY material_code
        LIMIT 25
    """, tuple(params))

    rows = cur.fetchall()
    results = [{
        "code": r["material_code"],
        "description": r["description"],
        "category": r["category"],
        "unit": r["unit"],
        "quantity": round(r["total_quantity"] or 0, 3),
        "reorder_level": r["reorder_level"]
    } for r in rows]

    return jsonify(results)

@app.route("/api/stock/adjust", methods=["POST"])
def api_stock_adjust():
    if "user" not in session:
        return jsonify({"success": False, "error": "Not logged in"}), 401
    data = request.get_json()
    material_code = (data.get("material_code") or "").strip()
    operation = data.get("operation", "add")  # "add" or "subtract"
    try:
        amount = float(data.get("amount", 0))
    except Exception:
        return jsonify({"success": False, "error": "Invalid amount"}), 400
    reason = (data.get("reason") or "Manual adjustment").strip()

    if not material_code or amount <= 0:
        return jsonify({"success": False, "error": "Missing material code or invalid amount"}), 400

    conn = get_db()
    cur = conn.cursor()

    cur.execute("SELECT SUM(quantity) as total FROM materials WHERE material_code = ?", (material_code,))
    row = cur.fetchone()
    if not row or row["total"] is None:
        return jsonify({"success": False, "error": "Material not found"}), 404

    current_total = row["total"] or 0

    if operation == "subtract":
        if amount > current_total:
            return jsonify({"success": False, "error": f"Cannot subtract {amount} — only {current_total:.3f} in stock"}), 400
        # FIFO: consume from oldest lots first
        remaining = amount
        cur.execute("SELECT id, quantity FROM materials WHERE material_code = ? AND quantity > 0 ORDER BY id ASC", (material_code,))
        lots = cur.fetchall()
        for lot in lots:
            if remaining <= 0:
                break
            if lot["quantity"] <= remaining:
                cur.execute("UPDATE materials SET quantity = 0 WHERE id = ?", (lot["id"],))
                remaining -= lot["quantity"]
            else:
                cur.execute("UPDATE materials SET quantity = quantity - ? WHERE id = ?", (remaining, lot["id"]))
                remaining = 0
        new_total = current_total - amount
    else:
        # Add to latest lot
        cur.execute("SELECT id FROM materials WHERE material_code = ? ORDER BY id DESC LIMIT 1", (material_code,))
        latest = cur.fetchone()
        if latest:
            cur.execute("UPDATE materials SET quantity = quantity + ? WHERE id = ?", (amount, latest["id"]))
        new_total = current_total + amount

    # Log the adjustment
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cur.execute("""
        INSERT INTO stock_adjustments (material_code, operation, amount, reason, before_qty, after_qty, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (material_code, operation, amount, reason, current_total, new_total, now_str))

    conn.commit()
    return jsonify({"success": True, "before": round(current_total, 3), "after": round(new_total, 3)})


def run_flask():
    # Only run the server here
    serve(app, host="127.0.0.1", port=5008)

if __name__ == "__main__":
    # 1. Start Flask in a background thread
    threading.Thread(target=run_flask, daemon=True).start()

    # 2. Start the Desktop Window
    webview.create_window(
        "Benchmark Tea & Chocolate Factory - MMS",
        "http://127.0.0.1:5008/login",
        width=1200,
        height=800
    )
    webview.start()
