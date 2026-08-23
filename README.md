# IT Warehouse - Inventory Management System

A desktop inventory management application built with **Python**, **PyQt5**, and **SQL Server**.

## Features
* **Interactive Dashboard:** Visual analytics, low-stock alerts, and key performance metrics.
* **Stock Control:** Log stock in/out, view detailed item sheets, and search inventory.
* **Data Management:** Export and import CSV reports effortlessly.
* **Audit Trail:** Append-only transaction logging for security and auditing.

## Requirements & Setup
1. **Required Packages:** `PyQt5`, `matplotlib`, `pyodbc`
2. **Run Application:** Execute `python main.py` in your project folder.

### Offline Installation
If deploying in an environment without internet access:
1. Install the Microsoft ODBC Driver (`installers/msodbcsql17.msi` or `18.msi`).
2. Install Microsoft SQL Server Express (`installers/SQLEXPR_x64_ENU.exe`).
3. Run `main.exe` or `python main.py` to start the application.
