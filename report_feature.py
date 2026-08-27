"""
report_feature.py

Adds an enhanced "Generate Report" feature to the warehouse application.

Key Features:
- Multi-attribute composite matching with checkboxes (default: ALL Attributes).
- Auto-detected Date Range based on oldest and newest DB ReceiveDate records.
- Automated report naming: IT-Warehouse-num.pdf.
- Rich PDF report featuring all standard IT Warehouse Report sections, visual charts,
  and a Price Loss & Financial Discrepancy breakdown.
"""

import csv
import datetime
import decimal
import os
import traceback

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QLabel, QLineEdit,
    QPushButton, QDateEdit, QFileDialog, QMessageBox, QDialogButtonBox,
    QWidget, QCheckBox, QGridLayout, QGroupBox, QScrollArea
)
from PyQt5.QtCore import QDate, Qt

from reportlab.lib.pagesizes import landscape, letter
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, KeepTogether
)
from reportlab.graphics.shapes import Drawing, Rect, String, Group
from reportlab.graphics.charts.piecharts import Pie
from reportlab.graphics.charts.barcharts import VerticalBarChart

from database import connect_db, log_audit


# ---------------------------------------------------------------------------
# Database column layout and mapping
# ---------------------------------------------------------------------------

INVENTORY_COLUMNS = [
    "DeviceName", "DeviceType", "Quantity", "Sender", "Receiver",
    "ReceiveDate", "WarrantyDate", "Barcode", "TicketNumber", "FromWhere",
    "SerialNumber", "HostName", "UnitPrice", "TotalPrice", "Note",
]

# UI Label to Column Name mapping
ATTRIBUTE_MAP = {
    "Device Name": "DeviceName",
    "Device type": "DeviceType",
    "Quantity": "Quantity",
    "Sender": "Sender",
    "Receiver": "Receiver",
    "Date & Time Receiving": "ReceiveDate",
    "Warranty Date": "WarrantyDate",
    "Barcode": "Barcode",
    "Ticket Number": "TicketNumber",
    "From Where": "FromWhere",
    "Serial Numbre": "SerialNumber",
    "Hostname": "HostName",
    "Price Per Unit": "UnitPrice",
    "Total Price": "TotalPrice"
}

COLUMN_TYPES = {
    "Quantity": "int",
    "UnitPrice": "decimal",
    "TotalPrice": "decimal",
    "ReceiveDate": "date",
    "WarrantyDate": "date",
}

REQUIRED_CSV_COLUMNS = {"ReceiveDate"}


# ---------------------------------------------------------------------------
# Value parsing & normalization helpers
# ---------------------------------------------------------------------------

def _parse_date(value):
    """Best-effort parse of a date coming from either DB or CSV cell."""
    if value in (None, ""):
        return None
    if isinstance(value, (datetime.date, datetime.datetime)):
        return value if isinstance(value, datetime.date) and not isinstance(value, datetime.datetime) else value.date()
    text = str(value).strip()
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y", "%Y/%m/%d", "%d-%m-%Y"):
        try:
            return datetime.datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def normalize_cell(column, value):
    """Turn DB or CSV cell into a standard comparable format."""
    if value is None:
        return ""
    col_type = COLUMN_TYPES.get(column, "str")

    if col_type == "int":
        try:
            return str(int(str(value).strip()))
        except (ValueError, TypeError):
            return str(value).strip()

    if col_type == "decimal":
        try:
            return format(decimal.Decimal(str(value).strip()), ".2f")
        except (decimal.InvalidOperation, ValueError, TypeError):
            return str(value).strip()

    if col_type == "date":
        parsed = _parse_date(value)
        return parsed.strftime("%Y-%m-%d") if parsed else str(value).strip()

    return str(value).strip().lower()


def parse_decimal(value):
    """Safely converts string/number into Decimal for monetary calculations."""
    if value in (None, ""):
        return decimal.Decimal("0.00")
    try:
        cleaned = str(value).replace("$", "").replace(",", "").strip()
        return decimal.Decimal(cleaned)
    except (decimal.InvalidOperation, ValueError, TypeError):
        return decimal.Decimal("0.00")


# ---------------------------------------------------------------------------
# Database & System Helpers
# ---------------------------------------------------------------------------

def fetch_db_date_bounds():
    """Queries DB for the oldest and newest ReceiveDate to set default filter range."""
    conn = connect_db()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT MIN(ReceiveDate), MAX(ReceiveDate) FROM Inventory")
        row = cursor.fetchone()
        if row and row[0] and row[1]:
            min_d = _parse_date(row[0])
            max_d = _parse_date(row[1])
            if min_d and max_d:
                return min_d, max_d
    except Exception:
        pass
    finally:
        conn.close()

    today = datetime.date.today()
    return today.replace(day=1), today


def get_next_report_number():
    """Returns sequential report index number (num for IT-Warehouse-num.pdf)."""
    conn = connect_db()
    num = 1
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM AuditLog WHERE Action = 'GenerateReport'")
        row = cursor.fetchone()
        if row and row[0] is not None:
            num = row[0] + 1
    except Exception:
        pass
    finally:
        conn.close()
    return num


def fetch_db_rows(start_date, end_date):
    """Fetches Inventory rows whose ReceiveDate falls within range."""
    conn = connect_db()
    try:
        cursor = conn.cursor()
        columns_sql = ", ".join(INVENTORY_COLUMNS)
        cursor.execute(
            f"SELECT {columns_sql} FROM Inventory WHERE ReceiveDate BETWEEN ? AND ?",
            (start_date, end_date),
        )
        rows = []
        for record in cursor.fetchall():
            rows.append(dict(zip(INVENTORY_COLUMNS, record)))
        return rows
    finally:
        conn.close()


def read_csv_rows(csv_path):
    """Reads CSV file with flexible header matching."""
    if not os.path.isfile(csv_path):
        raise ValueError(f"File not found:\n{csv_path}")

    with open(csv_path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None:
            raise ValueError("The CSV file appears to be empty.")

        header_map = {}
        for raw_header in reader.fieldnames:
            cleaned = raw_header.strip().lower().replace(" ", "").replace("_", "")
            for canonical in INVENTORY_COLUMNS:
                if cleaned == canonical.lower():
                    header_map[raw_header] = canonical
                    break

        missing_required = [col for col in REQUIRED_CSV_COLUMNS if col not in header_map.values()]
        if missing_required:
            raise ValueError(
                "The CSV is missing required column(s): " + ", ".join(missing_required)
            )

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
        if d is not None and start_date <= d <= end_date:
            filtered.append(row)
    return filtered


# ---------------------------------------------------------------------------
# Multi-Attribute Record Comparison
# ---------------------------------------------------------------------------

def compare_records(csv_rows, db_rows, selected_columns):
    """Matches CSV and DB rows using a composite key built from selected_columns."""
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
# Graphics & PDF Visual Generators
# ---------------------------------------------------------------------------

def create_pie_chart(missing_db_cnt, missing_csv_cnt, mismatched_cnt, total_compared):
    matched_cnt = max(0, total_compared - missing_db_cnt - missing_csv_cnt - mismatched_cnt)
    drawing = Drawing(440, 160)

    pc = Pie()
    pc.x = 20
    pc.y = 15
    pc.width = 130
    pc.height = 130
    pc.data = [matched_cnt, missing_db_cnt, missing_csv_cnt, mismatched_cnt]
    pc.labels = [
        f"Matched: {matched_cnt}",
        f"Missing DB: {missing_db_cnt}",
        f"Missing CSV: {missing_csv_cnt}",
        f"Mismatched: {mismatched_cnt}"
    ]
    pc.sideLabels = 1
    pc.slices.strokeWidth = 0.5
    pc.slices[0].fillColor = colors.HexColor("#2e7d32")
    pc.slices[1].fillColor = colors.HexColor("#c62828")
    pc.slices[2].fillColor = colors.HexColor("#ef6c00")
    pc.slices[3].fillColor = colors.HexColor("#f57f17")

    drawing.add(pc)
    return drawing


def create_price_bar_chart(db_loss, csv_missing_val, total_loss):
    drawing = Drawing(440, 160)
    bc = VerticalBarChart()
    bc.x = 45
    bc.y = 25
    bc.height = 115
    bc.width = 360
    bc.data = [[float(db_loss), float(csv_missing_val), float(total_loss)]]
    bc.categoryAxis.categoryNames = ['Unaccounted DB Loss', 'Unrecorded CSV Items', 'Net Price Loss']
    bc.categoryAxis.labels.fontSize = 8
    bc.valueAxis.valueMin = 0
    bc.bars[(0, 0)].fillColor = colors.HexColor("#c62828")
    bc.bars[(0, 1)].fillColor = colors.HexColor("#ef6c00")
    bc.bars[(0, 2)].fillColor = colors.HexColor("#880e4f")
    drawing.add(bc)
    return drawing


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


# ---------------------------------------------------------------------------
# PDF Generation Function
# ---------------------------------------------------------------------------

def generate_pdf_report(output_path, start_date, end_date, selected_attrs_str, csv_path, comparison):
    styles = getSampleStyleSheet()

    loss_header_style = ParagraphStyle(
        'LossHeader', parent=styles['Heading2'], textColor=colors.HexColor('#b71c1c')
    )
    kpi_title_style = ParagraphStyle(
        'KPITitle', parent=styles['Normal'], fontSize=9, textColor=colors.HexColor('#555555')
    )
    kpi_val_style = ParagraphStyle(
        'KPIVal', parent=styles['Normal'], fontSize=15, fontName='Helvetica-Bold', textColor=colors.HexColor('#b71c1c')
    )

    doc = SimpleDocTemplate(
        output_path, pagesize=landscape(letter),
        topMargin=1.2 * cm, bottomMargin=1.2 * cm,
        leftMargin=1.5 * cm, rightMargin=1.5 * cm
    )
    story = []

    # 1. TITLE PAGE & EXECUTIVE SUMMARY
    story.append(Paragraph("IT Warehouse Inventory & Asset Audit Report", styles["Title"]))
    story.append(Spacer(1, 4))
    
    exec_text = (
        f"<b>Audit Date Range:</b> {start_date.isoformat()} to {end_date.isoformat()} | "
        f"<b>Generated:</b> {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}<br/>"
        f"<b>Source File:</b> {os.path.basename(csv_path)} | <b>Match Strategy:</b> {selected_attrs_str}"
    )
    story.append(Paragraph(exec_text, styles["Normal"]))
    story.append(Spacer(1, 10))

    # Financial Impact Calculations
    unaccounted_db_loss = decimal.Decimal("0.00")
    for r in comparison["missing_in_csv"]:
        tot = parse_decimal(r.get("TotalPrice"))
        if tot == 0:
            tot = parse_decimal(r.get("UnitPrice")) * parse_decimal(r.get("Quantity", 1))
        unaccounted_db_loss += tot

    missing_db_value = decimal.Decimal("0.00")
    for r in comparison["missing_in_db"]:
        tot = parse_decimal(r.get("TotalPrice"))
        if tot == 0:
            tot = parse_decimal(r.get("UnitPrice")) * parse_decimal(r.get("Quantity", 1))
        missing_db_value += tot

    mismatch_price_loss = decimal.Decimal("0.00")
    for _, diffs, csv_r, db_r in comparison["mismatched"]:
        csv_p = parse_decimal(csv_r.get("TotalPrice")) or parse_decimal(csv_r.get("UnitPrice"))
        db_p = parse_decimal(db_r.get("TotalPrice")) or parse_decimal(db_r.get("UnitPrice"))
        if db_p > csv_p:
            mismatch_price_loss += (db_p - csv_p)

    total_price_loss = unaccounted_db_loss + mismatch_price_loss

    kpi_card_1 = [
        Paragraph("Unaccounted DB Loss", kpi_title_style),
        Paragraph(f"${unaccounted_db_loss:,.2f}", kpi_val_style)
    ]
    kpi_card_2 = [
        Paragraph("Unrecorded CSV Value", kpi_title_style),
        Paragraph(f"${missing_db_value:,.2f}", ParagraphStyle('K2', parent=kpi_val_style, textColor=colors.HexColor('#ef6c00')))
    ]
    kpi_card_3 = [
        Paragraph("Total Loss Impact", kpi_title_style),
        Paragraph(f"${total_price_loss:,.2f}", ParagraphStyle('K3', parent=kpi_val_style, textColor=colors.HexColor('#880e4f')))
    ]

    kpi_table = Table([[kpi_card_1, kpi_card_2, kpi_card_3]], colWidths=[8 * cm, 8 * cm, 8 * cm])
    kpi_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#fff5f5')),
        ('BOX', (0, 0), (-1, -1), 1, colors.HexColor('#ef9a9a')),
        ('PADDING', (0, 0), (-1, -1), 6),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
    ]))
    story.append(kpi_table)
    story.append(Spacer(1, 12))

    # 2. TERMS OF REFERENCE
    story.append(Paragraph("1. Terms of Reference", styles["Heading2"]))
    tor_text = (
        "This report evaluates warehouse inventory balance, hardware stock discrepancies, "
        "and monetary variance between physical audit records (CSV) and the central SQLite inventory database. "
        "It covers asset intake verification, hardware serial consistency, and asset price reconciliation."
    )
    story.append(Paragraph(tor_text, styles["Normal"]))
    story.append(Spacer(1, 10))

    # 3. INVENTORY STATUS & STOCK SUMMARY
    story.append(Paragraph("2. Inventory Status & Stock Summary", styles["Heading2"]))
    total_items = (
        len(comparison["missing_in_db"]) +
        len(comparison["missing_in_csv"]) +
        len(comparison["mismatched"])
    )
    pie_drawing = create_pie_chart(
        len(comparison["missing_in_db"]),
        len(comparison["missing_in_csv"]),
        len(comparison["mismatched"]),
        max(total_items, 1)
    )
    story.append(pie_drawing)
    story.append(Spacer(1, 10))

    # 4. ASSET MOVEMENT & TRANSACTIONS
    story.append(Paragraph("3. Asset Movement & Transactions Summary", styles["Heading2"]))
    movement_summary = (
        f"<b>Evaluated Window:</b> {start_date} to {end_date}<br/>"
        f"<b>Total Items Missing in DB (Unrecorded Intake):</b> {len(comparison['missing_in_db'])} units<br/>"
        f"<b>Total Items Missing in CSV (Unaccounted Dispatches/Loss):</b> {len(comparison['missing_in_csv'])} units"
    )
    story.append(Paragraph(movement_summary, styles["Normal"]))
    story.append(PageBreak())

    # 5. FINDINGS & DATA ANALYSIS
    story.append(Paragraph("4. Findings & Financial Data Analysis", styles["Heading2"]))
    bar_drawing = create_price_bar_chart(unaccounted_db_loss, missing_db_value, total_price_loss)
    story.append(bar_drawing)
    story.append(Spacer(1, 10))

    display_cols = ["DeviceName", "DeviceType", "Quantity", "UnitPrice", "TotalPrice", "ReceiveDate"]

    def rows_table(rows):
        header = display_cols[:]
        data = [header]
        for r in rows:
            data.append([str(r.get(c, "")) for c in header])
        return _simple_table(data)

    story.append(Paragraph("Unaccounted Inventory Items (In DB but Missing in CSV)", loss_header_style))
    story.append(Spacer(1, 4))
    if comparison["missing_in_csv"]:
        story.append(rows_table(comparison["missing_in_csv"]))
    else:
        story.append(Paragraph("No unaccounted inventory items missing from CSV.", styles["Normal"]))
    story.append(Spacer(1, 14))

    story.append(Paragraph("Mismatched Attribute Records", styles["Heading3"]))
    story.append(Spacer(1, 4))
    if comparison["mismatched"]:
        data = [["Matched Key Combination", "Column", "CSV Value", "DB Value"]]
        for key_repr, diffs, csv_r, db_r in comparison["mismatched"]:
            for column, csv_val, db_val in diffs:
                data.append([key_repr[:35], column, csv_val, db_val])
        story.append(_simple_table(data, col_widths=[7 * cm, 4 * cm, 7 * cm, 7 * cm]))
    else:
        story.append(Paragraph("No mismatched attributes detected.", styles["Normal"]))
    story.append(Spacer(1, 14))

    # 6. ACTIONABLE RECOMMENDATIONS
    story.append(Paragraph("5. Actionable Recommendations", styles["Heading2"]))
    recs = (
        "<b>1. Barcode Standardization:</b> Enforce mandatory barcode and serial number scans during intake.<br/>"
        "<b>2. Weekly Cycle Counting:</b> Implement bi-weekly cycle counts for high-value IT hardware.<br/>"
        "<b>3. Discrepancy Reconciliation:</b> Audit unrecorded CSV items into the main database prior to closing financial periods."
    )
    story.append(Paragraph(recs, styles["Normal"]))
    story.append(Spacer(1, 14))

    # 7. APPENDICES & GLOSSARY
    story.append(Paragraph("6. Appendices & Glossary", styles["Heading2"]))
    glossary = (
        "<b>DB:</b> Central Database storing inventory records.<br/>"
        "<b>CSV:</b> Comma-Separated Values file containing physical audit scan results.<br/>"
        "<b>Unaccounted DB Loss:</b> Inventory items logged in the database but missing from physical audit counts."
    )
    story.append(Paragraph(glossary, styles["Normal"]))

    doc.build(story)


# ---------------------------------------------------------------------------
# Enhanced Report Dialog (PyQt5)
# ---------------------------------------------------------------------------

class ReportDialog(QDialog):
    def __init__(self, parent=None, current_username=None):
        super().__init__(parent)
        self.setWindowTitle("Generate IT Warehouse Reconciliation Report")
        self.setMinimumWidth(540)
        self.current_username = current_username or "unknown"

        # CSV File Selector
        self.csv_path_edit = QLineEdit()
        self.csv_path_edit.setReadOnly(True)
        browse_btn = QPushButton("Browse...")
        browse_btn.clicked.connect(self._browse_csv)

        csv_row = QHBoxLayout()
        csv_row.addWidget(self.csv_path_edit)
        csv_row.addWidget(browse_btn)
        csv_row_widget = QWidget()
        csv_row_widget.setLayout(csv_row)

        # Multi-Attribute Checkboxes
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
            row = idx // 2
            col = idx % 2
            grid.addWidget(cb, row, col)

        grid_container = QWidget()
        grid_container.setLayout(grid)

        attr_box = QGroupBox("Match Rows By:")
        attr_layout = QVBoxLayout()
        attr_layout.addWidget(self.all_attr_cb)
        attr_layout.addWidget(grid_container)
        attr_box.setLayout(attr_layout)

        # Date Pickers - Automatically set to Min/Max dates from DB
        min_db_date, max_db_date = fetch_db_date_bounds()

        self.from_date = QDateEdit(calendarPopup=True)
        self.from_date.setDate(QDate(min_db_date.year, min_db_date.month, min_db_date.day))

        self.to_date = QDateEdit(calendarPopup=True)
        self.to_date.setDate(QDate(max_db_date.year, max_db_date.month, max_db_date.day))

        form = QFormLayout()
        form.addRow("CSV File:", csv_row_widget)
        form.addRow("From Date:", self.from_date)
        form.addRow("To Date:", self.to_date)

        # Dialog Buttons
        buttons = QDialogButtonBox(QDialogButtonBox.Cancel)
        self.generate_btn = QPushButton("Generate Report")
        self.generate_btn.clicked.connect(self._on_generate)
        buttons.addButton(self.generate_btn, QDialogButtonBox.AcceptRole)
        buttons.rejected.connect(self.reject)

        # Main Layout
        layout = QVBoxLayout()
        layout.addWidget(QLabel("<b>Reconcile CSV Export Against Warehouse Database</b>"))
        layout.addLayout(form)
        layout.addWidget(attr_box)
        layout.addWidget(buttons)
        self.setLayout(layout)

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
        csv_path = self.csv_path_edit.text().strip()
        if not csv_path:
            QMessageBox.warning(self, "Missing file", "Please choose a CSV file first.")
            return

        selected_attrs = [
            ATTRIBUTE_MAP[label] for label, cb in self.attr_checkboxes.items() if cb.isChecked()
        ]

        if not selected_attrs:
            QMessageBox.warning(self, "No attributes selected", "Please select at least one attribute to match rows by.")
            return

        start_date = self.from_date.date().toPyDate()
        end_date = self.to_date.date().toPyDate()
        if start_date > end_date:
            QMessageBox.warning(self, "Invalid range", "'From date' must be before 'To date'.")
            return

        # Generate output filename: IT-Warehouse-num.pdf
        report_num = get_next_report_number()
        default_filename = f"IT-Warehouse-{report_num}.pdf"

        output_path, _ = QFileDialog.getSaveFileName(
            self, "Save Report As", default_filename, "PDF files (*.pdf)"
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

            generate_pdf_report(output_path, start_date, end_date, selected_str, csv_path, comparison)

            try:
                log_audit(
                    self.current_username, "GenerateReport",
                    details=(
                        f"CSV={os.path.basename(csv_path)} range={start_date}..{end_date} "
                        f"missing_in_db={len(comparison['missing_in_db'])} "
                        f"missing_in_csv={len(comparison['missing_in_csv'])} "
                        f"mismatched={len(comparison['mismatched'])}"
                    ),
                )
            except Exception:
                pass  # Ignore audit-logging failures

            QMessageBox.information(
                self, "Report Generated",
                f"Report successfully saved to:\n{output_path}\n\n"
                f"Missing from Database: {len(comparison['missing_in_db'])}\n"
                f"Missing from CSV (Price Loss): {len(comparison['missing_in_csv'])}\n"
                f"Mismatched Items: {len(comparison['mismatched'])}"
            )
            self.accept()
        except ValueError as e:
            QMessageBox.critical(self, "Could not generate report", str(e))
        except Exception as e:
            traceback.print_exc()
            QMessageBox.critical(self, "Unexpected error", f"{type(e).__name__}: {e}")
        finally:
            self.generate_btn.setEnabled(True)


def open_report_dialog(parent, current_username=None):
    """Helper method to open the report dialog."""
    dialog = ReportDialog(parent, current_username=current_username)
    dialog.exec_()