import sys
import ctypes
import os
import csv
import re
import webbrowser
from datetime import datetime, date

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QTableWidget, QTableWidgetItem, QHeaderView, QPushButton, QLabel,
    QFrame, QMessageBox, QDialog, QScrollArea, QAbstractItemView,
    QStackedWidget, QMenuBar, QAction, QLineEdit, QComboBox,
    QMenu, QFileDialog, QFontDialog, QInputDialog, QStatusBar,
    QFormLayout, QRadioButton, QGroupBox, QCheckBox, QDateEdit
)
from PyQt5.QtCore import Qt, QUrl, QDate
from PyQt5.QtGui import QIcon, QPixmap, QKeySequence, QFont, QGuiApplication, QTextDocument
from PyQt5.QtPrintSupport import QPrinter, QPrintDialog, QPageSetupDialog

from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure

from database import init_db, connect_db, log_audit
from auth import LoginDialog, find_logo_path
from dialogs import StockInDialog, StockOutDialog

# Force Windows Taskbar to use custom icon
myappid = 'aubmc.itwarehouse.app.3.0'
ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)


# ==========================================
# EXPORT DIALOG
# ==========================================
class ExportDialog(QDialog):
    def __init__(self, username, parent=None):
        super().__init__(parent)
        self.username = username
        self.setWindowTitle("Export Inventory Data")
        self.setMinimumWidth(480)
        self.setStyleSheet("QDialog { background-color: #FFFFFF; }")
        self._init_ui()
        self._populate_device_types()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        # Title
        title = QLabel("Export Options")
        title.setStyleSheet("font-size: 18px; font-weight: bold; color: #101828;")
        layout.addWidget(title)

        subtitle = QLabel("Select whether to export all inventory records or apply custom filters.")
        subtitle.setStyleSheet("font-size: 12px; color: #667085;")
        layout.addWidget(subtitle)

        # Mode Selection (Radio buttons)
        mode_box = QGroupBox("Export Mode")
        mode_box.setStyleSheet("QGroupBox { font-weight: bold; color: #101828; border: 1px solid #E4E4E7; border-radius: 6px; margin-top: 6px; padding-top: 10px; }")
        mode_layout = QVBoxLayout(mode_box)

        self.rb_export_all = QRadioButton("Export All Data")
        self.rb_export_all.setChecked(True)
        self.rb_export_all.setStyleSheet("font-size: 13px; font-weight: bold; color: #1F2D3D;")
        self.rb_export_all.toggled.connect(self._toggle_filter_options)

        self.rb_export_filtered = QRadioButton("Export Filtered Data")
        self.rb_export_filtered.setStyleSheet("font-size: 13px; font-weight: bold; color: #1F2D3D;")

        mode_layout.addWidget(self.rb_export_all)
        mode_layout.addWidget(self.rb_export_filtered)
        layout.addWidget(mode_box)

        # Filter Options Group
        self.filter_box = QGroupBox("Filter Criteria")
        self.filter_box.setEnabled(False)
        self.filter_box.setStyleSheet("QGroupBox { font-weight: bold; color: #101828; border: 1px solid #E4E4E7; border-radius: 6px; margin-top: 6px; padding-top: 10px; }")
        filter_layout = QFormLayout(self.filter_box)
        filter_layout.setSpacing(10)

        # 1. Device Name
        self.input_device_name = QLineEdit()
        self.input_device_name.setPlaceholderText("Filter by Name (e.g. Laptop, Dell)...")
        self.input_device_name.setStyleSheet("padding: 6px; border: 1px solid #D0D5DD; border-radius: 4px; background: white;")
        filter_layout.addRow(QLabel("Device Name:"), self.input_device_name)

        # 2. Device Type
        self.combo_device_type = QComboBox()
        self.combo_device_type.setStyleSheet("padding: 6px; border: 1px solid #D0D5DD; border-radius: 4px; background: white;")
        filter_layout.addRow(QLabel("Device Type:"), self.combo_device_type)

        # 3. Time Frame (Receive Date)
        self.chk_enable_dates = QCheckBox("Filter by Receive Date Range")
        self.chk_enable_dates.setStyleSheet("font-weight: normal; font-size: 12px; color: #3F3F46;")
        self.chk_enable_dates.toggled.connect(self._toggle_date_inputs)

        date_layout = QHBoxLayout()
        self.date_start = QDateEdit()
        self.date_start.setCalendarPopup(True)
        self.date_start.setDate(QDate.currentDate().addMonths(-1))
        self.date_start.setStyleSheet("padding: 5px; border: 1px solid #D0D5DD; border-radius: 4px; background: white;")
        self.date_start.setEnabled(False)

        self.date_end = QDateEdit()
        self.date_end.setCalendarPopup(True)
        self.date_end.setDate(QDate.currentDate())
        self.date_end.setStyleSheet("padding: 5px; border: 1px solid #D0D5DD; border-radius: 4px; background: white;")
        self.date_end.setEnabled(False)

        date_layout.addWidget(QLabel("From:"))
        date_layout.addWidget(self.date_start)
        date_layout.addWidget(QLabel("To:"))
        date_layout.addWidget(self.date_end)

        filter_layout.addRow(self.chk_enable_dates)
        filter_layout.addRow(date_layout)

        layout.addWidget(self.filter_box)

        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        btn_cancel = QPushButton("Cancel")
        btn_cancel.setStyleSheet("background-color: #F4F4F5; color: #18181B; border: 1px solid #D4D4D8; padding: 8px 16px; border-radius: 4px; font-weight: bold;")
        btn_cancel.clicked.connect(self.reject)

        btn_export = QPushButton("📤 Export to CSV")
        btn_export.setStyleSheet("background-color: #1F2D3D; color: white; border: none; padding: 8px 16px; border-radius: 4px; font-weight: bold;")
        btn_export.clicked.connect(self.process_export)

        btn_layout.addWidget(btn_cancel)
        btn_layout.addWidget(btn_export)
        layout.addLayout(btn_layout)

    def _toggle_filter_options(self, checked):
        self.filter_box.setEnabled(not checked)

    def _toggle_date_inputs(self, checked):
        self.date_start.setEnabled(checked)
        self.date_end.setEnabled(checked)

    def _populate_device_types(self):
        try:
            conn = connect_db()
            cursor = conn.cursor()
            cursor.execute("SELECT DISTINCT DeviceType FROM Inventory WHERE DeviceType IS NOT NULL AND DeviceType <> ''")
            types = [row[0] for row in cursor.fetchall()]
            conn.close()

            self.combo_device_type.addItem("-- All Types --")
            for t in sorted(types):
                self.combo_device_type.addItem(t)
        except Exception:
            self.combo_device_type.addItem("-- All Types --")

    def process_export(self):
        # Open save file dialog
        file_path, _ = QFileDialog.getSaveFileName(self, "Save Inventory Export", "inventory_export.csv", "CSV Files (*.csv)")
        if not file_path:
            return

        try:
            conn = connect_db()
            cursor = conn.cursor()

            query = "SELECT * FROM Inventory WHERE 1=1"
            params = []
            filter_descriptions = []

            # Construct query based on export mode
            if self.rb_export_filtered.isChecked():
                # Filter by Device Name
                name_filter = self.input_device_name.text().strip()
                if name_filter:
                    query += " AND DeviceName LIKE ?"
                    params.append(f"%{name_filter}%")
                    filter_descriptions.append(f"Name containing '{name_filter}'")

                # Filter by Device Type
                selected_type = self.combo_device_type.currentText()
                if selected_type and selected_type != "-- All Types --":
                    query += " AND DeviceType = ?"
                    params.append(selected_type)
                    filter_descriptions.append(f"Type '{selected_type}'")

                # Filter by Time Frame (Receive Date)
                if self.chk_enable_dates.isChecked():
                    start_str = self.date_start.date().toString("yyyy-MM-dd")
                    end_str = self.date_end.date().toString("yyyy-MM-dd") + " 23:59:59"
                    query += " AND ReceiveDate >= ? AND ReceiveDate <= ?"
                    params.extend([start_str, end_str])
                    filter_descriptions.append(f"Date range {start_str} to {self.date_end.date().toString('yyyy-MM-dd')}")

            query += " ORDER BY Id DESC"

            cursor.execute(query, params)
            columns = [col[0] for col in cursor.description] if cursor.description else []
            rows = cursor.fetchall()
            conn.close()

            if not rows:
                QMessageBox.warning(self, "Export Warning", "No inventory records matched your selected export criteria.")
                return

            with open(file_path, mode='w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow(columns)
                writer.writerows(rows)

            desc = ", ".join(filter_descriptions) if filter_descriptions else "All Records"
            log_audit(self.username, "EXPORT_CSV", f"Exported {len(rows)} record(s) to CSV ({desc})")

            QMessageBox.information(
                self, 
                "Export Successful", 
                f"Successfully exported {len(rows)} record(s) to:\n{file_path}"
            )
            self.accept()

        except Exception as e:
            QMessageBox.critical(self, "Export Failed", f"An error occurred while exporting data:\n{e}")


# ==========================================
# USER MANAGEMENT DIALOG
# ==========================================
class UserManagementDialog(QDialog):
    def __init__(self, current_username, current_role, parent=None):
        super().__init__(parent)
        self.current_username = current_username
        self.current_role = current_role
        self.setWindowTitle("User Management")
        self.resize(650, 500)
        self.setStyleSheet("QDialog { background-color: #FFFFFF; }")
        self._init_ui()
        self.load_users()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        title = QLabel("Manage Application Users")
        title.setStyleSheet("font-size: 18px; font-weight: bold; color: #101828;")
        layout.addWidget(title)

        # User Table
        self.user_table = QTableWidget(0, 3)
        self.user_table.setHorizontalHeaderLabels(["ID", "USERNAME", "ROLE"])
        self.user_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.user_table.verticalHeader().setVisible(False)
        self.user_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.user_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.user_table.setStyleSheet("""
            QTableWidget { border: 1px solid #E4E4E7; border-radius: 6px; background-color: white; font-size: 12px; }
            QHeaderView::section { background-color: #FAFAFA; border: none; border-bottom: 1px solid #E4E4E7; padding: 8px; font-weight: bold; font-size: 10px; color: #71717A; }
            QTableWidget::item { padding: 8px; border-bottom: 1px solid #F4F4F5; }
        """)
        layout.addWidget(self.user_table)
        
        # Delete User Button (Admin Only)
        self.btn_delete = QPushButton("🗑 Delete Selected User")
        self.btn_delete.setStyleSheet("background-color: #EF4444; color: white; border: none; padding: 6px 14px; border-radius: 4px; font-weight: bold;")
        self.btn_delete.clicked.connect(self.delete_user)
        
        if self.current_role != "Admin":
            self.btn_delete.hide()
            
        layout.addWidget(self.btn_delete, alignment=Qt.AlignRight)

        # Form to create a new user
        form_frame = QFrame()
        form_frame.setStyleSheet("background-color: #F9FAFB; border: 1px solid #E4E4E7; border-radius: 6px;")
        form_layout = QHBoxLayout(form_frame)
        form_layout.setContentsMargins(10, 10, 10, 10)
        form_layout.setSpacing(10)

        self.input_user = QLineEdit()
        self.input_user.setPlaceholderText("Username")
        self.input_user.setStyleSheet("padding: 6px; border: 1px solid #D0D5DD; border-radius: 4px; background: white;")

        self.input_pass = QLineEdit()
        self.input_pass.setPlaceholderText("Password")
        self.input_pass.setEchoMode(QLineEdit.Password)
        self.input_pass.setStyleSheet("padding: 6px; border: 1px solid #D0D5DD; border-radius: 4px; background: white;")

        self.combo_role = QComboBox()
        self.combo_role.addItems(["Admin", "User", "Operator"])
        self.combo_role.setStyleSheet("padding: 6px; border: 1px solid #D0D5DD; border-radius: 4px; background: white;")

        btn_add = QPushButton("Add User")
        btn_add.setStyleSheet("background-color: #1F2D3D; color: white; border: none; padding: 6px 14px; border-radius: 4px; font-weight: bold;")
        btn_add.clicked.connect(self.add_user)

        form_layout.addWidget(self.input_user)
        form_layout.addWidget(self.input_pass)
        form_layout.addWidget(self.combo_role)
        form_layout.addWidget(btn_add)

        layout.addWidget(form_frame)

    def load_users(self):
        try:
            conn = connect_db()
            cursor = conn.cursor()

            cursor.execute("""
                IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'Users')
                BEGIN
                    CREATE TABLE Users (
                        Id INT IDENTITY(1,1) PRIMARY KEY,
                        Username NVARCHAR(50) NOT NULL UNIQUE,
                        Password NVARCHAR(255) NOT NULL,
                        Role NVARCHAR(50) NOT NULL
                    )
                END
            """)
            conn.commit()

            cursor.execute("SELECT Id, Username, Role FROM Users ORDER BY Id DESC")
            rows = cursor.fetchall()
            self.user_table.setRowCount(0)
            for row_idx, row_data in enumerate(rows):
                self.user_table.insertRow(row_idx)
                for col_idx, value in enumerate(row_data):
                    item = QTableWidgetItem(str(value))
                    if col_idx == 0:
                        item.setTextAlignment(Qt.AlignCenter | Qt.AlignVCenter)
                    self.user_table.setItem(row_idx, col_idx, item)
            conn.close()
        except Exception as e:
            QMessageBox.critical(self, "Database Error", str(e))

    def add_user(self):
        username = self.input_user.text().strip()
        password = self.input_pass.text().strip()
        role = self.combo_role.currentText()

        if not username or not password:
            QMessageBox.warning(self, "Validation Error", "Username and Password cannot be empty.")
            return

        try:
            conn = connect_db()
            cursor = conn.cursor()
            cursor.execute("INSERT INTO Users (Username, Password, Role) VALUES (?, ?, ?)", (username, password, role))
            conn.commit()
            conn.close()

            log_audit(self.current_username, "USER_ADD", f"Created user '{username}' with role '{role}'")
            QMessageBox.information(self, "Success", f"User '{username}' added successfully!")

            self.input_user.clear()
            self.input_pass.clear()
            self.load_users()
        except Exception as e:
            QMessageBox.critical(self, "Error Adding User", f"Could not add user. Username may already exist.\n\nError: {e}")

    def delete_user(self):
        selected_row = self.user_table.currentRow()
        if selected_row < 0:
            QMessageBox.warning(self, "Selection Error", "Please select a user to delete.")
            return
            
        user_id = self.user_table.item(selected_row, 0).text()
        username = self.user_table.item(selected_row, 1).text()

        if username == self.current_username:
            QMessageBox.warning(self, "Action Denied", "You cannot delete your currently active account.")
            return

        reply = QMessageBox.question(self, "Confirm Deletion", f"Are you sure you want to permanently delete the user '{username}'?", QMessageBox.Yes | QMessageBox.No)
        
        if reply == QMessageBox.Yes:
            try:
                conn = connect_db()
                cursor = conn.cursor()
                cursor.execute("DELETE FROM Users WHERE Id = ?", (user_id,))
                conn.commit()
                conn.close()

                log_audit(self.current_username, "USER_DELETE", f"Deleted user '{username}'")
                QMessageBox.information(self, "Success", f"User '{username}' was deleted.")
                self.load_users()
            except Exception as e:
                QMessageBox.critical(self, "Database Error", f"Failed to delete user:\n{e}")


# ==========================================
# ITEM DETAILS DIALOG
# ==========================================
class ItemDetailsDialog(QDialog):
    def __init__(self, item_data, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Full Record Details")
        self.resize(520, 650)
        self.setStyleSheet("QDialog { background-color: #FFFFFF; }")
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        
        title = QLabel("Complete Record Fields")
        title.setStyleSheet("font-size: 18px; font-weight: bold; color: #101828; margin-bottom: 10px;")
        layout.addWidget(title)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: 1px solid #E4E4E7; border-radius: 6px; background-color: #F9FAFB; }")
        
        content_widget = QWidget()
        content_widget.setStyleSheet("background-color: #F9FAFB;")
        form_layout = QFormLayout(content_widget)
        form_layout.setLabelAlignment(Qt.AlignRight)
        form_layout.setSpacing(12)
        
        for key, val in item_data.items():
            formatted_key = self._format_key_name(key)
            lbl_key = QLabel(f"{formatted_key}:")
            lbl_key.setStyleSheet("color: #71717A; font-size: 12px; font-weight: bold;")
            
            lbl_val = QLabel(str(val) if val is not None and str(val).strip() not in ("", "None") else "-")
            lbl_val.setStyleSheet("color: #101828; font-size: 13px;")
            lbl_val.setWordWrap(True)
            form_layout.addRow(lbl_key, lbl_val)
            
        scroll.setWidget(content_widget)
        layout.addWidget(scroll)

        btn_close = QPushButton("Close")
        btn_close.setStyleSheet("background-color: #1F2D3D; color: white; padding: 8px 16px; border-radius: 4px; font-weight: bold;")
        btn_close.clicked.connect(self.accept)
        
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        btn_layout.addWidget(btn_close)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)

    def _format_key_name(self, key):
        if " " in key:
            return key
        clean = key.replace("_", " ")
        clean = re.sub(r'([a-z])([A-Z])', r'\1 \2', clean)
        return clean.title()


# ==========================================
# CHARTS
# ==========================================
class DonutChartCanvas(FigureCanvas):
    def __init__(self, parent=None, width=4, height=3, dpi=100):
        fig = Figure(figsize=(width, height), dpi=dpi)
        fig.patch.set_alpha(0.0)
        self.axes = fig.add_subplot(111)
        self.axes.axis('equal')
        super(DonutChartCanvas, self).__init__(fig)
        self.setStyleSheet("background-color: transparent;")

    def update_chart(self, data_dict):
        self.axes.clear()
        if not data_dict:
            self.axes.text(0.5, 0.5, "No data", horizontalalignment='center', verticalalignment='center', color="#667085")
            self.draw()
            return

        labels = list(data_dict.keys())
        sizes = list(data_dict.values())
        total = sum(sizes)
        colors = ['#3B5998', '#D97757', '#5C8A8A', '#D9A05B', '#6B5B95', '#88B04B']

        wedges, _ = self.axes.pie(
            sizes, colors=colors, startangle=90, 
            wedgeprops=dict(width=0.25, edgecolor='#FFFFFF', linewidth=2)
        )

        self.axes.text(0, 0.1, str(total), horizontalalignment='center', verticalalignment='center', fontsize=18, fontweight='bold', color="#101828")
        self.axes.text(0, -0.2, "units", horizontalalignment='center', verticalalignment='center', fontsize=9, color="#667085")
        
        self.axes.legend(
            wedges, [f"{l} ({s})" for l, s in zip(labels, sizes)],
            title="Legend", loc="center left", bbox_to_anchor=(0.9, 0, 0.5, 1),
            frameon=False, fontsize=9
        )
        self.draw()


# ==========================================
# MAIN WINDOW
# ==========================================
class MainWindow(QMainWindow):
    def __init__(self, username, user_role):
        super().__init__()
        self.username = username
        self.user_role = user_role

        self.setWindowTitle("Inventory Desk - Operations")
        self.setGeometry(50, 50, 1400, 850)
        self.setStyleSheet("QMainWindow { background-color: #FBFBFA; }")
        
        icon_path = find_logo_path()
        if icon_path:
            self.setWindowIcon(QIcon(icon_path))

        self._ensure_database_schema()
        self._init_ui()
        self.refresh_all_data()

    def _ensure_database_schema(self):
        """ ensure required fields exist in the Inventory and AuditLogs tables """
        try:
            conn = connect_db()
            cursor = conn.cursor()
            
            # Additional standard columns to enforce in Inventory
            inventory_cols = [
                ("Sender", "NVARCHAR(255)"),
                ("WarrantyDate", "NVARCHAR(100)"),
                ("TicketNumber", "NVARCHAR(100)"),
                ("FromWhere", "NVARCHAR(255)")
            ]
            for col_name, col_type in inventory_cols:
                cursor.execute(f"""
                    IF NOT EXISTS (
                        SELECT * FROM INFORMATION_SCHEMA.COLUMNS 
                        WHERE TABLE_NAME = 'Inventory' AND COLUMN_NAME = '{col_name}'
                    )
                    BEGIN
                        ALTER TABLE Inventory ADD {col_name} {col_type} NULL
                    END
                """)

            # Ensure ReceiveDate column can store date and time
            cursor.execute("""
                IF EXISTS (
                    SELECT * FROM INFORMATION_SCHEMA.COLUMNS 
                    WHERE TABLE_NAME = 'Inventory' AND COLUMN_NAME = 'ReceiveDate' AND DATA_TYPE = 'date'
                )
                BEGIN
                    ALTER TABLE Inventory ALTER COLUMN ReceiveDate NVARCHAR(100) NULL
                END
            """)

            audit_cols = [
                ("Sender", "NVARCHAR(255)"),
                ("WarrantyDate", "NVARCHAR(100)"),
                ("TicketNumber", "NVARCHAR(100)"),
                ("FromWhere", "NVARCHAR(255)")
            ]
            for col_name, col_type in audit_cols:
                cursor.execute(f"""
                    IF NOT EXISTS (
                        SELECT * FROM INFORMATION_SCHEMA.COLUMNS 
                        WHERE TABLE_NAME = 'AuditLogs' AND COLUMN_NAME = '{col_name}'
                    )
                    BEGIN
                        ALTER TABLE AuditLogs ADD {col_name} {col_type} NULL
                    END
                """)

            conn.commit()
            conn.close()
        except Exception as e:
            print(f"Schema verification warning: {e}")

    def _init_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Top Header
        top_header = self._build_top_header()
        main_layout.addWidget(top_header)

        # Body Layout
        body_layout = QHBoxLayout()
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(0)

        # Sidebar
        sidebar = self._build_sidebar()
        body_layout.addWidget(sidebar)

        # Stacked Tabs
        self.stacked_widget = QStackedWidget()
        self.stacked_widget.addWidget(self._build_dashboard_tab()) # Index 0
        self.stacked_widget.addWidget(self._build_inventory_tab()) # Index 1
        self.stacked_widget.addWidget(self._build_history_tab())   # Index 2
        
        body_layout.addWidget(self.stacked_widget)
        main_layout.addLayout(body_layout)

    def _build_top_header(self):
        header_frame = QFrame()
        header_frame.setStyleSheet("background-color: #FFFFFF; border-bottom: 1px solid #E4E4E7;")
        header_frame.setFixedHeight(90)
        layout = QVBoxLayout(header_frame)
        layout.setContentsMargins(15, 10, 20, 10)
        layout.setSpacing(5)

        brand_row = QHBoxLayout()
        
        icon_lbl = QLabel()
        icon_path = find_logo_path()
        if icon_path and os.path.exists(icon_path):
            pixmap = QPixmap(icon_path).scaled(30, 30, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            icon_lbl.setPixmap(pixmap)
            icon_lbl.setStyleSheet("border-radius: 4px; padding: 2px;")
        else:
            icon_lbl.setText("🏛") 
            icon_lbl.setStyleSheet("background-color: #1F2D3D; color: white; border-radius: 4px; padding: 4px; font-size: 16px;")
        
        brand_text_layout = QVBoxLayout()
        brand_title = QLabel("INVENTORY DESK")
        brand_title.setStyleSheet("font-weight: 800; font-size: 12px; color: #1F2D3D; border: none;")
        brand_sub = QLabel("IT WAREHOUSE / LOCAL")
        brand_sub.setStyleSheet("font-size: 9px; color: #71717A; font-weight: bold; border: none;")
        brand_text_layout.addWidget(brand_title)
        brand_text_layout.addWidget(brand_sub)
        
        brand_row.addWidget(icon_lbl)
        brand_row.addLayout(brand_text_layout)
        brand_row.addSpacing(20)

        tab_btn = QPushButton("⚙ Operations")
        tab_btn.setStyleSheet("background-color: #F4F4F5; border: 1px solid #E4E4E7; padding: 6px 12px; border-radius: 4px; font-weight: bold; color: #1F2D3D;")
        brand_row.addWidget(tab_btn)
        brand_row.addStretch()
        
        layout.addLayout(brand_row)

        toolbar_row = QHBoxLayout()
        
        menu_bar = QMenuBar()
        menu_bar.setStyleSheet("""
            QMenuBar { background-color: transparent; font-size: 11px; color: #3F3F46; }
            QMenuBar::item { padding: 4px 8px; background: transparent; }
            QMenuBar::item:selected { background: #F4F4F5; border-radius: 4px; }
            QMenu { background-color: #FFFFFF; border: 1px solid #E4E4E7; font-size: 11px; color: #3F3F46; }
            QMenu::item { padding: 4px 20px; }
            QMenu::item:selected { background-color: #F4F4F5; }
        """)
        
        # File Menu
        file_menu = menu_bar.addMenu("File")
        
        import_action = QAction("📥 Import Inventory (CSV)", self)
        import_action.triggered.connect(self.import_csv)
        file_menu.addAction(import_action)

        export_action = QAction("📤 Export Inventory (CSV)", self)
        export_action.setShortcut(QKeySequence("Ctrl+E"))
        export_action.triggered.connect(self.export_to_csv)
        file_menu.addAction(export_action)

        print_action = QAction("🖨 Print / PDF Report", self)
        print_action.setShortcut(QKeySequence("Ctrl+P"))
        print_action.triggered.connect(self.print_inventory_report)
        file_menu.addAction(print_action)

        file_menu.addSeparator()

        exit_action = QAction("❌ Exit", self)
        exit_action.setShortcut(QKeySequence("Ctrl+Q"))
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        # Edit Menu
        edit_menu = menu_bar.addMenu("Edit")

        stock_in_action = QAction("↓ Stock In Item", self)
        stock_in_action.setShortcut(QKeySequence("Ctrl+I"))
        stock_in_action.triggered.connect(self.open_stock_in)
        edit_menu.addAction(stock_in_action)

        stock_out_action = QAction("↑ Stock Out Item", self)
        stock_out_action.setShortcut(QKeySequence("Ctrl+O"))
        stock_out_action.triggered.connect(self.open_stock_out)
        edit_menu.addAction(stock_out_action)

        edit_menu.addSeparator()

        delete_action = QAction("🗑 Delete Selected Inventory Item", self)
        delete_action.setShortcut(QKeySequence("Delete"))
        delete_action.triggered.connect(self.delete_inventory_item)
        
        current_role_clean = str(self.user_role).strip().lower() if self.user_role else ""
        if current_role_clean != "admin":
            delete_action.setEnabled(False)
            
        edit_menu.addAction(delete_action)

        edit_menu.addSeparator()

        users_action = QAction("👤 User Management", self)
        users_action.triggered.connect(self.open_users)
        edit_menu.addAction(users_action)

        # View Menu
        view_menu = menu_bar.addMenu("View")

        refresh_action = QAction("🔄 Refresh All Data", self)
        refresh_action.setShortcut(QKeySequence("F5"))
        refresh_action.triggered.connect(self.refresh_all_data)
        view_menu.addAction(refresh_action)

        view_menu.addSeparator()

        dash_action = QAction("📊 Dashboard View", self)
        dash_action.setShortcut(QKeySequence("Ctrl+1"))
        dash_action.triggered.connect(lambda: self.switch_tab(0, self.btn_dash))
        view_menu.addAction(dash_action)

        inv_action = QAction("📦 All Inventory View", self)
        inv_action.setShortcut(QKeySequence("Ctrl+2"))
        inv_action.triggered.connect(lambda: self.switch_tab(1, self.btn_inv))
        view_menu.addAction(inv_action)

        hist_action = QAction("📜 History & Audit Logs View", self)
        hist_action.setShortcut(QKeySequence("Ctrl+3"))
        hist_action.triggered.connect(lambda: self.switch_tab(2, self.btn_hist))
        view_menu.addAction(hist_action)

        toolbar_row.addWidget(menu_bar)
        toolbar_row.addStretch()
        
        user_info = QLabel(f"👤 {self.username} - {self.user_role}")
        user_info.setStyleSheet("font-size: 11px; color: #71717A;")
        toolbar_row.addWidget(user_info)
        
        manage_btn = QPushButton("Manage users")
        manage_btn.setStyleSheet("border: 1px solid #D4D4D8; background: white; padding: 4px 8px; border-radius: 4px; font-size: 11px;")
        manage_btn.clicked.connect(self.open_users)
        toolbar_row.addWidget(manage_btn)
        
        layout.addLayout(toolbar_row)
        return header_frame

    def import_csv(self):
        expected_headers = [
            "DeviceName", "DeviceType", "Quantity", "Sender", "Receiver",
            "ReceiveDate", "WarrantyDate", "Barcode", "TicketNumber",
            "FromWhere", "SerialNumber", "HostName", "Note"
        ]

        file_path, _ = QFileDialog.getOpenFileName(
            self, "Import Inventory CSV", "", "CSV Files (*.csv);;All Files (*)"
        )
        if not file_path:
            return

        try:
            with open(file_path, mode='r', encoding='utf-8-sig') as file:
                reader = csv.DictReader(file)

                if not reader.fieldnames:
                    QMessageBox.critical(self, "Import Error", "The selected CSV file is empty.")
                    return

                file_headers = [h.strip() for h in reader.fieldnames]

                missing_headers = [h for h in expected_headers if h not in file_headers]
                if missing_headers:
                    QMessageBox.critical(
                        self,
                        "Format Mismatch Error",
                        f"Invalid CSV structure!\n\n"
                        f"Missing Required Columns:\n• " + "\n• ".join(missing_headers) + "\n\n"
                        f"Please ensure your header matches exact database fields:\n"
                        f"{', '.join(expected_headers)}"
                    )
                    return

                rows_to_insert = []
                for row_idx, row in enumerate(reader, start=2):
                    dev_name = row.get("DeviceName", "").strip()
                    dev_type = row.get("DeviceType", "").strip()
                    barcode = row.get("Barcode", "").strip()

                    if not dev_name or not dev_type or not barcode:
                        QMessageBox.critical(
                            self,
                            "Row Validation Error",
                            f"Row {row_idx} is missing mandatory fields (DeviceName, DeviceType, or Barcode)."
                        )
                        return

                    try:
                        qty = int(row.get("Quantity", 1))
                    except ValueError:
                        QMessageBox.critical(
                            self,
                            "Data Type Error",
                            f"Row {row_idx}: 'Quantity' must be a valid integer number."
                        )
                        return

                    rows_to_insert.append((
                        dev_name,
                        dev_type,
                        qty,
                        row.get("Sender", "").strip(),
                        row.get("Receiver", "").strip(),
                        row.get("ReceiveDate", "").strip(),
                        row.get("WarrantyDate", "").strip(),
                        barcode,
                        row.get("TicketNumber", "").strip(),
                        row.get("FromWhere", "").strip(),
                        row.get("SerialNumber", "").strip(),
                        row.get("HostName", "").strip(),
                        row.get("Note", "").strip()
                    ))

                if not rows_to_insert:
                    QMessageBox.warning(self, "Warning", "No valid data rows found in the CSV file.")
                    return

                conn = connect_db()
                cursor = conn.cursor()
                insert_query = """
                    INSERT INTO Inventory 
                    (DeviceName, DeviceType, Quantity, Sender, Receiver, ReceiveDate, WarrantyDate, Barcode, TicketNumber, FromWhere, SerialNumber, HostName, Note)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """
                cursor.executemany(insert_query, rows_to_insert)
                conn.commit()
                conn.close()

                try:
                    log_audit(
                        username=self.username,
                        action_type="IMPORT",
                        details=f"Batch imported {len(rows_to_insert)} items from '{os.path.basename(file_path)}'"
                    )
                except Exception:
                    pass

                QMessageBox.information(self, "Import Successful", f"Successfully imported {len(rows_to_insert)} item(s) into inventory.")
                self.refresh_all_data()

        except Exception as e:
            QMessageBox.critical(self, "Import Failed", f"An error occurred while reading the CSV:\n{e}")

    def export_to_csv(self):
        """ Opens custom export options dialog """
        dialog = ExportDialog(username=self.username, parent=self)
        dialog.exec_()

    def print_inventory_report(self):
        try:
            printer = QPrinter(QPrinter.HighResolution)
            dialog = QPrintDialog(printer, self)
            if dialog.exec_() == QDialog.Accepted:
                conn = connect_db()
                cursor = conn.cursor()
                cursor.execute("SELECT Id, DeviceName, DeviceType, Quantity, Receiver, ReceiveDate FROM Inventory")
                rows = cursor.fetchall()
                conn.close()

                html = "<h2>IT Warehouse - Inventory Report</h2>"
                html += f"<p><b>Generated by:</b> {self.username} | <b>Date:</b> {datetime.now().strftime('%Y-%m-%d %H:%M')}</p>"
                html += "<table border='1' cellspacing='0' cellpadding='6' style='width:100%; border-collapse:collapse; font-size:12px;'>"
                html += "<tr style='background-color:#F4F4F5;'><th>ID</th><th>Device Name</th><th>Type</th><th>Qty</th><th>Receiver</th><th>Date</th></tr>"
                for row in rows:
                    date_str = self.format_value_clean(row[5])
                    html += f"<tr><td align='center'>#{row[0]}</td><td>{row[1]}</td><td>{row[2]}</td><td align='center'>{row[3]}</td><td>{row[4]}</td><td>{date_str}</td></tr>"
                html += "</table>"

                doc = QTextDocument()
                doc.setHtml(html)
                doc.print_(printer)
                log_audit(self.username, "PRINT_REPORT", "Printed inventory summary report")
        except Exception as e:
            QMessageBox.critical(self, "Print Error", f"Failed to send job to printer:\n{e}")

    def _build_sidebar(self):
        sidebar = QFrame()
        sidebar.setFixedWidth(220)
        sidebar.setStyleSheet("""
            QFrame { background-color: #F9FAFB; border-right: 1px solid #E4E4E7; }
            QPushButton { text-align: left; padding: 12px 15px; font-size: 13px; font-weight: 600; color: #52525B; border: none; border-radius: 6px; margin: 2px 10px; }
            QPushButton:hover { background-color: #F4F4F5; color: #18181B; }
            QPushButton:checked { background-color: #1F2D3D; color: #FFFFFF; }
        """)
        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(0, 20, 0, 20)
        
        lbl_ws = QLabel("WORKSTATION")
        lbl_ws.setStyleSheet("font-size: 10px; font-weight: bold; color: #A1A1AA; letter-spacing: 1px; border: none; padding-left: 15px;")
        layout.addWidget(lbl_ws)
        
        self.buttons = []
        self.btn_dash = self._make_nav_button("Dashboard", 0)
        self.btn_inv = self._make_nav_button("Inventory", 1)
        
        btn_in = QPushButton("Stock In")
        btn_in.clicked.connect(self.open_stock_in)
        
        btn_out = QPushButton("Stock Out")
        btn_out.clicked.connect(self.open_stock_out)
        
        self.btn_hist = self._make_nav_button("History", 2)

        layout.addWidget(self.btn_dash)
        layout.addWidget(self.btn_inv)
        layout.addWidget(btn_in)
        layout.addWidget(btn_out)
        layout.addWidget(self.btn_hist)
        
        layout.addStretch()

        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setFrameShadow(QFrame.Sunken)
        line.setStyleSheet("border-top: 1px solid #E4E4E7; margin: 0px 15px;")
        layout.addWidget(line)
        
        lbl_storage = QLabel(" LOCAL STORAGE\n Automatic persistence is active.\n Data stored in SQL server.")
        lbl_storage.setStyleSheet("font-size: 10px; color: #71717A; border: none; padding-left: 15px; padding-top: 5px;")
        layout.addWidget(lbl_storage)
        
        self.btn_dash.setChecked(True)
        return sidebar

    def _make_nav_button(self, text, index):
        btn = QPushButton(text)
        btn.setCheckable(True)
        btn.clicked.connect(lambda: self.switch_tab(index, btn))
        self.buttons.append(btn)
        return btn

    def switch_tab(self, index, active_btn):
        self.stacked_widget.setCurrentIndex(index)
        for btn in self.buttons:
            btn.setChecked(False)
        active_btn.setChecked(True)

    def _build_dashboard_tab(self):
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setStyleSheet("QScrollArea { border: none; background-color: #FBFBFA; }")
        
        container = QWidget()
        container.setStyleSheet("background-color: #FBFBFA;")
        layout = QVBoxLayout(container)
        layout.setContentsMargins(40, 30, 40, 40)
        layout.setSpacing(25)

        title_row = QHBoxLayout()
        title_texts = QVBoxLayout()
        
        self.title_sup = QLabel()
        self.title_sup.setStyleSheet("color: #C2410C; font-size: 10px; font-weight: 800; letter-spacing: 1px;")
        
        title_main = QLabel("Operations desk")
        title_main.setStyleSheet("font-size: 26px; font-weight: bold; color: #101828;")
        title_sub = QLabel("A clear view of what is on the shelf, what moved recently, and what needs attention.")
        title_sub.setStyleSheet("font-size: 13px; color: #667085;")
        
        title_texts.addWidget(self.title_sup)
        title_texts.addWidget(title_main)
        title_texts.addWidget(title_sub)
        title_row.addLayout(title_texts)
        title_row.addStretch()
        
        btn_top_in = QPushButton("↓ Stock In")
        btn_top_in.setStyleSheet("background-color: white; border: 1px solid #D0D5DD; padding: 8px 16px; border-radius: 4px; font-weight: bold;")
        btn_top_in.clicked.connect(self.open_stock_in)
        
        btn_top_out = QPushButton("↑ Stock Out")
        btn_top_out.setStyleSheet("background-color: #1F2D3D; color: white; border: none; padding: 8px 16px; border-radius: 4px; font-weight: bold;")
        btn_top_out.clicked.connect(self.open_stock_out)
        
        title_row.addWidget(btn_top_in)
        title_row.addWidget(btn_top_out)
        layout.addLayout(title_row)

        kpi_row = QHBoxLayout()
        kpi_row.setSpacing(15)
        self.kpi_units = self._create_kpi_card("AVAILABLE UNITS", "0", "Across all catalog lines")
        self.kpi_lines = self._create_kpi_card("CATALOG LINES", "0", "Unique device models")
        self.kpi_trans = self._create_kpi_card("TRANSACTIONS", "0", "Local movement ledger")
        self.kpi_low = self._create_kpi_card("LOW STOCK WATCH", "0", "Lines at 3 units or less")
        
        kpi_row.addWidget(self.kpi_units)
        kpi_row.addWidget(self.kpi_lines)
        kpi_row.addWidget(self.kpi_trans)
        kpi_row.addWidget(self.kpi_low)
        layout.addLayout(kpi_row)

        charts_row = QHBoxLayout()
        charts_row.setSpacing(15)
        
        c1_frame = QFrame()
        c1_frame.setStyleSheet("background-color: #FFFFFF; border: 1px solid #E4E4E7; border-radius: 6px;")
        c1_layout = QVBoxLayout(c1_frame)
        c1_header = QHBoxLayout()
        c1_title = QLabel("Device names")
        c1_title.setStyleSheet("font-weight: bold; border: none;")
        c1_header.addWidget(c1_title)
        c1_header.addStretch()
        c1_header.addWidget(QLabel("<span style='color:#A1A1AA; font-size:10px; border:none;'>units on hand</span>"))
        c1_layout.addLayout(c1_header)
        
        self.chart_names = DonutChartCanvas(self, width=4, height=3)
        c1_layout.addWidget(self.chart_names)
        charts_row.addWidget(c1_frame)

        c2_frame = QFrame()
        c2_frame.setStyleSheet("background-color: #FFFFFF; border: 1px solid #E4E4E7; border-radius: 6px;")
        c2_layout = QVBoxLayout(c2_frame)
        c2_header = QHBoxLayout()
        c2_title = QLabel("Device types")
        c2_title.setStyleSheet("font-weight: bold; border: none;")
        c2_header.addWidget(c2_title)
        c2_header.addStretch()
        c2_header.addWidget(QLabel("<span style='color:#A1A1AA; font-size:10px; border:none;'>units on hand</span>"))
        c2_layout.addLayout(c2_header)
        
        self.chart_types = DonutChartCanvas(self, width=4, height=3)
        c2_layout.addWidget(self.chart_types)
        charts_row.addWidget(c2_frame)
        
        layout.addLayout(charts_row)

        table_frame = QFrame()
        table_frame.setStyleSheet("background-color: #FFFFFF; border: 1px solid #E4E4E7; border-radius: 6px;")
        table_layout = QVBoxLayout(table_frame)
        
        tbl_header = QHBoxLayout()
        tbl_title = QLabel("Recent inventory records")
        tbl_title.setStyleSheet("font-weight: bold; border: none;")
        tbl_header.addWidget(tbl_title)
        tbl_header.addStretch()
        tbl_header.addWidget(QLabel("<span style='color:#A1A1AA; font-size:10px; border:none;'>latest records</span>"))
        table_layout.addLayout(tbl_header)
        
        self.dash_table = QTableWidget(0, 6)
        self.dash_table.setHorizontalHeaderLabels(["ID", "DEVICE NAME", "TYPE", "QTY", "RECEIVER", "DATE"])
        self.dash_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.dash_table.verticalHeader().setVisible(False)
        self.dash_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.dash_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.dash_table.setFocusPolicy(Qt.NoFocus)
        self.dash_table.setStyleSheet("""
            QTableWidget { border: none; background-color: white; color: #3F3F46; font-size: 12px; }
            QHeaderView::section { background-color: #FAFAFA; border: none; border-bottom: 1px solid #E4E4E7; padding: 8px; font-weight: bold; font-size: 10px; color: #71717A; text-align: left; }
            QTableWidget::item { padding: 8px; border-bottom: 1px solid #F4F4F5; }
        """)
        table_layout.addWidget(self.dash_table)
        
        layout.addWidget(table_frame)
        layout.addStretch()
        
        scroll_area.setWidget(container)
        return scroll_area

    def _build_inventory_tab(self):
        container = QWidget()
        container.setStyleSheet("background-color: #FBFBFA;")
        layout = QVBoxLayout(container)
        layout.setContentsMargins(40, 30, 40, 40)
        layout.setSpacing(15)
        
        header_layout = QHBoxLayout()
        title_layout = QVBoxLayout()
        
        lbl_sup = QLabel("SHELF REGISTER / LIVE VIEW")
        lbl_sup.setStyleSheet("color: #C2410C; font-size: 10px; font-weight: 800; letter-spacing: 1px;")
        lbl_title = QLabel("All Inventory")
        lbl_title.setStyleSheet("font-size: 26px; font-weight: bold; color: #101828;")
        
        title_layout.addWidget(lbl_sup)
        title_layout.addWidget(lbl_title)
        
        header_layout.addLayout(title_layout)
        header_layout.addStretch()

        # Import CSV Button
        self.btn_import_csv = QPushButton("📥 Import CSV")
        self.btn_import_csv.setStyleSheet("background-color: #FFFFFF; color: #1F2D3D; border: 1px solid #D0D5DD; padding: 8px 16px; border-radius: 4px; font-weight: bold;")
        self.btn_import_csv.clicked.connect(self.import_csv)
        header_layout.addWidget(self.btn_import_csv)

        # Export CSV Button (Placed side-by-side with Import CSV)
        self.btn_export_csv = QPushButton("📤 Export CSV")
        self.btn_export_csv.setStyleSheet("background-color: #FFFFFF; color: #1F2D3D; border: 1px solid #D0D5DD; padding: 8px 16px; border-radius: 4px; font-weight: bold;")
        self.btn_export_csv.clicked.connect(self.export_to_csv)
        header_layout.addWidget(self.btn_export_csv)

        self.btn_view_details = QPushButton("👁 View Details")
        self.btn_view_details.setStyleSheet("background-color: #FFFFFF; color: #1F2D3D; border: 1px solid #D0D5DD; padding: 8px 16px; border-radius: 4px; font-weight: bold;")
        self.btn_view_details.clicked.connect(self.show_inventory_details)
        header_layout.addWidget(self.btn_view_details)

        self.btn_delete_inventory = QPushButton("🗑 Delete Selected Item")
        self.btn_delete_inventory.setStyleSheet("background-color: #EF4444; color: white; border: none; padding: 8px 16px; border-radius: 4px; font-weight: bold;")
        self.btn_delete_inventory.clicked.connect(self.delete_inventory_item)
        
        current_role_clean = str(self.user_role).strip().lower() if self.user_role else ""
        if current_role_clean != "admin":
            self.btn_delete_inventory.hide()
            
        header_layout.addWidget(self.btn_delete_inventory)
        layout.addLayout(header_layout)
        
        self.inventory_table = QTableWidget(0, 0)
        self.inventory_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.inventory_table.horizontalHeader().setStretchLastSection(True)
        self.inventory_table.verticalHeader().setVisible(False)
        self.inventory_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.inventory_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.inventory_table.setFocusPolicy(Qt.NoFocus)
        self.inventory_table.setStyleSheet("""
            QTableWidget { border: 1px solid #E4E4E7; border-radius: 6px; background-color: white; color: #3F3F46; font-size: 12px; }
            QHeaderView::section { background-color: #FAFAFA; border: none; border-bottom: 1px solid #E4E4E7; padding: 8px; font-weight: bold; font-size: 10px; color: #71717A; text-align: left; }
            QTableWidget::item { padding: 8px; border-bottom: 1px solid #F4F4F5; }
        """)
        
        self.inventory_table.itemDoubleClicked.connect(self.show_inventory_details)

        layout.addWidget(self.inventory_table)
        return container

    def show_inventory_details(self):
        row = self.inventory_table.currentRow()
        if row < 0:
            QMessageBox.warning(self, "Selection Error", "Please select an inventory item row to view its details.")
            return
            
        item_id_item = self.inventory_table.item(row, 0)
        if not item_id_item:
            return
        item_id = item_id_item.text().replace("#", "").strip()

        try:
            self._ensure_database_schema()
            conn = connect_db()
            cursor = conn.cursor()

            cursor.execute("SELECT * FROM Inventory WHERE Id = ?", (item_id,))
            row_data = cursor.fetchone()
            columns = [col[0] for col in cursor.description] if cursor.description else []
            conn.close()

            if not row_data:
                QMessageBox.warning(self, "Error", "Selected inventory item could not be found in the database.")
                return

            db_data = {col_name: self.format_value_clean(val) for col_name, val in zip(columns, row_data)}

            ordered_fields = [
                ("Id", "Id"),
                ("DeviceName", "Device Name"),
                ("DeviceType", "Device Type"),
                ("Quantity", "Quantity"),
                ("Barcode", "Barcode"),
                ("SerialNumber", "Serial Number"),
                ("HostName", "Host Name"),
                ("Sender", "Sender"),
                ("WarrantyDate", "Warranty Date"),
                ("TicketNumber", "Ticket Number"),
                ("FromWhere", "From Where"),
                ("Receiver", "Receiver"),
                ("ReceiveDate", "Receive Date"),
                ("Note", "Note")
            ]

            item_data = {}
            for col_key, display_label in ordered_fields:
                val = db_data.get(col_key, db_data.get(display_label, "-"))
                item_data[display_label] = val if val != "" else "-"

            for col_name in columns:
                clean_name = self._format_key_name_helper(col_name)
                if clean_name not in item_data:
                    val = db_data.get(col_name, "-")
                    item_data[clean_name] = val if val != "" else "-"

            dialog = ItemDetailsDialog(item_data, self)
            dialog.exec_()
        except Exception as e:
            QMessageBox.critical(self, "Database Error", f"Failed to fetch item details from database:\n{e}")

    def delete_inventory_item(self):
        selected_row = self.inventory_table.currentRow()
        if selected_row < 0:
            QMessageBox.warning(self, "Selection Error", "Please select an inventory item row from the 'All Inventory' tab to delete.")
            return
            
        item = self.inventory_table.item(selected_row, 0)
        if not item or not item.text():
            QMessageBox.warning(self, "Selection Error", "Could not identify the item ID of the selected row.")
            return

        item_id = item.text().replace("#", "").strip()

        reply = QMessageBox.question(
            self, 
            "Confirm Deletion", 
            f"Are you sure you want to permanently delete inventory item #{item_id}?", 
            QMessageBox.Yes | QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            try:
                conn = connect_db()
                cursor = conn.cursor()
                cursor.execute("DELETE FROM Inventory WHERE Id = ?", (item_id,))
                conn.commit()
                conn.close()

                log_audit(self.username, "INVENTORY_DELETE", f"Deleted inventory item #{item_id}")
                QMessageBox.information(self, "Success", f"Inventory item #{item_id} deleted successfully.")
                self.refresh_all_data()
            except Exception as e:
                QMessageBox.critical(self, "Database Error", f"Failed to delete item:\n{e}")

    def _build_history_tab(self):
        container = QWidget()
        container.setStyleSheet("background-color: #FBFBFA;")
        layout = QVBoxLayout(container)
        layout.setContentsMargins(40, 30, 40, 40)
        
        header_layout = QHBoxLayout()
        title_layout = QVBoxLayout()
        
        lbl_sup = QLabel("AUDIT TRAIL / APPEND ONLY")
        lbl_sup.setStyleSheet("color: #C2410C; font-size: 10px; font-weight: 800; letter-spacing: 1px;")
        lbl_title = QLabel("History & Audit Logs")
        lbl_title.setStyleSheet("font-size: 26px; font-weight: bold; color: #101828;")
        
        title_layout.addWidget(lbl_sup)
        title_layout.addWidget(lbl_title)
        
        header_layout.addLayout(title_layout)
        header_layout.addStretch()

        self.btn_view_hist_details = QPushButton("👁 View Details")
        self.btn_view_hist_details.setStyleSheet("background-color: #FFFFFF; color: #1F2D3D; border: 1px solid #D0D5DD; padding: 8px 16px; border-radius: 4px; font-weight: bold;")
        self.btn_view_hist_details.clicked.connect(self.show_history_details)
        header_layout.addWidget(self.btn_view_hist_details)

        self.btn_delete_history = QPushButton("🗑 Delete Selected Log")
        self.btn_delete_history.setStyleSheet("background-color: #EF4444; color: white; border: none; padding: 8px 16px; border-radius: 4px; font-weight: bold;")
        self.btn_delete_history.clicked.connect(self.delete_history_record)
        
        current_role_clean = str(self.user_role).strip().lower() if self.user_role else ""
        if current_role_clean != "admin":
            self.btn_delete_history.hide()
            
        header_layout.addWidget(self.btn_delete_history)
        layout.addLayout(header_layout)
        
        self.history_table = QTableWidget(0, 0)
        self.history_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.history_table.horizontalHeader().setStretchLastSection(True)
        self.history_table.verticalHeader().setVisible(False)
        self.history_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.history_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.history_table.setStyleSheet("""
            QTableWidget { border: 1px solid #E4E4E7; border-radius: 6px; background-color: white; color: #3F3F46; font-size: 12px; }
            QHeaderView::section { background-color: #FAFAFA; border: none; border-bottom: 1px solid #E4E4E7; padding: 8px; font-weight: bold; font-size: 10px; color: #71717A; text-align: left; }
            QTableWidget::item { padding: 8px; border-bottom: 1px solid #F4F4F5; }
        """)

        self.history_table.itemDoubleClicked.connect(self.show_history_details)

        layout.addWidget(self.history_table)
        return container

    def show_history_details(self):
        row = self.history_table.currentRow()
        if row < 0:
            QMessageBox.warning(self, "Selection Error", "Please select a history log row to view its details.")
            return
            
        log_id_item = self.history_table.item(row, 0)
        if not log_id_item:
            return
        log_id = log_id_item.text().replace("#", "").strip()

        try:
            self._ensure_database_schema()
            conn = connect_db()
            cursor = conn.cursor()
            try:
                cursor.execute("SELECT * FROM AuditLogs WHERE Id = ?", (log_id,))
            except Exception:
                cursor.execute("SELECT * FROM AuditLogs WHERE LogId = ?", (log_id,))

            row_data = cursor.fetchone()
            columns = [col[0] for col in cursor.description] if cursor.description else []
            conn.close()

            if not row_data:
                QMessageBox.warning(self, "Error", "Selected audit log record could not be found in the database.")
                return

            db_data = {col_name: self.format_value_clean(val) for col_name, val in zip(columns, row_data)}

            ordered_fields = [
                ("Id", "Id"),
                ("Username", "Username"),
                ("Action", "Action"),
                ("Details", "Details"),
                ("Sender", "Sender"),
                ("WarrantyDate", "Warranty Date"),
                ("TicketNumber", "Ticket Number"),
                ("FromWhere", "From Where"),
                ("Timestamp", "Timestamp")
            ]

            item_data = {}
            for col_key, display_label in ordered_fields:
                val = db_data.get(col_key, db_data.get(display_label, "-"))
                item_data[display_label] = val if val != "" else "-"

            for col_name in columns:
                clean_name = self._format_key_name_helper(col_name)
                if clean_name not in item_data:
                    val = db_data.get(col_name, "-")
                    item_data[clean_name] = val if val != "" else "-"

            dialog = ItemDetailsDialog(item_data, self)
            dialog.exec_()
        except Exception as e:
            QMessageBox.critical(self, "Database Error", f"Failed to fetch history details from database:\n{e}")

    def delete_history_record(self):
        selected_row = self.history_table.currentRow()
        if selected_row < 0:
            QMessageBox.warning(self, "Selection Error", "Please select a history record row to delete.")
            return
            
        item = self.history_table.item(selected_row, 0)
        if not item or not item.text():
            QMessageBox.warning(self, "Selection Error", "Could not identify the record ID of the selected row.")
            return

        log_id = item.text().replace("#", "").strip()

        reply = QMessageBox.question(
            self, 
            "Confirm Deletion", 
            f"Are you sure you want to permanently delete audit log record #{log_id}?", 
            QMessageBox.Yes | QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            try:
                conn = connect_db()
                cursor = conn.cursor()
                try:
                    cursor.execute("DELETE FROM AuditLogs WHERE Id = ?", (log_id,))
                except Exception:
                    cursor.execute("DELETE FROM AuditLogs WHERE LogId = ?", (log_id,))

                conn.commit()
                conn.close()

                QMessageBox.information(self, "Success", f"Log record #{log_id} deleted successfully.")
                self.refresh_all_data()
            except Exception as e:
                QMessageBox.critical(self, "Database Error", f"Failed to delete record:\n{e}")

    def _create_kpi_card(self, title, val, sub):
        frame = QFrame()
        frame.setStyleSheet("background-color: #FFFFFF; border: 1px solid #E4E4E7; border-radius: 6px;")
        frame.setFixedHeight(100)
        layout = QVBoxLayout(frame)
        
        lbl_title = QLabel(title)
        lbl_title.setStyleSheet("font-size: 10px; color: #A1A1AA; font-weight: bold; letter-spacing: 0.5px; border: none;")
        
        lbl_val = QLabel(val)
        lbl_val.setStyleSheet("font-size: 28px; font-weight: bold; color: #18181B; border: none;")
        
        lbl_sub = QLabel(sub)
        lbl_sub.setStyleSheet("font-size: 11px; color: #71717A; border: none;")
        
        layout.addWidget(lbl_title)
        layout.addWidget(lbl_val)
        layout.addWidget(lbl_sub)
        return frame

    def refresh_all_data(self):
        self.load_dashboard_data()
        self.load_inventory_data()
        self.load_history_data()

    def format_value_clean(self, value):
        if value is None or str(value).strip() in ("", "None"):
            return ""
        
        if isinstance(value, datetime):
            return value.strftime("%Y-%m-%d %H:%M")
        
        if isinstance(value, date):
            return f"{value.strftime('%Y-%m-%d')} 00:00"

        val_str = str(value).strip()
        
        match_dt = re.match(r"^(\d{4}-\d{2}-\d{2})[ T](\d{2}:\d{2})(:\d{2})?", val_str)
        if match_dt:
            return f"{match_dt.group(1)} {match_dt.group(2)}"
        
        match_d = re.match(r"^(\d{4}-\d{2}-\d{2})$", val_str)
        if match_d:
            return f"{match_d.group(1)} 00:00"

        return val_str

    def _format_key_name_helper(self, key):
        clean = key.replace("_", " ")
        clean = re.sub(r'([a-z])([A-Z])', r'\1 \2', clean)
        return clean.title()

    def load_dashboard_data(self):
        try:
            current_day = datetime.now().strftime("%A").upper()
            self.title_sup.setText(f"{current_day} / WAREHOUSE CONTROL")

            conn = connect_db()
            cursor = conn.cursor()

            cursor.execute("SELECT ISNULL(SUM(Quantity), 0) FROM Inventory")
            self.kpi_units.findChildren(QLabel)[1].setText(str(cursor.fetchone()[0]))

            cursor.execute("SELECT COUNT(DISTINCT DeviceName) FROM Inventory")
            self.kpi_lines.findChildren(QLabel)[1].setText(str(cursor.fetchone()[0]))

            cursor.execute("SELECT COUNT(*) FROM AuditLogs")
            self.kpi_trans.findChildren(QLabel)[1].setText(str(cursor.fetchone()[0]))

            cursor.execute("SELECT COUNT(*) FROM Inventory WHERE Quantity <= 3")
            self.kpi_low.findChildren(QLabel)[1].setText(str(cursor.fetchone()[0]))

            cursor.execute("SELECT TOP 5 DeviceName, SUM(Quantity) FROM Inventory GROUP BY DeviceName ORDER BY SUM(Quantity) DESC")
            data_names = {row[0]: row[1] for row in cursor.fetchall()}
            self.chart_names.update_chart(data_names)

            cursor.execute("SELECT ISNULL(DeviceType, 'Uncategorized'), SUM(Quantity) FROM Inventory GROUP BY DeviceType")
            data_types = {row[0]: row[1] for row in cursor.fetchall()}
            self.chart_types.update_chart(data_types)

            cursor.execute("SELECT TOP 10 Id, DeviceName, DeviceType, Quantity, Receiver, ReceiveDate FROM Inventory ORDER BY Id DESC")
            rows = cursor.fetchall()
            self.dash_table.setRowCount(0)
            for row_idx, row_data in enumerate(rows):
                self.dash_table.insertRow(row_idx)
                for col_idx, value in enumerate(row_data):
                    if col_idx == 0:
                        val_str = f"#{value}"
                    elif col_idx == 5:
                        val_str = self.format_value_clean(value)
                    else:
                        val_str = str(value) if value is not None else ""
                    
                    item = QTableWidgetItem(val_str)
                    if col_idx in [0, 3]:
                        item.setTextAlignment(Qt.AlignCenter | Qt.AlignVCenter)
                    else:
                        item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
                    self.dash_table.setItem(row_idx, col_idx, item)

            conn.close()
        except Exception as e:
            QMessageBox.critical(self, "Database Fetch Error", str(e))

    def load_inventory_data(self):
        try:
            conn = connect_db()
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM Inventory")
            
            raw_columns = [col[0] for col in cursor.description] if cursor.description else []
            
            display_columns = [c for c in raw_columns if c.lower() != 'note']
            note_cols = [c for c in raw_columns if c.lower() == 'note']
            display_columns.extend(note_cols)

            col_indices = [raw_columns.index(c) for c in display_columns]

            self.inventory_table.setColumnCount(len(display_columns))
            self.inventory_table.setHorizontalHeaderLabels([col.upper() for col in display_columns])
            
            rows = cursor.fetchall()
            self.inventory_table.setRowCount(0)
            for row_idx, row_data in enumerate(rows):
                self.inventory_table.insertRow(row_idx)
                for new_col_idx, orig_col_idx in enumerate(col_indices):
                    value = row_data[orig_col_idx]
                    val_str = self.format_value_clean(value)
                    item = QTableWidgetItem(val_str)
                    if new_col_idx == 0:
                        item.setTextAlignment(Qt.AlignCenter | Qt.AlignVCenter)
                    else:
                        item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
                    self.inventory_table.setItem(row_idx, new_col_idx, item)
            conn.close()
        except Exception as e:
            QMessageBox.critical(self, "Database Fetch Error", str(e))

    def load_history_data(self):
        try:
            conn = connect_db()
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM AuditLogs")
            
            raw_columns = [col[0] for col in cursor.description] if cursor.description else []
            
            display_columns = [c for c in raw_columns if c.lower() not in ('note', 'details')]
            trailing_cols = [c for c in raw_columns if c.lower() in ('details', 'note')]
            display_columns.extend(trailing_cols)

            col_indices = [raw_columns.index(c) for c in display_columns]

            self.history_table.setColumnCount(len(display_columns))
            self.history_table.setHorizontalHeaderLabels([col.upper() for col in display_columns])
            
            rows = cursor.fetchall()
            self.history_table.setRowCount(0)
            for row_idx, row_data in enumerate(rows):
                self.history_table.insertRow(row_idx)
                for new_col_idx, orig_col_idx in enumerate(col_indices):
                    value = row_data[orig_col_idx]
                    val_str = self.format_value_clean(value)
                    item = QTableWidgetItem(val_str)
                    if new_col_idx == 0:
                        item.setTextAlignment(Qt.AlignCenter | Qt.AlignVCenter)
                    else:
                        item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
                    self.history_table.setItem(row_idx, new_col_idx, item)
            conn.close()
        except Exception as e:
            QMessageBox.critical(self, "Database Fetch Error", str(e))

    def open_stock_in(self):
        dialog = StockInDialog(self)
        if dialog.exec_() == QDialog.Accepted:
            self.refresh_all_data()

    def open_stock_out(self):
        dialog = StockOutDialog(username=self.username, parent=self)
        if dialog.exec_() == QDialog.Accepted:
            self.refresh_all_data()

    def open_users(self):
        dialog = UserManagementDialog(
            current_username=self.username, 
            current_role=self.user_role, 
            parent=self
        )
        dialog.exec_()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    
    try:
        init_db()
    except Exception as e:
        QMessageBox.critical(None, "Startup Error", f"Failed to connect to database:\n{e}")
        sys.exit(1)

    login = LoginDialog()
    if login.exec_() == QDialog.Accepted:
        main_win = MainWindow(username=login.username, user_role=login.user_role)
        main_win.show()
        sys.exit(app.exec_())
    else:
        sys.exit(0)