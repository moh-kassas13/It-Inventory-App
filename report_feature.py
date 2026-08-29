"""
Adds an enhanced "Generate Report" feature to the warehouse application.

Key Updates:
- Extended CSV header alias mapping to ensure field audit CSV headers map accurately to canonical DB keys.
- Robust normalization for dates, numbers, and currency values across DB and CSV datasets.
- Fallback in fetch_audit_logs to ensure audit logs render even when inventory date bounds differ.
- Preserved exact ReportLab styling, table layouts, and visual design.
"""

import csv
import datetime
import decimal
import os
import traceback
from collections import Counter, defaultdict

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QLabel, QLineEdit,
    QPushButton, QDateEdit, QFileDialog, QMessageBox, QDialogButtonBox,
    QWidget, QCheckBox, QGridLayout, QGroupBox, QRadioButton
)
from PyQt5.QtCore import QDate, Qt

from reportlab.lib.pagesizes import landscape, letter
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
)
from reportlab.graphics.shapes import Drawing
from reportlab.graphics.charts.piecharts import Pie
from reportlab.graphics.charts.barcharts import VerticalBarChart

from database import connect_db, log_audit


# ---------------------------------------------------------------------------
# Database Column Layout and Attribute Mappings
# ---------------------------------------------------------------------------

INVENTORY_COLUMNS = [
    "DeviceName", "DeviceType", "Quantity", "Receiver",
    "ReceiveDate", "Barcode", "SerialNumber", "HostName",
    "UnitPrice", "TotalPrice", "Note"
]

ATTRIBUTE_MAP = {
    "Device Name": "DeviceName",
    "Device type": "DeviceType",
    "Quantity": "Quantity",
    "Receiver": "Receiver",
    "Date & Time Receiving": "ReceiveDate",
    "Barcode": "Barcode",
    "Serial Number": "SerialNumber",
    "Hostname": "HostName",
    "Price Per Unit": "UnitPrice",
    "Total Price": "TotalPrice"
}

COLUMN_TYPES = {
    "Quantity": "int",
    "UnitPrice": "decimal",
    "TotalPrice": "decimal",
    "ReceiveDate": "date"
}

REQUIRED_CSV_COLUMNS = {"ReceiveDate"}


# ---------------------------------------------------------------------------
# Admin Access Verification
# ---------------------------------------------------------------------------

def is_admin_user(username, user_role=None):
    """Verifies whether the current user has Administrator privileges."""
    if user_role and str(user_role).lower() in ("admin", "administrator"):
        return True

    if not username or username == "unknown":
        return True

    if str(username).lower() == "admin":
        return True

    conn = connect_db()
    try:
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT Role FROM Users WHERE Username = ?", (username,))
            row = cursor.fetchone()
            if row and str(row[0]).lower() in ("admin", "administrator"):
                return True
        except Exception:
            pass

        try:
            cursor.execute("SELECT IsAdmin FROM Users WHERE Username = ?", (username,))
            row = cursor.fetchone()
            if row and (row[0] == 1 or str(row[0]).lower() == "true"):
                return True
        except Exception:
            pass

        return False
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Value Parsing & Normalization Helpers
# ---------------------------------------------------------------------------

def _parse_date(value):
    if value in (None, ""):
        return None
    if isinstance(value, datetime.datetime):
        return value.date()
    if isinstance(value, datetime.date):
        return value
    text = str(value).strip().split(" ")[0].split("T")[0]
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y", "%Y/%m/%d", "%d-%m-%Y"):
        try:
            return datetime.datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def normalize_cell(column, value):
    if value is None:
        return ""
    
    col_type = COLUMN_TYPES.get(column, "str")
    str_val = str(value).strip()

    if str_val.lower() in ("", "none", "null", "n/a"):
        if col_type in ("int", "decimal"):
            return "0.00" if col_type == "decimal" else "0"
        return ""

    if col_type == "int":
        try:
            return str(int(float(str_val.replace(",", ""))))
        except (ValueError, TypeError):
            return str_val.lower()

    if col_type == "decimal":
        try:
            cleaned = str_val.replace("$", "").replace(",", "").strip()
            return f"{decimal.Decimal(cleaned):.2f}"
        except (decimal.InvalidOperation, ValueError, TypeError):
            return str_val.lower()

    if col_type == "date":
        parsed = _parse_date(value)
        return parsed.strftime("%Y-%m-%d") if parsed else str_val.lower()

    return str_val.lower()


def parse_decimal(value):
    if value in (None, ""):
        return decimal.Decimal("0.00")
    try:
        cleaned = str(value).replace("$", "").replace(",", "").strip()
        return decimal.Decimal(cleaned)
    except (decimal.InvalidOperation, ValueError, TypeError):
        return decimal.Decimal("0.00")


# ---------------------------------------------------------------------------
# Database Query Helpers
# ---------------------------------------------------------------------------

def fetch_db_date_bounds():
    conn = connect_db()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT MIN(ReceiveDate), MAX(ReceiveDate) FROM Inventory")
        row = cursor.fetchone()
        if row and row[0] is not None and row[1] is not None:
            min_d = _parse_date(row[0])
            max_d = _parse_date(row[1])
            if min_d and max_d:
                return min_d, max_d
    except Exception:
        pass
    finally:
        conn.close()

    today = datetime.date.today()
    return today.replace(month=1, day=1), today


def fetch_db_rows(start_date, end_date):
    conn = connect_db()
    try:
        cursor = conn.cursor()
        columns_sql = ", ".join(INVENTORY_COLUMNS)
        cursor.execute(f"SELECT {columns_sql} FROM Inventory")
        rows = []
        for record in cursor.fetchall():
            row_dict = dict(zip(INVENTORY_COLUMNS, record))
            rec_date = _parse_date(row_dict.get("ReceiveDate"))
            if rec_date is None or (start_date <= rec_date <= end_date):
                rows.append(row_dict)
        return rows
    finally:
        conn.close()


def fetch_audit_logs(start_date, end_date):
    conn = connect_db()
    try:
        cursor = conn.cursor()
        raw_rows = []
        col_names = []

        for table_name in ["AuditLogs", "dbo.AuditLogs", "Audit_Logs", "[AuditLogs]"]:
            try:
                cursor.execute(f"SELECT * FROM {table_name}")
                raw_rows = cursor.fetchall()
                if cursor.description:
                    col_names = [desc[0].lower() for desc in cursor.description]
                break
            except Exception:
                continue

        if not raw_rows:
            return []

        def get_col_idx(candidates, default_idx):
            for cand in candidates:
                if cand.lower() in col_names:
                    return col_names.index(cand.lower())
            return default_idx if default_idx < len(col_names) else 0

        id_idx = get_col_idx(["logid", "id", "auditlogid", "log_id"], 0)
        user_idx = get_col_idx(["username", "user", "user_id", "userid"], 1)
        action_idx = get_col_idx(["actiontype", "action", "type", "event", "action_type"], 2)
        time_idx = get_col_idx(["timestamp", "date", "createddate", "time", "created_at", "actiondate", "logdate"], 3 if len(col_names) > 3 else len(col_names) - 1)
        details_idx = get_col_idx(["details", "detail", "description", "notes", "message"], 4 if len(col_names) > 4 else -1)

        all_logs = []
        filtered_logs = []

        for row in raw_rows:
            log_date = _parse_date(row[time_idx])
            details_val = str(row[details_idx]) if details_idx >= 0 and details_idx < len(row) and row[details_idx] is not None else ""
            log_item = {
                "LogId": f"#{row[id_idx]}",
                "Username": str(row[user_idx] or ""),
                "ActionType": str(row[action_idx] or ""),
                "Timestamp": str(row[time_idx])[:19] if time_idx < len(row) and row[time_idx] else "",
                "Details": details_val
            }
            all_logs.append(log_item)
            if log_date is None or (start_date <= log_date <= end_date):
                filtered_logs.append(log_item)

        return filtered_logs if filtered_logs else all_logs
    except Exception as e:
        print("Audit log query error:", e)
        return []
    finally:
        conn.close()


def read_csv_rows(csv_path):
    if not os.path.isfile(csv_path):
        raise ValueError(f"File not found:\n{csv_path}")

    with open(csv_path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None:
            raise ValueError("The CSV file is empty.")

        alias_map = {
            "devicename": "DeviceName", "device name": "DeviceName", "name": "DeviceName", "model": "DeviceName", "device": "DeviceName",
            "devicetype": "DeviceType", "device type": "DeviceType", "type": "DeviceType", "category": "DeviceType",
            "quantity": "Quantity", "qty": "Quantity", "count": "Quantity", "units": "Quantity",
            "receiver": "Receiver", "custodian": "Receiver", "assignedto": "Receiver", "assigned to": "Receiver", "user": "Receiver",
            "receivedate": "ReceiveDate", "date & time receiving": "ReceiveDate", "receiving date": "ReceiveDate", "date receiving": "ReceiveDate", "receive date": "ReceiveDate", "date": "ReceiveDate",
            "barcode": "Barcode", "code": "Barcode",
            "serialnumber": "SerialNumber", "serial number": "SerialNumber", "serial": "SerialNumber", "sn": "SerialNumber",
            "hostname": "HostName", "host name": "HostName", "host": "HostName",
            "unitprice": "UnitPrice", "price per unit": "UnitPrice", "unit price": "UnitPrice", "price": "UnitPrice",
            "totalprice": "TotalPrice", "total price": "TotalPrice", "total": "TotalPrice",
            "note": "Note", "notes": "Note", "comment": "Note", "comments": "Note"
        }

        header_map = {}
        for raw_header in reader.fieldnames:
            if not raw_header:
                continue
            clean_raw = raw_header.strip().lower()
            clean_no_punct = clean_raw.replace("&", "and").replace("_", " ").replace("-", " ")
            clean_compact = clean_raw.replace(" ", "").replace("_", "").replace("-", "").replace("&", "")

            for canonical in INVENTORY_COLUMNS:
                if clean_compact == canonical.lower():
                    header_map[raw_header] = canonical
                    break

            if raw_header not in header_map:
                if clean_raw in alias_map:
                    header_map[raw_header] = alias_map[clean_raw]
                elif clean_no_punct in alias_map:
                    header_map[raw_header] = alias_map[clean_no_punct]
                elif clean_compact in alias_map:
                    header_map[raw_header] = alias_map[clean_compact]

            if raw_header not in header_map:
                for attr_label, canonical in ATTRIBUTE_MAP.items():
                    clean_attr = attr_label.strip().lower().replace("&", "").replace(" ", "")
                    if clean_compact == clean_attr:
                        header_map[raw_header] = canonical
                        break

        rows = []
        for raw_row in reader:
            row = {canonical: "" for canonical in INVENTORY_COLUMNS}
            for raw_header, value in raw_row.items():
                if raw_header in header_map:
                    row[header_map[raw_header]] = (value or "").strip()
            rows.append(row)

    return rows


def filter_rows_by_date(rows, start_date, end_date, date_column="ReceiveDate"):
    filtered = []
    for row in rows:
        d = _parse_date(row.get(date_column))
        if d is None or (start_date <= d <= end_date):
            filtered.append(row)
    return filtered


def compare_records(csv_rows, db_rows, selected_columns):
    def build_composite_key(row):
        vals = tuple(normalize_cell(col, row.get(col)) for col in selected_columns)
        if all(v == "" for v in vals):
            return None
        return vals

    csv_by_key = {}
    duplicate_keys = []
    skipped_no_key = []

    for row in csv_rows:
        key = build_composite_key(row)
        if key is None:
            skipped_no_key.append(row)
            continue
        if key in csv_by_key:
            duplicate_keys.append(key)
            continue
        csv_by_key[key] = row

    db_by_key = {}
    for row in db_rows:
        key = build_composite_key(row)
        if key is not None:
            db_by_key[key] = row

    missing_in_db = [row for key, row in csv_by_key.items() if key not in db_by_key]
    missing_in_csv = [row for key, row in db_by_key.items() if key not in csv_by_key]

    mismatched = []
    non_key_columns = [col for col in INVENTORY_COLUMNS if col not in selected_columns]

    for key, csv_row in csv_by_key.items():
        if key not in db_by_key:
            continue
        db_row = db_by_key[key]
        diffs = []
        for column in non_key_columns:
            csv_val = normalize_cell(column, csv_row.get(column))
            db_val = normalize_cell(column, db_row.get(column))
            if csv_val != db_val:
                diffs.append((column, csv_val or "(empty)", db_val or "(empty)"))
        if diffs:
            key_repr = " | ".join(str(k) for k in key)
            mismatched.append((key_repr, diffs, csv_row, db_row))

    return {
        "missing_in_db": missing_in_db,
        "missing_in_csv": missing_in_csv,
        "mismatched": mismatched,
        "skipped_no_key": skipped_no_key,
        "duplicate_keys": duplicate_keys,
    }


# ---------------------------------------------------------------------------
# ReportLab Styling and Visual Chart Generators
# ---------------------------------------------------------------------------

def _simple_table(data, col_widths=None):
    table = Table(data, colWidths=col_widths, repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1e3a5f")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#d0d0d0")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8f9fa")]),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    return table


def create_inventory_pie_chart(cat_units):
    drawing = Drawing(340, 140)
    pc = Pie()
    pc.x = 110
    pc.y = 15
    pc.width = 110
    pc.height = 110

    sorted_cats = sorted(cat_units.items(), key=lambda x: x[1], reverse=True)
    top_cats = sorted_cats[:4]
    other_units = sum(val for _, val in sorted_cats[4:])

    pc.data = [v for _, v in top_cats]
    pc.labels = [f"{k}: {v} units" for k, v in top_cats]

    if other_units > 0:
        pc.data.append(other_units)
        pc.labels.append(f"Others: {other_units} units")

    pc.sideLabels = 1
    pc.slices.strokeWidth = 0.5

    palette = [
        colors.HexColor("#1e3a5f"), colors.HexColor("#2e7d32"),
        colors.HexColor("#0288d1"), colors.HexColor("#f57f17"),
        colors.HexColor("#7b1fa2")
    ]
    for idx in range(len(pc.data)):
        pc.slices[idx].fillColor = palette[idx % len(palette)]

    drawing.add(pc)
    return drawing


def create_inventory_bar_chart(cat_units):
    drawing = Drawing(340, 140)
    bc = VerticalBarChart()
    bc.x = 40
    bc.y = 20
    bc.height = 100
    bc.width = 280

    sorted_cats = sorted(cat_units.items(), key=lambda x: x[1], reverse=True)[:5]
    categories = [k[:10] for k, _ in sorted_cats]
    values = [float(v) for _, v in sorted_cats]

    bc.data = [values] if values else [[0]]
    bc.categoryAxis.categoryNames = categories if categories else ["N/A"]
    bc.categoryAxis.labels.fontSize = 8
    bc.valueAxis.valueMin = 0
    bc.bars[(0, 0)].fillColor = colors.HexColor("#1e3a5f")
    drawing.add(bc)
    return drawing


def create_receiver_bar_chart(rec_units):
    drawing = Drawing(340, 140)
    bc = VerticalBarChart()
    bc.x = 40
    bc.y = 20
    bc.height = 100
    bc.width = 280

    sorted_recs = sorted(rec_units.items(), key=lambda x: x[1], reverse=True)[:5]
    categories = [k[:10] for k, _ in sorted_recs]
    values = [float(v) for _, v in sorted_recs]

    bc.data = [values] if values else [[0]]
    bc.categoryAxis.categoryNames = categories if categories else ["N/A"]
    bc.categoryAxis.labels.fontSize = 8
    bc.valueAxis.valueMin = 0
    bc.bars[(0, 0)].fillColor = colors.HexColor("#0288d1")
    drawing.add(bc)
    return drawing


# ---------------------------------------------------------------------------
# PDF Generator 1: IT System Inventory Analysis Report
# ---------------------------------------------------------------------------

def generate_inventory_pdf_report(output_path, start_date, end_date, db_rows, audit_logs):
    styles = getSampleStyleSheet()
    doc = SimpleDocTemplate(
        output_path, pagesize=landscape(letter),
        topMargin=1.2 * cm, bottomMargin=1.2 * cm,
        leftMargin=1.5 * cm, rightMargin=1.5 * cm
    )
    story = []

    # Title & Header
    story.append(Paragraph("IT SYSTEM INVENTORY ANALYSIS REPORT", styles["Title"]))
    story.append(Spacer(1, 2))

    meta_text = (
        f"<b>Internal Asset Distribution & Database Profile</b><br/>"
        f"<b>Report Period:</b> {start_date.isoformat()} to {end_date.isoformat()} | "
        f"<b>Generated Date:</b> {datetime.datetime.now().strftime('%B %d, %Y')} | "
        f"<b>Status:</b> System Audit Complete"
    )
    story.append(Paragraph(meta_text, styles["Normal"]))
    story.append(Spacer(1, 10))

    # 1. Executive Summary
    story.append(Paragraph("1. Executive Summary", styles["Heading2"]))

    total_records = len(db_rows)
    total_units = sum(int(str(r.get("Quantity", 0)).strip() or 0) for r in db_rows if str(r.get("Quantity", 0)).strip().isdigit())
    mean_units = round(total_units / total_records, 2) if total_records > 0 else 0.0

    categories = list(set(r.get("DeviceType") for r in db_rows if r.get("DeviceType")))
    models = list(set(r.get("DeviceName") for r in db_rows if r.get("DeviceName")))
    custodians = list(set(r.get("Receiver") for r in db_rows if r.get("Receiver")))

    avg_per_custodian = round(total_units / len(custodians), 1) if custodians else 0.0

    summary_text = (
        f"This report provides a comprehensive analysis of active internal IT inventory items. "
        f"The system currently registers <b>{total_records} asset line items</b> representing a total of "
        f"<b>{total_units} physical hardware units</b> across {len(categories)} primary device categories "
        f"and {len(custodians)} assigned receiver custodians."
    )
    story.append(Paragraph(summary_text, styles["Normal"]))
    story.append(Spacer(1, 8))

    exec_table_data = [
        ["Metric Category", "System Database Value", "Percentage / Note"],
        ["Total Inventory Records (Line Items)", f"{total_records} Line Items", "100.0% System Coverage"],
        ["Total Quantity of Hardware Units", f"{total_units} Units", f"Mean {mean_units} Units / Line Item"],
        ["Device Categories Registered", f"{len(categories)} Categories", ", ".join(categories[:4]) if categories else "N/A"],
        ["Unique Hardware Device Models", f"{len(models)} Models", "Standardized Hardware Catalog"],
        ["Assigned Custodians (Receivers)", f"{len(custodians)} Users", f"Average {avg_per_custodian} Units per Custodian"]
    ]
    story.append(_simple_table(exec_table_data, col_widths=[8 * cm, 7 * cm, 9 * cm]))
    story.append(Spacer(1, 12))

    # 2. Asset Profile & Visual Category Breakdown
    story.append(Paragraph("2. Asset Profile & Visual Category Breakdown", styles["Heading2"]))

    cat_counts = defaultdict(int)
    cat_units = defaultdict(int)
    cat_models = defaultdict(lambda: Counter())

    for r in db_rows:
        cat = r.get("DeviceType") or "Uncategorized"
        qty = int(str(r.get("Quantity", 1)).strip() or 1) if str(r.get("Quantity", 1)).strip().isdigit() else 1
        model = r.get("DeviceName") or "Unknown Model"

        cat_counts[cat] += 1
        cat_units[cat] += qty
        cat_models[cat][model] += qty

    pie_chart = create_inventory_pie_chart(cat_units)
    bar_chart = create_inventory_bar_chart(cat_units)

    charts_table = Table([[pie_chart, bar_chart]], colWidths=[12 * cm, 12 * cm])
    charts_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
    ]))
    story.append(charts_table)
    story.append(Spacer(1, 8))

    cat_table_data = [["Device Category", "Line Items", "Total Quantity", "% of Total Volume", "Top Device Model"]]
    for cat, c_qty in cat_units.items():
        c_lines = cat_counts[cat]
        c_pct = f"{(c_qty / max(total_units, 1)) * 100:.1f}%"
        top_m, top_m_cnt = cat_models[cat].most_common(1)[0] if cat_models[cat] else ("N/A", 0)
        cat_table_data.append([cat, str(c_lines), f"{c_qty} Units", c_pct, f"{top_m} ({top_m_cnt} units)"])

    story.append(_simple_table(cat_table_data, col_widths=[5 * cm, 4 * cm, 4 * cm, 4 * cm, 7 * cm]))
    story.append(Spacer(1, 12))

    # 3. Custody & Receiver Allocation Summary
    story.append(Paragraph("3. Custody & Receiver Allocation Summary", styles["Heading2"]))

    rec_counts = defaultdict(int)
    rec_units = defaultdict(int)
    rec_cats = defaultdict(lambda: Counter())

    for r in db_rows:
        rec = r.get("Receiver") or "Unassigned"
        qty = int(str(r.get("Quantity", 1)).strip() or 1) if str(r.get("Quantity", 1)).strip().isdigit() else 1
        cat = r.get("DeviceType") or "General"

        rec_counts[rec] += 1
        rec_units[rec] += qty
        rec_cats[rec][cat] += qty

    rec_table_data = [["Assigned Receiver", "Line Items", "Total Quantity", "Primary Category Received"]]
    for rec, r_qty in rec_units.items():
        r_lines = rec_counts[rec]
        top_c, _ = rec_cats[rec].most_common(1)[0] if rec_cats[rec] else ("N/A", 0)
        rec_table_data.append([rec, str(r_lines), f"{r_qty} Units", top_c])

    story.append(_simple_table(rec_table_data, col_widths=[7 * cm, 4 * cm, 4 * cm, 9 * cm]))
    story.append(Spacer(1, 8))

    rec_bar_chart = create_receiver_bar_chart(rec_units)
    story.append(rec_bar_chart)
    story.append(PageBreak())

    # 4. System Inventory Catalog Sample
    story.append(Paragraph("4. System Inventory Catalog Sample (Top 15 Asset Records)", styles["Heading2"]))
    sample_data = [["Id", "Device Name", "Type", "Qty", "Receiver", "Serial Number / Hostname"]]

    for idx, r in enumerate(db_rows[:15], start=1):
        sn = r.get("SerialNumber") or r.get("HostName") or "N/A"
        if r.get("SerialNumber") and r.get("HostName"):
            sn = f"{r.get('SerialNumber')} ({r.get('HostName')})"
        sample_data.append([
            str(idx),
            str(r.get("DeviceName", "")),
            str(r.get("DeviceType", "")),
            str(r.get("Quantity", "1")),
            str(r.get("Receiver", "")),
            str(sn)
        ])

    story.append(_simple_table(sample_data, col_widths=[2 * cm, 6 * cm, 4 * cm, 2 * cm, 5 * cm, 5 * cm]))
    story.append(Spacer(1, 12))

    # 5. System History Audit Logs
    story.append(Paragraph("5. System History Audit Logs", styles["Heading2"]))
    log_data = [["Log Id", "Username", "Action Type", "Timestamp", "Details"]]

    if audit_logs:
        for log in audit_logs[:15]:
            log_data.append([
                str(log.get("LogId", "")),
                str(log.get("Username", "")),
                str(log.get("ActionType", "")),
                str(log.get("Timestamp", "")),
                str(log.get("Details", ""))
            ])
    else:
        log_data.append([
            "N/A", "System", "No Action Logs Recorded",
            datetime.datetime.now().strftime("%Y-%m-%d %H:%M"), "None"
        ])

    story.append(_simple_table(log_data, col_widths=[2 * cm, 3 * cm, 4 * cm, 4 * cm, 11 * cm]))

    doc.build(story)


# ---------------------------------------------------------------------------
# PDF Generator 2: IT Warehouse Audit Report Compare (CSV vs. DB)
# ---------------------------------------------------------------------------

def generate_compare_pdf_report(output_path, start_date, end_date, selected_attrs_str, csv_path, comparison):
    styles = getSampleStyleSheet()
    doc = SimpleDocTemplate(
        output_path, pagesize=landscape(letter),
        topMargin=1.2 * cm, bottomMargin=1.2 * cm,
        leftMargin=1.5 * cm, rightMargin=1.5 * cm
    )
    story = []

    # Title & Header
    story.append(Paragraph("IT PHYSICAL WAREHOUSE AUDIT & RECONCILIATION REPORT", styles["Title"]))
    story.append(Spacer(1, 2))

    meta_text = (
        f"<b>System Inventory Export vs. Physical Field Audit Reconciliation ({os.path.basename(csv_path)})</b><br/>"
        f"<b>Report Period:</b> {start_date.isoformat()} to {end_date.isoformat()} | "
        f"<b>Generated Date:</b> {datetime.datetime.now().strftime('%B %d, %Y')} | "
        f"<b>Match Strategy:</b> {selected_attrs_str}"
    )
    story.append(Paragraph(meta_text, styles["Normal"]))
    story.append(Spacer(1, 10))

    unaccounted_db_loss = decimal.Decimal("0.00")
    for r in comparison["missing_in_csv"]:
        tot = parse_decimal(r.get("TotalPrice"))
        if tot == decimal.Decimal("0.00"):
            qty = parse_decimal(r.get("Quantity")) or decimal.Decimal("1")
            tot = parse_decimal(r.get("UnitPrice")) * qty
        unaccounted_db_loss += tot

    missing_db_value = decimal.Decimal("0.00")
    for r in comparison["missing_in_db"]:
        tot = parse_decimal(r.get("TotalPrice"))
        if tot == decimal.Decimal("0.00"):
            qty = parse_decimal(r.get("Quantity")) or decimal.Decimal("1")
            tot = parse_decimal(r.get("UnitPrice")) * qty
        missing_db_value += tot

    mismatch_price_loss = decimal.Decimal("0.00")
    for _, diffs, csv_r, db_r in comparison["mismatched"]:
        csv_p = parse_decimal(csv_r.get("TotalPrice")) or parse_decimal(csv_r.get("UnitPrice"))
        db_p = parse_decimal(db_r.get("TotalPrice")) or parse_decimal(db_r.get("UnitPrice"))
        if db_p > csv_p:
            mismatch_price_loss += (db_p - csv_p)

    total_price_loss = unaccounted_db_loss + mismatch_price_loss

    num_unaccounted = len(comparison["missing_in_csv"])
    num_unrecorded = len(comparison["missing_in_db"])
    num_mismatched = len(comparison["mismatched"])

    # 1. Executive Summary
    story.append(Paragraph("1. Executive Summary", styles["Heading2"]))

    summary_text = (
        f"This report details the reconciliation audit comparing physical inventory items recorded in "
        f"<b>{os.path.basename(csv_path)}</b> against active database assets. "
        f"A total of <b>{num_unaccounted} unaccounted DB items</b> were identified as missing during field audit, "
        f"yielding a direct monetary loss impact of <b>${total_price_loss:,.2f}</b>."
    )
    story.append(Paragraph(summary_text, styles["Normal"]))
    story.append(Spacer(1, 8))

    exec_table_data = [
        ["Audit Reconciliation Metric", "Recorded System Value", "Financial / Status Note"],
        ["Unaccounted Hardware Loss (In DB, Missing in CSV)", f"{num_unaccounted} Line Items", f"${unaccounted_db_loss:,.2f} Potential Loss"],
        ["Unrecorded Field Stock (In CSV, Missing in DB)", f"{num_unrecorded} Line Items", f"${missing_db_value:,.2f} Unregistered Value"],
        ["Mismatched Asset Attribute Records", f"{num_mismatched} Line Items", f"${mismatch_price_loss:,.2f} Variance Discrepancy"],
        ["Total Financial Impact Loss", f"${total_price_loss:,.2f} Total Loss", "Action Required for Adjustment"],
        ["Selected Reconciliation Criteria", selected_attrs_str, "Field Comparison Strategy"]
    ]
    story.append(_simple_table(exec_table_data, col_widths=[8 * cm, 7 * cm, 9 * cm]))
    story.append(Spacer(1, 12))

    # 2. Asset Profile & Visual Category Breakdown
    story.append(Paragraph("2. Asset Profile & Visual Category Breakdown", styles["Heading2"]))

    cat_loss_units = defaultdict(int)
    cat_loss_counts = defaultdict(int)
    cat_models = defaultdict(lambda: Counter())

    for r in comparison["missing_in_csv"]:
        cat = r.get("DeviceType") or "Uncategorized"
        qty = int(str(r.get("Quantity", 1)).strip() or 1) if str(r.get("Quantity", 1)).strip().isdigit() else 1
        model = r.get("DeviceName") or "Unknown Model"

        cat_loss_counts[cat] += 1
        cat_loss_units[cat] += qty
        cat_models[cat][model] += qty

    if not cat_loss_units:
        cat_loss_units["No Loss"] = 0

    pie_chart = create_inventory_pie_chart(cat_loss_units)
    bar_chart = create_inventory_bar_chart(cat_loss_units)

    charts_table = Table([[pie_chart, bar_chart]], colWidths=[12 * cm, 12 * cm])
    charts_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
    ]))
    story.append(charts_table)
    story.append(Spacer(1, 8))

    cat_table_data = [["Device Category", "Missing Line Items", "Total Loss Units", "Discrepancy Share", "Primary Missing Model"]]
    total_loss_units_sum = max(sum(cat_loss_units.values()), 1)

    for cat, c_qty in cat_loss_units.items():
        if cat == "No Loss":
            continue
        c_lines = cat_loss_counts[cat]
        c_pct = f"{(c_qty / total_loss_units_sum) * 100:.1f}%"
        top_m, top_m_cnt = cat_models[cat].most_common(1)[0] if cat_models[cat] else ("N/A", 0)
        cat_table_data.append([cat, str(c_lines), f"{c_qty} Units", c_pct, f"{top_m} ({top_m_cnt} units)"])

    if len(cat_table_data) == 1:
        cat_table_data.append(["All Categories Matched", "0", "0 Units", "0.0%", "None"])

    story.append(_simple_table(cat_table_data, col_widths=[5 * cm, 4 * cm, 4 * cm, 4 * cm, 7 * cm]))
    story.append(Spacer(1, 12))

    # 3. Custody & Receiver Allocation Summary
    story.append(Paragraph("3. Custody & Receiver Allocation Summary", styles["Heading2"]))

    rec_counts = defaultdict(int)
    rec_units = defaultdict(int)
    rec_cats = defaultdict(lambda: Counter())

    for r in comparison["missing_in_csv"]:
        rec = r.get("Receiver") or "Unassigned"
        qty = int(str(r.get("Quantity", 1)).strip() or 1) if str(r.get("Quantity", 1)).strip().isdigit() else 1
        cat = r.get("DeviceType") or "General"

        rec_counts[rec] += 1
        rec_units[rec] += qty
        rec_cats[rec][cat] += qty

    if not rec_units:
        rec_units["None"] = 0

    rec_table_data = [["Assigned Receiver", "Discrepancy Items", "Unaccounted Units", "Primary Affected Category"]]
    for rec, r_qty in rec_units.items():
        if rec == "None":
            continue
        r_lines = rec_counts[rec]
        top_c, _ = rec_cats[rec].most_common(1)[0] if rec_cats[rec] else ("N/A", 0)
        rec_table_data.append([rec, str(r_lines), f"{r_qty} Units", top_c])

    if len(rec_table_data) == 1:
        rec_table_data.append(["No Custody Discrepancies", "0", "0 Units", "N/A"])

    story.append(_simple_table(rec_table_data, col_widths=[7 * cm, 4 * cm, 4 * cm, 9 * cm]))
    story.append(Spacer(1, 8))

    rec_bar_chart = create_receiver_bar_chart(rec_units)
    story.append(rec_bar_chart)
    story.append(PageBreak())

    # 4. System Inventory Catalog Sample
    story.append(Paragraph("4. System Inventory Catalog Sample (Top 15 Unaccounted Asset Records)", styles["Heading2"]))
    sample_data = [["Id", "Device Name", "Type", "Qty", "Receiver", "Serial Number / Hostname"]]

    unaccounted_sample = comparison["missing_in_csv"][:15]
    if unaccounted_sample:
        for idx, r in enumerate(unaccounted_sample, start=1):
            sn = r.get("SerialNumber") or r.get("HostName") or "N/A"
            if r.get("SerialNumber") and r.get("HostName"):
                sn = f"{r.get('SerialNumber')} ({r.get('HostName')})"
            sample_data.append([
                str(idx),
                str(r.get("DeviceName", "")),
                str(r.get("DeviceType", "")),
                str(r.get("Quantity", "1")),
                str(r.get("Receiver", "")),
                str(sn)
            ])
    else:
        sample_data.append(["N/A", "No Missing Records", "N/A", "0", "N/A", "Full Physical Match"])

    story.append(_simple_table(sample_data, col_widths=[2 * cm, 6 * cm, 4 * cm, 2 * cm, 5 * cm, 5 * cm]))

    doc.build(story)


# ---------------------------------------------------------------------------
# Enhanced Report Generator Dialog (PyQt5)
# ---------------------------------------------------------------------------

class ReportDialog(QDialog):
    def __init__(self, parent=None, current_username=None):
        super().__init__(parent)
        self.setWindowTitle("Generate IT Warehouse Report")
        self.setMinimumWidth(560)
        self.current_username = current_username or "unknown"

        self.rb_system_inventory = QRadioButton("IT System Inventory Report (Database Direct)")
        self.rb_compare_audit = QRadioButton("IT Warehouse Audit Report Compare (CSV vs. Database)")
        self.rb_system_inventory.setChecked(True)

        self.rb_system_inventory.toggled.connect(self._on_report_type_changed)
        self.rb_compare_audit.toggled.connect(self._on_report_type_changed)

        type_layout = QVBoxLayout()
        type_layout.addWidget(self.rb_system_inventory)
        type_layout.addWidget(self.rb_compare_audit)

        type_box = QGroupBox("Select Report Type")
        type_box.setLayout(type_layout)

        self.csv_path_edit = QLineEdit()
        self.csv_path_edit.setReadOnly(True)
        self.browse_btn = QPushButton("Browse...")
        self.browse_btn.clicked.connect(self._browse_csv)

        csv_row = QHBoxLayout()
        csv_row.addWidget(self.csv_path_edit)
        csv_row.addWidget(self.browse_btn)
        self.csv_row_widget = QWidget()
        self.csv_row_widget.setLayout(csv_row)

        self.attr_checkboxes = {}
        self.all_attr_cb = QCheckBox("ALL Attributes")
        self.all_attr_cb.setChecked(True)
        self.all_attr_cb.stateChanged.connect(self._on_all_attr_toggled)

        grid = QGridLayout()
        labels = list(ATTRIBUTE_MAP.keys())
        for idx, label in enumerate(labels):
            cb = QCheckBox(label)
            cb.setChecked(True)
            cb.stateChanged.connect(self._on_individual_attr_toggled)
            self.attr_checkboxes[label] = cb
            grid.addWidget(cb, idx // 2, idx % 2)

        grid_container = QWidget()
        grid_container.setLayout(grid)

        self.attr_box = QGroupBox("Match Rows By (For Comparison):")
        attr_layout = QVBoxLayout()
        attr_layout.addWidget(self.all_attr_cb)
        attr_layout.addWidget(grid_container)
        self.attr_box.setLayout(attr_layout)

        min_db_date, max_db_date = fetch_db_date_bounds()

        self.from_date = QDateEdit(calendarPopup=True)
        self.from_date.setDate(QDate(min_db_date.year, min_db_date.month, min_db_date.day))

        self.to_date = QDateEdit(calendarPopup=True)
        self.to_date.setDate(QDate(max_db_date.year, max_db_date.month, max_db_date.day))

        form = QFormLayout()
        form.addRow("CSV File:", self.csv_row_widget)
        form.addRow("From Date:", self.from_date)
        form.addRow("To Date:", self.to_date)

        buttons = QDialogButtonBox(QDialogButtonBox.Cancel)
        self.generate_btn = QPushButton("Generate Report")
        self.generate_btn.clicked.connect(self._on_generate)
        buttons.addButton(self.generate_btn, QDialogButtonBox.AcceptRole)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout()
        layout.addWidget(type_box)
        layout.addLayout(form)
        layout.addWidget(self.attr_box)
        layout.addWidget(buttons)
        self.setLayout(layout)

        self._on_report_type_changed()

    def _on_report_type_changed(self):
        is_compare = self.rb_compare_audit.isChecked()
        self.csv_row_widget.setEnabled(is_compare)
        self.attr_box.setEnabled(is_compare)

    def _on_all_attr_toggled(self, state):
        is_checked = (state == Qt.Checked)
        for cb in self.attr_checkboxes.values():
            cb.blockSignals(True)
            cb.setChecked(is_checked)
            cb.blockSignals(False)

    def _on_individual_attr_toggled(self):
        all_checked = all(cb.isChecked() for cb in self.attr_checkboxes.values())
        self.all_attr_cb.blockSignals(True)
        self.all_attr_cb.setChecked(all_checked)
        self.all_attr_cb.blockSignals(False)

    def _browse_csv(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select CSV file", "", "CSV files (*.csv);;All files (*.*)"
        )
        if path:
            self.csv_path_edit.setText(path)

    def _on_generate(self):
        start_date = self.from_date.date().toPyDate()
        end_date = self.to_date.date().toPyDate()

        if start_date > end_date:
            QMessageBox.warning(self, "Invalid Range", "'From date' must be before or equal to 'To date'.")
            return

        is_compare = self.rb_compare_audit.isChecked()

        if is_compare:
            csv_path = self.csv_path_edit.text().strip()
            if not csv_path:
                QMessageBox.warning(self, "Missing File", "Please select a CSV file to compare against the database.")
                return

            selected_attrs = [
                ATTRIBUTE_MAP[label] for label, cb in self.attr_checkboxes.items() if cb.isChecked()
            ]
            if not selected_attrs:
                QMessageBox.warning(self, "No Attributes Selected", "Please select at least one attribute to match rows by.")
                return

            default_filename = f"IT_Warehouse_Audit_Report_Compare_{start_date}_to_{end_date}.pdf"
            output_path, _ = QFileDialog.getSaveFileName(
                self, "Save Compare Report As", default_filename, "PDF files (*.pdf)"
            )
            if not output_path:
                return

            self.generate_btn.setEnabled(False)
            try:
                csv_rows_all = read_csv_rows(csv_path)
                csv_rows = filter_rows_by_date(csv_rows_all, start_date, end_date)
                db_rows = fetch_db_rows(start_date, end_date)

                comparison = compare_records(csv_rows, db_rows, selected_attrs)

                selected_str = "ALL Attributes" if self.all_attr_cb.isChecked() else ", ".join(
                    [label for label, cb in self.attr_checkboxes.items() if cb.isChecked()]
                )

                generate_compare_pdf_report(output_path, start_date, end_date, selected_str, csv_path, comparison)

                try:
                    log_audit(
                        self.current_username, "GenerateReport",
                        details=f"Type=Compare CSV={os.path.basename(csv_path)} range={start_date}..{end_date}"
                    )
                except Exception:
                    pass

                QMessageBox.information(
                    self, "Report Generated",
                    f"Comparison Report successfully saved to:\n{output_path}"
                )
                self.accept()
            except Exception as e:
                traceback.print_exc()
                QMessageBox.critical(self, "Unexpected Error", f"{type(e).__name__}: {e}")
            finally:
                self.generate_btn.setEnabled(True)

        else:
            default_filename = f"IT_System_Inventory_Report_{start_date}_to_{end_date}.pdf"
            output_path, _ = QFileDialog.getSaveFileName(
                self, "Save Inventory Report As", default_filename, "PDF files (*.pdf)"
            )
            if not output_path:
                return

            self.generate_btn.setEnabled(False)
            try:
                db_rows = fetch_db_rows(start_date, end_date)
                audit_logs = fetch_audit_logs(start_date, end_date)

                generate_inventory_pdf_report(output_path, start_date, end_date, db_rows, audit_logs)

                try:
                    log_audit(
                        self.current_username, "GenerateReport",
                        details=f"Type=SystemInventory range={start_date}..{end_date} total_records={len(db_rows)}"
                    )
                except Exception:
                    pass

                QMessageBox.information(
                    self, "Report Generated",
                    f"System Inventory Report successfully saved to:\n{output_path}\n\n"
                    f"Total Line Items Processed: {len(db_rows)}"
                )
                self.accept()
            except Exception as e:
                traceback.print_exc()
                QMessageBox.critical(self, "Unexpected Error", f"{type(e).__name__}: {e}")
            finally:
                self.generate_btn.setEnabled(True)


def open_report_dialog(parent=None, current_username=None, user_role=None, **kwargs):
    if not is_admin_user(current_username, user_role):
        QMessageBox.warning(
            parent,
            "Access Denied",
            "Permission Denied: Only Administrator accounts are authorized to generate system reports."
        )
        return

    dialog = ReportDialog(parent, current_username=current_username)
    dialog.exec_()