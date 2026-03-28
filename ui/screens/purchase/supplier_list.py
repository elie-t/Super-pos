"""
Supplier List screen — searchable table + add/edit form.
"""
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFrame,
    QPushButton, QLabel, QLineEdit, QTableWidget,
    QTableWidgetItem, QHeaderView, QAbstractItemView,
    QCheckBox, QComboBox, QDoubleSpinBox, QTextEdit,
    QSplitter, QMessageBox,
)
from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtGui import QColor, QFont

from services.supplier_service import SupplierService, SupplierDetail


class SupplierListScreen(QWidget):
    back = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._current_id = ""
        self._search_timer = QTimer()
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(300)
        self._search_timer.timeout.connect(self._load_list)
        self._build_ui()
        self._load_list()

    # ── Build UI ──────────────────────────────────────────────────────────────

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Top bar
        bar = QFrame()
        bar.setFixedHeight(44)
        bar.setStyleSheet("background:#1a3a5c;")
        bar_lay = QHBoxLayout(bar)
        bar_lay.setContentsMargins(12, 0, 12, 0)

        back_btn = QPushButton("←  Back")
        back_btn.setStyleSheet(
            "QPushButton{background:rgba(255,255,255,0.15);color:#fff;border:1px solid rgba(255,255,255,0.3);"
            "border-radius:4px;padding:4px 12px;font-size:12px;}"
            "QPushButton:hover{background:rgba(255,255,255,0.3);}"
        )
        back_btn.setFixedHeight(28)
        back_btn.setCursor(Qt.PointingHandCursor)
        back_btn.clicked.connect(self.back.emit)
        bar_lay.addWidget(back_btn)

        title = QLabel("Suppliers")
        title.setStyleSheet("color:#fff;font-size:15px;font-weight:700;margin-left:12px;")
        bar_lay.addWidget(title)
        bar_lay.addStretch()

        new_btn = QPushButton("+ New Supplier")
        new_btn.setStyleSheet(
            "QPushButton{background:#2e7d32;color:#fff;border:none;"
            "border-radius:4px;padding:4px 14px;font-size:12px;font-weight:700;}"
            "QPushButton:hover{background:#1b5e20;}"
        )
        new_btn.setFixedHeight(28)
        new_btn.setCursor(Qt.PointingHandCursor)
        new_btn.clicked.connect(self._new_supplier)
        bar_lay.addWidget(new_btn)

        root.addWidget(bar)

        # Splitter: table left, form right
        splitter = QSplitter(Qt.Horizontal)
        splitter.setHandleWidth(2)
        splitter.setStyleSheet("QSplitter::handle{background:#cdd5e0;}")

        # ── Left: search + table ──────────────────────────────────────────────
        left = QWidget()
        left_lay = QVBoxLayout(left)
        left_lay.setContentsMargins(12, 10, 8, 10)
        left_lay.setSpacing(8)

        search_row = QHBoxLayout()
        self._search_box = QLineEdit()
        self._search_box.setObjectName("searchBox")
        self._search_box.setPlaceholderText("🔍 Search name, code, phone…")
        self._search_box.setFixedHeight(32)
        self._search_box.textChanged.connect(self._search_timer.start)
        search_row.addWidget(self._search_box)

        self._count_lbl = QLabel("")
        self._count_lbl.setStyleSheet(
            "background:#1a3a5c;color:#fff;border-radius:10px;"
            "padding:2px 10px;font-size:11px;font-weight:600;"
        )
        search_row.addWidget(self._count_lbl)
        left_lay.addLayout(search_row)

        self._table = QTableWidget()
        self._table.setColumnCount(5)
        self._table.setHorizontalHeaderLabels(["Name", "Code", "Phone", "Balance", "Active"])
        self._table.setAlternatingRowColors(True)
        self._table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._table.setSelectionMode(QAbstractItemView.SingleSelection)
        self._table.verticalHeader().setVisible(False)
        self._table.verticalHeader().setDefaultSectionSize(26)
        self._table.setShowGrid(True)
        hdr = self._table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.Stretch)
        for c in (1, 2, 3, 4):
            hdr.setSectionResizeMode(c, QHeaderView.ResizeToContents)
        self._table.doubleClicked.connect(self._on_double_click)
        self._table.clicked.connect(self._on_row_clicked)
        left_lay.addWidget(self._table)

        splitter.addWidget(left)

        # ── Right: form ───────────────────────────────────────────────────────
        right = QFrame()
        right.setStyleSheet("background:#f8fafc;border-left:1px solid #cdd5e0;")
        right_lay = QVBoxLayout(right)
        right_lay.setContentsMargins(16, 14, 16, 14)
        right_lay.setSpacing(10)

        form_title = QLabel("Supplier Details")
        form_title.setStyleSheet("font-size:14px;font-weight:700;color:#1a3a5c;")
        right_lay.addWidget(form_title)

        def _lbl(text):
            l = QLabel(text)
            l.setStyleSheet("font-size:11px;color:#555;font-weight:600;margin-top:4px;")
            return l

        def _field(placeholder=""):
            f = QLineEdit()
            f.setPlaceholderText(placeholder)
            f.setFixedHeight(30)
            return f

        right_lay.addWidget(_lbl("Name *"))
        self._f_name = _field("Required")
        right_lay.addWidget(self._f_name)

        row2 = QHBoxLayout()
        row2.setSpacing(8)
        col_code = QVBoxLayout()
        col_code.addWidget(_lbl("Code"))
        self._f_code = _field("Optional")
        col_code.addWidget(self._f_code)
        col_class = QVBoxLayout()
        col_class.addWidget(_lbl("Classification"))
        self._f_class = QComboBox()
        self._f_class.setFixedHeight(30)
        self._f_class.addItems(["", "A", "B", "C", "D"])
        col_class.addWidget(self._f_class)
        row2.addLayout(col_code)
        row2.addLayout(col_class)
        right_lay.addLayout(row2)

        row3 = QHBoxLayout()
        row3.setSpacing(8)
        col_ph = QVBoxLayout()
        col_ph.addWidget(_lbl("Phone"))
        self._f_phone = _field("+961…")
        col_ph.addWidget(self._f_phone)
        col_ph2 = QVBoxLayout()
        col_ph2.addWidget(_lbl("Phone 2"))
        self._f_phone2 = _field("")
        col_ph2.addWidget(self._f_phone2)
        row3.addLayout(col_ph)
        row3.addLayout(col_ph2)
        right_lay.addLayout(row3)

        right_lay.addWidget(_lbl("Email"))
        self._f_email = _field("")
        right_lay.addWidget(self._f_email)

        right_lay.addWidget(_lbl("Address"))
        self._f_address = _field("")
        right_lay.addWidget(self._f_address)

        row4 = QHBoxLayout()
        row4.setSpacing(8)
        col_cr = QVBoxLayout()
        col_cr.addWidget(_lbl("Credit Limit"))
        self._f_credit = QDoubleSpinBox()
        self._f_credit.setFixedHeight(30)
        self._f_credit.setRange(0, 99_999_999)
        self._f_credit.setDecimals(2)
        self._f_credit.setGroupSeparatorShown(True)
        col_cr.addWidget(self._f_credit)
        col_cur = QVBoxLayout()
        col_cur.addWidget(_lbl("Currency"))
        self._f_currency = QComboBox()
        self._f_currency.setFixedHeight(30)
        self._f_currency.addItems(["USD", "LBP"])
        col_cur.addWidget(self._f_currency)
        row4.addLayout(col_cr)
        row4.addLayout(col_cur)
        right_lay.addLayout(row4)

        right_lay.addWidget(_lbl("Notes"))
        self._f_notes = QTextEdit()
        self._f_notes.setFixedHeight(60)
        right_lay.addWidget(self._f_notes)

        self._f_active = QCheckBox("Active")
        self._f_active.setChecked(True)
        right_lay.addWidget(self._f_active)

        right_lay.addStretch()

        # Save button
        self._save_btn = QPushButton("💾  Save")
        self._save_btn.setFixedHeight(36)
        self._save_btn.setStyleSheet(
            "QPushButton{background:#1a6cb5;color:#fff;border:none;"
            "border-radius:6px;font-size:13px;font-weight:700;}"
            "QPushButton:hover{background:#1a3a5c;}"
        )
        self._save_btn.setCursor(Qt.PointingHandCursor)
        self._save_btn.clicked.connect(self._save)
        right_lay.addWidget(self._save_btn)

        self._status_lbl = QLabel("")
        self._status_lbl.setAlignment(Qt.AlignCenter)
        self._status_lbl.setStyleSheet("font-size:11px; color:#2e7d32;")
        right_lay.addWidget(self._status_lbl)

        splitter.addWidget(right)
        splitter.setSizes([560, 380])

        root.addWidget(splitter, stretch=1)

    # ── Data ──────────────────────────────────────────────────────────────────

    def _load_list(self):
        q = self._search_box.text().strip()
        rows = SupplierService.search(query=q, limit=500)
        self._table.setRowCount(0)
        self._table.setRowCount(len(rows))

        inactive_fg = QColor("#aaaaaa")
        inactive_bg = QColor("#f5f5f5")

        for i, r in enumerate(rows):
            vals = [
                r.name, r.code, r.phone,
                f"{r.balance:,.2f} {r.currency}",
                "✔" if r.is_active else "✘",
            ]
            for col, val in enumerate(vals):
                cell = QTableWidgetItem(str(val))
                cell.setData(Qt.UserRole, r.id)
                if not r.is_active:
                    cell.setForeground(inactive_fg)
                    cell.setBackground(inactive_bg)
                if col == 4:
                    cell.setTextAlignment(Qt.AlignCenter)
                    if r.is_active:
                        cell.setForeground(QColor("#2e7d32"))
                        cell.setFont(QFont("", -1, QFont.Bold))
                    else:
                        cell.setForeground(QColor("#c62828"))
                self._table.setItem(i, col, cell)

        self._count_lbl.setText(f"  {len(rows):,}  ")

    def _load_form(self, supplier_id: str):
        self._current_id = supplier_id
        detail = SupplierService.get(supplier_id)
        if not detail:
            return
        self._f_name.setText(detail.name)
        self._f_code.setText(detail.code)
        idx = self._f_class.findText(detail.classification or "")
        self._f_class.setCurrentIndex(max(0, idx))
        self._f_phone.setText(detail.phone)
        self._f_phone2.setText(detail.phone2)
        self._f_email.setText(detail.email)
        self._f_address.setText(detail.address)
        self._f_credit.setValue(detail.credit_limit)
        cur_idx = self._f_currency.findText(detail.currency)
        self._f_currency.setCurrentIndex(max(0, cur_idx))
        self._f_notes.setPlainText(detail.notes)
        self._f_active.setChecked(detail.is_active)
        self._status_lbl.setText("")

    def _clear_form(self):
        self._current_id = ""
        self._f_name.clear()
        self._f_code.clear()
        self._f_class.setCurrentIndex(0)
        self._f_phone.clear()
        self._f_phone2.clear()
        self._f_email.clear()
        self._f_address.clear()
        self._f_credit.setValue(0)
        self._f_currency.setCurrentIndex(0)
        self._f_notes.clear()
        self._f_active.setChecked(True)
        self._status_lbl.setText("")
        self._f_name.setFocus()

    # ── Actions ───────────────────────────────────────────────────────────────

    def _on_row_clicked(self, index):
        item = self._table.item(index.row(), 0)
        if item:
            self._load_form(item.data(Qt.UserRole))

    def _on_double_click(self, index):
        item = self._table.item(index.row(), 0)
        if item:
            self._load_form(item.data(Qt.UserRole))
            self._f_name.setFocus()

    def _new_supplier(self):
        self._table.clearSelection()
        self._clear_form()

    def _save(self):
        name = self._f_name.text().strip()
        if not name:
            QMessageBox.warning(self, "Required", "Supplier name is required.")
            self._f_name.setFocus()
            return

        from database.models.base import new_uuid
        detail = SupplierDetail(
            id=self._current_id or new_uuid(),
            name=name,
            code=self._f_code.text().strip(),
            phone=self._f_phone.text().strip(),
            phone2=self._f_phone2.text().strip(),
            email=self._f_email.text().strip(),
            address=self._f_address.text().strip(),
            classification=self._f_class.currentText(),
            credit_limit=self._f_credit.value(),
            balance=0.0,
            currency=self._f_currency.currentText(),
            notes=self._f_notes.toPlainText().strip(),
            is_active=self._f_active.isChecked(),
        )

        ok, err = SupplierService.save(detail)
        if ok:
            self._current_id = detail.id
            self._status_lbl.setStyleSheet("font-size:11px; color:#2e7d32;")
            self._status_lbl.setText("✔ Saved successfully")
            self._load_list()
            # Re-select the saved row
            for row in range(self._table.rowCount()):
                item = self._table.item(row, 0)
                if item and item.data(Qt.UserRole) == self._current_id:
                    self._table.selectRow(row)
                    break
        else:
            self._status_lbl.setStyleSheet("font-size:11px; color:#c62828;")
            self._status_lbl.setText(f"✘ {err}")
