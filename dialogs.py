import os
from datetime import datetime
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QSpinBox, QDateEdit, QDateTimeEdit, QTextEdit, QPushButton,
    QMessageBox, QFormLayout, QScrollArea, QWidget, QComboBox
)
from PyQt5.QtCore import Qt, QDate, QDateTime
from database import connect_db, log_audit


# ==========================================
# STOCK IN DIALOG
# ==========================================
class StockInDialog(QDialog):
    def __init__(self, username="System", parent=None):
        if isinstance(username, QWidget):
            parent = username
            username = getattr(parent, 'username', 'System')
        
        super().__init__(parent)
        self.username = username
        self.setWindowTitle("Stock In - Inbound Transaction")
        self.resize(540, 750)
        self.setStyleSheet("QDialog { background-color: #FFFFFF; }")
        self._init_ui()

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

        # 1. Device Name *
        self.txt_dev_name = QLineEdit()
        self.txt_dev_name.setPlaceholderText("e.g. ThinkPad X1 Carbon, Dell Latitude")
        self._style_input(self.txt_dev_name)

        # 2. Device Type *
        self.txt_dev_type = QLineEdit()
        self.txt_dev_type.setPlaceholderText("e.g. Laptop, Monitor, Adapter, Printer")
        self._style_input(self.txt_dev_type)

        # 3. Quantity *
        self.spn_quantity = QSpinBox()
        self.spn_quantity.setRange(1, 10000)
        self.spn_quantity.setValue(1)
        self._style_input(self.spn_quantity)

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
        self.dt_warranty_date = QDateEdit()
        self.dt_warranty_date.setDate(QDate.currentDate().addYears(1))
        self.dt_warranty_date.setDisplayFormat("yyyy-MM-dd")
        self.dt_warranty_date.setCalendarPopup(True)
        self._style_input(self.dt_warranty_date)

        # 8. Barcode Number *
        self.txt_barcode = QLineEdit()
        self.txt_barcode.setPlaceholderText("Asset tag or barcode scan")
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

        # 13. Notes
        self.txt_notes = QTextEdit()
        self.txt_notes.setPlaceholderText("Condition remarks, batch details, extra context...")
        self.txt_notes.setFixedHeight(70)
        self.txt_notes.setStyleSheet("border: 1px solid #D0D5DD; border-radius: 4px; padding: 6px; font-size: 12px;")

        # Form Layout Setup
        form_layout.addRow(self._make_label("Device Name *"), self.txt_dev_name)
        form_layout.addRow(self._make_label("Device Type *"), self.txt_dev_type)
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

    def save_stock_in(self):
        dev_name = self.txt_dev_name.text().strip()
        dev_type = self.txt_dev_type.text().strip()
        quantity = self.spn_quantity.value()
        sender = self.txt_sender.text().strip()
        receiver = self.txt_receiver.text().strip()
        receive_dt = self.dt_receive_datetime.dateTime().toString("yyyy-MM-dd HH:mm")
        warranty_date = self.dt_warranty_date.date().toString("yyyy-MM-dd")
        barcode = self.txt_barcode.text().strip()
        ticket_num = self.txt_ticket_num.text().strip()
        from_where = self.txt_from_where.text().strip()
        serial_num = self.txt_serial_num.text().strip()
        hostname = self.txt_hostname.text().strip()
        notes = self.txt_notes.toPlainText().strip()

        # Validation
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
                (DeviceName, DeviceType, Quantity, Sender, Receiver, ReceiveDate, WarrantyDate, Barcode, TicketNumber, FromWhere, SerialNumber, HostName, Note)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """
            cursor.execute(query, (
                dev_name, dev_type, quantity, sender, receiver, receive_dt,
                warranty_date, barcode, ticket_num, from_where, serial_num, hostname, notes
            ))
            conn.commit()
            conn.close()

            # Log transaction in Audit Table
            audit_details = f"Stock In: Added {quantity}x '{dev_name}' ({dev_type}) received from '{sender}'."
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
    def __init__(self, username="System", parent=None):
        if isinstance(username, QWidget):
            parent = username
            username = getattr(parent, 'username', 'System')

        super().__init__(parent)
        self.username = username
        self.setWindowTitle("Stock Out - Outbound Transaction")
        self.resize(540, 750)
        self.setStyleSheet("QDialog { background-color: #FFFFFF; }")
        self._init_ui()

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

        # 1. Device Name *
        self.txt_dev_name = QLineEdit()
        self.txt_dev_name.setPlaceholderText("e.g. ThinkPad X1 Carbon, Dell Latitude")
        self._style_input(self.txt_dev_name)

        # 2. Device Type *
        self.txt_dev_type = QLineEdit()
        self.txt_dev_type.setPlaceholderText("e.g. Laptop, Monitor, Adapter, Printer")
        self._style_input(self.txt_dev_type)

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
        form_layout.addRow(self._make_label("Device Name *"), self.txt_dev_name)
        form_layout.addRow(self._make_label("Device Type *"), self.txt_dev_type)
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

    def save_stock_out(self):
        dev_name = self.txt_dev_name.text().strip()
        dev_type = self.txt_dev_type.text().strip()
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

        # Strict Mandatory Validation Check
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

            # Search database for a matching item
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

            # Check quantity availability
            if current_qty < quantity:
                QMessageBox.critical(
                    self, 
                    "Stock Out Error: Insufficient Quantity", 
                    f"Cannot issue {quantity} unit(s).\n\n"
                    f"Currently available in stock: {current_qty} unit(s)."
                )
                conn.close()
                return

            # Deduct quantity or remove item if quantity hits 0
            new_qty = current_qty - quantity
            if new_qty <= 0:
                cursor.execute("DELETE FROM Inventory WHERE Id = ?", (item_id,))
            else:
                cursor.execute("UPDATE Inventory SET Quantity = ? WHERE Id = ?", (new_qty, item_id))

            conn.commit()
            conn.close()

            # Log transaction in Audit Table
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