import os
import sys
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, 
    QLineEdit, QPushButton, QMessageBox
)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QPixmap, QIcon
from database import connect_db

def find_logo_path():
    if getattr(sys, 'frozen', False):
        base_dir = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
    else:
        base_dir = os.path.dirname(os.path.abspath(__file__))

    candidates = [
        os.path.join(base_dir, "assets", "logo.ico"),
        os.path.join(base_dir, "assets", "logo.png"),
        os.path.join(base_dir, "logo.ico"),
        os.path.join(base_dir, "logo.png"),
    ]
    for path in candidates:
        if os.path.exists(path):
            return path
    return None


class LoginDialog(QDialog):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Sign In - Inventory Desk")
        self.setFixedSize(440, 560)
        self.user_role = None
        self.username = None

        icon_path = find_logo_path()
        if icon_path:
            self.setWindowIcon(QIcon(icon_path))

        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self._init_ui()

    def get_username(self):
        return self.txt_user.text().strip()

    def get_role(self):
        return self.user_role

    def _init_ui(self):
        self.setStyleSheet("""
            QDialog { background-color: #FBFBFA; }
            QLabel { font-family: 'Segoe UI', -apple-system, sans-serif; }
            QLineEdit { 
                border: 1px solid #D0D5DD; 
                border-radius: 6px; 
                padding: 10px 12px; 
                font-size: 14px; 
                background-color: #FFFFFF; 
                color: #1D2939; 
            }
            QLineEdit:focus { border: 1.5px solid #1F2D3D; }
            QPushButton#btn_login { 
                background-color: #1F2D3D; 
                color: #FFFFFF; 
                border-radius: 6px; 
                padding: 12px; 
                font-size: 15px; 
                font-weight: 600; 
                border: none; 
            }
            QPushButton#btn_login:hover { background-color: #334155; }
            QPushButton#btn_login:pressed { background-color: #0F172A; }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(36, 36, 36, 30)
        layout.setSpacing(0)

        # Header Section (Logo and Brand)
        header_layout = QHBoxLayout()
        header_layout.setSpacing(12)

        icon_box = QLabel()
        icon_box.setFixedSize(42, 42)
        icon_box.setAlignment(Qt.AlignCenter)
        icon_path = find_logo_path()
        
        if icon_path:
            pixmap = QPixmap(icon_path)
            icon_box.setPixmap(pixmap.scaled(38, 38, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            icon_box.setStyleSheet("background-color: transparent;")
        else:
            icon_box.setText("📦")
            icon_box.setStyleSheet("background-color: #1F2D3D; border-radius: 6px; color: white; font-size: 18px;")

        header_text_layout = QVBoxLayout()
        header_text_layout.setSpacing(2)
        
        title_brand = QLabel("INVENTORY DESK")
        title_brand.setStyleSheet("font-weight: 800; font-size: 14px; color: #1F2D3D; letter-spacing: 0.5px;")
        
        sub_brand = QLabel("IT WAREHOUSE")
        sub_brand.setStyleSheet("font-size: 10px; color: #71717A; font-weight: 600; letter-spacing: 0.5px;")
        
        header_text_layout.addWidget(title_brand)
        header_text_layout.addWidget(sub_brand)
        
        header_layout.addWidget(icon_box)
        header_layout.addLayout(header_text_layout)
        header_layout.addStretch()
        layout.addLayout(header_layout)

        tag_label = QLabel("LOCAL ACCESS")
        tag_label.setStyleSheet("font-size: 10px; font-weight: 700; color: #C2410C; margin-top: 4px;")
        layout.addWidget(tag_label)
        layout.addSpacing(28)

        # Main Headings
        heading = QLabel("Sign in to the warehouse")
        heading.setStyleSheet("font-size: 24px; font-weight: 600; color: #101828;")
        layout.addWidget(heading)
        
        sub_heading = QLabel("Use your Inventory Desk account to continue.")
        sub_heading.setStyleSheet("font-size: 13px; color: #667085; margin-top: 6px;")
        layout.addWidget(sub_heading)
        layout.addSpacing(28)

        # Inputs
        lbl_account = QLabel("Account <font color='#C2410C'>*</font>")
        lbl_account.setStyleSheet("font-size: 12px; font-weight: 700; color: #344054; margin-bottom: 6px;")
        self.txt_user = QLineEdit()
        self.txt_user.setPlaceholderText("Enter account username")
        layout.addWidget(lbl_account)
        layout.addWidget(self.txt_user)
        layout.addSpacing(16)

        lbl_pass = QLabel("Password <font color='#C2410C'>*</font>")
        lbl_pass.setStyleSheet("font-size: 12px; font-weight: 700; color: #344054; margin-bottom: 6px;")
        self.txt_pass = QLineEdit()
        self.txt_pass.setEchoMode(QLineEdit.Password)
        self.txt_pass.setPlaceholderText("Enter password")
        self.txt_pass.returnPressed.connect(self.authenticate)
        layout.addWidget(lbl_pass)
        layout.addWidget(self.txt_pass)
        layout.addSpacing(24)

        # Login Button
        self.btn_login = QPushButton("➔   Sign in")
        self.btn_login.setObjectName("btn_login")
        self.btn_login.setCursor(Qt.PointingHandCursor)
        self.btn_login.clicked.connect(self.authenticate)
        layout.addWidget(self.btn_login)
        layout.addSpacing(28)

        # Footer
        footer_hint = QLabel("👤 Created by: <b>Mohammad Kassas</b>")
        footer_hint.setStyleSheet("font-size: 12px; color: #667085;")
        layout.addWidget(footer_hint)
        layout.addStretch()

    def authenticate(self):
        username = self.txt_user.text().strip()
        password = self.txt_pass.text().strip()

        if not username or not password:
            QMessageBox.warning(self, "Validation Error", "Please enter both Account and Password.")
            return

        # Default hardcoded Admin fallback for first setup or emergency
        if username == "admin" and password == "admin":
            self.user_role = "Admin"
            self.username = username
            self.accept()
            return

        try:
            conn = connect_db()
            cursor = conn.cursor()
            
            # Create Users table if it somehow got bypassed
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS Users (
                    Id INTEGER PRIMARY KEY AUTOINCREMENT,
                    Username TEXT NOT NULL UNIQUE,
                    Password TEXT NOT NULL,
                    Role TEXT NOT NULL
                )
            """)
            conn.commit()

            cursor.execute("SELECT Role FROM Users WHERE Username=? AND Password=?", (username, password))
            row = cursor.fetchone()
            conn.close()

            if row:
                self.user_role = row[0]
                self.username = username
                self.accept()
            else:
                QMessageBox.warning(self, "Access Denied", "Invalid Account or Password.")
        except Exception as e:
            QMessageBox.critical(self, "Database Error", str(e))