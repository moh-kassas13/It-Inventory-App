import os
import csv
import pyodbc
from datetime import datetime
from PyQt5.QtWidgets import (
    QDialog, QDoubleSpinBox, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QSpinBox, QDateEdit, QDateTimeEdit, QTextEdit, QPushButton,
    QMessageBox, QFormLayout, QScrollArea, QWidget, QComboBox, QInputDialog, QFileDialog
)
from PyQt5.QtCore import QCoreApplication, Qt, QDate, QDateTime, QEvent, QPoint
from PyQt5.QtGui import QFont, QMouseEvent
from database import connect_db, log_audit


class BlankDateEdit(QDateEdit):
    """QDateEdit that stays blank by default, auto-fills Today on click/focus, and clears on Backspace/Delete."""
    def __init__(self, parent=None):
        self._has_value = False
        super().__init__(parent)
        self.setDisplayFormat("yyyy-MM-dd")
        self.setCalendarPopup(True)
        self.setSpecialValueText(" ")  # Keeps input visually blank initially
        self.setDate(self.minimumDate())

        self.dateChanged.connect(self._on_date_changed)
        self.lineEdit().installEventFilter(self)

    def _on_date_changed(self, date):
        if date != self.minimumDate():
            self._has_value = True

    def textFromDateTime(self, dateTime):
        if not getattr(self, '_has_value', False) or dateTime.date() == self.minimumDate():
            return ""
        return super().textFromDateTime(dateTime)

    def focusInEvent(self, event):
        if not getattr(self, '_has_value', False) or self.date() == self.minimumDate():
            self._set_to_today()
        super().focusInEvent(event)

    def mousePressEvent(self, event):
        if not getattr(self, '_has_value', False) or self.date() == self.minimumDate():
            self._set_to_today()
        super().mousePressEvent(event)

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Delete, Qt.Key_Backspace):
            self._has_value = False
            self.setDate(self.minimumDate())
            self.lineEdit().setText("")
            return
        else:
            self._has_value = True
        super().keyPressEvent(event)

    def _set_to_today(self):
        today = QDate.currentDate()
        self._has_value = True
        self.setDate(today)
        cal = self.calendarWidget()
        if cal:
            cal.setCurrentPage(today.year(), today.month())
            cal.setSelectedDate(today)

    def eventFilter(self, obj, event):
        if obj == self.lineEdit():
            if event.type() in (QEvent.MouseButtonPress, QEvent.FocusIn):
                if not getattr(self, '_has_value', False) or self.date() == self.minimumDate():
                    self._set_to_today()

            elif event.type() == QEvent.MouseButtonDblClick:
                self._set_to_today()
                self.lineEdit().deselect()

                arrow_pos = QPoint(self.width() - 10, self.height() // 2)
                press = QMouseEvent(QEvent.MouseButtonPress, arrow_pos, Qt.LeftButton, Qt.LeftButton, Qt.NoModifier)
                release = QMouseEvent(QEvent.MouseButtonRelease, arrow_pos, Qt.LeftButton, Qt.LeftButton, Qt.NoModifier)
                
                QCoreApplication.postEvent(self, press)
                QCoreApplication.postEvent(self, release)
                return True

        return super().eventFilter(obj, event)

    def is_blank(self):
        return not getattr(self, '_has_value', False) or self.date() == self.minimumDate()


# ==========================================
# EXPORT DIALOG
# ==========================================
class ExportDialog(QDialog):
    def __init__(self, username="System", is_admin=False, parent=None):
        if isinstance(username, QWidget):
            parent = username
            username = getattr(parent, 'username', 'System')
            is_admin = getattr(parent, 'is_admin', False)

        super().__init__(parent)
        self.username = username
        self.is_admin = is_admin or self._check_admin_status()
        self.setWindowTitle("Export Data to CSV")
        self.resize(340, 160)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)

        app_font = QFont("Segoe UI", 9)
        self.setFont(app_font)

        self.setStyleSheet("""
            QDialog { background-color: #f8f9fa; }
            QLabel { color: #000000; font-size: 12px; font-weight: normal; }
            QComboBox {
                background-color: #ffffff;
                border: 1px solid #ababab;
                border-radius: 4px;
                padding: 4px 8px;
                font-size: 12px;
                color: #000000;
            }
            QComboBox:hover, QComboBox:focus { border-color: #0078d7; }
            QPushButton {
                background-color: #ffffff;
                color: #000000;
                border: 1px solid #ababab;
                border-radius: 4px;
                padding: 5px 14px;
                font-size: 12px;
                font-weight: normal;
            }
            QPushButton:hover { background-color: #e5f1fb; border-color: #0078d7; }
            QPushButton:pressed { background-color: #cce4f7; }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(10)

        lbl_title = QLabel("Select Dataset to Export:", self)
        layout.addWidget(lbl_title)

        self.combo_dataset = QComboBox(self)
        datasets = ["Inventory"]
        if self.is_admin:
            datasets.append("Audit Logs")
        self.combo_dataset.addItems(datasets)
        layout.addWidget(self.combo_dataset)

        layout.addStretch()

        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(8)

        self.btn_cancel = QPushButton("Cancel", self)
        self.btn_cancel.clicked.connect(self.reject)

        self.btn_export = QPushButton("Export CSV", self)
        self.btn_export.clicked.connect(self.export_data)

        btn_layout.addWidget(self.btn_cancel)
        btn_layout.addWidget(self.btn_export)

        layout.addLayout(btn_layout)

    def _check_admin_status(self):
        if self.username == "System":
            return True
        try:
            conn = connect_db()
            cursor = conn.cursor()
            cursor.execute("SELECT Role FROM Users WHERE Username = ?", (self.username,))
            row = cursor.fetchone()
            conn.close()
            if row and str(row[0]).strip().lower() in ['admin', 'administrator']:
                return True
        except Exception:
            pass
        return False

    def export_data(self):
        dataset_choice = self.combo_dataset.currentText().strip()

        if dataset_choice == "Audit Logs" and not self.is_admin:
            QMessageBox.warning(self, "Access Denied", "Only administrators can view or export History/Audit Logs.")
            return

        file_path, _ = QFileDialog.getSaveFileName(
            self, 
            "Save CSV File", 
            f"{dataset_choice.lower().replace(' ', '_')}_export.csv", 
            "CSV Files (*.csv)"
        )

        if not file_path:
            return

        if dataset_choice == "Inventory":
            query = "SELECT * FROM Inventory"
        elif dataset_choice == "Audit Logs":
            query = "SELECT * FROM AuditLogs"
        else:
            QMessageBox.warning(self, "Export Error", f"Unknown dataset option: {dataset_choice}")
            return

        conn = None
        try:
            conn = connect_db()
            cursor = conn.cursor()
            cursor.execute(query)

            rows = cursor.fetchall()
            headers = [column[0] for column in cursor.description] if cursor.description else []

            with open(file_path, mode='w', newline='', encoding='utf-8-sig') as file:
                writer = csv.writer(file)
                writer.writerow(headers)
                for row in rows:
                    writer.writerow([str(val) if val is not None else "" for val in row])

            msg_box = QMessageBox(self)
            msg_box.setIcon(QMessageBox.Information)
            msg_box.setWindowTitle("Export Success")
            msg_box.setText(f"Data successfully exported to:\n{file_path}")
            msg_box.setStyleSheet("QLabel { font-weight: normal; font-size: 12px; }")
            msg_box.exec_()

            self.accept()

        except Exception as e:
            QMessageBox.critical(self, "Export Failed", f"An error occurred while exporting:\n{e}")
        finally:
            if conn:
                conn.close()


# ==========================================
# STOCK IN DIALOG
# ==========================================
class StockInDialog(QDialog):
    def __init__(self, username="System", is_admin=False, parent=None):
        if isinstance(username, QWidget):
            parent = username
            username = getattr(parent, 'username', 'System')
            is_admin = getattr(parent, 'is_admin', False)
        
        super().__init__(parent)
        self.username = username
        self.is_admin = is_admin or self._check_admin_status()
        self.setWindowTitle("Stock In - Inbound Transaction")
        self.resize(560, 780)
        self.setStyleSheet("QDialog { background-color: #FFFFFF; }")
        self._init_ui()

    def _check_admin_status(self):
        if self.username == "System":
            return True
        try:
            conn = connect_db()
            cursor = conn.cursor()
            cursor.execute("SELECT Role FROM Users WHERE Username = ?", (self.username,))
            row = cursor.fetchone()
            conn.close()
            if row and str(row[0]).strip().lower() in ['admin', 'administrator']:
                return True
        except Exception:
            pass
        return False

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(15, 15, 15, 15)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; background-color: #FFFFFF; }")

        container = QWidget()
        form_layout = QFormLayout(container)
        form_layout.setSpacing(12)
        form_layout.setLabelAlignment(Qt.AlignRight)

        btn_add_style = """
            QPushButton {
                background-color: #1F2D3D; 
                color: white; 
                font-weight: bold; 
                font-size: 14px; 
                border-radius: 4px; 
                padding: 4px;
            }
            QPushButton:hover { background-color: #34495E; }
        """

        btn_del_style = """
            QPushButton {
                background-color: #EF4444; 
                color: white; 
                font-weight: bold; 
                font-size: 14px; 
                border-radius: 4px; 
                padding: 4px;
            }
            QPushButton:hover { background-color: #DC2626; }
        """

        # 1. Device Name *
        dev_name_layout = QHBoxLayout()
        dev_name_layout.setSpacing(6)

        self.cbo_dev_name = QComboBox()
        self._style_input(self.cbo_dev_name)

        btn_add_dev_name = QPushButton("+")
        btn_add_dev_name.setFixedWidth(30)
        btn_add_dev_name.setToolTip("Add new Device Name")
        btn_add_dev_name.setStyleSheet(btn_add_style)
        btn_add_dev_name.setVisible(self.is_admin)
        btn_add_dev_name.clicked.connect(self._add_new_device_name)

        btn_del_dev_name = QPushButton("-")
        btn_del_dev_name.setFixedWidth(30)
        btn_del_dev_name.setToolTip("Remove selected Device Name from options")
        btn_del_dev_name.setStyleSheet(btn_del_style)
        btn_del_dev_name.setVisible(self.is_admin)
        btn_del_dev_name.clicked.connect(self._delete_device_name)

        dev_name_layout.addWidget(self.cbo_dev_name, stretch=1)
        if self.is_admin:
            dev_name_layout.addWidget(btn_add_dev_name)
            dev_name_layout.addWidget(btn_del_dev_name)

        self._populate_device_names()

        # 2. Device Type *
        dev_type_layout = QHBoxLayout()
        dev_type_layout.setSpacing(6)

        self.cbo_dev_type = QComboBox()
        self._style_input(self.cbo_dev_type)

        btn_add_dev_type = QPushButton("+")
        btn_add_dev_type.setFixedWidth(30)
        btn_add_dev_type.setToolTip("Add new Device Type")
        btn_add_dev_type.setStyleSheet(btn_add_style)
        btn_add_dev_type.setVisible(self.is_admin)
        btn_add_dev_type.clicked.connect(self._add_new_device_type)

        btn_del_dev_type = QPushButton("-")
        btn_del_dev_type.setFixedWidth(30)
        btn_del_dev_type.setToolTip("Remove selected Device Type from options")
        btn_del_dev_type.setStyleSheet(btn_del_style)
        btn_del_dev_type.setVisible(self.is_admin)
        btn_del_dev_type.clicked.connect(self._delete_device_type)

        dev_type_layout.addWidget(self.cbo_dev_type, stretch=1)
        if self.is_admin:
            dev_type_layout.addWidget(btn_add_dev_type)
            dev_type_layout.addWidget(btn_del_dev_type)

        self._populate_device_types()

        # 3. Quantity *
        self.spn_quantity = QSpinBox()
        self.spn_quantity.setRange(1, 10000)
        self.spn_quantity.setValue(1)
        self._style_input(self.spn_quantity)
        self.spn_quantity.valueChanged.connect(self._recalculate_from_unit)

        # 4. Sender *
        self.txt_sender = QLineEdit()
        self.txt_sender.setPlaceholderText("Supplier, vendor, or sending department")
        self._style_input(self.txt_sender)

        # 5. Receiver *
        self.txt_receiver = QLineEdit()
        self.txt_receiver.setPlaceholderText("Warehouse officer receiving stock")
        self._style_input(self.txt_receiver)

        # 6. Date and Time of Receiving *
        self.dt_receive_datetime = QDateTimeEdit()
        self.dt_receive_datetime.setDateTime(QDateTime.currentDateTime())
        self.dt_receive_datetime.setDisplayFormat("yyyy-MM-dd HH:mm")
        self.dt_receive_datetime.setCalendarPopup(True)
        self._style_input(self.dt_receive_datetime)

        # 7. Warranty Date
        self.dt_warranty_date = BlankDateEdit()
        self._style_input(self.dt_warranty_date)

        # 8. Barcode Number *
        self.txt_barcode = QLineEdit()
        self.txt_barcode.setPlaceholderText("Scan barcode (Zebra DS4308) or type manually...")
        self._style_input(self.txt_barcode)

        # 9. Ticket Number
        self.txt_ticket_num = QLineEdit()
        self.txt_ticket_num.setPlaceholderText("PO, RMA, or Service Desk ticket #")
        self._style_input(self.txt_ticket_num)

        # 10. From Where
        self.txt_from_where = QLineEdit()
        self.txt_from_where.setPlaceholderText("Branch office, vendor depot, supplier location")
        self._style_input(self.txt_from_where)

        # 11. Serial Number
        self.txt_serial_num = QLineEdit()
        self.txt_serial_num.setPlaceholderText("Factory serial number")
        self._style_input(self.txt_serial_num)

        # 12. Host Name
        self.txt_hostname = QLineEdit()
        self.txt_hostname.setPlaceholderText("Network or workstation hostname")
        self._style_input(self.txt_hostname)

        # 13. Unit Price
        self.spn_unit_price = QDoubleSpinBox()
        self.spn_unit_price.setRange(0.00, 999999.99)
        self.spn_unit_price.setDecimals(2)
        self.spn_unit_price.setPrefix("$ ")
        self._style_input(self.spn_unit_price)
        self.spn_unit_price.valueChanged.connect(self._recalculate_from_unit)

        # 14. Total Price (Bidirectional & Editable)
        self.spn_total_price = QDoubleSpinBox()
        self.spn_total_price.setRange(0.00, 99999999.99)
        self.spn_total_price.setDecimals(2)
        self.spn_total_price.setPrefix("$ ")
        self._style_input(self.spn_total_price)
        self.spn_total_price.valueChanged.connect(self._recalculate_from_total)

        # 15. Notes
        self.txt_notes = QTextEdit()
        self.txt_notes.setPlaceholderText("Condition remarks, batch details, extra context...")
        self.txt_notes.setFixedHeight(70)
        self.txt_notes.setStyleSheet("border: 1px solid #D0D5DD; border-radius: 4px; padding: 6px; font-size: 12px;")

        # Form Layout Setup
        form_layout.addRow(self._make_label("Device Name *"), dev_name_layout)
        form_layout.addRow(self._make_label("Device Type *"), dev_type_layout)
        form_layout.addRow(self._make_label("Quantity *"), self.spn_quantity)
        form_layout.addRow(self._make_label("Sender *"), self.txt_sender)
        form_layout.addRow(self._make_label("Receiver *"), self.txt_receiver)
        form_layout.addRow(self._make_label("Date & Time Receiving *"), self.dt_receive_datetime)
        form_layout.addRow(self._make_label("Warranty Date"), self.dt_warranty_date)
        form_layout.addRow(self._make_label("Barcode Number *"), self.txt_barcode)
        form_layout.addRow(self._make_label("Ticket Number"), self.txt_ticket_num)
        form_layout.addRow(self._make_label("From Where"), self.txt_from_where)
        form_layout.addRow(self._make_label("Serial Number"), self.txt_serial_num)
        form_layout.addRow(self._make_label("Host Name"), self.txt_hostname)
        form_layout.addRow(self._make_label("Price Per Unit"), self.spn_unit_price)
        form_layout.addRow(self._make_label("Total Price"), self.spn_total_price)
        form_layout.addRow(self._make_label("Notes"), self.txt_notes)

        scroll.setWidget(container)
        main_layout.addWidget(scroll)

        # Action Buttons
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        btn_cancel = QPushButton("Cancel")
        btn_cancel.setStyleSheet("background-color: #F4F4F5; border: 1px solid #D0D5DD; padding: 8px 16px; border-radius: 4px; font-weight: bold;")
        btn_cancel.clicked.connect(self.reject)

        btn_save = QPushButton("Save Inbound")
        btn_save.setStyleSheet("background-color: #1F2D3D; color: white; border: none; padding: 8px 18px; border-radius: 4px; font-weight: bold;")
        btn_save.clicked.connect(self.save_stock_in)

        btn_layout.addWidget(btn_cancel)
        btn_layout.addWidget(btn_save)
        main_layout.addLayout(btn_layout)

    def _make_label(self, text):
        lbl = QLabel(text)
        lbl.setStyleSheet("font-weight: bold; color: #3F3F46; font-size: 12px;")
        return lbl

    def _style_input(self, widget):
        widget.setStyleSheet("border: 1px solid #D0D5DD; border-radius: 4px; padding: 6px; font-size: 12px; background: white;")

    def _recalculate_from_unit(self):
        """Calculates Total Price when Quantity or Unit Price changes."""
        qty = self.spn_quantity.value()
        unit_price = self.spn_unit_price.value()
        
        self.spn_total_price.blockSignals(True)
        self.spn_total_price.setValue(qty * unit_price)
        self.spn_total_price.blockSignals(False)

    def _recalculate_from_total(self):
        """Calculates Unit Price when Total Price changes."""
        qty = self.spn_quantity.value()
        total_price = self.spn_total_price.value()
        
        if qty > 0:
            self.spn_unit_price.blockSignals(True)
            self.spn_unit_price.setValue(total_price / qty)
            self.spn_unit_price.blockSignals(False)

    # --- DEVICE NAME HELPER METHODS ---
    def _populate_device_names(self):
        self.cbo_dev_name.clear()
        try:
            conn = connect_db()
            cursor = conn.cursor()
            cursor.execute("""
                SELECT DISTINCT DeviceName 
                FROM Inventory 
                WHERE DeviceName IS NOT NULL AND DeviceName <> '' 
                ORDER BY DeviceName
            """)
            rows = cursor.fetchall()
            conn.close()

            for row in rows:
                self.cbo_dev_name.addItem(row[0])

            self.cbo_dev_name.setCurrentIndex(-1)
        except Exception as e:
            print(f"Failed to load device names: {e}")

    def _add_new_device_name(self):
        if not self.is_admin:
            QMessageBox.warning(self, "Access Denied", "Only administrators can add new Device Names.")
            return

        text, ok = QInputDialog.getText(self, "Add Device Name", "Enter new Device Name:")
        if ok and text.strip():
            new_name = text.strip()
            index = self.cbo_dev_name.findText(new_name, Qt.MatchExactly)
            if index < 0:
                self.cbo_dev_name.addItem(new_name)
                self.cbo_dev_name.setCurrentText(new_name)
            else:
                self.cbo_dev_name.setCurrentIndex(index)

    def _delete_device_name(self):
        if not self.is_admin:
            QMessageBox.warning(self, "Access Denied", "Only administrators can remove Device Names.")
            return

        items = [self.cbo_dev_name.itemText(i) for i in range(self.cbo_dev_name.count()) if self.cbo_dev_name.itemText(i).strip()]
        if not items:
            QMessageBox.warning(self, "Warning", "No Device Names available to remove.")
            return

        current_text = self.cbo_dev_name.currentText().strip()
        if not current_text or current_text not in items:
            item, ok = QInputDialog.getItem(self, "Remove Device Name", "Select Device Name to remove:", items, 0, False)
            if ok and item:
                current_text = item
            else:
                return

        reply = QMessageBox.question(
            self,
            "Remove Option",
            f"Are you sure you want to remove '{current_text}'?\n\n"
            f"(This will remove it from the list and clear it from existing records so it won't reappear.)",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )

        if reply == QMessageBox.Yes:
            idx = self.cbo_dev_name.findText(current_text, Qt.MatchExactly)
            if idx >= 0:
                self.cbo_dev_name.removeItem(idx)
            self.cbo_dev_name.setCurrentIndex(-1)

            try:
                conn = connect_db()
                cursor = conn.cursor()
                cursor.execute("UPDATE Inventory SET DeviceName = '' WHERE DeviceName = ?", (current_text,))
                conn.commit()
                conn.close()
            except Exception as e:
                print(f"Database error clearing DeviceName: {e}")

    # --- DEVICE TYPE HELPER METHODS ---
    def _populate_device_types(self):
        self.cbo_dev_type.clear()
        try:
            conn = connect_db()
            cursor = conn.cursor()
            cursor.execute("""
                SELECT DISTINCT DeviceType 
                FROM Inventory 
                WHERE DeviceType IS NOT NULL AND DeviceType <> '' 
                ORDER BY DeviceType
            """)
            rows = cursor.fetchall()
            conn.close()

            for row in rows:
                self.cbo_dev_type.addItem(row[0])

            self.cbo_dev_type.setCurrentIndex(-1)
        except Exception as e:
            print(f"Failed to load device types: {e}")

    def _add_new_device_type(self):
        if not self.is_admin:
            QMessageBox.warning(self, "Access Denied", "Only administrators can add new Device Types.")
            return

        text, ok = QInputDialog.getText(self, "Add Device Type", "Enter new Device Type:")
        if ok and text.strip():
            new_type = text.strip()
            index = self.cbo_dev_type.findText(new_type, Qt.MatchExactly)
            if index < 0:
                self.cbo_dev_type.addItem(new_type)
                self.cbo_dev_type.setCurrentText(new_type)
            else:
                self.cbo_dev_type.setCurrentIndex(index)

    def _delete_device_type(self):
        if not self.is_admin:
            QMessageBox.warning(self, "Access Denied", "Only administrators can remove Device Types.")
            return

        items = [self.cbo_dev_type.itemText(i) for i in range(self.cbo_dev_type.count()) if self.cbo_dev_type.itemText(i).strip()]
        if not items:
            QMessageBox.warning(self, "Warning", "No Device Types available to remove.")
            return

        current_text = self.cbo_dev_type.currentText().strip()
        if not current_text or current_text not in items:
            item, ok = QInputDialog.getItem(self, "Remove Device Type", "Select Device Type to remove:", items, 0, False)
            if ok and item:
                current_text = item
            else:
                return

        reply = QMessageBox.question(
            self,
            "Remove Option",
            f"Are you sure you want to remove '{current_text}'?\n\n"
            f"(This will remove it from the list and clear it from existing records so it won't reappear.)",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )

        if reply == QMessageBox.Yes:
            idx = self.cbo_dev_type.findText(current_text, Qt.MatchExactly)
            if idx >= 0:
                self.cbo_dev_type.removeItem(idx)
            self.cbo_dev_type.setCurrentIndex(-1)

            try:
                conn = connect_db()
                cursor = conn.cursor()
                cursor.execute("UPDATE Inventory SET DeviceType = '' WHERE DeviceType = ?", (current_text,))
                conn.commit()
                conn.close()
            except Exception as e:
                print(f"Database error clearing DeviceType: {e}")

    def save_stock_in(self):
        dev_name = self.cbo_dev_name.currentText().strip()
        dev_type = self.cbo_dev_type.currentText().strip()
        quantity = self.spn_quantity.value()
        unit_price = self.spn_unit_price.value()
        total_price = self.spn_total_price.value()
        sender = self.txt_sender.text().strip()
        receiver = self.txt_receiver.text().strip()
        receive_dt = self.dt_receive_datetime.dateTime().toString("yyyy-MM-dd HH:mm")
        
        if self.dt_warranty_date.is_blank():
            warranty_date = ""
        else:
            warranty_date = self.dt_warranty_date.date().toString("yyyy-MM-dd")

        barcode = self.txt_barcode.text().strip()
        ticket_num = self.txt_ticket_num.text().strip()
        from_where = self.txt_from_where.text().strip()
        serial_num = self.txt_serial_num.text().strip()
        hostname = self.txt_hostname.text().strip()
        notes = self.txt_notes.toPlainText().strip()

        if not dev_name or not dev_type or not sender or not receiver or not barcode:
            QMessageBox.warning(
                self, 
                "Validation Error", 
                "Please fill in all required fields:\n• Device Name\n• Device Type\n• Sender\n• Receiver\n• Barcode Number"
            )
            return

        try:
            conn = connect_db()
            cursor = conn.cursor()
            query = """
                INSERT INTO Inventory 
                (DeviceName, DeviceType, Quantity, UnitPrice, TotalPrice, Sender, Receiver, ReceiveDate, WarrantyDate, Barcode, TicketNumber, FromWhere, SerialNumber, HostName, Note)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """
            cursor.execute(query, (
                dev_name, dev_type, quantity, unit_price, total_price, sender, receiver, receive_dt,
                warranty_date, barcode, ticket_num, from_where, serial_num, hostname, notes
            ))
            conn.commit()
            conn.close()

            audit_details = (
                f"Stock In: Added {quantity}x '{dev_name}' ({dev_type}) "
                f"@ ${unit_price:.2f}/unit (Total: ${total_price:.2f}) received from '{sender}'."
            )
            if notes:
                audit_details += f" Notes: {notes}"

            try:
                log_audit(
                    username=self.username,
                    action_type="STOCK_IN",
                    details=audit_details,
                    sender=sender,
                    warranty_date=warranty_date,
                    ticket_number=ticket_num,
                    from_where=from_where
                )
            except TypeError:
                log_audit(self.username, "STOCK_IN", audit_details)

            QMessageBox.information(self, "Success", f"Successfully recorded Inbound Stock for {quantity} unit(s).")
            self.accept()
        except Exception as e:
            QMessageBox.critical(self, "Database Error", f"Failed to save stock in record:\n{e}")


# ==========================================
# STOCK OUT DIALOG
# ==========================================
class StockOutDialog(QDialog):
    def __init__(self, username="System", is_admin=False, parent=None):
        if isinstance(username, QWidget):
            parent = username
            username = getattr(parent, 'username', 'System')
            is_admin = getattr(parent, 'is_admin', False)

        super().__init__(parent)
        self.username = username
        self.is_admin = is_admin or self._check_admin_status()
        self.setWindowTitle("Stock Out - Outbound Transaction")
        self.resize(560, 780)
        self.setStyleSheet("QDialog { background-color: #FFFFFF; }")
        self._init_ui()

    def _check_admin_status(self):
        if self.username == "System":
            return True
        try:
            conn = connect_db()
            cursor = conn.cursor()
            cursor.execute("SELECT Role FROM Users WHERE Username = ?", (self.username,))
            row = cursor.fetchone()
            conn.close()
            if row and str(row[0]).strip().lower() in ['admin', 'administrator']:
                return True
        except Exception:
            pass
        return False

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(15, 15, 15, 15)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; background-color: #FFFFFF; }")

        container = QWidget()
        form_layout = QFormLayout(container)
        form_layout.setSpacing(12)
        form_layout.setLabelAlignment(Qt.AlignRight)

        btn_add_style = """
            QPushButton {
                background-color: #1F2D3D; 
                color: white; 
                font-weight: bold; 
                font-size: 14px; 
                border-radius: 4px; 
                padding: 4px;
            }
            QPushButton:hover { background-color: #34495E; }
        """

        btn_del_style = """
            QPushButton {
                background-color: #EF4444; 
                color: white; 
                font-weight: bold; 
                font-size: 14px; 
                border-radius: 4px; 
                padding: 4px;
            }
            QPushButton:hover { background-color: #DC2626; }
        """

        # 1. Device Name *
        dev_name_layout = QHBoxLayout()
        dev_name_layout.setSpacing(6)

        self.cbo_dev_name = QComboBox()
        self._style_input(self.cbo_dev_name)

        btn_add_dev_name = QPushButton("+")
        btn_add_dev_name.setFixedWidth(30)
        btn_add_dev_name.setToolTip("Add new Device Name")
        btn_add_dev_name.setStyleSheet(btn_add_style)
        btn_add_dev_name.setVisible(self.is_admin)
        btn_add_dev_name.clicked.connect(self._add_new_device_name)

        btn_del_dev_name = QPushButton("-")
        btn_del_dev_name.setFixedWidth(30)
        btn_del_dev_name.setToolTip("Remove selected Device Name from options")
        btn_del_dev_name.setStyleSheet(btn_del_style)
        btn_del_dev_name.setVisible(self.is_admin)
        btn_del_dev_name.clicked.connect(self._delete_device_name)

        dev_name_layout.addWidget(self.cbo_dev_name, stretch=1)
        if self.is_admin:
            dev_name_layout.addWidget(btn_add_dev_name)
            dev_name_layout.addWidget(btn_del_dev_name)

        self._populate_device_names()

        # 2. Device Type *
        dev_type_layout = QHBoxLayout()
        dev_type_layout.setSpacing(6)

        self.cbo_dev_type = QComboBox()
        self._style_input(self.cbo_dev_type)

        btn_add_dev_type = QPushButton("+")
        btn_add_dev_type.setFixedWidth(30)
        btn_add_dev_type.setToolTip("Add new Device Type")
        btn_add_dev_type.setStyleSheet(btn_add_style)
        btn_add_dev_type.setVisible(self.is_admin)
        btn_add_dev_type.clicked.connect(self._add_new_device_type)

        btn_del_dev_type = QPushButton("-")
        btn_del_dev_type.setFixedWidth(30)
        btn_del_dev_type.setToolTip("Remove selected Device Type from options")
        btn_del_dev_type.setStyleSheet(btn_del_style)
        btn_del_dev_type.setVisible(self.is_admin)
        btn_del_dev_type.clicked.connect(self._delete_device_type)

        dev_type_layout.addWidget(self.cbo_dev_type, stretch=1)
        if self.is_admin:
            dev_type_layout.addWidget(btn_add_dev_type)
            dev_type_layout.addWidget(btn_del_dev_type)

        self._populate_device_types()

        # 3. Quantity *
        self.spn_quantity = QSpinBox()
        self.spn_quantity.setRange(1, 10000)
        self.spn_quantity.setValue(1)
        self._style_input(self.spn_quantity)

        # 4. Sender *
        self.txt_sender = QLineEdit()
        self.txt_sender.setPlaceholderText("Warehouse officer issuing stock")
        self._style_input(self.txt_sender)

        # 5. Receiver *
        self.txt_receiver = QLineEdit()
        self.txt_receiver.setPlaceholderText("Employee, department, or client receiving item")
        self._style_input(self.txt_receiver)

        # 6. Date and Time of Sending *
        self.dt_send_datetime = QDateTimeEdit()
        self.dt_send_datetime.setDateTime(QDateTime.currentDateTime())
        self.dt_send_datetime.setDisplayFormat("yyyy-MM-dd HH:mm")
        self.dt_send_datetime.setCalendarPopup(True)
        self._style_input(self.dt_send_datetime)

        # 7. Barcode Number *
        self.txt_barcode = QLineEdit()
        self.txt_barcode.setPlaceholderText("Asset tag or barcode scan")
        self._style_input(self.txt_barcode)

        # 8. Ticket Number *
        self.txt_ticket_num = QLineEdit()
        self.txt_ticket_num.setPlaceholderText("Service Desk, Dispatch, or RMA ticket #")
        self._style_input(self.txt_ticket_num)

        # 9. To Where *
        self.txt_to_where = QLineEdit()
        self.txt_to_where.setPlaceholderText("Destination branch, department, or office location")
        self._style_input(self.txt_to_where)

        # 10. Serial Number *
        self.txt_serial_num = QLineEdit()
        self.txt_serial_num.setPlaceholderText("Factory serial number")
        self._style_input(self.txt_serial_num)

        # 11. Host Name (Optional)
        self.txt_hostname = QLineEdit()
        self.txt_hostname.setPlaceholderText("Network or workstation hostname (optional)")
        self._style_input(self.txt_hostname)

        # 12. Notes (Optional)
        self.txt_notes = QTextEdit()
        self.txt_notes.setPlaceholderText("Reason for checkout, dispatch details, extra context...")
        self.txt_notes.setFixedHeight(70)
        self.txt_notes.setStyleSheet("border: 1px solid #D0D5DD; border-radius: 4px; padding: 6px; font-size: 12px;")

        # Form Layout Setup
        form_layout.addRow(self._make_label("Device Name *"), dev_name_layout)
        form_layout.addRow(self._make_label("Device Type *"), dev_type_layout)
        form_layout.addRow(self._make_label("Quantity *"), self.spn_quantity)
        form_layout.addRow(self._make_label("Sender *"), self.txt_sender)
        form_layout.addRow(self._make_label("Receiver *"), self.txt_receiver)
        form_layout.addRow(self._make_label("Date & Time Sending *"), self.dt_send_datetime)
        form_layout.addRow(self._make_label("Barcode Number *"), self.txt_barcode)
        form_layout.addRow(self._make_label("Ticket Number *"), self.txt_ticket_num)
        form_layout.addRow(self._make_label("To Where *"), self.txt_to_where)
        form_layout.addRow(self._make_label("Serial Number *"), self.txt_serial_num)
        form_layout.addRow(self._make_label("Host Name"), self.txt_hostname)
        form_layout.addRow(self._make_label("Notes"), self.txt_notes)

        scroll.setWidget(container)
        main_layout.addWidget(scroll)

        # Action Buttons
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        btn_cancel = QPushButton("Cancel")
        btn_cancel.setStyleSheet("background-color: #F4F4F5; border: 1px solid #D0D5DD; padding: 8px 16px; border-radius: 4px; font-weight: bold;")
        btn_cancel.clicked.connect(self.reject)

        btn_save = QPushButton("Confirm Stock Out")
        btn_save.setStyleSheet("background-color: #EF4444; color: white; border: none; padding: 8px 18px; border-radius: 4px; font-weight: bold;")
        btn_save.clicked.connect(self.save_stock_out)

        btn_layout.addWidget(btn_cancel)
        btn_layout.addWidget(btn_save)
        main_layout.addLayout(btn_layout)

    def _make_label(self, text):
        lbl = QLabel(text)
        lbl.setStyleSheet("font-weight: bold; color: #3F3F46; font-size: 12px;")
        return lbl

    def _style_input(self, widget):
        widget.setStyleSheet("border: 1px solid #D0D5DD; border-radius: 4px; padding: 6px; font-size: 12px; background: white;")

    # --- DEVICE NAME HELPER METHODS ---
    def _populate_device_names(self):
        self.cbo_dev_name.clear()
        try:
            conn = connect_db()
            cursor = conn.cursor()
            cursor.execute("""
                SELECT DISTINCT DeviceName 
                FROM Inventory 
                WHERE DeviceName IS NOT NULL AND DeviceName <> '' 
                ORDER BY DeviceName
            """)
            rows = cursor.fetchall()
            conn.close()

            for row in rows:
                self.cbo_dev_name.addItem(row[0])

            self.cbo_dev_name.setCurrentIndex(-1)
        except Exception as e:
            print(f"Failed to load device names: {e}")

    def _add_new_device_name(self):
        if not self.is_admin:
            QMessageBox.warning(self, "Access Denied", "Only administrators can add new Device Names.")
            return

        text, ok = QInputDialog.getText(self, "Add Device Name", "Enter new Device Name:")
        if ok and text.strip():
            new_name = text.strip()
            index = self.cbo_dev_name.findText(new_name, Qt.MatchExactly)
            if index < 0:
                self.cbo_dev_name.addItem(new_name)
                self.cbo_dev_name.setCurrentText(new_name)
            else:
                self.cbo_dev_name.setCurrentIndex(index)

    def _delete_device_name(self):
        if not self.is_admin:
            QMessageBox.warning(self, "Access Denied", "Only administrators can remove Device Names.")
            return

        items = [self.cbo_dev_name.itemText(i) for i in range(self.cbo_dev_name.count()) if self.cbo_dev_name.itemText(i).strip()]
        if not items:
            QMessageBox.warning(self, "Warning", "No Device Names available to remove.")
            return

        current_text = self.cbo_dev_name.currentText().strip()
        if not current_text or current_text not in items:
            item, ok = QInputDialog.getItem(self, "Remove Device Name", "Select Device Name to remove:", items, 0, False)
            if ok and item:
                current_text = item
            else:
                return

        reply = QMessageBox.question(
            self,
            "Remove Option",
            f"Are you sure you want to remove '{current_text}'?\n\n"
            f"(This will remove it from the list and clear it from existing records so it won't reappear.)",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )

        if reply == QMessageBox.Yes:
            idx = self.cbo_dev_name.findText(current_text, Qt.MatchExactly)
            if idx >= 0:
                self.cbo_dev_name.removeItem(idx)
            self.cbo_dev_name.setCurrentIndex(-1)

            try:
                conn = connect_db()
                cursor = conn.cursor()
                cursor.execute("UPDATE Inventory SET DeviceName = '' WHERE DeviceName = ?", (current_text,))
                conn.commit()
                conn.close()
            except Exception as e:
                print(f"Database error clearing DeviceName: {e}")

    # --- DEVICE TYPE HELPER METHODS ---
    def _populate_device_types(self):
        self.cbo_dev_type.clear()
        try:
            conn = connect_db()
            cursor = conn.cursor()
            cursor.execute("""
                SELECT DISTINCT DeviceType 
                FROM Inventory 
                WHERE DeviceType IS NOT NULL AND DeviceType <> '' 
                ORDER BY DeviceType
            """)
            rows = cursor.fetchall()
            conn.close()

            for row in rows:
                self.cbo_dev_type.addItem(row[0])

            self.cbo_dev_type.setCurrentIndex(-1)
        except Exception as e:
            print(f"Failed to load device types: {e}")

    def _add_new_device_type(self):
        if not self.is_admin:
            QMessageBox.warning(self, "Access Denied", "Only administrators can add new Device Types.")
            return

        text, ok = QInputDialog.getText(self, "Add Device Type", "Enter new Device Type:")
        if ok and text.strip():
            new_type = text.strip()
            index = self.cbo_dev_type.findText(new_type, Qt.MatchExactly)
            if index < 0:
                self.cbo_dev_type.addItem(new_type)
                self.cbo_dev_type.setCurrentText(new_type)
            else:
                self.cbo_dev_type.setCurrentIndex(index)

    def _delete_device_type(self):
        if not self.is_admin:
            QMessageBox.warning(self, "Access Denied", "Only administrators can remove Device Types.")
            return

        items = [self.cbo_dev_type.itemText(i) for i in range(self.cbo_dev_type.count()) if self.cbo_dev_type.itemText(i).strip()]
        if not items:
            QMessageBox.warning(self, "Warning", "No Device Types available to remove.")
            return

        current_text = self.cbo_dev_type.currentText().strip()
        if not current_text or current_text not in items:
            item, ok = QInputDialog.getItem(self, "Remove Device Type", "Select Device Type to remove:", items, 0, False)
            if ok and item:
                current_text = item
            else:
                return

        reply = QMessageBox.question(
            self,
            "Remove Option",
            f"Are you sure you want to remove '{current_text}'?\n\n"
            f"(This will remove it from the list and clear it from existing records so it won't reappear.)",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )

        if reply == QMessageBox.Yes:
            idx = self.cbo_dev_type.findText(current_text, Qt.MatchExactly)
            if idx >= 0:
                self.cbo_dev_type.removeItem(idx)
            self.cbo_dev_type.setCurrentIndex(-1)

            try:
                conn = connect_db()
                cursor = conn.cursor()
                cursor.execute("UPDATE Inventory SET DeviceType = '' WHERE DeviceType = ?", (current_text,))
                conn.commit()
                conn.close()
            except Exception as e:
                print(f"Database error clearing DeviceType: {e}")

    def save_stock_out(self):
        dev_name = self.cbo_dev_name.currentText().strip()
        dev_type = self.cbo_dev_type.currentText().strip()
        quantity = self.spn_quantity.value()
        sender = self.txt_sender.text().strip()
        receiver = self.txt_receiver.text().strip()
        send_dt = self.dt_send_datetime.dateTime().toString("yyyy-MM-dd HH:mm")
        barcode = self.txt_barcode.text().strip()
        ticket_num = self.txt_ticket_num.text().strip()
        to_where = self.txt_to_where.text().strip()
        serial_num = self.txt_serial_num.text().strip()
        hostname = self.txt_hostname.text().strip()
        notes = self.txt_notes.toPlainText().strip()

        missing_fields = []
        if not dev_name: missing_fields.append("Device Name")
        if not dev_type: missing_fields.append("Device Type")
        if not sender: missing_fields.append("Sender")
        if not receiver: missing_fields.append("Receiver")
        if not barcode: missing_fields.append("Barcode Number")
        if not ticket_num: missing_fields.append("Ticket Number")
        if not to_where: missing_fields.append("To Where")
        if not serial_num: missing_fields.append("Serial Number")

        if missing_fields:
            QMessageBox.warning(
                self, 
                "Validation Error", 
                "Please fill in all mandatory fields before proceeding:\n• " + "\n• ".join(missing_fields)
            )
            return

        try:
            conn = connect_db()
            cursor = conn.cursor()

            search_query = """
                SELECT Id, Quantity FROM Inventory 
                WHERE LOWER(DeviceName) = LOWER(?) 
                  AND LOWER(DeviceType) = LOWER(?) 
                  AND (SerialNumber = ? OR Barcode = ?)
            """
            cursor.execute(search_query, (dev_name, dev_type, serial_num, barcode))
            row = cursor.fetchone()

            if not row:
                QMessageBox.critical(
                    self, 
                    "Stock Out Error: Item Not Found", 
                    f"No matching inventory item was found in the database.\n\n"
                    f"Searched for:\n"
                    f"• Device Name: {dev_name}\n"
                    f"• Device Type: {dev_type}\n"
                    f"• Serial / Barcode: {serial_num} / {barcode}\n\n"
                    f"Please verify the entered details."
                )
                conn.close()
                return

            item_id, current_qty = row[0], row[1]

            if current_qty < quantity:
                QMessageBox.critical(
                    self, 
                    "Stock Out Error: Insufficient Quantity", 
                    f"Cannot issue {quantity} unit(s).\n\n"
                    f"Currently available in stock: {current_qty} unit(s)."
                )
                conn.close()
                return

            new_qty = current_qty - quantity
            if new_qty <= 0:
                cursor.execute("DELETE FROM Inventory WHERE Id = ?", (item_id,))
            else:
                cursor.execute("UPDATE Inventory SET Quantity = ? WHERE Id = ?", (new_qty, item_id))

            conn.commit()
            conn.close()

            audit_details = (
                f"Stock Out: {quantity}x '{dev_name}' ({dev_type}) issued to '{receiver}' "
                f"at '{to_where}'. Sent by: '{sender}'. Serial: '{serial_num}', Ticket: '{ticket_num}'."
            )
            if notes:
                audit_details += f" Notes: {notes}"

            try:
                log_audit(
                    username=self.username,
                    action_type="STOCK_OUT",
                    details=audit_details,
                    sender=sender,
                    warranty_date="",
                    ticket_number=ticket_num,
                    from_where=to_where
                )
            except TypeError:
                log_audit(self.username, "STOCK_OUT", audit_details)

            QMessageBox.information(self, "Success", f"Successfully processed Stock Out for {quantity} unit(s).")
            self.accept()

        except Exception as e:
            QMessageBox.critical(self, "Database Error", f"Failed to execute Stock Out transaction:\n{e}")