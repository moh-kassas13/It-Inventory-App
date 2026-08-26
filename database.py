import os
import subprocess
import sys
import time
import pyodbc

PREFERRED_DRIVERS = [
    "ODBC Driver 18 for SQL Server",
    "ODBC Driver 17 for SQL Server",
    "ODBC Driver 13 for SQL Server",
    "SQL Server Native Client 11.0",
    "SQL Server",
]

def get_resource_path(relative_path):
    """Locates resource files whether running as .py or standalone PyInstaller .exe."""
    if hasattr(sys, 'frozen'):
        exe_dir = os.path.dirname(sys.executable)
        ext_path = os.path.join(exe_dir, relative_path)
        if os.path.exists(ext_path):
            return ext_path
    
    base_dir = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base_dir, relative_path)

def find_installed_driver():
    available_drivers = pyodbc.drivers()
    for driver in PREFERRED_DRIVERS:
        if driver in available_drivers:
            return driver
    return None

def install_bundled_driver():
    """Installs ODBC Driver if missing."""
    msi_names = ["msodbcsql17.msi", "msodbcsql.msi", "msodbcsql18.msi"]
    msi_path = None
    for name in msi_names:
        path = get_resource_path(os.path.join("installers", name))
        if os.path.exists(path):
            msi_path = path
            break

    if msi_path and os.path.exists(msi_path):
        cmd = f'msiexec /i "{msi_path}" /qn IACCEPTMSODBCSQLLICENSETERMS=YES'
        subprocess.run(cmd, shell=True, check=True)

def try_start_sql_service():
    """Attempts to start the SQL Server service if installed but stopped."""
    try:
        subprocess.run("net start MSSQL$SQLEXPRESS", shell=True, capture_output=True, timeout=10)
    except Exception:
        pass

def install_bundled_sql_express():
    """Silently installs SQL Server Express from the installers directory."""
    sql_names = ["SQLEXPR_x64_ENU.exe", "SQLEXPR.exe", "SQLEXPRESS.exe"]
    sql_path = None
    for name in sql_names:
        path = get_resource_path(os.path.join("installers", name))
        if os.path.exists(path):
            sql_path = path
            break

    if sql_path and os.path.exists(sql_path):
        cmd = (
            f'"{sql_path}" /QS /ACTION=Install /FEATURES=SQLEngine '
            r'/INSTANCENAME=SQLEXPRESS /SQLSYSADMINACCOUNTS="Builtin\Administrators" '
            r'/IAcceptSQLServerLicenseTerms /TCPENABLED=1'
        )
        subprocess.run(cmd, shell=True, check=True)
        time.sleep(15)  # Allow service time to start

def connect_db(db_name="WarehouseDB", autocommit=False):
    driver = find_installed_driver()
    
    if not driver:
        install_bundled_driver()
        driver = find_installed_driver()
        
    if not driver:
        raise RuntimeError("No SQL Server ODBC Driver found or installed.")

    extra_params = ";TrustServerCertificate=yes" if "18" in driver else ""
    
    conn_str = (
        f"DRIVER={{{driver}}};"
        r"SERVER=localhost\SQLEXPRESS;"
        f"DATABASE={db_name};"
        r"Trusted_Connection=yes;"
        f"{extra_params}"
    )

    try:
        conn = pyodbc.connect(conn_str)
    except pyodbc.Error:
        try_start_sql_service()
        try:
            conn = pyodbc.connect(conn_str)
        except pyodbc.Error:
            install_bundled_sql_express()
            conn = pyodbc.connect(conn_str)

    if autocommit:
        conn.autocommit = True
    return conn

def init_db():
    # 1. Connect to system 'master' DB to create WarehouseDB if missing
    try:
        conn_master = connect_db(db_name="master", autocommit=True)
        cursor_master = conn_master.cursor()
        cursor_master.execute("""
            IF NOT EXISTS (SELECT name FROM sys.databases WHERE name = 'WarehouseDB')
            CREATE DATABASE WarehouseDB
        """)
        conn_master.close()
    except Exception as e:
        raise RuntimeError(f"Could not check/create WarehouseDB on SQL Server instance:\n{e}")

    # 2. Connect to WarehouseDB and create/update tables
    conn = connect_db()
    cursor = conn.cursor()
    
    # Users Table
    cursor.execute("""
        IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='Users' and xtype='U')
        CREATE TABLE Users (
            Id INT PRIMARY KEY IDENTITY(1,1),
            Username VARCHAR(50) UNIQUE,
            Password VARCHAR(50),
            Role VARCHAR(20)
        )
    """)
    
    # Inventory Table with all 15 attributes
    cursor.execute("""
        IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='Inventory' and xtype='U')
        CREATE TABLE Inventory (
            Id INT PRIMARY KEY IDENTITY(1,1),
            DeviceName VARCHAR(100),
            DeviceType VARCHAR(50),
            Quantity INT DEFAULT 0,
            Sender VARCHAR(100),
            Receiver VARCHAR(100),
            ReceiveDate DATE,
            WarrantyDate VARCHAR(50),
            Barcode VARCHAR(100),
            TicketNumber VARCHAR(100),
            FromWhere VARCHAR(100),
            SerialNumber VARCHAR(100),
            HostName VARCHAR(100),
            UnitPrice DECIMAL(18, 2) DEFAULT 0.00,
            TotalPrice DECIMAL(18, 2) DEFAULT 0.00,
            Note TEXT
        )
    """)

    # Audit Logs Table
    cursor.execute("""
        IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='AuditLogs' and xtype='U')
        CREATE TABLE AuditLogs (
            LogId INT PRIMARY KEY IDENTITY(1,1),
            Username VARCHAR(50),
            ActionType VARCHAR(50),
            Timestamp DATETIME DEFAULT GETDATE(),
            Sender VARCHAR(100),
            WarrantyDate VARCHAR(50),
            TicketNumber VARCHAR(100),
            FromWhere VARCHAR(100),
            Details TEXT
        )
    """)

    # Automatic Migration: Adds any missing columns to existing Inventory table
    inventory_columns = [
        ("Sender", "VARCHAR(100)"),
        ("Receiver", "VARCHAR(100)"),
        ("ReceiveDate", "DATE"),
        ("WarrantyDate", "VARCHAR(50)"),
        ("Barcode", "VARCHAR(100)"),
        ("TicketNumber", "VARCHAR(100)"),
        ("FromWhere", "VARCHAR(100)"),
        ("SerialNumber", "VARCHAR(100)"),
        ("HostName", "VARCHAR(100)"),
        ("UnitPrice", "DECIMAL(18, 2) DEFAULT 0.00"),
        ("TotalPrice", "DECIMAL(18, 2) DEFAULT 0.00"),
        ("Note", "TEXT")
    ]
    for col, col_type in inventory_columns:
        cursor.execute(f"""
            IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('Inventory') AND name = '{col}')
            ALTER TABLE Inventory ADD {col} {col_type}
        """)

    # Automatic Migration: Adds missing history columns to existing AuditLogs table
    audit_columns = [
        ("Sender", "VARCHAR(100)"),
        ("WarrantyDate", "VARCHAR(50)"),
        ("TicketNumber", "VARCHAR(100)"),
        ("FromWhere", "VARCHAR(100)")
    ]
    for col, col_type in audit_columns:
        cursor.execute(f"""
            IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('AuditLogs') AND name = '{col}')
            ALTER TABLE AuditLogs ADD {col} {col_type}
        """)
    
    # Create default Admin user if table is empty
    cursor.execute("SELECT COUNT(*) FROM Users")
    if cursor.fetchone()[0] == 0:
        cursor.execute("INSERT INTO Users (Username, Password, Role) VALUES ('admin', 'admin', 'Admin')")
        
    conn.commit()
    conn.close()

def log_audit(username, action_type, details="", sender="", warranty_date="", ticket_number="", from_where="", **kwargs):
    """Inserts a new event log into the AuditLogs table with all metadata fields."""
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