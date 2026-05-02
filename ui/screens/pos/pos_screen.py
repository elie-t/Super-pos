"""
POS Screen — fast cashier interface.

Layout
──────
Left  (55 %) : barcode/search bar  ▸  items table  ▸  action bar
Right (45 %) : totals panel  ▸  PAY button  ▸  function buttons  ▸  quick-cash

Shortcuts
─────────
F8  = Pay        F9  = Print last    F10 = Price check
F2  = Hold       F3  = Recall        F4  = New Sale
Del = Void line  Esc = Scan focus
"""
import json
import threading
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QLabel, QPushButton,
    QLineEdit, QFrame, QTableWidget, QTableWidgetItem, QHeaderView,
    QAbstractItemView, QDialog, QSplitter, QGridLayout,
    QListWidget, QListWidgetItem, QDialogButtonBox, QMessageBox,
    QDoubleSpinBox, QDateEdit, QInputDialog,
)
from PySide6.QtCore import Qt, Signal, QTimer, QObject, QEvent
from PySide6.QtGui import QColor, QFont, QKeySequence, QShortcut

from services.pos_service import PosService, PosLineItem
from services.item_service import ItemService
from services.auth_service import AuthService

# All POS prices in LBP
CURRENCY      = "LBP"
LBP_RATE      = 89_500       # 1 USD → LBP
POS_PRICE_TYPE = "individual"

# LBP quick-cash note denominations
LBP_NOTES = [50_000, 100_000, 200_000, 500_000, 1_000_000, 5_000_000]

# ── column indices ─────────────────────────────────────────────────────────────
COL_NUM   = 0
COL_CODE  = 1
COL_DESC  = 2
COL_QTY   = 3
COL_PRICE = 4
COL_DISC  = 5
COL_TOT   = 6
COL_DEL   = 7


# ──────────────────────────────────────────────────────────────────────────────
# Payment dialog  (LBP only)
# ──────────────────────────────────────────────────────────────────────────────

class PaymentDialog(QDialog):
    def __init__(self, grand_total: float, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Payment")
        self.setFixedSize(500, 460)
        self._total   = grand_total
        self.method   = "cash"
        self.tendered = grand_total
        self._build()

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        # ── header ─────────────────────────────────────────────────────────
        hdr = QFrame()
        hdr.setFixedHeight(64)
        hdr.setStyleSheet("background:#1a1a2e;")
        hl = QHBoxLayout(hdr)
        hl.setContentsMargins(16, 0, 16, 0)
        t = QLabel("PAYMENT")
        t.setStyleSheet("color:#fff;font-size:16px;font-weight:700;letter-spacing:2px;")
        hl.addWidget(t)
        hl.addStretch()
        tot_col = QVBoxLayout()
        tot_col.setSpacing(2)
        tot = QLabel(f"ل.ل  {self._total:,.0f}")
        tot.setStyleSheet("color:#00e676;font-size:24px;font-weight:700;")
        tot.setAlignment(Qt.AlignRight)
        tot_col.addWidget(tot)
        try:
            from database.engine import get_session, init_db
            from database.models.items import Setting
            init_db()
            _s = get_session()
            try:
                _r = _s.get(Setting, "lbp_rate")
                lbp_rate = int(_r.value) if _r and _r.value else 0
            finally:
                _s.close()
            if lbp_rate:
                usd = self._total / lbp_rate
                usd_lbl = QLabel(f"$  {usd:,.2f}")
                usd_lbl.setStyleSheet("color:#80cbc4;font-size:14px;font-weight:600;")
                usd_lbl.setAlignment(Qt.AlignRight)
                tot_col.addWidget(usd_lbl)
        except Exception:
            pass
        hl.addLayout(tot_col)
        lay.addWidget(hdr)

        body = QWidget()
        body.setStyleSheet("background:#f8fafc;")
        bl = QVBoxLayout(body)
        bl.setContentsMargins(20, 16, 20, 16)
        bl.setSpacing(12)

        # ── method tabs ────────────────────────────────────────────────────
        tab_row = QHBoxLayout()
        tab_row.setSpacing(0)
        self._method_btns = {}
        for key, label, color in [
            ("cash",    "💵  Cash",       "#2e7d32"),
            ("card",    "💳  Card",       "#1565c0"),
            ("account", "👤  On Account", "#6a1b9a"),
        ]:
            btn = QPushButton(label)
            btn.setFixedHeight(40)
            btn.setCheckable(True)
            btn.setStyleSheet(
                f"QPushButton{{background:#e8ecf2;color:#445566;border:1px solid #c0ccd8;"
                f"border-radius:0;font-size:13px;font-weight:600;padding:0 14px;}}"
                f"QPushButton:checked{{background:{color};color:#fff;border-color:{color};}}"
            )
            btn.clicked.connect(lambda _, k=key: self._set_method(k))
            tab_row.addWidget(btn)
            self._method_btns[key] = btn
        self._method_btns["cash"].setChecked(True)
        bl.addLayout(tab_row)

        # ── tender input ───────────────────────────────────────────────────
        tender_frame = QFrame()
        tender_frame.setStyleSheet(
            "QFrame{background:#fff;border:1px solid #d0d8e4;border-radius:6px;}"
            "QLabel{color:#1a1a2e;}"
        )
        tf = QVBoxLayout(tender_frame)
        tf.setContentsMargins(16, 12, 16, 12)
        tf.setSpacing(10)

        tender_lbl = QLabel("Amount Tendered  (ل.ل)")
        tender_lbl.setStyleSheet("font-size:12px;font-weight:700;color:#6680a0;")
        tf.addWidget(tender_lbl)

        self._tender_input = QLineEdit(f"{self._total:,.0f}")
        self._tender_input.setFixedHeight(52)
        self._tender_input.setAlignment(Qt.AlignRight)
        self._tender_input.setStyleSheet(
            "font-size:26px;font-weight:700;color:#1a3a5c;"
            "border:2px solid #1a6cb5;border-radius:5px;padding:0 12px;"
        )
        self._tender_input.textChanged.connect(self._update_change)
        self._tender_input.setPlaceholderText("leave blank = exact")
        tf.addWidget(self._tender_input)

        # Change row
        change_row = QHBoxLayout()
        change_lbl = QLabel("Change:")
        change_lbl.setStyleSheet("font-size:14px;color:#445566;font-weight:600;")
        change_row.addWidget(change_lbl)
        change_row.addStretch()
        self._change_lbl = QLabel("ل.ل  0")
        self._change_lbl.setStyleSheet("font-size:22px;font-weight:700;color:#2e7d32;")
        change_row.addWidget(self._change_lbl)
        tf.addLayout(change_row)

        bl.addWidget(tender_frame)

        # ── LBP quick amounts ──────────────────────────────────────────────
        quick_lbl = QLabel("Quick Amount  (ل.ل):")
        quick_lbl.setStyleSheet("font-size:11px;font-weight:700;color:#6680a0;")
        bl.addWidget(quick_lbl)

        qrow = QHBoxLayout()
        qrow.setSpacing(5)

        exact_btn = QPushButton("EXACT")
        exact_btn.setFixedHeight(36)
        exact_btn.setStyleSheet(
            "QPushButton{background:#e65100;color:#fff;font-size:12px;font-weight:700;"
            "border:none;border-radius:4px;}"
            "QPushButton:hover{background:#bf360c;}"
        )
        exact_btn.clicked.connect(lambda: self._set_tender(self._total))
        qrow.addWidget(exact_btn)

        for amt in LBP_NOTES:
            lbl_text = f"{amt // 1000}K" if amt < 1_000_000 else f"{amt // 1_000_000}M"
            b = QPushButton(lbl_text)
            b.setFixedHeight(36)
            b.setStyleSheet(
                "QPushButton{background:#1a6cb5;color:#fff;font-size:12px;font-weight:700;"
                "border:none;border-radius:4px;}"
                "QPushButton:hover{background:#1a3a5c;}"
            )
            b.clicked.connect(lambda _, a=amt: self._set_tender(a))
            qrow.addWidget(b)

        bl.addLayout(qrow)
        bl.addStretch()
        lay.addWidget(body, 1)

        # ── footer buttons ─────────────────────────────────────────────────
        footer = QFrame()
        footer.setFixedHeight(58)
        footer.setStyleSheet(
            "QFrame{background:#e8f0fb;border-top:1px solid #c0d0e8;}"
            "QLabel{color:#1a1a2e;}"
        )
        fl = QHBoxLayout(footer)
        fl.setContentsMargins(16, 8, 16, 8)
        fl.setSpacing(10)

        cancel = QPushButton("✕  Cancel")
        cancel.setFixedHeight(40)
        cancel.setStyleSheet(
            "QPushButton{background:#607d8b;color:#fff;font-size:13px;font-weight:700;"
            "border:none;border-radius:5px;}"
            "QPushButton:hover{background:#455a64;}"
        )
        cancel.clicked.connect(self.reject)
        fl.addWidget(cancel)
        fl.addStretch()

        confirm = QPushButton("✓  Confirm Payment  [Enter]")
        confirm.setFixedHeight(40)
        confirm.setMinimumWidth(210)
        confirm.setStyleSheet(
            "QPushButton{background:#2e7d32;color:#fff;font-size:14px;font-weight:700;"
            "border:none;border-radius:5px;}"
            "QPushButton:hover{background:#1b5e20;}"
        )
        confirm.clicked.connect(self._confirm)
        fl.addWidget(confirm)
        QShortcut(QKeySequence("Return"), self).activated.connect(self._confirm)

        lay.addWidget(footer)
        self._tender_input.setFocus()
        self._update_change()

    def _set_method(self, key: str):
        self.method = key
        for k, btn in self._method_btns.items():
            btn.setChecked(k == key)

    def _set_tender(self, amount: float):
        self._tender_input.setText(f"{amount:,.0f}")
        self._tender_input.selectAll()

    def _update_change(self):
        txt = self._tender_input.text().strip().replace(",", "")
        try:
            tendered = float(txt)
        except ValueError:
            tendered = self._total   # blank = exact
        change = tendered - self._total
        self.tendered = tendered
        if change >= 0:
            self._change_lbl.setText(f"ل.ل  {change:,.0f}")
            self._change_lbl.setStyleSheet("font-size:22px;font-weight:700;color:#2e7d32;")
        else:
            self._change_lbl.setText(f"ل.ل  {change:,.0f}")
            self._change_lbl.setStyleSheet("font-size:22px;font-weight:700;color:#c62828;")

    def _confirm(self):
        txt = self._tender_input.text().strip().replace(",", "")
        try:
            self.tendered = float(txt)
        except ValueError:
            self.tendered = self._total  # blank = exact
        # allow 1 LBP tolerance for rounding
        if self.method == "cash" and self.tendered < self._total - 1:
            QMessageBox.warning(self, "Insufficient",
                                "Tendered amount is less than the total.")
            return
        self.accept()


# ──────────────────────────────────────────────────────────────────────────────
# Held-sales recall dialog
# ──────────────────────────────────────────────────────────────────────────────

class RecallDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Recall Held Sale")
        self.setFixedSize(520, 360)
        self.chosen_json = None

        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 16, 16, 16)
        lay.setSpacing(10)

        lbl = QLabel("Select a held sale to recall:")
        lbl.setStyleSheet("font-size:13px;font-weight:700;color:#1a3a5c;")
        lay.addWidget(lbl)

        self._list = QListWidget()
        self._list.setStyleSheet("font-size:13px;")
        self._list.itemDoubleClicked.connect(self._pick)
        lay.addWidget(self._list, 1)

        row = QHBoxLayout()
        del_btn = QPushButton("🗑  Delete")
        del_btn.setStyleSheet(
            "QPushButton{background:#c62828;color:#fff;border:none;border-radius:4px;"
            "padding:6px 14px;font-weight:700;}"
            "QPushButton:hover{background:#a01010;}"
        )
        del_btn.clicked.connect(self._delete_selected)
        row.addWidget(del_btn)
        row.addStretch()
        recall_btn = QPushButton("✓  Recall")
        recall_btn.setStyleSheet(
            "QPushButton{background:#2e7d32;color:#fff;border:none;border-radius:4px;"
            "padding:6px 18px;font-weight:700;}"
            "QPushButton:hover{background:#1b5e20;}"
        )
        recall_btn.clicked.connect(self._pick)
        row.addWidget(recall_btn)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.setStyleSheet(
            "QPushButton{background:#607d8b;color:#fff;border:none;border-radius:4px;"
            "padding:6px 14px;font-weight:700;}"
        )
        cancel_btn.clicked.connect(self.reject)
        row.addWidget(cancel_btn)
        lay.addLayout(row)

        self._held = PosService.list_held_sales()
        for h in self._held:
            it = QListWidgetItem(
                f"  {h['label']}  —  ل.ل {h['total']:,.0f}  [{h['created_at']}]"
            )
            it.setData(Qt.UserRole, h["id"])
            self._list.addItem(it)

    def _pick(self):
        item = self._list.currentItem()
        if not item:
            return
        held_id = item.data(Qt.UserRole)
        match = next((h for h in self._held if h["id"] == held_id), None)
        if match:
            self.chosen_json = match["items_json"]
            PosService.delete_held_sale(held_id)
            self.accept()

    def _delete_selected(self):
        item = self._list.currentItem()
        if not item:
            return
        held_id = item.data(Qt.UserRole)
        PosService.delete_held_sale(held_id)
        self._held = [h for h in self._held if h["id"] != held_id]
        self._list.takeItem(self._list.row(item))


# ──────────────────────────────────────────────────────────────────────────────
# Vegetable / bulk price-entry dialog
# ──────────────────────────────────────────────────────────────────────────────

class VegeDialog(QDialog):
    """
    Quick price entry for vegetables / bulk items.
    Input format:
      • A single number  → qty=1, price=that number
      • A * B            → qty=A, price=B, total=A×B
    Press Enter or click Add to confirm.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("🥬  Vegetables / Bulk")
        self.setFixedSize(360, 210)
        self.setWindowFlags(self.windowFlags() | Qt.WindowStaysOnTopHint)
        self.result_qty   = 0.0
        self.result_price = 0.0
        self.result_total = 0.0
        self._build()

    def showEvent(self, event):
        super().showEvent(event)
        self.activateWindow()
        self.raise_()
        # If the cashier typed digits before this dialog got OS focus,
        # those chars landed in the parent's scan_input (still focused then).
        # Grab them and pre-fill our input field.
        parent = self.parent()
        if parent and hasattr(parent, '_scan_input'):
            pre = parent._scan_input.text().strip()
            if pre:
                self._inp.setText(pre)
                self._inp.setCursorPosition(len(pre))
                parent._scan_input.clear()
        self._inp.setFocus()

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 16, 20, 16)
        lay.setSpacing(10)

        title = QLabel("🥬  Vegetables / Bulk Item")
        title.setStyleSheet("font-size:14px;font-weight:700;color:#1b5e20;")
        lay.addWidget(title)

        hint = QLabel("Enter a price  —  or  qty * price  (e.g.  2.5 * 3000)")
        hint.setStyleSheet("color:#666;font-size:11px;")
        lay.addWidget(hint)

        self._inp = QLineEdit()
        self._inp.setPlaceholderText("e.g.  5000  or  2.5 * 3000")
        self._inp.setFixedHeight(46)
        self._inp.setStyleSheet(
            "font-size:22px;font-weight:700;"
            "border:2px solid #1b5e20;border-radius:6px;padding:0 10px;"
        )
        self._inp.textChanged.connect(self._update_preview)
        self._inp.returnPressed.connect(self._try_accept)
        lay.addWidget(self._inp)

        self._preview = QLabel("")
        self._preview.setAlignment(Qt.AlignCenter)
        self._preview.setFixedHeight(26)
        self._preview.setStyleSheet("color:#1b5e20;font-size:15px;font-weight:700;")
        lay.addWidget(self._preview)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)
        cancel = QPushButton("Cancel")
        cancel.setFixedHeight(32)
        cancel.clicked.connect(self.reject)
        add = QPushButton("✓  Add to Cart")
        add.setFixedHeight(32)
        add.setStyleSheet(
            "QPushButton{background:#1b5e20;color:#fff;font-weight:700;"
            "border:none;border-radius:4px;font-size:13px;padding:0 16px;}"
            "QPushButton:hover{background:#2e7d32;}"
        )
        add.clicked.connect(self._try_accept)
        btn_row.addWidget(cancel)
        btn_row.addWidget(add)
        lay.addLayout(btn_row)

        self._inp.setFocus()

    def _parse(self):
        text = self._inp.text().strip()
        if not text:
            return None, None, None
        if "*" in text:
            parts = text.split("*", 1)
            try:
                a = float(parts[0].strip())
                b = float(parts[1].strip())
                return a, b, a * b
            except ValueError:
                return None, None, None
        try:
            val = float(text.replace(",", ""))
            return 1.0, val, val
        except ValueError:
            return None, None, None

    def _update_preview(self):
        qty, price, total = self._parse()
        if total is not None and total > 0:
            if qty != 1.0:
                self._preview.setText(
                    f"{qty:g} × ل.ل {price:,.0f}  =  ل.ل {total:,.0f}"
                )
            else:
                self._preview.setText(f"ل.ل {total:,.0f}")
            self._preview.setStyleSheet(
                "color:#1b5e20;font-size:15px;font-weight:700;"
            )
            self._inp.setStyleSheet(
                "font-size:22px;font-weight:700;"
                "border:2px solid #1b5e20;border-radius:6px;padding:0 10px;"
            )
        else:
            if self._inp.text().strip():
                self._preview.setText("—")
                self._preview.setStyleSheet("color:#aaa;font-size:13px;")

    def _try_accept(self):
        qty, price, total = self._parse()
        if total is None or total <= 0:
            self._inp.setStyleSheet(
                "font-size:22px;font-weight:700;"
                "border:2px solid #c62828;border-radius:6px;padding:0 10px;"
            )
            return
        self.result_qty   = qty
        self.result_price = price
        self.result_total = total
        self.accept()


# ──────────────────────────────────────────────────────────────────────────────
# Free Amount dialog
# ──────────────────────────────────────────────────────────────────────────────

class FreeAmountDialog(QDialog):
    """
    Quickly add a free-form line (custom description + amount) to the cart.
    Trigger: type  A  in the scan box and press Enter.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Free Amount Entry")
        self.setFixedSize(380, 230)
        self.setWindowFlags(self.windowFlags() | Qt.WindowStaysOnTopHint)
        self.result_desc  = ""
        self.result_qty   = 1.0
        self.result_price = 0.0
        self.result_total = 0.0
        self._build()

    def showEvent(self, event):
        super().showEvent(event)
        self.activateWindow()
        self.raise_()
        parent = self.parent()
        if parent and hasattr(parent, '_scan_input'):
            pre = parent._scan_input.text().strip()
            if pre:
                self._inp.setText(pre)
                self._inp.setCursorPosition(len(pre))
                parent._scan_input.clear()
        self._inp.setFocus()

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 16, 20, 16)
        lay.setSpacing(8)

        title = QLabel("💰  Free Amount Entry")
        title.setStyleSheet("font-size:14px;font-weight:700;color:#1a3a5c;")
        lay.addWidget(title)

        self._desc = QLineEdit()
        self._desc.setPlaceholderText("Description (optional)")
        self._desc.setFixedHeight(34)
        self._desc.setStyleSheet(
            "font-size:13px;border:1px solid #4a7aac;border-radius:4px;padding:0 8px;"
        )
        lay.addWidget(self._desc)

        self._inp = QLineEdit()
        self._inp.setPlaceholderText("Amount  —  or  qty * price  (e.g.  2 * 50000)")
        self._inp.setFixedHeight(46)
        self._inp.setStyleSheet(
            "font-size:22px;font-weight:700;"
            "border:2px solid #1a3a5c;border-radius:6px;padding:0 10px;"
        )
        self._inp.textChanged.connect(self._update_preview)
        self._inp.returnPressed.connect(self._try_accept)
        lay.addWidget(self._inp)

        self._preview = QLabel("")
        self._preview.setAlignment(Qt.AlignCenter)
        self._preview.setFixedHeight(24)
        self._preview.setStyleSheet("color:#1a3a5c;font-size:14px;font-weight:700;")
        lay.addWidget(self._preview)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)
        cancel = QPushButton("Cancel")
        cancel.setFixedHeight(32)
        cancel.clicked.connect(self.reject)
        add = QPushButton("✓  Add to Cart")
        add.setFixedHeight(32)
        add.setStyleSheet(
            "QPushButton{background:#1a3a5c;color:#fff;font-weight:700;"
            "border:none;border-radius:4px;font-size:13px;padding:0 16px;}"
            "QPushButton:hover{background:#1565c0;}"
        )
        add.clicked.connect(self._try_accept)
        btn_row.addWidget(cancel)
        btn_row.addWidget(add)
        lay.addLayout(btn_row)

        self._inp.setFocus()
        # Tab from desc goes to amount
        self._desc.returnPressed.connect(self._inp.setFocus)

    def _parse(self):
        text = self._inp.text().strip()
        if not text:
            return None, None, None
        if "*" in text:
            parts = text.split("*", 1)
            try:
                a = float(parts[0].strip())
                b = float(parts[1].strip().replace(",", ""))
                return a, b, a * b
            except ValueError:
                return None, None, None
        try:
            val = float(text.replace(",", ""))
            return 1.0, val, val
        except ValueError:
            return None, None, None

    def _update_preview(self):
        qty, price, total = self._parse()
        if total is not None and total > 0:
            if qty != 1.0:
                self._preview.setText(f"{qty:g} × ل.ل {price:,.0f}  =  ل.ل {total:,.0f}")
            else:
                self._preview.setText(f"ل.ل {total:,.0f}")
            self._preview.setStyleSheet("color:#1a3a5c;font-size:14px;font-weight:700;")
            self._inp.setStyleSheet(
                "font-size:22px;font-weight:700;"
                "border:2px solid #1a3a5c;border-radius:6px;padding:0 10px;"
            )
        elif self._inp.text().strip():
            self._preview.setText("—")
            self._preview.setStyleSheet("color:#aaa;font-size:13px;")

    def _try_accept(self):
        qty, price, total = self._parse()
        if total is None or total <= 0:
            self._inp.setStyleSheet(
                "font-size:22px;font-weight:700;"
                "border:2px solid #c62828;border-radius:6px;padding:0 10px;"
            )
            self._inp.setFocus()
            return
        self.result_desc  = self._desc.text().strip() or "Misc"
        self.result_qty   = qty
        self.result_price = price
        self.result_total = total
        self.accept()


# ──────────────────────────────────────────────────────────────────────────────
# Sales invoices list dialog
# ──────────────────────────────────────────────────────────────────────────────

class SalesListDialog(QDialog):
    def __init__(self, parent=None, warehouse_id: str = "", operator_id: str = ""):
        super().__init__(parent)
        self.setWindowTitle("POS Sales Invoices")
        self.setMinimumSize(1000, 580)
        self._warehouse_id  = warehouse_id
        self._operator_id   = operator_id
        self._all_rows: list[dict] = []
        self._show_archived = False
        self._selected_row: dict | None = None
        self.edit_lines: list[dict] | None = None
        self._build()
        self._load()

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        # ── Header ────────────────────────────────────────────────────────
        hdr = QFrame()
        hdr.setFixedHeight(44)
        hdr.setStyleSheet("background:#1a3a5c;")
        hl = QHBoxLayout(hdr)
        hl.setContentsMargins(12, 0, 12, 0)
        self._title_lbl = QLabel("📋  POS Sales Invoices")
        self._title_lbl.setStyleSheet("color:#fff;font-size:14px;font-weight:700;")
        hl.addWidget(self._title_lbl)
        hl.addStretch()

        # "Old Sales" button — blue, not yellow
        self._toggle_btn = QPushButton("📂  Old Sales")
        self._toggle_btn.setFixedHeight(28)
        self._toggle_btn.setStyleSheet(
            "QPushButton{background:#1a6cb5;color:#fff;border:none;"
            "border-radius:4px;font-size:12px;font-weight:700;padding:0 12px;}"
            "QPushButton:hover{background:#1a3a5c;border:1px solid #5599dd;}"
        )
        self._toggle_btn.setCursor(Qt.PointingHandCursor)
        self._toggle_btn.clicked.connect(self._toggle_view)
        hl.addWidget(self._toggle_btn)
        hl.addSpacing(8)

        self._search = QLineEdit()
        self._search.setPlaceholderText("Search invoice # or customer…")
        self._search.setFixedHeight(28)
        self._search.setFixedWidth(220)
        self._search.setStyleSheet(
            "background:#fff;color:#1a1a2e;border:none;border-radius:4px;padding:0 8px;"
        )
        self._search.textChanged.connect(self._filter)
        hl.addWidget(self._search)
        lay.addWidget(hdr)

        # ── Old Sales date bar (hidden until Old Sales mode) ───────────────
        self._date_bar = QFrame()
        self._date_bar.setFixedHeight(40)
        self._date_bar.setStyleSheet(
            "background:#1a6cb5;border-bottom:1px solid #1a3a5c;"
        )
        dl = QHBoxLayout(self._date_bar)
        dl.setContentsMargins(12, 4, 12, 4)
        dl.setSpacing(8)

        from PySide6.QtCore import QDate
        lbl_from = QLabel("Date:")
        lbl_from.setStyleSheet("color:#fff;font-size:12px;font-weight:600;")
        dl.addWidget(lbl_from)

        self._date_from = QDateEdit()
        self._date_from.setFixedHeight(28)
        self._date_from.setMinimumWidth(100)
        self._date_from.setDisplayFormat("dd/MM/yyyy")
        self._date_from.setCalendarPopup(True)
        self._date_from.setDate(QDate.currentDate())
        self._date_from.setStyleSheet(
            "background:#fff;color:#1a1a2e;border:none;border-radius:3px;padding:0 4px;"
        )
        dl.addWidget(self._date_from)

        lbl_to = QLabel("to")
        lbl_to.setStyleSheet("color:#fff;font-size:12px;")
        dl.addWidget(lbl_to)

        self._date_to = QDateEdit()
        self._date_to.setFixedHeight(28)
        self._date_to.setMinimumWidth(100)
        self._date_to.setDisplayFormat("dd/MM/yyyy")
        self._date_to.setCalendarPopup(True)
        self._date_to.setDate(QDate.currentDate())
        self._date_to.setStyleSheet(
            "background:#fff;color:#1a1a2e;border:none;border-radius:3px;padding:0 4px;"
        )
        dl.addWidget(self._date_to)

        load_btn = QPushButton("Load")
        load_btn.setFixedHeight(28)
        load_btn.setFixedWidth(60)
        load_btn.setStyleSheet(
            "QPushButton{background:#fff;color:#1a3a5c;border:none;"
            "border-radius:3px;font-weight:700;font-size:12px;}"
            "QPushButton:hover{background:#e8f0fb;}"
        )
        load_btn.clicked.connect(self._load)
        dl.addWidget(load_btn)

        dl.addStretch()
        self._date_bar.setVisible(False)
        lay.addWidget(self._date_bar)

        # ── Body: invoice list (left) + items panel (right) ───────────────
        body = QSplitter(Qt.Horizontal)
        body.setHandleWidth(2)

        # Left — invoice list
        left = QWidget()
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 0, 0)
        ll.setSpacing(0)

        self._table = QTableWidget()
        self._table.setColumnCount(5)
        self._table.setHorizontalHeaderLabels([
            "Invoice #", "Date", "Customer", "Cashier", "Total (ل.ل)",
        ])
        self._table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SingleSelection)
        self._table.verticalHeader().setVisible(False)
        self._table.verticalHeader().setDefaultSectionSize(34)
        self._table.setAlternatingRowColors(True)
        self._table.setShowGrid(True)
        self._table.currentItemChanged.connect(self._on_invoice_selected)

        th = self._table.horizontalHeader()
        th.setSectionResizeMode(2, QHeaderView.Stretch)
        for col, w in ((0, 80), (1, 130), (3, 140), (4, 130)):
            th.setSectionResizeMode(col, QHeaderView.Fixed)
            self._table.setColumnWidth(col, w)
        th.setStyleSheet(
            "QHeaderView::section{background:#1a3a5c;color:#fff;font-weight:700;"
            "border:none;padding:4px;}"
        )
        ll.addWidget(self._table)
        body.addWidget(left)

        # Right — items panel
        right = QFrame()
        right.setStyleSheet("QFrame{background:#f8fafc;border-left:2px solid #c8d8e8;}")
        rl = QVBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(0)

        panel_hdr = QFrame()
        panel_hdr.setFixedHeight(36)
        panel_hdr.setStyleSheet("background:#e8f0fb;border-bottom:1px solid #c8d8e8;")
        ph = QHBoxLayout(panel_hdr)
        ph.setContentsMargins(10, 0, 10, 0)
        self._detail_title = QLabel("← Select an invoice")
        self._detail_title.setStyleSheet("font-size:12px;font-weight:700;color:#1a3a5c;")
        ph.addWidget(self._detail_title)
        ph.addStretch()
        self._detail_total = QLabel("")
        self._detail_total.setStyleSheet("font-size:13px;font-weight:700;color:#2e7d32;")
        ph.addWidget(self._detail_total)
        rl.addWidget(panel_hdr)

        self._detail_table = QTableWidget()
        self._detail_table.setColumnCount(4)
        self._detail_table.setHorizontalHeaderLabels(["Description", "Qty", "Price", "Total"])
        self._detail_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._detail_table.setSelectionMode(QAbstractItemView.NoSelection)
        self._detail_table.verticalHeader().setVisible(False)
        self._detail_table.verticalHeader().setDefaultSectionSize(30)
        self._detail_table.setAlternatingRowColors(True)
        self._detail_table.setShowGrid(True)
        dth = self._detail_table.horizontalHeader()
        dth.setSectionResizeMode(0, QHeaderView.Stretch)
        for c, w in ((1, 55), (2, 100), (3, 110)):
            dth.setSectionResizeMode(c, QHeaderView.Fixed)
            self._detail_table.setColumnWidth(c, w)
        dth.setStyleSheet(
            "QHeaderView::section{background:#2a5a8c;color:#fff;font-weight:700;"
            "border:none;padding:4px;}"
        )
        self._detail_table.setStyleSheet("font-size:12px;")
        rl.addWidget(self._detail_table, 1)
        body.addWidget(right)

        body.setSizes([620, 380])
        lay.addWidget(body, 1)

        # ── Footer ────────────────────────────────────────────────────────
        footer = QFrame()
        footer.setFixedHeight(44)
        footer.setStyleSheet(
            "QFrame{background:#e8f0fb;border-top:2px solid #1a6cb5;}"
            "QLabel{color:#1a1a2e;}"
        )
        fl = QHBoxLayout(footer)
        fl.setContentsMargins(12, 6, 12, 6)
        fl.setSpacing(8)
        self._total_lbl = QLabel("")
        self._total_lbl.setStyleSheet("font-size:12px;color:#445566;font-weight:600;")
        fl.addWidget(self._total_lbl)
        fl.addStretch()

        self._edit_btn = QPushButton("✏  Edit Invoice")
        self._edit_btn.setFixedHeight(32)
        self._edit_btn.setEnabled(False)
        self._edit_btn.setStyleSheet(
            "QPushButton{background:#e65100;color:#fff;font-size:12px;font-weight:700;"
            "border:none;border-radius:5px;padding:0 14px;}"
            "QPushButton:hover{background:#bf360c;}"
            "QPushButton:disabled{background:#bbb;}"
        )
        self._edit_btn.setCursor(Qt.PointingHandCursor)
        self._edit_btn.clicked.connect(self._edit_invoice)
        fl.addWidget(self._edit_btn)

        self._print_inv_btn = QPushButton("🖨  Print")
        self._print_inv_btn.setFixedHeight(32)
        self._print_inv_btn.setEnabled(False)
        self._print_inv_btn.setStyleSheet(
            "QPushButton{background:#2e7d32;color:#fff;font-size:12px;font-weight:700;"
            "border:none;border-radius:5px;padding:0 14px;}"
            "QPushButton:hover{background:#1b5e20;}"
            "QPushButton:disabled{background:#bbb;}"
        )
        self._print_inv_btn.setCursor(Qt.PointingHandCursor)
        self._print_inv_btn.clicked.connect(self._print_selected_invoice)
        fl.addWidget(self._print_inv_btn)

        self._cancel_inv_btn = QPushButton("✕  Cancel Invoice")
        self._cancel_inv_btn.setFixedHeight(32)
        self._cancel_inv_btn.setEnabled(False)
        self._cancel_inv_btn.setStyleSheet(
            "QPushButton{background:#b71c1c;color:#fff;font-size:12px;font-weight:700;"
            "border:none;border-radius:5px;padding:0 14px;}"
            "QPushButton:hover{background:#7f0000;}"
            "QPushButton:disabled{background:#bbb;}"
        )
        self._cancel_inv_btn.setCursor(Qt.PointingHandCursor)
        self._cancel_inv_btn.clicked.connect(self._cancel_invoice)
        fl.addWidget(self._cancel_inv_btn)

        close_btn = QPushButton("Close")
        close_btn.setFixedHeight(32)
        close_btn.setStyleSheet(
            "QPushButton{background:#607d8b;color:#fff;font-size:12px;font-weight:700;"
            "border:none;border-radius:5px;padding:0 16px;}"
            "QPushButton:hover{background:#455a64;}"
        )
        close_btn.clicked.connect(self.reject)
        fl.addWidget(close_btn)
        lay.addWidget(footer)

    def _toggle_view(self):
        self._show_archived = not self._show_archived
        if self._show_archived:
            self._toggle_btn.setText("📋  Current Shift")
            self._toggle_btn.setStyleSheet(
                "QPushButton{background:#37474f;color:#fff;border:none;"
                "border-radius:4px;font-size:12px;font-weight:700;padding:0 12px;}"
                "QPushButton:hover{background:#263238;}"
            )
            self._title_lbl.setText("📂  Old Sales")
            self.setWindowTitle("POS Sales Invoices — Old Sales")
            self._date_bar.setVisible(True)
            # Don't auto-load; wait for user to pick date and press Load
            self._all_rows = []
            self._filter()
        else:
            self._toggle_btn.setText("📂  Old Sales")
            self._toggle_btn.setStyleSheet(
                "QPushButton{background:#1a6cb5;color:#fff;border:none;"
                "border-radius:4px;font-size:12px;font-weight:700;padding:0 12px;}"
                "QPushButton:hover{background:#1a3a5c;border:1px solid #5599dd;}"
            )
            self._title_lbl.setText("📋  POS Sales Invoices")
            self.setWindowTitle("POS Sales Invoices")
            self._date_bar.setVisible(False)
            self._search.clear()
            self._load()

    def _load(self):
        if self._show_archived:
            from PySide6.QtCore import QDate
            date_from = self._date_from.date().toString("yyyy-MM-dd")
            date_to   = self._date_to.date().toString("yyyy-MM-dd")
            self._all_rows = PosService.list_archived_sales(
                date_from=date_from, date_to=date_to
            )
        else:
            self._all_rows = PosService.list_sales(
                warehouse_id=self._warehouse_id,
                operator_id=self._operator_id,
            )
        self._filter()

    def _filter(self):
        q = self._search.text().strip().lower()
        rows = [r for r in self._all_rows
                if not q
                or q in r["invoice_number"].lower()
                or q in r["customer"].lower()
                or q in r["date"]]
        self._fill(rows)

    def _fill(self, rows: list[dict]):
        self._table.setRowCount(len(rows))
        grand = 0.0
        for i, r in enumerate(rows):
            grand += r["total"]

            def cell(txt, align=Qt.AlignCenter, bold=False, color=None, _r=r):
                it = QTableWidgetItem(str(txt))
                it.setTextAlignment(align)
                it.setData(Qt.UserRole, _r["id"])
                if bold:
                    it.setFont(QFont("", -1, QFont.Bold))
                if color:
                    it.setForeground(QColor(color))
                return it

            self._table.setItem(i, 0, cell(r["invoice_number"]))
            self._table.setItem(i, 1, cell(r["date"]))
            self._table.setItem(i, 2, cell(r["customer"], Qt.AlignLeft | Qt.AlignVCenter))
            self._table.setItem(i, 3, cell(r.get("cashier", "—"), Qt.AlignLeft | Qt.AlignVCenter))
            self._table.setItem(i, 4, cell(f"{r['total']:,.0f}", bold=True))

        self._total_lbl.setText(f"{len(rows)} invoices  ·  Total ل.ل  {grand:,.0f}")
        self._detail_table.setRowCount(0)
        self._detail_title.setText("← Select an invoice")
        self._detail_total.setText("")

    def _on_invoice_selected(self, current, _prev):
        if not current:
            self._selected_row = None
            self._edit_btn.setEnabled(False)
            self._print_inv_btn.setEnabled(False)
            self._cancel_inv_btn.setEnabled(False)
            return
        inv_id  = current.data(Qt.UserRole)
        inv_num = self._table.item(current.row(), 0).text()

        # Track selected row data
        self._selected_row = next(
            (r for r in self._all_rows if r["id"] == inv_id), None
        )

        # Edit/Cancel only available for current-shift (non-archived) invoices
        can_act = not self._show_archived
        self._edit_btn.setEnabled(can_act)
        self._cancel_inv_btn.setEnabled(can_act)
        self._print_inv_btn.setEnabled(True)  # print works for any invoice

        lines   = PosService.get_sale_lines(inv_id)

        self._detail_title.setText(f"Invoice  {inv_num}")
        self._detail_table.setRowCount(len(lines))
        for i, l in enumerate(lines):
            is_void = l["qty"] < 0
            bg = QColor("#ffcccc") if is_void else None
            fg = QColor("#a01010") if is_void else None
            for c, txt, align in [
                (0, l["description"],          Qt.AlignLeft | Qt.AlignVCenter),
                (1, f"{l['qty']:.3f}",         Qt.AlignCenter),
                (2, f"{l['unit_price']:,.0f}", Qt.AlignRight | Qt.AlignVCenter),
                (3, f"{l['total']:,.0f}",       Qt.AlignRight | Qt.AlignVCenter),
            ]:
                it = QTableWidgetItem(txt)
                it.setTextAlignment(align)
                if bg:
                    it.setBackground(bg)
                if fg:
                    it.setForeground(fg)
                self._detail_table.setItem(i, c, it)

        total = sum(l["total"] for l in lines)
        self._detail_total.setText(f"ل.ل  {total:,.0f}")

    def _require_manager_pin(self) -> bool:
        """Return True if PIN check passes (admin/manager skip PIN)."""
        user = AuthService.current_user()
        if user and user.role in ("admin", "manager"):
            return True
        pin, ok = QInputDialog.getText(
            self, "Manager Override", "Enter manager PIN:",
            QLineEdit.Password,
        )
        if not ok:
            return False
        if pin != "0000":
            QMessageBox.warning(self, "Access Denied", "Incorrect PIN.")
            return False
        return True

    def _cancel_invoice(self):
        if not self._selected_row:
            return
        row = self._selected_row
        if not self._require_manager_pin():
            return
        confirm = QMessageBox.question(
            self, "Cancel Invoice",
            f"Cancel invoice  {row['invoice_number']}?\n\n"
            f"This will reverse the stock deduction and remove the invoice.",
            QMessageBox.Yes | QMessageBox.No,
        )
        if confirm != QMessageBox.Yes:
            return

        user = AuthService.current_user()
        operator_id = user.id if user else ""
        ok, result = PosService.cancel_invoice(
            row["id"], row.get("warehouse_id", ""), operator_id
        )
        if ok:
            QMessageBox.information(self, "Cancelled", f"Invoice {result} cancelled.")
            self._load()
        else:
            QMessageBox.critical(self, "Error", result)

    def _print_selected_invoice(self):
        if not self._selected_row:
            return
        inv_id = self._selected_row["id"]
        payment_method = self._selected_row.get("payment_method", "cash")
        tendered = float(self._selected_row.get("amount_paid") or 0)
        from utils.receipt_printer import print_receipt
        data = PosService.get_invoice_for_print(inv_id)
        if data:
            print_receipt(data, payment_method, tendered, parent=self, show_preview=True)

    def _edit_invoice(self):
        if not self._selected_row:
            return
        row = self._selected_row
        if not self._require_manager_pin():
            return

        # Load full line data
        lines = PosService.get_sale_lines(row["id"])
        if not lines:
            QMessageBox.warning(self, "Empty", "No line items found.")
            return

        confirm = QMessageBox.question(
            self, "Edit Invoice",
            f"Load invoice  {row['invoice_number']}  into the cart for editing?\n\n"
            f"The original invoice will be cancelled and stock restored.\n"
            f"A new invoice will be created when you save.",
            QMessageBox.Yes | QMessageBox.No,
        )
        if confirm != QMessageBox.Yes:
            return

        # Cancel the original invoice first
        user = AuthService.current_user()
        operator_id = user.id if user else ""
        ok, result = PosService.cancel_invoice(
            row["id"], row.get("warehouse_id", ""), operator_id
        )
        if not ok:
            QMessageBox.critical(self, "Error", f"Could not cancel original:\n{result}")
            return

        self.edit_lines = lines
        self.accept()


# ──────────────────────────────────────────────────────────────────────────────
# ──────────────────────────────────────────────────────────────────────────────
# Elevation / Manager-override Dialog
# ──────────────────────────────────────────────────────────────────────────────

class _ElevationDialog(QDialog):
    """Ask for a manager / power-user's username + password to authorise a restricted action."""

    def __init__(self, action: str = "this action", parent=None):
        super().__init__(parent)
        self.setWindowTitle("Manager Authorisation Required")
        self.setFixedWidth(360)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 20, 24, 20)
        lay.setSpacing(12)

        icon = QLabel("🔒")
        icon.setAlignment(Qt.AlignCenter)
        icon.setStyleSheet("font-size:36px;")
        lay.addWidget(icon)

        msg = QLabel(f"<b>{action}</b> requires manager authorisation.<br>Enter a manager or power-user's credentials.")
        msg.setAlignment(Qt.AlignCenter)
        msg.setWordWrap(True)
        msg.setStyleSheet("font-size:13px;color:#1a3a5c;")
        lay.addWidget(msg)

        form = QFormLayout()
        form.setSpacing(8)
        self._user_edit = QLineEdit()
        self._user_edit.setFixedHeight(34)
        self._user_edit.setPlaceholderText("Username")
        form.addRow("Username:", self._user_edit)

        self._pass_edit = QLineEdit()
        self._pass_edit.setEchoMode(QLineEdit.Password)
        self._pass_edit.setFixedHeight(34)
        self._pass_edit.setPlaceholderText("Password")
        form.addRow("Password:", self._pass_edit)
        lay.addLayout(form)

        self._err = QLabel("")
        self._err.setStyleSheet("color:#c62828;font-size:12px;")
        self._err.hide()
        lay.addWidget(self._err)

        btn_row = QHBoxLayout()
        cancel = QPushButton("Cancel")
        cancel.setFixedHeight(34)
        cancel.setStyleSheet("QPushButton{background:#eceff1;color:#37474f;border:none;border-radius:5px;}")
        cancel.clicked.connect(self.reject)
        btn_row.addWidget(cancel)

        ok_btn = QPushButton("Authorise")
        ok_btn.setFixedHeight(34)
        ok_btn.setStyleSheet(
            "QPushButton{background:#1a3a5c;color:#fff;border:none;border-radius:5px;font-weight:700;}"
            "QPushButton:hover{background:#1a6cb5;}"
        )
        ok_btn.clicked.connect(self._verify)
        btn_row.addWidget(ok_btn)
        lay.addLayout(btn_row)

        self._pass_edit.returnPressed.connect(self._verify)

    def _verify(self):
        import bcrypt
        username = self._user_edit.text().strip()
        password = self._pass_edit.text()
        if not username or not password:
            self._show_err("Enter username and password.")
            return
        try:
            from database.engine import get_session, init_db
            from database.models.users import User
            init_db()
            session = get_session()
            try:
                user = session.query(User).filter_by(username=username, is_active=True).first()
                if not user:
                    self._show_err("Invalid credentials.")
                    return
                if not bcrypt.checkpw(password.encode(), user.password_hash.encode()):
                    self._show_err("Invalid credentials.")
                    return
                is_elevated = (
                    user.role in ("admin", "manager")
                    or bool(getattr(user, "is_power_user", False))
                )
                if not is_elevated:
                    self._show_err("That user does not have manager privileges.")
                    return
            finally:
                session.close()
        except Exception as e:
            self._show_err(f"Error: {e}")
            return
        self.accept()

    def _show_err(self, msg: str):
        self._err.setText(msg)
        self._err.show()


# ──────────────────────────────────────────────────────────────────────────────
# Online Orders Dialog
# ──────────────────────────────────────────────────────────────────────────────

class OnlineOrdersDialog(QDialog):
    """Shows all online orders for this branch (last 24 h) with status tabs."""

    load_order = Signal(dict)

    PENDING_STATUSES    = ("new", "confirmed")
    PROCESSING_STATUSES = ("processing", "preparing")
    DONE_STATUSES       = ("delivered", "finished", "cancelled")

    STATUS_COLOR = {
        "new":        "#f57c00",
        "confirmed":  "#f57c00",
        "processing": "#1a6cb5",
        "preparing":  "#1a6cb5",
        "delivered":  "#2e7d32",
        "finished":   "#2e7d32",
        "cancelled":  "#c62828",
    }
    STATUS_LABEL = {
        "new":        "🔴 Pending",
        "confirmed":  "🔴 Pending",
        "processing": "🔵 Processing",
        "preparing":  "🔵 Processing",
        "delivered":  "✅ Delivered",
        "finished":   "✅ Finished",
        "cancelled":  "✕ Cancelled",
    }

    def __init__(self, warehouse_id: str, parent=None):
        super().__init__(parent)
        self._wh_id   = warehouse_id
        self._orders: list[dict] = []
        self._filter  = "pending"
        self.setWindowTitle("🌐  Online Orders")
        self.resize(960, 560)
        self._build()
        self._load()

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 10, 12, 10)
        lay.setSpacing(8)

        # ── Filter tabs ──────────────────────────────────────────────────────
        tab_row = QHBoxLayout()
        self._tab_btns = {}
        for key, label in [("all", "All"), ("pending", "🔴 Pending"),
                            ("processing", "🔵 Processing"), ("done", "✅ Done")]:
            btn = QPushButton(label)
            btn.setCheckable(True)
            btn.setChecked(key == "pending")
            btn.setFixedHeight(30)
            btn.clicked.connect(lambda _=False, k=key: self._set_filter(k))
            btn.setStyleSheet(
                "QPushButton{background:#eef2f7;color:#1a3a5c;border:1px solid #c0ccd8;"
                "border-radius:4px;padding:0 14px;font-size:12px;font-weight:600;}"
                "QPushButton:checked{background:#1a3a5c;color:#fff;border-color:#1a3a5c;}"
            )
            self._tab_btns[key] = btn
            tab_row.addWidget(btn)
        tab_row.addStretch()
        refresh_btn = QPushButton("↺  Refresh")
        refresh_btn.setFixedHeight(30)
        refresh_btn.setStyleSheet(
            "QPushButton{background:#e8f0fb;color:#1a6cb5;border:1px solid #b0c8e8;"
            "border-radius:4px;padding:0 12px;font-size:12px;font-weight:600;}"
        )
        refresh_btn.clicked.connect(self._load)
        tab_row.addWidget(refresh_btn)
        lay.addLayout(tab_row)

        # ── Table ────────────────────────────────────────────────────────────
        self._table = QTableWidget()
        self._table.setColumnCount(7)
        self._table.setHorizontalHeaderLabels(
            ["Time", "Customer", "Phone", "Address / Type", "Items", "Total (ل.ل)", "Status"]
        )
        self._table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        self._table.horizontalHeader().setDefaultSectionSize(115)
        self._table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._table.setAlternatingRowColors(True)
        self._table.verticalHeader().setVisible(False)
        self._table.setStyleSheet("font-size:13px;")
        self._table.doubleClicked.connect(self._on_double_click)
        lay.addWidget(self._table)

        # ── Action buttons ───────────────────────────────────────────────────
        btn_row = QHBoxLayout()

        def _action_btn(label, bg, hover, slot):
            b = QPushButton(label)
            b.setFixedHeight(34)
            b.setStyleSheet(
                f"QPushButton{{background:{bg};color:#fff;border:none;border-radius:6px;"
                f"padding:0 16px;font-size:13px;font-weight:700;}}"
                f"QPushButton:hover{{background:{hover};}}"
            )
            b.clicked.connect(slot)
            return b

        btn_row.addWidget(_action_btn("📥  Load into POS",   "#1a3a5c", "#0d2a48", self._do_load))
        btn_row.addWidget(_action_btn("🔵  Mark Processing", "#1a6cb5", "#0d4a8a", self._do_processing))
        btn_row.addWidget(_action_btn("🚚  Mark Delivered",  "#2e7d32", "#1b5e20", self._do_delivered))
        btn_row.addWidget(_action_btn("✅  Mark Finished",   "#4a148c", "#311b92", self._do_finished))
        btn_row.addWidget(_action_btn("✖  Cancel Order",    "#c62828", "#b71c1c", self._do_cancel))
        btn_row.addWidget(_action_btn("🚫  Blacklist",       "#4a0000", "#2d0000", self._do_blacklist))
        btn_row.addStretch()

        close_btn = QPushButton("Close")
        close_btn.setFixedHeight(34)
        close_btn.setStyleSheet(
            "QPushButton{background:#eee;color:#333;border:1px solid #ccc;"
            "border-radius:6px;padding:0 20px;font-size:13px;}"
        )
        close_btn.clicked.connect(self.accept)
        btn_row.addWidget(close_btn)
        lay.addLayout(btn_row)

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _set_filter(self, key: str):
        self._filter = key
        for k, btn in self._tab_btns.items():
            btn.setChecked(k == key)
        self._fill_table()

    def _load(self):
        try:
            from sync.service import fetch_branch_orders
            self._orders = fetch_branch_orders(self._wh_id, hours=24)
        except Exception:
            self._orders = []
        self._fill_table()

    def _fill_table(self):
        if self._filter == "all":
            rows = self._orders
        elif self._filter == "pending":
            rows = [o for o in self._orders if o.get("status") in self.PENDING_STATUSES]
        elif self._filter == "processing":
            rows = [o for o in self._orders if o.get("status") in self.PROCESSING_STATUSES]
        elif self._filter == "done":
            rows = [o for o in self._orders if o.get("status") in self.DONE_STATUSES]
        else:
            rows = self._orders

        self._table.setRowCount(0)
        for o in rows:
            r = self._table.rowCount()
            self._table.insertRow(r)
            ts    = (o.get("created_at") or "")[:16].replace("T", " ")
            addr  = o.get("address") or ""
            dtype = "🚚 Delivery" if o.get("delivery_type") == "delivery" else "🏪 Pickup"
            addr_cell = f"{addr}  |  {dtype}" if addr and addr != "Pickup" else dtype
            n_items = len(o.get("items") or [])
            status  = o.get("status") or "new"
            color   = self.STATUS_COLOR.get(status, "#666")
            label   = self.STATUS_LABEL.get(status, status)

            for c, val in enumerate([
                ts,
                o.get("customer_name") or "—",
                o.get("customer_phone") or "—",
                addr_cell,
                str(n_items),
                f"{o.get('total', 0):,.0f}",
                label,
            ]):
                cell = QTableWidgetItem(val)
                cell.setData(Qt.UserRole, o)
                if c == 6:
                    cell.setForeground(QColor(color))
                    font = cell.font(); font.setBold(True); cell.setFont(font)
                self._table.setItem(r, c, cell)

    def _selected_order(self) -> dict | None:
        row = self._table.currentRow()
        if row < 0:
            return None
        item = self._table.item(row, 0)
        return item.data(Qt.UserRole) if item else None

    def _on_double_click(self, _idx):
        o = self._selected_order()
        if o and o.get("status") in self.PENDING_STATUSES:
            self._do_load()

    def _do_load(self):
        o = self._selected_order()
        if not o:
            QMessageBox.information(self, "Select Order", "Select an order first.")
            return
        self.load_order.emit(o)
        self.accept()

    def _set_status(self, new_status: str):
        o = self._selected_order()
        if not o:
            QMessageBox.information(self, "Select Order", "Select an order first.")
            return
        order_id = o.get("id")
        try:
            from sync.service import update_online_order_status
            update_online_order_status(order_id, new_status)
        except Exception:
            pass
        # Update self._orders by ID — QTableWidgetItem stores a copy of the dict
        # so mutating the returned object doesn't affect the source list
        for order in self._orders:
            if order.get("id") == order_id:
                order["status"] = new_status
                break
        self._fill_table()

    def _do_processing(self): self._set_status("processing")
    def _do_delivered(self):  self._set_status("delivered")
    def _do_finished(self):   self._set_status("finished")

    def _do_cancel(self):
        o = self._selected_order()
        if not o:
            QMessageBox.information(self, "Select Order", "Select an order first.")
            return
        reply = QMessageBox.question(
            self, "Cancel Order",
            f"Cancel order from {o.get('customer_name') or 'customer'}?\n"
            "The customer will be notified.",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            self._set_status("cancelled")

    def _do_blacklist(self):
        o = self._selected_order()
        if not o:
            QMessageBox.information(self, "Select Order", "Select an order first.")
            return
        phone = o.get("customer_phone") or ""
        name  = o.get("customer_name")  or "customer"
        if not phone:
            QMessageBox.warning(self, "No Phone", "This order has no phone number to blacklist.")
            return
        reason, ok = __import__('PySide6.QtWidgets', fromlist=['QInputDialog']).QInputDialog.getText(
            self, "Blacklist Reason",
            f"Blacklist {phone} ({name})?\nOptional reason:",
        )
        if not ok:
            return
        from sync.service import blacklist_phone
        if blacklist_phone(phone, reason):
            self._set_status("cancelled")
            QMessageBox.information(self, "Blacklisted",
                f"{phone} has been blacklisted.\nFuture orders from this number will be rejected.")
        else:
            QMessageBox.warning(self, "Error", "Could not blacklist phone. Check connection.")


# Main POS Screen
# ──────────────────────────────────────────────────────────────────────────────

class POSScreen(QWidget):
    back = Signal()
    # Thread-safe signal to notify UI when background sync finishes
    _prices_sync_finished_sig = Signal(int, str)

    def __init__(self, parent=None, forced_warehouse_id: str | None = None):
        super().__init__(parent)
        self._lines: list[dict] = []
        self._customer_id   = ""
        self._customer_name = "Walk-In"
        self._currency      = CURRENCY
        self._table_updating = False
        self._last_invoice_id      = ""
        self._last_payment_method  = "cash"
        self._last_tendered        = 0.0
        self._last_pack_qty        = 1    # pack_qty of the last selected cart line
        self._forced_warehouse_id  = forced_warehouse_id
        self._active_online_order_id = ""   # set when an online order is loaded into cart
        self._vege_id: str = ""             # cached after first DB lookup
        self._alert_sound = None            # QSoundEffect, created lazily
        self._alert_playing = False
        self._alert_repeat_timer = None     # QTimer: re-beep every 10 s

        self._build_ui()
        self._load_defaults()
        self._setup_shortcuts()
        self._install_focus_return_filter()
        
        # Connect the sync signal
        self._prices_sync_finished_sig.connect(self._finish_prices_sync)
        
        QTimer.singleShot(0, self._scan_input.setFocus)
        QTimer.singleShot(2000, self._poll_online_orders)  # first poll 2s after load

        # Auto-refresh cart prices when a remote price push is detected
        try:
            from sync.worker import get_sync_worker
            sw = get_sync_worker()
            if sw is not None:
                sw.prices_refreshed.connect(lambda _n: self._apply_fresh_cart_prices(update_btn=False))
        except Exception:
            pass

    def showEvent(self, event):
        super().showEvent(event)
        QTimer.singleShot(100, self._scan_input.setFocus)

    def _install_focus_return_filter(self):
        """After any mouse click on the POS screen, return focus to the barcode input
        unless the user intentionally clicked into a text/spin input."""
        from PySide6.QtWidgets import QApplication, QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox
        screen = self

        class _FocusReturnFilter(QObject):
            def eventFilter(self, obj, event):
                if event.type() == QEvent.Type.MouseButtonRelease:
                    # Walk up to check if this widget belongs to our POS screen
                    w = obj
                    while w is not None:
                        if w is screen:
                            QTimer.singleShot(150, screen._return_focus_to_scan)
                            break
                        w = w.parent()
                return False  # never consume the event

        self._focus_return_filter = _FocusReturnFilter(self)
        QApplication.instance().installEventFilter(self._focus_return_filter)

    def _return_focus_to_scan(self):
        """Set focus to barcode input unless user is actively typing in another field."""
        from PySide6.QtWidgets import QApplication, QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox
        fw = QApplication.focusWidget()
        if fw is None or fw is self._scan_input:
            self._scan_input.setFocus()
            return
        # Don't steal focus from intentional input fields
        if isinstance(fw, (QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox)):
            return
        self._scan_input.setFocus()

    # ── Build UI ───────────────────────────────────────────────────────────────

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addWidget(self._make_top_bar())

        splitter = QSplitter(Qt.Horizontal)
        splitter.setHandleWidth(3)
        splitter.addWidget(self._make_left_panel())
        splitter.addWidget(self._make_right_panel())
        splitter.setStretchFactor(0, 55)
        splitter.setStretchFactor(1, 45)
        splitter.setSizes([660, 500])
        root.addWidget(splitter, 1)

        root.addWidget(self._make_status_bar())

    # ── Top bar ────────────────────────────────────────────────────────────────

    def _make_top_bar(self):
        bar = QFrame()
        bar.setFixedHeight(44)
        bar.setStyleSheet("background:#1a3a5c;")
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(10, 0, 10, 0)
        lay.setSpacing(10)

        back_btn = QPushButton("←  Back")
        back_btn.setFixedHeight(28)
        back_btn.setStyleSheet(
            "QPushButton{background:#2a5a8c;color:#fff;border:1px solid #4a7aac;"
            "border-radius:4px;padding:2px 10px;font-size:12px;}"
            "QPushButton:hover{background:#1a4a7c;}"
        )
        back_btn.clicked.connect(self.back.emit)
        lay.addWidget(back_btn)

        self._refresh_prices_btn = QPushButton("↻  Prices")
        self._refresh_prices_btn.setFixedHeight(28)
        self._refresh_prices_btn.setStyleSheet(
            "QPushButton{background:#1a6cb5;color:#fff;border:1px solid #3a8cd5;"
            "border-radius:4px;padding:2px 10px;font-size:12px;}"
            "QPushButton:hover{background:#155a9a;}"
            "QPushButton:disabled{background:#2a4a6a;color:#7a9aba;}"
        )
        self._refresh_prices_btn.clicked.connect(self._refresh_prices)
        lay.addWidget(self._refresh_prices_btn)

        self._pos_title_lbl = QLabel("🖥️  POS — Point of Sale  (ل.ل  LBP)")
        self._pos_title_lbl.setStyleSheet("color:#fff;font-size:14px;font-weight:700;margin-left:8px;")
        lay.addWidget(self._pos_title_lbl)

        lay.addStretch()

        # Last invoice amount display
        last_inv_lbl = QLabel("Last Inv:")
        last_inv_lbl.setStyleSheet("color:#a8c8e8;font-size:12px;")
        lay.addWidget(last_inv_lbl)
        self._last_inv_amt_lbl = QLabel("—")
        self._last_inv_amt_lbl.setStyleSheet(
            "color:#00e676;font-size:12px;font-weight:700;min-width:130px;"
        )
        lay.addWidget(self._last_inv_amt_lbl)

        lay.addSpacing(16)

        # Customer display
        cust_lbl = QLabel("Customer:")
        cust_lbl.setStyleSheet("color:#a8c8e8;font-size:12px;")
        lay.addWidget(cust_lbl)
        self._cust_name_lbl = QLabel("Walk-In")
        self._cust_name_lbl.setStyleSheet(
            "color:#f0c040;font-size:12px;font-weight:700;min-width:120px;"
        )
        lay.addWidget(self._cust_name_lbl)

        self._delivery_lbl = QLabel("")
        self._delivery_lbl.setStyleSheet(
            "color:#80cbc4;font-size:10px;max-width:160px;"
        )
        self._delivery_lbl.setWordWrap(True)
        self._delivery_lbl.setVisible(False)
        lay.addWidget(self._delivery_lbl)

        change_cust = QPushButton("Change")
        change_cust.setFixedHeight(24)
        change_cust.setStyleSheet(
            "QPushButton{background:#2a5a8c;color:#fff;border:1px solid #4a7aac;"
            "border-radius:3px;padding:0 8px;font-size:11px;}"
            "QPushButton:hover{background:#1a4a7c;}"
        )
        change_cust.clicked.connect(self._change_customer)
        lay.addWidget(change_cust)

        lay.addSpacing(16)

        self._print_copies = 2   # 0=OFF  1=ON  2=ON×2  (default: ×2)
        self._print_enabled = True
        self._print_toggle_btn = QPushButton("🖨 Print: ×2")
        self._print_toggle_btn.setFixedHeight(24)
        self._print_toggle_btn.setStyleSheet(
            "QPushButton{background:#f57f17;color:#fff;border:none;"
            "border-radius:3px;padding:0 10px;font-size:11px;font-weight:700;}"
            "QPushButton:hover{background:#e65100;}"
        )
        self._print_toggle_btn.setCursor(Qt.PointingHandCursor)
        self._print_toggle_btn.clicked.connect(self._toggle_print)
        lay.addWidget(self._print_toggle_btn)

        return bar

    # ── Left panel ─────────────────────────────────────────────────────────────

    def _make_left_panel(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        # ── Scan bar ──────────────────────────────────────────────────────
        scan_bar = QFrame()
        scan_bar.setStyleSheet(
            "QFrame{background:#e8f0fb;border-bottom:2px solid #1a6cb5;}"
            "QLabel{color:#1a1a2e;}"
        )
        scan_bar.setFixedHeight(52)
        sl = QHBoxLayout(scan_bar)
        sl.setContentsMargins(10, 6, 10, 6)
        sl.setSpacing(8)

        bc_lbl = QLabel("Barcode / Code:")
        bc_lbl.setStyleSheet("font-size:12px;font-weight:700;color:#1a3a5c;")
        sl.addWidget(bc_lbl)

        self._scan_input = QLineEdit()
        self._scan_input.setPlaceholderText("Scan barcode or type item code… (/ for name search)")
        self._scan_input.setFixedHeight(36)
        self._scan_input.setMinimumWidth(220)
        self._scan_input.setStyleSheet(
            "font-size:14px;font-weight:600;border:2px solid #1a6cb5;"
            "border-radius:4px;padding:0 8px;background:#fff;color:#1a1a2e;"
        )
        self._scan_input.returnPressed.connect(self._on_barcode_entered)

        # Event filter: Ctrl+Enter → item picker, +/- → qty shortcuts
        class _ScanFilter(QObject):
            def __init__(self, screen):
                super().__init__(screen)
                self._screen = screen
            def eventFilter(self, obj, event):
                if event.type() == QEvent.Type.KeyPress:
                    k = event.key()
                    mod = event.modifiers()
                    if k in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and (mod & Qt.KeyboardModifier.ControlModifier):
                        self._screen._open_item_picker()
                        return True
                    if k == Qt.Key.Key_Plus and not self._screen._scan_input.text():
                        self._screen._increment_qty()
                        return True
                return False

        self._scan_filter = _ScanFilter(self)
        self._scan_input.installEventFilter(self._scan_filter)

        sl.addWidget(self._scan_input, 1)

        search_btn = QPushButton("🔍")
        search_btn.setFixedSize(36, 36)
        search_btn.setToolTip("Search items  (Ctrl+Enter)")
        search_btn.setStyleSheet(
            "QPushButton{background:#1a6cb5;color:#fff;font-size:15px;"
            "border:none;border-radius:4px;}"
            "QPushButton:hover{background:#1256a0;}"
        )
        search_btn.clicked.connect(self._open_item_picker)
        sl.addWidget(search_btn)

        lay.addWidget(scan_bar)

        # ── Box info bar (visible only for box items) ─────────────────────
        self._box_bar = QFrame()
        self._box_bar.setStyleSheet(
            "QFrame{background:#fff8e1;border-bottom:2px solid #f57c00;}"
            "QLabel{color:#1a1a2e;}"
        )
        self._box_bar.setFixedHeight(40)
        self._box_bar.setVisible(False)
        bl = QHBoxLayout(self._box_bar)
        bl.setContentsMargins(10, 4, 10, 4)
        bl.setSpacing(16)

        self._box_item_lbl = QLabel("")
        self._box_item_lbl.setStyleSheet("font-size:12px;font-weight:700;color:#e65100;")
        bl.addWidget(self._box_item_lbl)

        bl.addStretch()

        bl.addWidget(QLabel("Box:"))
        self._box_qty_lbl = QLabel("0")
        self._box_qty_lbl.setStyleSheet("font-size:13px;font-weight:700;color:#e65100;min-width:30px;")
        bl.addWidget(self._box_qty_lbl)

        self._box_pcs_lbl = QLabel("")
        self._box_pcs_lbl.setStyleSheet("font-size:12px;color:#555;")
        bl.addWidget(self._box_pcs_lbl)

        bl.addWidget(QLabel("Price:"))
        self._box_price_lbl = QLabel("")
        self._box_price_lbl.setStyleSheet("font-size:13px;font-weight:700;color:#e65100;")
        bl.addWidget(self._box_price_lbl)

        lay.addWidget(self._box_bar)

        # ── Items table ───────────────────────────────────────────────────
        self._table = QTableWidget()
        self._table.setColumnCount(8)
        self._table.setHorizontalHeaderLabels([
            "#", "Barcode", "Description", "Qty", "Price (ل.ل)", "Disc%", "Total (ل.ل)", "",
        ])
        self._table.setAlternatingRowColors(True)
        self._table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SingleSelection)
        self._table.setEditTriggers(
            QAbstractItemView.DoubleClicked | QAbstractItemView.SelectedClicked
        )
        self._table.verticalHeader().setVisible(False)
        self._table.verticalHeader().setDefaultSectionSize(48)
        self._table.setShowGrid(True)
        self._table.itemChanged.connect(self._on_cell_edited)
        self._table.currentCellChanged.connect(
            lambda row, *_: self._update_box_bar(row)
        )

        # Enter/Return while editing a table cell → commit + return to barcode
        class _TableFilter(QObject):
            def __init__(self, screen):
                super().__init__(screen)
                self._screen = screen
            def eventFilter(self, obj, event):
                if event.type() == QEvent.Type.KeyPress:
                    if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                        self._screen._table.clearFocus()
                        QTimer.singleShot(0, lambda: (
                            self._screen._scan_input.setFocus(),
                            self._screen._scan_input.selectAll(),
                        ))
                        return False  # let table commit the edit first
                return False
        self._table_filter = _TableFilter(self)
        self._table.installEventFilter(self._table_filter)

        th = self._table.horizontalHeader()
        th.setSectionResizeMode(COL_DESC, QHeaderView.Stretch)
        for col, w_ in ((COL_NUM, 44), (COL_CODE, 110), (COL_QTY, 80),
                        (COL_PRICE, 115), (COL_DISC, 56), (COL_TOT, 130), (COL_DEL, 72)):
            th.setSectionResizeMode(col, QHeaderView.Fixed)
            self._table.setColumnWidth(col, w_)
        th.setStyleSheet(
            "QHeaderView::section{background:#1a3a5c;color:#fff;font-weight:700;"
            "font-size:13px;border:none;padding:6px 4px;}"
        )
        self._table.setStyleSheet(
            "QTableWidget{font-size:16px;}"
            "QTableWidget::item{padding:4px 6px;}"
            "QTableWidget QLineEdit{color:#1a1a2e;background:#fff;"
            "border:2px solid #1a6cb5;font-size:16px;font-weight:700;"
            "min-height:36px;padding:0 4px;}"
        )
        lay.addWidget(self._table, 1)

        # ── Action bar ────────────────────────────────────────────────────
        act = QFrame()
        act.setStyleSheet(
            "QFrame{background:#f0f4f8;border-top:1px solid #cdd5e0;}"
            "QLabel{color:#1a1a2e;}"
        )
        act.setFixedHeight(44)
        al = QHBoxLayout(act)
        al.setContentsMargins(8, 4, 8, 4)
        al.setSpacing(8)

        def aBtn(label, color, hover, callback):
            b = QPushButton(label)
            b.setFixedHeight(32)
            b.setStyleSheet(
                f"QPushButton{{background:{color};color:#fff;font-size:12px;font-weight:700;"
                f"border:none;border-radius:4px;padding:0 10px;}}"
                f"QPushButton:hover{{background:{hover};}}"
            )
            b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(callback)
            return b

        al.addWidget(aBtn("🗑  Void Line", "#c62828", "#a01010", self._void_line))
        al.addWidget(aBtn("🧹  Clear All", "#e65100", "#bf360c", self._clear_all))
        al.addSpacing(16)
        al.addWidget(aBtn("➕  Qty", "#1a6cb5", "#1a3a5c", self._increment_qty))
        al.addWidget(aBtn("➖  Qty", "#607d8b", "#455a64", self._decrement_qty))
        al.addStretch()

        disc_lbl = QLabel("Global Disc%:")
        disc_lbl.setStyleSheet("font-size:12px;color:#445566;")
        al.addWidget(disc_lbl)
        self._global_disc = QDoubleSpinBox()
        self._global_disc.setRange(0, 100)
        self._global_disc.setDecimals(1)
        self._global_disc.setFixedHeight(30)
        self._global_disc.setFixedWidth(70)
        self._global_disc.setStyleSheet("font-size:12px;color:#1a1a2e;")
        self._global_disc.valueChanged.connect(self._update_totals)
        al.addWidget(self._global_disc)

        lay.addWidget(act)
        return w

    # ── Right panel ────────────────────────────────────────────────────────────

    def _make_right_panel(self):
        from PySide6.QtWidgets import QScrollArea
        outer = QWidget()
        outer.setStyleSheet("background:#f0f4f8;")
        outer_lay = QVBoxLayout(outer)
        outer_lay.setContentsMargins(0, 0, 0, 0)
        outer_lay.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setStyleSheet(
            "QScrollArea{border:none;background:#f0f4f8;}"
            "QScrollBar:vertical{width:6px;background:#e0e8f0;border-radius:3px;}"
            "QScrollBar::handle:vertical{background:#9ab;border-radius:3px;}"
        )
        outer_lay.addWidget(scroll)

        w = QWidget()
        w.setStyleSheet("background:#f0f4f8;")
        scroll.setWidget(w)

        lay = QVBoxLayout(w)
        lay.setContentsMargins(10, 10, 10, 10)
        lay.setSpacing(8)

        # ── Totals card ───────────────────────────────────────────────────
        totals = QFrame()
        totals.setStyleSheet("background:#1a1a2e;border-radius:8px;")
        tl = QVBoxLayout(totals)
        tl.setContentsMargins(16, 14, 16, 14)
        tl.setSpacing(6)

        def tot_row(label, color="#a8c8e8", size=13, bold=False):
            row = QHBoxLayout()
            lbl = QLabel(label)
            lbl.setStyleSheet("color:#a8c8e8;font-size:12px;background:transparent;")
            val = QLabel("0")
            val.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            val.setStyleSheet(
                f"color:{color};font-size:{size}px;"
                f"font-weight:{'700' if bold else '400'};background:transparent;"
            )
            row.addWidget(lbl)
            row.addStretch()
            row.addWidget(val)
            tl.addLayout(row)
            return val

        self._sub_lbl   = tot_row("Sub-Total  ل.ل:")
        self._disc_lbl2 = tot_row("Discount   ل.ل:", color="#f0c040")

        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet("color:#334466;background:#334466;")
        sep.setFixedHeight(1)
        tl.addWidget(sep)

        grand_lbl = QLabel("GRAND TOTAL  (ل.ل)")
        grand_lbl.setStyleSheet(
            "color:#a8c8e8;font-size:11px;font-weight:700;"
            "letter-spacing:1px;background:transparent;"
        )
        tl.addWidget(grand_lbl)

        self._grand_usd_lbl = QLabel("")
        self._grand_usd_lbl.setAlignment(Qt.AlignRight)
        self._grand_usd_lbl.setStyleSheet(
            "color:#78909c;font-size:24px;font-weight:400;background:transparent;"
        )
        tl.addWidget(self._grand_usd_lbl)

        self._grand_lbl = QLabel("0")
        self._grand_lbl.setAlignment(Qt.AlignRight)
        self._grand_lbl.setStyleSheet(
            "color:#00e676;font-size:30px;font-weight:700;background:transparent;"
        )
        tl.addWidget(self._grand_lbl)

        lay.addWidget(totals)

        # ── PAY button ────────────────────────────────────────────────────
        self._pay_btn = QPushButton("💳   PAY  [F8]")
        self._pay_btn.setFixedHeight(70)
        self._pay_btn.setStyleSheet(
            "QPushButton{background:#2e7d32;color:#fff;font-size:24px;font-weight:700;"
            "border:none;border-radius:8px;letter-spacing:2px;}"
            "QPushButton:hover{background:#1b5e20;}"
            "QPushButton:pressed{background:#0a3d12;}"
        )
        self._pay_btn.setCursor(Qt.PointingHandCursor)
        self._pay_btn.clicked.connect(self._do_pay)
        lay.addWidget(self._pay_btn)

        # ── Function buttons ──────────────────────────────────────────────
        fn_frame = QFrame()
        fn_frame.setStyleSheet(
            "QFrame{background:#fff;border:1px solid #d0d8e4;border-radius:6px;}"
        )
        fn_lay = QGridLayout(fn_frame)
        fn_lay.setContentsMargins(8, 8, 8, 8)
        fn_lay.setSpacing(6)

        def fn_btn(label, bg, hover, callback, row, col):
            b = QPushButton(label)
            b.setFixedHeight(38)
            b.setStyleSheet(
                f"QPushButton{{background:{bg};color:#fff;font-size:12px;font-weight:700;"
                f"border:none;border-radius:5px;}}"
                f"QPushButton:hover{{background:{hover};}}"
            )
            b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(callback)
            fn_lay.addWidget(b, row, col)
            return b

        fn_btn("⏸  Hold  [F2]",      "#e65100", "#bf360c", self._hold_sale,      0, 0)
        fn_btn("▶  Recall  [F3]",   "#1a6cb5", "#1a3a5c", self._recall_sale,    0, 1)
        fn_btn("📋  Invoices",       "#37474f", "#263238", self._open_invoices,  1, 0)
        fn_btn("🌐  Online Orders", "#1a6cb5", "#0d4a8a", self._open_online_orders, 1, 1)
        self._touch_mode_btn = fn_btn(
            "⊞  Touch Mode", "#00838f", "#006064", self._toggle_touch_mode, 2, 0)
        fn_btn("👤  Customer",     "#5c6bc0", "#3949ab", self._change_customer, 2, 1)
        fn_btn("🔍  Price  [F10]", "#455a64", "#263238", self._price_check,       3, 0)
        fn_btn("🖨  Print  [F9]",  "#2e7d32", "#1b5e20", self._print_last,        3, 1)
        fn_btn("📊  Daily Sales",  "#4a148c", "#311b92", self._open_daily_sales,  4, 0)
        fn_btn("🔴  End of Shift", "#b71c1c", "#7f0000", self._open_end_of_shift, 4, 1)

        # ── Touch panel (hidden until touch mode activated) ───────────────
        from ui.screens.pos.touch_panel import TouchPanel
        self._touch_panel = TouchPanel()
        self._touch_panel.item_selected.connect(self._on_touch_item)
        self._touch_panel.exit_requested.connect(self._exit_touch_mode)

        from PySide6.QtWidgets import QStackedWidget as _SW
        self._fn_stack = _SW()
        self._fn_stack.addWidget(fn_frame)        # index 0 — normal buttons
        self._fn_stack.addWidget(self._touch_panel)  # index 1 — touch mode

        lay.addWidget(self._fn_stack)

        # ── Held invoices panel ────────────────────────────────────────────
        held_frame = QFrame()
        held_frame.setStyleSheet(
            "QFrame{background:#fff;border:1px solid #d0d8e4;border-radius:6px;}"
            "QLabel{color:#1a1a2e;}"
        )
        hl2 = QVBoxLayout(held_frame)
        hl2.setContentsMargins(6, 4, 6, 4)
        hl2.setSpacing(3)

        held_hdr = QHBoxLayout()
        held_lbl = QLabel("⏸  Held Invoices")
        held_lbl.setStyleSheet("font-size:11px;font-weight:700;color:#e65100;letter-spacing:1px;")
        held_hdr.addWidget(held_lbl)
        held_hdr.addStretch()
        refresh_btn = QPushButton("↺")
        refresh_btn.setFixedSize(22, 22)
        refresh_btn.setStyleSheet(
            "QPushButton{background:#e8f0fb;color:#1a3a5c;border:1px solid #b0c8e8;"
            "border-radius:3px;font-weight:700;font-size:13px;}"
            "QPushButton:hover{background:#c0d8f0;}"
        )
        refresh_btn.clicked.connect(self._refresh_held_panel)
        held_hdr.addWidget(refresh_btn)
        hl2.addLayout(held_hdr)

        self._held_list = QListWidget()
        self._held_list.setStyleSheet(
            "QListWidget{font-size:12px;border:none;background:transparent;}"
            "QListWidget::item{padding:5px 4px;border-bottom:1px solid #e8eef4;}"
            "QListWidget::item:hover{background:#e8f0fb;}"
            "QListWidget::item:selected{background:#1a6cb5;color:#fff;}"
        )
        self._held_list.setMaximumHeight(130)
        self._held_list.itemClicked.connect(self._recall_from_panel)
        hl2.addWidget(self._held_list)

        lay.addWidget(held_frame)
        self._refresh_held_panel()

        # ── Online Orders panel ────────────────────────────────────────────────
        self._online_frame = QFrame()
        self._online_frame.setStyleSheet(
            "QFrame{background:#fff3f0;border:2px solid #e53935;border-radius:6px;}"
            "QLabel{color:#c62828;}"
        )
        self._online_frame.setVisible(False)
        ol = QVBoxLayout(self._online_frame)
        ol.setContentsMargins(6, 4, 6, 4)
        ol.setSpacing(3)

        online_hdr = QHBoxLayout()
        self._online_hdr_lbl = QLabel("🔴  Online Orders")
        self._online_hdr_lbl.setStyleSheet(
            "font-size:11px;font-weight:700;color:#c62828;letter-spacing:1px;"
        )
        online_hdr.addWidget(self._online_hdr_lbl)
        online_hdr.addStretch()
        ol.addLayout(online_hdr)

        self._online_list = QListWidget()
        self._online_list.setStyleSheet(
            "QListWidget{font-size:12px;border:none;background:transparent;}"
            "QListWidget::item{padding:6px 4px;border-bottom:1px solid #ffcdd2;color:#b71c1c;font-weight:600;}"
            "QListWidget::item:hover{background:#ffebee;}"
            "QListWidget::item:selected{background:#e53935;color:#fff;}"
        )
        self._online_list.setMaximumHeight(140)
        self._online_list.itemClicked.connect(self._load_online_order_from_panel)
        ol.addWidget(self._online_list)

        lay.addWidget(self._online_frame)

        # Flash timer for online orders alert
        self._flash_on = True
        self._flash_timer = QTimer(self)
        self._flash_timer.timeout.connect(self._flash_online_panel)
        # Poll timer — check for new online orders every 10 seconds
        self._online_poll_timer = QTimer(self)
        self._online_poll_timer.timeout.connect(self._poll_online_orders)
        self._online_poll_timer.start(10_000)

        hints = QLabel(
            "F8=Pay · F9=Print · F10=Price · F2=Hold · F3=Recall · F4=New · +=Qty+ · −=Qty− · Del=Void"
        )
        hints.setStyleSheet("font-size:10px;color:#8899aa;")
        hints.setAlignment(Qt.AlignCenter)
        lay.addWidget(hints)

        return outer

    # ── Status bar ─────────────────────────────────────────────────────────────

    def _make_status_bar(self):
        bar = QFrame()
        bar.setFixedHeight(24)
        bar.setStyleSheet("background:#1a3a5c;")
        bl = QHBoxLayout(bar)
        bl.setContentsMargins(12, 0, 12, 0)
        bl.setSpacing(30)

        self._items_count_lbl = QLabel("Lines: 0")
        self._items_count_lbl.setStyleSheet("color:#fff;font-size:12px;font-weight:700;")
        bl.addWidget(self._items_count_lbl)

        user = AuthService.current_user()
        cashier = QLabel(f"Cashier: {user.full_name if user else '—'}")
        cashier.setStyleSheet("color:#a8c8e8;font-size:11px;")
        bl.addWidget(cashier)

        bl.addStretch()

        self._clock_lbl = QLabel("")
        self._clock_lbl.setStyleSheet("color:#a8c8e8;font-size:11px;")
        bl.addWidget(self._clock_lbl)

        self._clock_timer = QTimer()
        self._clock_timer.timeout.connect(self._update_clock)
        self._clock_timer.start(10000)
        self._update_clock()

        return bar

    # ── Defaults ───────────────────────────────────────────────────────────────

    def _load_defaults(self):
        wh_name = ""
        if self._forced_warehouse_id:
            self._warehouse_id = self._forced_warehouse_id
            # Resolve warehouse name
            wh_list = ItemService.get_warehouses()
            for wh_id, name, _is_def, _num, _cust in wh_list:
                if wh_id == self._forced_warehouse_id:
                    wh_name = name
                    break
        else:
            wh = ItemService.get_warehouses()
            self._warehouse_id = wh[0][0] if wh else ""
            for wh_id, name, is_default, _wh_num, _def_cust in wh:
                if is_default:
                    self._warehouse_id = wh_id
                    wh_name = name
                    break
            if not wh_name and wh:
                wh_name = wh[0][1]

        # Update POS title with branch name
        if wh_name:
            self._pos_title_lbl.setText(f"🖥️  POS — {wh_name}  (ل.ل  LBP)")

        # Resolve default customer and show their name
        self._customer_id = PosService.get_walk_in_customer_id(self._warehouse_id)
        self._customer_name = self._resolve_customer_name(self._customer_id)
        self._cust_name_lbl.setText(self._customer_name)
        self._scan_input.setFocus()

    def _resolve_customer_name(self, customer_id: str) -> str:
        if not customer_id:
            return "Walk-In"
        from database.engine import get_session
        from database.models.parties import Customer
        session = get_session()
        try:
            c = session.get(Customer, customer_id)
            return c.name if c else "Walk-In"
        finally:
            session.close()

    def _setup_shortcuts(self):
        QShortcut(QKeySequence("F8"),  self).activated.connect(self._do_pay)
        QShortcut(QKeySequence("F9"),  self).activated.connect(self._print_last)
        QShortcut(QKeySequence("F10"), self).activated.connect(self._price_check)
        QShortcut(QKeySequence("F2"),  self).activated.connect(self._hold_sale)
        QShortcut(QKeySequence("F3"),  self).activated.connect(self._recall_sale)
        QShortcut(QKeySequence("F4"),  self).activated.connect(self._new_sale)
        QShortcut(QKeySequence("Del"), self).activated.connect(self._void_line)
        QShortcut(QKeySequence("Escape"), self).activated.connect(
            lambda: self._scan_input.setFocus()
        )

    # ── Barcode scan ───────────────────────────────────────────────────────────

    def _on_barcode_entered(self):
        query = self._scan_input.text().strip()
        if not query:
            return

        # "5000V" or "2.5*3000V" — inline vege, no dialog
        if len(query) > 1 and query[-1].upper() == "V":
            expr = query[:-1].strip()
            vqty, vprice, vtotal = None, None, None
            try:
                if "*" in expr:
                    a, b = expr.split("*", 1)
                    vqty  = float(a.strip())
                    vprice = float(b.strip())
                    vtotal = vqty * vprice
                else:
                    vprice = float(expr.replace(",", ""))
                    vqty, vtotal = 1.0, vprice
            except ValueError:
                pass
            if vtotal and vtotal > 0:
                self._scan_input.clear()
                self._add_vege_line(vqty, vprice, vtotal)
                return

        # "V" or "v" — vegetable/bulk price entry (dialog)
        if query.upper() == "V":
            self._scan_input.clear()
            self._open_vege_dialog()
            return

        # "A" or "a" — item without barcode: look up by barcode "A", ask for price
        if query.upper() == "A":
            self._scan_input.clear()
            self._open_manual_price_dialog()
            return

        # "-code" prefix — deduct (negative qty) from invoice
        negative_qty = False
        if query.startswith("-") and len(query) > 1:
            negative_qty = True
            query = query[1:].strip()

        # "3*something" — multiplier prefix sets quantity
        prefix_qty = None
        if "*" in query:
            parts = query.split("*", 1)
            try:
                prefix_qty = float(parts[0])
            except ValueError:
                pass
            query = parts[1].strip()

        # "/" prefix forces name search → open picker
        if query.startswith("/"):
            self._scan_input.setText(query[1:])
            self._open_item_picker()
            return

        # ── Scale barcode: try to decode before normal lookup ─────────────────
        from utils.scale_barcode import decode_scale_barcode
        scale_result = decode_scale_barcode(query)
        if scale_result is not None:
            scale_item = PosService.lookup_item(
                scale_result.item_code, "barcode", currency="LBP", price_type=POS_PRICE_TYPE
            )
            if scale_item is not None:
                # Resolve unit price in LBP
                lbp_unit = (scale_item.unit_price if scale_item.currency == "LBP"
                            else round(scale_item.unit_price * LBP_RATE))

                if scale_result.price is not None:
                    # Price-embedded barcode: barcode total IS the price, qty=1
                    qty   = 1.0
                    price = scale_result.price   # total from barcode (e.g. 598,500 LBP)
                    total = scale_result.price
                else:
                    # Weight-embedded barcode: qty=weight, price from DB, total=qty×price
                    qty   = scale_result.weight or 1.0
                    price = lbp_unit
                    total = round(lbp_unit * qty)

                sign = -1 if negative_qty else 1
                self._lines.append({
                    "item": PosLineItem(
                        item_id    = scale_item.item_id,
                        code       = scale_item.code,
                        barcode    = scale_item.barcode,
                        description= scale_item.description,
                        qty        = sign * qty,
                        unit_price = price,
                        disc_pct   = 0.0,
                        vat_pct    = scale_item.vat_pct,
                        total      = sign * total,
                        currency   = "LBP",
                        price_type = scale_item.price_type,
                        stock_qty  = scale_item.stock_qty,
                    ),
                    "qty":   sign * qty,
                    "price": price,
                    "disc":  0.0,
                    "total": sign * total,
                })
                self._refresh_table()
                self._table.selectRow(len(self._lines) - 1)
                self._scan_input.clear()
                return

        # Cascade: barcode → code only (name search requires Ctrl+Enter or "/" prefix)
        item = (
            PosService.lookup_item(query, "barcode", currency="USD", price_type=POS_PRICE_TYPE)
            or PosService.lookup_item(query, "code",    currency="USD", price_type=POS_PRICE_TYPE)
        )
        if item:
            if negative_qty:
                self._add_item(item, force_qty=-(prefix_qty or item.qty))
            elif prefix_qty is not None:
                self._add_item(item, force_qty=prefix_qty)
            else:
                self._add_item(item)
        else:
            # Nothing found → beep + blocking message so cashier must acknowledge
            self._beep_not_found()
            QMessageBox.warning(self, "Item Not Found",
                                f"No item found for:\n\n{query}\n\nPlease check the barcode and try again.")
            self._scan_input.clear()
            self._scan_input.setFocus()

    def _open_item_picker(self):
        """Ctrl+Enter: browse all items and select one."""
        try:
            from services.purchase_service import PurchaseService
            raw = self._scan_input.text().strip()

            # Parse optional "N*name" prefix (e.g. "2*bread" → qty=2, search="bread")
            prefix_qty = None
            query = raw
            if "*" in raw:
                parts = raw.split("*", 1)
                try:
                    prefix_qty = float(parts[0])
                    query = parts[1].strip()
                except ValueError:
                    pass  # not a qty prefix — treat as literal search

            try:
                rows = PurchaseService.search_items_by_sales(query, limit=200)
            except Exception:
                rows = []
            if not rows:
                rows = PurchaseService.search_items_by_usage(query, limit=200)
            if not rows:
                QMessageBox.information(self, "No Items", "No items found in database.")
                return
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Item picker failed:\n{e}")
            return

        dlg = QDialog(self)
        dlg.setWindowTitle("Item Search  —  ↑↓ browse · Enter select")
        dlg.setMinimumSize(820, 480)
        lay = QVBoxLayout(dlg)
        lay.setContentsMargins(10, 10, 10, 10)
        lay.setSpacing(8)

        # Filter bar
        top = QHBoxLayout()
        search_box = QLineEdit(query)
        search_box.setPlaceholderText("Type to filter…")
        search_box.setFixedHeight(34)
        search_box.setStyleSheet("font-size:13px;")
        top.addWidget(search_box)
        lay.addLayout(top)

        tbl = QTableWidget()
        tbl.setColumnCount(4)
        tbl.setHorizontalHeaderLabels(["Code", "Description", "Price (ل.ل)", "Stock"])
        tbl.setEditTriggers(QAbstractItemView.NoEditTriggers)
        tbl.setSelectionBehavior(QAbstractItemView.SelectRows)
        tbl.setSelectionMode(QAbstractItemView.SingleSelection)
        tbl.verticalHeader().setVisible(False)
        tbl.verticalHeader().setDefaultSectionSize(32)
        th = tbl.horizontalHeader()
        th.setSectionResizeMode(1, QHeaderView.Stretch)
        for c, w_ in ((0, 80), (2, 110), (3, 70)):
            th.setSectionResizeMode(c, QHeaderView.Fixed)
            tbl.setColumnWidth(c, w_)
        th.setStyleSheet(
            "QHeaderView::section{background:#1a3a5c;color:#fff;font-weight:700;"
            "border:none;padding:4px;}"
        )
        lay.addWidget(tbl, 1)

        def _fill(filter_text=""):
            filtered = [r for r in rows
                        if not filter_text
                        or filter_text.lower() in r["name"].lower()
                        or filter_text.lower() in r["code"].lower()]
            tbl.setRowCount(len(filtered))
            for i, r in enumerate(filtered):
                sp = sell_prices.get(r["item_id"])
                if sp:
                    lbp_price = sp["amount"] * LBP_RATE if sp["currency"] == "USD" else sp["amount"]
                else:
                    lbp_price = r["cost"] * LBP_RATE
                for c, txt, align in [
                    (0, r["code"],              Qt.AlignCenter),
                    (1, r["name"],              Qt.AlignLeft | Qt.AlignVCenter),
                    (2, f"{lbp_price:,.0f}",   Qt.AlignRight | Qt.AlignVCenter),
                    (3, str(int(r.get("usage", 0))), Qt.AlignCenter),
                ]:
                    it = QTableWidgetItem(txt)
                    it.setTextAlignment(align)
                    it.setData(Qt.UserRole, r)
                    tbl.setItem(i, c, it)
            if tbl.rowCount():
                tbl.selectRow(0)

        # Batch-fetch retail selling prices for all returned items
        from database.engine import get_session, init_db
        from database.models.items import ItemPrice
        init_db()
        _sess = get_session()
        try:
            item_ids = [r["item_id"] for r in rows]
            _prices = _sess.query(ItemPrice).filter(
                ItemPrice.item_id.in_(item_ids),
                ItemPrice.price_type == POS_PRICE_TYPE,
            ).all()
            sell_prices = {p.item_id: {"amount": p.amount, "currency": p.currency}
                           for p in _prices}
        finally:
            _sess.close()

        search_box.textChanged.connect(_fill)
        _fill(query)

        chosen = [None]

        def _pick():
            row_idx = tbl.currentRow()
            if row_idx >= 0:
                it = tbl.item(row_idx, 0)
                if it:
                    chosen[0] = it.data(Qt.UserRole)
                    dlg.accept()

        tbl.doubleClicked.connect(_pick)

        # Forward Up/Down/Enter from search box to the table
        def _search_key(event):
            key = event.key()
            if key in (Qt.Key_Down, Qt.Key_Up):
                cur = tbl.currentRow()
                if key == Qt.Key_Down:
                    tbl.selectRow(min(cur + 1, tbl.rowCount() - 1))
                else:
                    tbl.selectRow(max(cur - 1, 0))
            elif key in (Qt.Key_Return, Qt.Key_Enter):
                _pick()
            else:
                QLineEdit.keyPressEvent(search_box, event)

        search_box.keyPressEvent = _search_key
        search_box.setFocus()

        btn_row = QHBoxLayout()
        sel_btn = QPushButton("✓  Select")
        sel_btn.setFixedHeight(34)
        sel_btn.setStyleSheet(
            "QPushButton{background:#2e7d32;color:#fff;font-weight:700;"
            "border:none;border-radius:4px;padding:0 16px;}"
        )
        sel_btn.clicked.connect(_pick)
        btn_row.addStretch()
        btn_row.addWidget(sel_btn)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.setFixedHeight(34)
        cancel_btn.setStyleSheet(
            "QPushButton{background:#607d8b;color:#fff;font-weight:700;"
            "border:none;border-radius:4px;padding:0 16px;}"
        )
        cancel_btn.clicked.connect(dlg.reject)
        btn_row.addWidget(cancel_btn)
        lay.addLayout(btn_row)

        if not dlg.exec() or not chosen[0]:
            return

        r = chosen[0]
        # Use the price already fetched in this dialog — avoids picking a
        # different duplicate row via a second lookup_item call.
        sp = sell_prices.get(r["item_id"])
        if sp:
            lbp_price = sp["amount"] * LBP_RATE if sp["currency"] == "USD" else sp["amount"]
        else:
            lbp_price = r["cost"] * LBP_RATE

        # Build a lightweight PosLineItem directly from what we already have
        item = PosLineItem(
            item_id    = r["item_id"],
            code       = r["code"],
            barcode    = r["barcode"],
            description= r["name"],
            qty        = 1.0,
            unit_price = lbp_price,
            disc_pct   = 0.0,
            vat_pct    = 0.0,
            total      = lbp_price,
            currency   = "LBP",
        )
        if prefix_qty is not None:
            self._add_item(item, force_qty=prefix_qty)
        else:
            self._add_item(item)
        self._scan_input.clear()

    def _get_vege_id(self) -> str:
        if not self._vege_id:
            self._vege_id = PosService.get_or_create_vege_item()
        return self._vege_id

    def _add_vege_line(self, qty: float, price: float, total: float):
        item = PosLineItem(
            item_id    = self._get_vege_id(),
            code       = "VEGE",
            barcode    = "V",
            description= "Vegetables",
            qty        = qty,
            unit_price = price,
            disc_pct   = 0.0,
            vat_pct    = 0.0,
            total      = total,
            currency   = "LBP",
            price_type = "retail",
            stock_qty  = 0.0,
        )
        self._lines.append({"item": item, "qty": qty, "price": price, "disc": 0.0, "total": total})
        self._append_row(self._lines[-1])
        self._table.selectRow(len(self._lines) - 1)
        self._pole_show_item("Vegetables", qty, price)
        QTimer.singleShot(0, self._scan_input.setFocus)

    def _open_vege_dialog(self):
        """Open vegetable/bulk price-entry dialog and add line to cart."""
        dlg = VegeDialog(self)
        if not dlg.exec():
            self._scan_input.setFocus()
            return
        self._add_vege_line(dlg.result_qty, dlg.result_price, dlg.result_total)

    def _open_manual_price_dialog(self):
        """Barcode A — item without barcode. Look it up, then ask for price."""
        item_data = PosService.lookup_item("A", "barcode", currency="LBP", price_type=POS_PRICE_TYPE)
        if item_data is None:
            self._flash_scan("Item 'A' not found", "#c62828")
            self._scan_input.setFocus()
            return
        dlg = VegeDialog(self)
        dlg.setWindowTitle(item_data.description)
        if not dlg.exec():
            self._scan_input.setFocus()
            return
        item = PosLineItem(
            item_id    = item_data.item_id,
            code       = item_data.code,
            barcode    = "A",
            description= item_data.description,
            qty        = dlg.result_qty,
            unit_price = dlg.result_price,
            disc_pct   = 0.0,
            vat_pct    = 0.0,
            total      = dlg.result_total,
            currency   = "LBP",
            price_type = POS_PRICE_TYPE,
            stock_qty  = item_data.stock_qty,
        )
        self._lines.append({
            "item":  item,
            "qty":   dlg.result_qty,
            "price": dlg.result_price,
            "disc":  0.0,
            "total": dlg.result_total,
        })
        self._append_row(self._lines[-1])
        self._table.selectRow(len(self._lines) - 1)
        self._pole_show_item(item_data.description, dlg.result_qty, dlg.result_price)
        QTimer.singleShot(0, self._scan_input.setFocus)

    def _open_free_amount_dialog(self):
        """Open free amount entry dialog and add a custom line to the cart."""
        dlg = FreeAmountDialog(self)
        if not dlg.exec():
            self._scan_input.setFocus()
            return
        free_id = PosService.get_or_create_free_item()
        item = PosLineItem(
            item_id    = free_id,
            code       = "FREE",
            barcode    = "",
            description= dlg.result_desc,
            qty        = dlg.result_qty,
            unit_price = dlg.result_price,
            disc_pct   = 0.0,
            vat_pct    = 0.0,
            total      = dlg.result_total,
            currency   = "LBP",
            price_type = "retail",
            stock_qty  = 0.0,
        )
        self._lines.append({
            "item":  item,
            "qty":   dlg.result_qty,
            "price": dlg.result_price,
            "disc":  0.0,
            "total": dlg.result_total,
        })
        self._append_row(self._lines[-1])
        self._table.selectRow(len(self._lines) - 1)
        QTimer.singleShot(0, self._scan_input.setFocus)

    def _add_item(self, item, force_qty=None):
        """Convert item price USD→LBP if needed, then add to cart.
        Items built directly with currency='LBP' skip conversion.
        force_qty overrides the qty spinner (used for negative/deduct lines)."""
        if item.currency != "LBP":
            item.unit_price = round(item.unit_price * LBP_RATE)
            item.currency   = "LBP"

        # force_qty → explicit override (negatives/deductions)
        # spinner != 1 → user-set quantity (overrides pack_qty)
        # otherwise → use item.qty which includes pack_qty from barcode
        if force_qty is not None:
            qty = force_qty
        else:
            qty = item.qty  # respects pack_qty from barcode

        # Increment existing line if same item
        existing = next(
            (i for i, l in enumerate(self._lines) if l["item"].item_id == item.item_id), None
        )
        if existing is not None:
            self._lines[existing]["qty"] += qty
            self._recalc_line(existing)
            self._refresh_table()
            self._scan_input.clear()
            self._pole_show_item(item.description, self._lines[existing]["qty"], item.unit_price)
            return

        price = item.unit_price
        total = price * qty
        self._lines.append({
            "item":  item,
            "qty":   qty,
            "price": price,
            "disc":  0.0,
            "total": total,
        })
        self._append_row(self._lines[-1])
        self._scan_input.clear()
        self._table.selectRow(len(self._lines) - 1)
        self._update_box_bar(len(self._lines) - 1)
        self._pole_show_item(item.description, qty, price)
        QTimer.singleShot(0, self._scan_input.setFocus)

    def _update_box_bar(self, row: int = -1):
        """Show/update the box info bar for the given cart row."""
        if row < 0 or row >= len(self._lines):
            self._box_bar.setVisible(False)
            self._last_pack_qty = 1
            return
        line = self._lines[row]
        item = line["item"]
        pack_qty = int(getattr(item, "qty", 1) or 1)
        # Only show bar for box items
        if pack_qty <= 1:
            self._box_bar.setVisible(False)
            self._last_pack_qty = 1
            return
        self._last_pack_qty = pack_qty
        boxes = int(line["qty"] / pack_qty) if pack_qty else 1
        pcs   = int(line["qty"])
        price = line["price"] * pack_qty   # box price
        self._box_item_lbl.setText(item.description[:30])
        self._box_qty_lbl.setText(str(boxes))
        self._box_pcs_lbl.setText(f"pcs ({pcs:g})")
        self._box_price_lbl.setText(f"{price:,.0f}")
        self._box_bar.setVisible(True)

    def _pole_show_welcome(self):
        try:
            from utils.pole_display import pole_show
            from database.engine import get_session, init_db
            from database.models.items import Setting
            init_db()
            _s = get_session()
            try:
                _sn = _s.get(Setting, "shop_name")
                name = (_sn.value if _sn else "Welcome!")[:20]
            finally:
                _s.close()
            pole_show(name, "")
        except Exception:
            pass

    def _pole_show_item(self, description: str, qty: float, unit_price: float):
        try:
            from utils.pole_display import pole_show
            line1 = description[:20]
            line2 = f"{qty:g} x {unit_price:,.0f}"[:20]
            pole_show(line1, line2)
        except Exception:
            pass

    def _flash_scan(self, text, color):
        self._scan_input.setText(text)
        self._scan_input.setStyleSheet(
            f"font-size:14px;font-weight:700;border:2px solid {color};"
            f"border-radius:4px;padding:0 8px;background:#fff3f3;color:{color};"
        )
        QTimer.singleShot(900, self._reset_scan_style)

    def _reset_scan_style(self):
        self._scan_input.clear()
        self._scan_input.setStyleSheet(
            "font-size:14px;font-weight:600;border:2px solid #1a6cb5;"
            "border-radius:4px;padding:0 8px;background:#fff;color:#1a1a2e;"
        )

    # ── Table ──────────────────────────────────────────────────────────────────

    def _build_row_text(self, r: int, line: dict):
        """Write only the text cells for row r — fast, no widget allocation."""
        it = line["item"]
        is_void = line.get("voided", False)
        void_color = QColor("#ffcccc") if is_void else None

        def ro(text, align=Qt.AlignCenter, _vc=void_color):
            cell = QTableWidgetItem(str(text))
            cell.setTextAlignment(align)
            cell.setFlags(cell.flags() & ~Qt.ItemIsEditable)
            if _vc:
                cell.setBackground(_vc)
                cell.setForeground(QColor("#a01010"))
            return cell

        def ed(text, align=Qt.AlignCenter, _vc=void_color):
            cell = QTableWidgetItem(str(text))
            cell.setTextAlignment(align)
            if _vc:
                cell.setBackground(_vc)
                cell.setForeground(QColor("#a01010"))
                cell.setFlags(cell.flags() & ~Qt.ItemIsEditable)
            return cell

        self._table.setItem(r, COL_NUM,   ro(str(r + 1)))
        self._table.setItem(r, COL_CODE,  ro(it.barcode or it.code, Qt.AlignLeft | Qt.AlignVCenter))
        self._table.setItem(r, COL_DESC,  ro(it.description, Qt.AlignLeft | Qt.AlignVCenter))
        qty_cell = ro(f"{line['qty']:.3f}") if line["qty"] < 0 else ed(f"{line['qty']:.3f}")
        self._table.setItem(r, COL_QTY, qty_cell)
        self._table.setItem(r, COL_PRICE, ed(f"{line['price']:.0f}"))
        self._table.setItem(r, COL_DISC,  ed(f"{line['disc']:.1f}"))

        tot_cell = ro(f"{line['total']:,.0f}")
        tot_cell.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
        tot_cell.setFont(QFont("", -1, QFont.Bold))
        self._table.setItem(r, COL_TOT, tot_cell)

    def _build_row_buttons(self, r: int):
        """Create the void/delete cell widget for row r."""
        if r >= self._table.rowCount():
            return
        btn_widget = QWidget()
        btn_layout = QHBoxLayout(btn_widget)
        btn_layout.setContentsMargins(3, 2, 3, 2)
        btn_layout.setSpacing(4)

        void_btn = QPushButton("⊘")
        void_btn.setFixedSize(28, 30)
        void_btn.setToolTip("Void — adds a negative entry")
        void_btn.setStyleSheet(
            "QPushButton{background:#e65100;color:#fff;border:none;"
            "border-radius:4px;font-weight:700;font-size:14px;}"
            "QPushButton:hover{background:#bf360c;}"
        )
        void_btn.clicked.connect(lambda _, row=r: self._void_or_delete(row, force_delete=False))

        x_btn = QPushButton("✕")
        x_btn.setFixedSize(28, 30)
        x_btn.setToolTip("Delete line (manager only)")
        x_btn.setStyleSheet(
            "QPushButton{background:#c62828;color:#fff;border:none;"
            "border-radius:4px;font-weight:700;font-size:12px;}"
            "QPushButton:hover{background:#a01010;}"
        )
        x_btn.clicked.connect(lambda _, row=r: self._void_or_delete(row, force_delete=True))

        btn_layout.addWidget(void_btn)
        btn_layout.addWidget(x_btn)
        self._table.setCellWidget(r, COL_DEL, btn_widget)

    def _build_row(self, r: int, line: dict):
        self._build_row_text(r, line)
        self._build_row_buttons(r)

    def _append_row(self, line: dict):
        """Insert only the new last row without blocking the UI.

        Text cells are written synchronously so the cashier sees the item
        immediately. The void/delete buttons are deferred to the next event
        loop tick so setCellWidget never blocks keystroke processing.
        """
        r = len(self._lines) - 1
        self._table_updating = True
        self._table.setUpdatesEnabled(False)
        self._table.insertRow(r)
        self._build_row_text(r, line)
        self._table.setUpdatesEnabled(True)
        self._table_updating = False
        self._update_totals()
        self._items_count_lbl.setText(f"Lines: {len(self._lines)}")
        self._table.scrollToBottom()
        QTimer.singleShot(0, lambda _r=r: self._build_row_buttons(_r))

    def _refresh_table(self):
        self._table_updating = True
        self._table.setUpdatesEnabled(False)
        self._table.setRowCount(0)
        self._table.setRowCount(len(self._lines))
        for r, line in enumerate(self._lines):
            self._build_row(r, line)
        self._table.setUpdatesEnabled(True)
        self._table_updating = False
        self._update_totals()
        self._items_count_lbl.setText(f"Lines: {len(self._lines)}")
        if self._lines:
            self._table.scrollToBottom()

    def _on_cell_edited(self, item):
        if self._table_updating:
            return
        row = item.row()
        col = item.column()
        if row >= len(self._lines):
            return
        try:
            val = float(item.text())
        except ValueError:
            return

        if col == COL_QTY:
            if val == 0:
                return   # disallow zero
            self._lines[row]["qty"] = val   # allow negatives (deduction lines)
        elif col == COL_PRICE:
            self._lines[row]["price"] = max(0.0, val)
        elif col == COL_DISC:
            self._lines[row]["disc"] = max(0.0, min(100.0, val))

        self._recalc_line(row)
        self._table_updating = True
        tot_cell = self._table.item(row, COL_TOT)
        if tot_cell:
            tot_cell.setText(f"{self._lines[row]['total']:,.0f}")
        self._table_updating = False
        self._update_totals()
        self._update_box_bar(row)

    def _recalc_line(self, row: int):
        line = self._lines[row]
        line["total"] = line["qty"] * line["price"] * (1 - line["disc"] / 100)

    # ── Totals ─────────────────────────────────────────────────────────────────

    def _update_totals(self):
        subtotal = sum(l["qty"] * l["price"] * (1 - l["disc"] / 100) for l in self._lines)
        disc_val = subtotal * (self._global_disc.value() / 100)
        grand    = subtotal - disc_val
        self._sub_lbl.setText(f"{subtotal:,.0f}")
        self._disc_lbl2.setText(f"{disc_val:,.0f}")
        self._grand_lbl.setText(f"{grand:,.0f}")
        usd = grand / LBP_RATE if grand else 0.0
        self._grand_usd_lbl.setText(f"≈ $ {usd:,.2f}" if grand else "")

    def _grand_total(self) -> float:
        subtotal = sum(l["qty"] * l["price"] * (1 - l["disc"] / 100) for l in self._lines)
        disc_val = subtotal * (self._global_disc.value() / 100)
        return subtotal - disc_val

    # ── Pay ────────────────────────────────────────────────────────────────────

    def _do_pay(self):
        if not self._lines:
            QMessageBox.warning(self, "Empty", "No items in the sale.")
            return
        total = self._grand_total()
        try:
            from utils.pole_display import pole_show
            pole_show("Total:", f"{total:,.0f}"[:20])
        except Exception:
            pass
        dlg = PaymentDialog(total, self)
        if not dlg.exec():
            return
        self._finish_sale(dlg)

    def _quick_pay(self, amount: float):
        if not self._lines:
            return
        dlg = PaymentDialog(self._grand_total(), self)
        dlg._set_tender(amount)
        if dlg.exec():
            self._finish_sale(dlg)

    def _finish_sale(self, dlg: PaymentDialog):
        user = AuthService.current_user()
        total    = self._grand_total()
        disc_val = (
            sum(l["qty"] * l["price"] for l in self._lines)
            * (self._global_disc.value() / 100)
        )
        lines = [
            PosLineItem(
                item_id    = l["item"].item_id,
                code       = l["item"].code,
                barcode    = l["item"].barcode,
                description= l["item"].description,
                qty        = l["qty"],
                unit_price = l["price"],
                disc_pct   = l["disc"],
                vat_pct    = l["item"].vat_pct,
                total      = l["total"],
                currency   = self._currency,
            )
            for l in self._lines
        ]
        ok, result = PosService.save_sale(
            customer_id    = self._customer_id,
            operator_id    = user.id if user else "",
            warehouse_id   = self._warehouse_id,
            lines          = lines,
            currency       = self._currency,
            payment_method = dlg.method,
            amount_paid    = dlg.tendered,
            discount_value = disc_val,
        )
        if ok:
            self._last_invoice_id     = result
            self._last_payment_method = dlg.method
            self._last_tendered       = dlg.tendered
            change = max(0.0, dlg.tendered - total) if dlg.method == "cash" else 0.0
            change_txt = f"  Change ل.ل {change:,.0f}" if change > 0 else ""
            self._last_inv_amt_lbl.setText(f"ل.ل {total:,.0f}{change_txt}")
            self._active_online_order_id = ""
            if self._print_copies == 1:   # ON only — ×2 is manual via F9
                self._print_receipt(result, dlg.method, dlg.tendered)
            self._new_sale()
        else:
            QMessageBox.critical(self, "Error", f"Failed to save sale:\n{result}")

    # ── Hold / Recall ──────────────────────────────────────────────────────────

    def _hold_sale(self):
        if not self._lines:
            return
        user = AuthService.current_user()
        lines_data = [
            {
                "item_id":     l["item"].item_id,
                "code":        l["item"].code,
                "description": l["item"].description,
                "barcode":     l["item"].barcode,
                "qty":         l["qty"],
                "unit_price":  l["price"],
                "disc_pct":    l["disc"],
                "vat_pct":     l["item"].vat_pct,
                "total":       l["total"],
                "currency":    self._currency,
            }
            for l in self._lines
        ]
        ok, _ = PosService.hold_sale(
            operator_id  = user.id if user else "",
            customer_name= self._customer_name,
            lines_json   = json.dumps(lines_data),
            total        = self._grand_total(),
            currency     = self._currency,
            label        = self._customer_name,
        )
        if ok:
            self._new_sale()
            self._refresh_held_panel()

    def _recall_sale(self):
        dlg = RecallDialog(self)
        if not dlg.exec() or not dlg.chosen_json:
            return
        try:
            lines_data = json.loads(dlg.chosen_json)
        except Exception:
            return

        self._lines.clear()
        for d in lines_data:
            it = PosLineItem(
                item_id    = d["item_id"],
                code       = d.get("code", ""),
                barcode    = d.get("barcode", ""),
                description= d["description"],
                qty        = d["qty"],
                unit_price = d["unit_price"],
                disc_pct   = d["disc_pct"],
                vat_pct    = d.get("vat_pct", 0.0),
                total      = d["total"],
                currency   = d.get("currency", self._currency),
            )
            self._lines.append({
                "item":  it,
                "qty":   d["qty"],
                "price": d["unit_price"],
                "disc":  d["disc_pct"],
                "total": d["total"],
            })
        self._refresh_table()

    # ── Online Orders ──────────────────────────────────────────────────────────

    def _open_online_orders(self):
        wh_id = getattr(self, "_warehouse_id", "")
        dlg = OnlineOrdersDialog(wh_id, parent=self)
        dlg.load_order.connect(self._load_online_order_from_dict)
        dlg.exec()

    def _load_online_order_from_dict(self, order: dict):
        """Load an online order from the Online Orders dialog into the POS cart."""
        self._load_online_order_to_cart(order)

    def _manually_finish_online_order(self, order_id: str):
        try:
            from sync.service import update_online_order_status
            update_online_order_status(order_id, "finished")
        except Exception:
            pass

    def _poll_online_orders(self):
        try:
            from sync.service import fetch_pending_online_orders, is_configured
            if not is_configured():
                return
            wh_id = getattr(self, "_warehouse_id", "")
            if not wh_id:
                return

            def _fetch(wh=wh_id):
                try:
                    orders = fetch_pending_online_orders(wh)
                    QTimer.singleShot(0, lambda o=orders: self._refresh_online_panel(o))
                except Exception:
                    pass

            threading.Thread(target=_fetch, daemon=True).start()
        except Exception:
            pass

    def _beep_not_found(self):
        """Short low-pitched error beep when a barcode is not found."""
        try:
            from PySide6.QtMultimedia import QSoundEffect
            from PySide6.QtCore import QUrl
            import wave, math
            from pathlib import Path

            wav_path = Path(__file__).parent.parent.parent / "assets" / "sounds" / "not_found.wav"
            wav_path.parent.mkdir(parents=True, exist_ok=True)
            if not wav_path.exists():
                sample_rate = 44100
                duration    = 0.25
                freq        = 320   # low tone = "error"
                n_samples   = int(sample_rate * duration)
                with wave.open(str(wav_path), "w") as wf:
                    wf.setnchannels(1)
                    wf.setsampwidth(2)
                    wf.setframerate(sample_rate)
                    for i in range(n_samples):
                        t   = i / sample_rate
                        env = min(t / 0.01, 1.0, (duration - t) / 0.02)
                        val = int(32767 * env * math.sin(2 * math.pi * freq * t))
                        wf.writeframes(val.to_bytes(2, "little", signed=True))

            self._not_found_sfx = QSoundEffect()
            self._not_found_sfx.setSource(QUrl.fromLocalFile(str(wav_path)))
            self._not_found_sfx.setVolume(0.9)
            self._not_found_sfx.play()
        except Exception:
            try:
                from PySide6.QtWidgets import QApplication
                QApplication.beep()
            except Exception:
                pass

    def _start_alert_sound(self):
        if self._alert_playing:
            return
        try:
            from PySide6.QtMultimedia import QSoundEffect
            from PySide6.QtCore import QUrl
            import struct, wave, math
            from pathlib import Path

            wav_path = Path(__file__).parent.parent.parent / "assets" / "sounds" / "alert.wav"
            wav_path.parent.mkdir(parents=True, exist_ok=True)
            if not wav_path.exists():
                # Generate a short two-tone alert beep (700 Hz, 0.35 s)
                sample_rate = 44100
                duration    = 0.35
                freq        = 700
                n_samples   = int(sample_rate * duration)
                with wave.open(str(wav_path), "w") as wf:
                    wf.setnchannels(1)
                    wf.setsampwidth(2)
                    wf.setframerate(sample_rate)
                    for i in range(n_samples):
                        t   = i / sample_rate
                        env = min(t / 0.02, 1.0, (duration - t) / 0.02)
                        val = int(32767 * env * math.sin(2 * math.pi * freq * t))
                        wf.writeframes(struct.pack("<h", val))

            if self._alert_sound is None:
                self._alert_sound = QSoundEffect(self)
                self._alert_sound.setSource(QUrl.fromLocalFile(str(wav_path)))
                self._alert_sound.setVolume(0.9)
                self._alert_sound.setLoopCount(1)

            self._alert_sound.play()
            self._alert_playing = True

            # Repeat beep every 10 seconds until alert is dismissed
            if self._alert_repeat_timer is None:
                from PySide6.QtCore import QTimer as _QTimer
                self._alert_repeat_timer = _QTimer(self)
                self._alert_repeat_timer.timeout.connect(
                    lambda: self._alert_sound.play() if self._alert_playing else None
                )
            self._alert_repeat_timer.start(10_000)
        except Exception:
            pass

    def _stop_alert_sound(self):
        if not self._alert_playing:
            return
        try:
            if self._alert_repeat_timer is not None:
                self._alert_repeat_timer.stop()
            if self._alert_sound is not None:
                self._alert_sound.stop()
        except Exception:
            pass
        self._alert_playing = False

    def _refresh_online_panel(self, orders: list):
        self._online_list.clear()
        if not orders:
            self._online_frame.setVisible(False)
            self._flash_timer.stop()
            self._stop_alert_sound()
            return
        self._online_frame.setVisible(True)
        self._flash_timer.start(600)
        self._start_alert_sound()
        # Auto-register customers from new orders
        try:
            from services.customer_service import CustomerService
            for o in orders:
                CustomerService.upsert_from_online_order(o)
        except Exception:
            pass
        for o in orders:
            name  = o.get("customer_name") or "Customer"
            total = o.get("total", 0)
            ts    = (o.get("created_at") or "")[:16].replace("T", " ")
            n_items = len(o.get("items") or [])
            it = QListWidgetItem(
                f"  🛒 {name}  —  ل.ل {total:,.0f}  ({n_items} items)  [{ts}]"
            )
            it.setData(Qt.UserRole, o)
            self._online_list.addItem(it)

    def _flash_online_panel(self):
        self._flash_on = not self._flash_on
        if self._flash_on:
            self._online_frame.setStyleSheet(
                "QFrame{background:#fff3f0;border:2px solid #e53935;border-radius:6px;}"
                "QLabel{color:#c62828;}"
            )
        else:
            self._online_frame.setStyleSheet(
                "QFrame{background:#e53935;border:2px solid #b71c1c;border-radius:6px;}"
                "QLabel{color:#fff;}"
            )

    def _load_online_order_from_panel(self, list_item):
        """Clicking a flashing order: acknowledge it (stop flash) and print a draft."""
        order = list_item.data(Qt.UserRole)
        if not order:
            return

        # Acknowledge in Supabase — stops flashing, status unchanged
        try:
            from sync.service import acknowledge_online_order
            acknowledge_online_order(order["id"])
        except Exception:
            pass

        # Print draft receipt so cashier has the order details
        self._print_online_order_draft(order)

        # Remove from flashing panel; order now lives in Online Orders dialog
        self._refresh_online_panel([])
        self._poll_online_orders()
        self._scan_input.setFocus()

    def _print_online_order_draft(self, order: dict):
        """Print the online order as a draft (no POS invoice created)."""
        from utils.receipt_printer import print_receipt
        from datetime import datetime as _dt

        raw_items = order.get("items") or []
        lines = []
        for d in raw_items:
            price = float(d.get("price") or d.get("unit_price", 0))
            qty   = float(d.get("qty", 1))
            lines.append({
                "description": d.get("name") or d.get("description", ""),
                "qty":         qty,
                "unit_price":  price,
                "disc_pct":    0.0,
                "total":       round(price * qty, 2),
            })

        shop_name = ""
        try:
            from database.engine import get_session, init_db
            from database.models.items import Setting
            init_db()
            _s = get_session()
            try:
                _r = _s.get(Setting, "shop_name")
                shop_name = _r.value if _r else ""
            finally:
                _s.close()
        except Exception:
            pass

        order_id  = (order.get("id") or "")[-8:].upper()
        ts        = (order.get("created_at") or "")[:16].replace("T", " ")
        dtype     = "Delivery" if order.get("delivery_type") == "delivery" else "Pickup"
        customer  = order.get("customer_name") or "—"
        phone     = order.get("customer_phone") or ""
        address   = order.get("address") or ""
        notes     = order.get("notes") or ""
        total     = float(order.get("total", 0))

        cust_line = customer
        if phone:   cust_line += f"  |  {phone}"
        if address: cust_line += f"\n{address}"

        footer_parts = ["** ONLINE ORDER DRAFT **", f"Type: {dtype}"]
        if notes:
            footer_parts.append(f"Notes: {notes}")

        data = {
            "shop_name":      shop_name,
            "invoice_number": f"ONL-{order_id}",
            "date":           ts,
            "cashier":        dtype,
            "customer":       cust_line,
            "lines":          lines,
            "subtotal":       total,
            "total":          total,
            "amount_paid":    0.0,
            "currency":       "LBP",
            "receipt_footer": "\n".join(footer_parts),
        }
        try:
            print_receipt(data, payment_method="cash", tendered=0.0,
                          parent=self, show_preview=False)
        except Exception:
            pass

    def _load_online_order_to_cart(self, order: dict):
        """Load an online order's items into the POS cart (called from dialog)."""
        name    = order.get("customer_name") or "Online Order"
        phone   = order.get("customer_phone") or ""
        address = order.get("address") or ""
        notes   = order.get("notes") or ""

        # Put current cart on hold if it has items
        if self._lines:
            self._hold_sale()

        self._active_online_order_id = order.get("id", "")

        raw_items = order.get("items") or []
        self._lines.clear()
        for d in raw_items:
            item_id = d.get("id") or d.get("item_id", "")
            code    = d.get("code", "")
            desc    = d.get("name") or d.get("description", "")
            qty     = float(d.get("qty", 1))
            price   = float(d.get("price") or d.get("unit_price", 0))
            vat_pct = 0.0
            barcode = ""
            try:
                detail = ItemService.get_item_detail(item_id)
                if detail:
                    vat_pct = getattr(detail, "vat_pct", 0.0) or 0.0
                    barcode = getattr(detail, "barcode", "") or ""
                    if not code:
                        code = getattr(detail, "code", "") or ""
            except Exception:
                pass
            it = PosLineItem(
                item_id    = item_id,
                code       = code,
                barcode    = barcode,
                description= desc,
                qty        = qty,
                unit_price = price,
                disc_pct   = 0.0,
                vat_pct    = vat_pct,
                total      = round(price * qty, 2),
                currency   = self._currency,
            )
            self._lines.append({
                "item":  it,
                "qty":   qty,
                "price": price,
                "disc":  0.0,
                "total": round(price * qty, 2),
            })

        self._customer_name = name
        self._cust_name_lbl.setText(name)
        delivery_parts = []
        if phone:   delivery_parts.append(f"📞 {phone}")
        if address: delivery_parts.append(f"📍 {address}")
        if notes:   delivery_parts.append(f"📝 {notes}")
        if delivery_parts:
            self._delivery_lbl.setText("\n".join(delivery_parts))
            self._delivery_lbl.setVisible(True)
        else:
            self._delivery_lbl.setVisible(False)

        self._refresh_table()
        self._scan_input.setFocus()

    # ── Line actions ───────────────────────────────────────────────────────────

    def _refresh_held_panel(self):
        self._held_list.clear()
        held = PosService.list_held_sales()
        for h in held:
            it = QListWidgetItem(
                f"  {h['label']}  —  ل.ل {h['total']:,.0f}  [{h['created_at'][11:16]}]"
            )
            it.setData(Qt.UserRole, h)
            self._held_list.addItem(it)

    def _recall_from_panel(self, item):
        h = item.data(Qt.UserRole)
        try:
            lines_data = json.loads(h["items_json"])
        except Exception:
            return
        if self._lines:
            from PySide6.QtWidgets import QMessageBox as MB
            r = MB.question(self, "Replace Cart",
                            "Replace current items with held invoice?",
                            MB.Yes | MB.No)
            if r != MB.Yes:
                return
        PosService.delete_held_sale(h["id"])
        self._lines.clear()
        for d in lines_data:
            it = PosLineItem(
                item_id    = d["item_id"],
                code       = d.get("code", ""),
                barcode    = d.get("barcode", ""),
                description= d["description"],
                qty        = d["qty"],
                unit_price = d["unit_price"],
                disc_pct   = d["disc_pct"],
                vat_pct    = d.get("vat_pct", 0.0),
                total      = d["total"],
                currency   = d.get("currency", self._currency),
            )
            self._lines.append({
                "item":  it,
                "qty":   d["qty"],
                "price": d["unit_price"],
                "disc":  d["disc_pct"],
                "total": d["total"],
            })
        self._refresh_table()
        self._refresh_held_panel()

    def _open_invoices(self):
        user = AuthService.current_user()
        dlg = SalesListDialog(
            self,
            warehouse_id=self._warehouse_id,
            operator_id=user.id if user else "",
        )
        dlg.exec()
        if dlg.edit_lines:
            self._load_invoice_into_cart(dlg.edit_lines)

    def _load_invoice_into_cart(self, lines: list[dict]):
        """Load saved invoice lines back into the current cart for editing."""
        if self._lines:
            if QMessageBox.question(
                self, "Replace Cart",
                "Replace current items with the invoice being edited?",
                QMessageBox.Yes | QMessageBox.No,
            ) != QMessageBox.Yes:
                return
        self._lines.clear()
        for l in lines:
            item = PosLineItem(
                item_id    = l["item_id"],
                code       = "",
                barcode    = l["barcode"],
                description= l["description"],
                qty        = l["qty"],
                unit_price = l["unit_price"],
                disc_pct   = l["disc_pct"],
                vat_pct    = l["vat_pct"],
                total      = l["total"],
                currency   = l["currency"],
            )
            self._lines.append({
                "item":  item,
                "qty":   l["qty"],
                "price": l["unit_price"],
                "disc":  l["disc_pct"],
                "total": l["total"],
            })
        self._refresh_table()
        self._update_totals()

    def _new_sale(self):
        self._lines.clear()
        self._global_disc.setValue(0.0)
        self._customer_id   = PosService.get_walk_in_customer_id(self._warehouse_id)
        self._customer_name = self._resolve_customer_name(self._customer_id)
        self._cust_name_lbl.setText(self._customer_name)
        self._delivery_lbl.setText("")
        self._delivery_lbl.setVisible(False)
        self._active_online_order_id = ""
        self._box_bar.setVisible(False)
        self._last_pack_qty = 1
        self._refresh_table()
        self._scan_input.setFocus()

    # ── Elevation guard ────────────────────────────────────────────────────────

    def _require_elevated(self, action: str = "this action") -> bool:
        """
        Returns True if the current user may perform a restricted action.
        - admin / manager / power_user  → True immediately (no prompt)
        - cashier                       → show manager login dialog; True if verified
        """
        user = AuthService.current_user()
        if user and (user.role in ("admin", "manager") or user.is_power_user):
            return True
        # Ask for a manager / power-user's credentials
        dlg = _ElevationDialog(action, parent=self)
        return dlg.exec() == QDialog.Accepted

    def _clear_all(self):
        if not self._require_elevated("Clear All"):
            return
        self._new_sale()

    def _void_line(self):
        """Del key — void the selected line (adds negative entry)."""
        if not self._require_elevated("Void Line"):
            return
        row = self._table.currentRow()
        if 0 <= row < len(self._lines):
            self._void_or_delete(row)

    def _void_or_delete(self, row: int, force_delete: bool = False):
        """
        Normal press  → void (add a negative-qty mirror line).
        Ctrl+click or manager role → actually remove the line (requires PIN).
        """
        if row < 0 or row >= len(self._lines):
            return

        from PySide6.QtWidgets import QApplication
        ctrl_held = bool(QApplication.keyboardModifiers() & Qt.ControlModifier)

        if ctrl_held or force_delete:
            if not self._require_elevated("Delete Line"):
                return
            del self._lines[row]
        else:
            # Void: append a negative-qty copy
            orig = self._lines[row]
            void_item = PosLineItem(
                item_id    = orig["item"].item_id,
                code       = orig["item"].code,
                barcode    = orig["item"].barcode,
                description= f"VOID — {orig['item'].description}",
                qty        = -orig["qty"],
                unit_price = orig["price"],
                disc_pct   = orig["disc"],
                vat_pct    = orig["item"].vat_pct,
                total      = -orig["total"],
                currency   = orig["item"].currency,
            )
            self._lines.append({
                "item":  void_item,
                "qty":   -orig["qty"],
                "price": orig["price"],
                "disc":  orig["disc"],
                "total": -orig["total"],
                "voided": True,
            })

        self._refresh_table()

    def _increment_qty(self):
        row = self._table.currentRow()
        if row < 0 and self._lines:
            row = len(self._lines) - 1
        if 0 <= row < len(self._lines):
            step = getattr(self._lines[row]["item"], "qty", 1) or 1
            self._lines[row]["qty"] += step
            self._recalc_line(row)
            self._refresh_table()
            self._table.selectRow(row)
            self._update_box_bar(row)

    def _decrement_qty(self):
        row = self._table.currentRow()
        if row < 0 and self._lines:
            row = len(self._lines) - 1
        if 0 <= row < len(self._lines):
            step = getattr(self._lines[row]["item"], "qty", 1) or 1
            self._lines[row]["qty"] = max(step, self._lines[row]["qty"] - step)
            self._recalc_line(row)
            self._refresh_table()
            self._table.selectRow(row)
            self._update_box_bar(row)

    # ── Touch Mode ─────────────────────────────────────────────────────────────

    def _toggle_touch_mode(self):
        if self._fn_stack.currentIndex() == 0:
            self._touch_panel.refresh()
            self._fn_stack.setCurrentIndex(1)
            self._touch_mode_btn.setStyleSheet(
                "QPushButton{background:#ff6f00;color:#fff;font-size:12px;font-weight:700;"
                "border:none;border-radius:5px;}"
                "QPushButton:hover{background:#e65100;}"
            )
            self._touch_mode_btn.setText("✕  Exit Touch")
        else:
            self._exit_touch_mode()

    def _exit_touch_mode(self):
        self._fn_stack.setCurrentIndex(0)
        self._touch_mode_btn.setStyleSheet(
            "QPushButton{background:#00838f;color:#fff;font-size:12px;font-weight:700;"
            "border:none;border-radius:5px;}"
            "QPushButton:hover{background:#006064;}"
        )
        self._touch_mode_btn.setText("⊞  Touch Mode")

    def _on_touch_item(self, item_dict: dict):
        """Item tile pressed in touch mode — add to cart."""
        from services.pos_service import PosLineItem
        lbp_price = item_dict["price"]
        if item_dict["currency"] != "LBP":
            lbp_price = round(item_dict["price"] * LBP_RATE)
        line = PosLineItem(
            item_id    = item_dict["item_id"],
            code       = item_dict["code"],
            barcode    = "",
            description= item_dict["name"],
            qty        = 1.0,
            unit_price = lbp_price,
            disc_pct   = 0.0,
            vat_pct    = 0.0,
            total      = lbp_price,
            currency   = "LBP",
            price_type = "retail",
        )
        self._add_item(line)

    # ── Customer ───────────────────────────────────────────────────────────────

    def _refresh_prices(self):
        """Push pending price changes then pull latest items/prices from Supabase."""
        if getattr(self, "_prices_syncing", False):
            return
        self._prices_syncing = True
        self._refresh_prices_btn.setEnabled(False)
        self._refresh_prices_btn.setText("↻  Syncing…")

        # Safety timeout: if pull never finishes (e.g. network dead) reset after 5 mins
        self._prices_timeout_timer = QTimer(self)
        self._prices_timeout_timer.setSingleShot(True)
        self._prices_timeout_timer.timeout.connect(
            lambda: self._finish_prices_sync(error="Timed out — catalog processing too slow")
        )
        self._prices_timeout_timer.start(300_000)

        import threading
        from config import IS_MAIN_BRANCH

        def _pull_then_refresh():
            err_msg = ""
            count   = 0
            try:
                from sync.service import pull_master_items, drain_sync_queue, is_configured, pull_item_prices_only
                from sync.snapshot import apply_master_snapshot
                from config import USE_SNAPSHOT_SYNC, IS_MAIN_BRANCH

                if is_configured():
                    # Main branch pushes pending changes first
                    if IS_MAIN_BRANCH:
                        try:
                            drain_sync_queue()
                        except Exception:
                            pass
                    
                    # Try Snapshot Sync first (Fast Bucket Sync)
                    if USE_SNAPSHOT_SYNC:
                        count, snap_err = apply_master_snapshot()
                        if snap_err:
                            # Fallback if snapshot fails
                            c2, e2 = pull_master_items()
                            count = c2
                            err_msg = f"Snapshot failed ({snap_err}), fallback used: {e2}"
                            # Only pull individual prices if we are NOT in snapshot mode or snapshot failed
                            try:
                                n, _ = pull_item_prices_only()
                                count += n
                            except Exception:
                                pass
                        elif count == -1:
                            # Snapshot not found yet, fallback
                            count, err_msg = pull_master_items()
                            try:
                                n, _ = pull_item_prices_only()
                                count += n
                            except Exception:
                                pass
                        else:
                            # Snapshot success! It already includes all items and prices.
                            # We SKIP the redundant pull_item_prices_only() call.
                            pass
                    else:
                        # Standard cursor-based pull
                        count, err_msg = pull_master_items()
                        try:
                            n, _ = pull_item_prices_only()
                            count += n
                        except Exception:
                            pass
                else:
                    err_msg = "Sync not configured"
            except Exception as e:
                err_msg = str(e)
            QTimer.singleShot(0, lambda: self._finish_prices_sync(max(0, count), err_msg))

        threading.Thread(target=_pull_then_refresh, daemon=True).start()

    def _finish_prices_sync(self, count: int = 0, error: str = ""):
        """Called on main thread when the price pull thread completes or times out."""
        if not getattr(self, "_prices_syncing", False):
            return  # timeout already fired and reset — ignore late thread completion
        self._apply_fresh_cart_prices(update_btn=False)
        if error:
            self._refresh_prices_btn.setText(f"⚠ {error[:30]}")
        else:
            self._refresh_prices_btn.setText(f"✓  {count} updated" if count else "✓  Up to date")
        QTimer.singleShot(3000, self._reset_prices_btn)

    def _reset_prices_btn(self):
        """Restore the prices button to its idle state."""
        self._prices_syncing = False
        try:
            self._prices_timeout_timer.stop()
        except Exception:
            pass
        self._refresh_prices_btn.setEnabled(True)
        self._refresh_prices_btn.setText("↻  Prices")

    def _apply_fresh_cart_prices(self, *, update_btn: bool = False):
        """Re-read prices for cart items from local DB after a pull."""
        try:
            updated = 0
            for row in self._lines:
                li = row.get("item")
                if not li or not li.code:
                    continue
                fresh = PosService.lookup_item(
                    li.code, "code",
                    currency=li.currency,
                    price_type=li.price_type,
                )
                if fresh and fresh.unit_price != li.unit_price:
                    li.unit_price = fresh.unit_price
                    li.total      = round(fresh.unit_price * li.qty)
                    row["price"]  = fresh.unit_price
                    row["total"]  = li.total
                    updated += 1
            if updated:
                self._refresh_table()
        except Exception:
            pass

    def _toggle_print(self):
        self._print_copies = (self._print_copies + 1) % 3   # 0→1→2→0
        self._print_enabled = self._print_copies > 0
        if self._print_copies == 1:
            self._print_toggle_btn.setText("🖨 Print: ON")
            self._print_toggle_btn.setStyleSheet(
                "QPushButton{background:#2e7d32;color:#fff;border:none;"
                "border-radius:3px;padding:0 10px;font-size:11px;font-weight:700;}"
                "QPushButton:hover{background:#1b5e20;}"
            )
        elif self._print_copies == 2:
            self._print_toggle_btn.setText("🖨 Print: ×2")
            self._print_toggle_btn.setStyleSheet(
                "QPushButton{background:#f57f17;color:#fff;border:none;"
                "border-radius:3px;padding:0 10px;font-size:11px;font-weight:700;}"
                "QPushButton:hover{background:#e65100;}"
            )
        else:
            self._print_toggle_btn.setText("🖨 Print: OFF")
            self._print_toggle_btn.setStyleSheet(
                "QPushButton{background:#546e7a;color:#cfd8dc;border:none;"
                "border-radius:3px;padding:0 10px;font-size:11px;font-weight:700;}"
                "QPushButton:hover{background:#37474f;}"
            )

    def _change_customer(self):
        from PySide6.QtWidgets import QInputDialog
        query, ok = QInputDialog.getText(self, "Customer Search", "Search customer:")
        if not ok or not query.strip():
            return
        results = PosService.search_customers(query.strip())
        if not results:
            QMessageBox.information(self, "Not Found", "No customer matched.")
            return
        if len(results) == 1:
            c = results[0]
        else:
            dlg = QDialog(self)
            dlg.setWindowTitle("Select Customer")
            dlg.setFixedSize(380, 280)
            vl = QVBoxLayout(dlg)
            vl.setContentsMargins(12, 12, 12, 12)
            lst = QListWidget()
            lst.setStyleSheet("font-size:13px;")
            for c in results:
                it = QListWidgetItem(f"  {c['name']}  — {c['phone']}")
                it.setData(Qt.UserRole, c)
                lst.addItem(it)
            lst.itemDoubleClicked.connect(lambda _: dlg.accept())
            vl.addWidget(lst)
            bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
            bb.accepted.connect(dlg.accept)
            bb.rejected.connect(dlg.reject)
            vl.addWidget(bb)
            if not dlg.exec() or not lst.currentItem():
                return
            c = lst.currentItem().data(Qt.UserRole)
        self._customer_id   = c["id"]
        self._customer_name = c["name"]
        self._cust_name_lbl.setText(c["name"])

    # ── Price check ────────────────────────────────────────────────────────────

    def _price_check(self):
        dlg = QDialog(self)
        dlg.setWindowTitle("POS Price Checking")
        dlg.setMinimumSize(560, 400)
        dlg.resize(600, 440)
        dlg.setStyleSheet("background:#fff;")

        lay = QVBoxLayout(dlg)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.setSpacing(8)

        # ── Barcode row ───────────────────────────────────────────────────
        bc_row = QHBoxLayout()
        bc_lbl = QLabel("Barcode:")
        bc_lbl.setStyleSheet("font-size:13px;font-weight:700;color:#1a1a2e;")
        bc_row.addWidget(bc_lbl)

        bc_input = QLineEdit()
        bc_input.setFixedHeight(32)
        bc_input.setStyleSheet(
            "font-size:13px;border:2px solid #1a6cb5;border-radius:3px;"
            "padding:0 8px;background:#fff;color:#1a1a2e;"
        )
        bc_row.addWidget(bc_input, 1)

        search_btn = QPushButton("Search 🔍")
        search_btn.setFixedHeight(32)
        search_btn.setStyleSheet(
            "QPushButton{background:#e8f0fb;color:#1a3a5c;font-size:12px;font-weight:700;"
            "border:1px solid #b0c8e8;border-radius:3px;padding:0 10px;}"
            "QPushButton:hover{background:#c0d8f0;}"
        )
        bc_row.addWidget(search_btn)
        lay.addLayout(bc_row)

        # ── Check button ──────────────────────────────────────────────────
        check_btn = QPushButton("Check  ✔")
        check_btn.setFixedHeight(38)
        check_btn.setStyleSheet(
            "QPushButton{background:#e8e8e8;color:#1a1a2e;font-size:15px;font-weight:700;"
            "border:1px solid #aaa;border-radius:3px;}"
            "QPushButton:hover{background:#d0d0d0;}"
        )
        lay.addWidget(check_btn)

        # ── Result area ───────────────────────────────────────────────────
        result_frame = QFrame()
        result_frame.setStyleSheet(
            "QFrame{background:#fff;border:1px solid #ddd;border-radius:4px;}"
            "QLabel{background:transparent;}"
        )
        rl = QVBoxLayout(result_frame)
        rl.setContentsMargins(12, 10, 12, 10)
        rl.setSpacing(4)

        code_lbl = QLabel("")
        code_lbl.setStyleSheet("font-size:13px;color:#333;")
        rl.addWidget(code_lbl)

        name_lbl = QLabel("")
        name_lbl.setStyleSheet("font-size:20px;font-weight:700;color:#cc0000;")
        name_lbl.setWordWrap(True)
        name_lbl.setMinimumHeight(30)
        rl.addWidget(name_lbl)

        lbp_lbl = QLabel("")
        lbp_lbl.setStyleSheet("font-size:32px;font-weight:700;color:#cc0000;")
        lbp_lbl.setMinimumHeight(42)
        lbp_lbl.setWordWrap(True)
        rl.addWidget(lbp_lbl)

        usd_lbl = QLabel("")
        usd_lbl.setStyleSheet("font-size:26px;font-weight:700;color:#cc0000;")
        usd_lbl.setMinimumHeight(36)
        usd_lbl.setWordWrap(True)
        rl.addWidget(usd_lbl)

        stock_title = QLabel("Stock Units:")
        stock_title.setStyleSheet("font-size:13px;font-weight:700;color:#333;")
        rl.addWidget(stock_title)

        stock_lbl = QLabel("")
        stock_lbl.setStyleSheet("font-size:18px;font-weight:700;color:#1a1a2e;")
        rl.addWidget(stock_lbl)

        lay.addWidget(result_frame, 1)

        # ── Buttons ───────────────────────────────────────────────────────
        btn_row = QHBoxLayout()
        btn_row.addStretch()

        self._pc_item = [None]   # holds last found item

        drop_btn = QPushButton("Drop To\nInvoice  ➕")
        drop_btn.setFixedSize(120, 50)
        drop_btn.setStyleSheet(
            "QPushButton{background:#2e7d32;color:#fff;font-size:11px;font-weight:700;"
            "border:none;border-radius:5px;}"
            "QPushButton:hover{background:#1b5e20;}"
        )

        close_btn = QPushButton("Close  ✕")
        close_btn.setFixedSize(90, 50)
        close_btn.setStyleSheet(
            "QPushButton{background:#c62828;color:#fff;font-size:11px;font-weight:700;"
            "border:none;border-radius:5px;}"
            "QPushButton:hover{background:#a01010;}"
        )
        close_btn.clicked.connect(dlg.reject)

        btn_row.addWidget(drop_btn)
        btn_row.addWidget(close_btn)
        lay.addLayout(btn_row)

        # ── Logic ─────────────────────────────────────────────────────────
        def do_check():
            query = bc_input.text().strip()
            if not query:
                return
            item = PosService.lookup_item(query, currency="USD", price_type=POS_PRICE_TYPE)
            if not item:
                name_lbl.setText("NOT FOUND")
                code_lbl.setText("")
                lbp_lbl.setText("")
                usd_lbl.setText("")
                stock_lbl.setText("")
                self._pc_item[0] = None
                return
            usd_price = item.unit_price if item.currency == "USD" else item.unit_price / LBP_RATE
            lbp_price = item.unit_price * LBP_RATE if item.currency == "USD" else item.unit_price
            self._pc_item[0] = item
            code_lbl.setText(f"Code:   {item.code}")
            name_lbl.setText(item.description)
            lbp_lbl.setText(f"{lbp_price:,.0f} LL")
            usd_lbl.setText(f"{usd_price:.4f} USD")
            stock_lbl.setText(str(int(item.stock_qty)))

        def do_drop():
            if self._pc_item[0]:
                self._add_item(self._pc_item[0])
                dlg.accept()

        check_btn.clicked.connect(do_check)
        search_btn.clicked.connect(do_check)
        bc_input.returnPressed.connect(do_check)
        drop_btn.clicked.connect(do_drop)
        QShortcut(QKeySequence("Escape"), dlg).activated.connect(dlg.reject)

        bc_input.setFocus()
        # Pre-fill if scan input had text
        if self._scan_input.text().strip():
            bc_input.setText(self._scan_input.text().strip())
            do_check()

        dlg.exec()

    # ── Print ──────────────────────────────────────────────────────────────────

    def _print_last(self):
        if not self._last_invoice_id:
            QMessageBox.information(self, "Print", "No sale to print yet.")
            return
        copies = max(1, self._print_copies)  # always at least 1 on F9
        for _ in range(copies):
            self._print_receipt(
                self._last_invoice_id,
                self._last_payment_method,
                self._last_tendered,
                show_preview=True,
            )

    def _print_receipt(
        self,
        invoice_id: str,
        payment_method: str,
        tendered: float,
        show_preview: bool = False,
    ):
        from services.pos_service import PosService
        from utils.receipt_printer import print_receipt
        data = PosService.get_invoice_for_print(invoice_id)
        if not data:
            return
        print_receipt(data, payment_method, tendered, parent=self, show_preview=show_preview)

    def _open_daily_sales(self):
        if not self._require_elevated("Daily Sales / End of Shift"):
            return
        from ui.screens.pos.daily_sales_dialog import DailySalesDialog
        wh_id = getattr(self, "_warehouse_id", "")
        dlg = DailySalesDialog(warehouse_id=wh_id, parent=self)
        dlg.exec()
        if dlg._shift_was_closed:
            # Clear current sale — new shift starts clean
            self._new_sale()
            self._refresh_held_panel()
            # Notify the main window to refresh the Sales module if it's loaded
            main = self.window()
            if hasattr(main, "_modules") and "sales" in main._modules:
                main._modules["sales"].refresh()

    def _open_end_of_shift(self):
        self._open_daily_sales()

    def _placeholder(self):
        QMessageBox.information(self, "Coming Soon", "This feature is coming soon.")

    # ── Helpers ────────────────────────────────────────────────────────────────

    def _update_clock(self):
        from datetime import datetime
        self._clock_lbl.setText(datetime.now().strftime("%a %d %b  %H:%M"))
