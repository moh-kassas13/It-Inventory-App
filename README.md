# IT Warehouse Inventory

A lightweight Windows desktop application designed to track, manage, and audit IT hardware assets at AUB Medical Center. Built with Python and PyQt, the application features an embedded SQLite database engine for fast, serverless local data storage and seamless standalone deployment.

---

## ✨ Features

* **Asset Tracking & Management:** Log, update, and search IT hardware stock, monitor specifications, and device allocations.
* **Embedded SQLite Database:** Migrated from heavy SQL Server dependencies to SQLite for zero-configuration, high-performance local storage.
* **PyInstaller Staging:** Dynamic path resolution (`sys._MEIPASS`) ensures icon assets and dependencies load reliably in compiled environments.
* **Windows Installer Integration:** Includes an Inno Setup script (`setup.iss`) that configures permissions, program shortcuts, and uninstall entries.

---

## 🛠️ Tech Stack

* **Language:** Python 3.x
* **GUI Framework:** PyQt / PySide
* **Database:** SQLite 3
* **Build Tools:** PyInstaller, Inno Setup Compiler

---

## 📁 Project Structure

```text
WarehouseApp/
├── assets/
│   ├── logo.ico
│   └── logo.png
├── auth.py             
├── database.py
├── dialogs.py
├── report_feature.py
├── main.py              
├── setup.iss            # Inno Setup installer script
└── README.md            # Repository documentation
