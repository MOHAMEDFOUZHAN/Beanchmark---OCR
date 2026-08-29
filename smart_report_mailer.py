import sqlite3
import smtplib
import os
import sys
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
from fpdf import FPDF

# -------------------------------------------------
# ✅ STABLE BASE DIRECTORY (EXE + PY SAFE)
# -------------------------------------------------
if getattr(sys, 'frozen', False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# -----------------------------
# ⭐ DATABASE CONFIG
# -----------------------------
FACTORY_NAME = "BeanchMark-MMS"
PROGRAM_DATA_DIR = os.path.join(os.environ["PROGRAMDATA"], FACTORY_NAME)
DATABASE = os.path.join(
    PROGRAM_DATA_DIR,
    "inventory - BeanchMark-MMS.db"
)

# -----------------------------
# Database Connection
# -----------------------------
def get_db():
    if not os.path.exists(DATABASE):
        print("Database not found:", DATABASE)
        return None
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

# -----------------------------
# FETCH TODAY'S REPORT DATA
# -----------------------------
def get_report_data():
    conn = get_db()
    if not conn:
        return None

    cur = conn.cursor()
    data = {}
    today_iso = datetime.now().strftime('%Y-%m-%d')     # 2026-02-06
    today_india = datetime.now().strftime('%d/%m/%Y')  # 06/02/2026
    
    # 1. Today's Invoices & Total Purchase
    # Search for both ISO and India formats
    cur.execute("""
        SELECT invoice_no, vendor, date, grand_total 
        FROM invoices 
        WHERE (date(date) = ? OR date LIKE ? OR date LIKE ?)
        ORDER BY date DESC
    """, (today_iso, f"{today_iso}%", f"{today_india}%"))
    data['invoices'] = [dict(row) for row in cur.fetchall()]
    
    cur.execute("""
        SELECT SUM(grand_total) as total 
        FROM invoices 
        WHERE (date(date) = ? OR date LIKE ? OR date LIKE ?)
    """, (today_iso, f"{today_iso}%", f"{today_india}%"))
    data['total_purchase_value'] = cur.fetchone()['total'] or 0
    
    # 2. Storage / New Batches Received Today
    cur.execute("""
        SELECT batch_no, description, received_quantity, uom 
        FROM batches 
        WHERE (date(created_at) = ? OR created_at LIKE ? OR created_at LIKE ?)
    """, (today_iso, f"{today_iso}%", f"{today_india}%"))
    data['new_batches'] = [dict(row) for row in cur.fetchall()]
    
    # 3. Today's Dispatches
    cur.execute("""
        SELECT date, product, quantity, units, department 
        FROM dispatches 
        WHERE (date(date) = ? OR date LIKE ? OR date LIKE ?)
        ORDER BY id DESC
    """, (today_iso, f"{today_iso}%", f"{today_india}%"))
    data['dispatches'] = [dict(row) for row in cur.fetchall()]

    # 4. Today's Transfers
    cur.execute("""
        SELECT date, description, outward, units, department 
        FROM transfers 
        WHERE (date(date) = ? OR date LIKE ? OR date LIKE ?)
        ORDER BY id DESC
    """, (today_iso, f"{today_iso}%", f"{today_india}%"))
    data['transfers'] = [dict(row) for row in cur.fetchall()]
    
    conn.close()
    return data

# -----------------------------
# CLEAN TEXT FOR PDF
# -----------------------------
def clean_for_pdf(text):
    REPLACE = {
        "—": "-", "–": "-",
        "“": '"', "”": '"',
        "‘": "'", "’": "'",
        "•": "-", "●": "-",
        "₹": "Rs."
    }
    for bad, good in REPLACE.items():
        text = text.replace(bad, good)
    return "".join(ch for ch in text if ord(ch) <= 0xFFFF)

# -----------------------------
# AI SUMMARY (PLAIN TEXT)
# -----------------------------
def generate_ai_summary():
    data = get_report_data()
    if not data:
        return "Error: Database not found."

    date_str = datetime.now().strftime("%d %B %Y")
    today = datetime.now().strftime('%d/%m/%Y')
    
    summary = f"BENCHMARK FACTORY - DAILY ACTIVITY REPORT ({date_str})\n"
    summary += "="*60 + "\n\n"

    # --- 1. OVERVIEW ---
    summary += f"ACTIVITY SUMMARY FOR: {today}\n"
    summary += f"• Invoices Recorded: {len(data['invoices'])}\n"
    summary += f"• Total Purchase Value: Rs.{data['total_purchase_value']:.2f}\n"
    summary += f"• Transfers Made: {len(data['transfers'])}\n"
    summary += f"• New Storage Batches: {len(data['new_batches'])}\n"
    summary += f"• Dispatches Made: {len(data['dispatches'])}\n\n"

    # --- 2. TODAY'S INVOICES ---
    summary += "1. TODAY'S INVOICES (Purchases):\n" + "-"*30 + "\n"
    if data['invoices']:
        for inv in data['invoices']:
            summary += f"• Inv: {inv['invoice_no']} | {inv['vendor']} | Rs.{inv['grand_total']}\n"
    else:
        summary += "No invoices recorded today.\n"
    summary += "\n"

    # --- 3. TODAY'S TRANSFERS ---
    summary += "2. TODAY'S MATERIAL TRANSFERS:\n" + "-"*30 + "\n"
    if data['transfers']:
        for t in data['transfers']:
            summary += f"• {t['description']} | Qty: {t['outward']} {t['units']} -> {t['department']}\n"
    else:
        summary += "No transfers recorded today.\n"
    summary += "\n"

    # --- 4. TODAY'S STORAGE (New Batches) ---
    summary += "3. TODAY'S NEW STORAGE BATCHES:\n" + "-"*30 + "\n"
    if data['new_batches']:
        for b in data['new_batches']:
            summary += f"• Batch: {b['batch_no']} | {b['description']} | Received: {b['received_quantity']} {b['uom']}\n"
    else:
        summary += "No new storage batches recorded today.\n"
    summary += "\n"

    # --- 5. TODAY'S DISPATCHES ---
    summary += "4. TODAY'S DISPATCHES:\n" + "-"*30 + "\n"
    if data['dispatches']:
        for d in data['dispatches']:
            summary += f"• {d['product']} | Qty: {d['quantity']} {d['units']} -> {d['department']}\n"
    else:
        summary += "No dispatches recorded today.\n"
    summary += "\n"

    summary += "\n" + "="*60 + "\n"
    summary += "END OF DAILY ACTIVITY REPORT\n"
    
    return summary

# -----------------------------
# CREATE PDF
# -----------------------------
def create_pdf(summary_text):
    REPORT_DIR = os.path.join(BASE_DIR, "reports")
    os.makedirs(REPORT_DIR, exist_ok=True)

    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()

    # Default font
    pdf.set_font("Arial", 'B', size=16)

    # Header
    pdf.set_text_color(12, 41, 75)
    pdf.cell(0, 15, "BenchMark Factory - Daily Report", ln=True, align="C")
    pdf.line(20, 25, 190, 25)
    pdf.ln(10)

    # Content
    pdf.set_text_color(0, 0, 0)
    pdf.set_font("Arial", size=10)
    pdf.multi_cell(0, 6, clean_for_pdf(summary_text))

    filename = os.path.join(
        REPORT_DIR,
        f"Daily_Report_{datetime.now().strftime('%Y%j_%H%M')}.pdf"
    )
    pdf.output(filename)
    return filename

# -----------------------------
# SEND EMAIL
# -----------------------------
def send_report_email(summary):
    sender = "maplepro2323@gmail.com"
    password = "vkah llvc mduj yfze"
    receiver = "24bcs228@kgcas.com,mukunth2307@gmail.com,uthsaharajesh@gmail.com"

    msg = MIMEMultipart()
    msg["Subject"] = f"Today's BenchMark Report - {datetime.now().strftime('%d %b %Y')}"
    msg["From"] = f"BenchMark MMS <{sender}>"
    msg["To"] = receiver

    # Attach Plain Text version
    msg.attach(MIMEText(summary, "plain"))

    # Create and attach PDF
    try:
        pdf_file = create_pdf(summary)
        with open(pdf_file, "rb") as f:
            part = MIMEApplication(f.read(), _subtype="pdf")
            part.add_header(
                "Content-Disposition",
                "attachment",
                filename=os.path.basename(pdf_file)
            )
            msg.attach(part)
    except Exception as e:
        print(f"Warning: Could not attach PDF: {e}")

    # Send
    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(sender, password)
            server.send_message(msg)
        print("[SUCCESS] Email sent successfully (Plain Text + PDF).")
    except Exception as e:
        print(f"[ERROR] Failed to send email: {e}")

# -----------------------------
# ENTRY POINT
# -----------------------------
if __name__ == "__main__":
    print("Generating Today's Report...")
    summary = generate_ai_summary()
    send_report_email(summary)
    print("Task Completed.")