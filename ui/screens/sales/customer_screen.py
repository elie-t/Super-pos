"""Customer management screen — list + create/edit form."""
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QSplitter,
    QFrame, QLabel, QPushButton, QLineEdit, QComboBox,
    QCheckBox, QDoubleSpinBox, QTextEdit, QListWidget,
    QListWidgetItem, QMessageBox, QFormLayout, QGroupBox,
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont

from services.customer_service import CustomerService


class CustomerScreen(QWidget):
    back = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._selected_id = ""
        self._build_ui()
        self._load()

    # ── Build ──────────────────────────────────────────────────────────────────

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Header bar
        bar = QFrame()
        bar.setFixedHeight(44)
        bar.setStyleSheet("background:#1a3a5c;")
        bl = QHBoxLayout(bar)
        bl.setContentsMargins(12, 0, 12, 0)
        back_btn = QPushButton("←  Back")
        back_btn.setStyleSheet(
            "QPushButton{background:rgba(255,255,255,0.15);color:#fff;border:1px solid rgba(255,255,255,0.3);"
            "border-radius:4px;padding:4px 12px;font-size:12px;}"
            "QPushButton:hover{background:rgba(255,255,255,0.3);}"
        )
        back_btn.setFixedHeight(28)
        back_btn.setCursor(Qt.PointingHandCursor)
        back_btn.clicked.connect(self.back.emit)
        bl.addWidget(back_btn)
        title = QLabel("👥  Customers")
        title.setStyleSheet("color:#fff;font-size:15px;font-weight:700;margin-left:12px;")
        bl.addWidget(title)
        bl.addStretch()
        root.addWidget(bar)

        # Splitter: left = list, right = form
        splitter = QSplitter(Qt.Horizontal)
        splitter.setHandleWidth(1)
        splitter.setStyleSheet("QSplitter::handle{background:#cdd5e0;}")

        # ── Left: search + list ────────────────────────────────────────────────
        left = QWidget()
        left.setMinimumWidth(260)
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 0, 0)
        ll.setSpacing(0)

        search_bar = QFrame()
        search_bar.setStyleSheet("background:#f0f4f8;border-bottom:1px solid #cdd5e0;")
        sl = QHBoxLayout(search_bar)
        sl.setContentsMargins(8, 6, 8, 6)
        sl.setSpacing(6)
        self._search = QLineEdit()
        self._search.setPlaceholderText("Search name, phone, code…")
        self._search.setFixedHeight(30)
        self._search.textChanged.connect(self._load)
        sl.addWidget(self._search)
        self._inactive_chk = QCheckBox("Show inactive")
        self._inactive_chk.setStyleSheet("font-size:11px;color:#555;")
        self._inactive_chk.stateChanged.connect(self._load)
        sl.addWidget(self._inactive_chk)
        ll.addWidget(search_bar)

        self._list = QListWidget()
        self._list.setStyleSheet(
            "QListWidget{border:none;font-size:13px;}"
            "QListWidget::item{padding:8px 12px;border-bottom:1px solid #eef0f3;}"
            "QListWidget::item:selected{background:#1a3a5c;color:#fff;}"
            "QListWidget::item:hover:!selected{background:#e8f0fb;}"
        )
        self._list.itemClicked.connect(self._on_select)
        ll.addWidget(self._list, 1)

        new_btn = QPushButton("➕  New Customer")
        new_btn.setStyleSheet(
            "QPushButton{background:#1a3a5c;color:#fff;border:none;"
            "font-size:13px;font-weight:700;padding:10px;}"
            "QPushButton:hover{background:#0d2a4a;}"
        )
        new_btn.setCursor(Qt.PointingHandCursor)
        new_btn.clicked.connect(self._new)
        ll.addWidget(new_btn)

        splitter.addWidget(left)

        # ── Right: form ───────────────────────────────────────────────────────
        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(16, 12, 16, 12)
        rl.setSpacing(10)

        grp = QGroupBox("Customer Details")
        grp.setStyleSheet(
            "QGroupBox{font-size:13px;font-weight:700;color:#1a3a5c;"
            "border:1px solid #cdd5e0;border-radius:6px;margin-top:8px;padding-top:10px;}"
            "QGroupBox::title{subcontrol-origin:margin;left:10px;padding:0 4px;}"
        )
        form = QFormLayout(grp)
        form.setSpacing(8)
        form.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)

        def field(placeholder, width=None):
            e = QLineEdit()
            e.setPlaceholderText(placeholder)
            e.setFixedHeight(30)
            if width:
                e.setFixedWidth(width)
            return e

        self._name_edit   = field("Full name *")
        self._code_edit   = field("Optional short code", 120)
        self._phone_edit  = field("+961…")
        self._phone2_edit = field("+961… (secondary)")
        self._email_edit  = field("email@example.com")
        self._addr_edit   = QTextEdit()
        self._addr_edit.setFixedHeight(56)
        self._addr_edit.setPlaceholderText("Street, city…")

        self._class_combo = QComboBox()
        self._class_combo.setFixedWidth(80)
        self._class_combo.setFixedHeight(30)
        self._class_combo.addItems(["", "A", "B", "C", "D"])

        self._currency_combo = QComboBox()
        self._currency_combo.setFixedWidth(80)
        self._currency_combo.setFixedHeight(30)
        self._currency_combo.addItems(["LBP", "USD"])

        self._credit_spin = QDoubleSpinBox()
        self._credit_spin.setFixedHeight(30)
        self._credit_spin.setFixedWidth(140)
        self._credit_spin.setRange(0, 999_999_999)
        self._credit_spin.setDecimals(0)
        self._credit_spin.setSingleStep(100_000)

        self._notes_edit = QTextEdit()
        self._notes_edit.setFixedHeight(56)
        self._notes_edit.setPlaceholderText("Internal notes…")

        self._active_chk = QCheckBox("Active")
        self._active_chk.setChecked(True)

        form.addRow("Name *",        self._name_edit)
        form.addRow("Code",          self._code_edit)
        form.addRow("Phone",         self._phone_edit)
        form.addRow("Phone 2",       self._phone2_edit)
        form.addRow("Email",         self._email_edit)
        form.addRow("Address",       self._addr_edit)

        cls_row = QHBoxLayout()
        cls_row.setSpacing(20)
        cls_row.addWidget(QLabel("Class:"))
        cls_row.addWidget(self._class_combo)
        cls_row.addWidget(QLabel("Currency:"))
        cls_row.addWidget(self._currency_combo)
        cls_row.addStretch()
        form.addRow("",              cls_row)

        form.addRow("Credit Limit",  self._credit_spin)
        form.addRow("Notes",         self._notes_edit)
        form.addRow("",              self._active_chk)

        rl.addWidget(grp)

        # Balance row (read-only)
        bal_row = QFrame()
        bal_row.setStyleSheet(
            "background:#e8f5e9;border:1px solid #a5d6a7;border-radius:6px;"
        )
        blrl = QHBoxLayout(bal_row)
        blrl.setContentsMargins(12, 6, 12, 6)
        bal_lbl = QLabel("Outstanding Balance:")
        bal_lbl.setStyleSheet("font-size:12px;font-weight:600;color:#1b5e20;")
        blrl.addWidget(bal_lbl)
        self._balance_lbl = QLabel("—")
        self._balance_lbl.setStyleSheet(
            "font-size:14px;font-weight:700;color:#1b5e20;"
        )
        blrl.addWidget(self._balance_lbl)
        blrl.addStretch()
        rl.addWidget(bal_row)

        self._status_lbl = QLabel("")
        self._status_lbl.setFixedHeight(18)
        rl.addWidget(self._status_lbl)

        # Buttons
        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)

        save_btn = QPushButton("💾  Save")
        save_btn.setFixedHeight(34)
        save_btn.setStyleSheet(
            "QPushButton{background:#2e7d32;color:#fff;border:none;"
            "border-radius:6px;font-size:13px;font-weight:700;padding:0 20px;}"
            "QPushButton:hover{background:#1b5e20;}"
        )
        save_btn.setCursor(Qt.PointingHandCursor)
        save_btn.clicked.connect(self._save)

        self._stmt_btn = QPushButton("📄  Statement")
        self._stmt_btn.setFixedHeight(34)
        self._stmt_btn.setEnabled(False)
        self._stmt_btn.setStyleSheet(
            "QPushButton{background:#1565c0;color:#fff;border:none;"
            "border-radius:6px;font-size:13px;font-weight:700;padding:0 14px;}"
            "QPushButton:hover{background:#0d47a1;}"
            "QPushButton:disabled{background:#bdbdbd;}"
        )
        self._stmt_btn.setCursor(Qt.PointingHandCursor)
        self._stmt_btn.clicked.connect(self._open_statement)

        btn_row.addWidget(save_btn)
        btn_row.addWidget(self._stmt_btn)
        btn_row.addStretch()
        rl.addLayout(btn_row)
        rl.addStretch()

        splitter.addWidget(right)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)

        root.addWidget(splitter, 1)

    # ── Data ───────────────────────────────────────────────────────────────────

    def _load(self):
        query   = self._search.text().strip()
        inc_in  = self._inactive_chk.isChecked()
        rows    = CustomerService.list_customers(query, include_inactive=inc_in)
        self._list.clear()
        for r in rows:
            phone = f"  —  {r['phone']}" if r["phone"] else ""
            badge = "  ●" if not r["is_active"] else ""
            label = f"{r['name']}{phone}{badge}"
            item  = QListWidgetItem(label)
            item.setData(Qt.UserRole, r)
            if not r["is_active"]:
                item.setForeground(Qt.gray)
                f = item.font(); f.setItalic(True); item.setFont(f)
            self._list.addItem(item)

    def _on_select(self, item: QListWidgetItem):
        r = item.data(Qt.UserRole)
        self._selected_id = r["id"]
        self._name_edit.setText(r["name"])
        self._code_edit.setText(r["code"])
        self._phone_edit.setText(r["phone"])
        self._phone2_edit.setText(r["phone2"])
        self._email_edit.setText(r["email"])
        self._addr_edit.setPlainText(r["address"])
        idx = self._class_combo.findText(r["classification"])
        self._class_combo.setCurrentIndex(max(0, idx))
        idx2 = self._currency_combo.findText(r["currency"])
        self._currency_combo.setCurrentIndex(max(0, idx2))
        self._credit_spin.setValue(r["credit_limit"])
        self._notes_edit.setPlainText(r["notes"])
        self._active_chk.setChecked(r["is_active"])

        bal = r["balance"]
        cur = r["currency"]
        sym = "ل.ل" if cur == "LBP" else "$"
        self._balance_lbl.setText(
            f"{sym} {bal:,.0f}" if cur == "LBP" else f"{sym} {bal:,.2f}"
        )
        self._stmt_btn.setEnabled(True)
        self._status_lbl.setText("")

    def _new(self):
        self._selected_id = ""
        for w in (self._name_edit, self._code_edit, self._phone_edit,
                  self._phone2_edit, self._email_edit):
            w.clear()
        self._addr_edit.clear()
        self._notes_edit.clear()
        self._class_combo.setCurrentIndex(0)
        self._currency_combo.setCurrentIndex(0)
        self._credit_spin.setValue(0)
        self._active_chk.setChecked(True)
        self._balance_lbl.setText("—")
        self._stmt_btn.setEnabled(False)
        self._status_lbl.setText("")
        self._name_edit.setFocus()

    def _save(self):
        name = self._name_edit.text().strip()
        if not name:
            self._status_lbl.setStyleSheet("color:#c62828;font-size:12px;")
            self._status_lbl.setText("Name is required.")
            return

        ok, result = CustomerService.save_customer(
            customer_id    = self._selected_id,
            name           = name,
            code           = self._code_edit.text().strip(),
            phone          = self._phone_edit.text().strip(),
            phone2         = self._phone2_edit.text().strip(),
            email          = self._email_edit.text().strip(),
            address        = self._addr_edit.toPlainText().strip(),
            classification = self._class_combo.currentText(),
            credit_limit   = self._credit_spin.value(),
            currency       = self._currency_combo.currentText(),
            notes          = self._notes_edit.toPlainText().strip(),
            is_active      = self._active_chk.isChecked(),
        )
        if ok:
            self._selected_id = result
            self._status_lbl.setStyleSheet("color:#2e7d32;font-size:12px;")
            self._status_lbl.setText("✔  Saved.")
            self._stmt_btn.setEnabled(True)
            self._load()
        else:
            self._status_lbl.setStyleSheet("color:#c62828;font-size:12px;")
            self._status_lbl.setText(f"Error: {result}")

    def _open_statement(self):
        if not self._selected_id:
            return
        data = CustomerService.get_statement(self._selected_id)
        if data:
            CustomerStatementDialog(data, self).exec()


# ── Customer Statement Dialog ──────────────────────────────────────────────────

class CustomerStatementDialog:
    """Shows all invoices for a customer with totals."""

    def __new__(cls, data: dict, parent=None):
        from PySide6.QtWidgets import (
            QDialog, QVBoxLayout, QHBoxLayout, QFrame, QLabel,
            QPushButton, QTableWidget, QTableWidgetItem, QHeaderView,
            QAbstractItemView,
        )
        from PySide6.QtGui import QColor, QFont as _Font
        from PySide6.QtCore import Qt as _Qt

        c    = data["customer"]
        invs = data["invoices"]
        cur  = c["currency"]
        sym  = "ل.ل" if cur == "LBP" else "$"

        dlg = QDialog(parent)
        dlg.setWindowTitle(f"Statement — {c['name']}")
        dlg.setMinimumSize(820, 520)

        root = QVBoxLayout(dlg)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Header
        hdr = QFrame(); hdr.setFixedHeight(48)
        hdr.setStyleSheet("background:#1a3a5c;")
        hl = QHBoxLayout(hdr); hl.setContentsMargins(16, 0, 16, 0)
        hl.addWidget(_lbl(f"📄  {c['name']}", "#fff", 15, bold=True))
        hl.addStretch()
        phone_lbl = _lbl(c["phone"], "#aed6f1", 12)
        if c["phone"]:
            hl.addWidget(phone_lbl)
        root.addWidget(hdr)

        # Summary bar
        sbar = QFrame()
        sbar.setFixedHeight(52)
        sbar.setStyleSheet("background:#e8f0fb;border-bottom:1px solid #cdd5e0;")
        sl = QHBoxLayout(sbar); sl.setContentsMargins(16, 0, 16, 0); sl.setSpacing(32)

        def stat(label, val):
            w = QWidget()
            wl = QHBoxLayout(w); wl.setContentsMargins(0,0,0,0); wl.setSpacing(6)
            wl.addWidget(_lbl(label, "#666", 11))
            wl.addWidget(_lbl(val, "#1a3a5c", 14, bold=True))
            return w

        total_due = sum(i["balance"] for i in invs if i["currency"] == cur)
        sl.addWidget(stat("Balance:", f"{sym} {c['balance']:,.0f}"))
        sl.addWidget(stat("Credit Limit:", f"{sym} {c['credit_limit']:,.0f}"))
        sl.addWidget(stat("Open Invoices:", str(sum(1 for i in invs if i["payment_status"] != "paid"))))
        sl.addWidget(stat("Total Due:", f"{sym} {total_due:,.0f}"))
        sl.addStretch()
        root.addWidget(sbar)

        # Table
        tbl = QTableWidget()
        tbl.setColumnCount(7)
        tbl.setHorizontalHeaderLabels(
            ["Invoice #", "W", "Date", "Branch", "Total", "Paid", "Status"]
        )
        tbl.setEditTriggers(QAbstractItemView.NoEditTriggers)
        tbl.setSelectionBehavior(QAbstractItemView.SelectRows)
        tbl.verticalHeader().setVisible(False)
        tbl.verticalHeader().setDefaultSectionSize(28)
        tbl.setAlternatingRowColors(True)
        tbl.setShowGrid(True)
        h = tbl.horizontalHeader()
        h.setStyleSheet("QHeaderView::section{background:#1a3a5c;color:#fff;"
                        "font-weight:700;border:none;padding:4px;}")
        for col, w in ((0, 110), (1, 34), (2, 90), (4, 120), (5, 120), (6, 80)):
            h.setSectionResizeMode(col, QHeaderView.Fixed)
            tbl.setColumnWidth(col, w)
        h.setSectionResizeMode(3, QHeaderView.Stretch)

        tbl.setRowCount(len(invs))
        for i, inv in enumerate(invs):
            s = "ل.ل" if inv["currency"] == "LBP" else "$"
            wn = inv["warehouse_num"]
            wn_str = str(wn) if wn != "" else "—"
            status_color = "#2e7d32" if inv["payment_status"] == "paid" else "#e65100"

            def ci(txt, align=_Qt.AlignCenter, color=None, bold=False):
                it = QTableWidgetItem(str(txt))
                it.setTextAlignment(align)
                if color: it.setForeground(QColor(color))
                if bold:  it.setFont(_Font("", -1, _Font.Bold))
                return it

            tbl.setItem(i, 0, ci(inv["invoice_number"], _Qt.AlignLeft | _Qt.AlignVCenter))
            tbl.setItem(i, 1, ci(wn_str, color="#1565c0", bold=True))
            tbl.setItem(i, 2, ci(inv["date"]))
            tbl.setItem(i, 3, ci(inv["warehouse_name"], _Qt.AlignLeft | _Qt.AlignVCenter))
            tbl.setItem(i, 4, ci(f"{s} {inv['total']:,.0f}", _Qt.AlignRight | _Qt.AlignVCenter, bold=True))
            tbl.setItem(i, 5, ci(f"{s} {inv['amount_paid']:,.0f}", _Qt.AlignRight | _Qt.AlignVCenter))
            tbl.setItem(i, 6, ci(inv["payment_status"].upper(), color=status_color, bold=True))

        root.addWidget(tbl, 1)

        # Footer
        foot = QFrame(); foot.setFixedHeight(44)
        foot.setStyleSheet("background:#f0f4f8;border-top:1px solid #cdd5e0;")
        fl = QHBoxLayout(foot); fl.setContentsMargins(16, 0, 16, 0)
        fl.addStretch()
        close = QPushButton("Close")
        close.setFixedHeight(30)
        close.setStyleSheet(
            "QPushButton{background:#607d8b;color:#fff;border:none;"
            "border-radius:4px;font-size:12px;font-weight:700;padding:0 20px;}"
            "QPushButton:hover{background:#455a64;}"
        )
        close.clicked.connect(dlg.accept)
        fl.addWidget(close)
        root.addWidget(foot)

        return dlg


def _lbl(text, color, size, bold=False):
    l = QLabel(text)
    w = "700" if bold else "400"
    l.setStyleSheet(f"color:{color};font-size:{size}px;font-weight:{w};background:transparent;")
    return l
