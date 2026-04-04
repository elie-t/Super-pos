"""
Data Collector Import Dialog
────────────────────────────
Opens a .txt file where each line is:  barcode,qty,
Looks up each barcode in the local item database and shows a preview table.
Returns a list of dicts on accept:
    { "barcode": str, "qty": float, "item": PurchaseLineItem|None }
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QFileDialog, QHeaderView,
    QMessageBox,
)


class DataCollectorDialog(QDialog):
    """
    Usage:
        dlg = DataCollectorDialog(parent=self)
        if dlg.exec():
            rows = dlg.rows   # list of {"barcode", "qty", "item"}
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Fill from Data Collector")
        self.resize(820, 480)
        self.rows: list[dict] = []   # populated after parsing

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(8)

        # Top bar
        top = QHBoxLayout()
        self._file_label = QLabel("No file selected")
        self._file_label.setStyleSheet("color:#555;font-size:12px;")
        top.addWidget(self._file_label, 1)
        browse_btn = QPushButton("📂  Browse…")
        browse_btn.setFixedHeight(32)
        browse_btn.setStyleSheet(
            "QPushButton{background:#1565c0;color:#fff;border:none;"
            "border-radius:4px;font-size:12px;padding:0 12px;}"
            "QPushButton:hover{background:#0d47a1;}"
        )
        browse_btn.clicked.connect(self._browse)
        top.addWidget(browse_btn)
        root.addLayout(top)

        # Table
        self._table = QTableWidget(0, 5)
        self._table.setHorizontalHeaderLabels(
            ["#", "Barcode", "Qty", "Item Code", "Item Name"]
        )
        self._table.horizontalHeader().setSectionResizeMode(4, QHeaderView.Stretch)
        self._table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self._table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._table.setAlternatingRowColors(True)
        self._table.setSelectionBehavior(QTableWidget.SelectRows)
        self._table.verticalHeader().setVisible(False)
        self._table.setStyleSheet("font-size:12px;")
        root.addWidget(self._table)

        # Summary
        self._summary_lbl = QLabel("")
        self._summary_lbl.setStyleSheet("font-size:12px;color:#555;")
        root.addWidget(self._summary_lbl)

        # Buttons
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        cancel_btn = QPushButton("Cancel")
        cancel_btn.setFixedHeight(34)
        cancel_btn.setStyleSheet(
            "QPushButton{background:#607d8b;color:#fff;border:none;"
            "border-radius:4px;font-size:13px;padding:0 16px;}"
            "QPushButton:hover{background:#455a64;}"
        )
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)

        self._import_btn = QPushButton("✓  Import")
        self._import_btn.setFixedHeight(34)
        self._import_btn.setEnabled(False)
        self._import_btn.setStyleSheet(
            "QPushButton{background:#2e7d32;color:#fff;border:none;"
            "border-radius:4px;font-size:13px;font-weight:700;padding:0 16px;}"
            "QPushButton:hover{background:#1b5e20;}"
            "QPushButton:disabled{background:#aaa;}"
        )
        self._import_btn.clicked.connect(self.accept)
        btn_row.addWidget(self._import_btn)
        root.addLayout(btn_row)

    # ── Browse / parse ────────────────────────────────────────────────────────

    def _browse(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Open Data Collector File", "",
            "Text Files (*.txt *.csv);;All Files (*)"
        )
        if not path:
            return
        self._load_file(path)

    def _load_file(self, path: str):
        from services.purchase_service import PurchaseService

        try:
            with open(path, encoding="utf-8", errors="replace") as f:
                raw_lines = f.readlines()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Cannot read file:\n{e}")
            return

        # Parse lines: barcode,qty[,anything]
        parsed = []
        for raw in raw_lines:
            line = raw.strip()
            if not line:
                continue
            parts = line.split(",")
            if len(parts) < 2:
                continue
            barcode = parts[0].strip()
            try:
                qty = float(parts[1].strip())
            except ValueError:
                continue
            if not barcode or qty <= 0:
                continue
            parsed.append((barcode, qty))

        if not parsed:
            QMessageBox.warning(self, "Empty", "No valid lines found in the file.")
            return

        # Lookup each barcode
        self.rows = []
        found = 0
        for barcode, qty in parsed:
            item = PurchaseService.lookup_item(barcode, "barcode")
            self.rows.append({"barcode": barcode, "qty": qty, "item": item})
            if item:
                found += 1

        # Populate table
        self._table.setRowCount(0)
        for i, row in enumerate(self.rows):
            item = row["item"]
            found_row = item is not None
            self._table.insertRow(i)

            def cell(text, color=None):
                c = QTableWidgetItem(str(text))
                c.setTextAlignment(Qt.AlignCenter)
                if color:
                    c.setForeground(color)
                return c

            from PySide6.QtGui import QColor
            ok_color  = QColor("#2e7d32")
            bad_color = QColor("#c62828")

            self._table.setItem(i, 0, cell(i + 1))
            self._table.setItem(i, 1, cell(row["barcode"]))
            self._table.setItem(i, 2, cell(f"{row['qty']:g}"))
            self._table.setItem(i, 3, cell(item.code if item else "", ok_color if found_row else bad_color))
            name_cell = QTableWidgetItem(item.description if item else "⚠ Not found")
            if not found_row:
                name_cell.setForeground(bad_color)
            self._table.setItem(i, 4, name_cell)

        total = len(self.rows)
        not_found = total - found
        import os
        self._file_label.setText(os.path.basename(path))
        self._summary_lbl.setText(
            f"Total: {total}   ✓ Found: {found}   ✗ Not found: {not_found}"
            + ("   (unmatched rows will be skipped)" if not_found else "")
        )
        self._import_btn.setEnabled(found > 0)
