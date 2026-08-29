import os
import sys
import sqlite3
from datetime import datetime

def get_resource_path(relative_path):
    """Locates resource files whether running as .py or standalone PyInstaller .exe."""
    if hasattr(sys, 'frozen'):
        exe_dir = os.path.dirname(sys.executable)
        ext_path = os.path.join(exe_dir, relative_path)
        if os.path.exists(ext_path):
            return ext_path
    
    base_dir = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base_dir, relative_path)

def connect_db():
    """Connects seamlessly to the local SQLite database."""
    db_path = get_resource_path("WarehouseDB.sqlite")
    conn = sqlite3.connect(db_path)
    return conn

def init_db():
    """Initializes and migrates the SQLite database schema."""
    conn = connect_db()
    cursor = conn.cursor()
    
    # Users Table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS Users (
            Id INTEGER PRIMARY KEY AUTOINCREMENT,
            Username TEXT UNIQUE,
            Password TEXT,
            Role TEXT
        )
    """)
    
    # Inventory Table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS Inventory (
            Id INTEGER PRIMARY KEY AUTOINCREMENT,
            DeviceName TEXT,
            DeviceType TEXT,
            Quantity INTEGER DEFAULT 0,
            Sender TEXT,
            Receiver TEXT,
            ReceiveDate TEXT,
            WarrantyDate TEXT,
            Barcode TEXT,
            TicketNumber TEXT,
            FromWhere TEXT,
            SerialNumber TEXT,
            HostName TEXT,
            UnitPrice REAL DEFAULT 0.00,
            TotalPrice REAL DEFAULT 0.00,
            Note TEXT
        )
    """)

    # Audit Logs Table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS AuditLogs (
            LogId INTEGER PRIMARY KEY AUTOINCREMENT,
            Username TEXT,
            ActionType TEXT,
            Timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            Details TEXT
        )
    """)

    # Automatic Migration: Add missing columns to existing Inventory table
    cursor.execute("PRAGMA table_info(Inventory)")
    inv_cols = [row[1] for row in cursor.fetchall()]
    inventory_columns = [
        ("Sender", "TEXT"), ("Receiver", "TEXT"), ("ReceiveDate", "TEXT"),
        ("WarrantyDate", "TEXT"), ("Barcode", "TEXT"), ("TicketNumber", "TEXT"),
        ("FromWhere", "TEXT"), ("SerialNumber", "TEXT"), ("HostName", "TEXT"),
        ("UnitPrice", "REAL DEFAULT 0.00"), ("TotalPrice", "REAL DEFAULT 0.00"),
        ("Note", "TEXT")
    ]
    for col, col_type in inventory_columns:
        if col not in inv_cols:
            cursor.execute(f"ALTER TABLE Inventory ADD COLUMN {col} {col_type}")

    # Automatic Migration: Add missing columns to existing AuditLogs table
    cursor.execute("PRAGMA table_info(AuditLogs)")
    audit_cols = [row[1] for row in cursor.fetchall()]
    audit_columns = [
        ("Sender", "TEXT"), ("WarrantyDate", "TEXT"),
        ("TicketNumber", "TEXT"), ("FromWhere", "TEXT")
    ]
    for col, col_type in audit_columns:
        if col not in audit_cols:
            cursor.execute(f"ALTER TABLE AuditLogs ADD COLUMN {col} {col_type}")
    
    # Create default Admin user if table is empty
    cursor.execute("SELECT COUNT(*) FROM Users")
    if cursor.fetchone()[0] == 0:
        cursor.execute("INSERT INTO Users (Username, Password, Role) VALUES ('admin', 'admin', 'Admin')")
        
    conn.commit()
    conn.close()

def log_audit(username, action_type, details="", sender="", warranty_date="", ticket_number="", from_where="", **kwargs):
    """Inserts a new event log into the SQLite AuditLogs table."""
    sender = kwargs.get('Sender', sender)
    warranty_date = kwargs.get('WarrantyDate', kwargs.get('warranty_date', warranty_date))
    ticket_number = kwargs.get('TicketNumber', kwargs.get('ticket_number', ticket_number))
    from_where = kwargs.get('FromWhere', kwargs.get('from_where', from_where))

    try:
        conn = connect_db()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO AuditLogs (Username, ActionType, Details, Sender, WarrantyDate, TicketNumber, FromWhere)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (username, action_type, details, sender, warranty_date, ticket_number, from_where))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Failed to record audit log: {e}")