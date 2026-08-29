import re
import cv2
import numpy as np
from PIL import Image
import io
from datetime import datetime

try:
    from rapidocr_onnxruntime import RapidOCR
    ocr_engine = RapidOCR()
except Exception as e:
    ocr_engine = None
    print(f"RapidOCR initialization warning: {e}")

try:
    import pypdfium2 as pdfium
except Exception:
    pdfium = None

GST_REGEX = r"\b\d{2}[A-Z]{5}\d{4}[A-Z]{1}[A-Z\d]{1}[Z]{1}[A-Z\d]{1}\b"

def preprocess_bytes(file_bytes: bytes) -> np.ndarray:
    """Preprocess uploaded image or PDF bytes into an optimized grayscale image."""
    # Check if PDF
    if file_bytes.startswith(b"%PDF") and pdfium:
        try:
            pdf = pdfium.PdfDocument(file_bytes)
            page = pdf[0]
            pil_img = page.render(scale=2).to_pil()
            rgb_arr = np.array(pil_img)
            gray = cv2.cvtColor(rgb_arr, cv2.COLOR_RGB2GRAY)
            return gray
        except Exception as e:
            print(f"PDF rendering error: {e}")

    nparr = np.frombuffer(file_bytes, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError("Could not decode image or PDF.")
    
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    h, w = gray.shape
    if w > 2000:
        scale = 2000.0 / w
        gray = cv2.resize(gray, (2000, int(h * scale)), interpolation=cv2.INTER_AREA)
    return gray

def parse_date(raw_str: str) -> str:
    """Normalize date strings like '4-Aug-26', '28/08/2026', '2026-08-04' to YYYY-MM-DD."""
    if not raw_str:
        return ""
    cleaned = raw_str.strip().replace(",", " ").replace(".", "-").replace("/", "-")
    # Clean words around it
    cleaned = re.sub(r"^(dated|date|on)[:\s]*", "", cleaned, flags=re.IGNORECASE).strip()
    
    formats = [
        "%d-%b-%y", "%d-%b-%Y", "%d-%B-%y", "%d-%B-%Y",
        "%d-%m-%Y", "%d-%m-%y",
        "%Y-%m-%d", "%Y-%b-%d",
        "%d %b %Y", "%d %b %y", "%d %B %Y", "%d %B %y"
    ]
    for fmt in formats:
        try:
            return datetime.strptime(cleaned, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return ""

def clean_amount(val_str: str) -> float:
    """Extract float amount from formatted string like '2,59,350.00' or '₹ 2,72,317.50'."""
    if not val_str:
        return 0.0
    # Remove currency symbols, commas, spaces
    cleaned = val_str.replace("₹", "").replace("Rs.", "").replace("Rs", "").replace(",", "").strip()
    match = re.search(r"[-+]?\d+(?:\.\d+)?", cleaned)
    if match:
        try:
            return float(match.group(0))
        except ValueError:
            return 0.0
    return 0.0

def extract_invoice_data_from_bytes(file_bytes: bytes) -> dict:
    """Run OCR and layout extraction to parse Indian GST invoices."""
    if ocr_engine is None:
        return {"success": False, "error": "OCR engine not initialized"}
    
    gray_img = preprocess_bytes(file_bytes)
    results, _ = ocr_engine(gray_img)
    
    if not results:
        return {
            "success": True,
            "data": {
                "invoice_no": "",
                "date": datetime.now().strftime("%Y-%m-%d"),
                "vendor": "",
                "gst_number": "",
                "subtotal": "0.00",
                "cgst_percent": "0.00",
                "sgst_percent": "0.00",
                "total_gst": "0.00",
                "total_igst": "0.00",
                "round_off": "0.00",
                "grand_total": "0.00",
                "items": [],
                "raw_lines": []
            }
        }

    # Bounding-box tokens
    tokens = []
    for item in results:
        box = item[0]
        text = str(item[1]).strip()
        score = float(item[2])
        if text:
            avg_y = sum(pt[1] for pt in box) / 4.0
            avg_x = sum(pt[0] for pt in box) / 4.0
            min_x = min(pt[0] for pt in box)
            max_x = max(pt[0] for pt in box)
            min_y = min(pt[1] for pt in box)
            max_y = max(pt[1] for pt in box)
            tokens.append({
                "text": text,
                "x": avg_x, "y": avg_y,
                "min_x": min_x, "max_x": max_x,
                "min_y": min_y, "max_y": max_y,
                "score": score
            })

    # Sort tokens top-to-bottom, left-to-right
    tokens.sort(key=lambda t: (t["y"], t["x"]))
    all_texts = [t["text"] for t in tokens]
    full_text = "\n".join(all_texts)

    # -------------------------------------------------------------
    # 1. GST Numbers (Seller vs Buyer)
    # -------------------------------------------------------------
    all_gsts = re.findall(GST_REGEX, full_text, re.IGNORECASE)
    seller_gst = all_gsts[0].upper() if all_gsts else ""

    # -------------------------------------------------------------
    # 2. Vendor / Seller Name
    # -------------------------------------------------------------
    vendor_name = ""
    # Check bottom signature first: 'for Rajan Spices'
    for t in tokens:
        m = re.search(r"for\s+([A-Za-z0-9\s&]+)", t["text"], re.IGNORECASE)
        if m:
            cand = m.group(1).strip()
            if len(cand) > 3 and not any(kw in cand.lower() for kw in ["consignee", "buyer", "authorised", "signature"]):
                vendor_name = cand
                break

    if not vendor_name:
        # Top-left box before 'Consignee' or 'Buyer'
        ignore_kws = ["tax invoice", "invoice", "gstin", "state name", "e-way", "delivery", "dated", "original", "bill no"]
        for t in tokens:
            if t["y"] < 300 and t["x"] < 500:
                tl = t["text"].lower()
                if "consignee" in tl or "buyer" in tl:
                    break
                if len(t["text"]) > 3 and not any(kw in tl for kw in ignore_kws) and not re.search(GST_REGEX, t["text"]):
                    # Avoid address lines starting with digits like 'MP 6/75' or '4/921'
                    if not re.match(r"^[\d\/\#\-\s,]+$", t["text"]) and not re.match(r"^(MP|No|Plot|Door|Flat)\s*\d+", t["text"], re.IGNORECASE):
                        cleaned = re.sub(r"^(M\/[Ss]|Messrs\.?|M\/s\.?)\s*", "", t["text"], flags=re.IGNORECASE).strip()
                        if len(cleaned) > 2:
                            vendor_name = cleaned
                            break

    # -------------------------------------------------------------
    # 3. Invoice Number & Date (Spatial Proximity)
    # -------------------------------------------------------------
    invoice_no = ""
    invoice_date = ""

    # Search for "Invoice No." label and find the token right below it (same column X ± 100, Y + 15 to 60)
    for idx, t in enumerate(tokens):
        txt = t["text"]
        if re.search(r"Invoice\s*No", txt, re.IGNORECASE) and not re.search(r"e-Way", txt, re.IGNORECASE):
            # Check same token if it has value e.g. "Invoice No: 16"
            m = re.search(r"Invoice\s*No[\.\s:]+([A-Za-z0-9\/\-_]+)", txt, re.IGNORECASE)
            if m and not m.group(1).lower() in ["e-way", "dated", "no", "date"]:
                invoice_no = m.group(1).strip()
                break
            # Find below token
            for below in tokens:
                if 10 < (below["y"] - t["y"]) < 70 and abs(below["x"] - t["x"]) < 100:
                    cand = below["text"].strip()
                    if cand and not any(kw in cand.lower() for kw in ["e-way", "dated", "delivery", "invoice", "date", "reference"]):
                        invoice_no = cand
                        break
            if invoice_no:
                break

    if not invoice_no:
        # Fallback regex
        m = re.search(r"\b(INV[\-\/][A-Za-z0-9\-\/]+)\b", full_text, re.IGNORECASE)
        if m:
            invoice_no = m.group(1)

    # Search for Date
    for t in tokens:
        txt = t["text"]
        if re.search(r"Dated|Date", txt, re.IGNORECASE):
            # Direct date in same string?
            p = parse_date(txt)
            if p:
                invoice_date = p
                break
            # Token right below or next to 'Dated'
            for below in tokens:
                if 10 < (below["y"] - t["y"]) < 70 and abs(below["x"] - t["x"]) < 120:
                    p = parse_date(below["text"])
                    if p:
                        invoice_date = p
                        break
            if invoice_date:
                break

    if not invoice_date:
        for t in tokens:
            p = parse_date(t["text"])
            if p:
                invoice_date = p
                break

    if not invoice_date:
        invoice_date = datetime.now().strftime("%Y-%m-%d")

    # -------------------------------------------------------------
    # 4. Financial Totals & Tax Amounts (Indian Number Comma Aware)
    # -------------------------------------------------------------
    subtotal = 0.0
    cgst_val = 0.0
    sgst_val = 0.0
    igst_val = 0.0
    grand_total = 0.0
    round_off = 0.0

    # Pattern matching with Indian format (e.g. 2,59,350.00 or 12,967.50)
    for idx, t in enumerate(tokens):
        txt = t["text"].lower()

        # IGST
        if "igst" in txt:
            # Check amounts in this token or nearby tokens
            amounts = re.findall(r"[\d,]+\.\d{2}", t["text"])
            if amounts:
                igst_val = clean_amount(amounts[-1])
            else:
                # Look on same Y level or next token
                for near in tokens:
                    if abs(near["y"] - t["y"]) < 20 and near["x"] > t["x"]:
                        near_amounts = re.findall(r"[\d,]+\.\d{2}", near["text"])
                        if near_amounts:
                            igst_val = clean_amount(near_amounts[-1])
                            break

        # CGST
        if "cgst" in txt:
            amounts = re.findall(r"[\d,]+\.\d{2}", t["text"])
            if amounts:
                cgst_val = clean_amount(amounts[-1])
            else:
                for near in tokens:
                    if abs(near["y"] - t["y"]) < 20 and near["x"] > t["x"]:
                        near_amounts = re.findall(r"[\d,]+\.\d{2}", near["text"])
                        if near_amounts:
                            cgst_val = clean_amount(near_amounts[-1])
                            break

        # SGST / UTGST
        if "sgst" in txt or "utgst" in txt:
            amounts = re.findall(r"[\d,]+\.\d{2}", t["text"])
            if amounts:
                sgst_val = clean_amount(amounts[-1])
            else:
                for near in tokens:
                    if abs(near["y"] - t["y"]) < 20 and near["x"] > t["x"]:
                        near_amounts = re.findall(r"[\d,]+\.\d{2}", near["text"])
                        if near_amounts:
                            sgst_val = clean_amount(near_amounts[-1])
                            break

        # Taxable Value / Subtotal
        if any(k in txt for k in ["taxable value", "taxable amt", "subtotal", "sub total", "total taxable"]):
            amounts = re.findall(r"[\d,]+\.\d{2}", t["text"])
            if amounts:
                subtotal = clean_amount(amounts[-1])
            else:
                for near in tokens:
                    if (abs(near["y"] - t["y"]) < 30 and near["x"] > t["x"]) or (10 < near["y"] - t["y"] < 40 and abs(near["x"] - t["x"]) < 50):
                        near_amounts = re.findall(r"[\d,]+\.\d{2}", near["text"])
                        if near_amounts:
                            subtotal = clean_amount(near_amounts[-1])
                            break

        # Grand Total / Net Total
        if txt == "total" or "grand total" in txt or "invoice total" in txt or "total amount" in txt:
            # Find largest amount near this line
            for near in tokens:
                if abs(near["y"] - t["y"]) < 25 and near["x"] > t["x"]:
                    near_amounts = re.findall(r"[\d,]+\.\d{2}", near["text"])
                    if near_amounts:
                        amt = clean_amount(near_amounts[-1])
                        if amt > grand_total:
                            grand_total = amt

    # Find highest amount at bottom if grand_total not captured
    all_bottom_amounts = []
    for t in tokens[len(tokens)//3:]:
        matches = re.findall(r"[\d,]+\.\d{2}", t["text"])
        for m in matches:
            val = clean_amount(m)
            if val > 100: # Ignore tiny values like quantities
                all_bottom_amounts.append(val)
    if all_bottom_amounts:
        max_bottom = max(all_bottom_amounts)
        if max_bottom > grand_total:
            grand_total = max_bottom

    # Subtotal calculation fallback
    total_tax = cgst_val + sgst_val + igst_val
    if subtotal == 0.0 and grand_total > 0:
        if total_tax > 0 and grand_total > total_tax:
            subtotal = grand_total - total_tax - round_off
        else:
            subtotal = grand_total

    # -------------------------------------------------------------
    # 5. Extract Line Items (e.g. Cardamom, 91.00 kgs, 2850.00, 259350.00)
    # -------------------------------------------------------------
    items = []
    ignore_item_names = [
        "total", "igst", "cgst", "sgst", "amount", "chargeable", "hsn",
        "description", "goods", "no.", "sl", "rate", "per", "quantity",
        "e.&0.e", "inr", "declaration"
    ]
    for t in tokens:
        if 650 < t["y"] < 1050 and t["x"] < 450:
            name = t["text"].strip()
            name_lower = name.lower()
            if len(name) > 2 and not any(kw == name_lower or kw in name_lower.split() for kw in ignore_item_names):
                item_qty = 1.0
                item_unit = "kg"
                item_rate = 0.0
                item_amt = 0.0
                item_igst_pct = 0.0
                item_gst_pct = 0.0

                for near in tokens:
                    if abs(near["y"] - t["y"]) < 25:
                        x = near["x"]
                        ntxt = near["text"].lower()
                        if "kg" in ntxt: item_unit = "kg"
                        elif "pcs" in ntxt: item_unit = "pcs"
                        elif "box" in ntxt: item_unit = "box"
                        elif "tin" in ntxt: item_unit = "tin"
                        elif "litre" in ntxt or "ltr" in ntxt: item_unit = "litre"

                        amts = re.findall(r"[\d,]+(?:\.\d+)?", near["text"])
                        if amts:
                            val = clean_amount(amts[-1])
                            if 600 <= x <= 720 and val < 10000:
                                item_qty = val
                            elif 730 <= x <= 850 and val > 0:
                                item_rate = val
                            elif x >= 870 and val > 0:
                                item_amt = val

                        # ✅ Detect IGST % column (usually between x=500–600 or labeled)
                        # Look for a small number like 5, 12, 18, 28 near the item row
                        if re.search(r"\bigst\b", ntxt):
                            pct_match = re.search(r"(\d+(?:\.\d+)?)\s*%?", near["text"])
                            if pct_match:
                                item_igst_pct = float(pct_match.group(1))
                        elif 480 <= x <= 620 and not item_igst_pct:
                            # Tax % column typically sits in this X range
                            pct_match = re.findall(r"^(\d{1,2}(?:\.\d+)?)$", near["text"].strip())
                            if pct_match:
                                pct_val = float(pct_match[0])
                                # Valid GST slabs: 0, 0.1, 0.25, 1, 1.5, 3, 5, 7.5, 12, 18, 28
                                valid_slabs = {0, 0.1, 0.25, 1, 1.5, 3, 5, 7.5, 12, 18, 28}
                                if pct_val in valid_slabs or pct_val == 0:
                                    item_igst_pct = pct_val

                if item_amt > 0 or item_rate > 0:
                    items.append({
                        "name": name,
                        "quantity": item_qty,
                        "unit": item_unit,
                        "unit_price": item_rate if item_rate > 0 else (round(item_amt / item_qty, 2) if item_qty else 0),
                        "amount": item_amt,
                        "igst_percent": item_igst_pct,   # ✅ Per-item IGST %
                        "gst_percent": item_gst_pct       # ✅ Per-item GST %
                    })

    total_gst = cgst_val + sgst_val

    return {
        "success": True,
        "data": {
            "invoice_no": invoice_no,
            "date": invoice_date,
            "vendor": vendor_name,
            "gst_number": seller_gst,
            "subtotal": f"{subtotal:.2f}",
            "cgst_percent": f"{cgst_val:.2f}",
            "sgst_percent": f"{sgst_val:.2f}",
            "total_gst": f"{total_gst:.2f}",
            "total_igst": f"{igst_val:.2f}",
            "round_off": f"{round_off:.2f}",
            "grand_total": f"{grand_total:.2f}",
            "items": items,
            "raw_lines": all_texts
        }
    }
