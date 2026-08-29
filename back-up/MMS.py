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
    """Convert any date format to clean YYYY-MM-DD (no time)."""
    if not raw_date:
        return datetime.now().strftime("%Y-%m-%d")

    raw_date = raw_date.strip()

    # If date has time → remove time part
    if " " in raw_date:
        raw_date = raw_date.split(" ")[0]

    # Try dd-mm-yyyy → yyyy-mm-dd
    try:
        dt = datetime.strptime(raw_date, "%d-%m-%Y")
        return dt.strftime("%Y-%m-%d")
    except:
        pass

    # Try yyyy-mm-dd → already correct
    try:
        dt = datetime.strptime(raw_date, "%Y-%m-%d")
        return dt.strftime("%Y-%m-%d")
    except:
        pass

    return datetime.now().strftime("%Y-%m-%d")

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
    """Reset daily data, update opening stocks, AND update material dates"""
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    
    today = datetime.now().strftime("%Y-%m-%d")
    
    print(f"Resetting daily data for {today}...")
    
    # Update: Yesterday's quantity becomes today's opening_stock
    # AND update purchase_date to today's date
    cur.execute("""
        UPDATE materials 
        SET opening_stock = quantity,
            purchase_date = ?,
            last_updated = ?
    """, (today, today))
    
    conn.commit()
    mirror.mirror_backup()
    conn.close()
    print("Daily data reset completed - dates updated to", today)
    print("Daily data reset completed")

# Optional: if you have this module, it will be launched in background
try:
    import smart_report_mailer
except Exception:
    smart_report_mailer = None


app = Flask(__name__)
app.secret_key = "super_secret_key"

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
        material_code TEXT NOT NULL UNIQUE,
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
        uom TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
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
    """Update existing database with ALL new fields automatically."""
    conn = sqlite3.connect(DATABASE)
    cur = conn.cursor()
    
    try:
        # 1. Update INVOICES Table
        cur.execute("PRAGMA table_info(invoices)")
        columns = [col[1] for col in cur.fetchall()]
        
        if 'cgst_percent' not in columns:
            cur.execute("ALTER TABLE invoices ADD COLUMN cgst_percent REAL DEFAULT 0")
        if 'sgst_percent' not in columns:
            cur.execute("ALTER TABLE invoices ADD COLUMN sgst_percent REAL DEFAULT 0")
        if 'round_off_value' not in columns:
            cur.execute("ALTER TABLE invoices ADD COLUMN round_off_value REAL DEFAULT 0")
        if 'final_total' not in columns:
            cur.execute("ALTER TABLE invoices ADD COLUMN final_total REAL DEFAULT 0")
        if 'total_igst' not in columns:
            cur.execute("ALTER TABLE invoices ADD COLUMN total_igst REAL DEFAULT 0")

        # 2. Update INVOICE_ITEMS Table
        cur.execute("PRAGMA table_info(invoice_items)")
        columns = [col[1] for col in cur.fetchall()]
        
        if 'discount_percentage' not in columns:
            cur.execute("ALTER TABLE invoice_items ADD COLUMN discount_percentage REAL DEFAULT 0")
        if 'igst_percentage' not in columns:
            cur.execute("ALTER TABLE invoice_items ADD COLUMN igst_percentage REAL DEFAULT 0")
        if 'item_igst_value' not in columns:
            cur.execute("ALTER TABLE invoice_items ADD COLUMN item_igst_value REAL DEFAULT 0")

        # 3. Update MATERIALS Table
        cur.execute("PRAGMA table_info(materials)")
        columns = [col[1] for col in cur.fetchall()]

        if 'purchase_date' not in columns:
            cur.execute("ALTER TABLE materials ADD COLUMN purchase_date TEXT")
        if 'expiry_date' not in columns:
            cur.execute("ALTER TABLE materials ADD COLUMN expiry_date TEXT")

        # 4. Update BATCHES Table (Add available_quantity)
        cur.execute("PRAGMA table_info(batches)")
        columns = [col[1] for col in cur.fetchall()]

        if 'available_quantity' not in columns:
            # Create the column
            cur.execute("ALTER TABLE batches ADD COLUMN available_quantity REAL")
            # Set initial available_quantity equal to current received_quantity for existing data
            cur.execute("UPDATE batches SET available_quantity = received_quantity")
            print("Added available_quantity column to batches")

        # 5. ⭐ NEW: Add received_date to batches table if missing
        if 'received_date' not in columns:
            cur.execute("ALTER TABLE batches ADD COLUMN received_date TEXT")
            # Set received_date to created_at for existing records
            cur.execute("UPDATE batches SET received_date = created_at WHERE received_date IS NULL")
            print("Added received_date column to batches")
            
            cur.execute("PRAGMA table_info(batches)")
        columns = [col[1] for col in cur.fetchall()]
        if 'department' not in columns:
            cur.execute("ALTER TABLE batches ADD COLUMN department TEXT")
            print("Added department column to batches")
            
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
# ⭐ ADD: Enhanced daily reset with date updates
if should_reset_daily_data():
    reset_daily_data()
    print("Daily data reset completed for new day - dates updated to current date")
else:
    # Even if no reset needed, ensure dates are current
    today = datetime.now().strftime("%Y-%m-%d")
    conn = sqlite3.connect(DATABASE)
    cur = conn.cursor()
    try:
        cur.execute("UPDATE materials SET purchase_date = ? WHERE purchase_date IS NULL OR purchase_date = ''", (today,))
        conn.commit()
    except:
        pass
    conn.close()
    print("Material dates verified.")

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

    # ⭐ ADD: Check and reset daily data (this will update dates)
    if should_reset_daily_data():
        reset_daily_data()

    conn = get_db()
    cur = conn.cursor()

    # Get today's date in 'YYYY-MM-DD' format
    today_str = datetime.now().strftime("%Y-%m-%d")

    # Fetch all materials
    cur.execute("SELECT * FROM materials ORDER BY material_code")
    all_materials = cur.fetchall()

    stock_data = []

    for material in all_materials:
        mat_code = material["material_code"]
        opening_stock = material["opening_stock"] or 0
        closing_stock = material["quantity"] or 0
        unit = material["unit"]

        # -------------------------------
        # ⭐ AUTO-UPDATED DATE DISPLAY
        # -------------------------------
        formatted_date = ""
        raw_date = material["purchase_date"]

        if raw_date:
            try:
                # Always show in dd-mm-yyyy format
                dt = datetime.strptime(raw_date, "%Y-%m-%d")
                formatted_date = dt.strftime("%d-%m-%Y")
            except:
                formatted_date = "Date Updated"

        # Calculate transfers, returns, etc.
        
        # 1. TRANSFERRED TODAY (Outward) - for display
        # ⭐ FIX: Use date(date) to ensure we match timestamps correctly
        cur.execute("""
            SELECT COALESCE(SUM(outward),0) AS total_outward 
            FROM transfers 
            WHERE code = ? AND date(date) = ?
        """, (mat_code, today_str))
        total_outward = cur.fetchone()["total_outward"] or 0

        # 2. RETURNED TODAY - for display
        # ⭐ FIX: Use date(date) here too
        cur.execute("""
            SELECT COALESCE(SUM(return_units),0) AS total_returned 
            FROM transfers 
            WHERE code = ? AND date(date) = ?
        """, (mat_code, today_str))
        total_returned = cur.fetchone()["total_returned"] or 0

        # 3. PURCHASED TODAY (Optional but good for math consistency)
        cur.execute("""
            SELECT COALESCE(SUM(ii.quantity), 0) as total_inward
            FROM invoice_items ii
            JOIN invoices i ON ii.invoice_id = i.id
            WHERE ii.material = ? AND date(i.date) = ?
        """, (mat_code, today_str))
        total_inward = cur.fetchone()["total_inward"] or 0

        # Append result
        stock_data.append(
            {
                "date": formatted_date,
                "code": mat_code,
                "name": material["description"], 
                "opening_stock": round(opening_stock, 3),
                "purchased_stock": round(total_inward, 3), # Added for completeness
                "transferred_stock": round(total_outward, 3),
                "returned_stock": round(total_returned, 3),
                "closing_stock": round(closing_stock, 3),
                "reorder_level": material["reorder_level"],
                "unit": unit,
            }
        )

    return render_template("materials/list.html", stock_data=stock_data)

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
    
    # Only show batches with Available Quantity > 0
    query = "SELECT * FROM batches WHERE available_quantity > 0"
    params = []
    
    # 1. Apply Date Filter
    if from_date:
        query += " AND date(created_at) >= ?"
        params.append(from_date)
        
    if to_date:
        query += " AND date(created_at) <= ?"
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
        # 1. Date Logic
        raw_date = batch["received_date"] or batch["created_at"] or ""
        formatted_date = "-"
        if raw_date:
            try:
                if " " in raw_date: raw_date = raw_date.split(" ")[0]
                dt = datetime.strptime(raw_date, "%Y-%m-%d")
                formatted_date = dt.strftime("%d-%m-%Y")
            except:
                formatted_date = raw_date

        # 2. Time Logic
        raw_created = batch["created_at"] or ""
        formatted_time = "-"
        if raw_created:
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
            "uom": batch["uom"]
        })

    conn.close()
    return render_template("storage/list.html", batches=formatted_batches)
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
# Add Storage Batch (POST) - UPDATED LOGIC (Always Insert New Row)
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
    # Placeholder code
    material_code = "STORAGE-ITEM"

    try:
        main_qty = float(request.form.get("quantity_main") or 0)
        sub_qty = float(request.form.get("quantity_sub") or 0)
        if uom in ["kg", "litre"]: quantity = main_qty + (sub_qty / 1000.0)
        else: quantity = main_qty
    except: quantity = 0

    if not all([batch_no, description, uom]) or quantity <= 0:
        return "<script>alert('Invalid input');window.history.back();</script>"

    try:
        rounded_qty = round(quantity, 3)
        
        # ⭐ ADDED department to INSERT
        cur.execute("""
            INSERT INTO batches (batch_no, material_code, description, received_quantity, available_quantity, uom, received_date, department, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (batch_no, material_code, description, rounded_qty, rounded_qty, uom, received_date, department, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        
        message = f"New batch {batch_no} created for {description}."
        
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

@app.route("/storage/edit/<int:batch_id>", methods=["POST"])
def edit_storage_data(batch_id):
    """Handle the form submission to update an existing batch."""
    if "user" not in session: return redirect(url_for("login"))
    conn = get_db()
    cur = conn.cursor()

    # 1. Get existing batch details to calculate stock difference
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
        main_qty = float(request.form.get("quantity_main") or 0)
        sub_qty = float(request.form.get("quantity_sub") or 0)
        if uom in ["kg", "litre"]: 
            new_quantity = main_qty + (sub_qty / 1000.0)
        else: 
            new_quantity = main_qty
    except: 
        new_quantity = 0

    if new_quantity <= 0:
        return "<script>alert('Invalid quantity');window.history.back();</script>"

    try:
        new_rounded_qty = round(new_quantity, 3)
        old_received_qty = batch['received_quantity']
        old_available_qty = batch['available_quantity']

        # 3. Calculate Difference
        # If we change received from 100 to 150, difference is +50. 
        # We add +50 to available.
        difference = new_rounded_qty - old_received_qty
        new_available_qty = old_available_qty + difference

        # Validation: Don't allow reducing stock below what has already been used
        if new_available_qty < 0:
             used_qty = old_received_qty - old_available_qty
             return f"<script>alert('Cannot reduce quantity to {new_rounded_qty}. You have already dispatched {used_qty}. Minimum allowed is {used_qty}.');window.history.back();</script>"

        # 4. Update Database
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
        
def refresh_storage_dates():
    """Update storage dates to current date when opening software (new day)."""
    conn = sqlite3.connect(DATABASE)
    cur = conn.cursor()
    
    today = datetime.now().strftime("%Y-%m-%d")
    
    try:
        # Check if any batch has today's date
        cur.execute("SELECT COUNT(*) as count FROM batches WHERE date(created_at) = ? OR date(received_date) = ?", (today, today))
        count = cur.fetchone()["count"]
        
        # If no batches have today's date, update all dates to today
        if count == 0:
            cur.execute("UPDATE batches SET created_at = ?, received_date = ? WHERE created_at IS NOT NULL", (today, today))
            print(f"Storage dates refreshed to: {today}")
            
    except Exception as e:
        print(f"Error refreshing storage dates: {e}")
    finally:
        conn.close()

# Call this function after your app starts
refresh_storage_dates()

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
        query += " AND date(created_at) >= ?"
        params.append(from_date)
    if to_date:
        query += " AND date(created_at) <= ?"
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
                formatted_date = dt.strftime("%d-%m-%Y")
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
        
    return render_template("storage/inward_history.html", history=history_data)
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
        
        if linked > 0:
            return "<script>alert('Cannot delete! This batch is already used in a dispatch.');window.history.back();</script>"

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
    query = "SELECT * FROM invoices"
    params = []

    # Date filters
    if from_date and to_date:
        query += " WHERE date BETWEEN ? AND ?"
        params.extend([from_date, to_date])
    elif from_date:
        query += " WHERE date >= ?"
        params.append(from_date)
    elif to_date:
        query += " WHERE date <= ?"
        params.append(to_date)

    query += " ORDER BY date DESC"

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
                formatted_date = dt.strftime("%d-%m-%Y %I:%M %p")
            except:
                try:
                    # Try date only
                    dt = datetime.strptime(raw_date, "%Y-%m-%d")
                    formatted_date = dt.strftime("%d-%m-%Y")
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

@app.route("/invoices/add", methods=["GET", "POST"])
def invoice_add():
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
                reorder_level = int(request.form.get(f"reorder_level_{i}") or 0)
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
                    discount_percentage, gst_percentage, igst_percentage, item_subtotal, item_gst_value, item_igst_value, item_total, batch_no)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (new_invoice_id, material_code, quantity, unit, unit_price, discount_percentage,
                      gst_percentage, igst_percentage, net_amount, item_gst_value, item_igst_value, item_total, batch_no))

                # Update Material Stock
                cur.execute("SELECT * FROM materials WHERE material_code=?", (material_code,))
                if cur.fetchone():
                    cur.execute("""
                        UPDATE materials SET description=?, quantity=quantity+?, opening_stock=opening_stock+?, 
                        category=?, reorder_level=?, unit_price=?, purchase_date=?, expiry_date=? WHERE material_code=?
                    """, (material_name, quantity, quantity, category, reorder_level, unit_price, item_p_date, item_e_date, material_code))
                else:
                    cur.execute("""
                        INSERT INTO materials(material_code, description, category, opening_stock, quantity, unit, unit_price, purchase_date, expiry_date, lot_no, reorder_level)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (material_code, material_name, category, quantity, quantity, unit, unit_price, item_p_date, item_e_date, batch_no, reorder_level))

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
            cur.execute("SELECT material, quantity FROM invoice_items WHERE invoice_id = ?", (iid,))
            old_items = cur.fetchall()
            for item in old_items:
                cur.execute("""
                    UPDATE materials SET quantity = quantity - ?, opening_stock = opening_stock - ? WHERE material_code = ?
                """, (item["quantity"], item["quantity"], item["material"]))

            cur.execute("DELETE FROM invoice_items WHERE invoice_id = ?", (iid,))

            # 2. UPDATE INVOICE HEADER
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
                reorder_level = int(request.form.get(f"reorder_level_{i}") or 0)
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
                    discount_percentage, gst_percentage, igst_percentage, item_subtotal, item_gst_value, item_igst_value, item_total, batch_no)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (iid, material_code, quantity, unit, unit_price, discount_percentage,
                      gst_percentage, igst_percentage, net_amount, item_gst_value, item_igst_value, item_total, batch_no))

                cur.execute("SELECT * FROM materials WHERE material_code=?", (material_code,))
                if cur.fetchone():
                    cur.execute("""
                        UPDATE materials SET description=?, quantity=quantity+?, opening_stock=opening_stock+?, 
                        category=?, reorder_level=?, unit_price=?, purchase_date=?, expiry_date=? WHERE material_code=?
                    """, (material_name, quantity, quantity, category, reorder_level, unit_price, item_p_date, item_e_date, material_code))
                else:
                    cur.execute("""
                        INSERT INTO materials(material_code, description, category, opening_stock, quantity, unit, unit_price, purchase_date, expiry_date, lot_no, reorder_level)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (material_code, material_name, category, quantity, quantity, unit, unit_price, item_p_date, item_e_date, batch_no, reorder_level))

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
        SELECT ii.*, m.category, m.description, m.reorder_level, m.purchase_date, m.expiry_date
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
            invoice["date"] = dt.strftime("%d-%m-%Y")
        except ValueError: pass 
    
    # ⭐ FIX: Added item_subtotal and item_total to this query
    cur.execute("""
        SELECT 
            ii.material AS code, 
            m.description AS name, 
            ii.quantity, 
            ii.unit, 
            ii.unit_price, 
            ii.discount_percentage,
            ii.gst_percentage AS gst,
            ii.igst_percentage AS igst,
            ii.item_subtotal,  
            ii.item_total
        FROM invoice_items AS ii 
        LEFT JOIN materials AS m ON ii.material = m.material_code 
        WHERE ii.invoice_id = ?
    """, (iid,))
    
    materials = cur.fetchall()
    
    return render_template("invoices/view_invoice.html", invoice=invoice, materials=materials)
@app.route("/invoices/delete/<int:iid>")
def invoice_delete(iid):
    if "user" not in session:
        return redirect(url_for("login"))
    
    conn = get_db()
    cur = conn.cursor()
    try:
        # 1. Get all items associated with this invoice
        cur.execute("SELECT material, quantity FROM invoice_items WHERE invoice_id = ?", (iid,))
        items_to_delete = cur.fetchall()
        
        for item in items_to_delete:
            mat_code = item["material"]
            qty_to_remove = item["quantity"]

            # 2. Reduce BOTH quantity AND opening_stock (Reverse the addition)
            cur.execute("""
                UPDATE materials 
                SET quantity = quantity - ?, 
                    opening_stock = opening_stock - ? 
                WHERE material_code = ?
            """, (qty_to_remove, qty_to_remove, mat_code))
            
            # --- ⭐ NEW LOGIC: DELETE ROW IF QUANTITY IS 0 ⭐ ---
            # Check the new quantity of the material
            cur.execute("SELECT quantity FROM materials WHERE material_code = ?", (mat_code,))
            row = cur.fetchone()
            
            if row:
                current_qty = row['quantity']
                # If quantity is 0 (or negative due to error), delete the material row entirely
                if current_qty <= 0.001: 
                    cur.execute("DELETE FROM materials WHERE material_code = ?", (mat_code,))
                    print(f"Material {mat_code} deleted because stock reached 0.")
            # -----------------------------------------------------
            
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
    cur.execute("SELECT DISTINCT description FROM batches WHERE description LIKE ? AND available_quantity > 0 LIMIT 10", (f"%{term}%",))
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
        WHERE description = ? AND available_quantity > 0 
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
                dispatch_dict["date"] = dt.strftime("%d-%m-%Y")
            except ValueError:
                pass 

        # Format Quantity
        display_quantity = format_quantity_display(dispatch_dict['quantity'], dispatch_dict['units'])
        dispatch_dict['display_quantity'] = display_quantity
        
        formatted_dispatches.append(dispatch_dict)
    
    total_quantity = sum(d['quantity'] for d in dispatches if d['quantity'] is not None)
    
    return render_template("dispatch/list.html", 
                           dispatches=formatted_dispatches, 
                           total_quantity=round(total_quantity, 3))
    
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

            main_q = float(request.form.get("quantity_main") or 0)
            sub_q = float(request.form.get("quantity_sub") or 0)
            if unit in ["kg", "litre"]: 
                quantity = round(main_q + (sub_q / 1000.0), 3)
            else: 
                quantity = round(main_q, 3)

            if quantity <= 0: 
                return "<script>alert('Invalid quantity');window.history.back();</script>"

            # 1. Get ALL batches for this product (oldest first)
            cur.execute("""
                SELECT id, batch_no, available_quantity 
                FROM batches 
                WHERE description = ? AND available_quantity > 0 
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
            
            # ⭐ AUTO-REMOVE EMPTY BATCHES FROM STORAGE REGISTER
            # Check if the batch is now empty
            cur.execute("SELECT available_quantity FROM batches WHERE id = ?", (batch_data['id'],))
            updated_batch = cur.fetchone()
            
            if updated_batch and updated_batch['available_quantity'] <= 0.001:  # Using small threshold for float comparison
                # Set available_quantity to 0 to ensure it doesn't show in storage
                cur.execute("UPDATE batches SET available_quantity = 0 WHERE id = ?", (batch_data['id'],))
                print(f"Batch {batch_data['batch_no']} marked as empty and removed from storage register")
            
            # 5. Link - ⭐ UPDATED: Store batch_id along with batch_no
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
    
    # ⭐ FIX: Left Join to get Batch No for the edit form
    cur.execute("""
        SELECT d.*, db.batch_no 
        FROM dispatches d
        LEFT JOIN dispatch_batches db ON d.id = db.dispatch_id
        WHERE d.id = ?
    """, (did,))
    row = cur.fetchone()
    if not row: return redirect(url_for("dispatch_list"))
    dispatch = dict(row)

    if dispatch['units'] in ['kg', 'litre']:
        dispatch['quantity_main'] = int(dispatch['quantity'])
        dispatch['quantity_sub'] = round((dispatch['quantity'] - dispatch['quantity_main']) * 1000)
    else:
        dispatch['quantity_main'] = int(dispatch['quantity'])
        dispatch['quantity_sub'] = 0

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

            main_q = float(request.form.get("quantity_main") or 0)
            sub_q = float(request.form.get("quantity_sub") or 0)
            if new_unit in ["kg", "litre"]: new_qty = round(main_q + (sub_q / 1000.0), 3)
            else: new_qty = round(main_q, 3)

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

    # Read transfer records
    cur.execute("SELECT * FROM transfers ORDER BY id DESC")
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
                formatted_date = dt.strftime("%d-%m-%Y %I:%M %p")
            except:
                try:
                    # only date
                    dt = datetime.strptime(raw_date, "%Y-%m-%d")
                    formatted_date = dt.strftime("%d-%m-%Y")
                except:
                    formatted_date = raw_date

        item["date"] = formatted_date

        # ----------------------------
        # ⭐ REMOVE LOT NUMBER FROM BACKEND
        # ----------------------------
        if "lot_no" in item:
            del item["lot_no"]

        transfers.append(item)

    # Load materials list
    cur.execute("SELECT material_code, description FROM materials ORDER BY material_code")
    materials_for_dropdown = cur.fetchall()

    # Today's date (for default)
    today = datetime.now().strftime("%Y-%m-%d")

    return render_template(
        "transfers/form.html",
        transfers=transfers,
        materials=materials_for_dropdown,
        date=today
    )
def normalize_date(raw_date):
    """Convert any date format to clean YYYY-MM-DD, auto-update to current date if needed."""
    today = datetime.now().strftime("%Y-%m-%d")
    
    if not raw_date:
        return today

    raw_date = raw_date.strip()

    # If date has time → remove time part
    if " " in raw_date:
        raw_date = raw_date.split(" ")[0]

    # Try dd-mm-yyyy → yyyy-mm-dd
    try:
        dt = datetime.strptime(raw_date, "%d-%m-%Y")
        parsed_date = dt.strftime("%Y-%m-%d")
        
        # ⭐ AUTO-UPDATE: If the parsed date is not today, return today's date
        if parsed_date != today:
            return today
        return parsed_date
    except:
        pass

    # Try yyyy-mm-dd → already correct
    try:
        dt = datetime.strptime(raw_date, "%Y-%m-%d")
        parsed_date = dt.strftime("%Y-%m-%d")
        
        # ⭐ AUTO-UPDATE: If the parsed date is not today, return today's date
        if parsed_date != today:
            return today
        return parsed_date
    except:
        pass

    # Fallback to today's date
    return today

@app.route("/transfers/add", methods=["GET", "POST"])
def transfer_add():
    if "user" not in session:
        return redirect(url_for("login"))

    conn = get_db()
    cur = conn.cursor()

    if request.method == "POST":
        code = request.form.get("code")
        department = request.form.get("department")
        person = request.form.get("person")
        transfer_date = normalize_date(request.form.get("date"))

        # ⭐ NEW: Single Box Logic
        outward = float(request.form.get("outward") or 0)
        return_units = float(request.form.get("return_units") or 0)
        
        units = request.form.get("units")

        # 1. Fetch Material Data
        cur.execute("SELECT quantity, description, lot_no, unit FROM materials WHERE material_code = ?", (code,))
        material_data = cur.fetchone()
        
        if not material_data:
            return "Error: Material not found", 400
            
        current_stock = material_data['quantity'] or 0
        description = material_data['description']
        lot_no = material_data['lot_no']
        
        if not units: 
            units = material_data['unit']

        # 2. VALIDATION
        if outward > current_stock:
            return f"""
            <script>
                alert('Insufficient Stock!\\nCurrent Available: {current_stock}\\nTransfer Out: {outward}');
                window.history.back();
            </script>
            """

        # 3. Calculate Net Change
        net_change = return_units - outward
        
        # ⭐ CALCULATE REMAINING BALANCE FOR DISPLAY
        remaining_balance = current_stock + net_change

        # 4. Update Stock
        cur.execute("UPDATE materials SET quantity = ROUND(quantity + ?, 3) WHERE material_code = ?", 
                    (net_change, code))

        # 5. Save Transfer Record (⭐ NOW SAVING REMAINING BALANCE)
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
                           date=datetime.now().strftime("%Y-%m-%d"))


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

        new_outward = float(request.form.get("outward") or 0)
        new_return_units = float(request.form.get("return_units") or 0)

        # 1. Get Current Stock
        cur.execute("SELECT quantity FROM materials WHERE material_code = ?", (material_code,))
        material_data = cur.fetchone()
        if not material_data:
            return "Error: Material not found", 400
        
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
        # Reverse Old
        reversal_change = old_outward - old_return
        cur.execute("UPDATE materials SET quantity = ROUND(quantity + ?, 3) WHERE material_code = ?", 
                    (reversal_change, material_code))
        
        # Apply New
        new_change = new_return_units - new_outward
        cur.execute("UPDATE materials SET quantity = ROUND(quantity + ?, 3) WHERE material_code = ?", 
                    (new_change, material_code))
        
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

    return render_template("transfers/edit_transfer.html", transfer=original_transfer)

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
        cur.execute("UPDATE materials SET quantity = quantity - ? WHERE material_code = ?", (net_change, transfer['code']))
        cur.execute("DELETE FROM transfers WHERE id=?", (tid,))
        conn.commit()
    return redirect(url_for("transfer_list"))

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
    current_date = datetime.now().strftime("%d-%m-%Y %H:%M")
    return render_template("reports/reorder.html", materials=materials, current_date=current_date)

@app.route("/reports/outofstock")
def report_outofstock():
    if "user" not in session:
        return redirect(url_for("login"))
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT material_code, description, category FROM materials WHERE quantity = 0")
    materials = cur.fetchall()
    current_date = datetime.now().strftime("%d-%m-%Y %H:%M")
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
        conditions.append("date = ?"); params.append(date_filter)
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
    current_date = datetime.now().strftime("%d-%m-%Y %H:%M")
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
        try: selected_dt = datetime.strptime(raw_selected_date, '%d-%m-%Y').date()
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
        
        cur.execute("""SELECT COALESCE(SUM(ii.quantity), 0) AS total FROM invoice_items AS ii JOIN invoices AS i ON ii.invoice_id = i.id WHERE ii.material = ? AND date(i.date) = ?""", (mat_code, selected_date_str))
        invoices_today = cur.fetchone()['total'] or 0
        
        cur.execute("""SELECT COALESCE(SUM(outward),0) AS total_outward FROM transfers WHERE code = ? AND date(date) = ?""", (mat_code, selected_date_str))
        transfers_outward_today = cur.fetchone()['total_outward'] or 0
        
        cur.execute("""SELECT COALESCE(SUM(return_units),0) AS total_return FROM transfers WHERE code = ? AND date(date) = ?""", (mat_code, selected_date_str))
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
                           current_date=datetime.now().strftime("%d-%m-%Y %H:%M"))
    
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
        SELECT material_code, description, quantity, unit, purchase_date, expiry_date 
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
                item["expiry_date"] = exp_dt.strftime("%d-%m-%Y")
                
                # Calculate Days Left
                days_left = (exp_dt.date() - datetime.now().date()).days
                item["days_left"] = days_left
            except:
                item["days_left"] = 0
        
        # Format Purchase Date (YYYY-MM-DD -> DD-MM-YYYY)
        if item.get("purchase_date"):
            try:
                pur_dt = datetime.strptime(item["purchase_date"], "%Y-%m-%d")
                item["purchase_date"] = pur_dt.strftime("%d-%m-%Y")
            except:
                pass # Keep original if error
        
        materials.append(item)
    
    current_date = datetime.now().strftime("%d-%m-%Y %H:%M")
    return render_template("reports/expiring.html", materials=materials, current_date=current_date)

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
    current_date_display = datetime.now().strftime("%d-%m-%Y") 
    
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
                           search_batch=search_batch) # <--- Pass search term back to template

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


def run_flask():
    serve(app, host="127.0.0.1", port=5004)

if __name__ == "__main__":
    # Start Flask in background
    threading.Thread(target=run_flask).start()

    # Start Smart Report Mailer in background (if available)
    if smart_report_mailer:
        def start_smart_report():
            try:
                smart_report_mailer.main()
            except Exception as e:
                print("smart_report_mailer failed:", e)
        threading.Thread(target=start_smart_report, daemon=True).start()

    # Create desktop window
    webview.create_window("Benchmark Tea & Chocolate Factory - MMS", "http://127.0.0.1:5004/login", width=1200, height=800)
    webview.start()
