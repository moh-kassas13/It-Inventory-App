import sys
import ctypes
import os
import csv
import re
import time
from datetime import datetime, date

import pyodbc
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QTableWidget, QTableWidgetItem, QHeaderView, QPushButton, QLabel,
    QFrame, QMessageBox, QDialog, QScrollArea, QAbstractItemView,
    QStackedWidget, QMenuBar, QAction, QLineEdit, QComboBox,
    QFileDialog, QFormLayout, QGroupBox, QCheckBox, QDateEdit,
    QShortcut, QSizePolicy
)
from PyQt5.QtCore import Qt, QDate
from PyQt5.QtGui import QIcon, QPixmap, QKeySequence, QTextDocument
from PyQt5.QtPrintSupport import QPrinter, QPrintDialog

from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure

from database import init_db, connect_db, log_audit, get_resource_path
from auth import LoginDialog, find_logo_path
from dialogs import StockInDialog, StockOutDialog, ExportDialog
from report_feature import open_report_dialog

# Force Windows Taskbar to use custom icon
if sys.platform == 'win32':
    myappid = 'aubmc.itwarehouse.app.3.0'
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)


def connect_with_retry(max_retries=5, delay=3):
    """
    Attempts to connect to SQL Server. 
    Retries up to 5 times with a 3-second delay to allow the background service to start.
    """
    conn_str = (
        "DRIVER={ODBC Driver 17 for SQL Server};"
        "SERVER=.\\SQLEXPRESS;"
        "DATABASE=master;"  # or WarehouseDB
        "Trusted_Connection=yes;"
    )
    
    for attempt in range(1, max_retries + 1):
        try:
            connection = pyodbc.connect(conn_str, timeout=5)
            return connection
        except pyodbc.Error as e:
            if attempt < max_retries:
                time.sleep(delay)
            else:
                raise e


def load_absolute_app_icon():
    """Locates and returns the application icon using strict absolute path resolution."""
    base_dir = os.path.dirname(os.path.abspath(__file__))
    candidates = [
        os.path.join(base_dir, "assets", "logo.ico"),
        os.path.join(base_dir, "assets", "logo.png"),
        os.path.join(base_dir, "logo.ico"),
        os.path.join(base_dir, "logo.png"),
    ]
    for path in candidates:
        if os.path.exists(path):
            return QIcon(path)
    return QIcon()


# ==========================================
# USER MANAGEMENT DIALOG
# ==========================================
class UserManagementDialog(QDialog):
    def __init__(self, current_username, current_role, parent=None):
        super().__init__(parent)
        self.current_username = current_username
        self.current_role = str(current_role).strip().lower()
        self.is_admin = self.current_role in ['admin', 'administrator']

        if not self.is_admin:
            QMessageBox.warning(parent or self, "Access Denied", "Only administrators can access user management.")
            self.reject()
            return

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
        
        self.btn_delete = QPushButton("🗑 Delete Selected User")
        self.btn_delete.setStyleSheet("background-color: #EF4444; color: white; border: none; padding: 6px 14px; border-radius: 4px; font-weight: bold;")
        self.btn_delete.clicked.connect(self.delete_user)
        
        if not self.is_admin:
            self.btn_delete.hide()
            
        layout.addWidget(self.btn_delete, alignment=Qt.AlignRight)

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
        self.combo_role.addItems(["Admin", "User"])
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
        conn = None
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
        except Exception as e:
            QMessageBox.critical(self, "Database Error", str(e))
        finally:
            if conn:
                conn.close()

    def add_user(self):
        username = self.input_user.text().strip()
        password = self.input_pass.text().strip()
        role = self.combo_role.currentText()

        if not username or not password:
            QMessageBox.warning(self, "Validation Error", "Username and Password cannot be empty.")
            return

        conn = None
        try:
            conn = connect_db()
            cursor = conn.cursor()
            cursor.execute("INSERT INTO Users (Username, Password, Role) VALUES (?, ?, ?)", (username, password, role))
            conn.commit()

            log_audit(self.current_username, "USER_ADD", f"Created user '{username}' with role '{role}'")
            QMessageBox.information(self, "Success", f"User '{username}' added successfully!")

            self.input_user.clear()
            self.input_pass.clear()
            self.load_users()
        except Exception as e:
            QMessageBox.critical(self, "Error Adding User", f"Could not add user. Username may already exist.\n\nError: {e}")
        finally:
            if conn:
                conn.close()

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
            conn = None
            try:
                conn = connect_db()
                cursor = conn.cursor()
                cursor.execute("DELETE FROM Users WHERE Id = ?", (user_id,))
                conn.commit()

                log_audit(self.current_username, "USER_DELETE", f"Deleted user '{username}'")
                QMessageBox.information(self, "Success", f"User '{username}' was deleted.")
                self.load_users()
            except Exception as e:
                QMessageBox.critical(self, "Database Error", f"Failed to delete user:\n{e}")
            finally:
                if conn:
                    conn.close()


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

        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.updateGeometry()

    def update_chart(self, data_dict, max_items=6):
        self.axes.clear()
        
        if not data_dict:
            self.axes.text(0, 0, "No data", horizontalalignment='center', verticalalignment='center', color="#667085")
            self.draw()
            return

        sorted_items = sorted(data_dict.items(), key=lambda x: x[1], reverse=True)
        if len(sorted_items) > max_items:
            top_items = dict(sorted_items[:max_items - 1])
            top_items["Other"] = sum(val for _, val in sorted_items[max_items - 1:])
            data_dict = top_items

        labels = list(data_dict.keys())
        sizes = list(data_dict.values())
        total = sum(sizes)
        
        colors = ['#3B5998', '#D97757', '#5C8A8A', '#D9A05B', '#6B5B95', '#88B04B', '#94A3B8']

        wedges, _ = self.axes.pie(
            sizes, 
            colors=colors[:len(sizes)], 
            startangle=90, 
            wedgeprops=dict(width=0.28, edgecolor='#FFFFFF', linewidth=2)
        )

        self.axes.text(0, 0.05, f"{total:,}", horizontalalignment='center', verticalalignment='center', fontsize=16, fontweight='bold', color="#101828")
        self.axes.text(0, -0.12, "units", horizontalalignment='center', verticalalignment='center', fontsize=9, color="#667085")
        
        legend_labels = [f"{lbl} ({val})" for lbl, val in zip(labels, sizes)]
        self.axes.legend(
            wedges, 
            legend_labels,
            title="Legend", 
            loc="center left", 
            bbox_to_anchor=(1.02, 0.5),
            frameon=False, 
            fontsize=8,
            title_fontsize=9,
            labelspacing=0.5
        )

        self.figure.subplots_adjust(left=0.05, right=0.58, top=0.92, bottom=0.08)
        self.draw()


# ==========================================
# MAIN WINDOW
# ==========================================
class MainWindow(QMainWindow):
    def __init__(self, username, user_role):
        super().__init__()
        self.username = username
        self.user_role = user_role

        self.is_admin = str(self.user_role).strip().lower() in ['admin', 'administrator']

        self.cached_total_qty = 0
        self.cached_total_unit_price = 0.0
        self.cached_total_price = 0.0

        self.setWindowTitle("Inventory Desk - Operations")
        self.setGeometry(50, 50, 1400, 850)
        self.setStyleSheet("QMainWindow { background-color: #FBFBFA; }")
        
        app_icon = load_absolute_app_icon()
        if not app_icon.isNull():
            self.setWindowIcon(app_icon)

        self._ensure_database_schema()
        self._init_ui()
        self.apply_user_permissions()
        self.refresh_all_data()

    def closeEvent(self, event):
        """Executes when the main window is closed to cleanly terminate all processes."""
        import matplotlib.pyplot as plt
        plt.close('all')
        event.accept()
        QApplication.quit()

    def apply_user_permissions(self):
        """Restricts UI access for non-admin accounts."""
        if hasattr(self, 'tab_widget'):
            for i in range(self.tab_widget.count()):
                tab_name = self.tab_widget.tabText(i).strip().lower()
                if tab_name in ["history", "audit logs", "audit log"]:
                    self.tab_widget.setTabVisible(i, self.is_admin)

        if hasattr(self, 'btn_hist'):
            self.btn_hist.setVisible(self.is_admin)
        if hasattr(self, 'btn_history'):
            self.btn_history.setVisible(self.is_admin)
        if hasattr(self, 'action_history'):
            self.action_history.setVisible(self.is_admin)

        if hasattr(self, 'manage_btn'):
            self.manage_btn.setVisible(self.is_admin)
        if hasattr(self, 'users_action'):
            self.users_action.setVisible(self.is_admin)

    def open_history(self):
        """Action handler to switch to or display History, guarded with an admin check."""
        if not self.is_admin:
            QMessageBox.warning(self, "Access Denied", "Only administrators can view History.")
            return

        if hasattr(self, 'stacked_widget'):
            self.switch_tab(2, getattr(self, 'btn_hist', None))

    def _ensure_database_schema(self):
        """Ensure required fields exist in the Inventory and AuditLogs tables."""
        conn = None
        try:
            conn = connect_db()
            cursor = conn.cursor()
            
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
        except Exception as e:
            print(f"Schema verification warning: {e}")
        finally:
            if conn:
                conn.close()

    def _init_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        top_header = self._build_top_header()
        main_layout.addWidget(top_header)

        body_layout = QHBoxLayout()
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(0)

        sidebar = self._build_sidebar()
        body_layout.addWidget(sidebar)

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

        self.report_button = QPushButton("Generate Report")
        self.report_button.setStyleSheet("""
            QPushButton {
                background-color: #F4F4F5;
                border: 1px solid #E4E4E7;
                padding: 6px 12px;
                border-radius: 4px;
                font-weight: bold;
                color: #1F2D3D;
                font-size: 11px;
            }
            QPushButton:hover {
                background-color: #E4E4E7;
            }
        """)
        self.report_button.clicked.connect(
            lambda: open_report_dialog(self, current_username=getattr(self, 'username', getattr(self, 'logged_in_user', '')))
        )
        brand_row.addWidget(self.report_button)
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
        
        if not self.is_admin:
            delete_action.setEnabled(False)
            
        edit_menu.addAction(delete_action)

        edit_menu.addSeparator()

        self.users_action = QAction("👤 User Management", self)
        self.users_action.triggered.connect(self.open_users)
        edit_menu.addAction(self.users_action)

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

        self.action_history = QAction("📜 History & Audit Logs View", self)
        self.action_history.setShortcut(QKeySequence("Ctrl+3"))
        self.action_history.triggered.connect(lambda: self.switch_tab(2, self.btn_hist))
        view_menu.addAction(self.action_history)

        toolbar_row.addWidget(menu_bar)
        toolbar_row.addStretch()
        
        self.user_info_label = QLabel(f"👤 {self.username} - {self.user_role}")
        self.user_info_label.setStyleSheet("font-size: 11px; color: #71717A;")
        toolbar_row.addWidget(self.user_info_label)
        
        self.manage_btn = QPushButton("Manage users")
        self.manage_btn.setStyleSheet("border: 1px solid #D4D4D8; background: white; padding: 4px 8px; border-radius: 4px; font-size: 11px;")
        self.manage_btn.clicked.connect(self.open_users)
        toolbar_row.addWidget(self.manage_btn)

        self.logout_btn = QPushButton("Logout")
        self.logout_btn.setStyleSheet("border: 1px solid #D4D4D8; background: #FEE2E2; color: #991B1B; padding: 4px 8px; border-radius: 4px; font-size: 11px;")
        self.logout_btn.clicked.connect(self.logout)
        toolbar_row.addWidget(self.logout_btn)

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

        conn = None
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
        finally:
            if conn:
                conn.close()

    def export_to_csv(self):
        """Opens custom export options dialog."""
        dialog = ExportDialog(username=self.username, parent=self)
        dialog.exec_()

    def print_inventory_report(self):
        conn = None
        try:
            printer = QPrinter(QPrinter.HighResolution)
            dialog = QPrintDialog(printer, self)
            if dialog.exec_() == QDialog.Accepted:
                conn = connect_db()
                cursor = conn.cursor()
                cursor.execute("SELECT Id, DeviceName, DeviceType, Quantity, Receiver, ReceiveDate FROM Inventory")
                rows = cursor.fetchall()

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
        finally:
            if conn:
                conn.close()

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

    def switch_tab(self, index, button):
        """Switches stacked widget view while enforcing admin role requirements."""
        if index == 2 and not self.is_admin:
            QMessageBox.warning(self, "Access Denied", "Only administrators can view History.")
            return

        self.stacked_widget.setCurrentIndex(index)
        if hasattr(self, 'buttons'):
            for btn in self.buttons:
                btn.setChecked(btn == button)

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

        self.search_combo = QComboBox(self)
        self.search_combo.addItems([
            "All Columns", 
            "Device Name", 
            "Device Type", 
            "Quantity", 
            "Sender", 
            "Receiver", 
            "Date & Time Receiving", 
            "Warranty Date", 
            "Barcode", 
            "Ticket Number", 
            "From Where", 
            "Serial Number", 
            "Hostname", 
            "Price Per Unit", 
            "Total Price", 
            "Notes"
        ])
        self.search_combo.setToolTip("Select column attribute to filter by")
        self.search_combo.setStyleSheet("""
            QComboBox {
                background-color: #FFFFFF;
                color: #1F2D3D;
                border: 1px solid #D0D5DD;
                border-radius: 4px;
                padding: 6px 12px;
                font-size: 12px;
                min-width: 140px;
            }
        """)

        self.search_input = QLineEdit(self)
        self.search_input.setPlaceholderText("Search inventory... (Ctrl+F)")
        self.search_input.setClearButtonEnabled(True)
        self.search_input.setStyleSheet("""
            QLineEdit {
                background-color: #FFFFFF;
                color: #1F2D3D;
                border: 1px solid #D0D5DD;
                border-radius: 4px;
                padding: 6px 12px;
                font-size: 12px;
                min-width: 180px;
            }
            QLineEdit:focus {
                border-color: #0078D7;
            }
        """)

        header_layout.addWidget(self.search_combo)
        header_layout.addWidget(self.search_input)

        self.search_input.textChanged.connect(self.filter_inventory_table)
        self.search_combo.currentIndexChanged.connect(self.filter_inventory_table)

        self.shortcut_find = QShortcut(QKeySequence("Ctrl+F"), self)
        self.shortcut_find.activated.connect(self.focus_search_bar)

        self.btn_import_csv = QPushButton("📥 Import CSV")
        self.btn_import_csv.setStyleSheet("background-color: #FFFFFF; color: #1F2D3D; border: 1px solid #D0D5DD; padding: 8px 16px; border-radius: 4px; font-weight: bold;")
        self.btn_import_csv.clicked.connect(self.import_csv)
        header_layout.addWidget(self.btn_import_csv)

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
        
        if not self.is_admin:
            self.btn_delete_inventory.hide()
            
        header_layout.addWidget(self.btn_delete_inventory)
        layout.addLayout(header_layout)

        summary_frame = QFrame()
        summary_frame.setStyleSheet("""
            QFrame {
                background-color: #FFFFFF;
                border: 1px solid #E4E4E7;
                border-radius: 6px;
                padding: 4px 10px;
            }
            QLabel {
                border: none;
            }
        """)
        summary_layout = QHBoxLayout(summary_frame)
        summary_layout.setContentsMargins(15, 8, 15, 8)
        summary_layout.setSpacing(25)

        self.lbl_total_qty = QLabel("Total Quantity: <b>0</b>")
        self.lbl_total_qty.setStyleSheet("font-size: 13px; color: #1F2D3D;")
        
        self.lbl_total_unit_price = QLabel("Total Unit Price: <b>$0.00</b>")
        self.lbl_total_unit_price.setStyleSheet("font-size: 13px; color: #1F2D3D;")
        
        self.lbl_total_total_price = QLabel("Total Price: <b>$0.00</b>")
        self.lbl_total_total_price.setStyleSheet("font-size: 13px; color: #101828; font-weight: bold;")

        summary_layout.addWidget(self.lbl_total_qty)
        summary_layout.addWidget(QLabel("<span style='color:#D4D4D8;'>|</span>"))
        summary_layout.addWidget(self.lbl_total_unit_price)
        summary_layout.addWidget(QLabel("<span style='color:#D4D4D8;'>|</span>"))
        summary_layout.addWidget(self.lbl_total_total_price)
        summary_layout.addStretch()

        layout.addWidget(summary_frame)
        
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

        conn = None
        try:
            self._ensure_database_schema()
            conn = connect_db()
            cursor = conn.cursor()

            cursor.execute("SELECT * FROM Inventory WHERE Id = ?", (item_id,))
            row_data = cursor.fetchone()
            columns = [col[0] for col in cursor.description] if cursor.description else []

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
        finally:
            if conn:
                conn.close()

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
            conn = None
            try:
                conn = connect_db()
                cursor = conn.cursor()
                cursor.execute("DELETE FROM Inventory WHERE Id = ?", (item_id,))
                conn.commit()

                log_audit(self.username, "INVENTORY_DELETE", f"Deleted inventory item #{item_id}")
                QMessageBox.information(self, "Success", f"Inventory item #{item_id} deleted successfully.")
                self.refresh_all_data()
            except Exception as e:
                QMessageBox.critical(self, "Database Error", f"Failed to delete item:\n{e}")
            finally:
                if conn:
                    conn.close()

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
        
        if not self.is_admin:
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

        conn = None
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
        finally:
            if conn:
                conn.close()

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
            conn = None
            try:
                conn = connect_db()
                cursor = conn.cursor()
                try:
                    cursor.execute("DELETE FROM AuditLogs WHERE Id = ?", (log_id,))
                except Exception:
                    cursor.execute("DELETE FROM AuditLogs WHERE LogId = ?", (log_id,))

                conn.commit()
                QMessageBox.information(self, "Success", f"Log record #{log_id} deleted successfully.")
                self.refresh_all_data()
            except Exception as e:
                QMessageBox.critical(self, "Database Error", f"Failed to delete record:\n{e}")
            finally:
                if conn:
                    conn.close()

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

    def _recalculate_cached_totals(self):
        """Calculates and stores total stats in cache to eliminate lag upon tab switching."""
        qty_col = 3
        unit_price_col = 13
        total_price_col = 14

        total_qty = 0
        total_unit_price = 0.0
        total_price = 0.0

        for row in range(self.inventory_table.rowCount()):
            row_qty = 0
            row_unit_price = 0.0
            row_total_price = 0.0

            if self.inventory_table.columnCount() > qty_col:
                item = self.inventory_table.item(row, qty_col)
                if item and item.text().strip():
                    digits = ''.join(filter(str.isdigit, item.text()))
                    if digits:
                        row_qty = int(digits)
                        total_qty += row_qty

            if self.inventory_table.columnCount() > unit_price_col:
                item = self.inventory_table.item(row, unit_price_col)
                if item and item.text().strip():
                    val_str = item.text().replace(',', '').replace('$', '').strip()
                    try:
                        match = re.search(r'\d+(\.\d+)?', val_str)
                        if match:
                            row_unit_price = float(match.group())
                            total_unit_price += row_unit_price
                    except Exception:
                        pass

            if self.inventory_table.columnCount() > total_price_col:
                item = self.inventory_table.item(row, total_price_col)
                if item and item.text().strip():
                    val_str = item.text().replace(',', '').replace('$', '').strip()
                    try:
                        match = re.search(r'\d+(\.\d+)?', val_str)
                        if match:
                            row_total_price = float(match.group())
                    except Exception:
                        pass

            if row_total_price == 0.0 and row_qty > 0 and row_unit_price > 0:
                row_total_price = row_qty * row_unit_price

            total_price += row_total_price

        self.cached_total_qty = total_qty
        self.cached_total_unit_price = total_unit_price
        self.cached_total_price = total_price

    def refresh_all_data(self):
        """Refreshes KPI statistics, charts, table views, and caches overall totals."""
        conn = None
        try:
            conn = connect_db()
            cursor = conn.cursor()

            # 1. Update KPI Cards
            cursor.execute("SELECT ISNULL(SUM(Quantity), 0), COUNT(*) FROM Inventory")
            total_units, total_lines = cursor.fetchone()

            cursor.execute("SELECT COUNT(*) FROM AuditLogs")
            total_trans = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) FROM Inventory WHERE Quantity <= 3")
            low_stock = cursor.fetchone()[0]

            self.kpi_units.findChildren(QLabel)[1].setText(str(total_units))
            self.kpi_lines.findChildren(QLabel)[1].setText(str(total_lines))
            self.kpi_trans.findChildren(QLabel)[1].setText(str(total_trans))
            self.kpi_low.findChildren(QLabel)[1].setText(str(low_stock))

            # 2. Update Charts
            cursor.execute("SELECT DeviceName, SUM(Quantity) FROM Inventory GROUP BY DeviceName")
            name_data = {row[0]: row[1] for row in cursor.fetchall() if row[0]}
            self.chart_names.update_chart(name_data)

            cursor.execute("SELECT DeviceType, SUM(Quantity) FROM Inventory GROUP BY DeviceType")
            type_data = {row[0]: row[1] for row in cursor.fetchall() if row[0]}
            self.chart_types.update_chart(type_data)

            # 3. Populate Dashboard Recent Inventory Table
            cursor.execute("SELECT TOP 10 * FROM Inventory ORDER BY 1 DESC")
            dash_rows = cursor.fetchall()
            dash_cols = [col[0] for col in cursor.description] if cursor.description else []
            self.dash_table.setColumnCount(len(dash_cols))
            self.dash_table.setHorizontalHeaderLabels([self._format_key_name_helper(c) for c in dash_cols])
            self.dash_table.setRowCount(len(dash_rows))
            for r_idx, r_data in enumerate(dash_rows):
                for c_idx, val in enumerate(r_data):
                    val_str = f"#{val}" if c_idx == 0 else self.format_value_clean(val)
                    self.dash_table.setItem(r_idx, c_idx, QTableWidgetItem(val_str))

            # 4. Populate Full Inventory Table
            ordered_headers = [
                "ID", "Device Name", "Device Type", "Quantity", "Sender", "Receiver",
                "Date & Time Receiving", "Warranty Date", "Barcode", "Ticket Number", "From Where",
                "Serial Number", "Hostname", "Price Per Unit", "Total Price", "Notes"
            ]

            cursor.execute("SELECT * FROM Inventory ORDER BY 1 DESC")
            inv_rows = cursor.fetchall()
            db_cols = [col[0].lower().replace("_", "").replace(" ", "") for col in cursor.description] if cursor.description else []

            self.inventory_table.setColumnCount(len(ordered_headers))
            self.inventory_table.setHorizontalHeaderLabels(ordered_headers)
            self.inventory_table.setRowCount(len(inv_rows))

            header_aliases = {
                0: ["id"],
                1: ["devicename", "name", "device"],
                2: ["devicetype", "type", "category"],
                3: ["quantity", "qty", "count"],
                4: ["sender", "sentby", "fromuser"],
                5: ["receiver", "receivedby", "assignedto"],
                6: ["receivedate", "datereceiving", "datetimereceiving", "date"],
                7: ["warrantydate", "warranty", "expirydate"],
                8: ["barcode", "code"],
                9: ["ticketnumber", "ticketno", "ticket", "refnumber"],
                10: ["fromwhere", "location", "source", "vendor"],
                11: ["serialnumber", "serialno", "sn", "serial"],
                12: ["hostname", "host", "computername"],
                13: ["unitprice", "priceperunit", "price", "cost"],
                14: ["totalprice", "totalcost", "total"],
                15: ["note", "notes", "comments", "comment", "description"]
            }

            col_index_map = {}
            for target_col_idx, aliases in header_aliases.items():
                for alias in aliases:
                    if alias in db_cols:
                        col_index_map[target_col_idx] = db_cols.index(alias)
                        break

            for r_idx, r_data in enumerate(inv_rows):
                for c_idx in range(len(ordered_headers)):
                    db_idx = col_index_map.get(c_idx)
                    val = r_data[db_idx] if (db_idx is not None and db_idx < len(r_data)) else None
                    val_str = self.format_value_clean(val)
                    self.inventory_table.setItem(r_idx, c_idx, QTableWidgetItem(val_str))

            # 5. Populate Audit Logs Table
            cursor.execute("SELECT * FROM AuditLogs ORDER BY 1 DESC")
            hist_rows = cursor.fetchall()
            audit_db_cols = [col[0].lower().replace("_", "").replace(" ", "") for col in cursor.description] if cursor.description else []

            headers = ["Log Id", "Username", "Action Type", "Details"]
            self.history_table.setColumnCount(len(headers))
            self.history_table.setHorizontalHeaderLabels(headers)
            self.history_table.setRowCount(len(hist_rows))

            id_idx = audit_db_cols.index("id") if "id" in audit_db_cols else (audit_db_cols.index("logid") if "logid" in audit_db_cols else 0)
            user_idx = audit_db_cols.index("username") if "username" in audit_db_cols else 1
            action_idx = audit_db_cols.index("action") if "action" in audit_db_cols else (audit_db_cols.index("actiontype") if "actiontype" in audit_db_cols else 2)
            details_idx = audit_db_cols.index("details") if "details" in audit_db_cols else 3

            col_map = [id_idx, user_idx, action_idx, details_idx]

            for r_idx, r_data in enumerate(hist_rows):
                for c_idx, db_idx in enumerate(col_map):
                    val = r_data[db_idx] if db_idx < len(r_data) else ""
                    val_str = f"#{val}" if c_idx == 0 else self.format_value_clean(val)
                    self.history_table.setItem(r_idx, c_idx, QTableWidgetItem(val_str))

            self._recalculate_cached_totals()
            self.update_inventory_totals()

        except Exception as e:
            QMessageBox.critical(self, "Data Refresh Error", f"Failed to refresh data from SQL database:\n{e}")
        finally:
            if conn:
                conn.close()

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

    def open_stock_in(self):
        """Opens Stock In dialog and refreshes all dashboard views on completion."""
        dialog = StockInDialog(username=self.username, parent=self)
        if dialog.exec_() == QDialog.Accepted:
            self.refresh_all_data()

    def open_stock_out(self):
        """Opens Stock Out dialog and refreshes all dashboard views on completion."""
        dialog = StockOutDialog(username=self.username, parent=self)
        if dialog.exec_() == QDialog.Accepted:
            self.refresh_all_data()

    def open_users(self):
        """Opens the User Management dialog with admin privileges check."""
        if not self.is_admin:
            QMessageBox.warning(self, "Access Denied", "Only administrators can view or manage user accounts.")
            return

        dialog = UserManagementDialog(self.username, self.user_role, self)
        dialog.exec_()

    def logout(self):
        """Logs out the current user and prompts for new credentials without quitting."""
        confirm = QMessageBox.question(
            self,
            "Logout Confirmation",
            "Are you sure you want to log out?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )

        if confirm != QMessageBox.Yes:
            return

        self.hide()

        login_dialog = LoginDialog()
        if login_dialog.exec_() == QDialog.Accepted:
            self.username = login_dialog.username
            self.user_role = login_dialog.user_role
            self.is_admin = str(self.user_role).strip().lower() in ['admin', 'administrator']

            if hasattr(self, 'user_info_label'):
                self.user_info_label.setText(f"👤 {self.username} - {self.user_role}")

            self.apply_user_permissions()
            self.refresh_all_data()
            self.show()
        else:
            self.close()

    def focus_search_bar(self):
        """Switches to inventory view if needed and focuses the search field."""
        if hasattr(self, 'stacked_widget'):
            self.switch_tab(1, self.btn_inv)
            
        self.search_input.setFocus()
        self.search_input.selectAll()

    def filter_inventory_table(self):
        query = self.search_input.text().strip().lower()
        search_col_name = self.search_combo.currentText()

        target_col = -1
        if search_col_name != "All Columns":
            for col in range(self.inventory_table.columnCount()):
                header_item = self.inventory_table.horizontalHeaderItem(col)
                if header_item and header_item.text().strip().lower() == search_col_name.strip().lower():
                    target_col = col
                    break

        for row in range(self.inventory_table.rowCount()):
            match = False
            if not query:
                match = True
            elif target_col != -1:
                item = self.inventory_table.item(row, target_col)
                if item and query in item.text().lower():
                    match = True
            else:
                for col in range(self.inventory_table.columnCount()):
                    item = self.inventory_table.item(row, col)
                    if item and query in item.text().lower():
                        match = True
                        break

            self.inventory_table.setRowHidden(row, not match)

        self.update_inventory_totals()

    def update_inventory_totals(self):
        """Uses cached totals for unfiltered inventory, recalculates dynamically when search filter is active."""
        query = self.search_input.text().strip() if hasattr(self, 'search_input') else ""

        if not query:
            total_qty = getattr(self, 'cached_total_qty', 0)
            total_unit_price = getattr(self, 'cached_total_unit_price', 0.0)
            total_price = getattr(self, 'cached_total_price', 0.0)
        else:
            qty_col = 3
            unit_price_col = 13
            total_price_col = 14

            total_qty = 0
            total_unit_price = 0.0
            total_price = 0.0

            for row in range(self.inventory_table.rowCount()):
                if not self.inventory_table.isRowHidden(row):
                    row_qty = 0
                    row_unit_price = 0.0
                    row_total_price = 0.0

                    if self.inventory_table.columnCount() > qty_col:
                        item = self.inventory_table.item(row, qty_col)
                        if item and item.text().strip():
                            digits = ''.join(filter(str.isdigit, item.text()))
                            if digits:
                                row_qty = int(digits)
                                total_qty += row_qty

                    if self.inventory_table.columnCount() > unit_price_col:
                        item = self.inventory_table.item(row, unit_price_col)
                        if item and item.text().strip():
                            val_str = item.text().replace(',', '').replace('$', '').strip()
                            try:
                                match = re.search(r'\d+(\.\d+)?', val_str)
                                if match:
                                    row_unit_price = float(match.group())
                                    total_unit_price += row_unit_price
                            except Exception:
                                pass

                    if self.inventory_table.columnCount() > total_price_col:
                        item = self.inventory_table.item(row, total_price_col)
                        if item and item.text().strip():
                            val_str = item.text().replace(',', '').replace('$', '').strip()
                            try:
                                match = re.search(r'\d+(\.\d+)?', val_str)
                                if match:
                                    row_total_price = float(match.group())
                            except Exception:
                                pass

                    if row_total_price == 0.0 and row_qty > 0 and row_unit_price > 0:
                        row_total_price = row_qty * row_unit_price

                    total_price += row_total_price

        if hasattr(self, 'lbl_total_qty'):
            self.lbl_total_qty.setText(f"Total Quantity: <b>{total_qty:,}</b>")
        if hasattr(self, 'lbl_total_unit_price'):
            self.lbl_total_unit_price.setText(f"Total Unit Price: <b>${total_unit_price:,.2f}</b>")
        if hasattr(self, 'lbl_total_total_price'):
            self.lbl_total_total_price.setText(f"Total Price: <b>${total_price:,.2f}</b>")


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(True)
    
    app_icon = load_absolute_app_icon()
    if not app_icon.isNull():
        app.setWindowIcon(app_icon)

    try:
        init_db()
    except Exception as e:
        QMessageBox.critical(None, "Startup Error", f"Failed to connect to database:\n{e}")
        sys.exit(1)

    login = LoginDialog()
    if login.exec_() == QDialog.Accepted:
        if not app_icon.isNull():
            app.setWindowIcon(app_icon)
            
        main_win = MainWindow(username=login.username, user_role=login.user_role)
        main_win.show()
        sys.exit(app.exec_())
    else:
        sys.exit(0)