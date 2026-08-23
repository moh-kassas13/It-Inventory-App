# Offline Prerequisites & Setup Guide

This directory holds third-party installer packages required for offline application deployment. Heavy binaries and extracted setup folders are excluded from GitHub due to file size limits.

---

## Deployment Directory Structure

### 1. `installers/` Directory (This Folder)
Place setup binaries here prior to offline deployment:
* **`msodbcsql17.msi`** (or `18.msi`) — Microsoft ODBC Driver for SQL Server.
* **`SQLEXPR_x64_ENU.exe`** — SQL Server Express installer package.

### 2. Project Root Directory (`./`)
* **`SQLEXPR_x64_ENU/`** — Extracted SQL Server Express setup folder. Place this directly in the main project folder (alongside `main.py` or `main.exe`) so the application's automated setup script can locate `SETUP.EXE`.

---

## Official Downloads
* [Microsoft ODBC Driver for SQL Server](https://learn.microsoft.com/en-us/sql/connect/odbc/download-odbc-driver-for-sql-server)
* [Microsoft SQL Server Express](https://www.microsoft.com/en-us/sql-server/sql-server-downloads)
